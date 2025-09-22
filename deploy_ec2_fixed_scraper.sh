#!/bin/bash

# =====================================
# EC2用修正済みスクレイパーデプロイスクリプト
# =====================================

echo "🚀 EC2用修正済みスクレイパーデプロイ開始"
echo "========================================"

# 設定変数（実際の値に変更してください）
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"  # 例: 3.112.123.45
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"       # 例: convex-key.pem
SCRAPER_PATH="/home/ubuntu/convex-scraper"

echo "📋 デプロイ設定:"
echo "   EC2 IP: $EC2_IP"
echo "   ユーザー: $EC2_USER"
echo "   キーファイル: $KEY_FILE"
echo "   パス: $SCRAPER_PATH"
echo ""

# 1. 現在のサービスを停止
echo "1. 現在のスクレイパーサービスを停止中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl stop convex-scraper"
if [ $? -eq 0 ]; then
    echo "   ✅ サービス停止完了"
else
    echo "   ⚠️ サービス停止に失敗（既に停止している可能性）"
fi

# 2. 修正されたファイルをアップロード
echo ""
echo "2. 修正されたファイルをアップロード中..."
scp -i $KEY_FILE convex_ec2_production.py $EC2_USER@$EC2_IP:$SCRAPER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ ファイルアップロード完了"
else
    echo "   ❌ ファイルアップロード失敗"
    exit 1
fi

# 3. ファイル権限を設定
echo ""
echo "3. ファイル権限を設定中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo chmod +x $SCRAPER_PATH/convex_ec2_production.py"
if [ $? -eq 0 ]; then
    echo "   ✅ 権限設定完了"
else
    echo "   ❌ 権限設定失敗"
    exit 1
fi

# 4. サービスを再起動
echo ""
echo "4. スクレイパーサービスを再起動中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl start convex-scraper"
if [ $? -eq 0 ]; then
    echo "   ✅ サービス再起動完了"
else
    echo "   ❌ サービス再起動失敗"
    exit 1
fi

# 5. サービス状態を確認
echo ""
echo "5. サービス状態を確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl status convex-scraper --no-pager"
if [ $? -eq 0 ]; then
    echo "   ✅ サービス正常稼働中"
else
    echo "   ❌ サービス異常"
    exit 1
fi

echo ""
echo "🎉 デプロイ完了!"
echo ""
echo "📋 次のステップ:"
echo "   1. ログを確認してエラーがないかチェック"
echo "   2. 次回実行時にデータ整合性チェックが動作することを確認"
echo ""
echo "🔍 ログ確認コマンド:"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo journalctl -u convex-scraper -f'"
echo ""
echo "📊 データ整合性確認:"
echo "   python3 EC2_Data_Consistency_Repair.py"
