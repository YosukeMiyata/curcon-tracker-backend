#!/bin/bash
# =====================================
# EC2上のAWS認証情報を更新するスクリプト
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
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH>"
    echo ""
    echo "必須パラメータ:"
    echo "  -h, --host     EC2のIPアドレスまたはホスト名"
    echo "  -k, --key      SSH秘密鍵のパス"
    echo ""
    echo "オプション:"
    echo "  -u, --user     ユーザー名 (デフォルト: ubuntu)"
    echo "  -p, --port     SSHポート (デフォルト: 22)"
    echo "  --help         このヘルプを表示"
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

# 新しい認証情報の入力
echo ""
echo "新しいAWS認証情報を入力してください（入力は非表示になります）"
read -s -p "AWS Access Key ID: " AWS_ACCESS_KEY
echo ""
read -s -p "AWS Secret Access Key: " AWS_SECRET_KEY
echo ""
echo ""

if [ -z "$AWS_ACCESS_KEY" ] || [ -z "$AWS_SECRET_KEY" ]; then
    log_error "認証情報が空です。処理を中止します。"
    exit 1
fi

# .envファイルの更新コマンド作成
# 特殊文字のエスケープ処理が必要な場合を考慮して、sedの区切り文字には|を使用
UPDATE_CMD="
sed -i 's|AWS_ACCESS_KEY_ID=.*|AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY|' /home/$SSH_USER/convex-scraper/.env && \
sed -i 's|AWS_SECRET_ACCESS_KEY=.*|AWS_SECRET_ACCESS_KEY=$AWS_SECRET_KEY|' /home/$SSH_USER/convex-scraper/.env
"

log_info "EC2上の認証情報を更新中..."
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "$UPDATE_CMD"

# サービスの再起動
log_info "サービスを再起動して変更を適用中..."
RESTART_CMD="sudo systemctl restart convex-scraper"
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "$RESTART_CMD"

# 状態確認
log_info "サービスの状態を確認中..."
STATUS_CMD="sudo systemctl status convex-scraper --no-pager | head -n 10"
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "$STATUS_CMD"

log_info "✅ 更新完了！"
log_info "ログを確認してエラーが解消されたか確認してください:"
log_info "ssh -i $SSH_KEY $SSH_USER@$EC2_HOST 'tail -f /home/$SSH_USER/convex-scraper/logs/convex_complete.log'"
