#!/usr/bin/env python3
# =====================================
# PriceHistoryテーブルからUSDJPYHistoryテーブルへの移行スクリプト
# 2025年11月13日のUSDJPYデータを移行
# =====================================

import boto3
import logging
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
from decimal import Decimal
from pathlib import Path
import sys

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class PriceHistoryToUSDJPYHistoryMigrator:
    def __init__(self):
        """移行システムの初期化"""
        # AWS認証情報を環境変数から取得（EC2のIAMロールも使用可能）
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.price_history_table = None
        self.usdjpy_history_table = None
        
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
        log_file = Path(__file__).parent / 'migrate_pricehistory_to_usdjpyhistory.log'
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
            
            self.usdjpy_history_table = self.dynamodb.Table('USDJPYHistory')
            self.usdjpy_history_table.load()
            self.logger.info("✅ USDJPYHistoryテーブルに接続しました")
        except ClientError as e:
            error_msg = f"❌ DynamoDBテーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to USDJPYHistory Migrator",
                    error=e
                )
            raise
    
    def get_pricehistory_data_for_date(self, target_date):
        """指定日のPriceHistoryテーブルからUSDJPYデータを取得"""
        try:
            self.logger.info(f"📊 {target_date.strftime('%Y-%m-%d')}のPriceHistoryデータを取得中...")
            
            # 日付範囲を計算（JST）
            date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)
            
            date_start_iso = date_start.isoformat()
            date_end_iso = date_end.isoformat()
            
            self.logger.info(f"   取得範囲: {date_start_iso} ～ {date_end_iso}")
            
            # 全データをスキャン
            all_items = []
            response = self.price_history_table.scan(
                FilterExpression='asset = :asset',
                ExpressionAttributeValues={':asset': 'USDJPY'}
            )
            all_items.extend(response.get('Items', []))
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.price_history_table.scan(
                    FilterExpression='asset = :asset',
                    ExpressionAttributeValues={':asset': 'USDJPY'},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_items.extend(response.get('Items', []))
            
            # 指定日のデータをフィルタリング
            filtered_items = []
            for item in all_items:
                timestamp = item.get('timestamp', '')
                if timestamp >= date_start_iso and timestamp < date_end_iso:
                    filtered_items.append(item)
            
            self.logger.info(f"✅ {len(filtered_items)}件のデータを取得しました")
            return filtered_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to USDJPYHistory Migrator",
                    error=e
                )
            return []
    
    def migrate_data(self, items):
        """PriceHistoryのデータをUSDJPYHistoryテーブルに移行"""
        if not items:
            self.logger.warning("⚠️ 移行するデータがありません")
            return False
        
        try:
            self.logger.info(f"💾 USDJPYHistoryテーブルに保存中... ({len(items)}件)")
            
            saved_count = 0
            failed_count = 0
            
            for item in items:
                try:
                    # USDJPYHistoryテーブルの形式に変換
                    new_item = {
                        'asset': item.get('asset', 'USDJPY'),
                        'timestamp': item.get('timestamp'),
                        'timezone': item.get('timezone', 'JST'),
                        'rate': item.get('rate'),  # Decimal型のまま
                        'source': item.get('source', 'PriceHistory'),
                        'datetime': item.get('timestamp'),  # timestampと同じ値
                        'created_at': item.get('created_at', datetime.now(self.JST).isoformat())
                    }
                    
                    self.usdjpy_history_table.put_item(Item=new_item)
                    saved_count += 1
                    
                except Exception as e:
                    self.logger.error(f"❌ {item.get('timestamp')} 保存エラー: {e}")
                    failed_count += 1
            
            self.logger.info(f"📊 データ移行完了: {saved_count}件成功, {failed_count}件失敗")
            
            if failed_count == 0:
                success_msg = f"✅ PriceHistoryからUSDJPYHistoryへの移行完了: {saved_count}件移行"
                self.logger.info(success_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_success(success_msg)
                return True
            else:
                warning_msg = f"⚠️ 一部データの移行に失敗: {saved_count}件成功, {failed_count}件失敗"
                self.logger.warning(warning_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_warning(warning_msg)
                return saved_count > 0
            
        except Exception as e:
            error_msg = f"❌ データ移行エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to USDJPYHistory Migrator",
                    error=e
                )
            return False
    
    def migrate_date(self, target_date_str):
        """指定日のデータを移行"""
        try:
            # 日付文字列をパース
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
            target_date = target_date.replace(tzinfo=self.JST)
            
            self.logger.info(f"🚀 移行処理開始: {target_date_str}")
            
            # データを取得
            items = self.get_pricehistory_data_for_date(target_date)
            
            if not items:
                self.logger.warning(f"⚠️ {target_date_str}のデータが見つかりませんでした")
                return False
            
            # データを移行
            success = self.migrate_data(items)
            
            if success:
                self.logger.info(f"✅ {target_date_str}の移行処理が正常に完了しました")
            else:
                self.logger.error(f"❌ {target_date_str}の移行処理中にエラーが発生しました")
            
            return success
            
        except Exception as e:
            error_msg = f"❌ 移行処理エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="PriceHistory to USDJPYHistory Migrator",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PriceHistoryテーブルからUSDJPYHistoryテーブルへの移行')
    parser.add_argument('date', help='移行対象日（YYYY-MM-DD形式）', default='2025-11-13', nargs='?')
    
    args = parser.parse_args()
    
    migrator = PriceHistoryToUSDJPYHistoryMigrator()
    success = migrator.migrate_date(args.date)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

