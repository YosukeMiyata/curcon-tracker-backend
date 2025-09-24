# =====================================
# Google Colab用 DeletionTrackingLogs データ確認・CSVダウンロードツール
# =====================================

import boto3
import pandas as pd
from datetime import datetime, timedelta
import json
from decimal import Decimal
import io

def convert_decimal_to_float(obj):
    """Decimal型をfloat型に変換する再帰関数"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_float(item) for item in obj]
    else:
        return obj

print("🔍 DeletionTrackingLogs データ確認・CSVダウンロードツール準備完了!")
print("🔧 必要なライブラリがインストールされました")

class DeletionTrackerViewer:
    def __init__(self):
        """DeletionTrackingLogsビューアーの初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table('DeletionTrackingLogs')
            self.connection_status = True
            print("✅ DeletionTrackingLogsテーブル接続成功")
        except Exception as e:
            self.connection_status = False
            print(f"❌ DeletionTrackingLogsテーブル接続エラー: {e}")

    def get_all_logs(self):
        """全削除ログを取得"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return []

        print("📊 全削除ログを取得中...")
        
        try:
            # 全データをスキャン
            response = self.table.scan()
            all_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                all_logs.extend(response['Items'])
            
            # Decimal型を変換
            all_logs = [convert_decimal_to_float(log) for log in all_logs]
            
            print(f"✅ {len(all_logs)}件のログを取得しました")
            return all_logs
            
        except Exception as e:
            print(f"❌ ログ取得エラー: {e}")
            return []

    def get_logs_by_date_range(self, days=7):
        """指定日数分のログを取得"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return []

        print(f"📅 過去{days}日間のログを取得中...")
        
        try:
            # 日付範囲を計算
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 日付文字列に変換
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # フィルター式を作成
            filter_expression = boto3.dynamodb.conditions.Attr('date').between(start_date_str, end_date_str)
            
            response = self.table.scan(FilterExpression=filter_expression)
            logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                logs.extend(response['Items'])
            
            # Decimal型を変換
            logs = [convert_decimal_to_float(log) for log in logs]
            
            print(f"✅ 過去{days}日間で{len(logs)}件のログを取得しました")
            return logs
            
        except Exception as e:
            print(f"❌ 日付範囲ログ取得エラー: {e}")
            return []

    def get_logs_by_table(self, table_name):
        """指定テーブルのログを取得"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return []

        print(f"📋 {table_name}のログを取得中...")
        
        try:
            # テーブル名でフィルター
            filter_expression = boto3.dynamodb.conditions.Attr('table_name').eq(table_name)
            
            response = self.table.scan(FilterExpression=filter_expression)
            logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                logs.extend(response['Items'])
            
            # Decimal型を変換
            logs = [convert_decimal_to_float(log) for log in logs]
            
            print(f"✅ {table_name}で{len(logs)}件のログを取得しました")
            return logs
            
        except Exception as e:
            print(f"❌ テーブル別ログ取得エラー: {e}")
            return []

    def analyze_logs(self, logs):
        """ログの分析"""
        if not logs:
            print("📊 分析対象のログがありません")
            return

        print("📊 ログ分析結果")
        print("=" * 60)
        
        # 基本統計
        print(f"📈 総ログ数: {len(logs):,}件")
        
        # テーブル別集計
        table_counts = {}
        operation_counts = {}
        function_counts = {}
        date_counts = {}
        
        for log in logs:
            table = log.get('table_name', 'Unknown')
            operation = log.get('operation_type', 'Unknown')
            function = log.get('function_name', 'Unknown')
            date = log.get('date', 'Unknown')
            
            table_counts[table] = table_counts.get(table, 0) + 1
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
            function_counts[function] = function_counts.get(function, 0) + 1
            date_counts[date] = date_counts.get(date, 0) + 1
        
        # テーブル別集計
        print("\n📋 テーブル別操作回数:")
        for table, count in sorted(table_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {table}: {count}件")
        
        # 操作タイプ別集計
        print("\n🔧 操作タイプ別回数:")
        for operation, count in sorted(operation_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {operation}: {count}件")
        
        # 関数別集計
        print("\n⚙️ 関数別操作回数:")
        for function, count in sorted(function_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {function}: {count}件")
        
        # 日別集計
        print("\n📅 日別操作回数:")
        for date, count in sorted(date_counts.items(), key=lambda x: x[0], reverse=True):
            print(f"   {date}: {count}件")
        
        # 最近の操作
        print("\n📋 最近の操作:")
        sorted_logs = sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True)
        for i, log in enumerate(sorted_logs[:10], 1):
            timestamp = log.get('timestamp', 'N/A')
            table = log.get('table_name', 'N/A')
            operation = log.get('operation_type', 'N/A')
            function = log.get('function_name', 'N/A')
            print(f"   {i}. {timestamp} - {table} - {operation} - {function}")

    def create_dataframe(self, logs):
        """ログをDataFrameに変換"""
        if not logs:
            print("📊 変換対象のログがありません")
            return pd.DataFrame()
        
        print("📊 ログをDataFrameに変換中...")
        
        # ログをDataFrameに変換
        df = pd.DataFrame(logs)
        
        # タイムスタンプをdatetime型に変換
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 日付でソート
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp', ascending=False)
        
        print(f"✅ {len(df)}件のログをDataFrameに変換しました")
        return df

    def display_logs_table(self, logs, limit=20):
        """ログをテーブル形式で表示"""
        if not logs:
            print("📊 表示対象のログがありません")
            return
        
        print(f"📋 削除ログ一覧（最新{min(limit, len(logs))}件）")
        print("=" * 100)
        
        # 最新のログを表示
        sorted_logs = sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True)
        display_logs = sorted_logs[:limit]
        
        for i, log in enumerate(display_logs, 1):
            timestamp = log.get('timestamp', 'N/A')
            table = log.get('table_name', 'N/A')
            operation = log.get('operation_type', 'N/A')
            function = log.get('function_name', 'N/A')
            caller = log.get('caller_info', 'N/A')
            date = log.get('date', 'N/A')
            
            print(f"{i:2d}. {timestamp}")
            print(f"    テーブル: {table}")
            print(f"    操作: {operation}")
            print(f"    関数: {function}")
            print(f"    呼び出し元: {caller}")
            print(f"    日付: {date}")
            print("-" * 80)

    def download_csv(self, logs, filename=None):
        """ログをCSVファイルとしてダウンロード"""
        if not logs:
            print("📊 ダウンロード対象のログがありません")
            return
        
        # ファイル名を生成
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"deletion_tracking_logs_{timestamp}.csv"
        
        print(f"📥 CSVファイルをダウンロード中: {filename}")
        
        try:
            # DataFrameに変換
            df = self.create_dataframe(logs)
            
            if df.empty:
                print("❌ データが空のためCSVダウンロードをスキップします")
                return
            
            # CSV文字列を生成
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8')
            csv_content = csv_buffer.getvalue()
            
            # ファイルをダウンロード
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            
            print(f"✅ CSVファイルがダウンロードされました: {filename}")
            print(f"📊 レコード数: {len(df)}件")
            print(f"📋 カラム数: {len(df.columns)}列")
            
            # カラム情報を表示
            print("\n📋 カラム情報:")
            for i, col in enumerate(df.columns, 1):
                print(f"   {i}. {col}")
            
            return filename
            
        except Exception as e:
            print(f"❌ CSVダウンロードエラー: {e}")
            return None

    def get_table_summary(self):
        """テーブル概要を取得"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return
        
        print("📊 DeletionTrackingLogsテーブル概要")
        print("=" * 60)
        
        try:
            # テーブル情報を取得
            response = self.table.scan(Select='COUNT')
            total_count = response['Count']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    Select='COUNT',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                total_count += response['Count']
            
            print(f"📈 総ログ数: {total_count:,}件")
            
            # 最新のログを取得
            response = self.table.scan(Limit=1)
            if response['Items']:
                latest_log = response['Items'][0]
                latest_timestamp = latest_log.get('timestamp', 'N/A')
                print(f"📅 最新ログ: {latest_timestamp}")
            
        except Exception as e:
            print(f"❌ テーブル概要取得エラー: {e}")

    def delete_old_logs(self, keep_days=30, confirm=True):
        """古いログを削除（指定日数分を保持）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False
        
        if confirm:
            print(f"🗑️ 古いログを削除（{keep_days}日分を保持）")
            print("⚠️ 指定日数より古いログが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input(f"本当に{keep_days}日より古いログを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ 古いログの削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ 古いログの削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")
        
        try:
            # 削除対象の日付を計算
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
            
            print(f"📅 削除対象: {cutoff_date_str}より古いログ")
            
            # 削除対象のログを取得
            filter_expression = boto3.dynamodb.conditions.Attr('date').lt(cutoff_date_str)
            response = self.table.scan(FilterExpression=filter_expression)
            old_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                old_logs.extend(response['Items'])
            
            if not old_logs:
                print("✅ 削除対象の古いログはありません")
                return True
            
            print(f"📊 削除対象: {len(old_logs):,}件")
            
            # バッチ削除
            deleted_count = 0
            for i in range(0, len(old_logs), 25):
                batch = old_logs[i:i+25]
                
                with self.table.batch_writer() as batch_writer:
                    for log in batch:
                        key = {
                            'log_id': log['log_id'],
                            'timestamp': log['timestamp']
                        }
                        batch_writer.delete_item(Key=key)
                        deleted_count += 1
                
                # 進捗表示
                if confirm and len(old_logs) > 100 and deleted_count % 100 == 0:
                    progress = (deleted_count / len(old_logs)) * 100
                    print(f"🔄 進捗: {deleted_count:,}/{len(old_logs):,} ({progress:.1f}%)")
                
                # レート制限対策
                import time
                time.sleep(0.1)
            
            if confirm:
                print(f"✅ 古いログ削除完了: {deleted_count:,}件削除")
            
            return True
            
        except Exception as e:
            if confirm:
                print(f"❌ 古いログ削除エラー: {e}")
            return False

    def delete_all_logs(self, confirm=True):
        """全ログを削除（⚠️危険⚠️）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False
        
        if confirm:
            print("🔥 全ログ削除機能")
            print("⚠️⚠️⚠️ 警告: 全てのログが削除されます ⚠️⚠️⚠️")
            print("=" * 60)
            
            # 確認プロンプト
            print("⚠️ この操作は取り消せません！")
            while True:
                user_input = input("本当に全ログを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ 全ログ削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ 全ログ削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")
        
        try:
            # 全ログを取得
            response = self.table.scan()
            all_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                all_logs.extend(response['Items'])
            
            if not all_logs:
                print("✅ 削除対象のログはありません")
                return True
            
            print(f"📊 削除対象: {len(all_logs):,}件")
            
            # バッチ削除
            deleted_count = 0
            for i in range(0, len(all_logs), 25):
                batch = all_logs[i:i+25]
                
                with self.table.batch_writer() as batch_writer:
                    for log in batch:
                        key = {
                            'log_id': log['log_id'],
                            'timestamp': log['timestamp']
                        }
                        batch_writer.delete_item(Key=key)
                        deleted_count += 1
                
                # 進捗表示
                if confirm and len(all_logs) > 100 and deleted_count % 100 == 0:
                    progress = (deleted_count / len(all_logs)) * 100
                    print(f"🔄 進捗: {deleted_count:,}/{len(all_logs):,} ({progress:.1f}%)")
                
                # レート制限対策
                import time
                time.sleep(0.1)
            
            if confirm:
                print(f"✅ 全ログ削除完了: {deleted_count:,}件削除")
            
            return True
            
        except Exception as e:
            if confirm:
                print(f"❌ 全ログ削除エラー: {e}")
            return False

    def preview_old_logs_deletion(self, keep_days=30):
        """古いログ削除のプレビュー"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return
        
        print(f"👁️ 古いログ削除プレビュー（{keep_days}日分を保持）")
        print("=" * 60)
        print("⚠️ 実際には削除されません - プレビューのみです")
        
        try:
            # 削除対象の日付を計算
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
            
            print(f"📅 保持対象: {cutoff_date_str}以降のログ")
            print(f"📅 削除対象: {cutoff_date_str}より古いログ")
            
            # 削除対象のログを取得
            filter_expression = boto3.dynamodb.conditions.Attr('date').lt(cutoff_date_str)
            response = self.table.scan(FilterExpression=filter_expression)
            old_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                old_logs.extend(response['Items'])
            
            # 保持対象のログを取得
            keep_filter = boto3.dynamodb.conditions.Attr('date').gte(cutoff_date_str)
            response = self.table.scan(FilterExpression=keep_filter)
            keep_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=keep_filter,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                keep_logs.extend(response['Items'])
            
            print(f"📊 総ログ数: {len(old_logs) + len(keep_logs):,}件")
            print(f"✅ 保持対象: {len(keep_logs):,}件")
            print(f"🗑️ 削除対象: {len(old_logs):,}件")
            
            if old_logs:
                print(f"\n🗑️ 削除予定の古いログ例:")
                sorted_old_logs = sorted(old_logs, key=lambda x: x.get('timestamp', ''), reverse=True)
                for i, log in enumerate(sorted_old_logs[:5], 1):
                    timestamp = log.get('timestamp', 'N/A')
                    table = log.get('table_name', 'N/A')
                    operation = log.get('operation_type', 'N/A')
                    date = log.get('date', 'N/A')
                    print(f"   {i}. {timestamp} - {table} - {operation} - {date}")
            
            return len(old_logs)
            
        except Exception as e:
            print(f"❌ プレビューエラー: {e}")
            return 0

    def delete_logs_by_condition(self, table_name=None, operation_type=None, days_old=None, confirm=True):
        """条件指定でログを削除"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False
        
        if confirm:
            print("🗑️ 条件指定ログ削除")
            print("=" * 60)
            
            conditions = []
            if table_name:
                conditions.append(f"テーブル: {table_name}")
            if operation_type:
                conditions.append(f"操作タイプ: {operation_type}")
            if days_old:
                conditions.append(f"古さ: {days_old}日以上")
            
            if conditions:
                print("📋 削除条件:")
                for condition in conditions:
                    print(f"   - {condition}")
            else:
                print("⚠️ 削除条件が指定されていません")
                return False
            
            # 確認プロンプト
            while True:
                user_input = input("指定条件のログを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ 条件指定ログ削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ 条件指定ログ削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")
        
        try:
            # フィルター条件を構築
            filter_conditions = []
            
            if table_name:
                filter_conditions.append(boto3.dynamodb.conditions.Attr('table_name').eq(table_name))
            
            if operation_type:
                filter_conditions.append(boto3.dynamodb.conditions.Attr('operation_type').eq(operation_type))
            
            if days_old:
                cutoff_date = datetime.now() - timedelta(days=days_old)
                cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
                filter_conditions.append(boto3.dynamodb.conditions.Attr('date').lt(cutoff_date_str))
            
            if not filter_conditions:
                print("❌ 削除条件が指定されていません")
                return False
            
            # フィルター式を結合
            if len(filter_conditions) == 1:
                filter_expression = filter_conditions[0]
            else:
                filter_expression = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    filter_expression = filter_expression & condition
            
            # 削除対象のログを取得
            response = self.table.scan(FilterExpression=filter_expression)
            target_logs = response['Items']
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=filter_expression,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                target_logs.extend(response['Items'])
            
            if not target_logs:
                print("✅ 削除対象のログはありません")
                return True
            
            print(f"📊 削除対象: {len(target_logs):,}件")
            
            # バッチ削除
            deleted_count = 0
            for i in range(0, len(target_logs), 25):
                batch = target_logs[i:i+25]
                
                with self.table.batch_writer() as batch_writer:
                    for log in batch:
                        key = {
                            'log_id': log['log_id'],
                            'timestamp': log['timestamp']
                        }
                        batch_writer.delete_item(Key=key)
                        deleted_count += 1
                
                # 進捗表示
                if confirm and len(target_logs) > 100 and deleted_count % 100 == 0:
                    progress = (deleted_count / len(target_logs)) * 100
                    print(f"🔄 進捗: {deleted_count:,}/{len(target_logs):,} ({progress:.1f}%)")
                
                # レート制限対策
                import time
                time.sleep(0.1)
            
            if confirm:
                print(f"✅ 条件指定ログ削除完了: {deleted_count:,}件削除")
            
            return True
            
        except Exception as e:
            if confirm:
                print(f"❌ 条件指定ログ削除エラー: {e}")
            return False

