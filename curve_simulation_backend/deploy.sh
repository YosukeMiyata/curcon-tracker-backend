#!/bin/bash
# Curve Simulation Backend API デプロイスクリプト

set -e

echo "🚀 Curve Simulation Backend API デプロイ開始"

# 1. 仮想環境作成
python3 -m venv venv
source venv/bin/activate

# 2. 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt

# 3. systemdサービス設定
sudo cp curve-simulation-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable curve-simulation-backend
sudo systemctl restart curve-simulation-backend

echo "✅ デプロイ完了"
echo "📊 ステータス確認: sudo systemctl status curve-simulation-backend"
echo "📝 ログ確認: sudo journalctl -u curve-simulation-backend -f"
