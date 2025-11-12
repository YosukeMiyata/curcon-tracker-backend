#!/usr/bin/env python3
# =====================================
# TokenOHLCDailyテーブルの内容を確認するスクリプト
# =====================================

import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta
from collections import defaultdict

def check_token_ohlc_daily():
    """TokenOHLCDailyテーブルの内容を確認"""
    dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
    table = dynamodb.Table('TokenOHLCDaily')
    
    print("🔍 TokenOHLCDailyテーブルの内容を確認中...")
    print("=" * 60)
    
    # CRVとCVXのデータを取得
    tokens = ['CRV', 'CVX']
    
    for token in tokens:
        print(f"\n📊 {token}のデータ:")
        print("-" * 60)
        
        try:
            # Queryを使用してtokenでフィルタリング
            response = table.query(
                KeyConditionExpression=Key('token').eq(token)
            )
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = table.query(
                    KeyConditionExpression=Key('token').eq(token),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))
            
            # 日付順にソート
            items.sort(key=lambda x: x.get('timestamp', ''))
            
            print(f"合計: {len(items)}件")
            
            if items:
                print(f"\n最初の日付: {items[0].get('timestamp')}")
                print(f"最後の日付: {items[-1].get('timestamp')}")
                
                # 日付ごとにグループ化
                dates = [item.get('timestamp') for item in items]
                unique_dates = sorted(set(dates))
                
                print(f"\n日付範囲: {unique_dates[0]} ～ {unique_dates[-1]}")
                print(f"ユニークな日付数: {len(unique_dates)}")
                
                # 最初の10件と最後の10件を表示
                print("\n最初の10件:")
                for item in items[:10]:
                    print(f"  {item.get('timestamp')}: Open={item.get('open')}, High={item.get('high')}, Low={item.get('low')}, Close={item.get('close')}")
                
                if len(items) > 10:
                    print("\n最後の10件:")
                    for item in items[-10:]:
                        print(f"  {item.get('timestamp')}: Open={item.get('open')}, High={item.get('high')}, Low={item.get('low')}, Close={item.get('close')}")
                
                # 2025-10-14以前のデータを確認
                early_dates = [d for d in unique_dates if d < '2025-10-14']
                if early_dates:
                    print(f"\n✅ 2025-10-14以前のデータ: {len(early_dates)}件")
                    print(f"日付: {', '.join(early_dates)}")
                    print("\n詳細:")
                    for date in early_dates:
                        item = next((i for i in items if i.get('timestamp') == date), None)
                        if item:
                            print(f"  {date}: Open={item.get('open')}, High={item.get('high')}, Low={item.get('low')}, Close={item.get('close')}, Source={item.get('data_source', 'N/A')}")
                else:
                    print("\n❌ 2025-10-14以前のデータは見つかりませんでした")
                
                # 2025-10-31までのデータを確認
                target_dates = [d for d in unique_dates if d <= '2025-10-31']
                print(f"\n📅 2025-10-31までのデータ: {len(target_dates)}件")
                if len(target_dates) < 33:
                    missing = []
                    expected_start = datetime(2025, 9, 29)
                    for i in range(33):
                        expected_date = (expected_start + timedelta(days=i)).strftime('%Y-%m-%d')
                        if expected_date not in unique_dates:
                            missing.append(expected_date)
                    if missing:
                        print(f"⚠️ 欠落している日付 ({len(missing)}件): {', '.join(missing[:10])}{'...' if len(missing) > 10 else ''}")
                
            else:
                print("データが見つかりませんでした")
                
        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    check_token_ohlc_daily()

