#!/bin/bash
# =====================================
# Convex Finance スクレイパー 監視スクリプト
# =====================================

set -e

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# 設定
PROJECT_DIR="/home/ubuntu/convex-scraper"
SERVICE_NAME="convex-scraper"
LOG_FILE="$PROJECT_DIR/logs/convex.log"

# 使用方法表示
show_usage() {
    echo "使用方法: $0 [コマンド]"
    echo ""
    echo "コマンド:"
    echo "  status      サービスステータス表示"
    echo "  logs        最新ログ表示（リアルタイム）"
    echo "  tail        ログの末尾表示"
    echo "  stats       実行統計表示"
    echo "  health      ヘルスチェック実行"
    echo "  restart     サービス再起動"
    echo "  stop        サービス停止"
    echo "  start       サービス開始"
    echo "  install     監視ツールインストール"
    echo "  alert       アラート設定"
    echo ""
    exit 1
}

# サービスステータス表示
show_status() {
    log_info "🔍 Convex Scraperサービスステータス"
    echo "=================================================="
    
    # systemdステータス
    if systemctl is-active --quiet $SERVICE_NAME; then
        log_info "✅ サービス状態: 実行中"
    else
        log_warn "⚠️ サービス状態: 停止中"
    fi
    
    # 詳細ステータス
    systemctl status $SERVICE_NAME --no-pager
    
    echo ""
    log_info "📊 リソース使用状況"
    echo "=================================================="
    
    # CPU・メモリ使用量
    if pgrep -f "convex_ec2_production.py" > /dev/null; then
        PID=$(pgrep -f "convex_ec2_production.py")
        echo "PID: $PID"
        ps -p $PID -o pid,ppid,%cpu,%mem,vsz,rss,tty,stat,start,time,cmd --no-headers
    else
        log_warn "プロセスが見つかりません"
    fi
    
    # ディスク使用量
    echo ""
    log_info "💾 ディスク使用量"
    df -h / | tail -1
    
    # ログファイルサイズ
    if [[ -f "$LOG_FILE" ]]; then
        LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
        echo "ログファイルサイズ: $LOG_SIZE"
    fi
}

# ログ表示（リアルタイム）
show_logs() {
    log_info "📄 リアルタイムログ表示（Ctrl+C で終了）"
    echo "=================================================="
    
    if [[ -f "$LOG_FILE" ]]; then
        tail -f "$LOG_FILE"
    else
        log_warn "ログファイルが見つかりません: $LOG_FILE"
        echo "systemdログを表示します:"
        journalctl -u $SERVICE_NAME -f
    fi
}

# ログ末尾表示
show_tail() {
    local lines=${1:-50}
    log_info "📄 最新ログ ($lines行)"
    echo "=================================================="
    
    if [[ -f "$LOG_FILE" ]]; then
        tail -n $lines "$LOG_FILE"
    else
        log_warn "ログファイルが見つかりません: $LOG_FILE"
        echo "systemdログを表示します:"
        journalctl -u $SERVICE_NAME -n $lines --no-pager
    fi
}

# 実行統計表示
show_stats() {
    log_info "📊 実行統計"
    echo "=================================================="
    
    if [[ -f "$LOG_FILE" ]]; then
        # 成功・エラー回数
        SUCCESS_COUNT=$(grep -c "日本時間保存成功" "$LOG_FILE" 2>/dev/null || echo "0")
        ERROR_COUNT=$(grep -c "❌" "$LOG_FILE" 2>/dev/null || echo "0")
        TOTAL_COUNT=$((SUCCESS_COUNT + ERROR_COUNT))
        
        echo "成功回数: $SUCCESS_COUNT"
        echo "エラー回数: $ERROR_COUNT"
        echo "合計実行回数: $TOTAL_COUNT"
        
        if [[ $TOTAL_COUNT -gt 0 ]]; then
            SUCCESS_RATE=$(echo "scale=1; $SUCCESS_COUNT * 100 / $TOTAL_COUNT" | bc -l 2>/dev/null || echo "0.0")
            echo "成功率: ${SUCCESS_RATE}%"
        fi
        
        # 最新実行時刻
        LATEST_SUCCESS=$(grep "日本時間保存成功" "$LOG_FILE" | tail -1 | cut -d' ' -f1-2 2>/dev/null || echo "N/A")
        echo "最新成功実行: $LATEST_SUCCESS"
        
        # 最新エラー
        LATEST_ERROR=$(grep "❌" "$LOG_FILE" | tail -1 | cut -d' ' -f1-2 2>/dev/null || echo "N/A")
        echo "最新エラー: $LATEST_ERROR"
        
        # 今日のエラー数
        TODAY=$(date +%Y-%m-%d)
        TODAY_ERRORS=$(grep "$TODAY" "$LOG_FILE" | grep -c "❌" 2>/dev/null || echo "0")
        echo "今日のエラー数: $TODAY_ERRORS"
        
    else
        log_warn "ログファイルが見つかりません"
    fi
}

