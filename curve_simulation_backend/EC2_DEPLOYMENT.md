# EC2デプロイガイド

## 📋 前提条件

- EC2インスタンス（t3.micro以上）
- Ubuntu 22.04 LTS
- Python 3.8以上
- AWS認証情報（DynamoDB用）
- Ethereum RPC URL（Infura, Alchemy等）

## 🚀 デプロイ手順

### 1. EC2インスタンスにSSH接続

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### 2. リポジトリをクローン

```bash
cd /home/ubuntu
git clone https://github.com/YosukeMiyata/curcon-tracker-backend.git
cd curcon-tracker-backend/curve-sim
```

### 3. 環境変数を設定

```bash
cp .env.example .env
nano .env
```

以下を設定:
```bash
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
ETH_RPC_URL=https://mainnet.infura.io/v3/your-project-id
LOG_LEVEL=INFO
```

### 4. デプロイスクリプト実行

```bash
chmod +x deploy.sh
./deploy.sh --systemd
```

### 5. サービス確認

```bash
# ステータス確認
sudo systemctl status curve-sim

# ログ確認
sudo journalctl -u curve-sim -f

# ヘルスチェック
curl http://localhost:8001/health
```

## 🔧 サービス管理

### 起動

```bash
sudo systemctl start curve_simulation_backend
```

### 停止

```bash
sudo systemctl stop curve_simulation_backend
```

### 再起動

```bash
sudo systemctl restart curve_simulation_backend
```

### 自動起動設定

```bash
sudo systemctl enable curve_simulation_backend
```

### 自動起動解除

```bash
sudo systemctl disable curve_simulation_backend
```

## 📊 監視

### リアルタイムログ

```bash
sudo journalctl -u curve_simulation_backend -f
```

### 過去のログ

```bash
sudo journalctl -u curve_simulation_backend -n 100
```

### システムリソース確認

```bash
# メモリ使用量
free -h

# CPU使用率
top

# ディスク使用量
df -h
```

## 🔒 セキュリティグループ設定

EC2のセキュリティグループで以下のポートを開放:

- **8001** (Curve Simulation API) - 必要に応じて特定のIPのみ許可

## 🐛 トラブルシューティング

### サービスが起動しない

```bash
# ログを確認
sudo journalctl -u curve_simulation_backend -n 50

# 手動起動してエラー確認
cd /home/ubuntu/curve_simulation_backend
source venv/bin/activate
python app.py
```

### DynamoDB接続エラー

```bash
# AWS認証情報を確認
aws sts get-caller-identity

# テーブルの存在確認
aws dynamodb describe-table --table-name SimulationsHistory
```

### Curve初期化エラー

```bash
# RPC URLを確認
echo $ETH_RPC_URL

# curve-fiライブラリを再インストール
pip install --upgrade curve-fi[all]
```

### メモリ不足

```bash
# スワップファイル作成（t3.microの場合）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 📈 パフォーマンス最適化

### Uvicornワーカー数調整

`curve-sim.service`を編集:

```ini
ExecStart=/home/ubuntu/curve-sim/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8001 --workers 2
```

### ログレベル調整

`.env`ファイルで設定:

```bash
LOG_LEVEL=WARNING  # INFO, WARNING, ERROR
```

## 🔄 アップデート手順

```bash
cd /home/ubuntu/curve-sim
git pull origin main
source venv/bin/activate
pip install -r requirements-curve-sim.txt
sudo systemctl restart curve-sim
```

## 📞 サポート

問題が発生した場合は、以下を確認してください:

1. ログファイル: `sudo journalctl -u curve-sim -n 100`
2. サービスステータス: `sudo systemctl status curve-sim`
3. ヘルスチェック: `curl http://localhost:8001/health`
