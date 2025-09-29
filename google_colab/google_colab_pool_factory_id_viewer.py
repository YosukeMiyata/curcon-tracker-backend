# Google Colab用: PoolLatestテーブルのPoolとfactory_id表示ツール
# 使用方法: Google Colabでこのセルを実行

import boto3
import pandas as pd
from datetime import datetime, timezone
import json

# AWS認証情報は別セルで設定済みと仮定

def get_pool_latest_data():
    """PoolLatestテーブルからデータを取得"""
    try:
        print("📊 PoolLatestテーブルからデータを取得中...")
        
        # DynamoDBクライアント作成
        dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        table = dynamodb.Table('PoolLatest')
        
        # 全データをスキャン
        response = table.scan()
        items = response['Items']
        
        # ページネーション対応
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        print(f"✅ {len(items)}件のデータを取得しました")
        return items
        
    except Exception as e:
        print(f"❌ データ取得エラー: {e}")
        return []

def display_pool_factory_mapping(items):
    """Poolとfactory_idのマッピングを表示"""
    if not items:
        print("❌ 表示するデータがありません")
        return
    
    print("\n" + "="*80)
    print("📋 PoolLatestテーブル: Pool : factory_id マッピング")
    print("="*80)
    
    # データを整理
    pool_factory_data = []
    for item in items:
        pool_name = item.get('Pool', 'N/A')
        factory_id = item.get('factory_id', 'N/A')
        
        # factory_idが空の場合は空文字列に設定
        if factory_id == 'N/A' or not factory_id:
            factory_id = ''
        
        pool_factory_data.append({
            'Pool': pool_name,
            'factory_id': factory_id,
            'mapping': f'"{pool_name}" : "{factory_id}",'
        })
    
    # factory_idでソート（空文字列は最後に）
    pool_factory_data.sort(key=lambda x: (x['factory_id'] == '', x['factory_id']))
    
    # 表示
    for data in pool_factory_data:
        print(data['mapping'])
    
    # factory_id付きと空欄の数を計算
    with_factory_id = len([d for d in pool_factory_data if d['factory_id']])
    without_factory_id = len([d for d in pool_factory_data if not d['factory_id']])
    
    print(f"\n📊 統計情報:")
    print(f"   - 総プール数: {len(items)}件")
    print(f"   - factory_id付きプール数: {with_factory_id}件")
    print(f"   - factory_id空欄プール数: {without_factory_id}件")
    print(f"   - マッチング成功率: {with_factory_id/len(items)*100:.1f}%")

def display_factory_id_statistics(items):
    """factory_idの統計情報を表示"""
    if not items:
        return
    
    print("\n" + "="*80)
    print("📊 factory_id統計情報")
    print("="*80)
    
    # factory_idの集計
    factory_id_count = {}
    no_factory_id_count = 0
    
    for item in items:
        factory_id = item.get('factory_id', '')
        if factory_id and factory_id != 'N/A':
            factory_id_count[factory_id] = factory_id_count.get(factory_id, 0) + 1
        else:
            no_factory_id_count += 1
    
    # 統計表示
    print(f"📈 factory_id別プール数:")
    for factory_id, count in sorted(factory_id_count.items()):
        print(f"   {factory_id}: {count}件")
    
    print(f"\n📉 未マッチングプール数: {no_factory_id_count}件")
    print(f"📊 重複factory_id数: {len([c for c in factory_id_count.values() if c > 1])}件")

def display_unmatched_pools(items):
    """factory_idが未設定のプールを表示"""
    if not items:
        return
    
    print("\n" + "="*80)
    print("❌ factory_id未設定プール一覧")
    print("="*80)
    
    unmatched_pools = []
    for item in items:
        factory_id = item.get('factory_id', '')
        if not factory_id or factory_id == 'N/A':
            pool_name = item.get('Pool', 'N/A')
            unmatched_pools.append(pool_name)
    
    if unmatched_pools:
        for pool_name in sorted(unmatched_pools):
            print(pool_name)
        print(f"\n📊 未マッチングプール数: {len(unmatched_pools)}件")
    else:
        print("✅ すべてのプールにfactory_idが設定されています！")

def export_to_csv(items):
    """データをCSVファイルとしてエクスポート"""
    if not items:
        print("❌ エクスポートするデータがありません")
        return
    
    try:
        # データをDataFrameに変換
        df_data = []
        for item in items:
            df_data.append({
                'Pool': item.get('Pool', ''),
                'factory_id': item.get('factory_id', ''),
                'token_symbols': str(item.get('token_symbols', [])),
                'normalized_name': item.get('normalized_name', ''),
                'search_tokens': str(item.get('search_tokens', [])),
                'is_vault': item.get('is_vault', False),
                'Current_vAPR': item.get('Current_vAPR', ''),
                'Projected_vAPR': item.get('Projected_vAPR', ''),
                'TVL': item.get('TVL', ''),
                'timestamp': item.get('timestamp', '')
            })
        
        df = pd.DataFrame(df_data)
        
        # CSVファイルとして保存
        filename = f"pool_latest_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8')
        
        print(f"✅ データをCSVファイルにエクスポートしました: {filename}")
        print(f"📊 エクスポート件数: {len(df)}件")
        
        return filename
        
    except Exception as e:
        print(f"❌ CSVエクスポートエラー: {e}")
        return None

def main():
    """メイン実行関数"""
    print("🚀 Google Colab用 PoolLatestテーブル表示ツール")
    print("="*60)
    
    # データ取得
    items = get_pool_latest_data()
    
    if not items:
        print("❌ データの取得に失敗しました")
        return
    
    # メニュー表示
    while True:
        print("\n" + "="*60)
        print("📋 メニュー")
        print("1. Pool : factory_id マッピング表示")
        print("2. factory_id統計情報表示")
        print("3. 未マッチングプール表示")
        print("4. CSVファイルエクスポート")
        print("5. 全表示")
        print("0. 終了")
        print("="*60)
        
        choice = input("選択してください (0-5): ").strip()
        
        if choice == '1':
            display_pool_factory_mapping(items)
        elif choice == '2':
            display_factory_id_statistics(items)
        elif choice == '3':
            display_unmatched_pools(items)
        elif choice == '4':
            export_to_csv(items)
        elif choice == '5':
            display_pool_factory_mapping(items)
            display_factory_id_statistics(items)
            display_unmatched_pools(items)
        elif choice == '0':
            print("👋 終了します")
            break
        else:
            print("❌ 無効な選択です")

# 実行
if __name__ == "__main__":
    main()
