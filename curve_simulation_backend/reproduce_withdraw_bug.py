import requests
import json

BASE_URL = "http://localhost:8001"

def test_withdraw_bug_reproduction():
    print("\n" + "="*50)
    print("🐛 Withdrawal Bug Reproduction (Single Token in withdrawTokens)")
    print("="*50)
    
    # Use 3pool (DAI+USDC+USDT)
    # Deposit 1000 DAI to get some LP tokens first (or just assume we have some LP amount)
    # Let's assume we have 1000 LP tokens (approx $1000 worth)
    # If we withdraw to DAI only:
    # - Proportional: We get ~333 DAI (and ignore USDC/USDT) -> Bug
    # - One Coin: We get ~1000 DAI -> Correct
    
    # First, let's get pool info to know symbols/indices
    # But for reproduction, we can just send the request.
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "lpAmount": 1000.0,
        "withdrawTokens": ["DAI"], # List with single token
        "returnAllTokenAmounts": False
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    
    response = requests.post(f"{BASE_URL}/simulate/withdraw", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"\nResponse: {json.dumps(result, indent=2)}")
        
        dai_amount = result.get('withdraw_amounts_decimal', {}).get('DAI', 0)
        method = result.get('calculation_method')
        
        print(f"\nMethod used: {method}")
        print(f"DAI Amount: {dai_amount}")
        
        if method == "proportional" and dai_amount < 500:
            print("\n❌ BUG CONFIRMED: Used proportional withdrawal for single token request.")
        elif method == "contract" or method == "one_coin" or dai_amount > 900:
             print("\n✅ NO BUG: Seems to have used one coin withdrawal.")
        else:
            print("\n⚠️ UNCERTAIN: Check values manually.")
            
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_withdraw_bug_reproduction()
