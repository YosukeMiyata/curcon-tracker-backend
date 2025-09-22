#!/bin/bash
# t3.micro EC2 自動デプロイスクリプト

set -e

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# パラメータ確認
if [ $# -lt 4 ]; then
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH>"
    echo "例: $0 -h 54.123.45.67 -k ~/.ssh/convex-key.pem"
    exit 1
fi

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            EC2_IP="$2"
            shift 2
            ;;
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        *)
            echo "不明なオプション: $1"
            exit 1
            ;;
    esac
done

# 必須パラメータ確認
if [ -z "$EC2_IP" ] || [ -z "$SSH_KEY" ]; then
    log_error "EC2_IPとSSH_KEYは必須です"
    exit 1
fi

log_info "🚀 t3.micro EC2 Convex Scraper デプロイ開始"
log_info "📍 EC2 IP: $EC2_IP"
log_info "🔑 SSH Key: $SSH_KEY"

# SSH接続テスト
log_info "🔍 SSH接続テスト"
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "echo 'SSH接続成功'" 2>/dev/null; then
    log_error "SSH接続に失敗しました。EC2_IPとSSH_KEYを確認してください。"
    exit 1
fi
log_info "✅ SSH接続成功"

# ファイル転送
log_info "📦 ファイル転送中..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no convex_ec2_production.py ubuntu@"$EC2_IP":/tmp/ || {
    log_error "ファイル転送に失敗しました"
    exit 1
}

# リモート実行スクリプト作成
cat > /tmp/setup_script.sh << 'EOF'
#!/bin/bash
set -e

log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }

log_info "🔧 システム更新とパッケージインストール"
sudo apt update && sudo apt upgrade -y

log_info "🐍 Python環境セットアップ"
sudo apt install -y python3 python3-pip python3-venv

log_info "🌐 Chrome/ChromeDriverインストール"
# Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# ChromeDriver (新しいChrome for Testing API使用)
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
echo "Chrome version: $CHROME_VERSION"

# Chrome for Testing APIから最新のChromeDriverを取得
CHROMEDRIVER_URL="https://storage.googleapis.com/chrome-for-testing/140.0.7339.185/linux64/chromedriver-linux64.zip"
wget -O /tmp/chromedriver.zip "$CHROMEDRIVER_URL" || {
    # フォールバック: 固定バージョン
    echo "最新版取得失敗、固定バージョンを使用"
    wget -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing/129.0.6668.70/linux64/chromedriver-linux64.zip"
}

sudo unzip /tmp/chromedriver.zip -d /tmp/
sudo mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64

log_info "📁 プロジェクトディレクトリ作成"
mkdir -p /home/ubuntu/convex-scraper/{logs,data}
cd /home/ubuntu/convex-scraper

log_info "🐍 Python仮想環境作成"
python3 -m venv venv
source venv/bin/activate

log_info "📦 Python依存関係インストール"
pip install --upgrade pip
pip install selenium beautifulsoup4 boto3 requests python-dateutil lxml

log_info "📄 メインスクリプト配置"
mv /tmp/convex_ec2_production.py /home/ubuntu/convex-scraper/
chmod +x /home/ubuntu/convex-scraper/convex_ec2_production.py

log_info "⚙️ 環境変数ファイル作成"
cat > /home/ubuntu/convex-scraper/.env << 'ENVEOF'
# AWS認証情報（要設定）
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
AWS_DEFAULT_REGION=ap-northeast-1

# API キー
ALPHAVANTAGE_API_KEY=PAEVD27FAP265CDL

# 実行設定
EXECUTION_INTERVAL=60
LOG_LEVEL=INFO
CHROME_HEADLESS=true
ENVEOF

log_info "🔧 systemdサービス作成"
sudo tee /etc/systemd/system/convex-scraper.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Convex Finance Data Scraper
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/convex-scraper
Environment=PATH=/home/ubuntu/convex-scraper/venv/bin
EnvironmentFile=/home/ubuntu/convex-scraper/.env
ExecStart=/home/ubuntu/convex-scraper/venv/bin/python /home/ubuntu/convex-scraper/convex_ec2_production.py
Restart=always
RestartSec=60
StandardOutput=append:/home/ubuntu/convex-scraper/logs/convex.log
StandardError=append:/home/ubuntu/convex-scraper/logs/convex.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

log_info "🔄 systemd設定リロード"
sudo systemctl daemon-reload
sudo systemctl enable convex-scraper

log_info "✅ セットアップ完了！"
echo ""
echo "🎯 次のステップ:"
echo "1. .envファイルにAWS認証情報を設定"
echo "   nano /home/ubuntu/convex-scraper/.env"
echo ""
echo "2. サービス開始"
echo "   sudo systemctl start convex-scraper"
echo ""
echo "3. 動作確認"
echo "   sudo systemctl status convex-scraper"
echo "   tail -f /home/ubuntu/convex-scraper/logs/convex.log"
EOF

# リモートスクリプト転送・実行
log_info "🚀 リモートセットアップ実行"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no /tmp/setup_script.sh ubuntu@"$EC2_IP":/tmp/
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "chmod +x /tmp/setup_script.sh && /tmp/setup_script.sh"

log_info "🎉 t3.micro EC2 デプロイ完了！"
echo ""
echo "🔧 最終設定手順:"
echo "1. SSH接続: ssh -i $SSH_KEY ubuntu@$EC2_IP"
echo "2. 環境変数設定: nano /home/ubuntu/convex-scraper/.env"
echo "3. サービス開始: sudo systemctl start convex-scraper"
echo "4. 動作確認: sudo systemctl status convex-scraper"
echo ""
echo "✅ 60分間隔での完全自動実行が開始されます！"
