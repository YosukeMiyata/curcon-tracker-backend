#!/bin/bash

# =====================================
# EC2定期実行システム状況確認スクリプト
# 複数の定期実行の重複を調査・解決
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

echo "🔍 EC2定期実行システム状況確認"
echo "=========================================="
echo "📍 EC2 IP: $EC2_IP"
echo "👤 ユーザー: $EC2_USER"
echo ""

# SSH接続テスト
log_info "🔍 SSH接続テスト"
if ! ssh -i "$KEY_FILE" -o ConnectTimeout=10 -o StrictHostKeyChecking=no $EC2_USER@$EC2_IP "echo 'SSH接続成功'" 2>/dev/null; then
    log_error "SSH接続に失敗しました。EC2_IPとSSH_KEYを確認してください。"
    exit 1
fi
log_info "✅ SSH接続成功"
echo ""

# 1. systemdサービスの状況確認
log_info "📊 systemdサービス状況確認"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 Convex Scraper関連サービス:"
systemctl list-units --type=service | grep -E "(convex|tracker|deletion)" || echo "関連サービスなし"

echo ""
echo "📋 詳細ステータス:"
if systemctl is-active --quiet convex-scraper; then
    echo "✅ convex-scraper: 実行中"
    systemctl status convex-scraper --no-pager | head -5
else
    echo "❌ convex-scraper: 停止中"
fi

if systemctl is-active --quiet deletion-tracker-final; then
    echo "✅ deletion-tracker-final: 実行中"
    systemctl status deletion-tracker-final --no-pager | head -5
else
    echo "❌ deletion-tracker-final: 停止中"
fi
EOF

echo ""

# 2. 実行中プロセスの確認
log_info "🔍 実行中プロセス確認"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🐍 Pythonプロセス:"
ps aux | grep -E "(python|convex|tracker)" | grep -v grep || echo "Pythonプロセスなし"

echo ""
echo "📊 プロセス詳細:"
ps aux | grep -E "(convex_ec2|tracking_monitor|final_tracking)" | grep -v grep || echo "関連プロセスなし"
EOF

echo ""

# 3. cronジョブの確認
log_info "⏰ cronジョブ確認"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "📋 現在のcronジョブ:"
crontab -l 2>/dev/null || echo "cronジョブなし"

echo ""
echo "🔍 システム全体のcron:"
sudo crontab -l 2>/dev/null || echo "システムcronジョブなし"
EOF

echo ""

# 4. ログファイルの確認
log_info "📄 ログファイル状況確認"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "📊 ログファイルサイズと最新更新:"
echo "Convex Scraper ログ:"
if [ -f /home/ubuntu/convex-scraper/logs/convex.log ]; then
    ls -lh /home/ubuntu/convex-scraper/logs/convex.log
    echo "最新の5行:"
    tail -5 /home/ubuntu/convex-scraper/logs/convex.log
else
    echo "ログファイルが存在しません"
fi

echo ""
echo "Deletion Tracking ログ:"
if [ -f /home/ubuntu/deletion-tracking/tracking_final.log ]; then
    ls -lh /home/ubuntu/deletion-tracking/tracking_final.log
    echo "最新の5行:"
    tail -5 /home/ubuntu/deletion-tracking/tracking_final.log
else
    echo "ログファイルが存在しません"
fi
EOF

echo ""

# 5. 重複実行の検出
log_info "🚨 重複実行検出"
echo "----------------------------------------"
ssh -i "$KEY_FILE" $EC2_USER@$EC2_IP << 'EOF'
echo "🔍 同じファイルを実行しているプロセス:"
ps aux | grep -E "convex_ec2_complete.py" | grep -v grep | wc -l | xargs echo "convex_ec2_complete.py 実行数:"
ps aux | grep -E "tracking_monitor_final.py" | grep -v grep | wc -l | xargs echo "tracking_monitor_final.py 実行数:"

echo ""
echo "🔍 ロックファイル確認:"
if [ -f /home/ubuntu/convex-scraper/.convex_scraper.lock ]; then
    echo "✅ ロックファイル存在:"
    cat /home/ubuntu/convex-scraper/.convex_scraper.lock
else
    echo "❌ ロックファイルなし"
fi
EOF

echo ""

# 6. 推奨解決策の提示
log_info "💡 推奨解決策"
echo "=========================================="
echo "1. 重複サービスの停止:"
echo "   sudo systemctl stop deletion-tracker-final"
echo "   sudo systemctl disable deletion-tracker-final"
echo ""
echo "2. メインサービスの再起動:"
echo "   sudo systemctl restart convex-scraper"
echo ""
echo "3. cronジョブの確認・整理:"
echo "   crontab -l"
echo ""
echo "4. ログの監視:"
echo "   tail -f /home/ubuntu/convex-scraper/logs/convex.log"
echo ""

log_info "✅ 状況確認完了"
echo "上記の推奨解決策を実行して、重複する定期実行を整理してください。"

