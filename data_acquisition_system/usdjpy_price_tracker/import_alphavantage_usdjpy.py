#!/usr/bin/env python3
# =====================================
# Alpha Vantage USD/JPY OHLCデータインポートスクリプト
# Alpha Vantageから取得したJSONデータをUSDJPYOHLCDailyテーブルに保存
# =====================================

import boto3
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from botocore.exceptions import ClientError
from pathlib import Path
import sys

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class AlphaVantageUSDJPYImporter:
    def __init__(self):
        """Alpha Vantage USD/JPYインポーターの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.ohlc_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
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
        log_file = Path(__file__).parent / 'import_alphavantage_usdjpy.log'
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
            self.ohlc_table = self.dynamodb.Table('USDJPYOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ USDJPYOHLCDailyテーブルに接続しました")
        except ClientError as e:
            error_msg = f"❌ DynamoDBテーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Alpha Vantage USD/JPY Importer",
                    error=e
                )
            raise
    
    def load_json_data(self, json_file_path):
        """JSONファイルを読み込む"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"✅ JSONファイルを読み込みました: {json_file_path}")
            return data
        except Exception as e:
            error_msg = f"❌ JSONファイル読み込みエラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Alpha Vantage USD/JPY Importer",
                    error=e
                )
            raise
    
    def parse_alphavantage_data(self, data):
        """Alpha VantageのデータをパースしてUSDJPYOHLCDaily形式に変換"""
        if 'Time Series FX (Daily)' not in data:
            raise ValueError("JSONデータに'Time Series FX (Daily)'キーがありません")
        
        time_series = data['Time Series FX (Daily)']
        meta_data = data.get('Meta Data', {})
        
        parsed_data = []
        jst_created_at = datetime.now(self.JST).isoformat()
        
        for date_str, ohlc_values in time_series.items():
            try:
                # 日付の検証
                datetime.strptime(date_str, '%Y-%m-%d')
                
                # OHLCデータの取得
                open_price = Decimal(str(ohlc_values.get('1. open', '0')))
                high_price = Decimal(str(ohlc_values.get('2. high', '0')))
                low_price = Decimal(str(ohlc_values.get('3. low', '0')))
                close_price = Decimal(str(ohlc_values.get('4. close', '0')))
                
                # datetimeフィールド（JSTのISO形式）
                # 日付文字列をJSTのdatetimeに変換（時刻は00:00:00）
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                jst_datetime = date_obj.replace(tzinfo=self.JST).isoformat()
                
                item = {
                    'asset': 'USDJPY',
                    'timestamp': date_str,  # YYYY-MM-DD形式
                    'timezone': 'JST',
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'sample_count': 1,  # 1日1データポイント
                    'data_source': 'AlphaVantage',
                    'datetime': jst_datetime,
                    'created_at': jst_created_at
                }
                
                parsed_data.append(item)
                
            except Exception as e:
                self.logger.warning(f"⚠️ 日付 {date_str} のデータ処理エラー: {e}")
                continue
        
        # 日付順にソート（古い順）
        parsed_data.sort(key=lambda x: x['timestamp'])
        
        self.logger.info(f"✅ {len(parsed_data)}件のデータをパースしました")
        return parsed_data
    
    def save_to_dynamodb(self, parsed_data, batch_size=25):
        """パースしたデータをDynamoDBに保存（バッチ処理）"""
        if not parsed_data:
            self.logger.warning("⚠️ 保存するデータがありません")
            return False
        
        try:
            self.logger.info(f"💾 USDJPYOHLCDailyテーブルに保存中... ({len(parsed_data)}件)")
            
            saved_count = 0
            failed_count = 0
            
            # バッチ処理で保存
            for i in range(0, len(parsed_data), batch_size):
                batch = parsed_data[i:i+batch_size]
                
                try:
                    with self.ohlc_table.batch_writer() as batch_writer:
                        for item in batch:
                            try:
                                batch_writer.put_item(Item=item)
                                saved_count += 1
                            except Exception as e:
                                self.logger.error(f"❌ {item['timestamp']} 保存エラー: {e}")
                                failed_count += 1
                    
                    if (i + batch_size) % 100 == 0:
                        self.logger.info(f"📊 進捗: {i + batch_size}/{len(parsed_data)}件処理済み")
                        
                except Exception as e:
                    self.logger.error(f"❌ バッチ保存エラー: {e}")
                    failed_count += len(batch)
            
            self.logger.info(f"📊 データ保存完了: {saved_count}件成功, {failed_count}件失敗")
            
            if failed_count == 0:
                success_msg = f"✅ Alpha Vantage USD/JPYデータインポート完了: {saved_count}件保存"
                self.logger.info(success_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_success(success_msg)
                return True
            else:
                warning_msg = f"⚠️ 一部データの保存に失敗: {saved_count}件成功, {failed_count}件失敗"
                self.logger.warning(warning_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_warning(warning_msg)
                return saved_count > 0
            
        except Exception as e:
            error_msg = f"❌ DynamoDB保存エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Alpha Vantage USD/JPY Importer",
                    error=e
                )
            return False
    
    def import_from_json(self, json_file_path):
        """JSONファイルからデータをインポート"""
        try:
            # JSONファイルを読み込む
            data = self.load_json_data(json_file_path)
            
            # データをパース
            parsed_data = self.parse_alphavantage_data(data)
            
            # DynamoDBに保存
            success = self.save_to_dynamodb(parsed_data)
            
            if success:
                self.logger.info("✅ インポート処理が正常に完了しました")
            else:
                self.logger.error("❌ インポート処理中にエラーが発生しました")
            
            return success
            
        except Exception as e:
            error_msg = f"❌ インポート処理エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Alpha Vantage USD/JPY Importer",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Alpha Vantage USD/JPY OHLCデータをUSDJPYOHLCDailyテーブルにインポート')
    parser.add_argument('json_file', help='Alpha Vantage JSONファイルのパス')
    
    args = parser.parse_args()
    
    importer = AlphaVantageUSDJPYImporter()
    success = importer.import_from_json(args.json_file)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

