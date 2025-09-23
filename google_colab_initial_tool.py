# セル1: パッケージインストール
!apt-get update
!apt install chromium-chromedriver -y
!cp /usr/lib/chromium-browser/chromedriver /usr/bin
!pip install selenium beautifulsoup4 pandas boto3 schedule lxml

print("✅ 全パッケージのインストールが完了しました")