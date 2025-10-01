#!/bin/bash

# =====================================
# 統合システム監視スクリプト
# 整理後の単一システムを監視
# =====================================

set -e

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# 設定
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"

# 使用方法表示
show_usage() {
    echo "使用方法: $0 [コマンド]"
    echo ""
    echo "コマンド:"
    echo "  status      システム全体のステータス表示"
    echo "  logs        最新ログ表示（リアルタイム）"
    echo "  health      ヘルスチェック実行"
    echo "  restart     サービス再起動"
    echo "  stats       実行統計表示"
    echo "  cleanup     古いログファイルのクリーンアップ"
    echo "  help        このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 status    # システム状況確認"
    echo "  $0 logs      # リアルタイムログ監視"
    echo "  $0 health    # ヘルスチェック"
    exit 1
}

# システム全体ステータス表示
show_status() {
    log_info "📊 統合システム全体ステータス"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 サービス状況:"
if systemctl is-active --quiet convex-scraper; then
    echo "✅ convex-scraper: 実行中"
    systemctl status convex-scraper --no-pager | head -8
else
    echo "❌ convex-scraper: 停止中"
    systemctl status convex-scraper --no-pager | head -5
fi

echo ""
echo "🐍 実行中プロセス:"
ps aux | grep -E "(convex_ec2|python.*convex)" | grep -v grep || echo "関連プロセスなし"

echo ""
echo "💾 リソース使用状況:"
if pgrep -f "convex_ec2_complete.py" > /dev/null; then
    PID=$(pgrep -f "convex_ec2_complete.py")
    echo "PID: $PID"
    ps -p $PID -o pid,ppid,%cpu,%mem,vsz,rss,tty,stat,start,time,cmd --no-headers
else
    echo "⚠️  convex_ec2_complete.py プロセスが見つかりません"
fi

echo ""
echo "💾 ディスク使用量:"
df -h / | tail -1

echo ""
echo "📄 ログファイル状況:"
if [ -f /home/ubuntu/convex-scraper/logs/convex.log ]; then
    LOG_SIZE=$(du -h /home/ubuntu/convex-scraper/logs/convex.log | cut -f1)
    echo "ログファイルサイズ: $LOG_SIZE"
    echo "最新更新: $(stat -c %y /home/ubuntu/convex-scraper/logs/convex.log 2>/dev/null || stat -f %Sm /home/ubuntu/convex-scraper/logs/convex.log 2>/dev/null || echo 'N/A')"
else
    echo "⚠️  ログファイルが見つかりません"
fi
EOF
}

# ログ表示（リアルタイム）
show_logs() {
    log_info "📄 リアルタイムログ表示（Ctrl+C で終了）"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP "tail -f /home/ubuntu/convex-scraper/logs/convex.log"
}

# ヘルスチェック
health_check() {
    log_info "🏥 ヘルスチェック実行"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
health_score=100
issues=()

echo "🔍 ヘルスチェック項目:"

# サービス稼働チェック
if systemctl is-active --quiet convex-scraper; then
    echo "✅ サービス稼働: OK"
else
    health_score=$((health_score - 50))
    issues+=("サービスが停止中")
    echo "❌ サービス稼働: NG"
fi

# プロセスチェック
if pgrep -f "convex_ec2_complete.py" > /dev/null; then
    echo "✅ Pythonプロセス: OK"
else
    health_score=$((health_score - 30))
    issues+=("Pythonプロセスが見つからない")
    echo "❌ Pythonプロセス: NG"
fi

# ログファイルチェック
if [ -f /home/ubuntu/convex-scraper/logs/convex.log ]; then
    echo "✅ ログファイル: OK"
    
    # 最新ログの時刻チェック（1時間以内か）
    if [ -s /home/ubuntu/convex-scraper/logs/convex.log ]; then
        LAST_LOG_TIME=$(tail -1 /home/ubuntu/convex-scraper/logs/convex.log | cut -d' ' -f1-2 2>/dev/null || echo "")
        if [ -n "$LAST_LOG_TIME" ]; then
            echo "✅ ログ更新: OK (最新: $LAST_LOG_TIME)"
        else
            health_score=$((health_score - 10))
            issues+=("ログの時刻が読み取れない")
            echo "⚠️  ログ更新: 時刻不明"
        fi
    fi
else
    health_score=$((health_score - 10))
    issues+=("ログファイルが存在しない")
    echo "❌ ログファイル: NG"
fi

# ディスク容量チェック
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
    health_score=$((health_score - 15))
    issues+=("ディスク使用率が90%を超過: ${DISK_USAGE}%")
    echo "❌ ディスク容量: 危険 (${DISK_USAGE}%)"
elif [ "$DISK_USAGE" -gt 80 ]; then
    health_score=$((health_score - 5))
    issues+=("ディスク使用率が80%を超過: ${DISK_USAGE}%")
    echo "⚠️  ディスク容量: 注意 (${DISK_USAGE}%)"
else
    echo "✅ ディスク容量: OK (${DISK_USAGE}%)"
fi

# 重複プロセスチェック
CONVEX_COUNT=$(ps aux | grep -c "convex_ec2_complete.py" | grep -v grep || echo "0")
if [ "$CONVEX_COUNT" -gt 1 ]; then
    health_score=$((health_score - 20))
    issues+=("重複プロセスが検出されました: ${CONVEX_COUNT}個")
    echo "❌ プロセス重複: NG (${CONVEX_COUNT}個)"
else
    echo "✅ プロセス重複: OK"
fi

echo ""
echo "📊 ヘルススコア: $health_score/100"

if [ $health_score -ge 90 ]; then
    echo "✅ システム状態: 健全"
elif [ $health_score -ge 70 ]; then
    echo "⚠️  システム状態: 注意"
else
    echo "❌ システム状態: 危険"
fi

if [ ${#issues[@]} -gt 0 ]; then
    echo ""
    echo "🚨 検出された問題:"
    for issue in "${issues[@]}"; do
        echo "  - $issue"
    done
fi
EOF
}

# サービス制御
control_service() {
    local action=$1
    
    log_info "🔧 サービス制御: $action"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << EOF
case "$action" in
    restart)
        echo "🔄 サービス再起動中..."
        sudo systemctl restart convex-scraper
        sleep 3
        ;;
    start)
        echo "🚀 サービス開始中..."
        sudo systemctl start convex-scraper
        sleep 3
        ;;
    stop)
        echo "🛑 サービス停止中..."
        sudo systemctl stop convex-scraper
        ;;
