#!/bin/bash

# =====================================
# EC2上での最終追跡システムデプロイ
# 定期実行と追跡システムを並行実行
# =====================================

echo "🚀 EC2最終追跡システムデプロイ開始"
echo "========================================"

# 設定変数（実際の値に変更してください）
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"  # 例: 3.112.123.45
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"       # 例: convex-key.pem
SCRAPER_PATH="/home/ubuntu/convex-scraper"
TRACKING_PATH="/home/ubuntu/deletion-tracking"

echo "📋 デプロイ設定:"
echo "   EC2 IP: $EC2_IP"
echo "   ユーザー: $EC2_USER"
echo "   キーファイル: $KEY_FILE"
echo "   スクレイパーパス: $SCRAPER_PATH"
echo "   追跡パス: $TRACKING_PATH"
echo ""

# 1. 追跡システムファイルをEC2にアップロード
echo "1. 追跡システムファイルをアップロード中..."
scp -i $KEY_FILE final_tracking_system.py $EC2_USER@$EC2_IP:$TRACKING_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ final_tracking_system.py アップロード完了"
else
    echo "   ❌ final_tracking_system.py アップロード失敗"
    exit 1
fi

# enhanced_cleanup_tool.py は不要のため削除

scp -i $KEY_FILE tracked_cleanup_tool_final.py $EC2_USER@$EC2_IP:$TRACKING_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ tracked_cleanup_tool_final.py アップロード完了"
else
    echo "   ❌ tracked_cleanup_tool_final.py アップロード失敗"
    exit 1
fi

# 2. EC2上で追跡システムをセットアップ
echo ""
echo "2. EC2上で追跡システムをセットアップ中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# 追跡システムディレクトリ作成
mkdir -p /home/ubuntu/deletion-tracking
cd /home/ubuntu/deletion-tracking

# 必要なパッケージをインストール
pip3 install boto3

# 追跡システムのsystemdサービスを作成
sudo tee /etc/systemd/system/deletion-tracker-final.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=Final Deletion Tracking System
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/deletion-tracking
ExecStart=/usr/bin/python3 /home/ubuntu/deletion-tracking/tracking_monitor_final.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# 追跡監視スクリプトを作成
cat > tracking_monitor_final.py << 'MONITOR_EOF'
#!/usr/bin/env python3
"""
EC2上での最終削除追跡監視システム
24時間常時動作で削除操作を監視
"""

import boto3
import json
import logging
import time
import os
from datetime import datetime
from final_tracking_system import FinalTrackingSystem

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/ubuntu/deletion-tracking/tracking_final.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EC2FinalDeletionTracker:
    def __init__(self):
        """EC2最終削除追跡システムの初期化"""
        self.tracker = FinalTrackingSystem()
        self.last_check = datetime.now()
        logger.info("✅ EC2最終削除追跡システム開始")

    def monitor_deletions(self):
        """削除操作の監視"""
        logger.info("🔍 削除操作監視開始")
        
        while True:
            try:
                # 現在のテーブル状況をチェック
                current_time = datetime.now()
                
                # 5分ごとにテーブル状況をチェック
                if (current_time - self.last_check).seconds >= 300:
                    logger.info("📊 テーブル状況チェック")
                    self.tracker.analyze_comprehensive_logs(1)
                    self.last_check = current_time
                
                # 削除ログをチェック
                self.check_deletion_logs()
                
                # 30秒待機
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ 監視エラー: {e}")
                time.sleep(60)  # エラー時は1分待機

    def check_deletion_logs(self):
        """削除ログのチェック"""
        try:
            # 最近の削除ログをチェック
            logs = self.tracker.query_logs_by_operation('cleanup', limit=10)
            
            if logs:
                logger.info(f"📊 最近の削除操作: {len(logs)}件")
                
                # 最新の削除操作をログに記録
                for log in logs[:3]:  # 最新3件
                    timestamp = log.get('timestamp', 'N/A')
                    table = log.get('table_name', 'N/A')
                    operation = log.get('operation_type', 'N/A')
                    function = log.get('function_name', 'N/A')
                    
                    logger.info(f"   削除: {timestamp} - {table} - {operation} - {function}")
            else:
                logger.info("📊 削除操作なし")
                
        except Exception as e:
            logger.error(f"❌ 削除ログチェックエラー: {e}")

