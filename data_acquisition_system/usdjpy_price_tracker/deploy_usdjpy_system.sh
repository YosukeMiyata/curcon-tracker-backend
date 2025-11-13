#!/bin/bash

# =====================================
# USD/JPY関連システムのデプロイスクリプト
# - migrate_pricehistory_to_usdjpyhistory.py
# - usdjpy_ohlc_aggregator.py
# - usdjpy_ohlc_aggregator.service
# - usdjpy_ohlc_aggregator.timer
# - convex_ec2_complete.py（USDJPYHistoryテーブル対応）
# =====================================

echo "🚀 USD/JPY関連システムのデプロイ"
echo "========================================"

# 設定変数
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"
SCRAPER_PATH="/home/ubuntu/convex-scraper"
TRACKER_PATH="/home/ubuntu/curcon-tracker/data_acquisition_system"
USDJPY_TRACKER_PATH="/home/ubuntu/curcon-tracker/data_acquisition_system/usdjpy_price_tracker"

echo "📋 デプロイ設定:"
echo "   EC2 IP: $EC2_IP"
echo "   ユーザー: $EC2_USER"
echo "   キーファイル: $KEY_FILE"
echo ""

# 1. 移行スクリプトをアップロード
echo "1. 移行スクリプトをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/usdjpy_price_tracker/migrate_pricehistory_to_usdjpyhistory.py $EC2_USER@$EC2_IP:$USDJPY_TRACKER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ migrate_pricehistory_to_usdjpyhistory.py アップロード完了"
else
    echo "   ❌ migrate_pricehistory_to_usdjpyhistory.py アップロード失敗"
    exit 1
fi

# 2. USDJPY OHLC集約システムをアップロード
echo ""
echo "2. USDJPY OHLC集約システムをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.py $EC2_USER@$EC2_IP:$USDJPY_TRACKER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ usdjpy_ohlc_aggregator.py アップロード完了"
else
    echo "   ❌ usdjpy_ohlc_aggregator.py アップロード失敗"
    exit 1
fi

# 3. Alpha Vantageインポートスクリプトをアップロード
echo ""
echo "3. Alpha Vantageインポートスクリプトをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/usdjpy_price_tracker/import_alphavantage_usdjpy.py $EC2_USER@$EC2_IP:$USDJPY_TRACKER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ import_alphavantage_usdjpy.py アップロード完了"
else
    echo "   ❌ import_alphavantage_usdjpy.py アップロード失敗"
    exit 1
fi

# 4. systemdサービスファイルをアップロード
echo ""
echo "4. systemdサービスファイルをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.service $EC2_USER@$EC2_IP:$USDJPY_TRACKER_PATH/
scp -i $KEY_FILE data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.timer $EC2_USER@$EC2_IP:$USDJPY_TRACKER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ systemdサービスファイル アップロード完了"
else
    echo "   ❌ systemdサービスファイル アップロード失敗"
    exit 1
fi

# 5. convex_ec2_complete.pyをアップロード（定期実行タイミングは変更なし）
echo ""
echo "5. convex_ec2_complete.pyをアップロード中（定期実行タイミングは変更なし）..."
scp -i $KEY_FILE data_acquisition_system/convex_ec2_complete.py $EC2_USER@$EC2_IP:$SCRAPER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ convex_ec2_complete.py アップロード完了"
    echo "   ⏰ 定期実行タイミング（毎時30分）は変更されていません"
else
    echo "   ❌ convex_ec2_complete.py アップロード失敗"
    exit 1
fi

# 6. systemdサービスを設定（EC2上で実行）
echo ""
echo "6. systemdサービスを設定中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# systemdディレクトリにコピー
sudo cp /home/ubuntu/curcon-tracker/data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.service /etc/systemd/system/
sudo cp /home/ubuntu/curcon-tracker/data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.timer /etc/systemd/system/

# systemdをリロード
sudo systemctl daemon-reload

# タイマーを有効化・開始
sudo systemctl enable usdjpy_ohlc_aggregator.timer
sudo systemctl start usdjpy_ohlc_aggregator.timer

# 状態確認
echo "   📊 USDJPY OHLC Aggregator Timer 状態:"
sudo systemctl status usdjpy_ohlc_aggregator.timer --no-pager | head -15

echo "   📊 次回実行予定時刻:"
sudo systemctl list-timers usdjpy_ohlc_aggregator.timer --no-pager
EOF

# 7. convex-scraperサービスの状態確認（再起動はしない）
echo ""
echo "7. convex-scraperサービスの状態確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
if sudo systemctl is-active --quiet convex-scraper; then
    echo "   ✅ convex-scraperサービスは実行中です"
    echo "   ⏰ 次回実行時間（毎時30分）まで待機します"
    echo "   📊 サービス状態:"
    sudo systemctl status convex-scraper --no-pager | head -10
else
    echo "   ⚠️ convex-scraperサービスは実行中ではありません"
    echo "   💡 サービスを開始する場合は以下を実行してください:"
    echo "      sudo systemctl restart convex-scraper"
fi
EOF

echo ""
echo "✅ USD/JPY関連システムのデプロイ完了"
echo "========================================"
echo "📋 デプロイ内容:"
echo "   ✅ migrate_pricehistory_to_usdjpyhistory.py - 移行スクリプト"
echo "   ✅ usdjpy_ohlc_aggregator.py - OHLC集約システム"
echo "   ✅ import_alphavantage_usdjpy.py - Alpha Vantageインポートスクリプト"
echo "   ✅ usdjpy_ohlc_aggregator.service - systemdサービス"
echo "   ✅ usdjpy_ohlc_aggregator.timer - systemdタイマー（毎日0:30 JST）"
echo "   ✅ convex_ec2_complete.py - USDJPYHistoryテーブル対応（定期実行タイミング変更なし）"
echo ""
echo "📋 次のステップ:"
echo "   1. 移行スクリプトを実行（2025-11-13のデータを移行）:"
echo "      ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'cd $USDJPY_TRACKER_PATH && python3 migrate_pricehistory_to_usdjpyhistory.py 2025-11-13'"
echo ""
echo "   2. convex-scraperサービスを再起動（次回実行時間まで待機する場合は不要）:"
echo "      ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl restart convex-scraper'"
echo ""
echo "   3. USDJPY OHLC Aggregatorタイマーの状態確認:"
echo "      ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl status usdjpy_ohlc_aggregator.timer'"
echo ""

