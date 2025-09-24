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
