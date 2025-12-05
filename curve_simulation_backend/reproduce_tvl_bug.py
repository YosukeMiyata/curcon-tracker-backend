import requests
import json

BASE_URL = "http://localhost:8001"

def test_tvl_bug_reproduction():
    print("\n" + "="*50)
    print("🐛 TVL Bug Reproduction (Single Token Deposit)")
    print("="*50)
    
    # User provided case
    # Pool: USDFI + frxUSD (assuming address from user request)
    # The user mentioned pool address: 0x2eFC11c7Bb2E0FBdBa8A05a3712398860E6A8E53
    # But I should check if this pool exists/works in my local fork or if I should use the 3pool I have been using.
    # The user's example used 3pool in previous tests.
    # Let's use 3pool (DAI+USDC+USDT) for reproduction as I know it works.
    # DAI+USDC+USDT.
    # Deposit only DAI.
    # Send price only for DAI.
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "amounts": {
            "DAI": 5000
        },
        "calculateAdjustedLpPrice": True,
        "tokenPrices": {
            "DAI": 1.0
            # Missing USDC and USDT prices
        }
    }
    
    print(f"Request (Missing prices): {json.dumps(payload, indent=2)}")
    
    response = requests.post(f"{BASE_URL}/simulate/deposit", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        tvl = result.get('tvl_analysis', {})
        print(f"\nResult TVL Analysis:")
        print(f"Original TVL: ${tvl.get('original_tvl_usd', 0):,.2f}")
        print(f"Original LP Price: ${tvl.get('original_lp_price', 0):.4f}")
        
        # 3pool TVL is huge (hundreds of millions). 
        # If it returns ~5000 (deposit amount) or similar small number, it confirms the bug.
        if tvl.get('original_tvl_usd', 0) < 1000000:
            print("\n❌ BUG CONFIRMED: TVL is too low (likely only counting deposited token).")
        else:
            print("\n✅ NO BUG: TVL seems reasonable.")
            
    else:
        print(f"Error: {response.text}")

def test_tvl_fix_verification():
    print("\n" + "="*50)
    print("✅ TVL Fix Verification (Sending All Prices)")
    print("="*50)
    
    payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "amounts": {
            "DAI": 5000
        },
        "calculateAdjustedLpPrice": True,
        "tokenPrices": {
            "DAI": 1.0,
            "USDC": 1.0,
            "USDT": 1.0
        }
    }
    
    print(f"Request (All prices): {json.dumps(payload, indent=2)}")
    
    response = requests.post(f"{BASE_URL}/simulate/deposit", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        tvl = result.get('tvl_analysis', {})
        print(f"\nResult TVL Analysis:")
        print(f"Original TVL: ${tvl.get('original_tvl_usd', 0):,.2f}")
        print(f"Original LP Price: ${tvl.get('original_lp_price', 0):.4f}")
        
        if tvl.get('original_tvl_usd', 0) > 1000000:
             print("\n✅ VERIFIED: TVL is reasonable when all prices are provided.")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_tvl_bug_reproduction()
    test_tvl_fix_verification()
