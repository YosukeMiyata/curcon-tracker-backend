# =====================================
# DynamoDB Google Colab用クリーンアップツール（修正版）
# 最新データ保持 + 全データ削除機能
# PriceHistory・PoolLatestテーブル対応
# data_acquisition_system/convex_ec2_complete.py統一版
# =====================================

import boto3
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal
import time
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
import sys
import os
import json
import uuid
from functools import wraps
warnings.filterwarnings('ignore')

# 日本語フォント設定
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.style.use('default')

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

# 削除追跡システムクラス（統合版）
class DeletionTrackingSystem:
    def __init__(self):
        """削除追跡システムの初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table('DeletionTrackingLogs')
            self.connection_status = True
            print("✅ 削除追跡システム初期化完了")
        except Exception as e:
            print(f"❌ 削除追跡システム初期化エラー: {e}")
            self.connection_status = False

    def log_deletion_operation(self, table_name, operation, function_name, caller_info, additional_data=None):
        """削除操作を専用テーブルに記録"""
        if not self.connection_status:
            return False

        try:
            # ログエントリを作成
            log_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
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
                'source': 'google_colab_cleanup_tool',
                'status': 'success'
            }
            
            # 専用テーブルに保存
            self.table.put_item(Item=log_entry)
            
            print(f"✅ 削除操作を記録: {table_name} - {operation}")
            return True
            
        except Exception as e:
            print(f"❌ 削除操作記録エラー: {e}")
            return False

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

print("🗑️ DynamoDB Google Colab用クリーンアップツール準備完了!")
print("🔧 必要なライブラリがインストールされました")
print("📊 DeletionTrackingLogsテーブルへの追跡機能を統合しました")

# セル2: クリーンアップツールクラス（修正版）
class DynamoDBCleanupTool:
    def __init__(self):
        """DynamoDBクリーンアップツールの初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.connection_status = True
            # 削除追跡システムを初期化
            self.tracker = DeletionTrackingSystem()
            print("✅ DynamoDB接続成功")
        except Exception as e:
            self.connection_status = False
            print(f"❌ DynamoDB接続エラー: {e}")

    def get_table_overview(self):
        """全テーブルの概要を表示"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return

        print("📊 DynamoDBテーブル概要")
        print("=" * 60)

        tables = [
            'CvxStakeMetrics',
            'CvxCrvStakeMetrics',
            'ConvexPoolMetrics',
            'PriceHistory',
            'TokenPriceHistory',
            'TokenOHLCDaily',
            'USDJPYHistory',
            'USDJPYOHLCDaily',
            'PoolLatest',
            'PoolMeta',
            'VaultMeta',
            'CvxStakeHistory',
            'CvxStakeOHLCDaily'
        ]

        total_items = 0
        overview_data = []

        for table_name in tables:
            try:
                table = self.dynamodb.Table(table_name)

                # 件数取得
                response = table.scan(Select='COUNT')
                count = response['Count']

                # ページネーション対応で正確な件数を取得
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        Select='COUNT',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    count += response['Count']

                # 最新データ取得
                if table_name in ['PriceHistory', 'TokenPriceHistory', 'TokenOHLCDaily', 'USDJPYHistory', 'USDJPYOHLCDaily', 'CvxStakeOHLCDaily']:
                    # 全データをスキャンして最新タイムスタンプを取得
                    response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
                    timestamps = [item['timestamp'] for item in response['Items']]

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(
                            ProjectionExpression='#ts',
                            ExpressionAttributeNames={'#ts': 'timestamp'},
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        timestamps.extend([item['timestamp'] for item in response['Items']])

                    latest_info = f"最新: {max(timestamps)}" if timestamps else "データなし"

                elif table_name == 'PoolLatest':
                    sample_response = table.scan(Limit=3)
                    sample_items = sample_response['Items']
                    if sample_items:
                        # 最新のupdated_atを持つデータを特定
                        items_with_time = []
                        for item in sample_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append(updated_at)

                        if items_with_time:
                            latest_time = max(items_with_time)
                            latest_info = f"最新更新: {latest_time}"
                        else:
                            latest_info = f"データ: {len(sample_items)}件"
                    else:
                        latest_info = "データなし"

                elif table_name in ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'CvxStakeHistory']:
                    # 特定のパーティションキーで最新データを取得
                    if table_name == 'CvxStakeMetrics':
                        partition_key = 'token'
                        partition_value = 'CVX'
                    elif table_name == 'CvxStakeHistory':
                        partition_key = 'token'
                        partition_value = 'CVX'
                    else:  # CvxCrvStakeMetrics
                        partition_key = 'stake'
                        partition_value = 'cvxCRV'

                    # ソートキーで降順ソートして最新データを取得
                    response = table.query(
                        KeyConditionExpression=Key(partition_key).eq(partition_value),
                        ScanIndexForward=False,  # 降順ソート
                        Limit=1
                    )

                    if response['Items']:
                        latest_timestamp = response['Items'][0]['timestamp']
                        latest_info = f"最新: {latest_timestamp}"
                    else:
                        latest_info = "データなし"

                elif table_name == 'ConvexPoolMetrics':
                    # 全データをスキャンして最新タイムスタンプを取得
                    response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
                    timestamps = [item['timestamp'] for item in response['Items']]

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(
                            ProjectionExpression='#ts',
                            ExpressionAttributeNames={'#ts': 'timestamp'},
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        timestamps.extend([item['timestamp'] for item in response['Items']])

                    latest_info = f"最新: {max(timestamps)}" if timestamps else "データなし"

                elif table_name in ['PoolMeta', 'VaultMeta']:
                    # メタデータテーブルは通常最新のupdated_atまたはtimestampで判定
                    sample_response = table.scan(Limit=5)
                    sample_items = sample_response['Items']
                    if sample_items:
                        # 最新のupdated_atまたはtimestampを持つデータを特定
                        items_with_time = []
                        for item in sample_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append(updated_at)

                        if items_with_time:
                            latest_time = max(items_with_time)
                            latest_info = f"最新更新: {latest_time}"
                        else:
                            latest_info = f"データ: {len(sample_items)}件"
                    else:
                        latest_info = "データなし"

                overview_data.append({
                    'テーブル名': table_name,
                    '件数': f"{count:,}件",
                    '状況': latest_info
                })

                total_items += count

                print(f"📈 {table_name}")
                print(f"   件数: {count:,}件")
                print(f"   状況: {latest_info}")
                print()

            except Exception as e:
                print(f"❌ {table_name}: エラー ({e})")
                overview_data.append({
                    'テーブル名': table_name,
                    '件数': 'エラー',
                    '状況': 'エラー'
                })

        # サマリーをDataFrameで表示
        if overview_data:
            overview_df = pd.DataFrame(overview_data)
            print("📊 テーブルサマリー:")
            display(overview_df)

        print(f"\n📊 全テーブル総計: {total_items:,}件")
        return total_items

    def preview_cleanup_latest(self):
        """最新データ保持クリーンアップのプレビュー"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return

        print("👁️ 最新データ保持クリーンアップ プレビュー")
        print("=" * 60)
        print("⚠️ 実際には削除されません - プレビューのみです")

        tables_to_clean = [
            {
                'name': 'CvxStakeMetrics',
                'partition_key': 'token',
                'partition_value': 'CVX',
                'sort_key': 'timestamp'
            },
            {
                'name': 'CvxCrvStakeMetrics',
                'partition_key': 'stake',
                'partition_value': 'cvxCRV',
                'sort_key': 'timestamp'
            },
            {
                'name': 'ConvexPoolMetrics',
                'partition_key': 'pool_id',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'PriceHistory',
                'partition_key': 'asset',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'TokenPriceHistory',
                'partition_key': 'token',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'TokenOHLCDaily',
                'partition_key': 'token',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'PoolLatest',
                'partition_key': 'pool_id',
                'partition_value': None,
                'sort_key': None
            },
            {
                'name': 'CvxStakeHistory',
                'partition_key': 'token',
                'partition_value': 'CVX',
                'sort_key': 'timestamp'
            },
            {
                'name': 'CvxStakeOHLCDaily',
                'partition_key': 'type',
                'partition_value': None,
                'sort_key': 'timestamp'
            }
        ]

        total_to_delete = 0

        for table_config in tables_to_clean:
            table_name = table_config['name']
            print(f"\n📊 {table_name} クリーンアップ予定:")

            try:
                table = self.dynamodb.Table(table_name)

                if table_name == 'ConvexPoolMetrics':
                    # 全データをスキャンして最新タイムスタンプを取得
                    response = table.scan(
                        ProjectionExpression='#ts',
                        ExpressionAttributeNames={'#ts': 'timestamp'}
                    )
                    timestamps = [item['timestamp'] for item in response['Items']]

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(
                            ProjectionExpression='#ts',
                            ExpressionAttributeNames={'#ts': 'timestamp'},
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        timestamps.extend([item['timestamp'] for item in response['Items']])

                    if timestamps:
                        unique_timestamps = list(set(timestamps))
                        unique_timestamps.sort(reverse=True)

                        latest_timestamp = unique_timestamps[0]
                        latest_count = timestamps.count(latest_timestamp)
                        old_count = len(timestamps) - latest_count

                        print(f"   総件数: {len(timestamps):,}件")
                        print(f"   最新データ: {latest_timestamp} ({latest_count:,}件)")
                        print(f"   保持対象: {latest_count:,}件")
                        print(f"   削除対象: {old_count:,}件")

                        if len(unique_timestamps) > 1:
                            print(f"   削除予定の古いタイムスタンプ例:")
                            for i, ts in enumerate(unique_timestamps[1:4], 1):
                                count = timestamps.count(ts)
                                print(f"     {i}. {ts} ({count:,}件)")

                        total_to_delete += old_count
                    else:
                        print(f"   データなし")

                elif table_name in ['PriceHistory', 'TokenPriceHistory', 'TokenOHLCDaily', 'USDJPYHistory', 'USDJPYOHLCDaily']:
                    # 全データをスキャンして最新タイムスタンプを取得
                    response = table.scan(
                        ProjectionExpression='#ts',
                        ExpressionAttributeNames={'#ts': 'timestamp'}
                    )
                    timestamps = [item['timestamp'] for item in response['Items']]

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(
                            ProjectionExpression='#ts',
                            ExpressionAttributeNames={'#ts': 'timestamp'},
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        timestamps.extend([item['timestamp'] for item in response['Items']])

                    if timestamps:
                        unique_timestamps = list(set(timestamps))
                        unique_timestamps.sort(reverse=True)

                        latest_timestamp = unique_timestamps[0]
                        latest_count = timestamps.count(latest_timestamp)
                        old_count = len(timestamps) - latest_count

                        print(f"   総件数: {len(timestamps):,}件")
                        print(f"   最新データ: {latest_timestamp} ({latest_count:,}件)")
                        print(f"   保持対象: {latest_count:,}件")
                        print(f"   削除対象: {old_count:,}件")

                        if len(unique_timestamps) > 1:
                            print(f"   削除予定の古いタイムスタンプ例:")
                            for i, ts in enumerate(unique_timestamps[1:4], 1):
                                count = timestamps.count(ts)
                                print(f"     {i}. {ts} ({count:,}件)")

                        total_to_delete += old_count
                    else:
                        print(f"   データなし")

                elif table_name == 'PoolLatest':
                    # 全データをスキャン
                    response = table.scan()
                    all_items = response['Items']

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                        all_items.extend(response['Items'])

                    if all_items:
                        # 最新のupdated_atを持つデータを特定
                        items_with_time = []
                        for item in all_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append((item, updated_at))

                        if items_with_time:
                            latest_time = max(items_with_time, key=lambda x: x[1])[1]
                            latest_items = [item for item, time in items_with_time if time == latest_time]
                            old_items = [item for item, time in items_with_time if time != latest_time]

                            print(f"   総件数: {len(all_items):,}件")
                            print(f"   最新更新日時: {latest_time}")
                            print(f"   保持対象: 最新データ {len(latest_items):,}件")
                            print(f"   削除対象: 古いデータ {len(old_items):,}件")

                            if old_items:
                                print(f"   削除予定の古いデータ:")
                                for i, item in enumerate(old_items, 1):
                                    pool_id = item.get('pool_id', 'N/A')
                                    updated_at = item.get('updated_at', 'N/A')
                                    print(f"     {i}. pool_id: {pool_id} | updated: {updated_at}")

                            total_to_delete += len(old_items)
                        else:
                            print(f"   総件数: {len(all_items):,}件")
                            print(f"   保持対象: 全データ {len(all_items):,}件（タイムスタンプなし）")
                            print(f"   削除対象: 0件")
                    else:
                        print(f"   データなし")

                elif table_name in ['PoolMeta', 'VaultMeta']:
                    # 全データをスキャン
                    response = table.scan()
                    all_items = response['Items']

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                        all_items.extend(response['Items'])

                    if all_items:
                        # 最新のupdated_atまたはtimestampを持つデータを特定
                        items_with_time = []
                        for item in all_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append((item, updated_at))

                        if items_with_time:
                            latest_time = max(items_with_time, key=lambda x: x[1])[1]
                            latest_items = [item for item, time in items_with_time if time == latest_time]
                            old_items = [item for item, time in items_with_time if time != latest_time]

                            print(f"   総件数: {len(all_items):,}件")
                            print(f"   最新更新日時: {latest_time}")
                            print(f"   保持対象: 最新データ {len(latest_items):,}件")
                            print(f"   削除対象: 古いデータ {len(old_items):,}件")

                            if old_items:
                                print(f"   削除予定の古いデータ:")
                                for i, item in enumerate(old_items, 1):
                                    if table_name == 'PoolMeta':
                                        item_id = item.get('pool_id', 'N/A')
                                    else:  # VaultMeta
                                        item_id = item.get('vault_id', 'N/A')
                                    updated_at = item.get('updated_at', 'N/A')
                                    print(f"     {i}. {table_name[:-4].lower()}_id: {item_id} | updated: {updated_at}")

                            total_to_delete += len(old_items)
                        else:
                            print(f"   総件数: {len(all_items):,}件")
                            print(f"   保持対象: 全データ {len(all_items):,}件（タイムスタンプなし）")
                            print(f"   削除対象: 0件")
                    else:
                        print(f"   データなし")

                else:
                    # CvxStakeMetrics, CvxCrvStakeMetrics用の処理
                    partition_key = table_config['partition_key']
                    partition_value = table_config['partition_value']

                    # 全データを取得
                    response = table.query(
                        KeyConditionExpression=Key(partition_key).eq(partition_value),
                        ScanIndexForward=False
                    )

                    items = response['Items']

                    if len(items) > 1:
                        latest_item = items[0]
                        old_items = items[1:]

                        print(f"   総件数: {len(items):,}件")
                        print(f"   最新データ: {latest_item['timestamp']}")
                        print(f"   保持対象: 1件")
                        print(f"   削除対象: {len(old_items):,}件")

                        if len(old_items) > 0:
                            print(f"   削除予定の古いデータ例:")
                            for i, item in enumerate(old_items[:3], 1):
                                print(f"     {i}. {item['timestamp']}")

                        total_to_delete += len(old_items)
                    else:
                        print(f"   総件数: {len(items):,}件")
                        print(f"   保持対象: {len(items):,}件（最新データのみ）")
                        print(f"   削除対象: 0件")

            except Exception as e:
                print(f"   ❌ {table_name}: エラー ({e})")

        print(f"\n📊 クリーンアップ予定サマリー:")
        print(f"   削除予定件数: {total_to_delete:,}件")
        print(f"   保持対象: 各テーブルの最新データのみ")

        return total_to_delete

    def clean_keep_latest_data(self, confirm=True):
        """最新データ以外を削除"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ 最新データ以外を削除（クリーンアップ）")
            print("⚠️ 最新のタイムスタンプのデータのみ保持します")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("本当に削除を実行しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ 削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ 削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        tables_to_clean = [
            {
                'name': 'CvxStakeMetrics',
                'partition_key': 'token',
                'partition_value': 'CVX',
                'sort_key': 'timestamp'
            },
            {
                'name': 'CvxCrvStakeMetrics',
                'partition_key': 'stake',
                'partition_value': 'cvxCRV',
                'sort_key': 'timestamp'
            },
            {
                'name': 'ConvexPoolMetrics',
                'partition_key': 'pool_id',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'PriceHistory',
                'partition_key': 'asset',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'TokenPriceHistory',
                'partition_key': 'token',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'TokenOHLCDaily',
                'partition_key': 'token',
                'partition_value': None,
                'sort_key': 'timestamp'
            },
            {
                'name': 'PoolLatest',
                'partition_key': 'pool_id',
                'partition_value': None,
                'sort_key': None
            },
            {
                'name': 'CvxStakeHistory',
                'partition_key': 'token',
                'partition_value': 'CVX',
                'sort_key': 'timestamp'
            },
            {
                'name': 'CvxStakeOHLCDaily',
                'partition_key': 'type',
                'partition_value': None,
                'sort_key': 'timestamp'
            }
        ]

        total_deleted = 0

        for table_config in tables_to_clean:
            table_name = table_config['name']
            if confirm:
                print(f"\n🔍 {table_name} の最新データ以外を削除中...")

            try:
                table = self.dynamodb.Table(table_name)

                if table_name == 'ConvexPoolMetrics':
                    # 最新のタイムスタンプを取得
                    response = table.scan(
                        ProjectionExpression='#ts',
                        ExpressionAttributeNames={'#ts': 'timestamp'},
                        Limit=1000
                    )

                    if response['Items']:
                        timestamps = [item['timestamp'] for item in response['Items']]
                        latest_timestamp = max(timestamps)

                        if confirm:
                            print(f"   📅 最新タイムスタンプ: {latest_timestamp}")

                        # 最新タイムスタンプ以外のデータを削除
                        response = table.scan(
                            FilterExpression=Attr('timestamp').ne(latest_timestamp)
                        )

                        old_items = response['Items']

                        # 追加ページがある場合は取得
                        while 'LastEvaluatedKey' in response:
                            response = table.scan(
                                FilterExpression=Attr('timestamp').ne(latest_timestamp),
                                ExclusiveStartKey=response['LastEvaluatedKey']
                            )
                            old_items.extend(response['Items'])

                        if confirm:
                            print(f"   📊 削除対象: {len(old_items):,}件（最新{latest_timestamp}以外）")

                        # バッチ削除
                        deleted_count = 0

                        for i in range(0, len(old_items), 25):
                            batch = old_items[i:i+25]

                            with table.batch_writer() as batch_writer:
                                for item in batch:
                                    key = {
                                        'pool_id': item['pool_id'],
                                        'timestamp': item['timestamp']
                                    }
                                    batch_writer.delete_item(Key=key)
                                    deleted_count += 1

                            # 進捗表示
                            if confirm and len(old_items) > 100 and deleted_count % 100 == 0:
                                progress = (deleted_count / len(old_items)) * 100
                                print(f"   🔄 進捗: {deleted_count:,}/{len(old_items):,} ({progress:.1f}%)")

                            time.sleep(0.1)

                        if confirm:
                            print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                        total_deleted += deleted_count

                elif table_name in ['PriceHistory', 'TokenPriceHistory', 'TokenOHLCDaily']:
                    # 最新のタイムスタンプを取得
                    response = table.scan(
                        ProjectionExpression='#ts',
                        ExpressionAttributeNames={'#ts': 'timestamp'},
                        Limit=1000
                    )

                    if response['Items']:
                        timestamps = [item['timestamp'] for item in response['Items']]
                        latest_timestamp = max(timestamps)

                        if confirm:
                            print(f"   📅 最新タイムスタンプ: {latest_timestamp}")

                        # 最新タイムスタンプ以外のデータを削除
                        response = table.scan(
                            FilterExpression=Attr('timestamp').ne(latest_timestamp)
                        )

                        old_items = response['Items']

                        # 追加ページがある場合は取得
                        while 'LastEvaluatedKey' in response:
                            response = table.scan(
                                FilterExpression=Attr('timestamp').ne(latest_timestamp),
                                ExclusiveStartKey=response['LastEvaluatedKey']
                            )
                            old_items.extend(response['Items'])

                        if confirm:
                            print(f"   📊 削除対象: {len(old_items):,}件（最新{latest_timestamp}以外）")

                        # バッチ削除
                        deleted_count = 0

                        for i in range(0, len(old_items), 25):
                            batch = old_items[i:i+25]

                            with table.batch_writer() as batch_writer:
                                for item in batch:
                                    if table_name == 'PriceHistory':
                                        key = {
                                            'asset': item['asset'],
                                            'timestamp': item['timestamp']
                                        }
                                    elif table_name == 'TokenPriceHistory':
                                        key = {
                                            'token': item['token'],
                                            'timestamp': item['timestamp']
                                        }
                                    elif table_name == 'TokenOHLCDaily':
                                        key = {
                                            'token': item['token'],
                                            'timestamp': item['timestamp']
                                        }
                                    elif table_name == 'USDJPYHistory':
                                        key = {
                                            'asset': item['asset'],
                                            'timestamp': item['timestamp']
                                        }
                                    else:  # USDJPYOHLCDaily
                                        key = {
                                            'asset': item['asset'],
                                            'timestamp': item['timestamp']
                                        }
                                    batch_writer.delete_item(Key=key)
                                    deleted_count += 1

                            # 進捗表示
                            if confirm and len(old_items) > 100 and deleted_count % 100 == 0:
                                progress = (deleted_count / len(old_items)) * 100
                                print(f"   🔄 進捗: {deleted_count:,}/{len(old_items):,} ({progress:.1f}%)")

                            time.sleep(0.1)

                        if confirm:
                            print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                        total_deleted += deleted_count

                elif table_name == 'PoolLatest':
                    # 全データをスキャン
                    response = table.scan()
                    all_items = response['Items']

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                        all_items.extend(response['Items'])

                    if all_items:
                        # 最新のupdated_atを持つデータを特定
                        items_with_time = []
                        for item in all_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append((item, updated_at))

                        if items_with_time:
                            # 最新のupdated_atを取得
                            latest_time = max(items_with_time, key=lambda x: x[1])[1]
                            items_to_delete = [item for item, time in items_with_time if time != latest_time]

                            if confirm:
                                print(f"   📅 最新更新日時: {latest_time}")
                                print(f"   📊 総データ数: {len(all_items):,}件")
                                print(f"   🎯 削除対象: 古いデータ {len(items_to_delete):,}件")
                                print(f"   ✅ 保持対象: 最新データ {len(all_items) - len(items_to_delete):,}件")
                        else:
                            items_to_delete = []
                            if confirm:
                                print(f"   📊 総データ数: {len(all_items):,}件")
                                print(f"   ✅ 保持対象: 全データ {len(all_items):,}件（タイムスタンプなし）")
                                print(f"   🎯 削除対象: 0件")

                        # バッチ削除実行
                        if items_to_delete:
                            deleted_count = 0

                            for i in range(0, len(items_to_delete), 25):
                                batch = items_to_delete[i:i+25]

                                with table.batch_writer() as batch_writer:
                                    for item in batch:
                                        key = {'pool_id': item['pool_id']}
                                        batch_writer.delete_item(Key=key)
                                        deleted_count += 1

                                # 進捗表示
                                if confirm and len(items_to_delete) > 50 and deleted_count % 25 == 0:
                                    progress = (deleted_count / len(items_to_delete)) * 100
                                    print(f"   🔄 進捗: {deleted_count:,}/{len(items_to_delete):,} ({progress:.1f}%)")

                                time.sleep(0.1)

                            if confirm:
                                print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                            total_deleted += deleted_count
                        else:
                            if confirm:
                                print(f"   ✅ {table_name}: 削除対象なし")
                    else:
                        if confirm:
                            print(f"   ✅ {table_name}: データなし")

                elif table_name in ['PoolMeta', 'VaultMeta']:
                    # 全データをスキャン
                    response = table.scan()
                    all_items = response['Items']

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                        all_items.extend(response['Items'])

                    if all_items:
                        # 最新のupdated_atまたはtimestampを持つデータを特定
                        items_with_time = []
                        for item in all_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append((item, updated_at))

                        if items_with_time:
                            # 最新のupdated_atを取得
                            latest_time = max(items_with_time, key=lambda x: x[1])[1]
                            items_to_delete = [item for item, time in items_with_time if time != latest_time]

                            if confirm:
                                print(f"   📅 最新更新日時: {latest_time}")
                                print(f"   📊 総データ数: {len(all_items):,}件")
                                print(f"   🎯 削除対象: 古いデータ {len(items_to_delete):,}件")
                                print(f"   ✅ 保持対象: 最新データ {len(all_items) - len(items_to_delete):,}件")
                        else:
                            items_to_delete = []
                            if confirm:
                                print(f"   📊 総データ数: {len(all_items):,}件")
                                print(f"   ✅ 保持対象: 全データ {len(all_items):,}件（タイムスタンプなし）")
                                print(f"   🎯 削除対象: 0件")

                        # バッチ削除実行
                        if items_to_delete:
                            deleted_count = 0

                            for i in range(0, len(items_to_delete), 25):
                                batch = items_to_delete[i:i+25]

                                with table.batch_writer() as batch_writer:
                                    for item in batch:
                                        # 実際のプライマリキーを動的に特定
                                        key = {}
                                        
                                        if table_name == 'PoolMeta':
                                            # PoolMetaのプライマリキー候補を順番に試す
                                            if 'pool_id' in item:
                                                key = {'pool_id': item['pool_id']}
                                            elif 'id' in item:
                                                key = {'id': item['id']}
                                            elif 'name' in item:
                                                key = {'name': item['name']}
                                            elif 'symbol' in item:
                                                key = {'symbol': item['symbol']}
                                        else:  # VaultMeta
                                            # VaultMetaのプライマリキーはvault_id（再作成後）
                                            if 'vault_id' in item:
                                                key = {'vault_id': item['vault_id']}
                                            elif 'pool_id' in item:
                                                key = {'pool_id': item['pool_id']}
                                            elif 'id' in item:
                                                key = {'id': item['id']}
                                            elif 'name' in item:
                                                key = {'name': item['name']}
                                            elif 'symbol' in item:
                                                key = {'symbol': item['symbol']}
                                        
                                        if key:
                                            batch_writer.delete_item(Key=key)
                                            deleted_count += 1
                                        else:
                                            # 利用可能なキーを表示してエラー
                                            available_keys = list(item.keys())
                                            print(f"   ❌ {table_name}のプライマリキーが見つかりません。利用可能なキー: {available_keys}")
                                            continue

                                # 進捗表示
                                if confirm and len(items_to_delete) > 50 and deleted_count % 25 == 0:
                                    progress = (deleted_count / len(items_to_delete)) * 100
                                    print(f"   🔄 進捗: {deleted_count:,}/{len(items_to_delete):,} ({progress:.1f}%)")

                                time.sleep(0.1)

                            if confirm:
                                print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                            total_deleted += deleted_count
                        else:
                            if confirm:
                                print(f"   ✅ {table_name}: 削除対象なし")
                    else:
                        if confirm:
                            print(f"   ✅ {table_name}: データなし")

                else:
                    # CvxStakeMetrics, CvxCrvStakeMetrics用の処理
                    partition_key = table_config['partition_key']
                    partition_value = table_config['partition_value']

                    # 全データを取得
                    response = table.query(
                        KeyConditionExpression=Key(partition_key).eq(partition_value),
                        ScanIndexForward=False
                    )

                    items = response['Items']

                    if len(items) > 1:
                        # 最新（最初）以外を削除対象とする
                        latest_item = items[0]
                        old_items = items[1:]

                        if confirm:
                            print(f"   📅 最新データ: {latest_item['timestamp']}")
                            print(f"   📊 削除対象: {len(old_items):,}件")

                        # バッチ削除
                        deleted_count = 0

                        for i in range(0, len(old_items), 25):
                            batch = old_items[i:i+25]

                            with table.batch_writer() as batch_writer:
                                for item in batch:
                                    key = {
                                        partition_key: item[partition_key],
                                        'timestamp': item['timestamp']
                                    }
                                    batch_writer.delete_item(Key=key)
                                    deleted_count += 1

                            time.sleep(0.1)

                        if confirm:
                            print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                        total_deleted += deleted_count
                    else:
                        if confirm:
                            print(f"   ✅ {table_name}: 削除対象なし（最新データのみ）")

            except Exception as e:
                if confirm:
                    print(f"   ❌ {table_name} 処理エラー: {e}")

        if confirm:
            print(f"\n📊 クリーンアップ完了:")
            print(f"   削除件数: {total_deleted:,}件")
            print(f"   保持: 各テーブルの最新データのみ")

        return total_deleted

    def delete_all_data(self, confirm=True):
        """全データ削除機能（⚠️危険⚠️）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🔥 全データ削除機能")
            print("⚠️⚠️⚠️ 警告: 全てのデータが削除されます ⚠️⚠️⚠️")
            print("=" * 60)
            
            # 確認プロンプト
            print("⚠️ この操作は取り消せません！")
            while True:
                user_input = input("本当に全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ 全データ削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ 全データ削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除対象テーブル
        tables_to_clear = [
            'CvxStakeMetrics',
            'CvxCrvStakeMetrics',
            'ConvexPoolMetrics',
            'PriceHistory',
            'TokenPriceHistory',
            'TokenOHLCDaily',
            'USDJPYHistory',
            'USDJPYOHLCDaily',
            'PoolLatest',
            'CvxStakeHistory',
            'CvxStakeOHLCDaily'
        ]

        total_deleted = 0

        for table_name in tables_to_clear:
            if confirm:
                print(f"\n🔥 {table_name} の全データを削除中...")

            try:
                table = self.dynamodb.Table(table_name)

                # テーブルの全データをスキャン
                response = table.scan()
                items = response['Items']

                # ページネーション対応
                while 'LastEvaluatedKey' in response:
                    response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                    items.extend(response['Items'])

                if items:
                    if confirm:
                        print(f"   📊 削除対象: {len(items):,}件")

                    # バッチ削除
                    deleted_count = 0

                    for i in range(0, len(items), 25):
                        batch = items[i:i+25]

                        with table.batch_writer() as batch_writer:
                            for item in batch:
                                # テーブルごとに適切なキーを設定
                                if table_name == 'CvxStakeMetrics':
                                    key = {
                                        'token': item['token'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'CvxCrvStakeMetrics':
                                    key = {
                                        'stake': item['stake'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'CvxStakeHistory':
                                    key = {
                                        'token': item['token'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'CvxStakeOHLCDaily':
                                    key = {
                                        'type': item['type'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'ConvexPoolMetrics':
                                    key = {
                                        'pool_id': item['pool_id'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'PriceHistory':
                                    key = {
                                        'asset': item['asset'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'TokenPriceHistory':
                                    key = {
                                        'token': item['token'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'TokenOHLCDaily':
                                    key = {
                                        'token': item['token'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'USDJPYHistory':
                                    key = {
                                        'asset': item['asset'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'USDJPYOHLCDaily':
                                    key = {
                                        'asset': item['asset'],
                                        'timestamp': item['timestamp']
                                    }
                                elif table_name == 'PoolLatest':
                                    key = {
                                        'pool_id': item['pool_id']
                                    }

                                batch_writer.delete_item(Key=key)
                                deleted_count += 1

                        # 進捗表示
                        if confirm and len(items) > 100 and deleted_count % 100 == 0:
                            progress = (deleted_count / len(items)) * 100
                            print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                        time.sleep(0.1)  # レート制限対策

                    if confirm:
                        print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                    total_deleted += deleted_count
                else:
                    if confirm:
                        print(f"   ✅ {table_name}: データなし")

            except Exception as e:
                if confirm:
                    print(f"   ❌ {table_name} 削除エラー: {e}")

        if confirm:
            print(f"\n🔥 全データ削除完了:")
            print(f"   削除件数: {total_deleted:,}件")

        return total_deleted

    def delete_poolmeta_all(self, confirm=True):
        """PoolMetaテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ PoolMetaテーブル全件削除機能")
            print("⚠️ PoolMetaテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("PoolMetaテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ PoolMetaテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ PoolMetaテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'metadata',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='PoolMeta',
            operation='full_delete',
            function_name='delete_poolmeta_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('PoolMeta')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            # 実際のプライマリキーを動的に特定
                            key = {}
                            
                            # プライマリキーの候補を順番に試す
                            if 'pool_id' in item:
                                key = {'pool_id': item['pool_id']}
                            elif 'id' in item:
                                key = {'id': item['id']}
                            elif 'name' in item:
                                key = {'name': item['name']}
                            elif 'symbol' in item:
                                key = {'symbol': item['symbol']}
                            else:
                                # 利用可能なキーを表示してエラー
                                available_keys = list(item.keys())
                                print(f"   ❌ プライマリキーが見つかりません。利用可能なキー: {available_keys}")
                                continue
                            
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ PoolMetaテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='PoolMeta',
                    operation='delete_completed',
                    function_name='delete_poolmeta_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ PoolMetaテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='PoolMeta',
                    operation='delete_completed',
                    function_name='delete_poolmeta_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ PoolMetaテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='PoolMeta',
                operation='delete_error',
                function_name='delete_poolmeta_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_vaultmeta_all(self, confirm=True):
        """VaultMetaテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ VaultMetaテーブル全件削除機能")
            print("⚠️ VaultMetaテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("VaultMetaテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ VaultMetaテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ VaultMetaテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'metadata',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='VaultMeta',
            operation='full_delete',
            function_name='delete_vaultmeta_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('VaultMeta')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            # 実際のプライマリキーを動的に特定
                            key = {}
                            
                            # VaultMetaテーブルのプライマリキーはvault_id（再作成後）
                            if 'vault_id' in item:
                                key = {'vault_id': item['vault_id']}
                            elif 'pool_id' in item:
                                key = {'pool_id': item['pool_id']}
                            elif 'id' in item:
                                key = {'id': item['id']}
                            elif 'name' in item:
                                key = {'name': item['name']}
                            elif 'symbol' in item:
                                key = {'symbol': item['symbol']}
                            else:
                                # 利用可能なキーを表示してエラー
                                available_keys = list(item.keys())
                                print(f"   ❌ プライマリキーが見つかりません。利用可能なキー: {available_keys}")
                                continue
                            
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ VaultMetaテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='VaultMeta',
                    operation='delete_completed',
                    function_name='delete_vaultmeta_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ VaultMetaテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='VaultMeta',
                    operation='delete_completed',
                    function_name='delete_vaultmeta_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ VaultMetaテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='VaultMeta',
                operation='delete_error',
                function_name='delete_vaultmeta_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_token_price_history_all(self, confirm=True):
        """TokenPriceHistoryテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ TokenPriceHistoryテーブル全件削除機能")
            print("⚠️ TokenPriceHistoryテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("TokenPriceHistoryテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ TokenPriceHistoryテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ TokenPriceHistoryテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'price_history',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='TokenPriceHistory',
            operation='full_delete',
            function_name='delete_token_price_history_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('TokenPriceHistory')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {
                                'token': item['token'],
                                'timestamp': item['timestamp']
                            }
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ TokenPriceHistoryテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='TokenPriceHistory',
                    operation='delete_completed',
                    function_name='delete_token_price_history_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ TokenPriceHistoryテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='TokenPriceHistory',
                    operation='delete_completed',
                    function_name='delete_token_price_history_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ TokenPriceHistoryテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='TokenPriceHistory',
                operation='delete_error',
                function_name='delete_token_price_history_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_token_ohlc_daily_all(self, confirm=True):
        """TokenOHLCDailyテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ TokenOHLCDailyテーブル全件削除機能")
            print("⚠️ TokenOHLCDailyテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("TokenOHLCDailyテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ TokenOHLCDailyテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ TokenOHLCDailyテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'ohlc_daily',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='TokenOHLCDaily',
            operation='full_delete',
            function_name='delete_token_ohlc_daily_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('TokenOHLCDaily')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {
                                'token': item['token'],
                                'timestamp': item['timestamp']
                            }
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ TokenOHLCDailyテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='TokenOHLCDaily',
                    operation='delete_completed',
                    function_name='delete_token_ohlc_daily_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ TokenOHLCDailyテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='TokenOHLCDaily',
                    operation='delete_completed',
                    function_name='delete_token_ohlc_daily_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ TokenOHLCDailyテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='TokenOHLCDaily',
                operation='delete_error',
                function_name='delete_token_ohlc_daily_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_usdjpy_history_all(self, confirm=True):
        """USDJPYHistoryテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ USDJPYHistoryテーブル全件削除機能")
            print("⚠️ USDJPYHistoryテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("USDJPYHistoryテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ USDJPYHistoryテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ USDJPYHistoryテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'usdjpy_history',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='USDJPYHistory',
            operation='full_delete',
            function_name='delete_usdjpy_history_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('USDJPYHistory')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {
                                'asset': item['asset'],
                                'timestamp': item['timestamp']
                            }
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ USDJPYHistoryテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='USDJPYHistory',
                    operation='delete_completed',
                    function_name='delete_usdjpy_history_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ USDJPYHistoryテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='USDJPYHistory',
                    operation='delete_completed',
                    function_name='delete_usdjpy_history_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ USDJPYHistoryテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='USDJPYHistory',
                operation='delete_error',
                function_name='delete_usdjpy_history_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_usdjpy_ohlc_daily_all(self, confirm=True):
        """USDJPYOHLCDailyテーブル全件削除機能（追跡付き）"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print("🗑️ USDJPYOHLCDailyテーブル全件削除機能")
            print("⚠️ USDJPYOHLCDailyテーブルの全データが削除されます")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input("USDJPYOHLCDailyテーブルの全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print("✅ USDJPYOHLCDailyテーブル全件削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print("❌ USDJPYOHLCDailyテーブル削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'full_delete',
            'table_type': 'usdjpy_ohlc_daily',
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='USDJPYOHLCDaily',
            operation='full_delete',
            function_name='delete_usdjpy_ohlc_daily_all',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table('USDJPYOHLCDaily')
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {
                                'asset': item['asset'],
                                'timestamp': item['timestamp']
                            }
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ USDJPYOHLCDailyテーブル: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='USDJPYOHLCDaily',
                    operation='delete_completed',
                    function_name='delete_usdjpy_ohlc_daily_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ USDJPYOHLCDailyテーブル: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='USDJPYOHLCDaily',
                    operation='delete_completed',
                    function_name='delete_usdjpy_ohlc_daily_all',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ USDJPYOHLCDailyテーブル削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='USDJPYOHLCDaily',
                operation='delete_error',
                function_name='delete_usdjpy_ohlc_daily_all',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def list_pools(self):
        """プール一覧表示機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return []

        print("📋 プール一覧表示")
        print("=" * 60)

        pools_data = []

        try:
            # PoolLatestテーブルからプール一覧を取得
            table = self.dynamodb.Table('PoolLatest')
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                print(f"📊 総プール数: {len(items):,}件")
                print()

                for i, item in enumerate(items, 1):
                    pool_id = item.get('pool_id', 'N/A')
                    name = item.get('name', 'N/A')
                    symbol = item.get('symbol', 'N/A')
                    updated_at = item.get('updated_at', item.get('timestamp', 'N/A'))
                    
                    pool_info = {
                        'index': i,
                        'pool_id': pool_id,
                        'name': name,
                        'symbol': symbol,
                        'updated_at': updated_at
                    }
                    pools_data.append(pool_info)

                    print(f"{i:3d}. Pool ID: {pool_id}")
                    print(f"     Name: {name}")
                    print(f"     Symbol: {symbol}")
                    print(f"     Updated: {updated_at}")
                    print()

                return pools_data
            else:
                print("❌ プールデータがありません")
                return []

        except Exception as e:
            print(f"❌ プール一覧取得エラー: {e}")
            return []

    def delete_individual_pool(self, pool_id, confirm=True):
        """個別プール削除機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print(f"🗑️ 個別プール削除機能")
            print(f"🎯 対象プール: {pool_id}")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input(f"プール '{pool_id}' を削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print(f"✅ プール '{pool_id}' の削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print(f"❌ プール '{pool_id}' の削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'individual_pool_delete',
            'pool_id': pool_id,
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name='PoolLatest',
            operation='individual_delete',
            function_name='delete_individual_pool',
            caller_info=caller_info,
            additional_data=additional_data
        )

        total_deleted = 0

        try:
            # PoolLatestテーブルから該当プールを削除
            table = self.dynamodb.Table('PoolLatest')
            
            # 該当プールのデータを取得
            response = table.query(
                KeyConditionExpression=Key('pool_id').eq(pool_id)
            )
            
            if response['Items']:
                if confirm:
                    print(f"   📊 削除対象: {len(response['Items']):,}件")
                
                # バッチ削除
                deleted_count = 0
                
                for i in range(0, len(response['Items']), 25):
                    batch = response['Items'][i:i+25]
                    
                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {'pool_id': item['pool_id']}
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1
                    
                    time.sleep(0.1)  # レート制限対策
                
                if confirm:
                    print(f"   ✅ PoolLatest: {deleted_count:,}件削除完了")
                total_deleted += deleted_count
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name='PoolLatest',
                    operation='delete_completed',
                    function_name='delete_individual_pool',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'pool_id': pool_id, 'status': 'success'}
                )
            else:
                if confirm:
                    print(f"   ✅ PoolLatest: プール '{pool_id}' のデータなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name='PoolLatest',
                    operation='delete_completed',
                    function_name='delete_individual_pool',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'pool_id': pool_id, 'status': 'no_data'}
                )

            # ConvexPoolMetricsテーブルからも該当プールを削除
            table = self.dynamodb.Table('ConvexPoolMetrics')
            
            # 該当プールのデータを取得
            response = table.query(
                KeyConditionExpression=Key('pool_id').eq(pool_id)
            )
            
            if response['Items']:
                if confirm:
                    print(f"   📊 ConvexPoolMetrics削除対象: {len(response['Items']):,}件")
                
                # バッチ削除
                deleted_count = 0
                
                for i in range(0, len(response['Items']), 25):
                    batch = response['Items'][i:i+25]
                    
                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            key = {
                                'pool_id': item['pool_id'],
                                'timestamp': item['timestamp']
                            }
                            batch_writer.delete_item(Key=key)
                            deleted_count += 1
                    
                    time.sleep(0.1)  # レート制限対策
                
                if confirm:
                    print(f"   ✅ ConvexPoolMetrics: {deleted_count:,}件削除完了")
                total_deleted += deleted_count
            else:
                if confirm:
                    print(f"   ✅ ConvexPoolMetrics: プール '{pool_id}' のデータなし")

            if confirm:
                print(f"\n📊 プール '{pool_id}' 削除完了:")
                print(f"   削除件数: {total_deleted:,}件")
                print(f"   対象テーブル: PoolLatest, ConvexPoolMetrics")

            return total_deleted

        except Exception as e:
            if confirm:
                print(f"   ❌ プール '{pool_id}' 削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name='PoolLatest',
                operation='delete_error',
                function_name='delete_individual_pool',
                caller_info=caller_info,
                additional_data={'error': str(e), 'pool_id': pool_id, 'status': 'error'}
            )
            
            return False

    def delete_multiple_pools(self, pool_ids, confirm=True):
        """複数プール一括削除機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print(f"🗑️ 複数プール一括削除機能")
            print(f"🎯 対象プール数: {len(pool_ids)}件")
            print(f"📋 対象プール: {', '.join(pool_ids)}")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input(f"{len(pool_ids)}個のプールを一括削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print(f"✅ {len(pool_ids)}個のプールの一括削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print(f"❌ 複数プールの一括削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        total_deleted = 0
        success_count = 0
        error_count = 0

        for i, pool_id in enumerate(pool_ids, 1):
            if confirm:
                print(f"\n🔄 処理中 ({i}/{len(pool_ids)}): {pool_id}")
            
            result = self.delete_individual_pool(pool_id, confirm=False)
            
            if result is not False:
                total_deleted += result
                success_count += 1
                if confirm:
                    print(f"   ✅ 成功: {result:,}件削除")
            else:
                error_count += 1
                if confirm:
                    print(f"   ❌ エラー: 削除失敗")

        if confirm:
            print(f"\n📊 複数プール一括削除完了:")
            print(f"   成功: {success_count}個のプール")
            print(f"   エラー: {error_count}個のプール")
            print(f"   総削除件数: {total_deleted:,}件")

        return total_deleted

    def list_tables(self):
        """テーブル一覧表示機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return []

        print("📋 テーブル一覧表示")
        print("=" * 60)

        tables_data = []

        # 対象テーブル一覧
        tables = [
            'CvxStakeMetrics',
            'CvxCrvStakeMetrics', 
            'ConvexPoolMetrics',
            'PriceHistory',
            'TokenPriceHistory',
            'TokenOHLCDaily',
            'USDJPYHistory',
            'USDJPYOHLCDaily',
            'PoolLatest',
            'PoolMeta',
            'VaultMeta',
            'CvxStakeHistory',
            'CvxStakeOHLCDaily'
        ]

        for i, table_name in enumerate(tables, 1):
            try:
                table = self.dynamodb.Table(table_name)
                
                # 件数取得
                response = table.scan(Select='COUNT')
                count = response['Count']

                # ページネーション対応で正確な件数を取得
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        Select='COUNT',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    count += response['Count']

                # 最新データ情報を取得
                if table_name in ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'CvxStakeHistory']:
                    # 特定のパーティションキーで最新データを取得
                    if table_name == 'CvxStakeMetrics':
                        partition_key = 'token'
                        partition_value = 'CVX'
                    elif table_name == 'CvxStakeHistory':
                        partition_key = 'token'
                        partition_value = 'CVX'
                    else:  # CvxCrvStakeMetrics
                        partition_key = 'stake'
                        partition_value = 'cvxCRV'

                    response = table.query(
                        KeyConditionExpression=Key(partition_key).eq(partition_value),
                        ScanIndexForward=False,  # 降順ソート
                        Limit=1
                    )

                    if response['Items']:
                        latest_timestamp = response['Items'][0]['timestamp']
                        latest_info = f"最新: {latest_timestamp}"
                    else:
                        latest_info = "データなし"

                elif table_name in ['ConvexPoolMetrics', 'PriceHistory', 'TokenPriceHistory', 'TokenOHLCDaily', 'USDJPYHistory', 'USDJPYOHLCDaily', 'CvxStakeOHLCDaily']:
                    # 全データをスキャンして最新タイムスタンプを取得
                    response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
                    timestamps = [item['timestamp'] for item in response['Items']]

                    # ページネーション対応
                    while 'LastEvaluatedKey' in response:
                        response = table.scan(
                            ProjectionExpression='#ts',
                            ExpressionAttributeNames={'#ts': 'timestamp'},
                            ExclusiveStartKey=response['LastEvaluatedKey']
                        )
                        timestamps.extend([item['timestamp'] for item in response['Items']])

                    latest_info = f"最新: {max(timestamps)}" if timestamps else "データなし"

                elif table_name == 'PoolLatest':
                    sample_response = table.scan(Limit=3)
                    sample_items = sample_response['Items']
                    if sample_items:
                        # 最新のupdated_atを持つデータを特定
                        items_with_time = []
                        for item in sample_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append(updated_at)

                        if items_with_time:
                            latest_time = max(items_with_time)
                            latest_info = f"最新更新: {latest_time}"
                        else:
                            latest_info = f"データ: {len(sample_items)}件"
                    else:
                        latest_info = "データなし"

                elif table_name in ['PoolMeta', 'VaultMeta']:
                    # メタデータテーブルは通常最新のupdated_atまたはtimestampで判定
                    sample_response = table.scan(Limit=5)
                    sample_items = sample_response['Items']
                    if sample_items:
                        # 最新のupdated_atまたはtimestampを持つデータを特定
                        items_with_time = []
                        for item in sample_items:
                            updated_at = item.get('updated_at', item.get('timestamp', ''))
                            if updated_at:
                                items_with_time.append(updated_at)

                        if items_with_time:
                            latest_time = max(items_with_time)
                            latest_info = f"最新更新: {latest_time}"
                        else:
                            latest_info = f"データ: {len(sample_items)}件"
                    else:
                        latest_info = "データなし"

                table_info = {
                    'index': i,
                    'table_name': table_name,
                    'count': count,
                    'latest_info': latest_info
                }
                tables_data.append(table_info)

                print(f"{i:2d}. {table_name}")
                print(f"    件数: {count:,}件")
                print(f"    状況: {latest_info}")
                print()

            except Exception as e:
                print(f"❌ {table_name}: エラー ({e})")
                table_info = {
                    'index': i,
                    'table_name': table_name,
                    'count': 'エラー',
                    'latest_info': 'エラー'
                }
                tables_data.append(table_info)

        return tables_data

    def delete_individual_table(self, table_name, confirm=True):
        """個別テーブル全件削除機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print(f"🗑️ 個別テーブル全件削除機能")
            print(f"🎯 対象テーブル: {table_name}")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input(f"テーブル '{table_name}' の全データを削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print(f"✅ テーブル '{table_name}' の全データ削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print(f"❌ テーブル '{table_name}' の削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        # 削除操作を追跡ログに記録
        caller_info = self.tracker._get_caller_info()
        additional_data = {
            'operation': 'individual_table_delete',
            'table_name': table_name,
            'confirmation_required': confirm
        }
        self.tracker.log_deletion_operation(
            table_name=table_name,
            operation='individual_delete',
            function_name='delete_individual_table',
            caller_info=caller_info,
            additional_data=additional_data
        )

        try:
            table = self.dynamodb.Table(table_name)
            
            # テーブルの全データをスキャン
            response = table.scan()
            items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response['Items'])

            if items:
                if confirm:
                    print(f"   📊 削除対象: {len(items):,}件")

                # バッチ削除
                deleted_count = 0

                for i in range(0, len(items), 25):
                    batch = items[i:i+25]

                    with table.batch_writer() as batch_writer:
                        for item in batch:
                            # テーブルごとに適切なキーを設定
                            key = {}
                            
                            if table_name == 'CvxStakeMetrics':
                                key = {
                                    'token': item['token'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'CvxCrvStakeMetrics':
                                key = {
                                    'stake': item['stake'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'CvxStakeHistory':
                                key = {
                                    'token': item['token'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'CvxStakeOHLCDaily':
                                key = {
                                    'type': item['type'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'ConvexPoolMetrics':
                                key = {
                                    'pool_id': item['pool_id'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'PriceHistory':
                                key = {
                                    'asset': item['asset'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'TokenPriceHistory':
                                key = {
                                    'token': item['token'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'TokenOHLCDaily':
                                key = {
                                    'token': item['token'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'USDJPYHistory':
                                key = {
                                    'asset': item['asset'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'USDJPYOHLCDaily':
                                key = {
                                    'asset': item['asset'],
                                    'timestamp': item['timestamp']
                                }
                            elif table_name == 'PoolLatest':
                                key = {
                                    'pool_id': item['pool_id']
                                }
                            elif table_name == 'PoolMeta':
                                # プライマリキーの候補を順番に試す
                                if 'pool_id' in item:
                                    key = {'pool_id': item['pool_id']}
                                elif 'id' in item:
                                    key = {'id': item['id']}
                                elif 'name' in item:
                                    key = {'name': item['name']}
                                elif 'symbol' in item:
                                    key = {'symbol': item['symbol']}
                                else:
                                    # 利用可能なキーを表示してエラー
                                    available_keys = list(item.keys())
                                    print(f"   ❌ プライマリキーが見つかりません。利用可能なキー: {available_keys}")
                                    continue
                            elif table_name == 'VaultMeta':
                                # VaultMetaテーブルのプライマリキーはvault_id（再作成後）
                                if 'vault_id' in item:
                                    key = {'vault_id': item['vault_id']}
                                elif 'pool_id' in item:
                                    key = {'pool_id': item['pool_id']}
                                elif 'id' in item:
                                    key = {'id': item['id']}
                                elif 'name' in item:
                                    key = {'name': item['name']}
                                elif 'symbol' in item:
                                    key = {'symbol': item['symbol']}
                                else:
                                    # 利用可能なキーを表示してエラー
                                    available_keys = list(item.keys())
                                    print(f"   ❌ プライマリキーが見つかりません。利用可能なキー: {available_keys}")
                                    continue
                            
                            if key:
                                batch_writer.delete_item(Key=key)
                                deleted_count += 1

                    # 進捗表示
                    if confirm and len(items) > 100 and deleted_count % 100 == 0:
                        progress = (deleted_count / len(items)) * 100
                        print(f"   🔄 進捗: {deleted_count:,}/{len(items):,} ({progress:.1f}%)")

                    time.sleep(0.1)  # レート制限対策

                if confirm:
                    print(f"   ✅ {table_name}: {deleted_count:,}件削除完了")
                
                # 削除完了ログを記録
                self.tracker.log_deletion_operation(
                    table_name=table_name,
                    operation='delete_completed',
                    function_name='delete_individual_table',
                    caller_info=caller_info,
                    additional_data={'deleted_count': deleted_count, 'status': 'success'}
                )
                
                return deleted_count
            else:
                if confirm:
                    print(f"   ✅ {table_name}: データなし")
                
                # 削除対象なしログを記録
                self.tracker.log_deletion_operation(
                    table_name=table_name,
                    operation='delete_completed',
                    function_name='delete_individual_table',
                    caller_info=caller_info,
                    additional_data={'deleted_count': 0, 'status': 'no_data'}
                )
                
                return 0

        except Exception as e:
            if confirm:
                print(f"   ❌ {table_name} 削除エラー: {e}")
            
            # エラーログを記録
            self.tracker.log_deletion_operation(
                table_name=table_name,
                operation='delete_error',
                function_name='delete_individual_table',
                caller_info=caller_info,
                additional_data={'error': str(e), 'status': 'error'}
            )
            
            return False

    def delete_multiple_tables(self, table_names, confirm=True):
        """複数テーブル一括削除機能"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return False

        if confirm:
            print(f"🗑️ 複数テーブル一括削除機能")
            print(f"🎯 対象テーブル数: {len(table_names)}件")
            print(f"📋 対象テーブル: {', '.join(table_names)}")
            print("=" * 60)
            
            # 確認プロンプト
            while True:
                user_input = input(f"{len(table_names)}個のテーブルを一括削除しますか？ (y/N): ").strip().lower()
                if user_input in ['y', 'yes']:
                    print(f"✅ {len(table_names)}個のテーブルの一括削除を実行します...")
                    break
                elif user_input in ['n', 'no', '']:
                    print(f"❌ 複数テーブルの一括削除をキャンセルしました")
                    return False
                else:
                    print("⚠️ 'y' または 'n' を入力してください")

        total_deleted = 0
        success_count = 0
        error_count = 0

        for i, table_name in enumerate(table_names, 1):
            if confirm:
                print(f"\n🔄 処理中 ({i}/{len(table_names)}): {table_name}")
            
            result = self.delete_individual_table(table_name, confirm=False)
            
            if result is not False:
                total_deleted += result
                success_count += 1
                if confirm:
                    print(f"   ✅ 成功: {result:,}件削除")
            else:
                error_count += 1
                if confirm:
                    print(f"   ❌ エラー: 削除失敗")

        if confirm:
            print(f"\n📊 複数テーブル一括削除完了:")
            print(f"   成功: {success_count}個のテーブル")
            print(f"   エラー: {error_count}個のテーブル")
            print(f"   総削除件数: {total_deleted:,}件")

        return total_deleted

    def create_cleanup_chart(self):
        """クリーンアップ前後のデータ件数比較チャート"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return

        print("📊 クリーンアップ前後のデータ件数比較チャート作成中...")

        # クリーンアップ前のデータ件数
        tables = ['CvxStakeMetrics', 'CvxCrvStakeMetrics', 'ConvexPoolMetrics', 'PriceHistory', 'TokenPriceHistory', 'TokenOHLCDaily', 'PoolLatest', 'PoolMeta', 'VaultMeta', 'CvxStakeHistory', 'CvxStakeOHLCDaily']
        before_counts = []
        after_counts = []

        # クリーンアップ前の件数取得
        for table_name in tables:
            try:
                table = self.dynamodb.Table(table_name)
                response = table.scan(Select='COUNT')
                count = response['Count']

                # ページネーション対応
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        Select='COUNT',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    count += response['Count']

                before_counts.append(count)
            except Exception as e:
                before_counts.append(0)

        # クリーンアップ実行
        deleted_count = self.clean_keep_latest_data(confirm=False)

        # クリーンアップ後の件数取得
        for table_name in tables:
            try:
                table = self.dynamodb.Table(table_name)
                response = table.scan(Select='COUNT')
                count = response['Count']

                # ページネーション対応
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        Select='COUNT',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    count += response['Count']

                after_counts.append(count)
            except Exception as e:
                after_counts.append(0)

        # チャート作成
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # クリーンアップ前後の比較バーチャート
        x = range(len(tables))
        width = 0.35

        ax1.bar([i - width/2 for i in x], before_counts, width, label='クリーンアップ前', color='lightcoral', alpha=0.8)
        ax1.bar([i + width/2 for i in x], after_counts, width, label='クリーンアップ後', color='lightgreen', alpha=0.8)

        ax1.set_xlabel('テーブル')
        ax1.set_ylabel('データ件数')
        ax1.set_title('クリーンアップ前後のデータ件数比較')
        ax1.set_xticks(x)
        ax1.set_xticklabels(tables, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 削除件数のパイチャート
        if deleted_count > 0:
            remaining = sum(after_counts)
            sizes = [deleted_count, remaining]
            labels = ['削除されたデータ', '残存データ']
            colors = ['lightcoral', 'lightgreen']

            ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax2.set_title(f'データ削除結果\n(削除: {deleted_count:,}件, 残存: {remaining:,}件)')
        else:
            ax2.text(0.5, 0.5, '削除対象データなし', ha='center', va='center', transform=ax2.transAxes, fontsize=12)
            ax2.set_title('クリーンアップ結果')

        plt.tight_layout()
        plt.show()

        # 結果サマリー表示
        print(f"\n📊 クリーンアップ結果サマリー:")
        print(f"   削除件数: {deleted_count:,}件")
        print(f"   残存件数: {sum(after_counts):,}件")
        print(f"   削除率: {(deleted_count / (deleted_count + sum(after_counts)) * 100):.1f}%")

# セル3: 実行用関数
def show_table_overview():
    """テーブル概要表示"""
    tool = DynamoDBCleanupTool()
    return tool.get_table_overview()

def preview_latest_cleanup():
    """最新データ保持クリーンアップのプレビュー"""
    tool = DynamoDBCleanupTool()
    return tool.preview_cleanup_latest()

def execute_latest_cleanup():
    """最新データ保持クリーンアップ実行"""
    tool = DynamoDBCleanupTool()
    return tool.clean_keep_latest_data()

def execute_full_cleanup():
    """全データ削除実行（⚠️危険⚠️）"""
    tool = DynamoDBCleanupTool()
    return tool.delete_all_data()

def create_cleanup_comparison():
    """クリーンアップ前後の比較チャート作成"""
    tool = DynamoDBCleanupTool()
    return tool.create_cleanup_chart()

def execute_poolmeta_delete():
    """PoolMetaテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_poolmeta_all()

def execute_vaultmeta_delete():
    """VaultMetaテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_vaultmeta_all()

def execute_token_price_history_delete():
    """TokenPriceHistoryテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_token_price_history_all()

def execute_token_ohlc_daily_delete():
    """TokenOHLCDailyテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_token_ohlc_daily_all()

def execute_usdjpy_history_delete():
    """USDJPYHistoryテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_usdjpy_history_all()

def execute_usdjpy_ohlc_daily_delete():
    """USDJPYOHLCDailyテーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_usdjpy_ohlc_daily_all()

def show_pool_list():
    """プール一覧表示"""
    tool = DynamoDBCleanupTool()
    return tool.list_pools()

def delete_single_pool(pool_id):
    """個別プール削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_individual_pool(pool_id)

def delete_multiple_pools(pool_ids):
    """複数プール一括削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_multiple_pools(pool_ids)

def show_table_list():
    """テーブル一覧表示"""
    tool = DynamoDBCleanupTool()
    return tool.list_tables()

def delete_single_table(table_name):
    """個別テーブル全件削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_individual_table(table_name)

def delete_multiple_tables(table_names):
    """複数テーブル一括削除実行"""
    tool = DynamoDBCleanupTool()
    return tool.delete_multiple_tables(table_names)

def debug_vault_meta_structure():
    """VaultMetaテーブルの構造をデバッグ表示（vault_idがプライマリキー）"""
    tool = DynamoDBCleanupTool()
    
    if not tool.connection_status:
        print("❌ DynamoDBに接続できません")
        return
    
    print("🔍 VaultMetaテーブル構造デバッグ")
    print("="*50)
    
    try:
        table = tool.dynamodb.Table('VaultMeta')
        
        # テーブルスキーマ情報を取得
        print("📋 テーブルスキーマ情報:")
        table_info = table.meta.client.describe_table(TableName='VaultMeta')
        key_schema = table_info['Table']['KeySchema']
        
        print("   🔑 キースキーマ:")
        for key in key_schema:
            key_name = key['AttributeName']
            key_type = key['KeyType']  # HASH (パーティションキー) または RANGE (ソートキー)
            print(f"      {key_name}: {key_type}")
        
        # 属性定義を取得
        attribute_definitions = table_info['Table']['AttributeDefinitions']
        print("\n   📝 属性定義:")
        for attr in attribute_definitions:
            attr_name = attr['AttributeName']
            attr_type = attr['AttributeType']  # S (文字列), N (数値), B (バイナリ)
            print(f"      {attr_name}: {attr_type}")
        
        # サンプルデータを取得
        response = table.scan(Limit=5)
        items = response['Items']
        
        if items:
            print(f"\n📊 取得データ: {len(items)}件")
            print("\n📋 サンプルデータの構造:")
            
            for i, item in enumerate(items, 1):
                print(f"\n   {i}. アイテム {i}:")
                for key, value in item.items():
                    print(f"      {key}: {value} (型: {type(value).__name__})")
            
            # 共通のキーを確認
            all_keys = set()
            for item in items:
                all_keys.update(item.keys())
            
            print(f"\n📋 全キー一覧: {sorted(list(all_keys))}")
            
            # プライマリキーの候補を特定
            print(f"\n🔑 プライマリキー候補:")
            primary_key_candidates = [key['AttributeName'] for key in key_schema]
            for key in primary_key_candidates:
                if key in all_keys:
                    print(f"   ✅ {key}: 存在")
                else:
                    print(f"   ❌ {key}: 存在しない")
                    
        else:
            print("❌ VaultMetaテーブルにデータがありません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")

def debug_pool_meta_structure():
    """PoolMetaテーブルの構造をデバッグ表示"""
    tool = DynamoDBCleanupTool()
    
    if not tool.connection_status:
        print("❌ DynamoDBに接続できません")
        return
    
    print("🔍 PoolMetaテーブル構造デバッグ")
    print("="*50)
    
    try:
        table = tool.dynamodb.Table('PoolMeta')
        
        # テーブルスキーマ情報を取得
        print("📋 テーブルスキーマ情報:")
        table_info = table.meta.client.describe_table(TableName='PoolMeta')
        key_schema = table_info['Table']['KeySchema']
        
        print("   🔑 キースキーマ:")
        for key in key_schema:
            key_name = key['AttributeName']
            key_type = key['KeyType']  # HASH (パーティションキー) または RANGE (ソートキー)
            print(f"      {key_name}: {key_type}")
        
        # 属性定義を取得
        attribute_definitions = table_info['Table']['AttributeDefinitions']
        print("\n   📝 属性定義:")
        for attr in attribute_definitions:
            attr_name = attr['AttributeName']
            attr_type = attr['AttributeType']  # S (文字列), N (数値), B (バイナリ)
            print(f"      {attr_name}: {attr_type}")
        
        # サンプルデータを取得
        response = table.scan(Limit=5)
        items = response['Items']
        
        if items:
            print(f"\n📊 取得データ: {len(items)}件")
            print("\n📋 サンプルデータの構造:")
            
            for i, item in enumerate(items, 1):
                print(f"\n   {i}. アイテム {i}:")
                for key, value in item.items():
                    print(f"      {key}: {value} (型: {type(value).__name__})")
            
            # 共通のキーを確認
            all_keys = set()
            for item in items:
                all_keys.update(item.keys())
            
            print(f"\n📋 全キー一覧: {sorted(list(all_keys))}")
            
            # プライマリキーの候補を特定
            print(f"\n🔑 プライマリキー候補:")
            primary_key_candidates = [key['AttributeName'] for key in key_schema]
            for key in primary_key_candidates:
                if key in all_keys:
                    print(f"   ✅ {key}: 存在")
                else:
                    print(f"   ❌ {key}: 存在しない")
                    
        else:
            print("❌ PoolMetaテーブルにデータがありません")
            
    except Exception as e:
        print(f"❌ エラー: {e}")

# セル4: 実行コマンド例
print("🚀 DynamoDB Google Colab用クリーンアップツール準備完了!")
print("\n📋 利用可能なコマンド:")
print("   - show_table_overview()              # テーブル概要表示")
print("   - preview_latest_cleanup()           # 最新データ保持クリーンアップ プレビュー")
print("   - execute_latest_cleanup()           # 最新データ保持クリーンアップ 実行")
print("   - execute_full_cleanup()             # 全データ削除 実行（⚠️危険⚠️）")
print("   - create_cleanup_comparison()        # クリーンアップ前後の比較チャート")
print("   - execute_poolmeta_delete()          # PoolMetaテーブル全件削除 実行")
print("   - execute_vaultmeta_delete()         # VaultMetaテーブル全件削除 実行")
print("   - execute_token_price_history_delete() # TokenPriceHistoryテーブル全件削除 実行")
print("   - execute_token_ohlc_daily_delete()   # TokenOHLCDailyテーブル全件削除 実行")
print("   - execute_usdjpy_history_delete()     # USDJPYHistoryテーブル全件削除 実行")
print("   - execute_usdjpy_ohlc_daily_delete() # USDJPYOHLCDailyテーブル全件削除 実行")
print("   - debug_vault_meta_structure()       # VaultMetaテーブル構造デバッグ")
print("   - debug_pool_meta_structure()        # PoolMetaテーブル構造デバッグ")
print("\n🎯 プール個別削除機能:")
print("   - show_pool_list()                   # プール一覧表示")
print("   - delete_single_pool(pool_id)       # 個別プール削除実行")
print("   - delete_multiple_pools(pool_ids)   # 複数プール一括削除実行")
print("\n🗂️ テーブル個別削除機能:")
print("   - show_table_list()                 # テーブル一覧表示")
print("   - delete_single_table(table_name)   # 個別テーブル全件削除実行")
print("   - delete_multiple_tables(table_names) # 複数テーブル一括削除実行")
print("\n💡 推奨使用順序:")
print("   1. show_table_overview()             # 現在の状況確認")
print("   2. preview_latest_cleanup()          # 削除予定確認")
print("   3. execute_latest_cleanup()          # クリーンアップ実行")
print("   4. create_cleanup_comparison()       # 結果確認")
print("\n🗑️ メタデータテーブル削除:")
print("   - execute_poolmeta_delete()          # PoolMetaテーブル全件削除")
print("   - execute_vaultmeta_delete()         # VaultMetaテーブル全件削除")
print("\n📊 価格履歴テーブル削除:")
print("   - execute_token_price_history_delete() # TokenPriceHistoryテーブル全件削除")
print("   - execute_token_ohlc_daily_delete()   # TokenOHLCDailyテーブル全件削除")
print("   - execute_usdjpy_history_delete()     # USDJPYHistoryテーブル全件削除")
print("   - execute_usdjpy_ohlc_daily_delete() # USDJPYOHLCDailyテーブル全件削除")
print("\n🎯 プール個別削除の使用例:")
print("   # プール一覧を表示")
print("   pools = show_pool_list()")
print("   ")
print("   # 個別プールを削除")
print("   delete_single_pool('pool_123')")
print("   ")
print("   # 複数プールを一括削除")
print("   pool_ids = ['pool_123', 'pool_456', 'pool_789']")
print("   delete_multiple_pools(pool_ids)")
print("\n🗂️ テーブル個別削除の使用例:")
print("   # テーブル一覧を表示")
print("   tables = show_table_list()")
print("   ")
print("   # 個別テーブルを全件削除")
print("   delete_single_table('PoolLatest')")
print("   ")
print("   # 複数テーブルを一括削除")
print("   table_names = ['PoolLatest', 'ConvexPoolMetrics']")
print("   delete_multiple_tables(table_names)")
print("\n⚠️ 安全機能:")
print("   - 最新データは必ず保持")
print("   - PoolLatest: 最新のupdated_atを持つデータのみ保持")
print("   - プレビューで削除対象を事前確認")
print("   - バッチ削除で効率的な処理")
print("   - 削除実行前にy/N確認プロンプト")
print("\n🔧 修正内容:")
print("   - 本番・テストの判別を削除")
print("   - convex_ec2_complete.py統一版に対応")
print("   - PoolLatestは最新のupdated_atで判定")
print("   - PoolMeta・VaultMetaテーブル対応追加")
print("   - PoolMeta・VaultMeta専用全件削除機能追加")
print("   - 削除実行前に確認プロンプトを追加")
print("   - プライマリキーの動的特定機能追加（vault_id/id/name/symbol対応）")
print("   - エラーハンドリング改善（利用可能キー表示）")
print("   - VaultMetaテーブル構造デバッグ機能追加")
print("   - VaultMetaテーブル再作成対応（vault_idがプライマリキー）")
print("   - DeletionTrackingLogsテーブルへの追跡機能統合")
print("   - PoolMeta・VaultMeta削除操作の完全追跡")
print("   - 削除開始・完了・エラーの各段階でログ記録")
print("   - 呼び出し元情報と詳細メタデータの記録")
