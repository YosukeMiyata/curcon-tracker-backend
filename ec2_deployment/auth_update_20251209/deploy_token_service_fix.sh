#!/bin/bash
# =====================================
# Token Price Tracker Service Fix Deploy Script
# =====================================

set -e

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# ヘルプ表示
show_help() {
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH>"
    echo "例: $0 -h 1.2.3.4 -k ~/.ssh/my-key.pem"
}

# パラメータ初期化
EC2_HOST=""
SSH_KEY=""
SSH_USER="ubuntu"
SSH_PORT="22"

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

log_info "🚀 トークン価格追跡サービスの修正をデプロイします"

# 1. 修正されたサービスファイルとデプロイスクリプトを転送
log_info "📤 ファイルを転送中..."
scp -i "$SSH_KEY" -P "$SSH_PORT" -o StrictHostKeyChecking=no \
    data_acquisition_system/token_price_tracker/token_price_tracker.service \
    data_acquisition_system/token_price_tracker/token_price_tracker.timer \
    data_acquisition_system/token_price_tracker/deploy_token_price_tracker.sh \
    "$SSH_USER@$EC2_HOST:/home/$SSH_USER/curcon-tracker/data_acquisition_system/token_price_tracker/"

# 2. リモートでデプロイスクリプトを実行（systemdの更新と再起動）
log_info "🔄 リモートでサービスを更新中..."
REMOTE_CMD="cd /home/$SSH_USER/curcon-tracker/data_acquisition_system/token_price_tracker && \
    chmod +x deploy_token_price_tracker.sh && \
    ./deploy_token_price_tracker.sh --update"

ssh -i "$SSH_KEY" -p "$SSH_PORT" -o StrictHostKeyChecking=no "$SSH_USER@$EC2_HOST" "$REMOTE_CMD"

log_info "✅ デプロイ完了！"
log_info "⚠️ 注意: AWS認証情報の更新も必要です。まだの場合は以下のコマンドを実行してください:"
log_info "./ec2_deployment/update_ec2_keys.sh -h $EC2_HOST -k $SSH_KEY"
