#!/usr/bin/env python3
"""
既存のConvexPoolMetricsテーブルのデータにfactory_idを付加するスクリプト
"""

import boto3
import json
import os
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

class ConvexPoolMetricsUpdater:
    def __init__(self):
        """初期化"""
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('ConvexPoolMetrics')
        
        # manual_pool_mapping.jsonを読み込み
        self.manual_mapping = self.load_manual_mapping()
        
        print("✅ ConvexPoolMetrics更新スクリプト初期化完了")
        print(f"📋 対応表エントリ数: {len(self.manual_mapping)}")

    def load_manual_mapping(self):
        """manual_pool_mapping.jsonを読み込み"""
        try:
            with open('manual_pool_mapping.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ manual_pool_mapping.json読み込みエラー: {e}")
            return {}

    def find_factory_id_for_pool(self, pool_name, token_symbols=None):
        """プール名からfactory_idを検索"""
        if not pool_name:
            return None
        
        # 文字の正規化（ゼロ幅スペースや特殊文字を除去）
        def normalize_text(text):
            if not text:
                return ""
            # ゼロ幅スペース、ゼロ幅非結合子、ゼロ幅結合子を除去
            import re
            text = re.sub(r'[\u200b\u200c\u200d]', '', text)
            # その他の特殊文字も除去
            text = re.sub(r'[^\w\s\+\-\(\)]', '', text)
            return text.strip()
        
        normalized_pool_name = normalize_text(pool_name)
            
        # 1. 完全一致で検索（正規化後）
        for mapping_name, factory_id in self.manual_mapping.items():
            if normalize_text(mapping_name) == normalized_pool_name:
                return factory_id
        
        # 2. 元の文字列での完全一致
        if pool_name in self.manual_mapping:
            return self.manual_mapping[pool_name]
        
        # 3. 部分一致で検索（正規化後）
        for mapping_name, factory_id in self.manual_mapping.items():
            normalized_mapping = normalize_text(mapping_name)
            if normalized_pool_name in normalized_mapping or normalized_mapping in normalized_pool_name:
                return factory_id
        
        # 4. 大文字小文字を無視した部分一致
        pool_name_lower = normalized_pool_name.lower()
        for mapping_name, factory_id in self.manual_mapping.items():
            normalized_mapping_lower = normalize_text(mapping_name).lower()
            if pool_name_lower in normalized_mapping_lower or normalized_mapping_lower in pool_name_lower:
                return factory_id
        
        # 5. token_symbolsを使用した検索
        if token_symbols:
            for symbol in token_symbols:
                symbol_normalized = normalize_text(symbol)
                for mapping_name, factory_id in self.manual_mapping.items():
                    if symbol_normalized.lower() in normalize_text(mapping_name).lower():
                        return factory_id
        
        return None

    def scan_all_items(self):
        """ConvexPoolMetricsテーブルの全データを取得"""
        print("🔍 ConvexPoolMetricsテーブルから全データを取得中...")
        
        all_items = []
        response = self.table.scan()
        all_items.extend(response['Items'])
        
        # ページネーション処理
        while 'LastEvaluatedKey' in response:
            response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            all_items.extend(response['Items'])
            print(f"   📊 取得中... {len(all_items)}件")
        
        print(f"✅ 全データ取得完了: {len(all_items)}件")
        return all_items

    def update_items_with_factory_id(self, items):
        """アイテムにfactory_idを追加して更新"""
        print(f"🔄 {len(items)}件のデータを更新中...")
        
        updated_count = 0
        matched_count = 0
        error_count = 0
        unmatched_pools = []  # 未マッチプールを記録
        
        for i, item in enumerate(items):
            try:
                pool_name = item.get('Pool', '')
                pool_id = item.get('pool_id', '')
                timestamp = item.get('timestamp', '')
                
                # 既にfactory_idがある場合はスキップ
                if 'factory_id' in item and item['factory_id'] is not None:
                    print(f"   ⏭️ スキップ: {pool_name} (既にfactory_idあり)")
                    continue
                
                # factory_idを検索
                factory_id = self.find_factory_id_for_pool(pool_name)
                
                if factory_id:
                    # factory_idを追加して更新
                    item['factory_id'] = str(factory_id)
                    self.table.put_item(Item=item)
                    matched_count += 1
                    print(f"   ✅ 更新: {pool_name} -> factory_id: {factory_id}")
                else:
                    # factory_idが見つからない場合はnullを設定
                    item['factory_id'] = None
                    self.table.put_item(Item=item)
                    print(f"   ⚠️ 未マッチ: {pool_name} -> factory_id: None")
                    
                    # 未マッチプールの情報を記録
                    unmatched_pool_info = {
                        'pool_name': pool_name,
                        'pool_id': pool_id,
                        'timestamp': timestamp,
                        'current_vapr': item.get('Current_vAPR', ''),
                        'projected_vapr': item.get('Projected_vAPR', ''),
                        'tvl': item.get('TVL', ''),
                        'remarks': item.get('Remarks', '')
                    }
                    unmatched_pools.append(unmatched_pool_info)
                
                updated_count += 1
                
                # 進捗表示
                if (i + 1) % 10 == 0:
                    print(f"   📊 進捗: {i + 1}/{len(items)}件処理完了")
                    
            except Exception as e:
                error_count += 1
                print(f"   ❌ エラー: {pool_name} -> {e}")
        
        # 未マッチプールをJSONファイルに保存
        if unmatched_pools:
            self.save_unmatched_pools(unmatched_pools)
        
        print(f"\n✅ 更新完了:")
        print(f"   - 総処理件数: {updated_count}件")
        print(f"   - factory_idマッチ: {matched_count}件")
        print(f"   - 未マッチプール: {len(unmatched_pools)}件")
        print(f"   - エラー: {error_count}件")
        
        return updated_count, matched_count, error_count, len(unmatched_pools)

    def save_unmatched_pools(self, unmatched_pools):
        """未マッチプールをmanual_pool_mapping.json形式で保存"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'unmatched_pools_{timestamp}.json'
            
            # 重複を除去（pool_nameでユニークにする）
            unique_pools = {}
            for pool in unmatched_pools:
                pool_name = pool['pool_name']
                if pool_name not in unique_pools:
                    unique_pools[pool_name] = pool
            
            # manual_pool_mapping.json形式で保存
            mapping_format = {}
            for pool_name in unique_pools.keys():
                mapping_format[pool_name] = ""  # 空のfactory_idで保存
            
            # JSONファイルに保存
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(mapping_format, f, ensure_ascii=False, indent=2)
            
            print(f"\n📄 未マッチプール情報を保存: {filename}")
            print(f"   - ユニークプール数: {len(unique_pools)}件")
            print(f"   - ファイルパス: {os.path.abspath(filename)}")
            print(f"   - 形式: manual_pool_mapping.json形式")
            
            # 未マッチプールの一覧を表示
            print(f"\n📋 未マッチプール一覧 (manual_pool_mapping.json形式):")
            for i, (pool_name, factory_id) in enumerate(list(mapping_format.items())[:10], 1):
                print(f"   {i:2d}. \"{pool_name}\" : \"{factory_id}\",")
            
            if len(mapping_format) > 10:
                print(f"   ... 他{len(mapping_format) - 10}件")
            
            # 追加用のテンプレートも表示
            print(f"\n💡 manual_pool_mapping.jsonへの追加方法:")
            print(f"   1. {filename} の内容をコピー")
            print(f"   2. manual_pool_mapping.json の適切な位置に貼り付け")
            print(f"   3. 各プールのfactory_idを調査して入力")
            print(f"   4. 再度このスクリプトを実行")
            
            # 生成されるJSONファイルの例を表示
            print(f"\n📝 生成されるJSONファイルの例:")
            print(f"   {{")
            for i, (pool_name, factory_id) in enumerate(list(mapping_format.items())[:3], 1):
                print(f"     \"{pool_name}\" : \"{factory_id}\",")
            if len(mapping_format) > 3:
                print(f"     ... 他{len(mapping_format) - 3}件")
            print(f"   }}")
            
            return filename
            
        except Exception as e:
            print(f"❌ 未マッチプール保存エラー: {e}")
            return None

    def run_update(self):
        """更新処理を実行"""
        print("🚀 ConvexPoolMetrics既存データ更新開始")
        print("="*50)
        
        try:
            # 全データを取得
            items = self.scan_all_items()
            
            if not items:
                print("❌ データが見つかりませんでした")
                return
            
            # 既にfactory_idがあるアイテムを除外
            items_without_factory_id = [
                item for item in items 
                if 'factory_id' not in item or item['factory_id'] is None
            ]
            
            print(f"📊 更新対象: {len(items_without_factory_id)}件 (全{len(items)}件中)")
            
            if not items_without_factory_id:
                print("✅ すべてのデータに既にfactory_idが設定されています")
                return
            
            # 更新実行
            updated_count, matched_count, error_count, unmatched_count = self.update_items_with_factory_id(items_without_factory_id)
            
            print(f"\n🎉 更新処理完了!")
            print(f"   - 更新件数: {updated_count}件")
            print(f"   - factory_idマッチ: {matched_count}件")
            print(f"   - 未マッチプール: {unmatched_count}件")
            print(f"   - エラー件数: {error_count}件")
            
            if unmatched_count > 0:
                print(f"\n💡 次のステップ:")
                print(f"   1. 生成されたunmatched_pools_*.jsonファイルを確認")
                print(f"   2. 未マッチプールのfactory_idを調査")
                print(f"   3. manual_pool_mapping.jsonに追加")
                print(f"   4. 再度このスクリプトを実行")
            
        except Exception as e:
            print(f"❌ 更新処理エラー: {e}")

def main():
    """メイン処理"""
    updater = ConvexPoolMetricsUpdater()
    updater.run_update()

if __name__ == "__main__":
    main()
