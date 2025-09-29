# Google Colab用: シンプル版 Pool : factory_id 表示
# 使用方法: Google Colabでこのセルを実行

import boto3
import os

# AWS認証情報は別セルで設定済みと仮定

def show_pool_factory_mapping():
    """Pool : factory_id のマッピングを表示"""
    try:
        # DynamoDBからデータ取得
        dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        table = dynamodb.Table('PoolLatest')
        
        response = table.scan()
        items = response['Items']
        
        # ページネーション対応
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        print(f"📊 PoolLatestテーブル: {len(items)}件のデータ")
        print("="*60)
        
        # 全プールを表示（factory_idが空の場合は空文字列）
        all_pools = []
        for item in items:
            pool_name = item.get('Pool', '')
            factory_id = item.get('factory_id', '')
            if factory_id == 'N/A' or not factory_id:
                factory_id = ''
            all_pools.append(f'"{pool_name}" : "{factory_id}"')
        
        # ソートして表示（空文字列は最後に）
        all_pools.sort(key=lambda x: (x.endswith('" : ""'), x))
        
        for mapping in all_pools:
            print(mapping)
        
        # 統計計算
        with_factory_id = len([p for p in all_pools if not p.endswith('" : ""')])
        without_factory_id = len([p for p in all_pools if p.endswith('" : ""')])
        
        print(f"\n📈 統計:")
        print(f"   - factory_id付き: {with_factory_id}件")
        print(f"   - factory_id空欄: {without_factory_id}件")
        print(f"   - 成功率: {with_factory_id/len(items)*100:.1f}%")
        
    except Exception as e:
        print(f"❌ エラー: {e}")

# 実行方法:
# show_pool_factory_mapping()  # 何度でも実行可能