esac

echo "📊 サービス状態:"
systemctl is-active --quiet convex-scraper && echo "✅ 実行中" || echo "❌ 停止中"
systemctl status convex-scraper --no-pager | head -5
EOF
}

# 実行統計表示
show_stats() {
    log_info "📊 実行統計"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
if [ -f /home/ubuntu/convex-scraper/logs/convex.log ]; then
    # 成功・エラー回数
    SUCCESS_COUNT=$(grep -c "日本時間保存成功\|✅.*保存完了" /home/ubuntu/convex-scraper/logs/convex.log 2>/dev/null || echo "0")
    ERROR_COUNT=$(grep -c "❌\|ERROR\|Exception" /home/ubuntu/convex-scraper/logs/convex.log 2>/dev/null || echo "0")
    TOTAL_COUNT=$((SUCCESS_COUNT + ERROR_COUNT))
    
    echo "成功回数: $SUCCESS_COUNT"
    echo "エラー回数: $ERROR_COUNT"
    echo "合計実行回数: $TOTAL_COUNT"
    
    if [ $TOTAL_COUNT -gt 0 ]; then
        SUCCESS_RATE=$(echo "scale=1; $SUCCESS_COUNT * 100 / $TOTAL_COUNT" | bc -l 2>/dev/null || echo "0.0")
        echo "成功率: ${SUCCESS_RATE}%"
    fi
    
    # 最新実行時刻
    LATEST_SUCCESS=$(grep "日本時間保存成功\|✅.*保存完了" /home/ubuntu/convex-scraper/logs/convex.log | tail -1 | cut -d' ' -f1-2 2>/dev/null || echo "N/A")
    echo "最新成功実行: $LATEST_SUCCESS"
    
    # 最新エラー
    LATEST_ERROR=$(grep "❌\|ERROR\|Exception" /home/ubuntu/convex-scraper/logs/convex.log | tail -1 | cut -d' ' -f1-2 2>/dev/null || echo "N/A")
    echo "最新エラー: $LATEST_ERROR"
    
    # 今日のエラー数
    TODAY=$(date +%Y-%m-%d)
    TODAY_ERRORS=$(grep "$TODAY" /home/ubuntu/convex-scraper/logs/convex.log | grep -c "❌\|ERROR\|Exception" 2>/dev/null || echo "0")
    echo "今日のエラー数: $TODAY_ERRORS"
    
else
    echo "⚠️  ログファイルが見つかりません"
fi
EOF
}

# ログクリーンアップ
cleanup_logs() {
    log_info "🧹 ログファイルクリーンアップ"
    echo "=================================================="
    
    ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 現在のログファイル状況:"
ls -lah /home/ubuntu/convex-scraper/logs/ 2>/dev/null || echo "ログディレクトリなし"

echo ""
echo "📦 古いログファイルをアーカイブ中..."
cd /home/ubuntu/convex-scraper/logs/

# 7日以上古いログファイルを圧縮
find . -name "*.log" -mtime +7 -exec gzip {} \; 2>/dev/null || true

# 30日以上古いログファイルを削除
find . -name "*.log.gz" -mtime +30 -delete 2>/dev/null || true

echo "✅ ログクリーンアップ完了"

echo ""
echo "📊 クリーンアップ後の状況:"
ls -lah /home/ubuntu/convex-scraper/logs/ 2>/dev/null || echo "ログディレクトリなし"
EOF
}

# メイン処理
case ${1:-""} in
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    health)
        health_check
        ;;
    restart)
        control_service restart
        ;;
    start)
        control_service start
        ;;
    stop)
        control_service stop
        ;;
    stats)
        show_stats
        ;;
    cleanup)
        cleanup_logs
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        show_usage
        ;;
esac

