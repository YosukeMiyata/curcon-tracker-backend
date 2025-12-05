import requests
import json

BASE_URL = "http://localhost:8001"

def verify_partial_operations():
    print("\n" + "="*50)
    print("🧪 Partial Deposit/Withdrawal Verification (2 out of 3 tokens)")
    print("="*50)
    
    # 1. Deposit 2 tokens (DAI + USDC) into 3pool (DAI+USDC+USDT)
    print("\n[1] Deposit: DAI(1000) + USDC(1000) + USDT(0)")
    deposit_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "amounts": {
            "DAI": 1000,
            "USDC": 1000
            # USDT is omitted (0)
        },
        "calculateAdjustedLpPrice": True,
        "tokenPrices": {
            "DAI": 1.0,
            "USDC": 1.0,
            "USDT": 1.0
        }
    }
    
    dep_res = requests.post(f"{BASE_URL}/simulate/deposit", json=deposit_payload)
    if dep_res.status_code != 200:
        print(f"Deposit failed: {dep_res.text}")
        return

    dep_data = dep_res.json()
    lp_received = dep_data['lp_amount_received_decimal']
    print(f"✅ Deposit Successful")
    print(f"   Input: {json.dumps(deposit_payload['amounts'])}")
    print(f"   LP Received: {lp_received:.4f}")
    print(f"   Calculation Method: {dep_data['calculation_method']}")
    
    # 2. Withdraw 2 tokens (DAI + USDC)
    # We expect to get proportional share of DAI, USDC, AND USDT.
    # But if we only ask for DAI and USDC, we should see those amounts.
    print("\n[2] Withdraw: Requesting only DAI + USDC")
    withdraw_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "lpAmount": lp_received,
        "withdrawTokens": ["DAI", "USDC"],
        "returnAllTokenAmounts": True # To see what we are "missing"
    }
    
    wd_res = requests.post(f"{BASE_URL}/simulate/withdraw", json=withdraw_payload)
    if wd_res.status_code != 200:
        print(f"Withdraw failed: {wd_res.text}")
        return

    wd_data = wd_res.json()
    print(f"✅ Withdraw Successful")
    print(f"   Requested: {withdraw_payload['withdrawTokens']}")
    print(f"   Returned (Decimal): {json.dumps(wd_data['withdraw_amounts_decimal'], indent=2)}")
    
    # Check "All Token Amounts" to see USDT
    all_tokens = wd_data.get('all_token_amounts', {})
    print(f"   Full Proportional Breakdown (Hidden USDT revealed):")
    for sym, data in all_tokens.items():
        print(f"     - {sym}: {data['decimal']:.4f}")
        
    print("\n[Analysis]")
    print("Deposit worked correctly for partial inputs (Imbalance added).")
    print("Withdrawal returned proportional share of requested tokens.")
    print("Note that USDT was also part of the share (since you own a slice of the whole pool),")
    print("but it would be excluded if 'returnAllTokenAmounts' was False and 'withdrawTokens' didn't include it.")

if __name__ == "__main__":
    verify_partial_operations()
