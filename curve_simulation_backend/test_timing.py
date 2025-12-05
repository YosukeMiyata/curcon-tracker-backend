#!/usr/bin/env python3
"""
処理時間計測付きテストスクリプト（全エンドポイント対応）
"""
import requests
import json
from datetime import datetime
import time

BASE_URL = "http://localhost:8001"

def print_section(title):
    print("\n" + "="*50)
    print(title)
    print("="*50)

def test_deposit():
    print_section("💰 デポジットシミュレーション")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp": 1704034800,
        "amounts": {
            "0": 1000,
            "1": 1000,
            "2": 1000
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
    else:
        print(f"Error: {response.json()}")

def test_withdraw():
    print_section("💸 引き出しシミュレーション")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp": 1704034800,
        "lpAmount": 100.0,
        "withdrawToken": "1"
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
    else:
        print(f"Error: {response.json()}")

def test_ideal_ratios():
    print_section("📊 理想比率計算")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "timestamp": 1704034800
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/ideal-ratios", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Client-side elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

def test_impermanent_loss():
    print_section("📉 インパーマネントロス計算")
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool (DAI+USDC+USDT)",
        "factoryId": "factory-stable-ng-1",
        "timestamp_deposit": 1704034800,
        "timestamp_withdraw": 1706713200,
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
    start = time.time()
    response = requests.post(f"{BASE_URL}/simulate/impermanent-loss", json=payload)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Client-side elapsed time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.json()}")

if __name__ == "__main__":
    print("\n🚀 処理時間計測テスト（全エンドポイント）\n")
    test_deposit()
    test_withdraw()
    test_ideal_ratios()
    test_impermanent_loss()
    print("\n✅ テスト完了\n")
