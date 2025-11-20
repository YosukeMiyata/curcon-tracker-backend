#!/usr/bin/env python3
# =====================================
# トークン価格追跡システム
# ConvexPoolHistoryからトークンを抽出し、Curve Finance APIから価格を取得してTokenPriceHistoryテーブルに保存
# 追跡対象トークンリスト（tracked_tokens.json）に追跡対象トークンを保存
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
import sys
from pathlib import Path
import traceback

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class TokenPriceTracker:
    def __init__(self):
        """トークン価格追跡システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.convex_pool_history_table = None
        self.convex_pool_ohlc_daily_table = None
        self.token_price_table = None
        self.curve_token_prices = {}
        self.failed_tokens = []
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # 追跡対象トークンリストファイルのパス
        self.tracked_tokens_file = '/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/tracked_tokens.json'
        
        # ログ設定
        self.setup_logging()
        
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
            # ConvexPoolHistoryテーブルに接続
            self.convex_pool_history_table = self.dynamodb.Table('ConvexPoolHistory')
            self.convex_pool_history_table.load()
            self.logger.info("✅ ConvexPoolHistoryテーブルに接続しました")
            
            # ConvexPoolOHLCDailyテーブルに接続
            self.convex_pool_ohlc_daily_table = self.dynamodb.Table('ConvexPoolOHLCDaily')
            self.convex_pool_ohlc_daily_table.load()
            self.logger.info("✅ ConvexPoolOHLCDailyテーブルに接続しました")
            
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
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
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
            error_msg = f"❌ テーブル作成エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
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
            error_msg = f"❌ Curve API取得エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
        except Exception as e:
            error_msg = f"❌ 価格データ処理エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
    
    def get_all_pool_data_from_ohlc_daily(self):
        """ConvexPoolOHLCDailyから全プールデータを取得"""
        try:
            self.logger.info("📊 ConvexPoolOHLCDailyからデータを取得中...")
            response = self.convex_pool_ohlc_daily_table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.convex_pool_ohlc_daily_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            self.logger.info(f"✅ {len(items)}件のデータを取得しました")
            return items
            
        except Exception as e:
            self.logger.error(f"❌ データ取得エラー: {e}")
            return []
    
    def get_all_pool_data_from_history(self):
        """ConvexPoolHistoryから全プールデータを取得"""
        try:
            self.logger.info("📊 ConvexPoolHistoryからデータを取得中...")
            response = self.convex_pool_history_table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.convex_pool_history_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
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
    
    def extract_tokens_from_items(self, items):
        """プールデータからトークンを抽出して詳細情報を含む辞書を返す"""
        token_info = {}
        
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
    
    def load_tracked_tokens(self):
        """追跡対象トークンリストファイルから読み込む（詳細情報形式）"""
        try:
            if os.path.exists(self.tracked_tokens_file):
                with open(self.tracked_tokens_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 旧形式（トークン名のリストのみ）との互換性
                    if 'tokens' in data and isinstance(data['tokens'], list) and len(data['tokens']) > 0 and isinstance(data['tokens'][0], str):
                        # 旧形式: トークン名のリスト
                        tokens_set = set(data.get('tokens', []))
                        self.logger.info(f"✅ 追跡対象トークンリストから {len(tokens_set)}個のトークンを読み込みました（旧形式）")
                        return tokens_set
                    elif 'tokens' in data and isinstance(data['tokens'], dict):
                        # 新形式: 詳細情報を含む辞書
                        token_info = data['tokens']
                        self.logger.info(f"✅ 追跡対象トークンリストから {len(token_info)}個のトークンを読み込みました（詳細情報形式）")
                        return token_info
                    else:
                        self.logger.warning("⚠️ 追跡対象トークンリストの形式が不明です。新規作成します。")
                        return {}
            else:
                self.logger.info("📝 追跡対象トークンリストファイルが存在しません。新規作成します。")
                return {}
        except Exception as e:
            self.logger.error(f"❌ 追跡対象トークンリスト読み込みエラー: {e}")
            return {}
    
    def save_tracked_tokens(self, token_data):
        """追跡対象トークンリストファイルに保存（詳細情報形式）"""
        try:
            # token_dataがセットの場合は辞書に変換（旧形式との互換性）
            if isinstance(token_data, set):
                token_info = {}
                for token in token_data:
                    price = self.curve_token_prices.get(token)
                    token_info[token] = {
                        'symbol': token,
                        'pool_count': 0,
                        'pools': [],
                        'factory_ids': [],
                        'price': price
                    }
                token_data = token_info
            
            # 保存用データ構造
            save_data = {
                'generated_at': datetime.now(self.JST).isoformat(),
                'total_tokens': len(token_data),
                'tokens': {}
            }
            
            # トークン名でソート
            for token, info in sorted(token_data.items()):
                save_data['tokens'][token] = {
                    'symbol': info.get('symbol', token),
                    'pool_count': len(info.get('pools', [])),
                    'pools': info.get('pools', []),
                    'factory_ids': info.get('factory_ids', []),
                    'price': info.get('price')
                }
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(self.tracked_tokens_file), exist_ok=True)
            
            with open(self.tracked_tokens_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ 追跡対象トークンリストに {len(token_data)}個のトークンを保存しました: {self.tracked_tokens_file}")
            return True
        except Exception as e:
            error_msg = f"❌ 追跡対象トークンリスト保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
            return False
    
    def initialize_tracked_tokens_from_ohlc_daily(self):
        """ConvexPoolOHLCDailyからトークンを抽出して追跡対象トークンリストに保存（初回処理）"""
        try:
            self.logger.info("🚀 ConvexPoolOHLCDailyからトークン抽出開始")
            
            # ConvexPoolOHLCDailyからデータを取得
            items = self.get_all_pool_data_from_ohlc_daily()
            if not items:
                self.logger.warning("⚠️ ConvexPoolOHLCDailyにデータがありません")
                return False
            
            # トークンを抽出（詳細情報を含む辞書を返す）
            token_info = self.extract_tokens_from_items(items)
            
            if not token_info:
                self.logger.warning("⚠️ トークンが抽出できませんでした")
                return False
            
            # 追跡対象トークンリストに保存
            if self.save_tracked_tokens(token_info):
                self.logger.info(f"✅ {len(token_info)}個のトークンを追跡対象トークンリストに保存しました")
                return True
            else:
                return False
                
        except Exception as e:
            error_msg = f"❌ トークン抽出エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
            return False
    
    def update_tracked_tokens_from_history(self):
        """ConvexPoolHistoryからトークンを抽出し、追跡対象トークンリストを更新"""
        try:
            self.logger.info("🔄 ConvexPoolHistoryからトークン抽出開始")
            
            # 追跡対象トークンリストから既存のトークンを読み込む
            existing_token_info = self.load_tracked_tokens()
            
            # 旧形式（セット）の場合は辞書に変換
            if isinstance(existing_token_info, set):
                existing_token_info = {token: {'symbol': token, 'pools': [], 'factory_ids': [], 'price': self.curve_token_prices.get(token)} for token in existing_token_info}
            
            # ConvexPoolHistoryからデータを取得
            items = self.get_all_pool_data_from_history()
            if not items:
                self.logger.warning("⚠️ ConvexPoolHistoryにデータがありません")
                return existing_token_info
            
            # トークンを抽出（詳細情報を含む辞書を返す）
            new_token_info = self.extract_tokens_from_items(items)
            
            # 既存のトークン情報とマージ
            all_token_info = existing_token_info.copy()
            
            # 新規トークンと既存トークンの情報を更新
            added_tokens = []
            for token, info in new_token_info.items():
                if token not in all_token_info:
                    # 新規トークン
                    all_token_info[token] = info
                    added_tokens.append(token)
                else:
                    # 既存トークン: プールとfactory_idをマージ
                    existing_pools = set(all_token_info[token].get('pools', []))
                    existing_factory_ids = set(all_token_info[token].get('factory_ids', []))
                    
                    # 新しいプールとfactory_idを追加
                    for pool in info.get('pools', []):
                        if pool not in existing_pools:
                            all_token_info[token]['pools'].append(pool)
                    for factory_id in info.get('factory_ids', []):
                        if factory_id and factory_id not in existing_factory_ids:
                            all_token_info[token]['factory_ids'].append(factory_id)
                    
                    # 価格を更新（新しい価格がある場合）
                    if info.get('price') is not None:
                        all_token_info[token]['price'] = info.get('price')
            
            # 新規トークンがある場合、または既存トークンの情報が更新された場合は保存
            if added_tokens:
                self.logger.info(f"✅ {len(added_tokens)}個の新規トークンを検出: {', '.join(sorted(added_tokens))}")
                # 追跡対象トークンリストを更新
                if self.save_tracked_tokens(all_token_info):
                    self.logger.info(f"✅ 追跡対象トークンリストを更新しました（総数: {len(all_token_info)}個）")
                else:
                    self.logger.warning("⚠️ 追跡対象トークンリストの更新に失敗しました")
            else:
                self.logger.info("ℹ️ 新規トークンはありませんでした")
                # 既存トークンの情報（プール、factory_id）が更新されている可能性があるため、保存
                if self.save_tracked_tokens(all_token_info):
                    self.logger.info(f"✅ 追跡対象トークンリストを更新しました（既存情報の更新、総数: {len(all_token_info)}個）")
            
            return all_token_info
                
        except Exception as e:
            error_msg = f"❌ トークン更新エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
            return {}
    
    def analyze_tracked_tokens(self, tracked_token_data):
        """追跡対象トークンから価格情報を取得"""
        if not tracked_token_data:
            return {}
        
        # tracked_token_dataがセットの場合は辞書に変換（旧形式との互換性）
        if isinstance(tracked_token_data, set):
            token_info = {}
            for token in tracked_token_data:
                price = self.curve_token_prices.get(token)
                token_info[token] = {
                    'symbol': token,
                    'pools': [],
                    'factory_ids': [],
                    'price': price
                }
            return token_info
        
        # 既に詳細情報形式の場合は、価格を更新
        token_info = tracked_token_data.copy()
        
        self.logger.info(f"🔍 {len(token_info)}個の追跡対象トークンを処理中...")
        
        for token, info in token_info.items():
            # トークン価格を更新（Curve Finance APIから最新の価格を取得）
            price = self.curve_token_prices.get(token)
            if price is not None:
                info['price'] = price
        
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
                    'price': f"${price:.6f}",  # $マーク付きの価格
                    'price_numeric': Decimal(str(price))
                }
                
                # poolsとfactory_idsが存在する場合のみ追加
                if info.get('pools') and len(info['pools']) > 0:
                    item['pool_count'] = int(len(info['pools']))
                    item['pools'] = ', '.join(info['pools'])
                
                if info.get('factory_ids') and len(info['factory_ids']) > 0:
                    item['factory_ids'] = ', '.join(info['factory_ids'])
                
                # priceフィールドが空でないことを確認
                if not item['price'] or item['price'] == '':
                    self.logger.warning(f"⚠️ {token}のpriceフィールドが空です: {item['price']}")
                    item['price'] = f"${price:.6f}"  # 再設定
                
                # NoneやNaN値を除去（priceフィールドは空文字列でも保持）
                item = {k: v for k, v in item.items() if v is not None and (k == 'price' or v != '')}
                
                # pool_countを確実に整数として保存
                if 'pool_count' in item:
                    item['pool_count'] = int(item['pool_count'])
                
                self.token_price_table.put_item(Item=item)
                saved_count += 1
                
                pool_count_str = f" (プール数: {len(info['pools'])})" if info.get('pools') and len(info['pools']) > 0 else ""
                self.logger.info(f"✅ {token}価格保存: ${price:.6f}{pool_count_str}")
                
            except Exception as e:
                error_msg = f"❌ {token}保存エラー: {e}"
                self.logger.error(error_msg)
                self.failed_tokens.append(token)
                failed_count += 1
                # 個別のトークン保存エラーはSlack通知しない（大量に発生する可能性があるため）
        
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
            error_msg = f"❌ 失敗トークンファイル保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
    
    def run_tracking(self):
        """価格追跡を実行（定期実行用）"""
        self.logger.info("🚀 トークン価格追跡開始")
        self.logger.info("=" * 50)
        
        try:
            # 1. ConvexPoolHistoryからトークンを抽出し、ファイルAを更新
            tracked_tokens = self.update_tracked_tokens_from_history()
            
            if not tracked_tokens:
                error_msg = "❌ 追跡対象トークンが取得できませんでした"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="Token Price Tracker"
                    )
                return False
            
            # 2. 追跡対象トークンから価格情報を取得
            token_info = self.analyze_tracked_tokens(tracked_tokens)
            
            if not token_info:
                error_msg = "❌ トークン情報の分析に失敗しました"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="Token Price Tracker"
                    )
                return False
            
            # 3. 価格データをDBに保存
            self.save_token_prices_to_db(token_info)
            
            # 4. 失敗したトークンをファイルに保存
            self.save_failed_tokens_to_file()
            
            # 5. 統計情報を表示
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
            error_msg = f"❌ 追跡実行エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token Price Tracker",
                    error=e
                )
            return False

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='トークン価格追跡システム')
    parser.add_argument('--init', action='store_true', help='ConvexPoolOHLCDailyからトークンを抽出してファイルAを初期化')
    args = parser.parse_args()
    
    try:
        tracker = TokenPriceTracker()
        
        if args.init:
            # 初期化モード: ConvexPoolOHLCDailyからトークンを抽出して追跡対象トークンリストに保存
            print("🔍 トークン価格追跡システム - 初期化モード")
            print("📊 ConvexPoolOHLCDailyからトークンを抽出して追跡対象トークンリストを初期化")
            success = tracker.initialize_tracked_tokens_from_ohlc_daily()
            if success:
                print("✅ ファイルAの初期化が正常に完了しました")
            else:
                print("❌ ファイルAの初期化に失敗しました")
                exit(1)
        else:
            # 通常モード: 定期実行
            print("🔍 トークン価格追跡システム")
            print("📊 ConvexPoolHistoryからトークンを抽出し、Curve Finance APIから価格を取得")
            success = tracker.run_tracking()
            
            if success:
                print("✅ トークン価格追跡が正常に完了しました")
            else:
                print("❌ トークン価格追跡に失敗しました")
                exit(1)
            
    except Exception as e:
        error_msg = f"❌ エラー: {e}"
        print(error_msg)
        # Slack通知（グローバルインスタンスを使用）
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from utils.slack_notifier import SlackNotifier
            notifier = SlackNotifier()
            notifier.notify_error(
                message=error_msg,
                system_name="Token Price Tracker",
                error=e
            )
        except Exception:
            pass  # Slack通知失敗は無視
        exit(1)

if __name__ == "__main__":
    main()
