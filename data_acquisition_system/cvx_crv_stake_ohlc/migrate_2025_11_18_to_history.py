#!/usr/bin/env python3
# =====================================
# 2025年11月18日のCvxCrvStakeMetricsデータをCvxCrvStakeHistoryに移行
# =====================================

import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
from pathlib import Path
import traceback

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class Migrate20251118:
    def __init__(self):
        """初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.JST = timezone(timedelta(hours=9))
        self.target_date = datetime(2025, 11, 18, tzinfo=self.JST)
        self.start_datetime = self.target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.end_datetime = self.target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        if SLACK_AVAILABLE:
            try:
                self.slack_notifier = SlackNotifier()
            except Exception:
                self.slack_notifier = None
        else:
            self.slack_notifier = None
        
        self.metrics_table = None
        self.history_table = None
        self.setup_tables()
    
    def setup_tables(self):
        """テーブルに接続"""
        try:
            self.metrics_table = self.dynamodb.Table('CvxCrvStakeMetrics')
            self.metrics_table.load()
            print("✅ CvxCrvStakeMetricsテーブルに接続しました")
            
            self.history_table = self.dynamodb.Table('CvxCrvStakeHistory')
            self.history_table.load()
            print("✅ CvxCrvStakeHistoryテーブルに接続しました")
        except Exception as e:
            print(f"❌ テーブル接続エラー: {e}")
            raise e
    
    def migrate(self):
        """移行処理"""
        print(f"🚀 2025年11月18日のデータ移行開始")
        print(f"   対象期間: {self.start_datetime.strftime('%Y-%m-%d %H:%M:%S')} - {self.end_datetime.strftime('%Y-%m-%d %H:%M:%S')} JST")
        
        try:
            # CvxCrvStakeMetricsからデータ取得
            all_items = []
            last_evaluated_key = None
            
            while True:
                query_params = {
                    'KeyConditionExpression': Key('stake').eq('cvxCRV'),
                    'ScanIndexForward': False
                }
                
                if last_evaluated_key:
                    query_params['ExclusiveStartKey'] = last_evaluated_key
                
                response = self.metrics_table.query(**query_params)
                items = response.get('Items', [])
                
                # 2025年11月18日のデータのみ抽出
                filtered_items = []
                for item in items:
                    timestamp_str = item.get('timestamp', '')
                    if not timestamp_str:
                        continue
                    
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                        timestamp_jst = timestamp.astimezone(self.JST)
                        
                        if self.start_datetime <= timestamp_jst <= self.end_datetime:
                            filtered_items.append(item)
                        elif timestamp_jst < self.start_datetime:
                            # 過去のデータに到達したら終了
                            break
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                        continue
                
                all_items.extend(filtered_items)
                
                # 過去のデータに到達したら終了
                if filtered_items and len(filtered_items) < len(items):
                    # 最新のアイテムが対象範囲外の場合
                    if items:
                        latest_item = items[0]
                        latest_timestamp_str = latest_item.get('timestamp', '')
                        if latest_timestamp_str:
                            try:
                                latest_timestamp = datetime.fromisoformat(latest_timestamp_str.replace('Z', '+00:00'))
                                if latest_timestamp.tzinfo is None:
                                    latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)
                                latest_timestamp_jst = latest_timestamp.astimezone(self.JST)
                                if latest_timestamp_jst < self.start_datetime:
                                    break
                            except (ValueError, TypeError):
                                pass
                
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
            
            print(f"✅ {len(all_items)}件のデータを取得しました")
            
            if not all_items:
                print("⚠️ 移行するデータがありません")
                return False
            
            # CvxCrvStakeHistoryに保存
            saved_count = 0
            for item in all_items:
                try:
                    # datetimeフィールドを追加（timestampと同じ値）
                    history_item = item.copy()
                    if 'datetime' not in history_item:
                        history_item['datetime'] = history_item['timestamp']
                    
                    self.history_table.put_item(Item=history_item)
                    saved_count += 1
                except Exception as e:
                    print(f"❌ 保存エラー ({item.get('timestamp', 'N/A')}): {e}")
            
            print(f"✅ {saved_count}件のデータをCvxCrvStakeHistoryに保存しました")
            return True
            
        except Exception as e:
            error_msg = f"❌ 移行エラー: {e}"
            print(error_msg)
            print(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="2025-11-18 Migration",
                    error=e
                )
            return False

def main():
    """メイン処理"""
    migrator = Migrate20251118()
    success = migrator.migrate()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

