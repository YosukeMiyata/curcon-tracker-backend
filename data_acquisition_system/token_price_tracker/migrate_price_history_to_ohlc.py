#!/usr/bin/env python3
# =====================================
# PriceHistoryからTokenOHLCDailyへのデータ移行スクリプト
# PriceHistoryテーブルの$CRVと$CVXのデータ（2025年10月31日まで）を
# TokenOHLCDailyテーブルのOHLC形式に集約して保存
# =====================================

import boto3
from boto3.dynamodb.conditions import Key
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from botocore.exceptions import ClientError
from decimal import Decimal
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

class PriceHistoryToOHLCMigrator:
    def __init__(self):
        """PriceHistoryからTokenOHLCDailyへの移行システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.price_history_table = None
        self.ohlc_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # データソース
        self.data_source_url = "PriceHistory (CoinGecko)"
        
        # 対象トークン
        self.target_tokens = ['CRV', 'CVX']
        
        # 終了日（2025年10月31日）
        self.end_date = datetime(2025, 10, 31, 23, 59, 59, tzinfo=self.JST)
        
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
    
    def setup_logging(self):
        """ログ設定"""
        log_file = Path(__file__).parent / 'migrate_price_history_to_ohlc.log'
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
            self.price_history_table = self.dynamodb.Table('PriceHistory')
            self.price_history_table.load()
            self.logger.info("✅ PriceHistoryテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('TokenOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ TokenOHLCDailyテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to OHLC Migrator",
                    error=e
                )
            raise e
    
    def get_price_history_data(self):
        """PriceHistoryテーブルからCRVとCVXのデータを取得（2025年10月31日まで）"""
        try:
            self.logger.info("📊 PriceHistoryテーブルからデータを取得中...")
            self.logger.info(f"📅 対象期間: ～ {self.end_date.strftime('%Y-%m-%d %H:%M:%S JST')}")
            self.logger.info(f"🎯 対象トークン: {', '.join(self.target_tokens)}")
            
            all_items = []
            
            # 各トークンごとにクエリ
            for token in self.target_tokens:
                self.logger.info(f"🔍 {token}のデータを取得中...")
                
                try:
                    # Queryを使用してassetでフィルタリング
                    response = self.price_history_table.query(
                        KeyConditionExpression=Key('asset').eq(token)
                    )
                    all_items.extend(response.get('Items', []))
                    
                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = self.price_history_table.query(
                            KeyConditionExpression=Key('asset').eq(token),
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        all_items.extend(response.get('Items', []))
                    
                    self.logger.info(f"✅ {token}: {len([i for i in all_items if i.get('asset') == token])}件取得")
                    
                except Exception as e:
                    self.logger.error(f"❌ {token}のデータ取得エラー: {e}")
                    continue
            
            # 2025年10月31日までのデータにフィルタリング
            filtered_items = []
            end_date_iso = self.end_date.isoformat()
            
            for item in all_items:
                timestamp = item.get('timestamp', '')
                if timestamp and timestamp <= end_date_iso:
                    # price_usdが存在することを確認
                    if 'price_usd' in item:
                        filtered_items.append(item)
            
            self.logger.info(f"✅ フィルタリング後: {len(filtered_items)}件のデータ")
            return filtered_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to OHLC Migrator",
                    error=e
                )
            return []
    
    def aggregate_ohlc_data(self, items):
        """OHLCデータを日次で集約"""
        if not items:
            self.logger.warning("⚠️ 集約するデータがありません")
            return {}
        
        # トークンと日付ごとにデータをグループ化
        token_date_data = defaultdict(list)
        
        for item in items:
            asset = item.get('asset')
            timestamp_str = item.get('timestamp', '')
            price_usd = item.get('price_usd')
            
            if not asset or not timestamp_str or price_usd is None:
                continue
            
            try:
                # ISO形式のタイムスタンプをパース
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                # JSTに変換
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp_jst = timestamp.astimezone(self.JST)
                
                # 日付キー（YYYY-MM-DD形式）
                date_key = timestamp_jst.strftime('%Y-%m-%d')
                
                # Decimal型をfloat型に変換
                price = float(price_usd)
                
                token_date_data[(asset, date_key)].append({
                    'timestamp': timestamp_str,
                    'timestamp_jst': timestamp_jst,
                    'price': price
                })
                
            except (ValueError, TypeError) as e:
                self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                continue
        
        # OHLCデータを計算
        ohlc_data = {}
        for (token, date_key), prices in token_date_data.items():
            # タイムスタンプでソート
            sorted_prices = sorted(prices, key=lambda x: x['timestamp'])
            
            if sorted_prices:
                # Open, High, Low, Closeを計算
                open_price = sorted_prices[0]['price']
                close_price = sorted_prices[-1]['price']
                high_price = max(p['price'] for p in sorted_prices)
                low_price = min(p['price'] for p in sorted_prices)
                sample_count = len(sorted_prices)
                
                ohlc_data[(token, date_key)] = {
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'sample_count': sample_count
                }
                
                self.logger.info(
                    f"✅ {token} {date_key} OHLC集約: "
                    f"Open={open_price:.6f}, High={high_price:.6f}, "
                    f"Low={low_price:.6f}, Close={close_price:.6f}, Samples={sample_count}"
                )
        
        return ohlc_data
    
    def check_existing_data(self, token, date_key):
        """TokenOHLCDailyテーブルに既存データがあるかチェック"""
        try:
            response = self.ohlc_table.get_item(
                Key={
                    'token': token,
                    'timestamp': date_key
                }
            )
            return 'Item' in response
        except Exception as e:
            self.logger.warning(f"⚠️ 既存データチェックエラー ({token}, {date_key}): {e}")
            return False
    
    def save_ohlc_data(self, ohlc_data):
        """OHLCデータをTokenOHLCDailyテーブルに保存"""
        if not ohlc_data:
            self.logger.warning("⚠️ 保存するOHLCデータがありません")
            return False
        
        try:
            self.logger.info("💾 TokenOHLCDailyテーブルに保存中...")
            
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            skipped_count = 0
            failed_count = 0
            
            # 日付順にソートして処理
            sorted_items = sorted(ohlc_data.items(), key=lambda x: (x[0][0], x[0][1]))
            
            for (token, date_key), data in sorted_items:
                try:
                    # 既存データをチェック
                    if self.check_existing_data(token, date_key):
                        self.logger.info(f"⏭️ {token} {date_key} は既に存在するためスキップ")
                        skipped_count += 1
                        continue
                    
                    item = {
                        'token': token,
                        'timestamp': date_key,
                        'open': Decimal(str(data['open'])),
                        'high': Decimal(str(data['high'])),
                        'low': Decimal(str(data['low'])),
                        'close': Decimal(str(data['close'])),
                        'sample_count': int(data['sample_count']),
                        'timezone': 'JST',
                        'data_source': self.data_source_url,
                        'created_at': jst_created_at
                    }
                    
                    self.ohlc_table.put_item(Item=item)
                    saved_count += 1
                    self.logger.debug(f"💾 {token} {date_key} を保存しました")
                    
                    if saved_count % 10 == 0:
                        self.logger.info(f"📊 進捗: {saved_count}件保存完了")
                    
                except Exception as e:
                    self.logger.error(f"❌ {token} {date_key}保存エラー: {e}")
                    self.logger.error(traceback.format_exc())
                    failed_count += 1
            
            self.logger.info(
                f"📊 OHLCデータ保存完了: {saved_count}件成功, "
                f"{skipped_count}件スキップ, {failed_count}件失敗"
            )
            return saved_count > 0
            
        except Exception as e:
            error_msg = f"❌ OHLCデータ保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to OHLC Migrator",
                    error=e
                )
            return False
    
    def run_migration(self):
        """移行処理を実行"""
        self.logger.info("🚀 PriceHistoryからTokenOHLCDailyへの移行開始")
        self.logger.info("=" * 50)
        
        try:
            # 1. PriceHistoryテーブルからデータを取得
            items = self.get_price_history_data()
            
            if not items:
                self.logger.warning("⚠️ 取得したデータが1件もありません。処理を終了します。")
                return True
            
            # 2. OHLCデータを集約
            ohlc_data = self.aggregate_ohlc_data(items)
            
            if not ohlc_data:
                self.logger.warning("⚠️ 集約したOHLCデータがありません。処理を終了します。")
                return True
            
            # 3. TokenOHLCDailyテーブルに保存
            if not self.save_ohlc_data(ohlc_data):
                error_msg = "❌ OHLCデータ保存に失敗しました。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="PriceHistory to OHLC Migrator"
                    )
                return False
            
            self.logger.info("=" * 50)
            self.logger.info("✅ 移行処理が正常に完了しました")
            return True
            
        except Exception as e:
            error_msg = f"❌ 移行処理エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to OHLC Migrator",
                    error=e
                )
            return False

def main():
    """メイン関数"""
    try:
        migrator = PriceHistoryToOHLCMigrator()
        success = migrator.run_migration()
        
        if success:
            print("✅ 移行処理が正常に完了しました")
        else:
            print("❌ 移行処理に失敗しました")
            exit(1)
            
    except Exception as e:
        error_msg = f"❌ エラー: {e}"
        print(error_msg)
        print(traceback.format_exc())
        # Slack通知（グローバルインスタンスを使用）
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from utils.slack_notifier import SlackNotifier
            notifier = SlackNotifier()
            notifier.notify_error(
                message=error_msg,
                system_name="PriceHistory to OHLC Migrator",
                error=e
            )
        except Exception:
            pass  # Slack通知失敗は無視
        exit(1)

if __name__ == "__main__":
    print("📊 PriceHistoryからTokenOHLCDailyへのデータ移行システム")
    print("📈 PriceHistoryテーブルの$CRVと$CVXデータ（2025年10月31日まで）をOHLC形式に集約")
    main()

