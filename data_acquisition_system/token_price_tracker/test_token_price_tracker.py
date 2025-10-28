#!/usr/bin/env python3
# =====================================
# トークン価格追跡システム テストスクリプト
# ローカル環境でテスト実行
# =====================================

import sys
import os
import json
from datetime import datetime, timezone, timedelta

# 現在のディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from token_price_tracker import TokenPriceTracker

def test_token_extraction():
    """トークン抽出機能のテスト"""
    print("🧪 トークン抽出機能をテスト中...")
    
    tracker = TokenPriceTracker()
    
    # テストケース
    test_cases = [
        ("3Crv", ["3Crv"]),
        ("CRV+", ["CRV+"]),
        ("crvUSD (CRV collateral)", ["crvUSD", "CRV"]),
        ("FRAXPYUSD", ["FRAX", "PYUSD"]),
        ("ETH+USDC", ["ETH", "USDC"]),
        ("USDT+USDC+DAI", ["USDT", "USDC", "DAI"]),
    ]
    
    for pool_name, expected_tokens in test_cases:
        extracted = tracker.extract_tokens_from_pool_name(pool_name)
        print(f"  プール名: {pool_name}")
        print(f"  抽出結果: {extracted}")
        print(f"  期待値: {expected_tokens}")
        print(f"  結果: {'✅' if extracted == expected_tokens else '❌'}")
        print()
    
    print("✅ トークン抽出テスト完了")

def test_curve_api():
    """Curve Finance API接続テスト"""
    print("🧪 Curve Finance API接続をテスト中...")
    
    tracker = TokenPriceTracker()
    
    print(f"取得したトークン数: {len(tracker.curve_token_prices)}")
    
    # 最初の10個のトークンを表示
    sample_tokens = list(tracker.curve_token_prices.items())[:10]
    print("サンプルトークン:")
    for token, price in sample_tokens:
        print(f"  {token}: ${price}")
    
    print("✅ Curve Finance APIテスト完了")

def test_database_connection():
    """データベース接続テスト"""
    print("🧪 データベース接続をテスト中...")
    
    try:
        tracker = TokenPriceTracker()
        
        if tracker.convex_table:
            print("✅ ConvexPoolMetricsテーブル接続成功")
        else:
            print("❌ ConvexPoolMetricsテーブル接続失敗")
        
        if tracker.token_price_table:
            print("✅ TokenPriceHistoryテーブル接続成功")
        else:
            print("❌ TokenPriceHistoryテーブル接続失敗")
            
    except Exception as e:
        print(f"❌ データベース接続エラー: {e}")
    
    print("✅ データベース接続テスト完了")

def test_full_tracking():
    """完全な追跡テスト（実際のDB保存は行わない）"""
    print("🧪 完全な追跡テストを実行中...")
    
    try:
        tracker = TokenPriceTracker()
        
        # トークン情報を取得
        token_info = tracker.analyze_pool_tokens()
        
        if token_info:
            print(f"✅ トークン分析成功: {len(token_info)}個のトークンを発見")
            
            # 統計情報を表示
            successful_tokens = [token for token, info in token_info.items() if info.get('price') is not None]
            failed_tokens = [token for token, info in token_info.items() if info.get('price') is None]
            
            print(f"  価格取得成功: {len(successful_tokens)}個")
            print(f"  価格取得失敗: {len(failed_tokens)}個")
            
            if failed_tokens:
                print(f"  失敗したトークン: {', '.join(failed_tokens[:10])}{'...' if len(failed_tokens) > 10 else ''}")
            
            # サンプルデータを表示
            print("\nサンプルデータ:")
            for i, (token, info) in enumerate(list(token_info.items())[:5]):
                price = info.get('price', 'N/A')
                pool_count = len(info['pools'])
                print(f"  {token}: ${price} (プール数: {pool_count})")
        else:
            print("❌ トークン分析失敗")
            
    except Exception as e:
        print(f"❌ 追跡テストエラー: {e}")
    
    print("✅ 完全な追跡テスト完了")

def main():
    """メインテスト関数"""
    print("🚀 トークン価格追跡システム テスト開始")
    print("=" * 60)
    
    try:
        # 各テストを実行
        test_token_extraction()
        print()
        
        test_curve_api()
        print()
        
        test_database_connection()
        print()
        
        test_full_tracking()
        print()
        
        print("🎉 全テスト完了")
        
    except Exception as e:
        print(f"❌ テスト実行エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