# ヘルスチェック
health_check() {
    log_info "🏥 ヘルスチェック実行"
    echo "=================================================="
    
    local health_score=100
    local issues=()
    
    # サービス稼働チェック
    if ! systemctl is-active --quiet $SERVICE_NAME; then
        health_score=$((health_score - 50))
        issues+=("サービスが停止中")
    fi
    
    # プロセスチェック
    if ! pgrep -f "convex_ec2_production.py" > /dev/null; then
        health_score=$((health_score - 30))
        issues+=("Pythonプロセスが見つからない")
    fi
    
    # ログファイルチェック
    if [[ ! -f "$LOG_FILE" ]]; then
        health_score=$((health_score - 10))
        issues+=("ログファイルが存在しない")
    else
        # 最新ログの時刻チェック（1時間以内か）
        if [[ -s "$LOG_FILE" ]]; then
            LAST_LOG_TIME=$(tail -1 "$LOG_FILE" | cut -d' ' -f1-2 2>/dev/null || echo "")
            if [[ -n "$LAST_LOG_TIME" ]]; then
                LAST_TIMESTAMP=$(date -d "$LAST_LOG_TIME" +%s 2>/dev/null || echo "0")
                CURRENT_TIMESTAMP=$(date +%s)
                TIME_DIFF=$((CURRENT_TIMESTAMP - LAST_TIMESTAMP))
                
                if [[ $TIME_DIFF -gt 3600 ]]; then  # 1時間 = 3600秒
                    health_score=$((health_score - 20))
                    issues+=("1時間以上ログが更新されていない")
                fi
            fi
        fi
    fi
    
    # ディスク容量チェック
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [[ $DISK_USAGE -gt 90 ]]; then
        health_score=$((health_score - 15))
        issues+=("ディスク使用率が90%を超過: ${DISK_USAGE}%")
    elif [[ $DISK_USAGE -gt 80 ]]; then
        health_score=$((health_score - 5))
        issues+=("ディスク使用率が80%を超過: ${DISK_USAGE}%")
    fi
    
    # メモリチェック
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [[ $MEMORY_USAGE -gt 90 ]]; then
        health_score=$((health_score - 10))
        issues+=("メモリ使用率が90%を超過: ${MEMORY_USAGE}%")
    fi
    
    # 結果表示
    if [[ $health_score -ge 90 ]]; then
        log_info "✅ ヘルススコア: $health_score/100 (健全)"
    elif [[ $health_score -ge 70 ]]; then
        log_warn "⚠️ ヘルススコア: $health_score/100 (注意)"
    else
        log_error "❌ ヘルススコア: $health_score/100 (危険)"
    fi
    
    if [[ ${#issues[@]} -gt 0 ]]; then
        echo ""
        log_warn "検出された問題:"
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
    fi
}

# サービス制御
control_service() {
    local action=$1
    
    case $action in
        start)
            log_info "🚀 サービス開始"
            sudo systemctl start $SERVICE_NAME
            ;;
        stop)
            log_info "🛑 サービス停止"
            sudo systemctl stop $SERVICE_NAME
            ;;
        restart)
            log_info "🔄 サービス再起動"
            sudo systemctl restart $SERVICE_NAME
            ;;
    esac
    
    sleep 2
    show_status
}

# 監視ツールインストール
install_monitoring() {
    log_info "📦 監視ツールインストール"
    
    # htop, iotop, netstat
    sudo apt update
    sudo apt install -y htop iotop net-tools bc
    
    # CloudWatch Agentインストール（オプション）
    read -p "CloudWatch Agentをインストールしますか？ (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
        sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
        rm amazon-cloudwatch-agent.deb
        log_info "✅ CloudWatch Agentインストール完了"
        log_info "設定は /opt/aws/amazon-cloudwatch-agent/etc/ で行ってください"
    fi
    
    log_info "✅ 監視ツールインストール完了"
}

# アラート設定
setup_alerts() {
    log_info "🚨 アラート設定"
    
    # Cronジョブでヘルスチェックを定期実行
    CRON_JOB="*/30 * * * * $PWD/monitor_convex.sh health > /tmp/convex_health.log 2>&1"
    
    # 既存のcronジョブをチェック
    if crontab -l 2>/dev/null | grep -q "monitor_convex.sh health"; then
        log_info "ヘルスチェックのcronジョブは既に設定されています"
    else
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        log_info "✅ 30分ごとのヘルスチェックを設定しました"
    fi
    
    # メール通知設定（オプション）
    read -p "メール通知を設定しますか？ (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo apt install -y mailutils
        read -p "通知先メールアドレス: " EMAIL
        
        # アラートスクリプト作成
        cat > /tmp/alert_script.sh << EOF
#!/bin/bash
HEALTH_SCORE=\$($(pwd)/monitor_convex.sh health | grep "ヘルススコア" | grep -o "[0-9]*" | head -1)
if [[ \$HEALTH_SCORE -lt 70 ]]; then
    echo "Convex Scraperのヘルススコアが低下しています: \$HEALTH_SCORE/100" | mail -s "Convex Scraper Alert" $EMAIL
fi
EOF
        chmod +x /tmp/alert_script.sh
        mv /tmp/alert_script.sh ~/convex_alert.sh
        
        # アラートcronジョブ追加
        ALERT_CRON="0 */2 * * * ~/convex_alert.sh"
        (crontab -l 2>/dev/null; echo "$ALERT_CRON") | crontab -
        
        log_info "✅ メール通知設定完了（2時間ごとにチェック）"
    fi
}

# メイン処理
case ${1:-""} in
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    tail)
        show_tail ${2:-50}
        ;;
    stats)
        show_stats
        ;;
    health)
        health_check
        ;;
    start)
        control_service start
        ;;
    stop)
        control_service stop
        ;;
    restart)
        control_service restart
        ;;
    install)
        install_monitoring
        ;;
    alert)
        setup_alerts
        ;;
    *)
        show_usage
        ;;
esac
