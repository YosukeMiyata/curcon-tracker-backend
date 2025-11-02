#!/usr/bin/env python3
# =====================================
# トークンOHLCデータ集約システム
# TokenPriceHistoryテーブルからOHLCデータを集約し、TokenOHLCDailyテーブルに保存
# 処理完了後、TokenPriceHistoryテーブルをクリア
# =====================================

import boto3
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from botocore.exceptions import ClientError
from decimal import Decimal

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
        
        # ログ設定
        self.setup_logging()
        
        # テーブル接続
        self.setup_tables()
    
    def setup_logging(self):
        """ログ設定"""
        log_file = '/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/token_ohlc_aggregator.log'
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
            self.price_history_table = self.dynamodb.Table('TokenPriceHistory')
            self.price_history_table.load()
            self.logger.info("✅ TokenPriceHistoryテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('TokenOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ TokenOHLCDailyテーブルに接続しました")
                    
        except ClientError as e:
            self.logger.error(f"❌ テーブル接続エラー: {e}")
            raise e
    
    def get_yesterday_price_data(self):
        """昨日のTokenPriceHistoryデータを全件取得"""
        try:
            self.logger.info("📊 昨日のTokenPriceHistoryデータを取得中...")
            
            # 昨日の日時範囲を計算（JST）
            now_jst = datetime.now(self.JST)
            yesterday_start = (now_jst - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            
            # ISO形式のタイムスタンプに変換
            yesterday_start_iso = yesterday_start.isoformat()
            yesterday_end_iso = yesterday_end.isoformat()
            
            self.logger.info(f"📅 対象期間: {yesterday_start_iso} ～ {yesterday_end_iso}")
            
            # 全データをスキャン
            all_items = []
            response = self.price_history_table.scan()
            all_items.extend(response.get('Items', []))
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.price_history_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_items.extend(response.get('Items', []))
            
            # 昨日のデータのみにフィルタリング
            yesterday_items = []
            for item in all_items:
                timestamp = item.get('timestamp', '')
                if timestamp >= yesterday_start_iso and timestamp < yesterday_end_iso:
                    yesterday_items.append(item)
            
            self.logger.info(f"✅ {len(yesterday_items)}件のデータを取得しました")
            return yesterday_items
            
        except Exception as e:
            self.logger.error(f"❌ データ取得エラー: {e}")
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
                    
                    self.ohlc_table.put_item(Item=item)
                    saved_count += 1
                    
                except Exception as e:
                    self.logger.error(f"❌ {token}保存エラー: {e}")
                    failed_count += 1
            
            self.logger.info(f"📊 OHLCデータ保存完了: {saved_count}件成功, {failed_count}件失敗")
            return saved_count > 0
            
        except Exception as e:
            self.logger.error(f"❌ OHLCデータ保存エラー: {e}")
            return False
    
    def clear_price_history_table_except_midnight(self):
        """TokenPriceHistoryテーブルをクリア（深夜00:00のデータは保持）"""
        try:
            self.logger.info("🗑️ TokenPriceHistoryテーブルをクリア中（深夜00:00のデータは保持）...")
            
            # 今日の深夜00:00のタイムスタンプを計算
            now_jst = datetime.now(self.JST)
            today_midnight = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
            midnight_iso = today_midnight.isoformat()
            
            self.logger.info(f"📅 保持するデータ: {midnight_iso} 以降")
            
            # 全データを取得
            all_items = []
            response = self.price_history_table.scan()
            all_items.extend(response.get('Items', []))
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.price_history_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_items.extend(response.get('Items', []))
            
            # 深夜00:00以降のデータは保持し、それ以前のデータを削除
            deleted_count = 0
            kept_count = 0
            failed_count = 0
            
            for item in all_items:
                timestamp = item.get('timestamp', '')
                
                # 深夜00:00以降のデータは保持
                if timestamp >= midnight_iso:
                    kept_count += 1
                    continue
                
                # 深夜00:00以前のデータを削除
                try:
                    self.price_history_table.delete_item(
                        Key={
                            'token': item['token'],
                            'timestamp': item['timestamp']
                        }
                    )
                    deleted_count += 1
                    
                except Exception as e:
                    self.logger.error(f"❌ 削除エラー {item.get('token')}: {e}")
                    failed_count += 1
            
            self.logger.info(f"✅ クリア完了: {deleted_count}件削除, {kept_count}件保持, {failed_count}件失敗")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ テーブルクリアエラー: {e}")
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
                return True
            
            # 3. OHLCデータを集約
            ohlc_data = self.aggregate_ohlc_data(items)
            
            # 4. TokenOHLCDailyテーブルに保存
            if not self.save_ohlc_data(ohlc_data, yesterday):
                self.logger.error("❌ OHLCデータ保存に失敗しました。処理を中止します。")
                return False
            
            # 5. TokenPriceHistoryテーブルをクリア（深夜00:00のデータは保持）
            if not self.clear_price_history_table_except_midnight():
                self.logger.error("❌ TokenPriceHistoryテーブルのクリアに失敗しました。")
                return False
            
            self.logger.info("=" * 50)
            self.logger.info("✅ 日次OHLC集約が正常に完了しました")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 日次OHLC集約エラー: {e}")
            self.logger.error("❌ TokenPriceHistoryテーブルはクリアされません。")
            return False

def main():
    """メイン関数"""
    try:
        aggregator = TokenOHLCAggregator()
        success = aggregator.run_daily_aggregation()
        
        if success:
            print("✅ 日次OHLC集約が正常に完了しました")
        else:
            print("❌ 日次OHLC集約に失敗しました")
            exit(1)
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        exit(1)

if __name__ == "__main__":
    print("📊 トークンOHLCデータ集約システム")
    print("📈 TokenPriceHistoryからOHLCデータを集約し、TokenOHLCDailyに保存")
    main()

