#!/bin/bash

# =====================================
# EC2重複定期実行システム整理スクリプト
# 複数の定期実行を適切に統合・整理
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

echo "🔧 EC2重複定期実行システム整理"
echo "=========================================="
echo "📍 EC2 IP: $EC2_IP"
echo "👤 ユーザー: $EC2_USER"
echo ""

# 確認プロンプト
read -p "⚠️  このスクリプトは重複するサービスを停止します。続行しますか？ (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "処理をキャンセルしました。"
    exit 0
fi

# SSH接続テスト
log_info "🔍 SSH接続テスト"
if ! ssh -i "$KEY_FILE" -o ConnectTimeout=10 -o StrictHostKeyChecking=no $EC2_USER@$EC2_IP "echo 'SSH接続成功'" 2>/dev/null; then
    log_error "SSH接続に失敗しました。"
    exit 1
fi
log_info "✅ SSH接続成功"
echo ""

# 1. 重複サービスの停止
log_info "🛑 重複サービスの停止"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 現在のサービス状況確認..."
systemctl list-units --type=service | grep -E "(convex|tracker|deletion)" || echo "関連サービスなし"

echo ""
echo "🛑 重複サービスの停止..."

# deletion-tracker-finalサービスを停止・無効化
if systemctl is-active --quiet deletion-tracker-final; then
    echo "❌ deletion-tracker-final サービスを停止中..."
    sudo systemctl stop deletion-tracker-final
    sudo systemctl disable deletion-tracker-final
    echo "✅ deletion-tracker-final サービス停止完了"
else
    echo "ℹ️  deletion-tracker-final サービスは既に停止中"
fi

# 古いバージョンのプロセスを強制終了
echo ""
echo "🔍 古いプロセスを検索・終了..."
OLD_PIDS=$(ps aux | grep -E "(tracking_monitor_final|convex_scraper_with_final_tracking)" | grep -v grep | awk '{print $2}' || true)
if [ -n "$OLD_PIDS" ]; then
    echo "古いプロセスを終了中: $OLD_PIDS"
    echo "$OLD_PIDS" | xargs sudo kill -TERM 2>/dev/null || true
    sleep 2
    echo "$OLD_PIDS" | xargs sudo kill -KILL 2>/dev/null || true
    echo "✅ 古いプロセス終了完了"
else
    echo "ℹ️  終了すべき古いプロセスなし"
fi
EOF

echo ""

# 2. メインサービスの確認・再起動
log_info "🔄 メインサービスの確認・再起動"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 convex-scraper サービスの状況..."
if systemctl is-enabled --quiet convex-scraper; then
    echo "✅ convex-scraper サービスは有効"
    
    if systemctl is-active --quiet convex-scraper; then
        echo "✅ convex-scraper サービスは実行中"
        echo "🔄 サービスを再起動中..."
        sudo systemctl restart convex-scraper
        sleep 3
        
        if systemctl is-active --quiet convex-scraper; then
            echo "✅ convex-scraper サービス再起動成功"
        else
            echo "❌ convex-scraper サービス再起動失敗"
            echo "エラー詳細:"
            sudo systemctl status convex-scraper --no-pager | head -10
        fi
    else
        echo "⚠️  convex-scraper サービスが停止中、開始中..."
        sudo systemctl start convex-scraper
        sleep 3
        
        if systemctl is-active --quiet convex-scraper; then
            echo "✅ convex-scraper サービス開始成功"
        else
            echo "❌ convex-scraper サービス開始失敗"
        fi
    fi
else
    echo "❌ convex-scraper サービスが無効、有効化中..."
    sudo systemctl enable convex-scraper
    sudo systemctl start convex-scraper
    sleep 3
    
    if systemctl is-active --quiet convex-scraper; then
        echo "✅ convex-scraper サービス有効化・開始成功"
    else
        echo "❌ convex-scraper サービス有効化・開始失敗"
    fi
fi
EOF

echo ""

# 3. cronジョブの整理
log_info "⏰ cronジョブの整理"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 現在のcronジョブ確認..."
crontab -l 2>/dev/null || echo "cronジョブなし"

echo ""
echo "🧹 重複するcronジョブを削除..."
# ヘルスチェックのcronジョブを削除（systemdサービスで管理するため）
if crontab -l 2>/dev/null | grep -q "monitor_convex.sh health"; then
    echo "⚠️  ヘルスチェックのcronジョブを削除中..."
    crontab -l 2>/dev/null | grep -v "monitor_convex.sh health" | crontab -
    echo "✅ ヘルスチェックのcronジョブ削除完了"
else
    echo "ℹ️  削除すべきヘルスチェックのcronジョブなし"
fi

echo ""
echo "📋 整理後のcronジョブ:"
crontab -l 2>/dev/null || echo "cronジョブなし"
EOF

echo ""

# 4. ログファイルの整理
log_info "📄 ログファイルの整理"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 ログファイルの状況確認..."

# 古いログファイルをアーカイブ
if [ -f /home/ubuntu/deletion-tracking/tracking_final.log ]; then
    echo "📦 古い追跡ログをアーカイブ中..."
    sudo mv /home/ubuntu/deletion-tracking/tracking_final.log /home/ubuntu/deletion-tracking/tracking_final.log.old.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    echo "✅ 古い追跡ログアーカイブ完了"
fi

# ログディレクトリの権限確認
echo ""
echo "🔐 ログディレクトリの権限確認..."
sudo chown -R ubuntu:ubuntu /home/ubuntu/convex-scraper/logs/ 2>/dev/null || true
sudo chown -R ubuntu:ubuntu /home/ubuntu/deletion-tracking/ 2>/dev/null || true

echo ""
echo "📊 現在のログファイル:"
ls -la /home/ubuntu/convex-scraper/logs/ 2>/dev/null || echo "ログディレクトリなし"
ls -la /home/ubuntu/deletion-tracking/ 2>/dev/null || echo "追跡ディレクトリなし"
EOF

echo ""

# 5. 最終確認
log_info "✅ 最終確認"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "📊 実行中サービス:"
systemctl list-units --type=service --state=running | grep -E "(convex|tracker|deletion)" || echo "関連サービスなし"

echo ""
echo "🐍 実行中プロセス:"
ps aux | grep -E "(convex_ec2|python.*convex)" | grep -v grep || echo "関連プロセスなし"

echo ""
echo "📋 最新ログ（最後の3行）:"
if [ -f /home/ubuntu/convex-scraper/logs/convex.log ]; then
    tail -3 /home/ubuntu/convex-scraper/logs/convex.log
else
    echo "ログファイルが見つかりません"
fi
EOF

echo ""
log_info "🎉 システム整理完了！"
echo "=========================================="
echo "📋 整理結果:"
echo "✅ 重複サービスを停止・無効化"
echo "✅ メインサービス（convex-scraper）を再起動"
echo "✅ cronジョブを整理"
echo "✅ ログファイルを整理"
echo ""
echo "🔍 今後の監視方法:"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl status convex-scraper'"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'tail -f /home/ubuntu/convex-scraper/logs/convex.log'"
echo ""
echo "⚠️  注意: 今後は一つのsystemdサービス（convex-scraper）のみが動作します。"

