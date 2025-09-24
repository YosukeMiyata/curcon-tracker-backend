#!/usr/bin/env python3
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
from decimal import Decimal
import time
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

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
            KeyConditionExpression=Key('stake').eq('cvxCRV'),
            ScanIndexForward=False
        )
        
        items = response['Items']
        if len(items) > 1:
            old_items = items[1:]
            deleted_count = 0
            
            for item in old_items:
                table.delete_item(Key={
                    'stake': item['stake'],
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
        response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
        timestamps = [item['timestamp'] for item in response['Items']]
        
        if timestamps:
            latest_timestamp = max(timestamps)
            response = table.scan(FilterExpression=Attr('timestamp').ne(latest_timestamp))
            old_items = response['Items']
            
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
        response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
        timestamps = [item['timestamp'] for item in response['Items']]
        
        if timestamps:
            latest_timestamp = max(timestamps)
            response = table.scan(FilterExpression=Attr('timestamp').ne(latest_timestamp))
            old_items = response['Items']
            
            deleted_count = 0
            for item in old_items:
                table.delete_item(Key={
                    'asset': item['asset'],
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
        all_items = response['Items']
        
        if all_items:
            items_with_time = []
            for item in all_items:
                updated_at = item.get('updated_at', item.get('timestamp', ''))
                if updated_at:
                    items_with_time.append((item, updated_at))
            
            if items_with_time:
                latest_time = max(items_with_time, key=lambda x: x[1])[1]
                items_to_delete = [item for item, time in items_with_time if time != latest_time]
                
                deleted_count = 0
                for item in items_to_delete:
                    table.delete_item(Key={'pool_id': item['pool_id']})
                    deleted_count += 1
                
                if confirm:
                    print(f"✅ プール最新データ: {deleted_count}件削除")
                return deleted_count
        return 0
    
    def get_table_overview(self):
        """テーブル概要表示"""
        print("📊 DynamoDBテーブル概要")
        print("=" * 60)
        
        for table_name, table in self.tables.items():
            try:
                response = table.scan(Select='COUNT')
                count = response['Count']
                
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        Select='COUNT',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    count += response['Count']
                
                print(f"📈 {table_name}: {count:,}件")
            except Exception as e:
                print(f"❌ {table_name}: エラー ({e})")
    
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
