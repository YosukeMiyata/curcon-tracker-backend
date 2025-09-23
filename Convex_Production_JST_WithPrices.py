# =====================================
# Convex Finance 本番用定期実行版（日本時間対応 + PoolLatest対応 + 価格取得）
# 日本時間でDynamoDBに保存・15分か60分間隔定期実行
# ConvexPoolMetrics（履歴）+ PoolLatest（最新データのみ）+ PriceHistory（価格履歴）
# =====================================

import time
import re
import schedule
import requests
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# AWS関連のインポート
try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

class ConvexJSTProductionWithPrices:
    def __init__(self):
        self.dynamodb = None
        self.tables = {}
        self.is_running = False
        self.success_count = 0
        self.error_count = 0
        self.start_time = datetime.now()
        self.JST = timezone(timedelta(hours=9))  # 日本時間
        
        # APIキーの設定
        self.setup_api_keys()
        
        self.setup_dynamodb()
    
    def setup_api_keys(self):
        """APIキーの設定（Colab Secrets対応）"""
        try:
            # Google Colab環境の場合
            try:
                from google.colab import userdata
                # Colab SecretsからAPIキーを取得
                self.alphavantage_api_key = userdata.get('ALPHAVANTAGE_API_KEY')
                if self.alphavantage_api_key:
                    os.environ['ALPHAVANTAGE_API_KEY'] = self.alphavantage_api_key
                    print("✅ AlphaVantage APIキーをColab Secretsから取得しました")
                else:
                    print("⚠️ Colab SecretsにALPHAVANTAGE_API_KEYが設定されていません")
            except ImportError:
                # Colab環境以外の場合、環境変数から取得
                self.alphavantage_api_key = os.getenv('ALPHAVANTAGE_API_KEY')
                if self.alphavantage_api_key:
                    print("✅ AlphaVantage APIキーを環境変数から取得しました")
                else:
                    print("⚠️ ALPHAVANTAGE_API_KEY環境変数が設定されていません")
        except Exception as e:
            print(f"❌ APIキー設定エラー: {e}")
            self.alphavantage_api_key = None
    
    def get_jst_timestamp(self):
        """日本時間のタイムスタンプを取得"""
        jst_now = datetime.now(self.JST)
        return jst_now.strftime("%Y-%m-%d %H:%M:%S JST")
    
    def get_jst_iso_timestamp(self):
        """日本時間のISO形式タイムスタンプを取得（DynamoDB保存用）"""
        jst_now = datetime.now(self.JST)
        return jst_now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    
    def setup_dynamodb(self):
        """DynamoDB接続設定（PriceHistoryテーブルを追加）"""
        if not AWS_AVAILABLE:
            print("❌ AWS SDK が利用できません")
            return

        try:
            self.dynamodb = boto3.resource('dynamodb')
            
            # 履歴テーブル + 最新データテーブル + 価格履歴テーブル
            table_names = ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'ConvexPoolMetrics', 'PoolLatest', 'PriceHistory']
            
            for table_name in table_names:
                try:
                    table = self.dynamodb.Table(table_name)
                    table.load()
                    self.tables[table_name] = table
                    print(f"✅ テーブル '{table_name}' に接続しました")
                except ClientError as e:
                    print(f"❌ テーブル '{table_name}' への接続に失敗: {e}")
                    if table_name == 'PriceHistory':
                        print("💡 PriceHistoryテーブルが存在しない場合は、以下の仕様で作成してください：")
                        print("   - パーティションキー: asset (String)")
                        print("   - ソートキー: timestamp (String)")
                        print("   - 価格履歴データを15分間隔で保存")
                    
        except Exception as e:
            print(f"❌ DynamoDB設定エラー: {e}")

    def get_coingecko_prices(self):
        """CoinGecko APIからCRV/CVX価格を取得"""
        try:
            # CoinGecko API（無料、APIキー不要）
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'curve-dao-token,convex-finance',
                'vs_currencies': 'usd',
                'include_last_updated_at': 'true'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            prices = {}
            
            # CRV価格
            if 'curve-dao-token' in data:
                crv_data = data['curve-dao-token']
                prices['CRV'] = {
                    'price_usd': crv_data.get('usd'),
                    'last_updated': crv_data.get('last_updated_at')
                }
            
            # CVX価格
            if 'convex-finance' in data:
                cvx_data = data['convex-finance']
                prices['CVX'] = {
                    'price_usd': cvx_data.get('usd'),
                    'last_updated': cvx_data.get('last_updated_at')
                }
            
            print(f"✅ CoinGecko価格取得成功: CRV=${prices.get('CRV', {}).get('price_usd', 'N/A')}, CVX=${prices.get('CVX', {}).get('price_usd', 'N/A')}")
            return prices
            
        except Exception as e:
            print(f"❌ CoinGecko価格取得エラー: {e}")
            return {}

    def get_usd_jpy_rate(self):
        """AlphaVantage APIからUSD/JPY為替レートを取得"""
        if not self.alphavantage_api_key:
            print("⚠️ ALPHAVANTAGE_API_KEY環境変数が設定されていません")
            return None
            
        try:
            # AlphaVantage API
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'CURRENCY_EXCHANGE_RATE',
                'from_currency': 'USD',
                'to_currency': 'JPY',
                'apikey': self.alphavantage_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'Realtime Currency Exchange Rate' in data:
                exchange_data = data['Realtime Currency Exchange Rate']
                rate = float(exchange_data['5. Exchange Rate'])
                last_refreshed = exchange_data['6. Last Refreshed']
                
                print(f"✅ USD/JPY為替レート取得成功: {rate} (更新: {last_refreshed})")
                return {
                    'rate': rate,
                    'last_refreshed': last_refreshed
                }
            else:
                print(f"❌ USD/JPY為替レート取得失敗: {data}")
                return None
                
        except Exception as e:
            print(f"❌ USD/JPY為替レート取得エラー: {e}")
            return None

    def convert_to_decimal(self, value):
        """値をDecimal型に安全に変換"""
        if value is None or value == 'N/A':
            return None
        
        if isinstance(value, str):
            if '%' in value:
                try:
                    num_str = value.replace('%', '')
                    return Decimal(num_str)
                except:
                    return None
            
            if '$' in value:
                try:
                    clean_value = value.replace('$', '').lower()
                    if 'b' in clean_value:
                        num = float(clean_value.replace('b', ''))
                        return Decimal(str(num * 1000000000))
                    elif 'm' in clean_value:
                        num = float(clean_value.replace('m', ''))
                        return Decimal(str(num * 1000000))
                    elif 'k' in clean_value:
                        num = float(clean_value.replace('k', ''))
                        return Decimal(str(num * 1000))
                    else:
                        return Decimal(clean_value)
                except:
                    return None
        
        try:
            return Decimal(str(value))
        except:
            return None

    def save_price_data(self, prices, usd_jpy_rate):
        """価格データをPriceHistoryテーブルに保存"""
        if 'PriceHistory' not in self.tables:
            print("❌ PriceHistoryテーブルが利用できません")
            return False
            
        try:
            table = self.tables['PriceHistory']
            jst_iso_timestamp = self.get_jst_iso_timestamp()
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            
            # CRV/CVX価格を保存
            for asset, price_data in prices.items():
                if price_data.get('price_usd'):
                    price_usd = price_data['price_usd']
                    
                    # JPY価格を計算
                    price_jpy = None
                    if usd_jpy_rate and usd_jpy_rate.get('rate'):
                        price_jpy = price_usd * usd_jpy_rate['rate']
                    
                    item = {
                        'asset': asset,
                        'timestamp': jst_iso_timestamp,
                        'price_usd': Decimal(str(price_usd)),
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
                    print(f"✅ {asset}価格保存: ${price_usd} | {jpy_display}")
            
            # USD/JPY為替レートを保存
            if usd_jpy_rate and usd_jpy_rate.get('rate'):
                item = {
                    'asset': 'USDJPY',
                    'timestamp': jst_iso_timestamp,
                    'rate': Decimal(str(usd_jpy_rate['rate'])),
                    'source': 'AlphaVantage',
                    'created_at': jst_created_at,
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                saved_count += 1
                print(f"✅ USD/JPY為替レート保存: {usd_jpy_rate['rate']}")
            
            print(f"✅ 価格データ保存完了: {saved_count}件")
            return True
            
        except Exception as e:
            print(f"❌ 価格データ保存エラー: {e}")
            return False

    def scrape_accurate_data(self):
        """正確なデータを抽出"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            
            # ページアクセス
            driver.get("https://curve.convexfinance.com/stake")
            print("📄 ページアクセス完了")
            
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
                print("🔘 Show Allボタンをクリックしました")
            except:
                print("⚠️ Show Allボタンのクリックに失敗しました")
            
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
                    print(f"✅ CVXセクション発見")
                    
                    for j in range(i, min(i+10, len(target_divs))):
                        check_div = target_divs[j]
                        check_text = check_div.get_text().strip()
                        
                        if 'vAPR' in check_text and '%' in check_text:
                            vapr_match = re.search(r'vAPR(\d+\.?\d*)\s*%', check_text)
                            if vapr_match:
                                cvx_vapr = vapr_match.group(1)
                                print(f"   ✅ CVX vAPR: {cvx_vapr}%")
                        
                        if 'TVL' in check_text and '$' in check_text:
                            tvl_match = re.search(r'TVL\$\s*([\d,\.]+[kmb]?)', check_text, re.IGNORECASE)
                            if tvl_match:
                                cvx_tvl = tvl_match.group(1)
                                print(f"   ✅ CVX TVL: ${cvx_tvl}")
                    break
            
            # cvxCRVデータ抽出
            max_vapr_gov = None
            max_vapr_stable = None
            cvxcrv_tvl = None
            
            for i, div in enumerate(target_divs):
                div_text = div.get_text().strip()
                
                if 'Max vAPR' in div_text and '%' in div_text:
                    print(f"✅ Max vAPR発見")
                    
                    percentages = re.findall(r'(\d+\.?\d*)\s*%', div_text)
                    valid_percentages = [p for p in percentages if 0 < float(p) < 100]
                    
                    if len(valid_percentages) >= 2:
                        max_vapr_gov = valid_percentages[0]
                        max_vapr_stable = valid_percentages[1]
                        print(f"   ✅ Gov: {max_vapr_gov}%, Stable: {max_vapr_stable}%")
                
                if 'TVL' in div_text and '$' in div_text:
                    tvl_match = re.search(r'TVL\$\s*([\d,\.]+[kmb]?)', div_text, re.IGNORECASE)
                    if tvl_match:
                        tvl_value = tvl_match.group(1)
                        if 'm' in tvl_value.lower():
                            try:
                                num_value = float(tvl_value.replace('m', '').replace(',', ''))
                                if num_value > 50:
                                    cvxcrv_tvl = tvl_value
                                    print(f"   ✅ cvxCRV TVL: ${cvxcrv_tvl}")
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

            print(f"📊 Curveプールデータ: {len(curve_pools_data)}件取得")
            
            return {
                'cvx': {'vapr': cvx_vapr, 'tvl': cvx_tvl},
                'cvxcrv': {'max_vapr_gov': max_vapr_gov, 'max_vapr_stable': max_vapr_stable, 'tvl': cvxcrv_tvl},
                'curve_pools': curve_pools_data
            }
            
        except Exception as e:
            print(f"❌ データ抽出エラー: {e}")
            return None
        
        finally:
            if driver:
                driver.quit()

    def save_pool_to_latest(self, pool_data, jst_iso_timestamp, jst_created_at):
        """個別プールデータをPoolLatestテーブルに保存（最新データのみ）"""
        if 'PoolLatest' not in self.tables:
            return False
            
        try:
            table = self.tables['PoolLatest']
            pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl = pool_data
            
            pool_id = pool_name.replace(' ', '_').replace('-', '_').replace('​', '').lower()
            
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
                'data_source': 'convex_jst_production_with_prices',
                'timezone': 'JST'
            }
            
            # 最新データを上書き保存（同じpool_idの場合は自動的に上書きされる）
            table.put_item(Item=latest_item)
            return True
            
        except Exception as e:
            print(f"❌ PoolLatest保存エラー (pool_id: {pool_id}): {e}")
            return False

    def save_to_dynamodb_jst(self, data):
        """日本時間でDynamoDBに保存（履歴 + 最新データ両方）"""
        if not self.tables or not data:
            return False

        try:
            # 日本時間のタイムスタンプを生成
            jst_iso_timestamp = self.get_jst_iso_timestamp()
            jst_created_at = datetime.now(self.JST).isoformat()
            
            print(f"💾 日本時間でDynamoDB保存中（履歴 + 最新データ）...")
            print(f"   日本時間: {self.get_jst_timestamp()}")
            print(f"   保存タイムスタンプ: {jst_iso_timestamp}")

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
                    'data_source': 'convex_jst_production_with_prices',
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                print(f"✅ CVX保存（JST）: vAPR={data['cvx']['vapr']}%, TVL=${data['cvx']['tvl']}")

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
                    'data_source': 'convex_jst_production_with_prices',
                    'timezone': 'JST'
                }
                
                table.put_item(Item=item)
                print(f"✅ cvxCRV保存（JST）: Gov={data['cvxcrv']['max_vapr_gov']}%, Stable={data['cvxcrv']['max_vapr_stable']}%, TVL=${data['cvxcrv']['tvl']}")

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
                        'data_source': 'convex_jst_production_with_prices',
                        'timezone': 'JST'
                    }
                    
                    history_table.put_item(Item=history_item)
                    
                    # 2. 最新テーブル（PoolLatest）に保存
                    if self.save_pool_to_latest(pool_data, jst_iso_timestamp, jst_created_at):
                        latest_success_count += 1
                
                print(f"✅ Curveプール {len(data['curve_pools'])}件を履歴テーブルに保存しました（JST）")
                print(f"✅ Curveプール {latest_success_count}件を最新テーブル（PoolLatest）に保存しました（JST）")

            return True

        except Exception as e:
            print(f"❌ DynamoDB保存エラー: {e}")
            return False

    def run_jst_job_with_prices(self):
        """日本時間ジョブを実行（価格取得機能付き）"""
        if self.is_running:
            print("⚠️ 既に実行中のため、スキップします")
            return False

        self.is_running = True
        jst_time = self.get_jst_timestamp()
        print(f"\n⏰ 日本時間スクレイピング + 価格取得開始 ({jst_time})")
        
        try:
            # 1. 価格データ取得
            print(f"\n💰 価格データ取得中...")
            prices = self.get_coingecko_prices()
            usd_jpy_rate = self.get_usd_jpy_rate()
            
            # 2. 価格データ保存
            price_saved = self.save_price_data(prices, usd_jpy_rate)
            
            # 3. Convexデータ抽出
            print(f"\n📊 Convexデータ取得中...")
            data = self.scrape_accurate_data()
            
            # 4. Convexデータ保存
            convex_saved = False
            if data and data['cvx']['vapr']:
                convex_saved = self.save_to_dynamodb_jst(data)
            
            # 結果判定
            if price_saved or convex_saved:
                self.success_count += 1
                status_msg = []
                if price_saved:
                    status_msg.append("価格データ")
                if convex_saved:
                    status_msg.append("Convexデータ")
                
                print(f"✅ 日本時間保存成功 ({' + '.join(status_msg)}) (成功: {self.success_count}回, エラー: {self.error_count}回)")
                return True
            else:
                self.error_count += 1
                print(f"❌ データ取得・保存失敗")
                return False

        except Exception as e:
            self.error_count += 1
            print(f"❌ ジョブエラー: {e}")
            return False
        
        finally:
            self.is_running = False

    def start_jst_production_with_prices(self, interval_minutes=15):
        """日本時間15分間隔定期実行を開始（価格取得機能付き・正確な時間制御）"""
        print(f"🚀 日本時間定期実行を開始します（{interval_minutes}分間隔・正確な時間制御）")
        print("🇯🇵 全データを日本時間（JST）で保存します")
        print("📊 履歴データ（ConvexPoolMetrics）+ 最新データ（PoolLatest）+ 価格履歴（PriceHistory）")
        print("💰 CRV/CVX価格（CoinGecko）+ USD/JPY為替（AlphaVantage）")
        print("⏰ 正確な間隔実行（累積誤差なし）")
        print("⚠️ このセルを停止すると定期実行も停止します\n")
        
        # APIキー確認
        if not self.alphavantage_api_key:
            print("⚠️ 警告: ALPHAVANTAGE_API_KEY環境変数が設定されていません")
            print("   USD/JPY為替レートの取得がスキップされます")
            print("   設定方法: export ALPHAVANTAGE_API_KEY='your_api_key'\n")
        
        # 初回実行
        self.run_jst_job_with_prices()
        
        # 正確な時間間隔での実行ループ
        interval_seconds = interval_minutes * 60
        last_stats_time = datetime.now()
        next_execution_time = datetime.now() + timedelta(seconds=interval_seconds)
        
        # 連続実行ループ
        try:
            while True:
                now = datetime.now()
                
                # 実行時間になったら実行
                if now >= next_execution_time:
                    execution_start = datetime.now()
                    self.run_jst_job_with_prices()
                    execution_duration = (datetime.now() - execution_start).total_seconds()
                    
                    # 次回実行時間を正確に計算（実行時間を考慮しない）
                    next_execution_time = next_execution_time + timedelta(seconds=interval_seconds)
                    
                    # 実行時間をログに記録
                    jst_time = datetime.now(self.JST).strftime("%Y-%m-%d %H:%M:%S JST")
                    print(f"⏱️ 実行時間: {execution_duration:.1f}秒 ({jst_time})")
                    print(f"⏰ 次回実行予定: {next_execution_time.astimezone(self.JST).strftime('%Y-%m-%d %H:%M:%S JST')}")
                
                # 30分ごとに統計を表示（日本時間）
                jst_now = datetime.now(self.JST)
                if (jst_now - last_stats_time).total_seconds() >= 1800:  # 30分間隔
                    elapsed = datetime.now() - self.start_time
                    success_rate = (self.success_count/(self.success_count+self.error_count)*100) if (self.success_count+self.error_count) > 0 else 0
                    jst_time = jst_now.strftime("%Y-%m-%d %H:%M:%S JST")
                    
                    print(f"\n📊 日本時間実行統計 ({jst_time}):")
                    print(f"   経過時間: {elapsed}")
                    print(f"   成功: {self.success_count}回")
                    print(f"   エラー: {self.error_count}回")
                    print(f"   成功率: {success_rate:.1f}%")
                    print(f"   次回実行予定: {next_execution_time.astimezone(self.JST).strftime('%Y-%m-%d %H:%M:%S JST')}")
                    print()
                    
                    last_stats_time = datetime.now()
                
                time.sleep(1)  # 1秒間隔でチェック
                
        except KeyboardInterrupt:
            elapsed = datetime.now() - self.start_time
            success_rate = (self.success_count/(self.success_count+self.error_count)*100) if (self.success_count+self.error_count) > 0 else 0
            jst_time = datetime.now(self.JST).strftime("%Y-%m-%d %H:%M:%S JST")
            
            print(f"\n🛑 日本時間定期実行を停止しました ({jst_time})")
            print(f"📊 最終統計 (総実行時間: {elapsed}):")
            print(f"   成功: {self.success_count}回")
            print(f"   エラー: {self.error_count}回")
            print(f"   成功率: {success_rate:.1f}%")

# 実行用関数
def start_jst_production_with_prices_15min():
    """日本時間15分間隔実行を開始（価格取得機能付き）"""
    scraper = ConvexJSTProductionWithPrices()
    scraper.start_jst_production_with_prices(interval_minutes=15)

def start_jst_production_with_prices_60min():
    """日本時間60分間隔実行を開始（価格取得機能付き）"""
    scraper = ConvexJSTProductionWithPrices()
    scraper.start_jst_production_with_prices(interval_minutes=60)

def test_jst_with_prices_once():
    """日本時間一度だけテスト実行（価格取得機能付き）"""
    scraper = ConvexJSTProductionWithPrices()
    return scraper.run_jst_job_with_prices()

def test_prices_only():
    """価格取得のみテスト"""
    scraper = ConvexJSTProductionWithPrices()
    
    print("💰 価格取得テスト")
    print("=" * 40)
    
    # CoinGecko価格取得
    prices = scraper.get_coingecko_prices()
    
    # AlphaVantage為替レート取得
    usd_jpy_rate = scraper.get_usd_jpy_rate()
    
    # 価格データ保存
    if prices or usd_jpy_rate:
        result = scraper.save_price_data(prices, usd_jpy_rate)
        print(f"\n💾 保存結果: {'成功' if result else '失敗'}")
    else:
        print(f"\n❌ 価格データ取得失敗")
    
    return prices, usd_jpy_rate

# データ確認用関数
def check_price_history():
    """PriceHistoryテーブルのデータ確認"""
    try:
        import boto3
        from boto3.dynamodb.conditions import Key
        from datetime import datetime, timezone, timedelta
        
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('PriceHistory')
        JST = timezone(timedelta(hours=9))
        
        print("🔍 PriceHistory データ確認")
        print("=" * 50)
        
        # 各資産の最新データを確認
        assets = ['CRV', 'CVX', 'USDJPY']
        
        for asset in assets:
            try:
                response = table.query(
                    KeyConditionExpression=Key('asset').eq(asset),
                    ScanIndexForward=False,  # 最新順
                    Limit=3
                )
                
                items = response['Items']
                
                print(f"\n📊 {asset} 最新3件:")
                if items:
                    for i, item in enumerate(items, 1):
                        timestamp = item.get('timestamp', 'N/A')
                        
                        # 日本時間表示
                        jst_display = timestamp
                        if '+09:00' in timestamp:
                            jst_display = timestamp.replace('T', ' ').replace('+09:00', ' JST')
                        
                        if asset == 'USDJPY':
                            rate = item.get('rate', 'N/A')
                            source = item.get('source', 'N/A')
                            print(f"   {i}. {jst_display}")
                            print(f"      レート: {rate} | ソース: {source}")
                        else:
                            price_usd = item.get('price_usd', 'N/A')
                            price_jpy = item.get('price_jpy', 'N/A')
                            source = item.get('source', 'N/A')
                            print(f"   {i}. {jst_display}")
                            print(f"      USD: ${price_usd} | JPY: ¥{price_jpy} | ソース: {source}")
                else:
                    print(f"   データなし")
                    
            except Exception as e:
                print(f"   ❌ {asset} 確認エラー: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ PriceHistory確認エラー: {e}")
        return False

# Colab専用セットアップ関数
def setup_colab_environment():
    """Google Colab環境のセットアップ"""
    try:
        from google.colab import userdata
        
        print("🔧 Google Colab環境セットアップ")
        print("=" * 50)
        
        # AWS認証情報の設定
        try:
            aws_access_key = userdata.get('AWS_ACCESS_KEY_ID')
            aws_secret_key = userdata.get('AWS_SECRET_ACCESS_KEY')
            aws_region = userdata.get('AWS_DEFAULT_REGION', 'ap-northeast-1')
            
            if aws_access_key and aws_secret_key:
                os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
                os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
                os.environ['AWS_DEFAULT_REGION'] = aws_region
                print("✅ AWS認証情報をColab Secretsから取得しました")
            else:
                print("⚠️ AWS認証情報がColab Secretsに設定されていません")
        except Exception as e:
            print(f"❌ AWS認証情報設定エラー: {e}")
        
        # AlphaVantage APIキーの設定
        try:
            alphavantage_key = userdata.get('ALPHAVANTAGE_API_KEY')
            if alphavantage_key:
                os.environ['ALPHAVANTAGE_API_KEY'] = alphavantage_key
                print("✅ AlphaVantage APIキーをColab Secretsから取得しました")
            else:
                print("⚠️ ALPHAVANTAGE_API_KEYがColab Secretsに設定されていません")
        except Exception as e:
            print(f"❌ AlphaVantage APIキー設定エラー: {e}")
        
        print("\n💡 Colab Secretsの設定方法:")
        print("   1. 左側パネルの🔑アイコンをクリック")
        print("   2. 以下のキーを追加:")
        print("      - AWS_ACCESS_KEY_ID")
        print("      - AWS_SECRET_ACCESS_KEY")  
        print("      - AWS_DEFAULT_REGION (オプション)")
        print("      - ALPHAVANTAGE_API_KEY")
        print("   3. 各キーに対応する値を入力")
        print("   4. このセルを再実行")
        
        return True
        
    except ImportError:
        print("❌ Google Colab環境ではありません")
        return False
    except Exception as e:
        print(f"❌ Colab環境セットアップエラー: {e}")
        return False

# 実行コマンド
"""
# Google Colab環境セットアップ（最初に実行）
setup_colab_environment()

# 日本時間15分間隔実行（価格取得機能付き、推奨）
start_jst_production_with_prices_15min()

# 日本時間60分間隔実行（価格取得機能付き）
start_jst_production_with_prices_60min()

# 日本時間一度だけテスト（価格取得機能付き）
test_jst_with_prices_once()

# 価格取得のみテスト
test_prices_only()

# 価格履歴データ確認
check_price_history()
"""

print("🇯🇵💰 Convex Finance 日本時間版（履歴+最新データ+価格取得対応）準備完了!")
print("\n📋 実行コマンド:")
print("   - setup_colab_environment()                # Google Colab環境セットアップ（最初に実行）")
print("   - start_jst_production_with_prices_15min() # 日本時間15分間隔実行（価格取得付き）")
print("   - start_jst_production_with_prices_60min() # 日本時間60分間隔実行（価格取得付き）")
print("   - test_jst_with_prices_once()              # 日本時間一度だけテスト（価格取得付き）")
print("   - test_prices_only()                       # 価格取得のみテスト")
print("   - check_price_history()                    # 価格履歴データ確認")
print("\n🚀 新機能:")
print("   ✅ ConvexPoolMetrics: 履歴データ保存（従来通り）")
print("   ✅ PoolLatest: 最新データのみ保存")
print("   ✅ PriceHistory: 価格履歴データ保存（新機能）")
print("   💰 CRV/CVX価格: CoinGecko API（無料、APIキー不要）")
print("   💱 USD/JPY為替: AlphaVantage API（要APIキー）")
print("\n🔑 必要なAPIキー:")
print("   - ALPHAVANTAGE_API_KEY: USD/JPY為替レート取得用")
print("   - 取得方法: https://www.alphavantage.co/support/#api-key")
print("   - Colab設定: 左側の🔑マークから 'ALPHAVANTAGE_API_KEY' を追加")
print("   - ローカル設定: export ALPHAVANTAGE_API_KEY='your_api_key'")
print("\n📊 PriceHistoryテーブル仕様:")
print("   - パーティションキー: asset (String) - 'CRV', 'CVX', 'USDJPY'")
print("   - ソートキー: timestamp (String) - 日本時間ISO形式")
print("   - 属性: price_usd, price_jpy, rate, source, created_at, timezone")
print("\n🇯🇵 日本時間対応機能:")
print("   - タイムスタンプ: 日本時間（JST）で保存")
print("   - created_at: 日本時間（JST）で保存")
print("   - data_source: convex_jst_production_with_prices")
print("   - timezone: JST フィールド追加")
print("   - 表示: 全て日本時間で表示")
