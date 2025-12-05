#!/usr/bin/env python3
"""
Curve Simulation API テストスクリプト
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"

def print_section(title):
    print("\n" + "="*50)
    print(title)
    print("="*50)

def test_health():
    print_section("🏥 ヘルスチェック")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_deposit():
    print_section("💰 デポジットシミュレーション")
    
    # 3pool (DAI/USDC/USDT)
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "timestamp": int(datetime(2024, 1, 1).timestamp()),  # 2024年1月1日
        "amounts": {
            "0": 1000,  # インデックス指定
            "1": 1000,
            "2": 1000
        }
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    response = requests.post(f"{BASE_URL}/simulate/deposit", json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

def test_withdraw():
    print_section("💸 引き出しシミュレーション")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "timestamp": int(datetime(2024, 1, 1).timestamp()),
        "lpAmount": 100.0,
        "withdrawToken": "1"  # USDC (index 1)
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    response = requests.post(f"{BASE_URL}/simulate/withdraw", json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

def test_ideal_ratios():
    print_section("📊 理想比率計算")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "timestamp": int(datetime(2024, 1, 1).timestamp())
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    response = requests.post(f"{BASE_URL}/simulate/ideal-ratios", json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

def test_impermanent_loss():
    print_section("📉 インパーマネントロス計算")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "timestamp_deposit": int(datetime(2024, 1, 1).timestamp()),
        "timestamp_withdraw": int(datetime(2024, 2, 1).timestamp()),
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
            "DAI": 1.01,
            "USDC": 0.99,
            "USDT": 1.0
        },
        "lpTokens": 3000.0
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    response = requests.post(f"{BASE_URL}/simulate/impermanent-loss", json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

if __name__ == "__main__":
    print("\n🚀 Curve Simulation API テスト開始\n")
    
    test_health()
    test_deposit()
    test_withdraw()
    test_ideal_ratios()
    test_impermanent_loss()
    
    print("\n✅ テスト完了\n")
