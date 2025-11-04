#!/usr/bin/env python3
"""
最終追跡システム
DeletionTrackingLogsテーブルを使用した完全な追跡システム
"""

import boto3
import json
import logging
from datetime import datetime, timezone, timedelta
import uuid
from boto3.dynamodb.conditions import Key, Attr
from functools import wraps
import os
import sys
from pathlib import Path
import traceback

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class FinalTrackingSystem:
    def __init__(self):
        """最終追跡システムの初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table('DeletionTrackingLogs')
            self.connection_status = True
            
            # ログ設定
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('final_tracking.log'),
                    logging.StreamHandler()
                ]
            )
            self.logger = logging.getLogger(__name__)
            
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
            
            print("✅ 最終追跡システム初期化完了")
        except Exception as e:
            error_msg = f"❌ 最終追跡システム初期化エラー: {e}"
            print(error_msg)
            self.connection_status = False
            # Slack通知（インスタンス作成前にエラーが発生した場合）
            try:
                if SLACK_AVAILABLE:
                    notifier = SlackNotifier()
                    notifier.notify_error(
                        message=error_msg,
                        system_name="Final Tracking System",
                        error=e
                    )
            except Exception:
                pass

    def log_deletion_operation(self, table_name, operation, function_name, caller_info, additional_data=None):
        """削除操作を専用テーブルに記録"""
        if not self.connection_status:
            return False

        try:
            # ログエントリを作成
            log_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            date = timestamp[:10]  # YYYY-MM-DD形式
            
            log_entry = {
                'log_id': log_id,
                'timestamp': timestamp,
                'table_name': table_name,
                'operation_type': operation,
                'function_name': function_name,
                'caller_info': json.dumps(caller_info, ensure_ascii=False),
                'additional_data': json.dumps(additional_data or {}, ensure_ascii=False),
                'created_at': timestamp,
                'date': date,
                'log_level': 'INFO',
                'source': 'cleanup_tool',
                'status': 'success'
            }
            
            # 専用テーブルに保存
            self.table.put_item(Item=log_entry)
            
            # ファイルログにも記録
            self.logger.info(f"削除操作記録: {json.dumps(log_entry, ensure_ascii=False)}")
            
            print(f"✅ 削除操作を記録: {table_name} - {operation}")
            return True
            
        except Exception as e:
            error_msg = f"❌ 削除操作記録エラー: {e}"
            print(error_msg)
            self.logger.error(f"削除操作記録エラー: {e}")
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Final Tracking System",
                    error=e
                )
            return False

    def track_deletion(self, table_name, operation="delete"):
        """削除追跡デコレータ"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 呼び出し元情報を取得
                caller_info = self._get_caller_info()
                
                # 削除操作を記録
                self.log_deletion_operation(
                    table_name=table_name,
                    operation=operation,
                    function_name=func.__name__,
                    caller_info=caller_info
                )
                
                # 元の関数を実行
                result = func(*args, **kwargs)
                
                return result
            return wrapper
        return decorator

    def _get_caller_info(self):
        """呼び出し元情報を取得"""
        try:
            frame = sys._getframe(3)  # 3つ上のフレーム
            filename = frame.f_code.co_filename
            line_number = frame.f_lineno
            function_name = frame.f_code.co_name
            
            return {
                'filename': os.path.basename(filename),
                'line_number': line_number,
                'function_name': function_name,
                'full_path': filename
            }
        except Exception as e:
            return {'error': str(e)}

    def query_logs_by_table(self, table_name, limit=100):
        """テーブル別にログをクエリ"""
        if not self.connection_status:
            return []

        try:
            response = self.table.query(
                IndexName='table-timestamp-index',
                KeyConditionExpression=Key('table_name').eq(table_name),
                ScanIndexForward=False,  # 新しい順
                Limit=limit
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            error_msg = f"❌ テーブル別ログクエリエラー: {e}"
            print(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Final Tracking System",
                    error=e
                )
            return []

    def query_logs_by_operation(self, operation_type, limit=100):
        """操作タイプ別にログをクエリ"""
        if not self.connection_status:
            return []

        try:
            response = self.table.query(
                IndexName='operation-timestamp-index',
                KeyConditionExpression=Key('operation_type').eq(operation_type),
                ScanIndexForward=False,  # 新しい順
                Limit=limit
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            error_msg = f"❌ 操作別ログクエリエラー: {e}"
            print(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Final Tracking System",
                    error=e
                )
            return []

    def analyze_comprehensive_logs(self, days=7):
        """包括的なログ分析"""
        print(f"🔍 過去{days}日間の包括的ログ分析")
        print("=" * 60)

        try:
            # 過去N日間のログを取得
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            response = self.table.scan(
                FilterExpression=Attr('timestamp').between(start_date.isoformat(), end_date.isoformat()),
                Limit=1000
            )
            
            logs = response.get('Items', [])
            
            if not logs:
                print("📊 追跡ログなし")
                return
            
            # 詳細分析
            table_counts = {}
            operation_counts = {}
            function_counts = {}
            hourly_counts = {}
            daily_counts = {}
            
            for log in logs:
                table = log.get('table_name', 'unknown')
                operation = log.get('operation_type', 'unknown')
                function = log.get('function_name', 'unknown')
                timestamp = log.get('timestamp', '')
                date = log.get('date', 'unknown')
                
                # カウント
                table_counts[table] = table_counts.get(table, 0) + 1
                operation_counts[operation] = operation_counts.get(operation, 0) + 1
                function_counts[function] = function_counts.get(function, 0) + 1
                daily_counts[date] = daily_counts.get(date, 0) + 1
                
                # 時間別カウント
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hour = dt.hour
                    hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
                except:
                    pass
            
            # 結果表示
            print(f"📊 総追跡ログ数: {len(logs)}件")
            
            print(f"\n📋 テーブル別操作回数:")
            for table, count in sorted(table_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {table}: {count}件")
            
            print(f"\n🔧 操作タイプ別回数:")
            for operation, count in sorted(operation_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {operation}: {count}件")
            
            print(f"\n⚙️ 関数別操作回数:")
            for function, count in sorted(function_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {function}: {count}件")
            
            print(f"\n📅 日別操作回数:")
            for date in sorted(daily_counts.keys()):
                print(f"   {date}: {daily_counts[date]}件")
            
            print(f"\n⏰ 時間別操作回数:")
            for hour in sorted(hourly_counts.keys()):
                print(f"   {hour:02d}時: {hourly_counts[hour]}件")
            
            # 最近の操作
            print(f"\n📋 最近の操作:")
            recent_logs = sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True)[:5]
            for i, log in enumerate(recent_logs, 1):
                timestamp = log.get('timestamp', 'N/A')
                table = log.get('table_name', 'N/A')
                operation = log.get('operation_type', 'N/A')
                function = log.get('function_name', 'N/A')
                print(f"   {i}. {timestamp} - {table} - {operation} - {function}")
                
        except Exception as e:
            error_msg = f"❌ 包括的ログ分析エラー: {e}"
            print(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="Final Tracking System",
                    error=e
                )

    def create_tracked_cleanup_tool(self):
        """追跡機能付きクリーンアップツールを作成"""
        print("\n🛠️ 追跡機能付きクリーンアップツール作成中...")
        
        tracked_tool_code = '''#!/usr/bin/env python3
"""
追跡機能付きクリーンアップツール
DeletionTrackingLogsテーブルを使用した完全追跡システム
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from final_tracking_system import FinalTrackingSystem
import boto3
from boto3.dynamodb.conditions import Key, Attr

class TrackedCleanupTool:
    def __init__(self):
        self.tracker = FinalTrackingSystem()
        self.dynamodb = boto3.resource('dynamodb')
        self.tables = {
            'CvxStakeMetrics': self.dynamodb.Table('CvxStakeMetrics'),
            'CvxCrvStakeMetrics': self.dynamodb.Table('CvxCrvStakeMetrics'),
            'ConvexPoolMetrics': self.dynamodb.Table('ConvexPoolMetrics'),
            'PriceHistory': self.dynamodb.Table('PriceHistory'),
            'PoolLatest': self.dynamodb.Table('PoolLatest')
        }
    
    def clean_cvx_stake_metrics(self, confirm=True):
        """CVXステーキングメトリクスのクリーンアップ（追跡付き）"""
        return self.tracker.track_deletion("CvxStakeMetrics", "cleanup")(self._clean_cvx_stake_metrics)(confirm)
    
    def clean_cvxcrv_stake_metrics(self, confirm=True):
        """cvxCRVステーキングメトリクスのクリーンアップ（追跡付き）"""
        return self.tracker.track_deletion("CvxCrvStakeMetrics", "cleanup")(self._clean_cvxcrv_stake_metrics)(confirm)
    
    def clean_convex_pool_metrics(self, confirm=True):
        """Convexプールメトリクスのクリーンアップ（追跡付き）"""
        return self.tracker.track_deletion("ConvexPoolMetrics", "cleanup")(self._clean_convex_pool_metrics)(confirm)
    
    def clean_price_history(self, confirm=True):
        """価格履歴のクリーンアップ（追跡付き）"""
        return self.tracker.track_deletion("PriceHistory", "cleanup")(self._clean_price_history)(confirm)
    
    def clean_pool_latest(self, confirm=True):
        """プール最新データのクリーンアップ（追跡付き）"""
        return self.tracker.track_deletion("PoolLatest", "cleanup")(self._clean_pool_latest)(confirm)
    
    def _clean_cvx_stake_metrics(self, confirm=True):
        """CVXステーキングメトリクスのクリーンアップ実装"""
        if confirm:
            print("🗑️ CVXステーキングメトリクスクリーンアップ")
        
        table = self.tables['CvxStakeMetrics']
        response = table.query(
            KeyConditionExpression=Key('token').eq('CVX'),
            ScanIndexForward=False
        )
        
        items = response['Items']
        if len(items) > 1:
            old_items = items[1:]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'token': item['token'],
                    'timestamp': item['timestamp']
                })
                deleted_count += 1
            
            if confirm:
                print(f"✅ CVXステーキングメトリクス: {deleted_count}件削除")
            return deleted_count
        return 0
    
    def _clean_cvxcrv_stake_metrics(self, confirm=True):
        """cvxCRVステーキングメトリクスのクリーンアップ実装"""
        if confirm:
            print("🗑️ cvxCRVステーキングメトリクスクリーンアップ")
        
        table = self.tables['CvxCrvStakeMetrics']
        response = table.query(
            KeyConditionExpression=Key('token').eq('cvxCRV'),
            ScanIndexForward=False
        )
        
        items = response['Items']
        if len(items) > 1:
            old_items = items[1:]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'token': item['token'],
                    'timestamp': item['timestamp']
                })
                deleted_count += 1
            
            if confirm:
                print(f"✅ cvxCRVステーキングメトリクス: {deleted_count}件削除")
            return deleted_count
        return 0
    
    def _clean_convex_pool_metrics(self, confirm=True):
        """Convexプールメトリクスのクリーンアップ実装"""
        if confirm:
            print("🗑️ Convexプールメトリクスクリーンアップ")
        
        table = self.tables['ConvexPoolMetrics']
        response = table.scan()
        
        items = response['Items']
        if len(items) > 1:
            # 最新のタイムスタンプを取得
            latest_timestamp = max(item['timestamp'] for item in items)
            old_items = [item for item in items if item['timestamp'] != latest_timestamp]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'pool_id': item['pool_id'],
                    'timestamp': item['timestamp']
                })
                deleted_count += 1
            
            if confirm:
                print(f"✅ Convexプールメトリクス: {deleted_count}件削除")
            return deleted_count
        return 0
    
    def _clean_price_history(self, confirm=True):
        """価格履歴のクリーンアップ実装"""
        if confirm:
            print("🗑️ 価格履歴クリーンアップ")
        
        table = self.tables['PriceHistory']
        response = table.scan()
        
        items = response['Items']
        if len(items) > 1:
            # 最新のタイムスタンプを取得
            latest_timestamp = max(item['timestamp'] for item in items)
            old_items = [item for item in items if item['timestamp'] != latest_timestamp]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'symbol': item['symbol'],
                    'timestamp': item['timestamp']
                })
                deleted_count += 1
            
            if confirm:
                print(f"✅ 価格履歴: {deleted_count}件削除")
            return deleted_count
        return 0
    
    def _clean_pool_latest(self, confirm=True):
        """プール最新データのクリーンアップ実装"""
        if confirm:
            print("🗑️ プール最新データクリーンアップ")
        
        table = self.tables['PoolLatest']
        response = table.scan()
        
        items = response['Items']
        if len(items) > 1:
            # 最新のタイムスタンプを取得
            latest_timestamp = max(item['updated_at'] for item in items)
            old_items = [item for item in items if item['updated_at'] != latest_timestamp]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'pool_id': item['pool_id']
                })
                deleted_count += 1
            
            if confirm:
                print(f"✅ プール最新データ: {deleted_count}件削除")
            return deleted_count
        return 0
    
    def analyze_deletion_history(self):
        """削除履歴を分析"""
        return self.tracker.analyze_comprehensive_logs()

# 実行用関数
def show_tracked_table_overview():
    """追跡機能付きテーブル概要表示"""
    tool = TrackedCleanupTool()
    return tool.get_table_overview()

def analyze_tracked_deletion_history():
    """追跡機能付き削除履歴分析"""
    tool = TrackedCleanupTool()
    return tool.analyze_deletion_history()

if __name__ == "__main__":
    print("🚀 追跡機能付きクリーンアップツール")
    print("=" * 60)
    print("1. テーブル概要表示")
    print("2. 削除履歴分析")
    print("3. 終了")
    
    choice = input("選択してください (1-3): ")
    
    if choice == "1":
        show_tracked_table_overview()
    elif choice == "2":
        analyze_tracked_deletion_history()
    elif choice == "3":
        print("終了します")
    else:
        print("無効な選択です")
'''
        
        with open('tracked_cleanup_tool_final.py', 'w', encoding='utf-8') as f:
            f.write(tracked_tool_code)
        
        print("✅ 追跡機能付きクリーンアップツールを作成しました")
        print("   ファイル: tracked_cleanup_tool_final.py")

def main():
    """メイン実行関数"""
    print("🚀 最終追跡システム")
    print("=" * 60)
    
    # 最終追跡システムを初期化
    tracking_system = FinalTrackingSystem()
    
    if not tracking_system.connection_status:
        print("❌ 最終追跡システムの初期化に失敗しました")
        return
    
    print("1. 包括的ログ分析")
    print("2. 追跡機能付きクリーンアップツール作成")
    print("3. 終了")
    
    choice = input("選択してください (1-3): ")
    
    if choice == "1":
        days = int(input("分析する日数を入力してください (デフォルト: 7): ") or "7")
        tracking_system.analyze_comprehensive_logs(days)
    elif choice == "2":
        tracking_system.create_tracked_cleanup_tool()
    elif choice == "3":
        print("終了します")
    else:
        print("無効な選択です")

if __name__ == "__main__":
    main()