# 実行用関数
def show_table_summary():
    """テーブル概要表示"""
    viewer = DeletionTrackerViewer()
    return viewer.get_table_summary()

def get_all_logs():
    """全ログ取得"""
    viewer = DeletionTrackerViewer()
    return viewer.get_all_logs()

def get_recent_logs(days=7):
    """最近のログ取得"""
    viewer = DeletionTrackerViewer()
    return viewer.get_logs_by_date_range(days)

def get_table_logs(table_name):
    """指定テーブルのログ取得"""
    viewer = DeletionTrackerViewer()
    return viewer.get_logs_by_table(table_name)

def analyze_logs(logs):
    """ログ分析"""
    viewer = DeletionTrackerViewer()
    return viewer.analyze_logs(logs)

def display_logs(logs, limit=20):
    """ログ表示"""
    viewer = DeletionTrackerViewer()
    return viewer.display_logs_table(logs, limit)

def download_logs_csv(logs, filename=None):
    """ログCSVダウンロード"""
    viewer = DeletionTrackerViewer()
    return viewer.download_csv(logs, filename)

def create_logs_dataframe(logs):
    """ログDataFrame作成"""
    viewer = DeletionTrackerViewer()
    return viewer.create_dataframe(logs)

def delete_old_logs(keep_days=30):
    """古いログ削除"""
    viewer = DeletionTrackerViewer()
    return viewer.delete_old_logs(keep_days)

