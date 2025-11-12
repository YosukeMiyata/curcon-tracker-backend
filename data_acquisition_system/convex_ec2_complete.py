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
    from botocore.exceptions import ClientError
    from boto3.dynamodb.conditions import Attr
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

# Slack通知のインポート
import traceback
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

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
        
        # 人力対応表ファイルパス
        self.manual_mapping_file = Path("/home/ubuntu/convex-scraper/manual_pool_mapping.json")
        self.failed_matching_file = Path("/home/ubuntu/convex-scraper/failed_pool_matching.json")
        
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
        
        # Slack通知の初期化
        if SLACK_AVAILABLE:
            try:
                self.slack_notifier = SlackNotifier()
                self.logger.info("✅ Slack通知機能が有効です")
            except Exception as e:
                self.logger.warning(f"⚠️ Slack通知初期化エラー: {e}")
                self.slack_notifier = None
        else:
            self.slack_notifier = None
            self.logger.warning("⚠️ Slack通知モジュールが利用できません")
        
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
            error_msg = "❌ boto3が利用できません"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete",
                    error=Exception("boto3 not available")
                )
            return False
        
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
            
            # 定期実行に関係のある全テーブルに接続
            table_names = ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'ConvexPoolMetrics', 'PoolLatest', 'PriceHistory']
            self.tables = {}
            
            for table_name in table_names:
                try:
                    table = self.dynamodb.Table(table_name)
                    table.load()
                    self.tables[table_name] = table
                    self.logger.info(f"✅ テーブル '{table_name}' に接続しました")
                except ClientError as e:
                    error_msg = f"❌ テーブル '{table_name}' への接続に失敗: {e}"
                    self.logger.error(error_msg)
                    if self.slack_notifier:
                        self.slack_notifier.notify_error(
                            message=error_msg,
                            system_name="Convex EC2 Complete",
                            error=e
                        )
            
            self.logger.info("✅ AWS DynamoDB接続成功")
            return True
        except Exception as e:
            error_msg = f"❌ AWS接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete",
                    error=e
                )
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

    # CRV/CVX価格取得処理は削除（TokenOHLCDailyテーブルから参照するため）
    # def get_crypto_prices(self):
    #     """暗号通貨価格取得（CoinGecko）"""
    #     ...

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

    def save_usd_jpy_rate(self, usd_jpy_rate):
        """USD/JPY為替レートをDynamoDBに保存（CRV/CVX価格は削除、TokenOHLCDailyテーブルから参照）"""
        if 'PriceHistory' not in self.tables:
            self.logger.error("❌ PriceHistoryテーブルが利用できません")
            return False
            
        try:
            table = self.tables['PriceHistory']
            jst_iso_timestamp = self.get_jst_iso_timestamp()
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            
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
            
            if saved_count > 0:
                self.logger.info(f"✅ 為替レート保存完了: {saved_count}件")
            return saved_count > 0
            
        except Exception as e:
            self.logger.error(f"❌ 為替レート保存エラー: {e}")
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

    def is_vault_data(self, pool_name):
        """Vaultデータかどうかを判定（Pool名またはpool_idで判定）"""
        # Pool名で判定: "crvUSD (" で始まる場合
        if pool_name.startswith('crvUSD ('):
            return True
        
        # pool_idで判定: "crvusd_(" で始まる場合
        pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').replace('(', '').replace(')', '').replace(' ', '').lower()
        if pool_id.startswith('crvusd_('):
            return True
            
        return False

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

    def get_curve_finance_pools_data(self):
        """Curve Finance APIから全プールデータを取得（24時間おき用）"""
        try:
            url = "https://api.curve.finance/api/getPools/all/ethereum"
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            if data.get('success') and 'data' in data:
                pools = data['data'].get('poolData', [])
                self.logger.info(f"✅ Curve Finance API取得成功: {len(pools)}件のプールデータ")
                return pools
            else:
                self.logger.error("❌ Curve Finance APIレスポンスが無効です")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Curve Finance API取得エラー: {e}")
            return None

    def find_factory_id_for_pool(self, pool_name, token_symbols, api_data, used_factory_ids=None):
        """トークンベースのマッチングでAPIデータのIDを特定"""
        if not api_data:
            return None
        
        if used_factory_ids is None:
            used_factory_ids = set()
            
        try:
            # 1. まず人力対応表をチェック
            self.logger.info(f"🔍 人力対応表チェック開始: {pool_name}")
            manual_factory_id = self._check_manual_mapping(pool_name, used_factory_ids)
            if manual_factory_id:
                self.logger.info(f"✅ 人力対応表マッチング成功: {pool_name} -> ID: {manual_factory_id}")
                return manual_factory_id
            else:
                self.logger.info(f"❌ 人力対応表マッチング失敗: {pool_name}")
            
            # 検索プール名を+で分割してトークンを取得
            search_tokens = self._split_pool_name(pool_name)
            if not search_tokens:
                return None
            
            self.logger.info(f"🔍 マッチング開始: {pool_name} -> 検索トークン: {search_tokens}")
            
            # プールデータから検索
            for pool in api_data.get('pools', []):
                pool_name_api = pool.get('name', '')
                pool_symbol = pool.get('symbol', '')
                pool_id = pool.get('id')
                
                # 既に使用済みのfactory_idはスキップ
                if pool_id in used_factory_ids:
                    continue
                
                # Convexプール名を[/\s\-:]で分割
                convex_tokens = self._split_convex_name(pool_name_api)
                
                # トークンベースのマッチングをチェック
                if self._tokens_match_improved(search_tokens, convex_tokens):
                    self.logger.info(f"✅ マッチング成功: {pool_name} -> {pool_name_api} (ID: {pool_id})")
                    return pool_id
                
                # シンボルでも同様にチェック
                if pool_symbol:
                    convex_tokens_symbol = self._split_convex_name(pool_symbol)
                    if self._tokens_match_improved(search_tokens, convex_tokens_symbol):
                        self.logger.info(f"✅ シンボルマッチング成功: {pool_name} -> {pool_symbol} (ID: {pool_id})")
                        return pool_id
            
            # Vaultデータから検索
            for vault in api_data.get('vaults', []):
                vault_name = vault.get('name', '')
                vault_symbol = vault.get('symbol', '')
                vault_id = vault.get('id')
                
                # 既に使用済みのfactory_idはスキップ
                if vault_id in used_factory_ids:
                    continue
                
                # Vaultの場合も同様のトークンマッチング
                convex_tokens_vault = self._split_convex_name(vault_name)
                if self._tokens_match_improved(search_tokens, convex_tokens_vault):
                    self.logger.info(f"✅ Vaultマッチング成功: {pool_name} -> {vault_name} (ID: {vault_id})")
                    return vault_id
                
                if vault_symbol:
                    convex_tokens_vault_symbol = self._split_convex_name(vault_symbol)
                    if self._tokens_match_improved(search_tokens, convex_tokens_vault_symbol):
                        self.logger.info(f"✅ Vaultシンボルマッチング成功: {pool_name} -> {vault_symbol} (ID: {vault_id})")
                        return vault_id
            
            # マッチング失敗時は失敗プールテーブルに保存
            self._save_failed_matching(pool_name, token_symbols)
            
            self.logger.info(f"❌ マッチング失敗: {pool_name} -> 検索トークン: {search_tokens}")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ factory_id検索エラー: {e}")
            return None

    def _split_pool_name(self, pool_name):
        """検索プール名を+で分割してトークンを取得"""
        try:
            # Vaultデータの場合は完全な文字列をそのまま使用
            if pool_name.startswith('crvUSD (') and pool_name.endswith(' collateral)'):
                # Vaultデータは完全な文字列をそのまま返す
                return [pool_name]
            
            # 通常のプールデータは+で分割
            tokens = []
            for token in pool_name.split('+'):
                # 特殊文字を除去してクリーンアップ
                clean_token = token.replace('​', '').replace(' ', '').strip()
                if clean_token:
                    # トークン正規化：3Crv → 3CRV, sdFXN → SDFXN
                    normalized_token = self._normalize_token_symbol(clean_token)
                    tokens.append(normalized_token)
            return tokens
        except:
            return []
    
    def _normalize_token_symbol(self, token):
        """トークンシンボルを正規化"""
        import re
        # 大文字に変換
        token = token.upper()
        
        # 特殊な正規化ルール
        # 3Crv → 3CRV
        if token == '3CRV':
            return '3CRV'
        # sdFXN → SDFXN
        if token.startswith('SD') and len(token) > 2:
            return token
        # yCRV → YCRV
        if token == 'YCRV':
            return 'YCRV'
        
        return token

    def _split_convex_name(self, convex_name):
        """Convexプール名を[/\s\-:]で分割してトークンを取得"""
        try:
            import re
            # [/\s\-:]で分割（スラッシュ、空白、ハイフン、コロン）
            tokens = re.split(r'[/\s\-:]+', convex_name)
            
            # 空文字と一般的な単語を除去してクリーンアップ
            clean_tokens = []
            skip_words = {
                'curve', 'fi', 'factory', 'pool', 'crypto', 'stable', 'v2', 'v3', 'ng', 
                'twocrypto', 'tricrypto', 'crvusd', 'metapool', 'plain', 'usd', 'btc', 
                'eth', 'plain', 'pool', 'factory', 'crypto', 'stable', 'metapool'
            }
            
            for token in tokens:
                clean_token = token.strip()
                if clean_token and clean_token.lower() not in skip_words:
                    # 数字のみのトークンは除外
                    if not clean_token.isdigit():
                        # 括弧内の内容を除去（例: "FRAX/USDC (FRAXBP)" → "FRAX/USDC"）
                        clean_token = re.sub(r'\([^)]*\)', '', clean_token).strip()
                        if clean_token:
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
                # 柔軟なマッチング：類似トークンをチェック
                if not self._flexible_token_match(search_token, convex_tokens_set):
                    return False
        
        return True
    
    def _flexible_token_match(self, search_token, convex_tokens_set):
        """柔軟なトークンマッチング（類似トークンの考慮）"""
        # 限定的なマッピングのみ許可（重複を防ぐため）
        token_mappings = {
            '3CRV': ['3CRV'],  # 3Crvは3CRVのみ（USDC/USDT/DAIは除外）
            'SDFXN': ['SDFXN', 'FXN'],  # sdFXNはFXNの変種
            'YCRV': ['YCRV', 'CRV'],  # yCRVはCRVの変種
        }
        
        # マッピングをチェック
        if search_token in token_mappings:
            for mapped_token in token_mappings[search_token]:
                if mapped_token in convex_tokens_set:
                    return True
        
        # 部分マッチングは除外（重複の原因となるため）
        return False

    def _check_manual_mapping(self, pool_name, used_factory_ids):
        """人力対応表からfactory_idを検索（改善版：柔軟なマッチング）"""
        try:
            if not self.manual_mapping_file.exists():
                return None
            
            # JSONファイルを読み込み
            with open(self.manual_mapping_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            
            # 文字の正規化（ゼロ幅スペースや特殊文字を除去）
            def normalize_text(text):
                if not text:
                    return ""
                # ゼロ幅スペース、ゼロ幅非結合子、ゼロ幅結合子を除去
                import re
                text = re.sub(r'[\u200b\u200c\u200d]', '', text)
                # その他の特殊文字も除去
                text = re.sub(r'[^\w\s\+\-\(\)]', '', text)
                return text.strip()
            
            normalized_pool_name = normalize_text(pool_name)
            
            # 1. 完全一致で検索（正規化後）
            for mapping_name, mapping in mappings.items():
                if normalize_text(mapping_name) == normalized_pool_name:
                    self.logger.info(f"🔍 正規化完全一致発見: {pool_name} -> {mapping_name}")
                    factory_id = self._extract_factory_id(mapping, used_factory_ids)
                    if factory_id:
                        self.logger.info(f"✅ 正規化完全一致: {pool_name} -> {mapping_name} (ID: {factory_id})")
                        return factory_id
                    else:
                        self.logger.info(f"❌ factory_id抽出失敗: {pool_name} -> {mapping_name}")
            
            # 2. 元の文字列での完全一致
            if pool_name in mappings:
                self.logger.info(f"🔍 元文字列完全一致発見: {pool_name}")
                factory_id = self._extract_factory_id(mappings[pool_name], used_factory_ids)
                if factory_id:
                    self.logger.info(f"✅ 元文字列完全一致: {pool_name} (ID: {factory_id})")
                    return factory_id
                else:
                    self.logger.info(f"❌ factory_id抽出失敗: {pool_name}")
            
            # 3. 部分一致で検索（正規化後）
            for mapping_name, mapping in mappings.items():
                normalized_mapping = normalize_text(mapping_name)
                if normalized_pool_name in normalized_mapping or normalized_mapping in normalized_pool_name:
                    factory_id = self._extract_factory_id(mapping, used_factory_ids)
                    if factory_id:
                        self.logger.info(f"✅ 正規化部分一致: {pool_name} -> {mapping_name} (ID: {factory_id})")
                        return factory_id
            
            # 4. 大文字小文字を無視した部分一致
            pool_name_lower = normalized_pool_name.lower()
            for mapping_name, mapping in mappings.items():
                normalized_mapping_lower = normalize_text(mapping_name).lower()
                if pool_name_lower in normalized_mapping_lower or normalized_mapping_lower in pool_name_lower:
                    factory_id = self._extract_factory_id(mapping, used_factory_ids)
                    if factory_id:
                        self.logger.info(f"✅ 大文字小文字無視部分一致: {pool_name} -> {mapping_name} (ID: {factory_id})")
                        return factory_id
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 人力対応表検索エラー: {e}")
            return None
    
    def _extract_factory_id(self, mapping, used_factory_ids):
        """マッピングからfactory_idを抽出し、有効性をチェック"""
        try:
            # シンプル形式（文字列）か詳細形式（オブジェクト）かを判定
            if isinstance(mapping, str):
                # シンプル形式: "pool_name": "factory_id"
                factory_id = mapping
                self.logger.info(f"🔍 シンプル形式factory_id: {factory_id}")
            else:
                # 詳細形式: "pool_name": {"factory_id": "...", "status": "...", ...}
                factory_id = mapping.get('factory_id')
                self.logger.info(f"🔍 詳細形式factory_id: {factory_id}")
                
                # 有効期限をチェック
                valid_until = mapping.get('valid_until')
                if valid_until:
                    if datetime.now() > datetime.fromisoformat(valid_until):
                        self.logger.warning(f"⚠️ 人力対応表の有効期限切れ")
                        return None
                
                # ステータスをチェック
                status = mapping.get('status', 'active')
                if status != 'active':
                    self.logger.info(f"❌ ステータスが非アクティブ: {status}")
                    return None
            
            # 既に使用済みのfactory_idはスキップ
            if factory_id in used_factory_ids:
                self.logger.info(f"❌ 既に使用済みfactory_id: {factory_id} (使用済み: {used_factory_ids})")
                return None
            
            self.logger.info(f"✅ factory_id抽出成功: {factory_id}")
            return factory_id
            
        except Exception as e:
            self.logger.error(f"❌ factory_id抽出エラー: {e}")
            return None

    def _save_failed_matching(self, pool_name, token_symbols):
        """マッチング失敗プールをJSONファイルに保存"""
        try:
            # 既存の失敗プールデータを読み込み
            failed_pools = {}
            if self.failed_matching_file.exists():
                with open(self.failed_matching_file, 'r', encoding='utf-8') as f:
                    failed_pools = json.load(f)
            
            is_new_entry = pool_name not in failed_pools
            
            # プール情報を更新
            if pool_name in failed_pools:
                # 既存エントリの更新
                old_failure_count = failed_pools[pool_name].get('failure_count', 0)
                failed_pools[pool_name]['last_seen'] = datetime.now().isoformat()
                failed_pools[pool_name]['failure_count'] = old_failure_count + 1
                new_failure_count = failed_pools[pool_name]['failure_count']
            else:
                # 新規エントリとして保存
                failed_pools[pool_name] = {
                    'token_symbols': token_symbols,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'failure_count': 1,
                    'status': 'pending'  # pending, resolved, ignored
                }
                new_failure_count = 1
                self.logger.info(f"📝 マッチング失敗プールを記録: {pool_name}")
            
            # JSONファイルに保存
            with open(self.failed_matching_file, 'w', encoding='utf-8') as f:
                json.dump(failed_pools, f, ensure_ascii=False, indent=2)
            
            # Slack通知を送信（新規エントリの場合、または失敗回数が5, 10, 20回などの閾値に達した場合）
            if self.slack_notifier:
                notification_thresholds = [1, 5, 10, 20, 50, 100]
                should_notify = is_new_entry or new_failure_count in notification_thresholds
                
                if should_notify:
                    jst_now = datetime.now(self.JST)
                    timestamp = jst_now.strftime("%Y-%m-%d %H:%M:%S JST")
                    
                    message = f"factory_idマッチング失敗: {pool_name}\n"
                    message += f"失敗回数: {new_failure_count}回\n"
                    message += f"初回発見: {failed_pools[pool_name].get('first_seen', 'N/A')}\n"
                    message += f"最終発見: {failed_pools[pool_name].get('last_seen', 'N/A')}\n"
                    if token_symbols:
                        message += f"トークンシンボル: {', '.join(token_symbols)}\n"
                    message += f"\n対応方法:\n"
                    message += f"1. manual_pool_mapping.jsonに対応表を追加\n"
                    message += f"2. update_existing_convex_pool_metrics.pyを実行して既存データを更新\n"
                    message += f"3. failed_pool_matching.jsonから該当エントリを削除"
                    
                    try:
                        self.slack_notifier.notify_warning(
                            message=message,
                            system_name="Convex EC2 Complete"
                        )
                        self.logger.info(f"✅ Slack通知を送信しました: {pool_name} (失敗回数: {new_failure_count}回)")
                    except Exception as e:
                        self.logger.error(f"❌ Slack通知送信エラー: {e}")
            
        except Exception as e:
            self.logger.error(f"❌ 失敗プール保存エラー: {e}")

    def add_manual_mapping(self, pool_name, factory_id, description="", valid_until=None):
        """人力対応表に新しいマッピングを追加"""
        try:
            # 既存の人力対応表を読み込み
            mappings = {}
            if self.manual_mapping_file.exists():
                with open(self.manual_mapping_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
            
            # 新しいマッピングを追加
            mappings[pool_name] = {
                'factory_id': factory_id,
                'description': description,
                'created_at': datetime.now().isoformat(),
                'created_by': 'manual',
                'status': 'active'
            }
            
            if valid_until:
                mappings[pool_name]['valid_until'] = valid_until
            
            # JSONファイルに保存
            with open(self.manual_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ 人力対応表に追加: {pool_name} -> {factory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 人力対応表追加エラー: {e}")
            return False

    def get_failed_matching_pools(self, status='pending'):
        """マッチング失敗プールの一覧を取得"""
        try:
            if not self.failed_matching_file.exists():
                return []
            
            with open(self.failed_matching_file, 'r', encoding='utf-8') as f:
                failed_pools = json.load(f)
            
            # ステータスでフィルタリング
            filtered_pools = []
            for pool_name, pool_data in failed_pools.items():
                if pool_data.get('status', 'pending') == status:
                    pool_data['pool_name'] = pool_name
                    filtered_pools.append(pool_data)
            
            return filtered_pools
            
        except Exception as e:
            self.logger.error(f"❌ 失敗プール取得エラー: {e}")
            return []

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

    def clear_pool_latest_table(self):
        """PoolLatestテーブルの全データを削除してクリーンな状態にする"""
        if 'PoolLatest' not in self.tables:
            self.logger.error("❌ PoolLatestテーブルが利用できません")
            return False
        
        try:
            table = self.tables['PoolLatest']
            
            # テーブルの全データをスキャン
            self.logger.info("🗑️ PoolLatestテーブルをクリア中...")
            response = table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応（データが多い場合）
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            deleted_count = 0
            
            # バッチ削除（最大25件ずつ）
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'pool_id': item['pool_id']})
                    deleted_count += 1
            
            self.logger.info(f"✅ PoolLatestテーブルクリア完了: {deleted_count}件削除")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ PoolLatestテーブルクリアエラー: {e}")
            return False

    def save_pool_to_latest(self, pool_data, jst_iso_timestamp, jst_created_at):
        """個別プールデータをPoolLatestテーブルに保存（最新データのみ）"""
        if 'PoolLatest' not in self.tables:
            self.logger.error("❌ PoolLatestテーブルが利用できません")
            return False
            
        try:
            table = self.tables['PoolLatest']
            pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl = pool_data
            
            # プールIDの生成を改善（特殊文字を適切に処理）
            pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').replace('(', '').replace(')', '').replace(' ', '').lower()
            
            # Vaultデータかどうかを判定（プール名で判定）
            is_vault = self.is_vault_data(pool_name)
            
            # デバッグ用ログ
            self.logger.info(f"🔍 PoolLatest保存開始: {pool_name}")
            self.logger.info(f"   - pool_id: {pool_id}")
            self.logger.info(f"   - is_vault: {is_vault}")
            
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
            
            # 既存データの確認（デバッグ用）
            try:
                existing_response = table.query(
                    KeyConditionExpression='pool_id = :pool_id',
                    ExpressionAttributeValues={':pool_id': pool_id},
                    Limit=1
                )
                existing_count = len(existing_response.get('Items', []))
                self.logger.info(f"   - 既存データ件数: {existing_count}")
            except Exception as e:
                self.logger.warning(f"   - 既存データ確認エラー: {e}")
            
            # 最新データを上書き保存（同じpool_idの場合は自動的に上書きされる）
            table.put_item(Item=latest_item)
            self.logger.info(f"✅ PoolLatest保存成功: {pool_name} (ID: {pool_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ PoolLatest保存エラー (pool_id: {pool_id}): {e}")
            self.logger.error(f"   - エラー詳細: {str(e)}")
            self.logger.error(f"   - latest_item keys: {list(latest_item.keys())}")
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
            used_factory_ids = set()  # 使用済みのfactory_idを追跡
            
            for item in items:
                pool_name = item.get('Pool', '')
                token_symbols = item.get('token_symbols', [])
                pool_id = item.get('pool_id', '')
                
                # factory_idを検索
                factory_id = self.find_factory_id_for_pool(pool_name, token_symbols, api_data, used_factory_ids)
                
                if factory_id:
                    # factory_idを追加して更新
                    item['factory_id'] = str(factory_id)
                    table.put_item(Item=item)
                    used_factory_ids.add(factory_id)  # 使用済みに追加
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
                # プールデータとボルトデータを分離
                pool_data_list = []
                vault_data_list = []
                
                for pool_data in data['curve_pools']:
                    pool_name = pool_data[0]
                    if self.is_vault_data(pool_name):
                        vault_data_list.append(pool_data)
                    else:
                        pool_data_list.append(pool_data)
                
                # 上から60個のプールと4個のボルトのみ取得
                filtered_pools = pool_data_list[:60]
                filtered_vaults = vault_data_list[:4]
                
                # 統合して保存
                filtered_data = filtered_pools + filtered_vaults
                
                self.logger.info(f"📊 データフィルタリング: プール {len(pool_data_list)}件 → {len(filtered_pools)}件, ボルト {len(vault_data_list)}件 → {len(filtered_vaults)}件")
                
                # PoolLatestテーブルを完全にクリア（クリーンなテーブルにするため）
                if 'PoolLatest' in self.tables:
                    self.clear_pool_latest_table()
                
                history_table = self.tables['ConvexPoolMetrics']
                latest_success_count = 0
                history_success_count = 0
                
                for pool_data in filtered_data:
                    pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl = pool_data
                    
                    # プールIDの生成を改善（特殊文字を適切に処理）
                    pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').replace('(', '').replace(')', '').replace(' ', '').lower()
                    
                    # デバッグ用ログ: プール情報を詳細に出力
                    self.logger.info(f"🔍 プール処理開始: {pool_name}")
                    self.logger.info(f"   - pool_id: {pool_id}")
                    self.logger.info(f"   - is_vault: {self.is_vault_data(pool_name)}")
                    self.logger.info(f"   - current_vapr: {current_vapr}")
                    self.logger.info(f"   - projected_vapr: {projected_vapr}")
                    self.logger.info(f"   - tvl: {tvl}")
                    
                    try:
                        # factory_idを検索
                        token_symbols = []
                        if isinstance(pool_data, dict):
                            token_symbols = pool_data.get('token_symbols', [])
                        factory_id = self.find_factory_id_for_pool(pool_name, token_symbols, data, set())
                        
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
                            'timezone': 'JST',
                            'factory_id': str(factory_id) if factory_id else None
                        }
                        
                        # NoneやNaN値を除去
                        history_item = {k: v for k, v in history_item.items() if v is not None}
                        
                        # 既存データの確認（デバッグ用）
                        try:
                            existing_response = history_table.query(
                                KeyConditionExpression='pool_id = :pool_id',
                                ExpressionAttributeValues={':pool_id': pool_id},
                                Limit=1
                            )
                            existing_count = len(existing_response.get('Items', []))
                            self.logger.info(f"   - 既存データ件数: {existing_count}")
                        except Exception as e:
                            self.logger.warning(f"   - 既存データ確認エラー: {e}")
                        
                        history_table.put_item(Item=history_item)
                        history_success_count += 1
                        factory_info = f" (factory_id: {factory_id})" if factory_id else " (factory_id: None)"
                        self.logger.info(f"✅ ConvexPoolMetrics保存成功: {pool_name} (ID: {pool_id}){factory_info}")
                        
                    except Exception as e:
                        self.logger.error(f"❌ ConvexPoolMetrics保存エラー: {pool_name} -> {e}")
                        self.logger.error(f"   - エラー詳細: {str(e)}")
                        self.logger.error(f"   - pool_id: {pool_id}")
                        self.logger.error(f"   - history_item keys: {list(history_item.keys())}")
                    
                    # 2. 最新テーブル（PoolLatest）に保存
                    if self.save_pool_to_latest(pool_data, jst_iso_timestamp, jst_created_at):
                        latest_success_count += 1
                        self.logger.info(f"✅ PoolLatest保存成功: {pool_name}")
                    else:
                        self.logger.warning(f"⚠️ PoolLatest保存失敗: {pool_name}")
                
                self.logger.info(f"✅ Curveプール {history_success_count}/{len(filtered_data)}件を履歴テーブル（ConvexPoolMetrics）に保存しました（JST）")
                self.logger.info(f"✅ Curveプール {latest_success_count}/{len(filtered_data)}件を最新テーブル（PoolLatest）に保存しました（JST）")

            return True

        except Exception as e:
            error_msg = f"❌ DynamoDB保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete",
                    error=e
                )
            return False

    def run_complete_job(self):
        """完全版ジョブ実行（Webスクレイピング + 価格取得）"""
        if self.is_running:
            self.logger.warning("⚠️ 前回の実行がまだ進行中です。スキップします。")
            return False
        
        self.is_running = True
        start_time = time.time()
        
        try:
            self.logger.info("🚀 完全版ジョブ開始（Webスクレイピング）")
            
            # 1. USD/JPY為替レート取得（CRV/CVX価格はTokenOHLCDailyテーブルから参照するため削除）
            usd_jpy_rate = self.get_usd_jpy_rate()
            rate_saved = False
            if usd_jpy_rate:
                rate_saved = self.save_usd_jpy_rate(usd_jpy_rate)
            
            # 2. Convexデータ抽出
            self.logger.info("📊 Convexデータ取得中...")
            data = self.scrape_convex_data()
            
            # 3. Convexデータ保存
            convex_saved = False
            if data and data['cvx']['vapr']:
                convex_saved = self.save_to_dynamodb_jst(data)
            
            # 4. Curve APIからfactory_idを取得してPoolLatestを更新
            factory_id_updated = False
            if convex_saved:
                self.logger.info("🔍 Curve APIからfactory_idを取得中...")
                api_data = self.get_curve_api_data()
                if api_data:
                    factory_id_updated = self.update_pool_latest_with_factory_ids(api_data)
            
            # 結果判定
            if rate_saved or convex_saved or factory_id_updated:
                self.success_count += 1
                status_msg = []
                if rate_saved:
                    status_msg.append("為替レート")
                if convex_saved:
                    status_msg.append("Convexデータ")
                if factory_id_updated:
                    status_msg.append("factory_id更新")
                
                execution_time = time.time() - start_time
                self.logger.info(f"✅ 完全版ジョブ完了 ({' + '.join(status_msg)}) (実行時間: {execution_time:.2f}秒)")
                return True
            else:
                self.error_count += 1
                error_msg = "❌ データ取得・保存失敗"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="Convex EC2 Complete"
                    )
                return False
        
        except Exception as e:
            self.error_count += 1
            error_msg = f"❌ ジョブエラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete",
                    error=e
                )
            return False
        
        finally:
            self.is_running = False

    def start_production(self, interval_minutes: int = 60, target_minute: int = 30):
        """本番環境定期実行開始（完全版・正確な時間制御）
        
        Args:
            interval_minutes: 実行間隔（分）
            target_minute: 毎時の実行分（0-59）。例: 30なら毎時30分に実行
        """
        # 排他ロック取得
        if not self.acquire_lock():
            error_msg = "❌ 排他ロック取得に失敗しました。他のプロセスが実行中です。"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete"
                )
            sys.exit(1)
        
        try:
            self.logger.info(f"🚀 EC2本番環境定期実行開始（{interval_minutes}分間隔・毎時{target_minute}分実行）")
            self.logger.info("🔒 重複実行防止機能有効")
            self.logger.info("🇯🇵 全データを日本時間（JST）で保存")
            self.logger.info("📊 履歴データ + 最新データ + 為替レート履歴")
            self.logger.info("💱 USD/JPY為替（AlphaVantage）")
            self.logger.info("📈 CRV/CVX価格はTokenOHLCDailyテーブルから参照")
            self.logger.info("🌐 Webスクレイピング（CVX、cvxCRV、Curveプール）")
            self.logger.info(f"⏰ 毎時{target_minute}分に実行（正確な時間制御）")
            
            # 次回実行時間を計算（毎時target_minute分）
            now = datetime.now()
            now_jst = now.astimezone(self.JST)
            
            # 今日のtarget_minute分を計算
            today_target = now_jst.replace(minute=target_minute, second=0, microsecond=0)
            
            # 現在時刻がtarget_minute分より前なら今日のtarget_minute分、後なら次の時間のtarget_minute分
            # サービス再起動時でも、すぐに実行せずに次回のtarget_minuteまで待機する
            if now_jst < today_target:
                next_execution_time = today_target
            else:
                # 現在時刻がtarget_minute分以降なら、次の時間のtarget_minute分まで待つ
                next_execution_time = today_target + timedelta(hours=1)
            
            self.logger.info(f"⏰ 次回実行時刻まで待機します（{next_execution_time.strftime('%Y-%m-%d %H:%M:%S JST')}）")
            
            # UTCに変換
            next_execution_time = next_execution_time.astimezone(timezone.utc).replace(tzinfo=None)
            
            # 正確な時間間隔での実行ループ
            interval_seconds = interval_minutes * 60
            last_stats_time = datetime.now()
            
            while True:
                now = datetime.now()
                
                # 実行時間になったら実行
                if now >= next_execution_time:
                    execution_start = datetime.now()
                    self.run_complete_job()
                    execution_duration = (datetime.now() - execution_start).total_seconds()
                    
                    # 次回実行時間を正確に計算（毎時target_minute分）
                    # 現在時刻をJSTに変換して次の時間のtarget_minute分を計算
                    now_jst = datetime.now().astimezone(self.JST)
                    next_execution_time_jst = now_jst.replace(minute=target_minute, second=0, microsecond=0)
                    # 現在時刻が既にtarget_minute分を過ぎている場合は次の時間
                    if now_jst >= next_execution_time_jst:
                        next_execution_time_jst = next_execution_time_jst + timedelta(hours=1)
                    # UTCに変換
                    next_execution_time = next_execution_time_jst.astimezone(timezone.utc).replace(tzinfo=None)
                    
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
            error_msg = f"❌ 実行エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Convex EC2 Complete",
                    error=e
                )
        finally:
            self.release_lock()

def main():
    """メイン関数"""
    try:
        # 実行間隔を環境変数から取得（デフォルト60分）
        interval = int(os.getenv('EXECUTION_INTERVAL', '60'))
        # 実行分を環境変数から取得（デフォルト30分）
        target_minute = int(os.getenv('EXECUTION_TARGET_MINUTE', '30'))
        
        # スクレイパー初期化・実行
        scraper = ConvexEC2Complete()
        scraper.start_production(interval_minutes=interval, target_minute=target_minute)
        
    except Exception as e:
        error_msg = f"❌ メイン関数エラー: {e}"
        print(error_msg)
        # Slack通知（グローバルインスタンスを使用）
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from utils.slack_notifier import SlackNotifier
            notifier = SlackNotifier()
            notifier.notify_error(
                message=error_msg,
                system_name="Convex EC2 Complete",
                error=e
            )
        except Exception:
            pass  # Slack通知失敗は無視
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Convex Finance EC2完全版（重複実行防止機能付き）")
    print("🌐 Webスクレイピング + 価格取得 + 全テーブル対応")
    print("🔒 排他ロック機能で重複実行を防止")
    print("⏰ 正確な60分間隔実行")
    print("🇯🇵 日本時間対応")
    main()
