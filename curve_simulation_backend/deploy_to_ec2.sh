#!/bin/bash
# =====================================
# Curve Simulation Backend EC2デプロイスクリプト
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
    echo "  --help         このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 -h 1.2.3.4 -k ~/.ssh/my-key.pem"
    echo "  $0 -h ec2-1-2-3-4.compute-1.amazonaws.com -k ~/.ssh/my-key.pem"
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

# 必要なファイルの存在確認
REQUIRED_FILES=("app.py" "blockchain.py" "requirements.txt" "deploy.sh" "curve-simulation-backend.service")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        log_error "必要なファイルが見つかりません: $file"
        exit 1
    fi
done

log_info "🚀 Curve Simulation Backend デプロイ開始"

# SSH接続テスト
log_info "EC2への接続をテスト中..."
if ! ssh -i "$SSH_KEY" -p "$SSH_PORT" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$SSH_USER@$EC2_HOST" "echo 'SSH接続成功'" > /dev/null 2>&1; then
    log_error "EC2への接続に失敗しました"
    exit 1
fi
log_info "✅ EC2接続成功"

# EC2上にディレクトリを作成
log_info "EC2上にディレクトリを作成中..."
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_USER@$EC2_HOST" "mkdir -p /home/$SSH_USER/curve_simulation_backend"

# ファイルをEC2にコピー
log_info "ファイルをEC2にコピー中..."
scp -i "$SSH_KEY" -P "$SSH_PORT" \
    app.py \
    blockchain.py \
    requirements.txt \
    deploy.sh \
    curve-simulation-backend.service \
    "$SSH_USER@$EC2_HOST:/home/$SSH_USER/curve_simulation_backend/"

log_info "✅ ファイルのコピー完了"

# 環境変数ファイルの作成を案内
log_warn "⚠️  次のステップ: EC2上で環境変数ファイルを作成してください"
echo ""
echo "以下のコマンドでEC2に接続し、.envファイルを作成してください:"
echo ""
echo "  ssh -i $SSH_KEY $SSH_USER@$EC2_HOST"
echo "  cd /home/$SSH_USER/curve_simulation_backend"
echo "  nano .env"
echo ""
echo ".envファイルの内容:"
echo "---"
echo "AWS_REGION=ap-northeast-1"
echo "AWS_ACCESS_KEY_ID=<YOUR-ACCESS-KEY-ID>"
echo "AWS_SECRET_ACCESS_KEY=<YOUR-SECRET-ACCESS-KEY>"
echo "ETH_RPC_URL=<YOUR-RPC-URL>"
echo "LOG_LEVEL=INFO"
echo "---"
echo ""
echo ".envファイルを作成後、以下のコマンドでデプロイを実行してください:"
echo ""
echo "  chmod +x deploy.sh"
echo "  ./deploy.sh"
echo ""
