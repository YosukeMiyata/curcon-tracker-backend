#!/usr/bin/env python3
# =====================================
# USD/JPY OHLCデータ集約システム
# USDJPYHistoryテーブルからOHLCデータを集約し、USDJPYOHLCDailyテーブルに保存
# 処理完了後、USDJPYHistoryテーブルをクリア
# =====================================

import boto3
import logging
from datetime import datetime, timezone, timedelta
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

class USDJPYOHLCAggregator:
    def __init__(self):
        """OHLC集約システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.usdjpy_history_table = None
        self.ohlc_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # データソース
        self.data_source = 'AlphaVantage'
        
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
        log_file = Path(__file__).parent / 'usdjpy_ohlc_aggregator.log'
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
            self.usdjpy_history_table = self.dynamodb.Table('USDJPYHistory')
            self.usdjpy_history_table.load()
            self.logger.info("✅ USDJPYHistoryテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('USDJPYOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ USDJPYOHLCDailyテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            raise e
    
    def get_yesterday_rate_data(self):
        """昨日のUSDJPYHistoryデータを全件取得"""
        try:
            self.logger.info("📊 昨日のUSDJPYHistoryデータを取得中...")
            
            # 昨日の日時範囲を計算（JST）
            now_jst = datetime.now(self.JST)
            yesterday_start = (now_jst - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            
            yesterday_start_iso = yesterday_start.isoformat()
            yesterday_end_iso = yesterday_end.isoformat()
            
            self.logger.info(f"   取得範囲: {yesterday_start_iso} ～ {yesterday_end_iso}")
            
            # 全データをスキャン
            all_items = []
            response = self.usdjpy_history_table.scan(
                FilterExpression='asset = :asset',
                ExpressionAttributeValues={':asset': 'USDJPY'}
            )
            all_items.extend(response.get('Items', []))
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.usdjpy_history_table.scan(
                    FilterExpression='asset = :asset',
                    ExpressionAttributeValues={':asset': 'USDJPY'},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_items.extend(response.get('Items', []))
            
            # 昨日のデータをフィルタリング
            yesterday_items = []
            for item in all_items:
                timestamp = item.get('timestamp', '')
                if timestamp >= yesterday_start_iso and timestamp < yesterday_end_iso:
                    yesterday_items.append(item)
            
            self.logger.info(f"✅ 昨日のデータ: {len(yesterday_items)}件取得")
            return yesterday_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            return []
    
    def aggregate_ohlc_data(self, items):
        """OHLCデータを集約"""
        if not items:
            self.logger.warning("⚠️ 集約するデータがありません")
            return None
        
        try:
            # タイムスタンプでソート
            sorted_items = sorted(items, key=lambda x: x.get('timestamp', ''))
            
            # rate値を取得（Decimal型をfloat型に変換）
            rates = []
            for item in sorted_items:
                rate = item.get('rate')
                if rate is not None:
                    if isinstance(rate, Decimal):
                        rates.append(float(rate))
                    else:
                        rates.append(float(rate))
            
            if not rates:
                self.logger.warning("⚠️ 有効なrateデータがありません")
                return None
            
            # Open, High, Low, Closeを計算
            open_price = rates[0]
            close_price = rates[-1]
            high_price = max(rates)
            low_price = min(rates)
            sample_count = len(rates)
            
            ohlc_data = {
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'sample_count': sample_count
            }
            
            self.logger.info(f"✅ USDJPY OHLC集約: Open={open_price:.2f}, High={high_price:.2f}, Low={low_price:.2f}, Close={close_price:.2f}, Samples={sample_count}")
            
            return ohlc_data
            
        except Exception as e:
            error_msg = f"❌ OHLC集約エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            return None
    
    def save_ohlc_data(self, ohlc_data, target_date):
        """OHLCデータをUSDJPYOHLCDailyテーブルに保存"""
        if not ohlc_data:
            self.logger.warning("⚠️ 保存するOHLCデータがありません")
            return False
        
        try:
            self.logger.info("💾 USDJPYOHLCDailyテーブルに保存中...")
            
            # タイムスタンプを生成（JSTの日付のみ）
            date_timestamp = target_date.strftime('%Y-%m-%d')
            jst_created_at = datetime.now(self.JST).isoformat()
            
            # datetimeフィールド（JSTのISO形式）
            # target_dateは既にJSTタイムゾーンが設定されているので、そのまま使用
            date_obj = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            jst_datetime = date_obj.isoformat()
            
            try:
                item = {
                    'asset': 'USDJPY',
                    'timestamp': date_timestamp,
                    'timezone': 'JST',
                    'open': Decimal(str(ohlc_data['open'])),
                    'high': Decimal(str(ohlc_data['high'])),
                    'low': Decimal(str(ohlc_data['low'])),
                    'close': Decimal(str(ohlc_data['close'])),
                    'sample_count': int(ohlc_data['sample_count']),
                    'data_source': self.data_source,
                    'datetime': jst_datetime,
                    'created_at': jst_created_at
                }
                
                self.ohlc_table.put_item(Item=item)
                self.logger.info(f"✅ USDJPY OHLCデータ保存完了: {date_timestamp}")
                return True
                
            except Exception as e:
                self.logger.error(f"❌ OHLCデータ保存エラー: {e}")
                return False
            
        except Exception as e:
            error_msg = f"❌ OHLCデータ保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            return False
    
    def clear_usdjpy_history_table(self):
        """USDJPYHistoryテーブルを全件クリア"""
        try:
            self.logger.info("🗑️ USDJPYHistoryテーブルをクリア中...")
            
            # 全データを取得
            all_items = []
            response = self.usdjpy_history_table.scan()
            all_items.extend(response.get('Items', []))
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.usdjpy_history_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_items.extend(response.get('Items', []))
            
            if not all_items:
                self.logger.info("✅ USDJPYHistoryテーブル: データなし（クリア不要）")
                return True
            
            # 全データを削除
            deleted_count = 0
            failed_count = 0
            
            for item in all_items:
                try:
                    self.usdjpy_history_table.delete_item(
                        Key={
                            'asset': item['asset'],
                            'timestamp': item['timestamp']
                        }
                    )
                    deleted_count += 1
                    
                except Exception as e:
                    self.logger.error(f"❌ 削除エラー {item.get('timestamp')}: {e}")
                    failed_count += 1
            
            self.logger.info(f"✅ クリア完了: {deleted_count}件削除, {failed_count}件失敗")
            return failed_count == 0
            
        except Exception as e:
            error_msg = f"❌ テーブルクリアエラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            return False
    
    def trigger_convex_job(self):
        """convex_ec2_complete.pyのrun_complete_job()を実行"""
        try:
            # convex_ec2_complete.pyをインポート
            # convex_ec2_complete.pyは/home/ubuntu/convex-scraper/にある可能性がある
            convex_paths = [
                Path(__file__).parent.parent / 'convex_ec2_complete.py',  # 親ディレクトリ（data_acquisition_system）
                Path('/home/ubuntu/convex-scraper/convex_ec2_complete.py')  # EC2上のパス
            ]
            
            convex_file = None
            for path in convex_paths:
                if path.exists():
                    convex_file = path
                    break
            
            if not convex_file:
                self.logger.error("❌ convex_ec2_complete.pyが見つかりません")
                return False
            
            # パスを追加してインポート
            sys.path.insert(0, str(convex_file.parent))
            from convex_ec2_complete import ConvexEC2Complete
            
            self.logger.info("📊 ConvexEC2Completeインスタンスを作成中...")
            scraper = ConvexEC2Complete()
            
            # ロックを取得（重複実行防止）
            if not scraper.acquire_lock():
                self.logger.warning("⚠️ convex_ec2_complete.pyが既に実行中です。スキップします。")
                return False
            
            try:
                # run_complete_job()を実行
                self.logger.info("🚀 convex_ec2_complete.pyのrun_complete_job()を実行中...")
                success = scraper.run_complete_job()
                
                if success:
                    self.logger.info("✅ convex_ec2_complete.pyの実行が成功しました")
                    return True
                else:
                    self.logger.warning("⚠️ convex_ec2_complete.pyの実行が失敗しました")
                    return False
            finally:
                # ロックを解放
                scraper.release_lock()
                
        except ImportError as e:
            self.logger.error(f"❌ convex_ec2_complete.pyのインポートエラー: {e}")
            return False
        except Exception as e:
            error_msg = f"❌ convex_ec2_complete.pyの実行エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            return False
    
    def run_daily_aggregation(self):
        """日次OHLC集約を実行"""
        self.logger.info("🚀 日次USD/JPY OHLC集約開始")
        self.logger.info("=" * 50)
        
        try:
            # 昨日の日付を取得
            now_jst = datetime.now(self.JST)
            yesterday = now_jst - timedelta(days=1)
            
            self.logger.info(f"📅 集約対象日: {yesterday.strftime('%Y-%m-%d')}")
            
            # 1. 昨日のUSDJPYHistoryデータを取得
            items = self.get_yesterday_rate_data()
            
            # 2. データが1件もない場合
            if not items:
                self.logger.warning("⚠️ 昨日のデータが1件もありません。処理を終了します。")
                self.logger.info("📊 USDJPYHistoryテーブルはクリアされません。")
                return True
            
            # 3. OHLCデータを集約
            ohlc_data = self.aggregate_ohlc_data(items)
            
            if not ohlc_data:
                error_msg = "❌ OHLCデータ集約に失敗しました。処理を中止します。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="USD/JPY OHLC Aggregator"
                    )
                return False
            
            # 4. USDJPYOHLCDailyテーブルに保存
            if not self.save_ohlc_data(ohlc_data, yesterday):
                error_msg = "❌ OHLCデータ保存に失敗しました。処理を中止します。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="USD/JPY OHLC Aggregator"
                    )
                return False
            
            # 5. USDJPYHistoryテーブルをクリア
            if not self.clear_usdjpy_history_table():
                error_msg = "⚠️ USDJPYHistoryテーブルのクリアに失敗しましたが、OHLCデータは保存済みです。"
                self.logger.warning(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_warning(error_msg)
                # クリア失敗は致命的ではないので、処理は続行
            
            # 6. convex_ec2_complete.pyの定期実行をトリガー（USDJPYHistoryテーブルに今日の最初のデータを保存）
            self.logger.info("🔄 convex_ec2_complete.pyの定期実行をトリガー中...")
            if self.trigger_convex_job():
                self.logger.info("✅ convex_ec2_complete.pyの実行が完了しました")
            else:
                self.logger.warning("⚠️ convex_ec2_complete.pyの実行に失敗しましたが、OHLC集約は完了しています")
            
            # 7. 成功通知
            success_msg = f"✅ 日次USD/JPY OHLC集約完了: {yesterday.strftime('%Y-%m-%d')}"
            self.logger.info(success_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_success(success_msg)
            
            self.logger.info("=" * 50)
            self.logger.info("✅ 日次OHLC集約処理が正常に完了しました")
            
            return True
            
        except Exception as e:
            error_msg = f"❌ 日次OHLC集約処理エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="USD/JPY OHLC Aggregator",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    aggregator = USDJPYOHLCAggregator()
    success = aggregator.run_daily_aggregation()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

