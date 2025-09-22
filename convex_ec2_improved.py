#!/usr/bin/env python3
# =====================================
# Convex Finance AWS EC2用改善版
# 重複実行防止 + 正確な60分間隔実行
# =====================================

import time
import re
import schedule
import requests
import json
import os
import sys
import logging
import signal
import subprocess
import fcntl
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

# 環境変数読み込み
from dotenv import load_dotenv

# AWS関連のインポート
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

class ConvexEC2Improved:
    def __init__(self):
        """EC2用Convex Financeスクレイパー初期化（改善版）"""
        # 環境変数読み込み
        load_dotenv()
        
        # ロックファイル設定
        self.lock_file_path = Path("/home/ubuntu/convex-scraper/.convex_scraper.lock")
        self.lock_file = None
        
        # 基本設定
        self.setup_logging()
        self.setup_directories()
        
        # 実行統計
        self.is_running = False
        self.success_count = 0
        self.error_count = 0
        self.start_time = datetime.now()
        self.JST = timezone(timedelta(hours=9))
        
        # Chrome設定
        self.setup_chrome_options()
        
        # API設定
        self.setup_api_keys()
        
        # AWS設定
        self.setup_aws()
        
        # シグナルハンドラー設定
        self.setup_signal_handlers()
        
        self.logger.info("🚀 Convex EC2 Improved スクレイパー初期化完了")
        self.logger.info("🔒 重複実行防止機能付き")
        self.logger.info("🇯🇵💰 全機能対応版: Webスクレイピング + 価格取得 + 日本時間対応")

    def acquire_lock(self):
        """排他ロックを取得"""
        try:
            self.lock_file = open(self.lock_file_path, 'w')
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.write(f"{datetime.now().isoformat()}\n")
            self.lock_file.flush()
            self.logger.info("🔒 排他ロック取得成功")
            return True
        except (IOError, OSError) as e:
            self.logger.error(f"❌ ロック取得失敗: {e}")
            self.logger.error("   他のプロセスが実行中か、ロックファイルが存在します")
            return False

    def release_lock(self):
        """排他ロックを解放"""
        try:
            if self.lock_file:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                self.lock_file = None
            
            if self.lock_file_path.exists():
                self.lock_file_path.unlink()
            
            self.logger.info("🔓 排他ロック解放完了")
        except Exception as e:
            self.logger.error(f"❌ ロック解放エラー: {e}")

    def setup_logging(self):
        """ログ設定"""
        log_dir = Path("/home/ubuntu/convex-scraper/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # ログフォーマット
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # ファイルハンドラー
        file_handler = logging.FileHandler(
            log_dir / 'convex_improved.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        
        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # ロガー設定
        self.logger = logging.getLogger('ConvexScraperImproved')
        self.logger.setLevel(getattr(logging, log_level))
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def setup_directories(self):
        """ディレクトリ設定"""
        base_dir = Path("/home/ubuntu/convex-scraper")
        self.logs_dir = base_dir / "logs"
        self.data_dir = base_dir / "data"
        
        for dir_path in [self.logs_dir, self.data_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def setup_chrome_options(self):
        """Chrome設定"""
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--window-size=1920,1080')
        self.chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    def setup_api_keys(self):
        """APIキー設定"""
        self.coingecko_api_key = os.getenv('COINGECKO_API_KEY')
        self.alphavantage_api_key = os.getenv('ALPHAVANTAGE_API_KEY')
        
        if not self.coingecko_api_key:
            self.logger.warning("⚠️ COINGECKO_API_KEY環境変数が設定されていません")

    def setup_aws(self):
        """AWS設定"""
        if not AWS_AVAILABLE:
            self.logger.error("❌ boto3が利用できません")
            return False
        
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
            self.logger.info("✅ AWS DynamoDB接続成功")
            return True
        except Exception as e:
            self.logger.error(f"❌ AWS接続エラー: {e}")
            return False

    def setup_signal_handlers(self):
        """シグナルハンドラー設定"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 シグナル受信: {signum}")
            self.release_lock()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def get_crypto_prices(self):
        """暗号通貨価格取得（CoinGecko）"""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'curve-dao-token,convex-finance',
                'vs_currencies': 'usd',
                'include_24hr_change': 'true'
            }
            
            if self.coingecko_api_key:
                params['x_cg_demo_api_key'] = self.coingecko_api_key
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            crv_price = data.get('curve-dao-token', {}).get('usd', 0)
            cvx_price = data.get('convex-finance', {}).get('usd', 0)
            
            self.logger.info(f"💰 価格取得成功: CRV=${crv_price:.4f}, CVX=${cvx_price:.4f}")
            return {'CRV': crv_price, 'CVX': cvx_price}
            
        except Exception as e:
            self.logger.error(f"❌ 暗号通貨価格取得エラー: {e}")
            return None

    def get_usd_jpy_rate(self):
        """USD/JPY為替レート取得（Alpha Vantage）"""
        if not self.alphavantage_api_key:
            self.logger.warning("⚠️ USD/JPY為替レート取得をスキップ（APIキー未設定）")
            return None
        
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'CURRENCY_EXCHANGE_RATE',
                'from_currency': 'USD',
                'to_currency': 'JPY',
                'apikey': self.alphavantage_api_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            rate = float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
            self.logger.info(f"💱 USD/JPY為替レート: ¥{rate:.2f}")
            return rate
            
        except Exception as e:
            self.logger.error(f"❌ USD/JPY為替レート取得エラー: {e}")
            return None

    def save_price_data(self, prices, usd_jpy_rate):
        """価格データをDynamoDBに保存"""
        try:
            table = self.dynamodb.Table('PriceHistory')
            jst_now = datetime.now(self.JST)
            timestamp = jst_now.isoformat()
            
            # 各アセットの価格データを保存
            for asset, price in prices.items():
                item = {
                    'asset': asset,
                    'timestamp': timestamp,
                    'price_usd': Decimal(str(price)),
                    'created_at': jst_now.isoformat()
                }
                
                if usd_jpy_rate:
                    item['price_jpy'] = Decimal(str(round(price * usd_jpy_rate, 2)))
                
                table.put_item(Item=item)
                self.logger.info(f"✅ {asset}価格保存: ${price:.4f} (JST: {timestamp})")
            
            # USD/JPYレートも保存
            if usd_jpy_rate:
                usd_jpy_item = {
                    'asset': 'USDJPY',
                    'timestamp': timestamp,
                    'price_usd': Decimal(str(usd_jpy_rate)),
                    'created_at': jst_now.isoformat()
                }
                table.put_item(Item=usd_jpy_item)
                self.logger.info(f"✅ USD/JPY為替レート保存: ¥{usd_jpy_rate:.2f}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 価格データ保存エラー: {e}")
            return False

    def run_price_job(self):
        """価格取得ジョブ実行"""
        if self.is_running:
            self.logger.warning("⚠️ 前回の実行がまだ進行中です。スキップします。")
            return False
        
        self.is_running = True
        start_time = time.time()
        
        try:
            self.logger.info("🚀 価格取得ジョブ開始")
            
            # 暗号通貨価格取得
            prices = self.get_crypto_prices()
            if not prices:
                self.logger.error("❌ 暗号通貨価格取得に失敗")
                return False
            
            # USD/JPY為替レート取得
            usd_jpy_rate = self.get_usd_jpy_rate()
            
            # データベース保存
            if self.save_price_data(prices, usd_jpy_rate):
                self.success_count += 1
                execution_time = time.time() - start_time
                self.logger.info(f"✅ 価格取得ジョブ完了 (実行時間: {execution_time:.2f}秒)")
                return True
            else:
                self.error_count += 1
                return False
        
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"❌ ジョブエラー: {e}")
            return False
        
        finally:
            self.is_running = False

    def start_production(self, interval_minutes: int = 60):
        """本番環境定期実行開始（改善版）"""
        # 排他ロック取得
        if not self.acquire_lock():
            self.logger.error("❌ 排他ロック取得に失敗しました。他のプロセスが実行中です。")
            sys.exit(1)
        
        try:
            self.logger.info(f"🚀 EC2本番環境定期実行開始（{interval_minutes}分間隔）")
            self.logger.info("🔒 重複実行防止機能有効")
            self.logger.info("🇯🇵 全データを日本時間（JST）で保存")
            self.logger.info("💰 CRV/CVX価格（CoinGecko）+ USD/JPY為替（AlphaVantage）")
            
            # スケジュール設定（正確な間隔で実行）
            schedule.every(interval_minutes).minutes.do(self.run_price_job)
            
            # 初回実行
            self.run_price_job()
            
            # 連続実行ループ（改善版）
            last_stats_time = datetime.now()
            
            while True:
                schedule.run_pending()
                
                # 1時間ごとに統計を表示
                now = datetime.now()
                if (now - last_stats_time).total_seconds() >= 3600:
                    elapsed = now - self.start_time
                    success_rate = (self.success_count/(self.success_count+self.error_count)*100) if (self.success_count+self.error_count) > 0 else 0
                    jst_time = now.astimezone(self.JST).strftime("%Y-%m-%d %H:%M:%S JST")
                    
                    self.logger.info(f"\n📊 実行統計 ({jst_time}):")
                    self.logger.info(f"   経過時間: {elapsed}")
                    self.logger.info(f"   成功: {self.success_count}回")
                    self.logger.info(f"   エラー: {self.error_count}回")
                    self.logger.info(f"   成功率: {success_rate:.1f}%")
                    self.logger.info(f"   次回実行予定: {schedule.next_run()}")
                    
                    last_stats_time = now
                
                # 1分間隔でチェック
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.logger.info("🛑 ユーザーによる停止")
        except Exception as e:
            self.logger.error(f"❌ 実行エラー: {e}")
        finally:
            self.release_lock()

def main():
    """メイン関数"""
    try:
        # 実行間隔を環境変数から取得（デフォルト60分）
        interval = int(os.getenv('EXECUTION_INTERVAL', '60'))
        
        # スクレイパー初期化・実行
        scraper = ConvexEC2Improved()
        scraper.start_production(interval_minutes=interval)
        
    except Exception as e:
        print(f"❌ メイン関数エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Convex Finance EC2改善版（重複実行防止機能付き）")
    print("💰 CRV/CVX価格 + USD/JPY為替レート取得")
    print("🔒 排他ロック機能で重複実行を防止")
    print("⏰ 正確な60分間隔実行")
    main()
