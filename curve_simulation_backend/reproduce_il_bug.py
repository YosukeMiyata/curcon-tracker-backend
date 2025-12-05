import requests
import json

BASE_URL = "http://localhost:8001"

def test_il_bug_reproduction():
    print("\n" + "="*50)
    print("🐛 IL Bug Reproduction (Single Token Deposit/Withdraw)")
    print("="*50)
    
    # User Case:
    # Deposit: 5000 frxUSD (Single token)
    # Price: ~1.0 (No change)
    # LP Amount: ~5000.13
    # Expected IL: ~0
    # Actual IL: -2759.14 (-55.18%)
    
    # Reproduction using 3pool (DAI+USDC+USDT)
    # Deposit 5000 DAI, Price 1.0 -> 1.0
    
    # 1. Get LP amount first (Simulate deposit)
    print("Step 1: Get LP amount for 5000 DAI deposit")
    dep_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "timestamp": 1704034800,
        "amounts": {"DAI": 5000},
        "calculateAdjustedLpPrice": True,
        "tokenPrices": {"DAI": 1.0, "USDC": 1.0, "USDT": 1.0}
    }
    dep_res = requests.post(f"{BASE_URL}/simulate/deposit", json=dep_payload)
    if dep_res.status_code != 200:
        print(f"Deposit failed: {dep_res.text}")
        return
    lp_tokens = dep_res.json()['lp_amount_received_decimal']
    print(f"LP Tokens: {lp_tokens}")

    # 2. Calculate IL
    print("\nStep 2: Calculate IL (No price change)")
    il_payload = {
        "poolAddress": "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",
        "poolName": "3pool",
        "lpTokenAddress": "0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490",
        "timestamp_deposit": 1704034800,
        "timestamp_withdraw": 1704034800 + 86400, # 1 day later
        "depositAmounts": {"DAI": 5000},
        "priceAtDeposit": {"DAI": 1.0, "USDC": 1.0, "USDT": 1.0},
        "priceAtWithdraw": {"DAI": 1.0, "USDC": 1.0, "USDT": 1.0},
        "lpTokens": lp_tokens
    }
    
    print(f"Request: {json.dumps(il_payload, indent=2)}")
    
    res = requests.post(f"{BASE_URL}/simulate/impermanent-loss", json=il_payload)
    
    if res.status_code == 200:
        result = res.json()
        print(f"\nResult:")
        print(f"Deposit Value: ${result['deposit_value_usd']:,.2f}")
        print(f"Withdraw Value: ${result['withdraw_value_usd']:,.2f}")
        print(f"HODL Value: ${result['hodl_value_usd']:,.2f}")
        print(f"IL: ${result['impermanent_loss_usd']:,.2f} ({result['impermanent_loss_percentage']:.2f}%)")
        print(f"Withdraw Amounts: {json.dumps(result['withdraw_amounts'], indent=2)}")
        
    # 3. Test Missing Prices (Simulate User Error)
    print("\nStep 3: Calculate IL with Missing Prices (DAI only)")
    il_payload_missing = il_payload.copy()
    il_payload_missing["priceAtWithdraw"] = {"DAI": 1.0} # Missing USDC, USDT
    
    res_missing = requests.post(f"{BASE_URL}/simulate/impermanent-loss", json=il_payload_missing)
    
    if res_missing.status_code == 200:
        result = res_missing.json()
        print(f"\nResult (Missing Prices):")
        print(f"Deposit Value: ${result['deposit_value_usd']:,.2f}")
        print(f"Withdraw Value: ${result['withdraw_value_usd']:,.2f}")
        print(f"IL: ${result['impermanent_loss_usd']:,.2f} ({result['impermanent_loss_percentage']:.2f}%)")
        
        if result['impermanent_loss_percentage'] < -10:
             print("\n✅ BUG REPRODUCED: Large negative IL due to missing prices.")
    else:
        print(f"Error: {res_missing.text}")

if __name__ == "__main__":
    test_il_bug_reproduction()
