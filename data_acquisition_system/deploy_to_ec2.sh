#!/bin/bash
# =====================================
# EC2上にトークン価格追跡システムをデプロイ
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
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH> [オプション]"
    echo ""
    echo "必須パラメータ:"
    echo "  -h, --host     EC2のIPアドレスまたはホスト名"
    echo "  -k, --key      SSH秘密鍵のパス"
    echo ""
    echo "オプション:"
    echo "  -u, --user     ユーザー名 (デフォルト: ubuntu)"
    echo "  -p, --port     SSHポート (デフォルト: 22)"
    echo "  -t, --test     テスト実行のみ"
    echo "  --help         このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 -h 1.2.3.4 -k ~/.ssh/my-key.pem"
    echo "  $0 -h ec2-1-2-3-4.compute-1.amazonaws.com -k ~/.ssh/my-key.pem -t"
}

# パラメータ初期化
EC2_HOST=""
SSH_KEY=""
SSH_USER="ubuntu"
SSH_PORT="22"
TEST_ONLY=false

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            EC2_HOST="$2"
            shift 2
            ;;
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        -u|--user)
            SSH_USER="$2"
            shift 2
            ;;
        -p|--port)
            SSH_PORT="$2"
            shift 2
            ;;
        -t|--test)
            TEST_ONLY=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "不明なオプション: $1"
            show_help
            exit 1
            ;;
    esac
done

# 必須パラメータチェック
if [ -z "$EC2_HOST" ] || [ -z "$SSH_KEY" ]; then
    log_error "必須パラメータが不足しています"
    show_help
    exit 1
fi

# SSH鍵ファイルの存在確認
if [ ! -f "$SSH_KEY" ]; then
    log_error "SSH鍵ファイルが見つかりません: $SSH_KEY"
    exit 1
fi

# SSH接続テスト
log_info "EC2への接続をテスト中..."
if ! ssh -i "$SSH_KEY" -p "$SSH_PORT" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$SSH_USER@$EC2_HOST" "echo 'SSH接続成功'" >/dev/null 2>&1; then
    log_error "EC2への接続に失敗しました"
    exit 1
fi
log_info "✅ EC2接続成功"

# ファイルをEC2にコピー
log_info "ファイルをEC2にコピー中..."
scp -i "$SSH_KEY" -P "$SSH_PORT" -r data_acquisition_system/token_price_tracker "$SSH_USER@$EC2_HOST:/home/$SSH_USER/curcon-tracker/data_acquisition_system/"

# EC2上でデプロイスクリプトを実行
if [ "$TEST_ONLY" = true ]; then
    log_info "テスト実行中..."
    ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "cd /home/$SSH_USER/curcon-tracker/data_acquisition_system/token_price_tracker && ./deploy_token_price_tracker.sh --test"
else
    log_info "本格デプロイ実行中..."
    ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "cd /home/$SSH_USER/curcon-tracker/data_acquisition_system/token_price_tracker && ./deploy_token_price_tracker.sh --start"
    
    # デプロイ後の状態確認
    log_info "デプロイ後の状態確認中..."
    ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "cd /home/$SSH_USER/curcon-tracker/data_acquisition_system/token_price_tracker && ./monitor_token_price_tracker.sh status"
fi

log_info "✅ デプロイ完了"