def delete_all_logs():
    """全ログ削除（⚠️危険⚠️）"""
    viewer = DeletionTrackerViewer()
    return viewer.delete_all_logs()

def preview_old_logs_deletion(keep_days=30):
    """古いログ削除プレビュー"""
    viewer = DeletionTrackerViewer()
    return viewer.preview_old_logs_deletion(keep_days)

def delete_logs_by_condition(table_name=None, operation_type=None, days_old=None):
    """条件指定でログ削除"""
    viewer = DeletionTrackerViewer()
    return viewer.delete_logs_by_condition(table_name, operation_type, days_old)

# セル4: 実行コマンド例
print("🚀 DeletionTrackingLogs データ確認・CSVダウンロードツール準備完了!")
print("\n📋 利用可能なコマンド:")
print("   - show_table_summary()                    # テーブル概要表示")
print("   - get_all_logs()                          # 全ログ取得")
print("   - get_recent_logs(days=7)                 # 最近7日間のログ取得")
print("   - get_table_logs('PoolLatest')            # 指定テーブルのログ取得")
print("   - analyze_logs(logs)                      # ログ分析")
print("   - display_logs(logs, limit=20)            # ログ表示")
print("   - download_logs_csv(logs, 'filename.csv') # ログCSVダウンロード")
print("   - create_logs_dataframe(logs)             # ログDataFrame作成")
print("   - preview_old_logs_deletion(keep_days=30) # 古いログ削除プレビュー")
print("   - delete_old_logs(keep_days=30)           # 古いログ削除（30日分保持）")
print("   - delete_logs_by_condition(table_name='PoolLatest') # 条件指定ログ削除")
print("   - delete_all_logs()                       # 全ログ削除（⚠️危険⚠️）")
print("\n💡 推奨使用順序:")
print("   1. show_table_summary()                   # テーブル概要確認")
print("   2. logs = get_all_logs()                  # 全ログ取得")
print("   3. analyze_logs(logs)                     # ログ分析")
print("   4. display_logs(logs)                      # ログ表示")
print("   5. download_logs_csv(logs)                 # CSVダウンロード")
print("\n🗑️ ログ削除機能:")
print("   1. preview_old_logs_deletion(30)          # 古いログ削除プレビュー")
print("   2. delete_old_logs(30)                    # 古いログ削除実行")
print("   3. delete_logs_by_condition(table_name='PoolLatest') # 条件指定削除")
print("   4. delete_all_logs()                       # 全ログ削除（⚠️危険⚠️）")
print("\n🔧 機能:")
print("   - 全削除ログの取得・表示")
print("   - 日付範囲・テーブル別フィルタリング")
print("   - 詳細なログ分析")
print("   - CSVファイルダウンロード")
print("   - DataFrame変換")
print("   - ページネーション対応")
print("   - 古いログの削除（指定日数分保持）")
print("   - 条件指定ログ削除（テーブル・操作タイプ・日付）")
print("   - 全ログ削除（⚠️危険⚠️）")
print("   - 削除実行前にy/N確認プロンプト")
