#!/bin/bash
# =====================================
# OHLC集約システム デプロイスクリプト
# EC2上でsystemdサービスとして設定し、毎日午前0時に実行
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
    echo "使用方法: $0 [オプション]"
    echo ""
    echo "オプション:"
    echo "  -h, --help     このヘルプを表示"
    echo "  -s, --start    サービスを開始"
    echo "  -t, --test     テスト実行（1回だけ実行）"
    echo "  -m, --monitor  サービス状態を監視"
    echo "  -l, --logs     ログを表示"
    echo "  -u, --update   コードを更新してサービスを再起動"
    echo ""
    echo "例:"
    echo "  $0 --test      # テスト実行"
    echo "  $0 --start     # サービス開始"
    echo "  $0 --monitor   # 状態監視"
}

# 環境チェック
check_environment() {
    log_info "環境チェック中..."
    
    # Python3の確認
    if ! command -v python3 &> /dev/null; then
        log_error "Python3がインストールされていません"
        exit 1
    fi
    
    # pip3の確認
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3がインストールされていません"
        exit 1
    fi
    
    # AWS認証情報の確認
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        log_warn "AWS認証情報が設定されていません"
        log_warn "環境変数または~/.aws/credentialsを確認してください"
    fi
    
    log_info "✅ 環境チェック完了"
}

# 必要なパッケージをインストール
install_dependencies() {
    log_info "依存関係をインストール中..."
    
    # boto3, requestsがインストールされているかチェック
    python3 -c "import boto3" 2>/dev/null || {
        log_info "必要なパッケージをインストール中..."
        pip3 install boto3
    }
    
    log_info "✅ 依存関係インストール完了"
}

# systemdサービスファイルをコピー
setup_systemd_service() {
    log_info "systemdサービスを設定中..."
    
    # サービスファイルをコピー
    sudo cp token_ohlc_aggregator.service /etc/systemd/system/
    sudo cp token_ohlc_aggregator.timer /etc/systemd/system/
    
    # 権限設定
    sudo chmod 644 /etc/systemd/system/token_ohlc_aggregator.service
    sudo chmod 644 /etc/systemd/system/token_ohlc_aggregator.timer
    
    # systemdをリロード
    sudo systemctl daemon-reload
    
    log_info "✅ systemdサービス設定完了"
}

# サービスを有効化・開始
start_service() {
    log_info "サービスを開始中..."
    
    # タイマーを有効化
    sudo systemctl enable token_ohlc_aggregator.timer
    sudo systemctl start token_ohlc_aggregator.timer
    
    # サービス状態を確認
    sudo systemctl status token_ohlc_aggregator.timer --no-pager
    
    log_info "✅ サービス開始完了"
    log_info "次回実行予定: $(sudo systemctl list-timers token_ohlc_aggregator.timer --no-pager | grep token_ohlc_aggregator.timer | awk '{print $1, $2, $3, $4}')"
}

# テスト実行
run_test() {
    log_info "テスト実行中..."
    
    # 実行権限を付与
    chmod +x token_ohlc_aggregator.py
    
    # テスト実行
    python3 token_ohlc_aggregator.py
    
    if [ $? -eq 0 ]; then
        log_info "✅ テスト実行成功"
    else
        log_error "❌ テスト実行失敗"
        exit 1
    fi
}

# サービス状態を監視
monitor_service() {
    log_info "サービス状態を監視中..."
    
    echo "=== タイマー状態 ==="
    sudo systemctl status token_ohlc_aggregator.timer --no-pager
    
    echo ""
    echo "=== サービス状態 ==="
    sudo systemctl status token_ohlc_aggregator.service --no-pager
    
    echo ""
    echo "=== 次回実行予定 ==="
    sudo systemctl list-timers token_ohlc_aggregator.timer --no-pager
    
    echo ""
    echo "=== 最近の実行履歴 ==="
    sudo journalctl -u token_ohlc_aggregator.service --since "24 hours ago" --no-pager
}

# ログを表示
show_logs() {
    log_info "ログを表示中..."
    
    echo "=== 最近のログ ==="
    sudo journalctl -u token_ohlc_aggregator.service --since "24 hours ago" --no-pager -f
}

# コードを更新してサービスを再起動
update_and_restart() {
    log_info "コードを更新してサービスを再起動中..."
    
    # タイマーを停止
    sudo systemctl stop token_ohlc_aggregator.timer
    
    # サービスを再読み込み
    sudo systemctl daemon-reload
    
    # タイマーを再開
    sudo systemctl start token_ohlc_aggregator.timer
    
    log_info "✅ 更新・再起動完了"
}

# メイン処理
main() {
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--start)
            check_environment
            install_dependencies
            setup_systemd_service
            start_service
            ;;
        -t|--test)
            check_environment
            install_dependencies
            run_test
            ;;
        -m|--monitor)
            monitor_service
            ;;
        -l|--logs)
            show_logs
            ;;
        -u|--update)
            update_and_restart
            ;;
        "")
            log_info "OHLC集約システム デプロイスクリプト"
            log_info "使用方法: $0 --help"
            ;;
        *)
            log_error "不明なオプション: $1"
            show_help
            exit 1
            ;;
    esac
}

# スクリプト実行
main "$@"

