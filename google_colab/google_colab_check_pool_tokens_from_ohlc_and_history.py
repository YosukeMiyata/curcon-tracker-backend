#!/usr/bin/env python3
# =====================================
# ConvexPoolOHLCDailyとConvexPoolHistoryからプール構成トークン一覧を取得
# 重複除去してトークン名、シンボル、アドレスを表示
# =====================================

import boto3
import json
from datetime import datetime
from collections import defaultdict
from botocore.exceptions import ClientError
import requests
import re

class PoolTokenAnalyzer:
    def __init__(self):
        """プールトークン分析器の初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.ohlc_daily_table = None
        self.history_table = None
        self.curve_token_prices = {}
        self.setup_tables()
        self.fetch_curve_prices()
    
    def setup_tables(self):
        """DynamoDBテーブルに接続"""
        try:
            self.ohlc_daily_table = self.dynamodb.Table('ConvexPoolOHLCDaily')
            self.ohlc_daily_table.load()
            print("✅ ConvexPoolOHLCDailyテーブルに接続しました")
            
            self.history_table = self.dynamodb.Table('ConvexPoolHistory')
            self.history_table.load()
            print("✅ ConvexPoolHistoryテーブルに接続しました")
        except ClientError as e:
            print(f"❌ テーブル接続エラー: {e}")
            return False
        return True
    
    def fetch_curve_prices(self):
        """Curve Finance APIからトークン価格データを取得"""
        try:
            print("💰 Curve Finance APIから価格データを取得中...")
            url = "https://api.curve.finance/api/getPools/all/ethereum"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # poolDataから全コインの価格情報を抽出
            if 'data' in data and 'poolData' in data['data']:
                pool_data = data['data']['poolData']
                
                for pool in pool_data:
                    if 'coins' in pool:
                        for coin in pool['coins']:
                            symbol = coin.get('symbol', '')
                            usd_price = coin.get('usdPrice')
                            
                            if symbol and usd_price is not None:
                                # 同じシンボルで複数の価格がある場合、最初に見つかったものを優先
                                if symbol not in self.curve_token_prices:
                                    self.curve_token_prices[symbol] = usd_price
                
                print(f"✅ {len(self.curve_token_prices)}個のトークン価格を取得しました")
            else:
                print("⚠️  APIレスポンスの構造が予期しない形式です")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Curve API取得エラー: {e}")
        except Exception as e:
            print(f"❌ 価格データ処理エラー: {e}")
    
    def get_all_pool_data_from_ohlc_daily(self):
        """ConvexPoolOHLCDailyから全プールデータを取得"""
        try:
            print("📊 ConvexPoolOHLCDailyからデータを取得中...")
            response = self.ohlc_daily_table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.ohlc_daily_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            print(f"✅ {len(items)}件のデータを取得しました（ConvexPoolOHLCDaily）")
            return items
            
        except Exception as e:
            print(f"❌ データ取得エラー: {e}")
            return []
    
    def get_all_pool_data_from_history(self):
        """ConvexPoolHistoryから全プールデータを取得"""
        try:
            print("📊 ConvexPoolHistoryからデータを取得中...")
            response = self.history_table.scan()
            items = response.get('Items', [])
            
            # ページネーション対応
            while 'LastEvaluatedKey' in response:
                response = self.history_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                items.extend(response.get('Items', []))
            
            print(f"✅ {len(items)}件のデータを取得しました（ConvexPoolHistory）")
            return items
            
        except Exception as e:
            print(f"❌ データ取得エラー: {e}")
            return []
    
    def normalize_token_symbol(self, token):
        """トークンシンボルを正規化（特殊文字を除去）"""
        if not token:
            return ""
        
        # ゼロ幅スペースや特殊文字を除去
        normalized = re.sub(r'[\u200b\u200c\u200d]', '', token)
        normalized = normalized.strip()
        
        return normalized
    
    def extract_tokens_from_pool_name(self, pool_name):
        """プール名からトークンを抽出（特殊ケース対応）"""
        if not pool_name:
            return []
        
        tokens = []
        
        # 特殊ケース1: crvUSD (XXX collateral) パターン
        if pool_name.startswith('crvUSD ('):
            # crvUSD (CRV collateral) -> crvUSD, CRV
            tokens.append('crvUSD')
            # 括弧内の内容を抽出
            match = re.search(r'crvUSD \((.*?)\)', pool_name)
            if match:
                collateral_token = match.group(1).strip()
                # "CRV collateral" -> "CRV" に正規化
                if collateral_token.endswith(' collateral'):
                    collateral_token = collateral_token.replace(' collateral', '')
                tokens.append(collateral_token)
            return tokens
        
        # 特殊ケース2: FRAXPYUSD のような連結トークン
        # 一般的な連結パターンをチェック
        if 'FRAXPYUSD' in pool_name:
            tokens.extend(['FRAX', 'PYUSD'])
            return tokens
        
        # 通常ケース: +で分割
        # 注意: 「ETH+」のようにトークン名自体に+が含まれる場合を考慮
        # split('+')後、空文字列でないものだけを抽出
        # さらに、トークン名の末尾の+を保持する
        parts = pool_name.split('+')
        for i, part in enumerate(parts):
            clean_token = self.normalize_token_symbol(part)
            if clean_token:
                # 次のパートが空文字列の場合、このトークンは「XXX+」という形式
                if i + 1 < len(parts) and not parts[i + 1].strip():
                    tokens.append(clean_token + '+')
                    # 空のパートをスキップするためのフラグは不要（次のループで空文字列として除外される）
                else:
                    tokens.append(clean_token)
        
        return tokens
    
    def analyze_pool_tokens(self):
        """プール構成トークンを分析（ConvexPoolOHLCDailyとConvexPoolHistoryの両方から）"""
        # 両方のテーブルからデータを取得
        ohlc_items = self.get_all_pool_data_from_ohlc_daily()
        history_items = self.get_all_pool_data_from_history()
        
        # データをマージ
        all_items = ohlc_items + history_items
        
        if not all_items:
            return {}
        
        # トークン情報を格納する辞書
        token_info = {}
        
        print("\n🔍 プールデータからトークンを抽出中...")
        
        for item in all_items:
            pool_name = item.get('Pool', '')
            factory_id = item.get('factory_id', '')
            
            if not pool_name:
                continue
            
            # プール名からトークンを抽出
            tokens = self.extract_tokens_from_pool_name(pool_name)
            
            for token in tokens:
                if token not in token_info:
                    # トークン価格を取得（見つからない場合は"Error"）
                    price = self.curve_token_prices.get(token, "Error")
                    
                    token_info[token] = {
                        'symbol': token,
                        'pools': [],
                        'factory_ids': [],
                        'price': price
                    }
                
                # このトークンが使われているプールを記録（重複除去）
                if pool_name not in token_info[token]['pools']:
                    token_info[token]['pools'].append(pool_name)
                    if factory_id and factory_id not in token_info[token]['factory_ids']:
                        token_info[token]['factory_ids'].append(factory_id)
        
        return token_info
    
    def display_token_summary(self, token_info):
        """トークン一覧を表示"""
        if not token_info:
            print("❌ トークン情報が見つかりません")
            return
        
        print(f"\n📋 プール構成トークン一覧（重複除去済み）")
        print(f"   総トークン数: {len(token_info)}")
        print("=" * 80)
        
        # トークン名でソート
        sorted_tokens = sorted(token_info.items(), key=lambda x: x[0])
        
        for token, info in sorted_tokens:
            print(f"\n🔸 トークン: {token}")
            print(f"   使用プール数: {len(info['pools'])}")
            
            # 使用されているプール（カンマ区切りで表示）
            if info['pools']:
                print(f"   使用プール:")
                print(f"      {', '.join(info['pools'])}")
            
            # factory_id（カンマ区切りで表示）
            if info.get('factory_ids'):
                print(f"   factory_id:")
                print(f"      {', '.join(info['factory_ids'])}")
            
            # 価格を表示
            price = info.get('price', 'Error')
            if price == 'Error':
                print(f"   price: Error")
            else:
                print(f"   price: ${price:,.6f}")
    
    def save_token_list_to_file(self, token_info, filename="pool_tokens_list.json"):
        """トークン一覧をJSONファイルに保存"""
        try:
            # ファイル保存用のデータ構造
            save_data = {
                'generated_at': datetime.now().isoformat(),
                'total_tokens': len(token_info),
                'tokens': {}
            }
            
            for token, info in token_info.items():
                save_data['tokens'][token] = {
                    'symbol': info['symbol'],
                    'pool_count': len(info['pools']),
                    'pools': info['pools'],
                    'factory_ids': info.get('factory_ids', []),
                    'price': info.get('price', 'Error')
                }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ トークン一覧を {filename} に保存しました")
            
        except Exception as e:
            print(f"❌ ファイル保存エラー: {e}")
    
    def get_most_common_tokens(self, token_info, top_n=20):
        """最も多く使用されているトークンを表示"""
        if not token_info:
            return
        
        # プール数でソート
        sorted_tokens = sorted(
            token_info.items(), 
            key=lambda x: len(x[1]['pools']), 
            reverse=True
        )
        
        print(f"\n🏆 最も多く使用されているトークン（上位{top_n}個）")
        print("=" * 60)
        
        for i, (token, info) in enumerate(sorted_tokens[:top_n], 1):
            print(f"{i:2d}. {token:<15} ({len(info['pools'])}個のプールで使用)")
    
    def run_analysis(self):
        """分析を実行"""
        print("🚀 プール構成トークン分析開始")
        print("=" * 50)
        print("📊 ConvexPoolOHLCDailyとConvexPoolHistoryからデータを取得")
        print("=" * 50)
        
        # トークン情報を取得
        token_info = self.analyze_pool_tokens()
        
        if not token_info:
            print("❌ 分析に失敗しました")
            return
        
        # 結果を表示
        self.display_token_summary(token_info)
        
        # 最も使用されているトークンを表示
        self.get_most_common_tokens(token_info)
        
        # ファイルに保存
        self.save_token_list_to_file(token_info)
        
        # 全トークンをカンマ区切りで表示
        all_tokens = sorted(token_info.keys())
        print(f"\n📝 全トークン一覧（カンマ区切り）:")
        print(f"{', '.join(all_tokens)}")
        
        # 価格取得に失敗したトークンを表示
        failed_tokens = [token for token, info in token_info.items() if info.get('price') == 'Error']
        if failed_tokens:
            print(f"\n⚠️  価格取得に失敗したトークン（{len(failed_tokens)}個）:")
            print("=" * 60)
            for token in sorted(failed_tokens):
                pool_count = len(token_info[token]['pools'])
                print(f"   • {token} ({pool_count}個のプールで使用)")
        else:
            print(f"\n✅ 全てのトークンの価格取得に成功しました")
        
        print(f"\n✅ 分析完了: {len(token_info)}個のユニークトークンを発見")

def main():
    """メイン関数"""
    try:
        analyzer = PoolTokenAnalyzer()
        analyzer.run_analysis()
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🔍 ConvexPoolOHLCDaily & ConvexPoolHistory プール構成トークン分析ツール")
    print("📊 重複除去してトークン一覧を表示")
    main()

