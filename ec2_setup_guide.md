# AWS EC2 移行ガイド - Convex Finance スクレイパー

## 🚀 Phase 1: EC2インスタンス作成

### 1.1 EC2インスタンス起動

```bash
# AWS CLI設定（ローカルから実行）
aws configure
# Access Key ID: your-access-key
# Secret Access Key: your-secret-key  
# Default region: ap-northeast-1 (東京リージョン推奨)
# Default output format: json

# インスタンス作成
aws ec2 run-instances \
    --image-id ami-0d52744d6551d851e \
    --instance-type t3.small \
    --key-name your-key-pair \
    --security-group-ids sg-xxxxxxxxx \
    --subnet-id subnet-xxxxxxxxx \
    --associate-public-ip-address \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ConvexScraper}]'
```

### 1.2 セキュリティグループ設定

```bash
# セキュリティグループ作成
aws ec2 create-security-group \
    --group-name convex-scraper-sg \
    --description "Security group for Convex scraper"

# SSH接続許可（あなたのIPのみ）
aws ec2 authorize-security-group-ingress \
    --group-name convex-scraper-sg \
    --protocol tcp \
    --port 22 \
    --cidr your-ip/32
```

## 🔧 Phase 2: 環境セットアップ

### 2.1 基本パッケージインストール

```bash
# EC2インスタンスにSSH接続後
sudo apt update && sudo apt upgrade -y

# Python環境
sudo apt install -y python3 python3-pip python3-venv git

# Chrome & ChromeDriver
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install -y google-chrome-stable

# ChromeDriver自動インストール
CHROME_VERSION=$(google-chrome --version | cut -d " " -f3 | cut -d "." -f1)
wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}/chromedriver_linux64.zip
sudo unzip /tmp/chromedriver.zip -d /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
```

### 2.2 Python仮想環境作成

```bash
# プロジェクトディレクトリ作成
mkdir -p /home/ubuntu/convex-scraper
cd /home/ubuntu/convex-scraper

# 仮想環境作成
python3 -m venv venv
source venv/bin/activate

# 必要パッケージインストール
pip install --upgrade pip
pip install selenium beautifulsoup4 schedule requests boto3 lxml pandas
```

### 2.3 環境変数設定

```bash
# 環境変数ファイル作成
cat > /home/ubuntu/convex-scraper/.env << EOF
# AWS認証情報
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
AWS_DEFAULT_REGION=ap-northeast-1

# API キー
ALPHAVANTAGE_API_KEY=your-alphavantage-key-here

# ログレベル
LOG_LEVEL=INFO

# 実行間隔（分）
EXECUTION_INTERVAL=15
EOF

# 権限設定
chmod 600 /home/ubuntu/convex-scraper/.env
```

## 📄 Phase 3: アプリケーションデプロイ

### 3.1 コード配置

```bash
# GitHubからクローン（または手動アップロード）
cd /home/ubuntu/convex-scraper
# git clone your-repo-url .

# または手動でファイルをアップロード
scp -i your-key.pem /path/to/local/Convex_Production_JST_WithPrices.py ubuntu@your-ec2-ip:/home/ubuntu/convex-scraper/
```

### 3.2 systemdサービス作成

```bash
# サービスファイル作成
sudo tee /etc/systemd/system/convex-scraper.service > /dev/null << EOF
[Unit]
Description=Convex Finance Scraper
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/convex-scraper
Environment=PATH=/home/ubuntu/convex-scraper/venv/bin
EnvironmentFile=/home/ubuntu/convex-scraper/.env
ExecStart=/home/ubuntu/convex-scraper/venv/bin/python convex_ec2_production.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# サービス有効化
sudo systemctl daemon-reload
sudo systemctl enable convex-scraper
```

## 🔍 Phase 4: 監視・ログ設定

### 4.1 ログローテーション

```bash
# logrotate設定
sudo tee /etc/logrotate.d/convex-scraper > /dev/null << EOF
/home/ubuntu/convex-scraper/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 ubuntu ubuntu
    postrotate
        systemctl reload convex-scraper
    endscript
}
EOF
```

### 4.2 CloudWatch監視（オプション）

```bash
# CloudWatch Agentインストール
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb

# 設定ファイル作成
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null << EOF
{
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "/home/ubuntu/convex-scraper/logs/convex.log",
                        "log_group_name": "convex-scraper",
                        "log_stream_name": "{instance_id}"
                    }
                ]
            }
        }
    }
}
EOF
```

## 🚀 Phase 5: 起動・運用

### 5.1 サービス開始

```bash
# サービス開始
sudo systemctl start convex-scraper

# ステータス確認
sudo systemctl status convex-scraper

# ログ確認
sudo journalctl -u convex-scraper -f
```

### 5.2 運用コマンド

```bash
# サービス停止
sudo systemctl stop convex-scraper

# サービス再起動
sudo systemctl restart convex-scraper

# ログ確認
tail -f /home/ubuntu/convex-scraper/logs/convex.log

# プロセス確認
ps aux | grep python
```

## 💰 コスト最適化

### 月額コスト見積もり（東京リージョン）

```
t3.small インスタンス: $16.06/月
EBS gp3 20GB: $1.60/月
データ転送: $1-3/月（推定）
---
合計: 約$19-21/月
```

### コスト削減オプション

1. **t3.micro使用**: 月額約$8.50（性能は劣る）
2. **Spot Instance**: 最大90%節約（中断リスク有り）
3. **Reserved Instance**: 1年契約で約40%節約

## 🔧 トラブルシューティング

### よくある問題

1. **Chrome/ChromeDriverエラー**
```bash
# Chrome再インストール
sudo apt remove google-chrome-stable
sudo apt install google-chrome-stable

# ChromeDriver更新
sudo rm /usr/local/bin/chromedriver
# 上記のChromeDriverインストール手順を再実行
```

2. **メモリ不足**
```bash
# スワップファイル作成
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

3. **DynamoDB接続エラー**
```bash
# IAMロール確認
aws sts get-caller-identity

# 権限確認
aws dynamodb list-tables
```

## 📊 監視ダッシュボード

### 基本監視項目

1. **CPU使用率** - 80%以下を維持
2. **メモリ使用率** - 85%以下を維持  
3. **ディスク使用量** - 80%以下を維持
4. **ネットワークI/O** - API制限監視
5. **アプリケーションログ** - エラー率監視

### アラート設定

```bash
# CloudWatch アラーム作成例
aws cloudwatch put-metric-alarm \
    --alarm-name "ConvexScraperHighCPU" \
    --alarm-description "High CPU usage" \
    --metric-name CPUUtilization \
    --namespace AWS/EC2 \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2
```
