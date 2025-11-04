#!/bin/bash
# =====================================
# プログラムを素早く更新するスクリプト
# systemdサービスを再起動して新しいコードを適用します
# 再起動は数秒で完了し、Restart=alwaysにより自動的に再開されます
# =====================================

set -e

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# パラメータ確認
if [ $# -lt 4 ]; then
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH>"
    echo "例: $0 -h 54.123.45.67 -k ~/.ssh/convex-key.pem"
    exit 1
fi

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            EC2_IP="$2"
            shift 2
            ;;
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        *)
            echo "不明なオプション: $1"
            exit 1
            ;;
    esac
done

# 必須パラメータ確認
if [ -z "$EC2_IP" ] || [ -z "$SSH_KEY" ]; then
    log_error "EC2_IPとSSH_KEYは必須です"
    exit 1
fi

log_info "🚀 プログラムを素早く更新"
log_info "📍 EC2 IP: $EC2_IP"
log_info "🔑 SSH Key: $SSH_KEY"

# SSH接続テスト
log_info "🔍 SSH接続テスト"
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "echo 'SSH接続成功'" 2>/dev/null; then
    log_error "SSH接続に失敗しました。EC2_IPとSSH_KEYを確認してください。"
    exit 1
fi
log_info "✅ SSH接続成功"

# 更新用スクリプトを作成
cat > /tmp/update_quick_script.sh << 'EOF'
#!/bin/bash
set -e

log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

SCRAPER_PATH="/home/ubuntu/convex-scraper"

# 1. 現在のサービス状態を確認
log_info "📊 現在のサービス状態を確認中..."
if sudo systemctl is-active --quiet convex-scraper; then
    log_info "✅ convex-scraperサービスは実行中です"
    SERVICE_RUNNING=true
else
    log_warn "⚠️  convex-scraperサービスが停止中です"
    SERVICE_RUNNING=false
fi

# 2. バックアップを作成
log_info "💾 既存ファイルをバックアップ中..."
if [ -f "$SCRAPER_PATH/convex_ec2_complete.py" ]; then
    BACKUP_FILE="$SCRAPER_PATH/convex_ec2_complete.py.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$SCRAPER_PATH/convex_ec2_complete.py" "$BACKUP_FILE"
    log_info "✅ バックアップ完了: $(basename $BACKUP_FILE)"
fi

# 3. 新しいファイルを配置
log_info "📦 新しいプログラムファイルを配置中..."
if [ -f /tmp/convex_ec2_complete.py ]; then
    cp /tmp/convex_ec2_complete.py "$SCRAPER_PATH/convex_ec2_complete.py"
    chmod +x "$SCRAPER_PATH/convex_ec2_complete.py"
    log_info "✅ convex_ec2_complete.pyを更新しました"
else
    log_error "❌ /tmp/convex_ec2_complete.py が見つかりません"
    exit 1
fi

# 4. utilsディレクトリとslack_notifier.pyを配置
log_info "📦 utils/slack_notifier.pyを配置中..."
mkdir -p "$SCRAPER_PATH/utils"
if [ -f /tmp/slack_notifier.py ]; then
    cp /tmp/slack_notifier.py "$SCRAPER_PATH/utils/slack_notifier.py"
    chmod +x "$SCRAPER_PATH/utils/slack_notifier.py"
    log_info "✅ utils/slack_notifier.pyを配置しました"
else
    log_warn "⚠️  /tmp/slack_notifier.py が見つかりません（スキップ）"
fi

# utils/__init__.pyを作成
if [ ! -f "$SCRAPER_PATH/utils/__init__.py" ]; then
    echo '"""Utils package"""' > "$SCRAPER_PATH/utils/__init__.py"
    log_info "✅ utils/__init__.pyを作成しました"
fi

# 5. 依存関係の更新（python-dotenv）
log_info "📦 Python依存関係を更新中..."
cd "$SCRAPER_PATH"
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install python-dotenv==1.0.0 --quiet || log_warn "⚠️  python-dotenvインストールに失敗（スキップ）"
    log_info "✅ 依存関係の更新完了"
else
    log_warn "⚠️  仮想環境が見つかりません（スキップ）"
fi

# 6. systemdサービスを再起動
log_info "🔄 systemdサービスを再起動中..."
sudo systemctl daemon-reload

if [ "$SERVICE_RUNNING" = true ]; then
    log_info "   ⏸️  サービスを停止中..."
    sudo systemctl stop convex-scraper
    sleep 2
    
    log_info "   ▶️  サービスを開始中..."
    sudo systemctl start convex-scraper
    sleep 3
    
    # サービス状態を確認
    if sudo systemctl is-active --quiet convex-scraper; then
        log_info "✅ サービス再起動成功"
    else
        log_error "❌ サービス再起動失敗"
        log_info "📊 サービス状態:"
        sudo systemctl status convex-scraper --no-pager | head -20 || true
        exit 1
    fi
else
    log_info "   📌 サービスは停止中でした"
    log_info "   💡 必要に応じて 'sudo systemctl start convex-scraper' で開始してください"
fi

# 7. サービス状態を表示
log_info "📊 サービス状態:"
sudo systemctl status convex-scraper --no-pager | head -15 || true

log_info "🎉 プログラム更新が正常に完了しました！"
log_info ""
log_info "💡 次のステップ:"
log_info "   1. .envファイルにSLACK_WEBHOOK_URLを追加:"
log_info "      nano $SCRAPER_PATH/.env"
log_info "      # SLACK_WEBHOOK_URL=https://hooks.slack.com/services/..."
log_info ""
log_info "   2. ログ確認:"
log_info "      tail -f $SCRAPER_PATH/logs/convex.log"
EOF

# 新しいファイルをEC2に転送
log_info "📤 新しいファイルをEC2に転送中..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    data_acquisition_system/convex_ec2_complete.py \
    ubuntu@"$EC2_IP":/tmp/convex_ec2_complete.py || {
    log_error "convex_ec2_complete.pyの転送に失敗しました"
    exit 1
}

# utils/slack_notifier.pyも転送
log_info "📤 utils/slack_notifier.pyを転送中..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    utils/slack_notifier.py \
    ubuntu@"$EC2_IP":/tmp/slack_notifier.py || {
    log_warn "utils/slack_notifier.pyの転送に失敗しました（スキップ）"
}

# 更新スクリプトを転送・実行
log_info "🚀 更新スクリプトを実行中..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no /tmp/update_quick_script.sh ubuntu@"$EC2_IP":/tmp/
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "chmod +x /tmp/update_quick_script.sh && /tmp/update_quick_script.sh"

log_info "🎉 プログラム更新が完了しました！"
echo ""
echo "📋 更新内容:"
echo "   ✅ convex_ec2_complete.py（Slack通知機能統合）"
echo "   ✅ utils/slack_notifier.py（新規）"
echo "   ✅ python-dotenv依存関係追加"
echo ""
echo "💡 次のステップ:"
echo "   1. .envファイルにSLACK_WEBHOOK_URLを追加:"
echo "      ssh -i $SSH_KEY ubuntu@$EC2_IP"
echo "      nano /home/ubuntu/convex-scraper/.env"
echo "      # SLACK_WEBHOOK_URL=https://hooks.slack.com/services/..."
echo ""
echo "   2. サービス状態確認:"
echo "      ssh -i $SSH_KEY ubuntu@$EC2_IP 'sudo systemctl status convex-scraper'"
echo ""
echo "   3. ログ確認:"
echo "      ssh -i $SSH_KEY ubuntu@$EC2_IP 'tail -f /home/ubuntu/convex-scraper/logs/convex.log'"

