#!/usr/bin/env python3
# =====================================
# Convex Finance EC2完全版
# Webスクレイピング + 価格取得 + 全テーブル対応
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

class ConvexEC2Complete:
    def __init__(self):
        """EC2用Convex Finance完全版スクレイパー初期化"""
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
        
        self.logger.info("🚀 Convex EC2 Complete スクレイパー初期化完了")
        self.logger.info("🔒 重複実行防止機能付き")
        self.logger.info("🇯🇵💰 完全版: Webスクレイピング + 価格取得 + 全テーブル対応")

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
            log_dir / 'convex_complete.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        
        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # ロガー設定
        self.logger = logging.getLogger('ConvexScraperComplete')
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
            
            # 全テーブルに接続
            table_names = ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'ConvexPoolMetrics', 'PoolLatest', 'PriceHistory']
            self.tables = {}
            
            for table_name in table_names:
                try:
                    table = self.dynamodb.Table(table_name)
                    table.load()
                    self.tables[table_name] = table
                    self.logger.info(f"✅ テーブル '{table_name}' に接続しました")
                except ClientError as e:
                    self.logger.error(f"❌ テーブル '{table_name}' への接続に失敗: {e}")
            
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

    def get_jst_timestamp(self):
        """日本時間のタイムスタンプを取得"""
        jst_now = datetime.now(self.JST)
        return jst_now.strftime("%Y-%m-%d %H:%M:%S JST")
    
    def get_jst_iso_timestamp(self):
        """日本時間のISO形式タイムスタンプを取得（DynamoDB保存用）"""
        jst_now = datetime.now(self.JST)
        return jst_now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

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
        """USD/JPY為替レート取得（複数のAPIを試行）"""
        # 1. Alpha Vantage API（無料プラン制限対応）
        if self.alphavantage_api_key:
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
                
                # レート制限チェック
                if 'Information' in data:
                    self.logger.warning(f"⚠️ AlphaVantage API制限: {data['Information']}")
                    raise Exception("API rate limit exceeded")
                
                if 'Realtime Currency Exchange Rate' in data:
                    rate = float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
                    self.logger.info(f"💱 USD/JPY為替レート (AlphaVantage): ¥{rate:.2f}")
                    return rate
                else:
                    raise Exception("Invalid API response structure")
                    
            except Exception as e:
                self.logger.warning(f"⚠️ AlphaVantage API失敗: {e}")
        
        # 2. 代替API: ExchangeRate-API
        try:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'rates' in data and 'JPY' in data['rates']:
                rate = float(data['rates']['JPY'])
                self.logger.info(f"💱 USD/JPY為替レート (ExchangeRate-API): ¥{rate:.2f}")
                return rate
            else:
                raise Exception("Invalid response structure")
                
        except Exception as e:
            self.logger.warning(f"⚠️ ExchangeRate-API失敗: {e}")
        
        # 3. 代替API: Fixer.io（無料プラン）
        try:
            url = "https://api.fixer.io/latest"
            params = {
                'base': 'USD',
                'symbols': 'JPY'
            }
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'rates' in data and 'JPY' in data['rates']:
                rate = float(data['rates']['JPY'])
                self.logger.info(f"💱 USD/JPY為替レート (Fixer.io): ¥{rate:.2f}")
                return rate
            else:
                raise Exception("Invalid response structure")
                
        except Exception as e:
            self.logger.warning(f"⚠️ Fixer.io失敗: {e}")
        
        # 4. 最後の手段: 固定レート（約150円）
        self.logger.warning("⚠️ 全てのAPIが失敗、固定レート（150円）を使用")
        return 150.0

    def convert_to_decimal(self, value):
        """値をDecimal型に安全に変換"""
        if value is None or value == 'N/A' or value == '':
            return None
        
        if isinstance(value, str):
            # パーセンテージ処理
            if '%' in value:
                try:
                    num_str = value.replace('%', '')
                    return Decimal(num_str)
                except:
                    return None
            
            # ドル記号処理（$がある場合）
            if '$' in value:
                try:
                    clean_value = value.replace('$', '').lower()
                    return self._parse_numeric_with_suffix(clean_value)
                except:
                    return None
            
            # ドル記号がない場合でも、数値パターンをチェック
            # 例: "123.45M", "1.2B", "500K" など
            if any(suffix in value.lower() for suffix in ['b', 'm', 'k', 'million', 'billion', 'thousand']):
                try:
                    clean_value = value.lower()
                    return self._parse_numeric_with_suffix(clean_value)
                except:
                    return None
            
            # 純粋な数値の場合（カンマ区切りも含む）
            try:
                # カンマを除去してから数値変換
                clean_value = value.replace(',', '').strip()
                return Decimal(clean_value)
            except:
                return None
        
        try:
            return Decimal(str(value))
        except:
            return None
    
    def _parse_numeric_with_suffix(self, value):
        """数値と接尾辞を解析してDecimal型に変換"""
        try:
            # カンマを除去
            clean_value = value.replace(',', '').strip()
            
            if 'b' in clean_value or 'billion' in clean_value:
                if 'billion' in clean_value:
                    clean_value = clean_value.replace('billion', '').strip()
                else:
                    clean_value = clean_value.replace('b', '').strip()
                num = float(clean_value)
                return Decimal(str(num * 1000000000))
            elif 'm' in clean_value or 'million' in clean_value:
                if 'million' in clean_value:
                    clean_value = clean_value.replace('million', '').strip()
                else:
                    clean_value = clean_value.replace('m', '').strip()
                num = float(clean_value)
                return Decimal(str(num * 1000000))
            elif 'k' in clean_value or 'thousand' in clean_value:
                if 'thousand' in clean_value:
                    clean_value = clean_value.replace('thousand', '').strip()
                else:
                    clean_value = clean_value.replace('k', '').strip()
                num = float(clean_value)
                return Decimal(str(num * 1000))
            else:
                # カンマ区切りの数値も処理
                return Decimal(clean_value)
        except:
            return None

    def save_price_data(self, prices, usd_jpy_rate):
        """価格データをDynamoDBに保存"""
        if 'PriceHistory' not in self.tables:
            self.logger.error("❌ PriceHistoryテーブルが利用できません")
            return False
            
        try:
            table = self.tables['PriceHistory']
            jst_iso_timestamp = self.get_jst_iso_timestamp()
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            
            # CRV/CVX価格を保存
            for asset, price in prices.items():
                if price:
                    # JPY価格を計算
                    price_jpy = None
                    if usd_jpy_rate:
                        price_jpy = price * usd_jpy_rate
                    
                    item = {
                        'asset': asset,
                        'timestamp': jst_iso_timestamp,
                        'price_usd': Decimal(str(price)),
                        'price_jpy': Decimal(str(price_jpy)) if price_jpy else None,
                        'source': 'CoinGecko',
                        'created_at': jst_created_at,
                        'timezone': 'JST'
                    }
                    
                    # NoneやNaN値を除去
                    item = {k: v for k, v in item.items() if v is not None}
                    
                    table.put_item(Item=item)
                    saved_count += 1
                    
                    jpy_display = f"¥{price_jpy:.2f}" if price_jpy else "N/A"
                    self.logger.info(f"✅ {asset}価格保存: ${price} | {jpy_display}")
            
            # USD/JPY為替レートを保存
            if usd_jpy_rate:
                item = {
                    'asset': 'USDJPY',
                    'timestamp': jst_iso_timestamp,
                    'rate': Decimal(str(usd_jpy_rate)),
                    'source': 'AlphaVantage',
                    'created_at': jst_created_at,
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                saved_count += 1
                self.logger.info(f"✅ USD/JPY為替レート保存: ¥{usd_jpy_rate:.2f}")
            
            self.logger.info(f"✅ 価格データ保存完了: {saved_count}件")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 価格データ保存エラー: {e}")
            return False

    def scrape_convex_data(self):
        """Convex Financeからデータをスクレイピング"""
        driver = None
        try:
            driver = webdriver.Chrome(options=self.chrome_options)
            
            # ページアクセス
            driver.get("https://curve.convexfinance.com/stake")
            self.logger.info("📄 ページアクセス完了")
            
            # 待機
            time.sleep(10)
            
            wait = WebDriverWait(driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'cvxCRV') or contains(text(), 'CVX')]")))
            
            # Show Allボタンをクリック
            try:
                pools_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Show All Curve Pools')]")))
                pools_button.click()
                time.sleep(3)
                
                vaults_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Show All Curve Lending Vaults')]")))
                vaults_button.click()
                time.sleep(3)
                self.logger.info("🔘 Show Allボタンをクリックしました")
            except:
                self.logger.warning("⚠️ Show Allボタンのクリックに失敗しました")
            
            time.sleep(15)
            
            # HTMLを取得
            html_content = driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')
            target_divs = soup.find_all('div', class_='jsx-d6fb22cbc31fb3e5')
            
            # CVXデータ抽出
            cvx_vapr = None
            cvx_tvl = None
            
            for i, div in enumerate(target_divs):
                div_text = div.get_text().strip()
                
                if div_text == 'CVX':
                    self.logger.info("✅ CVXセクション発見")
                    
                    for j in range(i, min(i+10, len(target_divs))):
                        check_div = target_divs[j]
                        check_text = check_div.get_text().strip()
                        
                        if 'vAPR' in check_text and '%' in check_text:
                            vapr_match = re.search(r'vAPR(\d+\.?\d*)\s*%', check_text)
                            if vapr_match:
                                cvx_vapr = vapr_match.group(1)
                                self.logger.info(f"   ✅ CVX vAPR: {cvx_vapr}%")
                        
                        if 'TVL' in check_text and '$' in check_text:
                            tvl_match = re.search(r'TVL\$\s*([\d,\.]+[kmb]?)', check_text, re.IGNORECASE)
                            if tvl_match:
                                cvx_tvl = tvl_match.group(1)
                                self.logger.info(f"   ✅ CVX TVL: ${cvx_tvl}")
                    break
            
            # cvxCRVデータ抽出
            max_vapr_gov = None
            max_vapr_stable = None
            cvxcrv_tvl = None
            
            for i, div in enumerate(target_divs):
                div_text = div.get_text().strip()
                
                if 'Max vAPR' in div_text and '%' in div_text:
                    self.logger.info("✅ Max vAPR発見")
                    
                    percentages = re.findall(r'(\d+\.?\d*)\s*%', div_text)
                    valid_percentages = [p for p in percentages if 0 < float(p) < 100]
                    
                    if len(valid_percentages) >= 2:
                        max_vapr_gov = valid_percentages[0]
                        max_vapr_stable = valid_percentages[1]
                        self.logger.info(f"   ✅ Gov: {max_vapr_gov}%, Stable: {max_vapr_stable}%")
                
                if 'TVL' in div_text and '$' in div_text:
                    tvl_match = re.search(r'TVL\$\s*([\d,\.]+[kmb]?)', div_text, re.IGNORECASE)
                    if tvl_match:
                        tvl_value = tvl_match.group(1)
                        if 'm' in tvl_value.lower():
                            try:
                                num_value = float(tvl_value.replace('m', '').replace(',', ''))
                                if num_value > 50:
                                    cvxcrv_tvl = tvl_value
                                    self.logger.info(f"   ✅ cvxCRV TVL: ${cvxcrv_tvl}")
                            except:
                                pass
            
            # Curveプールデータ抽出
            anchors = soup.select('a[href*="/stake/"]')
            curve_pools_data = []

            for a in anchors:
                pool_name = a.get_text(strip=True)
                if pool_name.startswith("Or"):
                    continue

                parent = a
                verticals = []
                for _ in range(10):
                    parent = parent.find_parent("div")
                    if not parent:
                        break
                    verticals = parent.find_all("div", class_=lambda x: x and "vertical" in x)
                    if len(verticals) >= 1:
                        break

                def safe_get(i):
                    return verticals[i].get_text(" ", strip=True) if len(verticals) > i else ""

                vapr_text = safe_get(1)
                current_vapr = projected_vapr = ""
                
                vapr_matches = re.findall(r'(\d+\.?\d*)\s*%', vapr_text)
                if vapr_matches:
                    current_vapr = vapr_matches[0] + "%"
                
                proj_match = re.search(r'proj\.\s*(\d+\.?\d*)\s*%', vapr_text, re.IGNORECASE)
                if proj_match:
                    projected_vapr = proj_match.group(1) + "%"
                
                if not current_vapr and vapr_text:
                    current_vapr = "500%"
                if not projected_vapr and vapr_text:
                    projected_vapr = "500%"
                
                vecrv_boost = ""
                boost_match = re.search(r'veCRV boost:\s*([^,\s]+)', vapr_text)
                if boost_match:
                    vecrv_boost = boost_match.group(1)
                
                remarks = ""
                or_match = re.search(r'Or\s+[^<]+', vapr_text)
                if or_match:
                    remarks = or_match.group(0).strip()
                
                tvl = safe_get(3)
                curve_pools_data.append([pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl])

            self.logger.info(f"📊 Curveプールデータ: {len(curve_pools_data)}件取得")
            
            return {
                'cvx': {'vapr': cvx_vapr, 'tvl': cvx_tvl},
                'cvxcrv': {'max_vapr_gov': max_vapr_gov, 'max_vapr_stable': max_vapr_stable, 'tvl': cvxcrv_tvl},
                'curve_pools': curve_pools_data
            }
            
        except Exception as e:
            self.logger.error(f"❌ データ抽出エラー: {e}")
            return None
        
        finally:
            if driver:
                driver.quit()

    def extract_pool_tokens(self, pool_name):
        """プール名からトークンシンボルを抽出"""
        try:
            # +マークで分割してトークンシンボルを取得
            tokens = [token.strip() for token in pool_name.split('+')]
            return tokens if len(tokens) > 1 else []
        except:
            return []

    def is_vault_data(self, pool_id):
        """Vaultデータかどうかを判定（crvusd_(で始まる場合はVault）"""
        return pool_id.startswith('crvusd_(')

    def get_curve_api_data(self):
        """Curve APIからプールとVaultデータを取得"""
        try:
            # プールデータを取得
            pools_response = requests.get("https://curve.convexfinance.com/api/curve/pools", timeout=30)
            pools_response.raise_for_status()
            pools_data = pools_response.json()
            
            # Vaultデータを取得
            vaults_response = requests.get("https://curve.convexfinance.com/api/curve/lending-vaults", timeout=30)
            vaults_response.raise_for_status()
            vaults_data = vaults_response.json()
            
            self.logger.info(f"✅ Curve API取得成功: プール {len(pools_data.get('pools', []))}件, Vault {len(vaults_data.get('vaults', []))}件")
            
            return {
                'pools': pools_data.get('pools', []),
                'vaults': vaults_data.get('vaults', [])
            }
            
        except Exception as e:
            self.logger.error(f"❌ Curve API取得エラー: {e}")
            return None

    def find_factory_id_for_pool(self, pool_name, token_symbols, api_data):
        """トークンベースのマッチングでAPIデータのIDを特定"""
        if not api_data:
            return None
            
        try:
            # 検索プール名を+で分割してトークンを取得
            search_tokens = self._split_pool_name(pool_name)
            if not search_tokens:
                return None
            
            self.logger.info(f"🔍 マッチング開始: {pool_name} -> 検索トークン: {search_tokens}")
            
            # プールデータから検索
            for pool in api_data.get('pools', []):
                pool_name_api = pool.get('name', '')
                pool_symbol = pool.get('symbol', '')
                
                # Convexプール名を[/\s\-:]で分割
                convex_tokens = self._split_convex_name(pool_name_api)
                
                # トークンベースのマッチングをチェック
                if self._tokens_match_improved(search_tokens, convex_tokens):
                    pool_id = pool.get('id')
                    self.logger.info(f"✅ マッチング成功: {pool_name} -> {pool_name_api} (ID: {pool_id})")
                    return pool_id
                
                # シンボルでも同様にチェック
                if pool_symbol:
                    convex_tokens_symbol = self._split_convex_name(pool_symbol)
                    if self._tokens_match_improved(search_tokens, convex_tokens_symbol):
                        pool_id = pool.get('id')
                        self.logger.info(f"✅ シンボルマッチング成功: {pool_name} -> {pool_symbol} (ID: {pool_id})")
                        return pool_id
            
            # Vaultデータから検索
            for vault in api_data.get('vaults', []):
                vault_name = vault.get('name', '')
                vault_symbol = vault.get('symbol', '')
                
                # Vaultの場合も同様のトークンマッチング
                convex_tokens_vault = self._split_convex_name(vault_name)
                if self._tokens_match_improved(search_tokens, convex_tokens_vault):
                    vault_id = vault.get('id')
                    self.logger.info(f"✅ Vaultマッチング成功: {pool_name} -> {vault_name} (ID: {vault_id})")
                    return vault_id
                
                if vault_symbol:
                    convex_tokens_vault_symbol = self._split_convex_name(vault_symbol)
                    if self._tokens_match_improved(search_tokens, convex_tokens_vault_symbol):
                        vault_id = vault.get('id')
                        self.logger.info(f"✅ Vaultシンボルマッチング成功: {pool_name} -> {vault_symbol} (ID: {vault_id})")
                        return vault_id
            
            self.logger.info(f"❌ マッチング失敗: {pool_name} -> 検索トークン: {search_tokens}")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ factory_id検索エラー: {e}")
            return None

    def _split_pool_name(self, pool_name):
        """検索プール名を+で分割してトークンを取得"""
        try:
            # +マークで分割し、空文字と記号を除去
            tokens = []
            for token in pool_name.split('+'):
                # 特殊文字を除去してクリーンアップ
                clean_token = token.replace('​', '').replace(' ', '').strip()
                if clean_token:
                    tokens.append(clean_token.upper())
            return tokens
        except:
            return []

    def _split_convex_name(self, convex_name):
        """Convexプール名を[/\s\-:]で分割してトークンを取得"""
        try:
            import re
            # [/\s\-:]で分割（スラッシュ、空白、ハイフン、コロン）
            tokens = re.split(r'[/\s\-:]+', convex_name)
            
            # 空文字と一般的な単語を除去してクリーンアップ
            clean_tokens = []
            skip_words = {'curve', 'fi', 'factory', 'pool', 'crypto', 'stable', 'v2', 'v3', 'ng', 'twocrypto', 'tricrypto', 'crvusd'}
            
            for token in tokens:
                clean_token = token.strip()
                if clean_token and clean_token.lower() not in skip_words:
                    # 数字のみのトークンは除外
                    if not clean_token.isdigit():
                        clean_tokens.append(clean_token.upper())
            
            return clean_tokens
        except:
            return []

    def _tokens_match_improved(self, search_tokens, convex_tokens):
        """改善されたトークンマッチング: 検索トークンがすべてConvexトークンに含まれているかチェック"""
        if not search_tokens or not convex_tokens:
            return False
        
        # 検索トークンがすべてConvexトークンに含まれているかチェック
        convex_tokens_set = set(convex_tokens)
        
        # 検索トークンのすべてが含まれている必要がある
        for search_token in search_tokens:
            if search_token not in convex_tokens_set:
                return False
        
        return True

    def _normalize_symbol(self, symbol):
        """シンボルを正規化（大文字小文字統一、記号除去）"""
        return symbol.replace('​', '').replace('+', '').replace('-', '').replace('_', '').upper()

    def _is_name_match(self, pool_name, api_name):
        """プール名の一致チェック"""
        # 特殊文字を除去して比較
        normalized_pool = self._normalize_symbol(pool_name)
        normalized_api = self._normalize_symbol(api_name)
        
        # 完全一致または一方が他方に含まれる場合
        return normalized_pool == normalized_api or normalized_pool in normalized_api or normalized_api in normalized_pool

    def _tokens_match(self, tokens1, tokens2):
        """トークンシンボルの一致チェック"""
        if not tokens1 or not tokens2:
            return False
            
        # トークンを正規化
        norm_tokens1 = [self._normalize_symbol(t) for t in tokens1]
        norm_tokens2 = [self._normalize_symbol(t) for t in tokens2]
        
        # 重複を除去
        set1 = set(norm_tokens1)
        set2 = set(norm_tokens2)
        
        # 共通トークンが50%以上ある場合に一致とみなす
        common_tokens = set1.intersection(set2)
        match_ratio = len(common_tokens) / max(len(set1), len(set2))
        
        return match_ratio >= 0.5

    def _is_vault_name_match(self, pool_name, vault_symbol, vault_name):
        """Vault名の一致チェック"""
        # Vaultの場合は"crvusd_"プレフィックスを考慮
        if pool_name.startswith('crvusd_('):
            # 括弧内の内容を抽出
            import re
            match = re.search(r'crvusd_\((.*?)\)', pool_name)
            if match:
                inner_name = match.group(1).lower()
                vault_symbol_lower = vault_symbol.lower()
                vault_name_lower = vault_name.lower()
                
                return inner_name in vault_symbol_lower or inner_name in vault_name_lower
        
        return False

    def save_pool_to_latest(self, pool_data, jst_iso_timestamp, jst_created_at):
        """個別プールデータをPoolLatestテーブルに保存（最新データのみ）"""
        if 'PoolLatest' not in self.tables:
            return False
            
        try:
            table = self.tables['PoolLatest']
            pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl = pool_data
            
            pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').lower()
            
            # Vaultデータかどうかを判定
            is_vault = self.is_vault_data(pool_id)
            
            # 最新データアイテム（パーティションキー: pool_id のみ）
            latest_item = {
                'pool_id': pool_id,  # パーティションキー
                'Pool': pool_name,
                'Current_vAPR': current_vapr,
                'Projected_vAPR': projected_vapr,
                'veCRV_boost': vecrv_boost,
                'Remarks': remarks,
                'TVL': tvl,
                'current_vapr_numeric': self.convert_to_decimal(current_vapr),
                'projected_vapr_numeric': self.convert_to_decimal(projected_vapr),
                'tvl_numeric': self.convert_to_decimal(tvl),
                'updated_at': jst_created_at,  # 最新更新日時（日本時間）
                'timestamp': jst_iso_timestamp,  # 最新タイムスタンプ（日本時間）
                'data_source': 'convex_ec2_complete',
                'timezone': 'JST',
                'is_vault': is_vault  # Vaultデータかどうかのフラグ
            }
            
            # Vaultデータでない場合のみ、追加の検索用項目を設定
            if not is_vault:
                # トークンシンボル配列を抽出
                token_symbols = self.extract_pool_tokens(pool_name)
                latest_item['token_symbols'] = token_symbols
                
                # 正規化された名前（全て小文字）
                normalized_name = pool_name.lower()
                latest_item['normalized_name'] = normalized_name
                
                # 検索用トークン配列（正規化された名前を+で区切る）
                search_tokens = [token.lower().strip() for token in normalized_name.split('+')]
                latest_item['search_tokens'] = search_tokens
                
                self.logger.info(f"✅ プールデータ検索項目追加: {pool_name} -> tokens: {token_symbols}")
            else:
                # Vaultデータの場合、検索用項目は空リストまたはNone
                latest_item['token_symbols'] = []
                latest_item['normalized_name'] = ''
                latest_item['search_tokens'] = []
                self.logger.info(f"✅ Vaultデータとして保存: {pool_name}")
            
            # 最新データを上書き保存（同じpool_idの場合は自動的に上書きされる）
            table.put_item(Item=latest_item)
            return True
            
        except Exception as e:
            self.logger.error(f"❌ PoolLatest保存エラー (pool_id: {pool_id}): {e}")
            return False

    def update_pool_latest_with_factory_ids(self, api_data):
        """PoolLatestテーブルの全てのデータにfactory_idを追加"""
        if 'PoolLatest' not in self.tables or not api_data:
            self.logger.warning("⚠️ PoolLatestテーブルまたはAPIデータが利用できません")
            return False
            
        try:
            table = self.tables['PoolLatest']
            
            # PoolLatestテーブルの全データを取得
            response = table.scan()
            items = response.get('Items', [])
            
            self.logger.info(f"📊 PoolLatestテーブルから {len(items)}件のデータを取得")
            
            updated_count = 0
            matched_count = 0
            
            for item in items:
                pool_name = item.get('Pool', '')
                token_symbols = item.get('token_symbols', [])
                pool_id = item.get('pool_id', '')
                
                # factory_idを検索
                factory_id = self.find_factory_id_for_pool(pool_name, token_symbols, api_data)
                
                if factory_id:
                    # factory_idを追加して更新
                    item['factory_id'] = str(factory_id)
                    table.put_item(Item=item)
                    matched_count += 1
                    self.logger.info(f"✅ factory_id追加: {pool_name} -> ID: {factory_id}")
                else:
                    # factory_idが見つからない場合はnullを設定
                    item['factory_id'] = None
                    table.put_item(Item=item)
                
                updated_count += 1
            
            self.logger.info(f"✅ PoolLatest更新完了: {updated_count}件中 {matched_count}件のfactory_idを特定")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ PoolLatest factory_id更新エラー: {e}")
            return False

    def save_to_dynamodb_jst(self, data):
        """日本時間でDynamoDBに保存（履歴 + 最新データ両方）"""
        if not self.tables or not data:
            return False

        try:
            # 日本時間のタイムスタンプを生成
            jst_iso_timestamp = self.get_jst_iso_timestamp()
            jst_created_at = datetime.now(self.JST).isoformat()
            
            self.logger.info(f"💾 日本時間でDynamoDB保存中（履歴 + 最新データ）...")
            self.logger.info(f"   日本時間: {self.get_jst_timestamp()}")
            self.logger.info(f"   保存タイムスタンプ: {jst_iso_timestamp}")

            # CVXデータを保存
            if data['cvx'] and data['cvx']['vapr'] and 'CvxStakeMetrics' in self.tables:
                table = self.tables['CvxStakeMetrics']
                
                item = {
                    'token': 'CVX',
                    'timestamp': jst_iso_timestamp,  # 日本時間
                    'vapr': f"{data['cvx']['vapr']}%",
                    'tvl': f"${data['cvx']['tvl']}",
                    'vapr_numeric': self.convert_to_decimal(data['cvx']['vapr']),
                    'tvl_numeric': self.convert_to_decimal(f"${data['cvx']['tvl']}"),
                    'created_at': jst_created_at,  # 日本時間
                    'data_source': 'convex_ec2_complete',
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                self.logger.info(f"✅ CVX保存（JST）: vAPR={data['cvx']['vapr']}%, TVL=${data['cvx']['tvl']}")

            # cvxCRVデータを保存
            if data['cvxcrv'] and data['cvxcrv']['max_vapr_gov'] and 'CvxCrvStakeMetrics' in self.tables:
                table = self.tables['CvxCrvStakeMetrics']
                
                item = {
                    'stake': 'cvxCRV',
                    'timestamp': jst_iso_timestamp,  # 日本時間
                    'pool': 'CRV',
                    'max_vapr_gov_token_rewards': f"{data['cvxcrv']['max_vapr_gov']}%",
                    'max_vapr_stablecoin_rewards': f"{data['cvxcrv']['max_vapr_stable']}%",
                    'tvl': f"${data['cvxcrv']['tvl']}",
                    'max_vapr_gov_numeric': self.convert_to_decimal(data['cvxcrv']['max_vapr_gov']),
                    'max_vapr_stable_numeric': self.convert_to_decimal(data['cvxcrv']['max_vapr_stable']),
                    'tvl_numeric': self.convert_to_decimal(f"${data['cvxcrv']['tvl']}"),
                    'created_at': jst_created_at,  # 日本時間
                    'data_source': 'convex_ec2_complete',
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                self.logger.info(f"✅ cvxCRV保存（JST）: Gov={data['cvxcrv']['max_vapr_gov']}%, Stable={data['cvxcrv']['max_vapr_stable']}%, TVL=${data['cvxcrv']['tvl']}")

            # Curveプールデータを履歴テーブル（ConvexPoolMetrics）と最新テーブル（PoolLatest）両方に保存
            if data['curve_pools'] and 'ConvexPoolMetrics' in self.tables:
                history_table = self.tables['ConvexPoolMetrics']
                latest_success_count = 0
                
                for pool_data in data['curve_pools']:
                    pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl = pool_data
                    
                    pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').lower()
                    
                    # 1. 履歴テーブル（ConvexPoolMetrics）に保存
                    history_item = {
                        'pool_id': pool_id,
                        'timestamp': jst_iso_timestamp,  # 日本時間
                        'Pool': pool_name,
                        'Current_vAPR': current_vapr,
                        'Projected_vAPR': projected_vapr,
                        'veCRV_boost': vecrv_boost,
                        'Remarks': remarks,
                        'TVL': tvl,
                        'current_vapr_numeric': self.convert_to_decimal(current_vapr),
                        'projected_vapr_numeric': self.convert_to_decimal(projected_vapr),
                        'tvl_numeric': self.convert_to_decimal(tvl),
                        'created_at': jst_created_at,  # 日本時間
                        'data_source': 'convex_ec2_complete',
                        'timezone': 'JST'
                    }
                    
                    history_table.put_item(Item=history_item)
                    
                    # 2. 最新テーブル（PoolLatest）に保存
                    if self.save_pool_to_latest(pool_data, jst_iso_timestamp, jst_created_at):
                        latest_success_count += 1
                
                self.logger.info(f"✅ Curveプール {len(data['curve_pools'])}件を履歴テーブルに保存しました（JST）")
                self.logger.info(f"✅ Curveプール {latest_success_count}件を最新テーブル（PoolLatest）に保存しました（JST）")

            return True

        except Exception as e:
            self.logger.error(f"❌ DynamoDB保存エラー: {e}")
            return False

    def run_complete_job(self):
        """完全版ジョブ実行（Webスクレイピング + 価格取得）"""
        if self.is_running:
            self.logger.warning("⚠️ 前回の実行がまだ進行中です。スキップします。")
            return False
        
        self.is_running = True
        start_time = time.time()
        
        try:
            self.logger.info("🚀 完全版ジョブ開始（Webスクレイピング + 価格取得）")
            
            # 1. 価格データ取得
            self.logger.info("💰 価格データ取得中...")
            prices = self.get_crypto_prices()
            usd_jpy_rate = self.get_usd_jpy_rate()
            
            # 2. 価格データ保存
            price_saved = self.save_price_data(prices, usd_jpy_rate)
            
            # 3. Convexデータ抽出
            self.logger.info("📊 Convexデータ取得中...")
            data = self.scrape_convex_data()
            
            # 4. Convexデータ保存
            convex_saved = False
            if data and data['cvx']['vapr']:
                convex_saved = self.save_to_dynamodb_jst(data)
            
            # 5. Curve APIからfactory_idを取得してPoolLatestを更新
            factory_id_updated = False
            if convex_saved:
                self.logger.info("🔍 Curve APIからfactory_idを取得中...")
                api_data = self.get_curve_api_data()
                if api_data:
                    factory_id_updated = self.update_pool_latest_with_factory_ids(api_data)
            
            # 結果判定
            if price_saved or convex_saved or factory_id_updated:
                self.success_count += 1
                status_msg = []
                if price_saved:
                    status_msg.append("価格データ")
                if convex_saved:
                    status_msg.append("Convexデータ")
                if factory_id_updated:
                    status_msg.append("factory_id更新")
                
                execution_time = time.time() - start_time
                self.logger.info(f"✅ 完全版ジョブ完了 ({' + '.join(status_msg)}) (実行時間: {execution_time:.2f}秒)")
                return True
            else:
                self.error_count += 1
                self.logger.error("❌ データ取得・保存失敗")
                return False
        
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"❌ ジョブエラー: {e}")
            return False
        
        finally:
            self.is_running = False

    def start_production(self, interval_minutes: int = 60):
        """本番環境定期実行開始（完全版・正確な時間制御）"""
        # 排他ロック取得
        if not self.acquire_lock():
            self.logger.error("❌ 排他ロック取得に失敗しました。他のプロセスが実行中です。")
            sys.exit(1)
        
        try:
            self.logger.info(f"🚀 EC2本番環境定期実行開始（{interval_minutes}分間隔・正確な時間制御）")
            self.logger.info("🔒 重複実行防止機能有効")
            self.logger.info("🇯🇵 全データを日本時間（JST）で保存")
            self.logger.info("📊 履歴データ + 最新データ + 価格履歴")
            self.logger.info("💰 CRV/CVX価格（CoinGecko）+ USD/JPY為替（AlphaVantage）")
            self.logger.info("🌐 Webスクレイピング（CVX、cvxCRV、Curveプール）")
            self.logger.info("⏰ 正確な60分間隔実行（累積誤差なし）")
            
            # 初回実行
            self.run_complete_job()
            
            # 正確な時間間隔での実行ループ
            interval_seconds = interval_minutes * 60
            last_stats_time = datetime.now()
            next_execution_time = datetime.now() + timedelta(seconds=interval_seconds)
            
            while True:
                now = datetime.now()
                
                # 実行時間になったら実行
                if now >= next_execution_time:
                    execution_start = datetime.now()
                    self.run_complete_job()
                    execution_duration = (datetime.now() - execution_start).total_seconds()
                    
                    # 次回実行時間を正確に計算（実行時間を考慮しない）
                    next_execution_time = next_execution_time + timedelta(seconds=interval_seconds)
                    
                    # 実行時間をログに記録
                    self.logger.info(f"⏱️ 実行時間: {execution_duration:.1f}秒")
                    self.logger.info(f"⏰ 次回実行予定: {next_execution_time.astimezone(self.JST).strftime('%Y-%m-%d %H:%M:%S JST')}")
                
                # 1時間ごとに統計を表示
                if (now - last_stats_time).total_seconds() >= 3600:
                    elapsed = now - self.start_time
                    success_rate = (self.success_count/(self.success_count+self.error_count)*100) if (self.success_count+self.error_count) > 0 else 0
                    jst_time = now.astimezone(self.JST).strftime("%Y-%m-%d %H:%M:%S JST")
                    
                    self.logger.info(f"\n📊 実行統計 ({jst_time}):")
                    self.logger.info(f"   経過時間: {elapsed}")
                    self.logger.info(f"   成功: {self.success_count}回")
                    self.logger.info(f"   エラー: {self.error_count}回")
                    self.logger.info(f"   成功率: {success_rate:.1f}%")
                    self.logger.info(f"   次回実行予定: {next_execution_time.astimezone(self.JST).strftime('%Y-%m-%d %H:%M:%S JST')}")
                    
                    last_stats_time = now
                
                # 効率的な待機（1秒間隔でチェック）
                time.sleep(1)
                
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
        scraper = ConvexEC2Complete()
        scraper.start_production(interval_minutes=interval)
        
    except Exception as e:
        print(f"❌ メイン関数エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Convex Finance EC2完全版（重複実行防止機能付き）")
    print("🌐 Webスクレイピング + 価格取得 + 全テーブル対応")
    print("🔒 排他ロック機能で重複実行を防止")
    print("⏰ 正確な60分間隔実行")
    print("🇯🇵 日本時間対応")
    main()
