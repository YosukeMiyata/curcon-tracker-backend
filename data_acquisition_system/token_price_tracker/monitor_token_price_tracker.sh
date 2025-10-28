#!/bin/bash
# =====================================
# トークン価格追跡システム 監視スクリプト
# サービス状態、ログ、統計情報を表示
# =====================================

set -e

# 色付きログ関数
log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

# ヘルプ表示
show_help() {
    echo "使用方法: $0 [コマンド]"
    echo ""
    echo "コマンド:"
    echo "  status    サービス状態を表示"
    echo "  logs      ログを表示"
    echo "  stats     統計情報を表示"
    echo "  health    ヘルスチェック実行"
    echo "  restart   サービスを再起動"
    echo "  stop      サービスを停止"
    echo "  start     サービスを開始"
    echo ""
    echo "例:"
    echo "  $0 status    # 状態表示"
    echo "  $0 logs      # ログ表示"
    echo "  $0 stats     # 統計表示"
}

# サービス状態を表示
show_status() {
    echo "=== トークン価格追跡システム 状態 ==="
    echo ""
    
    echo "📊 タイマー状態:"
    sudo systemctl status token_price_tracker.timer --no-pager
    echo ""
    
    echo "📊 サービス状態:"
    sudo systemctl status token_price_tracker.service --no-pager
    echo ""
    
    echo "📊 次回実行予定:"
    sudo systemctl list-timers token_price_tracker.timer --no-pager
    echo ""
    
    echo "📊 最近の実行履歴:"
    sudo journalctl -u token_price_tracker.service --since "24 hours ago" --no-pager | tail -20
}

# ログを表示
show_logs() {
    echo "=== トークン価格追跡システム ログ ==="
    echo ""
    
    if [ "${1:-}" = "-f" ]; then
        echo "リアルタイムログ表示中... (Ctrl+Cで終了)"
        sudo journalctl -u token_price_tracker.service -f
    else
        echo "最近のログ:"
        sudo journalctl -u token_price_tracker.service --since "1 hour ago" --no-pager
    fi
}

# 統計情報を表示
show_stats() {
    echo "=== トークン価格追跡システム 統計 ==="
    echo ""
    
    # 実行回数
    echo "📈 実行統計:"
    total_runs=$(sudo journalctl -u token_price_tracker.service --since "7 days ago" --no-pager | grep -c "トークン価格追跡開始" || echo "0")
    successful_runs=$(sudo journalctl -u token_price_tracker.service --since "7 days ago" --no-pager | grep -c "追跡完了" || echo "0")
    failed_runs=$((total_runs - successful_runs))
    
    echo "   過去7日間の実行回数: $total_runs"
    echo "   成功: $successful_runs"
    echo "   失敗: $failed_runs"
    
    if [ $total_runs -gt 0 ]; then
        success_rate=$((successful_runs * 100 / total_runs))
        echo "   成功率: ${success_rate}%"
    fi
    echo ""
    
    # 最後の実行結果
    echo "📊 最後の実行結果:"
    last_run=$(sudo journalctl -u token_price_tracker.service --since "24 hours ago" --no-pager | grep "追跡完了" | tail -1)
    if [ -n "$last_run" ]; then
        echo "   $last_run"
    else
        echo "   過去24時間に実行記録なし"
    fi
    echo ""
    
    # エラー統計
    echo "⚠️ エラー統計:"
    error_count=$(sudo journalctl -u token_price_tracker.service --since "7 days ago" --no-pager | grep -c "ERROR" || echo "0")
    warn_count=$(sudo journalctl -u token_price_tracker.service --since "7 days ago" --no-pager | grep -c "WARN" || echo "0")
    
    echo "   エラー数: $error_count"
    echo "   警告数: $warn_count"
    echo ""
    
    # リソース使用量
    echo "💻 リソース使用量:"
    echo "   CPU使用率: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
    echo "   メモリ使用率: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
    echo "   ディスク使用率: $(df -h / | awk 'NR==2{print $5}')"
}

# ヘルスチェック
run_health_check() {
    echo "=== ヘルスチェック実行 ==="
    echo ""
    
    # サービス状態チェック
    if systemctl is-active --quiet token_price_tracker.timer; then
        log_info "✅ タイマーサービス: アクティブ"
    else
        log_error "❌ タイマーサービス: 非アクティブ"
    fi
    
    # 最近の実行チェック
    last_run=$(sudo journalctl -u token_price_tracker.service --since "2 hours ago" --no-pager | grep "追跡完了" | tail -1)
    if [ -n "$last_run" ]; then
        log_info "✅ 最近の実行: 正常"
        echo "   $last_run"
    else
        log_warn "⚠️ 最近の実行: 2時間以内に実行記録なし"
    fi
    
    # エラーチェック
    recent_errors=$(sudo journalctl -u token_price_tracker.service --since "1 hour ago" --no-pager | grep -c "ERROR" || echo "0")
    if [ $recent_errors -eq 0 ]; then
        log_info "✅ エラー: なし"
    else
        log_warn "⚠️ エラー: 過去1時間に $recent_errors 件"
    fi
    
    # ログファイルチェック
    if [ -f "/var/log/token_price_tracker.log" ]; then
        log_info "✅ ログファイル: 存在"
        log_size=$(du -h /var/log/token_price_tracker.log | cut -f1)
        echo "   サイズ: $log_size"
    else
        log_warn "⚠️ ログファイル: 存在しない"
    fi
    
    echo ""
    log_info "ヘルスチェック完了"
}

# サービス制御
control_service() {
    local action="$1"
    
    case "$action" in
        restart)
            log_info "サービスを再起動中..."
            sudo systemctl restart token_price_tracker.timer
            sudo systemctl restart token_price_tracker.service
            log_info "✅ 再起動完了"
            ;;
        stop)
            log_info "サービスを停止中..."
            sudo systemctl stop token_price_tracker.timer
            sudo systemctl stop token_price_tracker.service
            log_info "✅ 停止完了"
            ;;
        start)
            log_info "サービスを開始中..."
            sudo systemctl start token_price_tracker.timer
            sudo systemctl start token_price_tracker.service
            log_info "✅ 開始完了"
            ;;
        *)
            log_error "不明なアクション: $action"
            exit 1
            ;;
    esac
}

# メイン処理
main() {
    case "${1:-}" in
        status)
            show_status
            ;;
        logs)
            show_logs "${2:-}"
            ;;
        stats)
            show_stats
            ;;
        health)
            run_health_check
            ;;
        restart|stop|start)
            control_service "$1"
            ;;
        -h|--help)
            show_help
            ;;
        "")
            log_info "トークン価格追跡システム 監視スクリプト"
            log_info "使用方法: $0 --help"
            ;;
        *)
            log_error "不明なコマンド: $1"
            show_help
            exit 1
            ;;
    esac
}

# スクリプト実行
main "$@"
