#!/bin/bash

# =====================================
# 改善された時間制御スクレイパーデプロイスクリプト
# =====================================

echo "🚀 改善された時間制御スクレイパーデプロイ開始"
echo "=============================================="

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

# 2. バックアップを作成
echo ""
echo "2. 既存ファイルのバックアップを作成中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "cp $SCRAPER_PATH/convex_ec2_improved.py $SCRAPER_PATH/convex_ec2_improved.py.backup.$(date +%Y%m%d_%H%M%S)"
if [ $? -eq 0 ]; then
    echo "   ✅ バックアップ作成完了"
else
    echo "   ⚠️ バックアップ作成に失敗（ファイルが存在しない可能性）"
fi

# 3. 改善されたファイルをアップロード
echo ""
echo "3. 改善されたファイルをアップロード中..."
scp -i $KEY_FILE convex_ec2_improved.py $EC2_USER@$EC2_IP:$SCRAPER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ ファイルアップロード完了"
else
    echo "   ❌ ファイルアップロード失敗"
    exit 1
fi

# 4. ファイル権限を設定
echo ""
echo "4. ファイル権限を設定中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "chmod +x $SCRAPER_PATH/convex_ec2_improved.py"
if [ $? -eq 0 ]; then
    echo "   ✅ 権限設定完了"
else
    echo "   ❌ 権限設定失敗"
    exit 1
fi

# 5. サービス設定を更新（必要に応じて）
echo ""
echo "5. サービス設定を確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl cat convex-scraper | grep ExecStart"
echo ""

# 6. サービスを再起動
echo "6. スクレイパーサービスを再起動中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl start convex-scraper"
if [ $? -eq 0 ]; then
    echo "   ✅ サービス再起動完了"
else
    echo "   ❌ サービス再起動失敗"
    exit 1
fi

# 7. サービス状態を確認
echo ""
echo "7. サービス状態を確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl status convex-scraper --no-pager"
if [ $? -eq 0 ]; then
    echo "   ✅ サービス正常稼働中"
else
    echo "   ❌ サービス異常"
    exit 1
fi

# 8. 初回実行ログを確認
echo ""
echo "8. 初回実行ログを確認中..."
echo "   最新のログを表示します（10行）:"
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo journalctl -u convex-scraper -n 10 --no-pager"

echo ""
echo "🎉 デプロイ完了!"
echo ""
echo "📋 改善された機能:"
echo "   ⏰ 正確な60分間隔実行（累積誤差なし）"
echo "   🔧 効率的なCPU使用率"
echo "   📊 実行時間と次回実行予定時刻の表示"
echo "   🔒 重複実行防止機能"
echo ""
echo "🔍 監視コマンド:"
echo "   リアルタイムログ: ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo journalctl -u convex-scraper -f'"
echo "   サービス状態: ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl status convex-scraper'"
echo "   実行統計: ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo journalctl -u convex-scraper | grep \"実行統計\"'"
echo ""
echo "📊 時間精度確認:"
echo "   次回実行予定時刻: ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo journalctl -u convex-scraper | grep \"次回実行予定\" | tail -1'"
echo ""
echo "🔄 ロールバック（必要に応じて）:"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl stop convex-scraper'"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'cp $SCRAPER_PATH/convex_ec2_improved.py.backup.* $SCRAPER_PATH/convex_ec2_improved.py'"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl start convex-scraper'"
