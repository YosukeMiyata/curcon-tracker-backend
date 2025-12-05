#!/usr/bin/env python3
"""
Phase 1拡張機能のテストスクリプト
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001"

def test_deposit_with_tvl():
    """TVL変動考慮付きデポジットテスト"""
    print("\n" + "="*50)
    print("💰 デポジット（TVL変動考慮）テスト")
    print("="*50)
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp": 1704034800,
        "amounts": {
            "DAI": 1000,
            "USDC": 1000,
            "USDT": 1000
        },
        "calculateAdjustedLpPrice": True,
        "tokenPrices": {
            "DAI": 1.0,
            "USDC": 1.0,
            "USDT": 1.0
        }
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/deposit", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Client-side elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        
        # TVL分析が含まれているか確認
        if 'tvl_analysis' in result:
            print("\n✅ TVL分析が正常に含まれています")
        else:
            print("\n⚠️ TVL分析が含まれていません")
    else:
        print(f"Error: {response.text}")

def test_withdraw_multiple_tokens():
    """複数トークン引き出しテスト"""
    print("\n" + "="*50)
    print("💸 引き出し（複数トークン）テスト")
    print("="*50)
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp": 1704034800,
        "lpAmount": 100.0,
        "withdrawTokens": ["USDC", "USDT"],
        "returnAllTokenAmounts": True
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/withdraw", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Client-side elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        
        # 複数トークンが含まれているか確認
        if 'withdraw_amounts_decimal' in result:
            print(f"\n✅ 引き出しトークン: {list(result['withdraw_amounts_decimal'].keys())}")
        
        # 全トークン量が含まれているか確認
        if 'all_token_amounts' in result:
            print(f"✅ 全トークン量が含まれています: {list(result['all_token_amounts'].keys())}")
    else:
        print(f"Error: {response.text}")

def test_batch_deposit_withdraw():
    """バッチエンドポイントテスト"""
    print("\n" + "="*50)
    print("🚀 バッチ（デポジット+引き出し）テスト")
    print("="*50)
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "depositTimestamp": 1704034800,
        "depositAmounts": {
            "DAI": 1000,
            "USDC": 1000,
            "USDT": 1000
        },
        "depositTokenPrices": {
            "DAI": 1.0,
            "USDC": 1.0,
            "USDT": 1.0
        },
        "withdrawTimestamp": 1706713200,
        "withdrawTokens": ["USDC", "USDT"]
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/batch-deposit-withdraw", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Client-side elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        print(f"\n✅ バッチ処理完了")
        print(f"   デポジット: {result['deposit']['lp_amount_received_decimal']:.2f} LP")
        print(f"   引き出し: {result['withdraw']['withdraw_amounts_decimal']}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    print("\n🚀 Phase 1拡張機能テスト開始\n")
    
    try:
        test_deposit_with_tvl()
        test_withdraw_multiple_tokens()
        test_batch_deposit_withdraw()
        
        print("\n" + "="*50)
        print("✅ 全テスト完了")
        print("="*50)
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        import traceback
        traceback.print_exc()
