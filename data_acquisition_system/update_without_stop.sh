#!/bin/bash
# =====================================
# 実行中のサービスを停止せずにプログラムを更新するスクリプト
# 現在実行中のジョブが完了するのを待ってから更新します
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

log_info "🚀 実行中のサービスを停止せずにプログラム更新"
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
cat > /tmp/update_script.sh << 'EOF'
#!/bin/bash
set -e

log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

SCRAPER_PATH="/home/ubuntu/convex-scraper"
LOCK_FILE="$SCRAPER_PATH/.convex_scraper.lock"

# 1. 現在のサービス状態を確認
log_info "📊 現在のサービス状態を確認中..."
if ! sudo systemctl is-active --quiet convex-scraper; then
    log_warn "⚠️  convex-scraperサービスが実行されていません"
    log_info "通常の更新を実行します..."
    UPDATE_METHOD="normal"
else
    log_info "✅ convex-scraperサービスは実行中です"
    UPDATE_METHOD="smooth"
fi

# 2. 新しいファイルを一時場所に配置
log_info "📦 新しいプログラムファイルを配置中..."
if [ -f /tmp/convex_ec2_complete.py ]; then
    # バックアップを作成
    if [ -f "$SCRAPER_PATH/convex_ec2_complete.py" ]; then
        log_info "💾 既存ファイルをバックアップ中..."
        cp "$SCRAPER_PATH/convex_ec2_complete.py" "$SCRAPER_PATH/convex_ec2_complete.py.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # 新しいファイルを配置（まだ実行中プロセスには影響しない）
    log_info "📝 新しいファイルを一時配置中..."
    cp /tmp/convex_ec2_complete.py "$SCRAPER_PATH/convex_ec2_complete.py.new"
    chmod +x "$SCRAPER_PATH/convex_ec2_complete.py.new"
    log_info "✅ 新しいファイルを一時配置しました"
else
    log_error "❌ /tmp/convex_ec2_complete.py が見つかりません"
    exit 1
fi

# 3. utilsディレクトリとslack_notifier.pyを配置
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
fi

# 4. 依存関係の更新（python-dotenv）
log_info "📦 Python依存関係を更新中..."
cd "$SCRAPER_PATH"
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install python-dotenv==1.0.0 --quiet || log_warn "⚠️  python-dotenvインストールに失敗（スキップ）"
    log_info "✅ 依存関係の更新完了"
else
    log_warn "⚠️  仮想環境が見つかりません（スキップ）"
fi

# 5. スムーズな更新（実行中のジョブ完了を待つ）
if [ "$UPDATE_METHOD" = "smooth" ]; then
    log_info "⏳ 実行中のジョブが完了するのを待機中..."
    log_info "   （ロックファイルの解放を待っています）"
    
    # 最大10分待機（60分間隔の実行なので、通常はすぐに完了する）
    MAX_WAIT=600
    WAIT_INTERVAL=10
    ELAPSED=0
    
    while [ $ELAPSED -lt $MAX_WAIT ]; do
        if [ ! -f "$LOCK_FILE" ]; then
            log_info "✅ ロックファイルが解放されました（ジョブ完了）"
            break
        fi
        
        # ロックファイルの内容を確認（PIDが存在するか）
        if [ -f "$LOCK_FILE" ]; then
            LOCK_PID=$(head -n 1 "$LOCK_FILE" 2>/dev/null || echo "")
            if [ -n "$LOCK_PID" ] && ! ps -p "$LOCK_PID" > /dev/null 2>&1; then
                log_info "✅ ロックファイルのプロセスが終了しました"
                rm -f "$LOCK_FILE"
                break
            fi
        fi
        
        sleep $WAIT_INTERVAL
        ELAPSED=$((ELAPSED + WAIT_INTERVAL))
        
        if [ $((ELAPSED % 60)) -eq 0 ]; then
            log_info "   ⏳ 待機中... ($ELAPSED秒経過)"
        fi
    done
    
    if [ -f "$LOCK_FILE" ]; then
        log_warn "⚠️  ロックファイルが残っていますが、更新を続行します"
        log_warn "   （次の実行サイクルで新しいコードが適用されます）"
    fi
fi

# 6. ファイルを実際に置き換え
log_info "🔄 プログラムファイルを更新中..."
mv "$SCRAPER_PATH/convex_ec2_complete.py.new" "$SCRAPER_PATH/convex_ec2_complete.py"
log_info "✅ プログラムファイルの更新完了"

# 7. systemdサービスをリロード（再起動はしない）
log_info "🔄 systemdサービス設定をリロード中..."
sudo systemctl daemon-reload

# 8. サービスが実行中の場合は、次の実行サイクルで新しいコードが使われることを確認
if [ "$UPDATE_METHOD" = "smooth" ] && sudo systemctl is-active --quiet convex-scraper; then
    log_info "✅ 更新完了！"
    log_info "   📌 現在実行中のジョブは既存のコードで完了します"
    log_info "   📌 次回の実行サイクルから新しいコードが使用されます"
    log_info "   📌 サービスは継続実行中です（停止されていません）"
    
    # サービス状態を確認
    log_info "📊 サービス状態:"
    sudo systemctl status convex-scraper --no-pager | head -15 || true
else
    log_info "✅ 更新完了！"
    log_info "   📌 サービスは現在停止中です"
    log_info "   📌 必要に応じて 'sudo systemctl start convex-scraper' で開始してください"
fi

log_info "🎉 プログラム更新が正常に完了しました！"
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
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no /tmp/update_script.sh ubuntu@"$EC2_IP":/tmp/
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "chmod +x /tmp/update_script.sh && /tmp/update_script.sh"

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

