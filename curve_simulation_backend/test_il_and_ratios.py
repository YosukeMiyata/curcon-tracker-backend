#!/usr/bin/env python3
"""
インパーマネントロスと理想比率エンドポイントのテスト
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001"

def test_ideal_ratios():
    """理想的なトークン比率のテスト"""
    print("\n" + "="*50)
    print("📊 理想的なトークン比率テスト")
    print("="*50)
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp": 1704034800
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/ideal-ratios", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ 成功")
        print(f"Block Number: {result['block_number']}")
        print(f"Ideal Ratios:")
        for symbol, ratio in result['ideal_ratios'].items():
            print(f"  {symbol}: {ratio:.4f} ({ratio*100:.2f}%)")
    else:
        print(f"❌ Error: {response.text}")

def test_impermanent_loss():
    """インパーマネントロステスト"""
    print("\n" + "="*50)
    print("📉 インパーマネントロステスト")
    print("="*50)
    
    # まずデポジットシミュレーションを実行してLP量を取得
    deposit_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
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
    
    print("Step 1: デポジットシミュレーション")
    dep_res = requests.post(f"{BASE_URL}/simulate/deposit", json=deposit_payload)
    if dep_res.status_code != 200:
        print(f"❌ デポジット失敗: {dep_res.text}")
        return
    
    dep_data = dep_res.json()
    lp_tokens = dep_data['lp_amount_received_decimal']
    print(f"  LP取得量: {lp_tokens:.4f}")
    
    # インパーマネントロス計算
    print("\nStep 2: インパーマネントロス計算")
    il_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp_deposit": 1704034800,
        "timestamp_withdraw": 1706713200,  # 約1ヶ月後
        "depositAmounts": {
            "DAI": 1000,
            "USDC": 1000,
            "USDT": 1000
        },
        "priceAtDeposit": {
            "DAI": 1.0,
            "USDC": 1.0,
            "USDT": 1.0
        },
        "priceAtWithdraw": {
            "DAI": 1.02,  # 2%上昇
            "USDC": 0.99,  # 1%下落
            "USDT": 1.01   # 1%上昇
        },
        "lpTokens": lp_tokens
    }
    
    print(f"Request: {json.dumps(il_payload, indent=2)}")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/impermanent-loss", json=il_payload)
    elapsed = time.time() - start
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ 成功")
        print(f"Block Number: {result['block_number']}")
        print(f"デポジット価値: ${result['deposit_value_usd']:,.2f}")
        print(f"引き出し価値: ${result['withdraw_value_usd']:,.2f}")
        print(f"HODL価値: ${result['hodl_value_usd']:,.2f}")
        print(f"インパーマネントロス: ${result['impermanent_loss_usd']:,.2f} ({result['impermanent_loss_percentage']:.2f}%)")
        print(f"\n引き出し量:")
        for symbol, amount in result['withdraw_amounts'].items():
            print(f"  {symbol}: {amount:.4f}")
    else:
        print(f"❌ Error: {response.text}")

if __name__ == "__main__":
    print("\n🚀 インパーマネントロスと理想比率エンドポイントテスト開始\n")
    
    try:
        test_ideal_ratios()
        test_impermanent_loss()
        
        print("\n" + "="*50)
        print("✅ 全テスト完了")
        print("="*50)
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        import traceback
        traceback.print_exc()
