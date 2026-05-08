#!/usr/bin/env python3
# =====================================
# トークンOHLCデータ集約システム
# TokenPriceHistoryテーブルからOHLCデータを集約し、TokenOHLCDailyテーブルに保存
# 処理完了後、TokenPriceHistoryテーブルをクリア
# =====================================

import boto3
import logging
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from botocore.exceptions import ClientError
from decimal import Decimal
import sys
from pathlib import Path
import traceback

# Supabase関連のインポート
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class TokenOHLCAggregator:
    def __init__(self):
        """OHLC集約システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.price_history_table = None
        self.ohlc_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # APIエンドポイント
        self.data_source_url = "https://api.curve.finance/api/getPools/all/ethereum"
        
        # 実行環境のベースディレクトリ
        default_base_dir = Path("/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker")
        if os.getenv("GITHUB_ACTIONS") == "true" or not default_base_dir.exists():
            self.base_dir = Path(__file__).resolve().parent
        else:
            self.base_dir = default_base_dir

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
        self.setup_database()
    
    def setup_logging(self):
        """ログ設定"""
        log_file = str(self.base_dir / "token_ohlc_aggregator.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_database(self):
        """DB設定（Supabase優先、なければDynamoDB）"""
        self.db_mode = "dynamodb"
        self.supabase = None

        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if supabase_url and supabase_key:
            if not SUPABASE_AVAILABLE:
                self.logger.error("❌ supabase パッケージが見つかりません")
                return False
            return self.setup_supabase(supabase_url, supabase_key)

        return self.setup_tables()

    def setup_supabase(self, supabase_url: str, supabase_key: str):
        """Supabase接続設定"""
        try:
            self.supabase = create_client(supabase_url, supabase_key)
            self.db_mode = "supabase"
            self.logger.info("✅ Supabase接続成功")
            return True
        except Exception as e:
            self.logger.error(f"❌ Supabase接続エラー: {e}")
            return False

    def _supabase_table_map(self):
        return {
            "TokenPriceHistory": {
                "table": "token_price_history",
                "columns": {
                    "token": "token",
                    "timestamp": "timestamp",
                    "timezone": "timezone",
                    "price": "price",
                    "price_numeric": "price_numeric",
                    "pool_count": "pool_count",
                    "pools": "pools",
                    "factory_ids": "factory_ids",
                    "data_source": "data_source",
                    "datetime": "datetime",
                    "created_at": "created_at",
                },
            },
            "TokenOHLCDaily": {
                "table": "token_ohlc_daily",
                "on_conflict": "token,timestamp",
                "columns": {
                    "token": "token",
                    "timestamp": "timestamp",
                    "timezone": "timezone",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "sample_count": "sample_count",
                    "data_source": "data_source",
                    "datetime": "datetime",
                    "created_at": "created_at",
                },
            },
        }

    def _normalize_value(self, value):
        if isinstance(value, Decimal):
            if value % 1 == 0:
                return int(value)
            return float(value)
        if isinstance(value, list):
            return [self._normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._normalize_value(v) for k, v in value.items()}
        return value

    def _map_from_supabase(self, table_name: str, row: dict) -> dict:
        mapping = self._supabase_table_map().get(table_name, {})
        columns = mapping.get("columns", {})
        reverse = {v: k for k, v in columns.items()}
        mapped = {}
        for key, value in row.items():
            if key in reverse:
                mapped[reverse[key]] = value
        return mapped

    def db_scan_items(self, table_name: str) -> list:
        if self.db_mode == "supabase":
            mapping = self._supabase_table_map().get(table_name, {})
            if not mapping:
                return []
            items = []
            offset = 0
            page_size = 1000
            while True:
                response = self.supabase.table(mapping["table"]).select("*").range(
                    offset, offset + page_size - 1
                ).execute()
                data = response.data or []
                if not data:
                    break
                items.extend([self._map_from_supabase(table_name, row) for row in data])
                if len(data) < page_size:
                    break
                offset += page_size
            return items

        table = self.price_history_table
        response = table.scan()
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
        return items

    def db_put_item(self, table_name: str, item: dict):
        if self.db_mode == "supabase":
            mapping = self._supabase_table_map().get(table_name, {})
            if not mapping:
                return
            columns = mapping.get("columns", {})
            payload = {
                columns[key]: self._normalize_value(value)
                for key, value in item.items()
                if key in columns
            }
            if not payload:
                return
            self.supabase.table(mapping["table"]).upsert(
                payload, on_conflict=mapping.get("on_conflict")
            ).execute()
            return

        self.ohlc_table.put_item(Item=item)

    def db_delete_items(self, table_name: str, keys: list) -> int:
        if self.db_mode == "supabase":
            mapping = self._supabase_table_map().get(table_name, {})
            if not mapping:
                return 0
            deleted = 0
            for key in keys:
                query = self.supabase.table(mapping["table"]).delete()
                for key_name, value in key.items():
                    column = mapping["columns"].get(key_name, key_name)
                    query = query.eq(column, value)
                query.execute()
                deleted += 1
            return deleted

        deleted = 0
        for key in keys:
            self.price_history_table.delete_item(Key=key)
            deleted += 1
        return deleted

    def setup_tables(self):
        """DynamoDBテーブルに接続"""
        try:
            self.price_history_table = self.dynamodb.Table('TokenPriceHistory')
            self.price_history_table.load()
            self.logger.info("✅ TokenPriceHistoryテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('TokenOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ TokenOHLCDailyテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token OHLC Aggregator",
                    error=e
                )
            raise e
    
    def get_yesterday_price_data(self):
        """昨日のTokenPriceHistoryデータを全件取得"""
        try:
            self.logger.info("📊 昨日のTokenPriceHistoryデータを取得中...")
            
            # 昨日の日時範囲を計算（JST）
            now_jst = datetime.now(self.JST)
            yesterday_start = (now_jst - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            yesterday_end = yesterday_start + timedelta(days=1)
            
            self.logger.info(f"📅 対象期間(JST): {yesterday_start.isoformat()} ～ {yesterday_end.isoformat()}")
            
            # 全データを取得
            all_items = self.db_scan_items("TokenPriceHistory")
            
            # 昨日のデータのみにフィルタリング
            yesterday_items = []
            for item in all_items:
                timestamp_str = item.get('timestamp', '')
                if not timestamp_str:
                    continue
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    timestamp_jst = timestamp.astimezone(self.JST)
                    if yesterday_start <= timestamp_jst < yesterday_end:
                        yesterday_items.append(item)
                except (ValueError, TypeError):
                    continue
            
            self.logger.info(f"✅ {len(yesterday_items)}件のデータを取得しました")
            return yesterday_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token OHLC Aggregator",
                    error=e
                )
            return []
    
    def aggregate_ohlc_data(self, items):
        """OHLCデータを集約"""
        if not items:
            self.logger.warning("⚠️ 集約するデータがありません")
            return {}
        
        # トークンごとにデータをグループ化
        token_data = defaultdict(list)
        
        for item in items:
            token = item.get('token')
            price_numeric = item.get('price_numeric')
            
            if token and price_numeric is not None:
                # Decimal型をfloat型に変換
                price = float(price_numeric)
                token_data[token].append({
                    'timestamp': item.get('timestamp'),
                    'price': price
                })
        
        # OHLCデータを計算
        ohlc_data = {}
        for token, prices in token_data.items():
            # タイムスタンプでソート
            sorted_prices = sorted(prices, key=lambda x: x['timestamp'])
            
            if sorted_prices:
                # Open, High, Low, Closeを計算
                open_price = sorted_prices[0]['price']
                close_price = sorted_prices[-1]['price']
                high_price = max(p['price'] for p in sorted_prices)
                low_price = min(p['price'] for p in sorted_prices)
                sample_count = len(sorted_prices)
                
                ohlc_data[token] = {
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'sample_count': sample_count
                }
                
                self.logger.info(f"✅ {token} OHLC集約: Open={open_price:.6f}, High={high_price:.6f}, Low={low_price:.6f}, Close={close_price:.6f}, Samples={sample_count}")
        
        return ohlc_data
    
    def save_ohlc_data(self, ohlc_data, target_date):
        """OHLCデータをTokenOHLCDailyテーブルに保存"""
        if not ohlc_data:
            self.logger.warning("⚠️ 保存するOHLCデータがありません")
            return False
        
        try:
            self.logger.info("💾 TokenOHLCDailyテーブルに保存中...")
            
            # タイムスタンプを生成（JSTの日付のみ）
            date_timestamp = target_date.strftime('%Y-%m-%d')
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            failed_count = 0
            
            for token, data in ohlc_data.items():
                try:
                    item = {
                        'token': token,
                        'timestamp': date_timestamp,
                        'open': Decimal(str(data['open'])),
                        'high': Decimal(str(data['high'])),
                        'low': Decimal(str(data['low'])),
                        'close': Decimal(str(data['close'])),
                        'sample_count': int(data['sample_count']),
                        'timezone': 'JST',
                        'data_source': self.data_source_url,
                        'created_at': jst_created_at
                    }
                    
                    self.db_put_item("TokenOHLCDaily", item)
                    saved_count += 1
                    
                except Exception as e:
                    self.logger.error(f"❌ {token}保存エラー: {e}")
                    failed_count += 1
            
            self.logger.info(f"📊 OHLCデータ保存完了: {saved_count}件成功, {failed_count}件失敗")
            return saved_count > 0
            
        except Exception as e:
            error_msg = f"❌ OHLCデータ保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token OHLC Aggregator",
                    error=e
                )
            return False
    
    def clear_price_history_table_except_midnight(self):
        """TokenPriceHistoryテーブルをクリア（昨日分のみ削除）"""
        try:
            self.logger.info("🗑️ TokenPriceHistoryテーブルをクリア中（昨日分のみ削除）...")
            
            # 昨日の日時範囲を計算（JST）
            now_jst = datetime.now(self.JST)
            yesterday_start = (now_jst - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            yesterday_end = yesterday_start + timedelta(days=1)
            
            self.logger.info(
                f"📅 削除対象期間(JST): {yesterday_start.isoformat()} ～ {yesterday_end.isoformat()}"
            )
            
            # 全データを取得
            all_items = self.db_scan_items("TokenPriceHistory")
            
            # 昨日分のみ削除
            deleted_count = 0
            kept_count = 0
            failed_count = 0
            
            delete_keys = []
            for item in all_items:
                timestamp_str = item.get('timestamp', '')
                if not timestamp_str:
                    kept_count += 1
                    continue

                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    timestamp_jst = timestamp.astimezone(self.JST)

                    if yesterday_start <= timestamp_jst < yesterday_end:
                        delete_keys.append({'token': item['token'], 'timestamp': item['timestamp']})
                    else:
                        kept_count += 1
                except Exception as e:
                    self.logger.error(f"❌ 削除エラー {item.get('token')}: {e}")
                    failed_count += 1

            if delete_keys:
                deleted_count = self.db_delete_items("TokenPriceHistory", delete_keys)
            
            self.logger.info(f"✅ クリア完了: {deleted_count}件削除, {kept_count}件保持, {failed_count}件失敗")
            return True
            
        except Exception as e:
            error_msg = f"❌ テーブルクリアエラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token OHLC Aggregator",
                    error=e
                )
            return False
    
    def run_daily_aggregation(self):
        """日次OHLC集約を実行"""
        self.logger.info("🚀 日次OHLC集約開始")
        self.logger.info("=" * 50)
        
        try:
            # 昨日の日付を取得
            now_jst = datetime.now(self.JST)
            yesterday = now_jst - timedelta(days=1)
            
            self.logger.info(f"📅 集約対象日: {yesterday.strftime('%Y-%m-%d')}")
            
            # 1. 昨日のTokenPriceHistoryデータを取得
            items = self.get_yesterday_price_data()
            
            # 2. データが1件もない場合
            if not items:
                self.logger.warning("⚠️ 昨日のデータが1件もありません。処理を終了します。")
                self.logger.info("📊 TokenPriceHistoryテーブルはクリアされません。")
                return False
            
            # 3. OHLCデータを集約
            ohlc_data = self.aggregate_ohlc_data(items)
            
            # 4. TokenOHLCDailyテーブルに保存
            if not self.save_ohlc_data(ohlc_data, yesterday):
                error_msg = "❌ OHLCデータ保存に失敗しました。処理を中止します。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="Token OHLC Aggregator"
                    )
                return False
            
            # 5. TokenPriceHistoryテーブルをクリア（深夜00:00のデータは保持）
            if not self.clear_price_history_table_except_midnight():
                error_msg = "❌ TokenPriceHistoryテーブルのクリアに失敗しました。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="Token OHLC Aggregator"
                    )
                return False
            
            self.logger.info("=" * 50)
            self.logger.info("✅ 日次OHLC集約が正常に完了しました")
            return True
            
        except Exception as e:
            error_msg = f"❌ 日次OHLC集約エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error("❌ TokenPriceHistoryテーブルはクリアされません。")
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Token OHLC Aggregator",
                    error=e
                )
            return False

def main():
    """メイン関数"""
    # JSTの指定時間のみ実行（手動実行での誤クリア防止）
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    target_hour = int(os.getenv("TARGET_HOUR", "0"))
    target_minute = int(os.getenv("TARGET_MINUTE", "0"))
    tolerance_min = int(os.getenv("TARGET_TOLERANCE_MINUTES", "10"))

    if os.getenv("FORCE_RUN") != "true":
        target_time = now_jst.replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0
        )
        delta_min = abs((now_jst - target_time).total_seconds()) / 60.0
        if delta_min > tolerance_min:
            print(
                f"⏭️  JST {target_hour:02d}:{target_minute:02d}±{tolerance_min}分外のためスキップ"
            )
            return

    try:
        aggregator = TokenOHLCAggregator()
        success = aggregator.run_daily_aggregation()
        
        if success:
            print("✅ 日次OHLC集約が正常に完了しました")
        else:
            print("❌ 日次OHLC集約に失敗しました")
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
                system_name="Token OHLC Aggregator",
                error=e
            )
        except Exception:
            pass  # Slack通知失敗は無視
        exit(1)

if __name__ == "__main__":
    print("📊 トークンOHLCデータ集約システム")
    print("📈 TokenPriceHistoryからOHLCデータを集約し、TokenOHLCDailyに保存")
    main()

