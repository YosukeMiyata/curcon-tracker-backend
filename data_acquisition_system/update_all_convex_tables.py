#!/usr/bin/env python3
"""
全てのConvex関連テーブルのfactory_idを更新するスクリプト
対象テーブル: PoolLatest, ConvexPoolHistory, ConvexPoolOHLCDaily, ConvexPoolRemarksHistory
"""

import boto3
import json
import os
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from dotenv import load_dotenv
from pathlib import Path

# .envファイルを読み込み
load_dotenv()


class ConvexTablesUpdater:
    def __init__(self):
        """初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        
        # 対象テーブル
        self.table_names = [
            'PoolLatest',
            'ConvexPoolHistory',
            'ConvexPoolOHLCDaily',
            'ConvexPoolRemarksHistory'
        ]
        
        self.tables = {}
        for table_name in self.table_names:
            self.tables[table_name] = self.dynamodb.Table(table_name)
        
        # manual_pool_mapping.jsonを読み込み
        self.manual_mapping = self.load_manual_mapping()
        
        print(f"✅ 初期化完了")
        print(f"📋 対象テーブル: {', '.join(self.table_names)}")
        print(f"📋 人力対応表エントリ数: {len(self.manual_mapping)}")

    def load_manual_mapping(self):
        """manual_pool_mapping.jsonを読み込み"""
        mapping_file = Path("/home/ubuntu/convex-scraper/manual_pool_mapping.json")
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def normalize_text(self, text):
        """テキストを正規化（ゼロ幅スペースなどを除去）"""
        if not text:
            return ""
        # ゼロ幅スペース（U+200B）を除去
        normalized = text.replace('\u200b', '')
        # その他の不可視文字も除去
        normalized = normalized.replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
        return normalized.strip()

    def find_factory_id_for_pool(self, pool_name):
        """プール名からfactory_idを検索"""
        if not pool_name:
            return None
        
        # プール名を正規化
        normalized_pool_name = self.normalize_text(pool_name)
        
        # 1. 完全一致を試みる
        if normalized_pool_name in self.manual_mapping:
            return self.manual_mapping[normalized_pool_name]
        
        # 2. 元のプール名でも試す
        if pool_name in self.manual_mapping:
            return self.manual_mapping[pool_name]
        
        # 3. 正規化したキーで検索
        for mapping_name, factory_id in self.manual_mapping.items():
            normalized_mapping_name = self.normalize_text(mapping_name)
            if normalized_mapping_name == normalized_pool_name:
                return factory_id
        
        return None

    def scan_table_items(self, table_name):
        """テーブルの全データを取得"""
        table = self.tables[table_name]
        items = []
        
        print(f"\n📊 {table_name}テーブルをスキャン中...")
        
        try:
            response = table.scan()
            items.extend(response.get('Items', []))
            
            # ページネーション処理
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            print(f"   ✅ {len(items)}件のアイテムを取得")
            return items
            
        except Exception as e:
            print(f"   ❌ スキャンエラー: {e}")
            return []

    def update_table_items(self, table_name, items):
        """テーブルのアイテムを更新"""
        table = self.tables[table_name]
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        # factory_idが空のアイテムのみを対象
        items_to_update = [item for item in items if not item.get('factory_id')]
        
        print(f"\n🔄 {table_name}テーブルを更新中...")
        print(f"   対象アイテム数: {len(items_to_update)}件")
        
        for item in items_to_update:
            # pool_nameを取得（テーブルによってキー名が異なる）
            pool_name = item.get('Pool') or item.get('pool_name')
            pool_id = item.get('pool_id')
            pool_id_type = item.get('pool_id_type')
            
            if not pool_name and not pool_id and not pool_id_type:
                print(f"   ⚠️ スキップ: 識別子なし (Item: {item})")
                skipped_count += 1
                continue
            
            # factory_idを検索（pool_nameがあればそれを使用、なければpool_idから推測）
            # pool_id_typeがある場合 (例: "pool_id#type") はpool_id部分を抽出
            if pool_name:
                search_name = pool_name
            elif pool_id:
                search_name = pool_id
            elif pool_id_type:
                search_name = pool_id_type.split('#')[0]
            else:
                search_name = "unknown"

            factory_id = self.find_factory_id_for_pool(search_name)
            
            if factory_id:
                try:
                    # テーブルごとにキー構造が異なる
                    if table_name == 'PoolLatest':
                        # PoolLatestのキー: pool_id (パーティションキー)
                        if not pool_id:
                            print(f"   ⚠️ スキップ ({search_name}): pool_id不足")
                            skipped_count += 1
                            continue
                        table.update_item(
                            Key={'pool_id': pool_id},
                            UpdateExpression='SET factory_id = :factory_id',
                            ExpressionAttributeValues={':factory_id': factory_id}
                        )
                    elif table_name == 'ConvexPoolHistory':
                        # ConvexPoolHistoryのキー: pool_id (パーティションキー), timestamp (ソートキー)
                        if not pool_id or 'timestamp' not in item:
                            print(f"   ⚠️ スキップ ({search_name}): pool_id/timestamp不足")
                            skipped_count += 1
                            continue
                        table.update_item(
                            Key={
                                'pool_id': pool_id,
                                'timestamp': item['timestamp']
                            },
                            UpdateExpression='SET factory_id = :factory_id',
                            ExpressionAttributeValues={':factory_id': factory_id}
                        )
                    elif table_name == 'ConvexPoolOHLCDaily':
                        # ConvexPoolOHLCDailyのキー: pool_id_type (パーティションキー), timestamp (ソートキー)
                        if 'pool_id_type' not in item or 'timestamp' not in item:
                            print(f"   ⚠️ スキップ ({search_name}): pool_id_type/timestamp不足 (Keys: {list(item.keys())})")
                            skipped_count += 1
                            continue
                        table.update_item(
                            Key={
                                'pool_id_type': item['pool_id_type'],
                                'timestamp': item['timestamp']
                            },
                            UpdateExpression='SET factory_id = :factory_id',
                            ExpressionAttributeValues={':factory_id': factory_id}
                        )
                    elif table_name == 'ConvexPoolRemarksHistory':
                        # ConvexPoolRemarksHistoryのキー: pool_id (パーティションキー), timestamp (ソートキー)
                        if not pool_id or 'timestamp' not in item:
                            print(f"   ⚠️ スキップ ({search_name}): pool_id/timestamp不足")
                            skipped_count += 1
                            continue
                        table.update_item(
                            Key={
                                'pool_id': pool_id,
                                'timestamp': item['timestamp']
                            },
                            UpdateExpression='SET factory_id = :factory_id',
                            ExpressionAttributeValues={':factory_id': factory_id}
                        )
                    
                    updated_count += 1
                    if updated_count % 10 == 0:
                        print(f"   進捗: {updated_count}件更新完了")
                    
                except Exception as e:
                    print(f"   ❌ 更新エラー ({search_name}): {e}")
                    error_count += 1
            else:
                print(f"   ⚠️ スキップ: factory_id未発見 (Search: {search_name})")
                skipped_count += 1
        
        print(f"\n   ✅ {table_name}更新完了:")
        print(f"      - 更新: {updated_count}件")
        print(f"      - スキップ: {skipped_count}件")
        print(f"      - エラー: {error_count}件")
        
        return updated_count, skipped_count, error_count

    def clear_failed_matching_file(self):
        """failed_pool_matching.jsonを空にする"""
        failed_file = Path("/home/ubuntu/convex-scraper/failed_pool_matching.json")
        
        try:
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2, ensure_ascii=False)
            print(f"\n✅ failed_pool_matching.jsonをクリアしました")
            return True
        except Exception as e:
            print(f"\n❌ failed_pool_matching.jsonのクリアに失敗: {e}")
            return False

    def run_update(self):
        """更新処理を実行"""
        print("\n" + "="*60)
        print("🚀 Convex関連テーブルのfactory_id更新を開始")
        print("="*60)
        
        total_updated = 0
        total_skipped = 0
        total_errors = 0
        
        # 各テーブルを処理
        for table_name in self.table_names:
            items = self.scan_table_items(table_name)
            if items:
                updated, skipped, errors = self.update_table_items(table_name, items)
                total_updated += updated
                total_skipped += skipped
                total_errors += errors
        
        # failed_pool_matching.jsonをクリア
        self.clear_failed_matching_file()
        
        print("\n" + "="*60)
        print("✅ 全テーブルの更新が完了しました")
        print("="*60)
        print(f"📊 更新サマリー:")
        print(f"   - 総更新件数: {total_updated}件")
        print(f"   - 総スキップ件数: {total_skipped}件")
        print(f"   - 総エラー件数: {total_errors}件")
        print("="*60)


def main():
    """メイン処理"""
    updater = ConvexTablesUpdater()
    updater.run_update()


if __name__ == "__main__":
    main()
