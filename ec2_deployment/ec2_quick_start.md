# 🚀 EC2 クイックスタートガイド

## 📋 事前準備

### 1. AWS EC2インスタンス作成

```bash
# AWS Management Consoleで以下を設定:
- AMI: Ubuntu 22.04 LTS
- インスタンスタイプ: t3.small (推奨) または t3.micro (低コスト)
- キーペア: 新規作成または既存選択
- セキュリティグループ: SSH (22) のみ許可
- ストレージ: 20GB gp3
```

### 2. 必要な情報を準備

```bash
✅ EC2インスタンスのパブリックIPアドレス
✅ SSH秘密鍵ファイル (.pem)
✅ AWS認証情報 (Access Key ID / Secret Access Key)
✅ AlphaVantage API キー (為替レート取得用)
```

## 🏗️ 自動デプロイ実行

### Step 1: デプロイスクリプト実行

```bash
# ローカルマシンで実行
./deploy_to_ec2.sh -h YOUR_EC2_IP -k ~/.ssh/your-key.pem

# 例:
./deploy_to_ec2.sh -h 54.123.45.67 -k ~/.ssh/convex-key.pem
```

### Step 2: EC2にSSH接続

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@YOUR_EC2_IP
```

### Step 3: 環境変数設定

```bash
cd /home/ubuntu/convex-scraper
nano .env

# 以下の値を設定:
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
AWS_DEFAULT_REGION=ap-northeast-1
ALPHAVANTAGE_API_KEY=your-alphavantage-key-here
LOG_LEVEL=INFO
EXECUTION_INTERVAL=15
```

### Step 4: サービス開始

```bash
# サービス開始
sudo systemctl start convex-scraper

# ステータス確認
sudo systemctl status convex-scraper

# ログ確認
tail -f /home/ubuntu/convex-scraper/logs/convex.log
```

## 🔍 監視・管理コマンド

### 基本監視

```bash
# 監視スクリプトを使用
./monitor_convex.sh status    # ステータス確認
./monitor_convex.sh logs      # リアルタイムログ
./monitor_convex.sh stats     # 実行統計
./monitor_convex.sh health    # ヘルスチェック
```

### サービス制御

```bash
# サービス管理
sudo systemctl start convex-scraper     # 開始
sudo systemctl stop convex-scraper      # 停止
sudo systemctl restart convex-scraper   # 再起動
sudo systemctl status convex-scraper    # ステータス

# または監視スクリプト経由
./monitor_convex.sh start
./monitor_convex.sh stop
./monitor_convex.sh restart
```

### ログ確認

```bash
# アプリケーションログ
tail -f /home/ubuntu/convex-scraper/logs/convex.log

# systemdログ
sudo journalctl -u convex-scraper -f

# 監視スクリプト経由
./monitor_convex.sh tail 100  # 最新100行
./monitor_convex.sh logs      # リアルタイム
```

## 📊 DynamoDBデータ確認

### AWS CLI使用

```bash
# テーブル一覧
aws dynamodb list-tables

# 最新データ確認（PoolLatest）
aws dynamodb scan --table-name PoolLatest --limit 5

# 価格履歴確認（PriceHistory）
aws dynamodb query --table-name PriceHistory --key-condition-expression "asset = :asset" --expression-attribute-values '{":asset":{"S":"CRV"}}' --limit 3 --scan-index-forward false
```

### Python確認スクリプト

```python
# EC2上で実行
cd /home/ubuntu/convex-scraper
source venv/bin/activate

python3 -c "
import boto3
from boto3.dynamodb.conditions import Key
dynamodb = boto3.resource('dynamodb')

# 最新プールデータ確認
table = dynamodb.Table('PoolLatest')
response = table.scan(Limit=5)
print('最新プールデータ:')
for item in response['Items']:
    print(f'  {item[\"Pool\"]}: {item[\"Current_vAPR\"]}')

# 価格データ確認
price_table = dynamodb.Table('PriceHistory')
response = price_table.query(
    KeyConditionExpression=Key('asset').eq('CRV'),
    ScanIndexForward=False,
    Limit=3
)
print('\nCRV価格履歴:')
for item in response['Items']:
    print(f'  {item[\"timestamp\"]}: ${item[\"price_usd\"]}')
"
```

## 🚨 トラブルシューティング

### よくある問題と解決法

#### 1. ChromeDriverエラー

```bash
# Chrome再インストール
sudo apt remove google-chrome-stable
sudo apt update
sudo apt install google-chrome-stable

# ChromeDriver更新
sudo rm /usr/local/bin/chromedriver
# deploy_to_ec2.shのChromeDriver部分を再実行
```

#### 2. メモリ不足

```bash
# スワップファイル作成
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# メモリ使用量確認
free -h
```

#### 3. DynamoDB接続エラー

```bash
# AWS認証情報確認
aws sts get-caller-identity

# 権限確認
aws dynamodb list-tables

# .envファイル確認
cat /home/ubuntu/convex-scraper/.env
```

#### 4. サービスが起動しない

```bash
# 詳細ログ確認
sudo journalctl -u convex-scraper -n 50

# 手動実行テスト
cd /home/ubuntu/convex-scraper
source venv/bin/activate
python3 convex_ec2_production.py

# 設定ファイル確認
sudo systemctl cat convex-scraper
```

## 💰 コスト最適化

### 月額コスト見積もり

```
t3.small (2 vCPU, 2GB): 約$16-20/月
t3.micro (1 vCPU, 1GB): 約$8-10/月（性能制限有り）
EBS 20GB: 約$2/月
データ転送: 約$1-3/月
---
合計: 約$11-25/月
```

### コスト削減オプション

1. **t3.microを使用** (性能は劣るが安価)
2. **Spot Instanceを使用** (最大90%節約、中断リスク有り)
3. **Reserved Instanceを購入** (1年契約で約40%節約)
4. **不要時に停止** (開発・テスト時)

### 自動停止設定

```bash
# 夜間自動停止（オプション）
crontab -e

# 毎日23:00に停止、7:00に開始
0 23 * * * sudo systemctl stop convex-scraper
0 7 * * * sudo systemctl start convex-scraper
```

## 📈 スケーリング・改善

### パフォーマンス最適化

```bash
# 実行間隔調整
nano /home/ubuntu/convex-scraper/.env
# EXECUTION_INTERVAL=15 を 30 や 60 に変更

# Chrome設定最適化（メモリ使用量削減）
# convex_ec2_production.py の chrome_options を調整
```

### 冗長性向上

```bash
# 複数リージョンでの実行
# 別のAZでのバックアップインスタンス
# Auto Scaling Groupの使用
```

### 監視強化

```bash
# CloudWatch監視設定
./monitor_convex.sh install

# アラート設定
./monitor_convex.sh alert
```

## 🔐 セキュリティ強化

### 基本セキュリティ

```bash
# 自動セキュリティアップデート
sudo apt install unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades

# ファイアウォール設定
sudo ufw enable
sudo ufw allow 22/tcp

# SSH設定強化
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PermitRootLogin no
sudo systemctl restart ssh
```

### AWS IAM最適化

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:*:*:table/CvxStakeMetrics",
                "arn:aws:dynamodb:*:*:table/CvxCrvStakeMetrics", 
                "arn:aws:dynamodb:*:*:table/ConvexPoolMetrics",
                "arn:aws:dynamodb:*:*:table/PoolLatest",
                "arn:aws:dynamodb:*:*:table/PriceHistory"
            ]
        }
    ]
}
```

これでEC2への移行準備が完了しました！🚀