if __name__ == "__main__":
    tracker = EC2FinalDeletionTracker()
    tracker.monitor_deletions()
MONITOR_EOF

chmod +x tracking_monitor_final.py

# systemdサービスを有効化・開始
sudo systemctl daemon-reload
sudo systemctl enable deletion-tracker-final.service
sudo systemctl start deletion-tracker-final.service

echo "✅ 最終追跡システムセットアップ完了"
EOF

# 3. 既存のスクレイパーとの統合
echo ""
echo "3. 既存スクレイパーとの統合中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# 既存のスクレイパーに追跡機能を追加
cd /home/ubuntu/convex-scraper

# 追跡機能付きスクレイパーを作成
cat > convex_scraper_with_final_tracking.py << 'SCRAPER_EOF'
#!/usr/bin/env python3
"""
追跡機能付きConvexスクレイパー（最終版）
既存のスクレイパーに最終追跡機能を追加
"""

import sys
import os
sys.path.append('/home/ubuntu/deletion-tracking')

from final_tracking_system import FinalTrackingSystem
from data_acquisition_system.convex_ec2_complete import ConvexEC2Complete

class TrackedConvexScraperFinal(ConvexEC2Complete):
    def __init__(self):
        super().__init__()
        self.tracker = FinalTrackingSystem()
    
    def run_complete_job(self):
        """追跡機能付きジョブ実行"""
        try:
            # 既存のスクレイピング処理
            result = super().run_complete_job()
            
            # 削除追跡ログを記録
            self.tracker.logger.info("スクレイピングジョブ実行完了")
            
            return result
        except Exception as e:
            self.tracker.logger.error(f"スクレイピングジョブエラー: {e}")
            raise

if __name__ == "__main__":
    scraper = TrackedConvexScraperFinal()
    scraper.start_production()
SCRAPER_EOF

chmod +x convex_scraper_with_final_tracking.py

echo "✅ 追跡機能付きスクレイパー（最終版）作成完了"
EOF

# 4. 監視スクリプトの作成
echo ""
echo "4. 監視スクリプトを作成中..."
cat > monitor_ec2_final_tracking.sh << 'EOF'
#!/bin/bash
"""
EC2最終追跡システム監視スクリプト
"""

EC2_USER="ubuntu"
EC2_HOST="54.64.254.201"  # 実際のEC2のIPアドレス
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"

echo "🔍 EC2最終追跡システム監視"
echo "=========================================="

# 追跡システムのステータス確認
echo "📊 追跡システムステータス:"
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl status deletion-tracker-final.service"

# 追跡ログの確認
echo "📋 追跡ログ:"
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "tail -20 /home/ubuntu/deletion-tracking/tracking_final.log"

# 削除履歴の確認
echo "🗑️ 削除履歴:"
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "cd /home/ubuntu/deletion-tracking && python3 -c 'from final_tracking_system import FinalTrackingSystem; FinalTrackingSystem().analyze_comprehensive_logs(1)'"

# テーブル状況の確認
echo "📊 テーブル状況:"
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "cd /home/ubuntu/deletion-tracking && python3 -c 'from final_tracking_system import FinalTrackingSystem; FinalTrackingSystem().analyze_comprehensive_logs(7)'"
EOF

chmod +x monitor_ec2_final_tracking.sh

echo "✅ EC2最終追跡システムデプロイ完了"
echo "=========================================="
echo "📋 利用可能なコマンド:"
echo "   ./monitor_ec2_final_tracking.sh              # EC2最終追跡システム監視"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl status deletion-tracker-final.service'  # 追跡システムステータス"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl restart deletion-tracker-final.service'  # 追跡システム再起動"
echo ""
echo "💡 特徴:"
echo "   - 24時間常時追跡"
echo "   - 既存スクレイパーとの統合"
echo "   - 削除操作の自動検出"
echo "   - ログの永続化"
echo "   - 包括的な分析機能"
