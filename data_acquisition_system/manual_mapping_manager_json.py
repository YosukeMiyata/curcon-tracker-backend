#!/usr/bin/env python3
"""
人力対応表管理スクリプト（JSONファイル版）
manual_pool_mapping.jsonとfailed_pool_matching.jsonを管理
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class ManualMappingManagerJSON:
    def __init__(self):
        """初期化"""
        self.base_path = Path("/home/ubuntu/convex-scraper")
        self.manual_mapping_file = self.base_path / "manual_pool_mapping.json"
        self.failed_matching_file = self.base_path / "failed_pool_matching.json"
    
    def add_mapping(self, pool_name, factory_id, description="", valid_days=None):
        """人力対応表にマッピングを追加"""
        try:
            # 既存の人力対応表を読み込み
            mappings = {}
            if self.manual_mapping_file.exists():
                with open(self.manual_mapping_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
            
            # 新しいマッピングを追加
            mappings[pool_name] = {
                'factory_id': factory_id,
                'description': description,
                'created_at': datetime.now().isoformat(),
                'created_by': 'manual',
                'status': 'active'
            }
            
            if valid_days:
                valid_until = datetime.now() + timedelta(days=valid_days)
                mappings[pool_name]['valid_until'] = valid_until.isoformat()
            
            # JSONファイルに保存
            with open(self.manual_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 人力対応表に追加: {pool_name} -> {factory_id}")
            return True
            
        except Exception as e:
            print(f"❌ 追加エラー: {e}")
            return False
    
    def list_failed_pools(self, status='pending'):
        """マッチング失敗プールの一覧を表示"""
        try:
            if not self.failed_matching_file.exists():
                print("📋 失敗プールファイルが存在しません")
                return []
            
            with open(self.failed_matching_file, 'r', encoding='utf-8') as f:
                failed_pools = json.load(f)
            
            print(f"\n📋 マッチング失敗プール一覧 (status: {status})")
            print("=" * 80)
            
            count = 0
            for pool_name, pool_data in failed_pools.items():
                if pool_data.get('status', 'pending') == status:
                    token_symbols = pool_data.get('token_symbols', [])
                    failure_count = pool_data.get('failure_count', 0)
                    first_seen = pool_data.get('first_seen', '')
                    last_seen = pool_data.get('last_seen', '')
                    
                    print(f"プール名: {pool_name}")
                    print(f"  トークン: {token_symbols}")
                    print(f"  失敗回数: {failure_count}")
                    print(f"  初回発見: {first_seen}")
                    print(f"  最終発見: {last_seen}")
                    print("-" * 40)
                    count += 1
            
            print(f"合計: {count}件")
            return failed_pools
            
        except Exception as e:
            print(f"❌ 取得エラー: {e}")
            return {}
    
    def mark_resolved(self, pool_name):
        """失敗プールを解決済みとしてマーク"""
        try:
            if not self.failed_matching_file.exists():
                print("❌ 失敗プールファイルが存在しません")
                return False
            
            with open(self.failed_matching_file, 'r', encoding='utf-8') as f:
                failed_pools = json.load(f)
            
            if pool_name in failed_pools:
                failed_pools[pool_name]['status'] = 'resolved'
                failed_pools[pool_name]['resolved_at'] = datetime.now().isoformat()
                
                with open(self.failed_matching_file, 'w', encoding='utf-8') as f:
                    json.dump(failed_pools, f, ensure_ascii=False, indent=2)
                
                print(f"✅ 解決済みマーク: {pool_name}")
                return True
            else:
                print(f"❌ プールが見つかりません: {pool_name}")
                return False
                
        except Exception as e:
            print(f"❌ 更新エラー: {e}")
            return False
    
    def bulk_add_from_failed(self, mappings):
        """失敗プールから一括で人力対応表に追加"""
        success_count = 0
        
        for mapping in mappings:
            pool_name = mapping.get('pool_name')
            factory_id = mapping.get('factory_id')
            description = mapping.get('description', '')
            
            if self.add_mapping(pool_name, factory_id, description):
                self.mark_resolved(pool_name)
                success_count += 1
        
        print(f"✅ 一括追加完了: {success_count}件")
        return success_count
    
    def show_manual_mappings(self):
        """人力対応表の内容を表示"""
        try:
            if not self.manual_mapping_file.exists():
                print("📋 人力対応表ファイルが存在しません")
                return {}
            
            with open(self.manual_mapping_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            
            print(f"\n📋 人力対応表一覧")
            print("=" * 80)
            
            for pool_name, mapping in mappings.items():
                # シンプル形式（文字列）か詳細形式（オブジェクト）かを判定
                if isinstance(mapping, str):
                    # シンプル形式: "pool_name": "factory_id"
                    factory_id = mapping
                    description = "（シンプル形式）"
                    status = "active"
                    created_at = ""
                else:
                    # 詳細形式: "pool_name": {"factory_id": "...", "status": "...", ...}
                    factory_id = mapping.get('factory_id', '')
                    description = mapping.get('description', '')
                    status = mapping.get('status', 'active')
                    created_at = mapping.get('created_at', '')
                
                print(f"プール名: {pool_name}")
                print(f"  factory_id: {factory_id}")
                print(f"  説明: {description}")
                print(f"  ステータス: {status}")
                if created_at:
                    print(f"  作成日時: {created_at}")
                print("-" * 40)
            
            print(f"合計: {len(mappings)}件")
            return mappings
            
        except Exception as e:
            print(f"❌ 取得エラー: {e}")
            return {}

def main():
    """メイン関数"""
    manager = ManualMappingManagerJSON()
    
    print("🔧 人力対応表管理ツール（JSON版）")
    print("=" * 50)
    
    while True:
        print("\n選択してください:")
        print("1. マッチング失敗プール一覧表示")
        print("2. 人力対応表一覧表示")
        print("3. 人力対応表に追加")
        print("4. 失敗プールを解決済みマーク")
        print("5. 一括追加（JSON形式）")
        print("6. ファイルの場所を表示")
        print("7. 終了")
        
        choice = input("\n選択 (1-7): ").strip()
        
        if choice == '1':
            status = input("ステータス (pending/resolved/ignored) [pending]: ").strip() or 'pending'
            manager.list_failed_pools(status)
        
        elif choice == '2':
            manager.show_manual_mappings()
        
        elif choice == '3':
            pool_name = input("プール名: ").strip()
            factory_id = input("factory_id: ").strip()
            description = input("説明 (任意): ").strip()
            valid_days = input("有効期限（日数、任意）: ").strip()
            
            if pool_name and factory_id:
                valid_days = int(valid_days) if valid_days.isdigit() else None
                manager.add_mapping(pool_name, factory_id, description, valid_days)
            else:
                print("❌ プール名とfactory_idは必須です")
        
        elif choice == '4':
            pool_name = input("プール名: ").strip()
            if pool_name:
                manager.mark_resolved(pool_name)
            else:
                print("❌ プール名は必須です")
        
        elif choice == '5':
            print("JSON形式で入力してください:")
            print('例: [{"pool_name": "ETH+USDC", "factory_id": "factory-crypto-1", "description": "手動追加"}]')
            json_input = input("JSON: ").strip()
            
            try:
                mappings = json.loads(json_input)
                if isinstance(mappings, list):
                    manager.bulk_add_from_failed(mappings)
                else:
                    print("❌ 配列形式で入力してください")
            except json.JSONDecodeError:
                print("❌ 無効なJSON形式です")
        
        elif choice == '6':
            print(f"\n📁 ファイルの場所:")
            print(f"  人力対応表: {manager.manual_mapping_file}")
            print(f"  失敗プール: {manager.failed_matching_file}")
            
            if manager.manual_mapping_file.exists():
                print(f"  人力対応表サイズ: {manager.manual_mapping_file.stat().st_size} bytes")
            if manager.failed_matching_file.exists():
                print(f"  失敗プールサイズ: {manager.failed_matching_file.stat().st_size} bytes")
        
        elif choice == '7':
            print("👋 終了します")
            break
        
        else:
            print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
