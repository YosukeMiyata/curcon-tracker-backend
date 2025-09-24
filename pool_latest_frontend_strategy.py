#!/usr/bin/env python3
"""
PoolLatestデータのフロントエンド表示戦略
アクティブ・非アクティブプールの適切な表示
"""

import boto3
from datetime import datetime, timezone
from collections import defaultdict

class PoolLatestFrontendStrategy:
    def __init__(self):
        """フロントエンド表示戦略の初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table('PoolLatest')
            self.connection_status = True
            print("✅ DynamoDB接続成功")
        except Exception as e:
            print(f"❌ DynamoDB接続エラー: {e}")
            self.connection_status = False

    def get_pools_for_frontend(self):
        """フロントエンド用のプールデータを取得"""
        if not self.connection_status:
            return []

        try:
            # 全データを取得
            response = self.table.scan()
            all_items = response['Items']

            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                all_items.extend(response['Items'])

            # 最新タイムスタンプを特定
            latest_timestamp = max(item.get('updated_at', item.get('timestamp', '')) 
                                 for item in all_items if item.get('updated_at', item.get('timestamp', '')))

            # プールを分類
            active_pools = []
            inactive_pools = []

            for item in all_items:
                updated_at = item.get('updated_at', item.get('timestamp', ''))
                is_active = updated_at == latest_timestamp
                
                pool_data = {
                    'pool_id': item.get('pool_id', ''),
                    'pool_name': item.get('Pool', ''),
                    'current_vapr': item.get('Current_vAPR', ''),
                    'projected_vapr': item.get('Projected_vAPR', ''),
                    'vecrv_boost': item.get('veCRV_boost', ''),
                    'remarks': item.get('Remarks', ''),
                    'tvl': item.get('TVL', ''),
                    'updated_at': updated_at,
                    'is_active': is_active,
                    'status': 'アクティブ' if is_active else '非アクティブ'
                }

                if is_active:
                    active_pools.append(pool_data)
                else:
                    inactive_pools.append(pool_data)

            # アクティブプールをAPR順でソート
            active_pools.sort(key=lambda x: self.parse_apr(x['current_vapr']), reverse=True)
            
            # 非アクティブプールを最終更新日時順でソート（新しい順）
            inactive_pools.sort(key=lambda x: x['updated_at'], reverse=True)

            # 結合: アクティブ + 非アクティブ
            all_pools = active_pools + inactive_pools

            return all_pools

        except Exception as e:
            print(f"❌ データ取得エラー: {e}")
            return []

    def parse_apr(self, apr_str):
        """APR文字列を数値に変換"""
        try:
            if isinstance(apr_str, str):
                # パーセント記号とカンマを除去
                cleaned = apr_str.replace('%', '').replace(',', '').replace('$', '')
                return float(cleaned)
            return float(apr_str)
        except:
            return 0.0

    def display_pools_preview(self, limit=20):
        """プールデータのプレビュー表示"""
        pools = self.get_pools_for_frontend()
        
        if not pools:
            print("❌ データが取得できません")
            return

        print(f"📊 フロントエンド表示用プールデータ (全{len(pools)}件)")
        print("=" * 80)

        # アクティブ・非アクティブの統計
        active_count = sum(1 for p in pools if p['is_active'])
        inactive_count = len(pools) - active_count

        print(f"✅ アクティブプール: {active_count}件")
        print(f"📋 非アクティブプール: {inactive_count}件")
        print()

        # 表示サンプル
        for i, pool in enumerate(pools[:limit], 1):
            status_icon = "🟢" if pool['is_active'] else "🔴"
            print(f"{i:2d}. {status_icon} {pool['pool_name']}")
            print(f"    プールID: {pool['pool_id']}")
            print(f"    現在APR: {pool['current_vapr']}")
            print(f"    予想APR: {pool['projected_vapr']}")
            print(f"    状態: {pool['status']}")
            print(f"    最終更新: {pool['updated_at']}")
            print()

        if len(pools) > limit:
            print(f"... 他 {len(pools) - limit}件")

    def generate_frontend_json(self):
        """フロントエンド用のJSONデータを生成"""
        pools = self.get_pools_for_frontend()
        
        if not pools:
            return None

        # フロントエンド用の構造化データ
        frontend_data = {
            'total_pools': len(pools),
            'active_pools': sum(1 for p in pools if p['is_active']),
            'inactive_pools': sum(1 for p in pools if not p['is_active']),
            'last_updated': max(p['updated_at'] for p in pools),
            'pools': pools
        }

        return frontend_data

    def suggest_frontend_implementation(self):
        """フロントエンド実装の提案"""
        print("\n💡 フロントエンド実装の提案")
        print("=" * 60)

        print("1. データ表示順序:")
        print("   - アクティブプール（APR順）")
        print("   - 非アクティブプール（最終更新日時順）")

        print("\n2. UI表示:")
        print("   - アクティブ: 通常の色で表示")
        print("   - 非アクティブ: グレーアウトまたは別セクション")

        print("\n3. フィルタリング:")
        print("   - アクティブのみ表示")
        print("   - 非アクティブのみ表示")
        print("   - 全表示")

        print("\n4. ソート機能:")
        print("   - APR順（デフォルト）")
        print("   - プール名順")
        print("   - 最終更新日時順")

        print("\n5. データ更新:")
        print("   - 定期的なデータ取得")
        print("   - リアルタイム更新（WebSocket等）")

    def create_sample_api_response(self):
        """サンプルAPIレスポンスを作成"""
        frontend_data = self.generate_frontend_json()
        
        if not frontend_data:
            return None

        # サンプルAPIレスポンス
        api_response = {
            "status": "success",
            "data": frontend_data,
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0"
            }
        }

        return api_response

def main():
    """メイン実行関数"""
    strategy = PoolLatestFrontendStrategy()
    
    if not strategy.connection_status:
        return

    # 1. プールデータのプレビュー
    strategy.display_pools_preview(15)
    
    # 2. フロントエンド実装提案
    strategy.suggest_frontend_implementation()
    
    # 3. サンプルAPIレスポンス
    api_response = strategy.create_sample_api_response()
    if api_response:
        print("\n📋 サンプルAPIレスポンス:")
        print(f"   総プール数: {api_response['data']['total_pools']}")
        print(f"   アクティブ: {api_response['data']['active_pools']}")
        print(f"   非アクティブ: {api_response['data']['inactive_pools']}")

if __name__ == "__main__":
    main()
