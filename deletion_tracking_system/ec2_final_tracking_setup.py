#!/usr/bin/env python3
"""
EC2最終追跡システムセットアップ
EC2上で定期実行と追跡システムを並行実行
"""

import os
import subprocess
import sys
import time
from datetime import datetime

class EC2FinalTrackingSetup:
    def __init__(self):
        """EC2最終追跡システムセットアップの初期化"""
        self.ec2_user = "ubuntu"
        self.ec2_host = None
        self.ec2_path = "/home/ubuntu/convex-scraper"
        self.tracking_path = "/home/ubuntu/deletion-tracking"
        
    def get_ec2_info(self):
        """EC2情報の取得"""
        print("🔧 EC2情報の設定")
        print("=" * 50)
        
        # EC2ホストの入力
        while True:
            ec2_host = input("EC2のIPアドレスまたはホスト名を入力してください: ").strip()
            if ec2_host:
                self.ec2_host = ec2_host
                break
            print("❌ 有効なIPアドレスまたはホスト名を入力してください")
        
        print(f"✅ EC2ホスト: {self.ec2_host}")
        return True
    
    def test_connection(self):
        """EC2接続テスト"""
        print("\n🔍 EC2接続テスト中...")
        try:
            result = subprocess.run(
                f"ssh -o ConnectTimeout=10 {self.ec2_user}@{self.ec2_host} 'echo Connection successful'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                print("✅ EC2接続成功")
                return True
            else:
                print(f"❌ EC2接続失敗: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ EC2接続タイムアウト")
            return False
        except Exception as e:
            print(f"❌ EC2接続エラー: {e}")
            return False
    
    def deploy_tracking_system(self):
        """追跡システムのデプロイ"""
        print("\n📤 追跡システムをデプロイ中...")
        
        try:
            # 追跡システムファイルをアップロード
            files_to_upload = [
                "final_tracking_system.py",
                "tracked_cleanup_tool_final.py"
            ]
            
            for file in files_to_upload:
                if os.path.exists(file):
                    print(f"   📤 {file} をアップロード中...")
                    result = subprocess.run(
                        f"scp {file} {self.ec2_user}@{self.ec2_host}:{self.tracking_path}/",
                        shell=True,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        print(f"   ✅ {file} アップロード完了")
                    else:
                        print(f"   ❌ {file} アップロード失敗: {result.stderr}")
                        return False
                else:
                    print(f"   ⚠️ {file} が見つかりません")
            
            return True
            
        except Exception as e:
            print(f"❌ デプロイエラー: {e}")
            return False
    
    def setup_ec2_services(self):
        """EC2上でサービスをセットアップ"""
        print("\n🔧 EC2上でサービスをセットアップ中...")
        
        setup_script = f"""
# 追跡システムディレクトリ作成
mkdir -p {self.tracking_path}
cd {self.tracking_path}

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
WorkingDirectory={self.tracking_path}
ExecStart=/usr/bin/python3 {self.tracking_path}/tracking_monitor_final.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# 追跡監視スクリプトを作成
cat > tracking_monitor_final.py << 'MONITOR_EOF'
#!/usr/bin/env python3
\"\"\"
EC2上での最終削除追跡監視システム
24時間常時動作で削除操作を監視
\"\"\"

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
        logging.FileHandler('{self.tracking_path}/tracking_final.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EC2FinalDeletionTracker:
    def __init__(self):
        \"\"\"EC2最終削除追跡システムの初期化\"\"\"
        self.tracker = FinalTrackingSystem()
        self.last_check = datetime.now()
        logger.info("✅ EC2最終削除追跡システム開始")

    def monitor_deletions(self):
        \"\"\"削除操作の監視\"\"\"
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
                logger.error(f"❌ 監視エラー: {{e}}")
                time.sleep(60)  # エラー時は1分待機

    def check_deletion_logs(self):
        \"\"\"削除ログのチェック\"\"\"
        try:
            # 最近の削除ログをチェック
            logs = self.tracker.query_logs_by_operation('cleanup', limit=10)
            
            if logs:
                logger.info(f"📊 最近の削除操作: {{len(logs)}}件")
                
                # 最新の削除操作をログに記録
                for log in logs[:3]:  # 最新3件
                    timestamp = log.get('timestamp', 'N/A')
                    table = log.get('table_name', 'N/A')
                    operation = log.get('operation_type', 'N/A')
                    function = log.get('function_name', 'N/A')
                    
                    logger.info(f"   削除: {{timestamp}} - {{table}} - {{operation}} - {{function}}")
            else:
                logger.info("📊 削除操作なし")
                
        except Exception as e:
            logger.error(f"❌ 削除ログチェックエラー: {{e}}")

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
"""
        
        try:
            result = subprocess.run(
                f"ssh {self.ec2_user}@{self.ec2_host} '{setup_script}'",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("✅ EC2サービスセットアップ完了")
                return True
            else:
                print(f"❌ EC2サービスセットアップ失敗: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ EC2サービスセットアップエラー: {e}")
            return False
    
    def verify_deployment(self):
        """デプロイメントの検証"""
        print("\n🔍 デプロイメントの検証中...")
        
        try:
            # 追跡システムのステータス確認
            result = subprocess.run(
                f"ssh {self.ec2_user}@{self.ec2_host} 'sudo systemctl status deletion-tracker-final.service'",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if "active (running)" in result.stdout:
                print("✅ 追跡システムが正常に動作中")
                return True
            else:
                print(f"⚠️ 追跡システムの状態: {result.stdout}")
                return False
                
        except Exception as e:
            print(f"❌ 検証エラー: {e}")
            return False
    
    def create_monitoring_script(self):
        """監視スクリプトの作成"""
        print("\n📊 監視スクリプトを作成中...")
        
        monitoring_script = f"""#!/bin/bash
\"\"\"
EC2最終追跡システム監視スクリプト
\"\"\"

EC2_USER="{self.ec2_user}"
EC2_HOST="{self.ec2_host}"

echo "🔍 EC2最終追跡システム監視"
echo "=========================================="

# 追跡システムのステータス確認
echo "📊 追跡システムステータス:"
ssh $EC2_USER@$EC2_HOST "sudo systemctl status deletion-tracker-final.service"

# 追跡ログの確認
echo "📋 追跡ログ:"
ssh $EC2_USER@$EC2_HOST "tail -20 {self.tracking_path}/tracking_final.log"

# 削除履歴の確認
echo "🗑️ 削除履歴:"
ssh $EC2_USER@$EC2_HOST "cd {self.tracking_path} && python3 -c 'from final_tracking_system import FinalTrackingSystem; FinalTrackingSystem().analyze_comprehensive_logs(1)'"

# テーブル状況の確認
echo "📊 テーブル状況:"
ssh $EC2_USER@$EC2_HOST "cd {self.tracking_path} && python3 -c 'from final_tracking_system import FinalTrackingSystem; FinalTrackingSystem().analyze_comprehensive_logs(7)'"
"""
        
        try:
            with open("monitor_ec2_final_tracking.sh", "w") as f:
                f.write(monitoring_script)
            
            os.chmod("monitor_ec2_final_tracking.sh", 0o755)
            print("✅ 監視スクリプト作成完了: monitor_ec2_final_tracking.sh")
            return True
            
        except Exception as e:
            print(f"❌ 監視スクリプト作成エラー: {e}")
            return False
    
    def run_setup(self):
        """セットアップの実行"""
        print("🚀 EC2最終追跡システムセットアップ開始")
        print("=" * 60)
        
        # 1. EC2情報の取得
        if not self.get_ec2_info():
            return False
        
        # 2. 接続テスト
        if not self.test_connection():
            return False
        
        # 3. 追跡システムのデプロイ
        if not self.deploy_tracking_system():
            return False
        
        # 4. EC2上でサービスをセットアップ
        if not self.setup_ec2_services():
            return False
        
        # 5. デプロイメントの検証
        if not self.verify_deployment():
            return False
        
        # 6. 監視スクリプトの作成
        if not self.create_monitoring_script():
            return False
        
        print("\n✅ EC2最終追跡システムセットアップ完了")
        print("=" * 60)
        print("📋 利用可能なコマンド:")
        print(f"   ./monitor_ec2_final_tracking.sh              # EC2最終追跡システム監視")
        print(f"   ssh {self.ec2_user}@{self.ec2_host} 'sudo systemctl status deletion-tracker-final.service'  # 追跡システムステータス")
        print(f"   ssh {self.ec2_user}@{self.ec2_host} 'sudo systemctl restart deletion-tracker-final.service'  # 追跡システム再起動")
        print("")
        print("💡 特徴:")
        print("   - 24時間常時追跡")
        print("   - 既存スクレイパーとの統合")
        print("   - 削除操作の自動検出")
        print("   - ログの永続化")
        print("   - 包括的な分析機能")
        
        return True

if __name__ == "__main__":
    setup = EC2FinalTrackingSetup()
    setup.run_setup()
