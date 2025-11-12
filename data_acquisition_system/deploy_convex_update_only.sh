#!/bin/bash

# =====================================
# EC2上のConvex Financeスクレイパーを更新（ファイルのみ）
# サービスは再起動せず、次回実行時間（毎時30分）まで待機
# =====================================

echo "🚀 EC2 Convex Financeスクレイパー更新（ファイルのみ）"
echo "========================================"

# 設定変数（実際の値に変更してください）
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"  # 実際のEC2のIPアドレス
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"       # SSHキーファイルのパス
SCRAPER_PATH="/home/ubuntu/convex-scraper"

echo "📋 デプロイ設定:"
echo "   EC2 IP: $EC2_IP"
echo "   ユーザー: $EC2_USER"
echo "   キーファイル: $KEY_FILE"
echo "   スクレイパーパス: $SCRAPER_PATH"
echo ""

# 1. 修正されたスクレイパーファイルをEC2にアップロード
echo "1. 修正されたスクレイパーファイルをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/convex_ec2_complete.py $EC2_USER@$EC2_IP:$SCRAPER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ convex_ec2_complete.py アップロード完了"
else
    echo "   ❌ convex_ec2_complete.py アップロード失敗"
    exit 1
fi

# 2. サービス状態確認（再起動はしない）
echo ""
echo "2. サービス状態確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# サービス状態を確認
if sudo systemctl is-active --quiet convex-scraper; then
    echo "   ✅ サービスは実行中です"
    echo "   ⏰ 次回実行時間（毎時30分）まで待機します"
    echo "   📊 サービス状態:"
    sudo systemctl status convex-scraper --no-pager | head -10
else
    echo "   ⚠️ サービスは実行中ではありません"
    echo "   💡 サービスを開始する場合は以下を実行してください:"
    echo "      sudo systemctl start convex-scraper"
fi
EOF

# 3. デプロイ後の確認
echo ""
echo "3. デプロイ後の確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# プロセス確認
echo "   📊 実行中プロセス:"
ps aux | grep -E '(convex|python.*convex)' | grep -v grep || echo "   実行中のプロセスなし"

# 最新ログの確認
echo "   📋 最新ログ（最後の10行）:"
if [ -f /home/ubuntu/convex-scraper/logs/convex_complete.log ]; then
    tail -10 /home/ubuntu/convex-scraper/logs/convex_complete.log
else
    echo "   ログファイルが見つかりません"
fi
EOF

echo ""
echo "✅ ファイル更新完了"
echo "=========================================="
echo "📋 注意事項:"
echo "   - ファイルは更新されましたが、サービスは再起動していません"
echo "   - 新しいコードを使用するには、次回の実行時間（毎時30分）まで待機します"
echo "   - または、手動でサービスを再起動してください:"
echo "     ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl restart convex-scraper'"
echo ""
echo "💡 変更内容:"
echo "   - CRV/CVX価格取得処理を削除（TokenOHLCDailyテーブルから参照）"
echo "   - USD/JPY為替レートのみ保存"
echo ""

