#!/usr/bin/env python3
# =====================================
# ConvexPoolMetricsから2025年11月20日のデータをConvexPoolHistoryに移行するスクリプト
# =====================================

import boto3
from boto3.dynamodb.conditions import Key, Attr
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

class ConvexPoolMetricsToHistoryMigrator:
    def __init__(self):
        """ConvexPoolMetricsからConvexPoolHistoryへの移行システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.metrics_table = None
        self.history_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # 対象日（2025年11月20日）
        self.target_date = datetime(2025, 11, 20, 0, 0, 0, tzinfo=self.JST)
        self.target_date_end = datetime(2025, 11, 20, 23, 59, 59, tzinfo=self.JST)
        
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
        log_file = Path(__file__).parent / 'migrate_2025_11_20_to_history.log'
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
            self.metrics_table = self.dynamodb.Table('ConvexPoolMetrics')
            self.metrics_table.load()
            self.logger.info("✅ ConvexPoolMetricsテーブルに接続しました")
            
            self.history_table = self.dynamodb.Table('ConvexPoolHistory')
            self.history_table.load()
            self.logger.info("✅ ConvexPoolHistoryテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPoolMetrics to History Migrator",
                    error=e
                )
            raise e
    
    def get_metrics_data_for_date(self):
        """ConvexPoolMetricsテーブルから2025年11月20日のデータを取得"""
        try:
            self.logger.info("📊 ConvexPoolMetricsテーブルからデータ取得中...")
            self.logger.info(f"   対象日: {self.target_date.strftime('%Y-%m-%d')} JST")
            
            all_items = []
            last_evaluated_key = None
            
            while True:
                scan_params = {}
                
                if last_evaluated_key:
                    scan_params['ExclusiveStartKey'] = last_evaluated_key
                
                response = self.metrics_table.scan(**scan_params)
                items = response.get('Items', [])
                
                # 2025年11月20日のデータのみ取得
                filtered_items = []
                for item in items:
                    timestamp_str = item.get('timestamp', '')
                    if not timestamp_str:
                        continue
                    
                    try:
                        # ISO形式のタイムスタンプをパース
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        
                        # JSTに変換
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                        timestamp_jst = timestamp.astimezone(self.JST)
                        
                        # 2025年11月20日のデータのみ
                        if self.target_date <= timestamp_jst <= self.target_date_end:
                            filtered_items.append(item)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                        continue
                
                all_items.extend(filtered_items)
                
                # ページネーション
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
                
                if len(all_items) % 1000 == 0:
                    self.logger.info(f"   📊 取得中... {len(all_items)}件")
            
            self.logger.info(f"✅ {len(all_items)}件のデータを取得しました")
            return all_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPoolMetrics to History Migrator",
                    error=e
                )
            return []
    
    def convert_to_decimal(self, value):
        """値をDecimal型に変換"""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            # パーセント記号やドル記号を除去
            cleaned = value.replace('%', '').replace('$', '').replace(',', '').replace('M', '000000').replace('B', '000000000').replace('x', '').strip()
            try:
                return Decimal(cleaned)
            except:
                return None
        return None
    
    def save_to_history(self, items):
        """ConvexPoolHistoryテーブルに保存"""
        try:
            self.logger.info("💾 ConvexPoolHistoryテーブルにデータ保存中...")
            
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            skipped_count = 0
            failed_count = 0
            
            for item in items:
                pool_id = item.get('pool_id', '')
                timestamp_str = item.get('timestamp', '')
                
                if not pool_id or not timestamp_str:
                    continue
                
                try:
                    # 既存データチェック
                    response = self.history_table.get_item(
                        Key={
                            'pool_id': pool_id,
                            'timestamp': timestamp_str
                        }
                    )
                    if 'Item' in response:
                        skipped_count += 1
                        continue
                    
                    # ISO形式のタイムスタンプをパースしてJSTに変換
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    timestamp_jst = timestamp.astimezone(self.JST)
                    jst_datetime = timestamp_jst.isoformat()
                    
                    # veCRV_boost_numericを計算
                    vecrv_boost_numeric = None
                    vecrv_boost = item.get('veCRV_boost', '')
                    if vecrv_boost:
                        try:
                            vecrv_boost_numeric = float(str(vecrv_boost).replace('x', '').strip())
                        except:
                            pass
                    
                    history_item = {
                        'pool_id': pool_id,
                        'timestamp': timestamp_str,
                        'timezone': 'JST',
                        'Pool': item.get('Pool', ''),
                        'factory_id': item.get('factory_id', ''),
                        'Current_vAPR': item.get('Current_vAPR', ''),
                        'Projected_vAPR': item.get('Projected_vAPR', ''),
                        'TVL': item.get('TVL', ''),
                        'veCRV_boost': vecrv_boost,
                        'Remarks': item.get('Remarks', ''),
                        'current_vapr_numeric': self.convert_to_decimal(item.get('current_vapr_numeric')),
                        'projected_vapr_numeric': self.convert_to_decimal(item.get('projected_vapr_numeric')),
                        'tvl_numeric': self.convert_to_decimal(item.get('tvl_numeric')),
                        'veCRV_boost_numeric': Decimal(str(vecrv_boost_numeric)) if vecrv_boost_numeric is not None else None,
                        'data_source': item.get('data_source', 'convex_ec2_complete'),
                        'datetime': jst_datetime,
                        'created_at': jst_created_at
                    }
                    
                    # None値を除去
                    history_item = {k: v for k, v in history_item.items() if v is not None and v != ''}
                    
                    self.history_table.put_item(Item=history_item)
                    saved_count += 1
                    
                    if saved_count % 100 == 0:
                        self.logger.info(f"📊 保存進捗: {saved_count}件保存完了")
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"❌ 保存エラー (pool_id: {pool_id}, timestamp: {timestamp_str}): {e}")
                    self.logger.error(traceback.format_exc())
            
            self.logger.info(
                f"📊 保存結果: "
                f"保存={saved_count}件, スキップ={skipped_count}件, 失敗={failed_count}件"
            )
            
            if failed_count > 0:
                error_msg = f"❌ データの保存で{failed_count}件失敗しました"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="ConvexPoolMetrics to History Migrator"
                    )
                return False
            
            return True
            
        except Exception as e:
            error_msg = f"❌ データ保存エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPoolMetrics to History Migrator",
                    error=e
                )
            return False
    
    def run_migration(self):
        """移行処理を実行"""
        self.logger.info("🚀 ConvexPoolMetricsからConvexPoolHistoryへの移行開始")
        self.logger.info("=" * 60)
        
        try:
            # 1. ConvexPoolMetricsから2025年11月20日のデータを取得
            items = self.get_metrics_data_for_date()
            
            if not items:
                self.logger.warning("⚠️ 取得したデータが1件もありません。処理を終了します。")
                return False
            
            # 2. ConvexPoolHistoryテーブルに保存
            if not self.save_to_history(items):
                error_msg = "❌ データ保存に失敗しました。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="ConvexPoolMetrics to History Migrator"
                    )
                return False
            
            self.logger.info("=" * 60)
            self.logger.info("✅ 移行処理が正常に完了しました")
            
            if self.slack_notifier:
                self.slack_notifier.notify_success(
                    message="ConvexPoolMetricsからConvexPoolHistoryへの移行が完了しました",
                    system_name="ConvexPoolMetrics to History Migrator"
                )
            
            return True
            
        except Exception as e:
            error_msg = f"❌ 移行処理エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPoolMetrics to History Migrator",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    migrator = ConvexPoolMetricsToHistoryMigrator()
    success = migrator.run_migration()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

