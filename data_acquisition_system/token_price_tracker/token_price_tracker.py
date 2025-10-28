#!/usr/bin/env python3
# =====================================
# トークン価格追跡システム
# ConvexPoolMetricsからトークンを抽出し、Curve Finance APIから価格を取得してTokenPriceHistoryテーブルに保存
# =====================================

import boto3
import json
import requests
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from botocore.exceptions import ClientError
from decimal import Decimal
import re
import os

class TokenPriceTracker:
    def __init__(self):
        """トークン価格追跡システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.convex_table = None
        self.token_price_table = None
        self.curve_token_prices = {}
        self.failed_tokens = []
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # ログ設定
        self.setup_logging()
        
        # テーブル接続
        self.setup_tables()
        
        # Curve Finance APIから価格データを取得
        self.fetch_curve_prices()
    
    def setup_logging(self):
        """ログ設定"""
        log_file = '/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/token_price_tracker.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_tables(self):
        """DynamoDBテーブルに接続"""
        try:
            self.convex_table = self.dynamodb.Table('ConvexPoolMetrics')
            self.convex_table.load()
            self.logger.info("✅ ConvexPoolMetricsテーブルに接続しました")
            
            # TokenPriceHistoryテーブルが存在しない場合は作成
            try:
                self.token_price_table = self.dynamodb.Table('TokenPriceHistory')
                self.token_price_table.load()
                self.logger.info("✅ TokenPriceHistoryテーブルに接続しました")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    self.logger.info("📝 TokenPriceHistoryテーブルを作成中...")
                    self.create_token_price_table()
                else:
                    raise e
                    
        except ClientError as e:
            self.logger.error(f"❌ テーブル接続エラー: {e}")
            return False
        return True
    
    def create_token_price_table(self):
        """TokenPriceHistoryテーブルを作成"""
        try:
            table = self.dynamodb.create_table(
                TableName='TokenPriceHistory',
                KeySchema=[
                    {
                        'AttributeName': 'token',
                        'KeyType': 'HASH'  # パーティションキー
                    },
                    {
                        'AttributeName': 'timestamp',
                        'KeyType': 'RANGE'  # ソートキー
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'token',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'timestamp',
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # テーブルの作成完了を待つ
            table.wait_until_exists()
            self.token_price_table = table
            self.logger.info("✅ TokenPriceHistoryテーブルを作成しました")
            
        except Exception as e:
            self.logger.error(f"❌ テーブル作成エラー: {e}")
            raise e
    
    def fetch_curve_prices(self):
        """Curve Finance APIからトークン価格データを取得"""
        try:
            self.logger.info("💰 Curve Finance APIから価格データを取得中...")
            url = "https://api.curve.finance/api/getPools/all/ethereum"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # poolDataから全コインの価格情報を抽出
            if 'data' in data and 'poolData' in data['data']:
                pool_data = data['data']['poolData']
                
                for pool in pool_data:
                    if 'coins' in pool:
                        for coin in pool['coins']:
                            symbol = coin.get('symbol', '')
                            usd_price = coin.get('usdPrice')
                            
                            if symbol and usd_price is not None:
                                # 同じシンボルで複数の価格がある場合、最初に見つかったものを優先
                                if symbol not in self.curve_token_prices:
                                    self.curve_token_prices[symbol] = usd_price
                
                self.logger.info(f"✅ {len(self.curve_token_prices)}個のトークン価格を取得しました")
            else:
                self.logger.warning("⚠️ APIレスポンスの構造が予期しない形式です")
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Curve API取得エラー: {e}")
        except Exception as e:
            self.logger.error(f"❌ 価格データ処理エラー: {e}")
    
    def get_all_pool_data(self):
        """ConvexPoolMetricsから全プールデータを取得"""
        try:
            self.logger.info("📊 ConvexPoolMetricsからデータを取得中...")
            response = self.convex_table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.convex_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            self.logger.info(f"✅ {len(items)}件のデータを取得しました")
            return items
            
        except Exception as e:
            self.logger.error(f"❌ データ取得エラー: {e}")
            return []
    
    def normalize_token_symbol(self, token):
        """トークンシンボルを正規化（特殊文字を除去）"""
        if not token:
            return ""
        
        # ゼロ幅スペースや特殊文字を除去
        normalized = re.sub(r'[\u200b\u200c\u200d]', '', token)
        normalized = normalized.strip()
        
        return normalized
    
    def extract_tokens_from_pool_name(self, pool_name):
        """プール名からトークンを抽出（特殊ケース対応）"""
        if not pool_name:
            return []
        
        tokens = []
        
        # 特殊ケース1: crvUSD (XXX collateral) パターン
        if pool_name.startswith('crvUSD ('):
            # crvUSD (CRV collateral) -> crvUSD, CRV
            tokens.append('crvUSD')
            # 括弧内の内容を抽出
            match = re.search(r'crvUSD \((.*?)\)', pool_name)
            if match:
                collateral_token = match.group(1).strip()
                # "CRV collateral" -> "CRV" に正規化
                if collateral_token.endswith(' collateral'):
                    collateral_token = collateral_token.replace(' collateral', '')
                tokens.append(collateral_token)
            return tokens
        
        # 特殊ケース2: FRAXPYUSD のような連結トークン
        if 'FRAXPYUSD' in pool_name:
            tokens.extend(['FRAX', 'PYUSD'])
            return tokens
        
        # 通常ケース: +で分割
        parts = pool_name.split('+')
        for i, part in enumerate(parts):
            clean_token = self.normalize_token_symbol(part)
            if clean_token:
                # 次のパートが空文字列の場合、このトークンは「XXX+」という形式
                if i + 1 < len(parts) and not parts[i + 1].strip():
                    tokens.append(clean_token + '+')
                else:
                    tokens.append(clean_token)
        
        return tokens
    
    def analyze_pool_tokens(self):
        """プール構成トークンを分析"""
        items = self.get_all_pool_data()
        if not items:
            return {}
        
        # トークン情報を格納する辞書
        token_info = {}
        
        self.logger.info("🔍 プールデータからトークンを抽出中...")
        
        for item in items:
            pool_name = item.get('Pool', '')
            factory_id = item.get('factory_id', '')
            
            if not pool_name:
                continue
            
            # プール名からトークンを抽出
            tokens = self.extract_tokens_from_pool_name(pool_name)
            
            for token in tokens:
                if token not in token_info:
                    # トークン価格を取得（見つからない場合はNone）
                    price = self.curve_token_prices.get(token)
                    
                    token_info[token] = {
                        'symbol': token,
                        'pools': [],
                        'factory_ids': [],
                        'price': price
                    }
                
                # このトークンが使われているプールを記録
                if pool_name not in token_info[token]['pools']:
                    token_info[token]['pools'].append(pool_name)
                    if factory_id and factory_id not in token_info[token]['factory_ids']:
                        token_info[token]['factory_ids'].append(factory_id)
        
        return token_info
    
    def save_token_prices_to_db(self, token_info):
        """トークン価格データをTokenPriceHistoryテーブルに保存"""
        if not token_info:
            self.logger.warning("❌ トークン情報が見つかりません")
            return
        
        jst_iso_timestamp = datetime.now(self.JST).isoformat()
        jst_created_at = datetime.now(self.JST).isoformat()
        
        saved_count = 0
        failed_count = 0
        
        for token, info in token_info.items():
            price = info.get('price')
            
            # 価格が取得できない場合はスキップ
            if price is None:
                self.failed_tokens.append(token)
                failed_count += 1
                continue
            
            try:
                # 価格データを保存
                item = {
                    'token': token,
                    'timestamp': jst_iso_timestamp,
                    'timezone': 'JST',
                    'created_at': jst_created_at,
                    'data_source': 'curve_finance_api',
                    'pool_count': len(info['pools']),
                    'pools': ', '.join(info['pools']),
                    'factory_ids': ', '.join(info['factory_ids']) if info['factory_ids'] else '',
                    'price': f"${price:.6f}",
                    'price_numeric': Decimal(str(price))
                }
                
                # NoneやNaN値を除去
                item = {k: v for k, v in item.items() if v is not None and v != ''}
                
                self.token_price_table.put_item(Item=item)
                saved_count += 1
                
                self.logger.info(f"✅ {token}価格保存: ${price:.6f} (プール数: {len(info['pools'])})")
                
            except Exception as e:
                self.logger.error(f"❌ {token}保存エラー: {e}")
                self.failed_tokens.append(token)
                failed_count += 1
        
        self.logger.info(f"📊 保存完了: {saved_count}個成功, {failed_count}個失敗")
    
    def save_failed_tokens_to_file(self):
        """価格取得に失敗したトークンをJSONファイルに保存"""
        if not self.failed_tokens:
            return
        
        try:
            failed_data = {
                'generated_at': datetime.now(self.JST).isoformat(),
                'failed_tokens': self.failed_tokens,
                'count': len(self.failed_tokens)
            }
            
            filename = f"/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/failed_tokens_{datetime.now(self.JST).strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(failed_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"📝 失敗したトークンを {filename} に保存しました")
            
        except Exception as e:
            self.logger.error(f"❌ 失敗トークンファイル保存エラー: {e}")
    
    def run_tracking(self):
        """価格追跡を実行"""
        self.logger.info("🚀 トークン価格追跡開始")
        self.logger.info("=" * 50)
        
        try:
            # トークン情報を取得
            token_info = self.analyze_pool_tokens()
            
            if not token_info:
                self.logger.error("❌ 分析に失敗しました")
                return False
            
            # 価格データをDBに保存
            self.save_token_prices_to_db(token_info)
            
            # 失敗したトークンをファイルに保存
            self.save_failed_tokens_to_file()
            
            # 統計情報を表示
            total_tokens = len(token_info)
            successful_tokens = total_tokens - len(self.failed_tokens)
            
            self.logger.info(f"📈 追跡完了:")
            self.logger.info(f"   総トークン数: {total_tokens}")
            self.logger.info(f"   成功: {successful_tokens}")
            self.logger.info(f"   失敗: {len(self.failed_tokens)}")
            
            if self.failed_tokens:
                self.logger.warning(f"⚠️ 失敗したトークン: {', '.join(self.failed_tokens)}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 追跡実行エラー: {e}")
            return False

def main():
    """メイン関数"""
    try:
        tracker = TokenPriceTracker()
        success = tracker.run_tracking()
        
        if success:
            print("✅ トークン価格追跡が正常に完了しました")
        else:
            print("❌ トークン価格追跡に失敗しました")
            exit(1)
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        exit(1)

if __name__ == "__main__":
    print("🔍 トークン価格追跡システム")
    print("📊 ConvexPoolMetricsからトークンを抽出し、Curve Finance APIから価格を取得")
    main()
