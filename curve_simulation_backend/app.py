#!/usr/bin/env python3
"""
Curve Simulation API
Web3.pyを使用した直接的なオンチェーンシミュレーションAPI
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import boto3
import uuid
import os
import logging
import traceback
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dotenv import load_dotenv
from pathlib import Path
import blockchain

# 環境変数読み込み
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# ログ設定
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API認証トークン
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN")

# 認証ミドルウェア
async def verify_token(authorization: Optional[str] = Header(None)):
    """
    Bearer token認証を検証
    API_SECRET_TOKENが設定されていない場合は認証をスキップ（開発用）
    """
    if not API_SECRET_TOKEN:
        # トークンが設定されていない場合は警告を出すが通過させる
        logger.warning("⚠️ API_SECRET_TOKEN not set - authentication disabled")
        return True
    
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # "Bearer <token>" 形式を想定
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication scheme. Use 'Bearer <token>'"
            )
        if token != API_SECRET_TOKEN:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Use 'Bearer <token>'"
        )
    
    return True

# FastAPIアプリ初期化（全エンドポイントに認証を適用）
app = FastAPI(
    title="Curve Simulation API",
    description="Web3.pyを使用した直接的なCurveシミュレーションAPI",
    version="2.0.0",
    dependencies=[Depends(verify_token)]  # 全エンドポイントに認証を適用
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# DynamoDB接続
try:
    dynamodb = boto3.resource(
        'dynamodb',
        region_name=os.getenv('AWS_REGION', 'ap-northeast-1')
    )
    simulations_table = dynamodb.Table('SimulationsHistory')
    logger.info("✅ DynamoDB接続成功")
except Exception as e:
    logger.error(f"❌ DynamoDB接続エラー: {e}")
    simulations_table = None


# ---------- Request Models ----------

class DepositRequest(BaseModel):
    poolAddress: str
    poolName: Optional[str] = None      # 表示名: USDFI+USDaf+ebUSD+BOLD
    factoryId: Optional[str] = None     # factory-stable-ng-564, oneway-14等
    lpTokenAddress: Optional[str] = None # フロントエンドから渡されるLPトークンアドレス
    timestamp: int                       # Past timestamp (UNIX)
    amounts: Dict[str, float]           # {symbol: amount} または {index: amount}
    poolMeta: Optional[Dict] = None     # PoolMeta情報（tokens, decimals, coinsAddresses等）
    calculateAdjustedLpPrice: bool = False  # TVL変動考慮フラグ
    tokenPrices: Optional[Dict[str, float]] = None  # トークン価格（TVL計算用）


class WithdrawRequest(BaseModel):
    poolAddress: str
    poolName: Optional[str] = None
    factoryId: Optional[str] = None
    lpTokenAddress: Optional[str] = None
    timestamp: int
    lpAmount: float
    withdrawToken: Optional[str] = None  # if None → proportional, else index as string
    poolMeta: Optional[Dict] = None     # PoolMeta情報
    withdrawTokens: Optional[List[str]] = None  # 複数トークン引き出し対応
    returnAllTokenAmounts: bool = False  # 全トークンの引き出し可能量を返す
    tokenPrices: Optional[Dict[str, float]] = None  # トークン価格（比例計算用）


class IdealRatioRequest(BaseModel):
    poolAddress: str
    poolName: Optional[str] = None
    factoryId: Optional[str] = None
    lpTokenAddress: Optional[str] = None
    timestamp: int


class ImpermanentLossRequest(BaseModel):
    poolAddress: str
    poolName: Optional[str] = None
    factoryId: Optional[str] = None
    lpTokenAddress: Optional[str] = None
    timestamp_deposit: int
    timestamp_withdraw: int
    depositAmounts: Dict[str, float]      # {symbol: amount}
    priceAtDeposit: Dict[str, float]      # {symbol: price_usd}
    priceAtWithdraw: Dict[str, float]     # {symbol: price_usd}
    lpTokens: float                       # depositで得たLP量


class BatchDepositWithdrawRequest(BaseModel):
    """デポジット+引き出しを一括で実行するリクエスト"""
    poolAddress: str
    poolName: Optional[str] = None
    factoryId: Optional[str] = None
    lpTokenAddress: Optional[str] = None
    poolMeta: Optional[Dict] = None
    
    # デポジット情報
    depositTimestamp: int
    depositAmounts: Dict[str, float]
    depositTokenPrices: Optional[Dict[str, float]] = None
    
    # 引き出し情報
    withdrawTimestamp: int
    withdrawTokens: List[str]
    withdrawTokenPrices: Optional[Dict[str, float]] = None


# ---------- DynamoDB保存関数 ----------

def convert_floats_to_decimals(obj):
    """DynamoDB用にfloatをDecimalに変換する再帰関数"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(v) for v in obj]
    return obj

def save_simulation_result(
    pool_id: str,
    pool_name: str,
    factory_id: str,
    request_data: dict,
    result_data: dict,
    status: str = "success",
    diagnostics: Optional[dict] = None
) -> str:
    """シミュレーション結果をDynamoDBに保存"""
    if simulations_table is None:
        logger.warning("⚠️ DynamoDBテーブルが利用できません")
        return "no-db"
    
    try:
        jst = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst)
        now_utc = datetime.now(timezone.utc)
        
        # TTL: 30日後
        expires_at = int((now_utc + timedelta(days=30)).timestamp())
        
        simulation_id = uuid.uuid4().hex
        
        # floatをDecimalに変換
        item_data = {
            'request': request_data,
            'result': result_data,
            'diagnostics': diagnostics or {}
        }
        item_data = convert_floats_to_decimals(item_data)
        
        item = {
            'pool_id': pool_id,
            'timestamp': now_jst.isoformat(),
            'timezone': 'JST',
            'pool': pool_name,
            'factory_id': factory_id,
            'simulation_id': simulation_id,
            'request': item_data['request'],
            'result': item_data['result'],
            'diagnostics': item_data['diagnostics'],
            'status': status,
            'data_source': 'curve_simulation_api',
            'datetime': now_utc.isoformat(),
            'created_at': now_jst.isoformat(),
            'expires_at': expires_at
        }
        
        simulations_table.put_item(Item=item)
        logger.info(f"✅ シミュレーション結果保存成功: {simulation_id}")
        return simulation_id
        
    except Exception as e:
        logger.error(f"❌ DynamoDB保存エラー: {e}")
        return "error"


# ---------- ヘルパー関数 ----------

def get_pool_info(pool_address: str, block_number: int, lp_token_address_input: Optional[str] = None) -> dict:
    """プールの基本情報を取得"""
    # コイン情報を取得（最大8コインまで試行）
    coins = []
    balances = []
    decimals_list = []
    symbols = []
    
    for i in range(8):
        try:
            logger.info(f"  Trying to get coin {i}...")
            coin_addr = blockchain.get_coin_address(pool_address, i, block_number)
            logger.info(f"  Coin {i} address: {coin_addr}")
            
            balance = blockchain.get_historical_balance(pool_address, i, block_number)
            logger.info(f"  Coin {i} balance: {balance}")
            
            decimals = blockchain.get_coin_decimals(coin_addr, block_number)
            logger.info(f"  Coin {i} decimals: {decimals}")
            
            symbol = blockchain.get_coin_symbol(coin_addr, block_number)
            logger.info(f"  Coin {i} symbol: {symbol}")
            
            coins.append(coin_addr)
            balances.append(int(balance))
            decimals_list.append(decimals)
            symbols.append(symbol)
        except Exception as e:
            logger.info(f"  Coin {i} not found (expected for end of list): {e}")
            break
    
    if len(coins) == 0:
        raise RuntimeError("No coins found in pool")
    
    # LPトークンアドレスと総供給量を取得
    # LPトークンアドレスと総供給量を取得
    lp_token_addr = lp_token_address_input
    if not lp_token_addr:
        lp_token_addr = blockchain.get_lp_token_address(pool_address, block_number)
    
    lp_supply = None
    
    if lp_token_addr:
        logger.info(f"  LP Token address found: {lp_token_addr}")
        try:
            lp_supply = blockchain.get_historical_total_supply(lp_token_addr, block_number)
            logger.info(f"  LP Supply: {lp_supply}")
        except Exception as e:
            logger.warning(f"  Failed to get totalSupply from {lp_token_addr}: {e}")
    else:
        logger.warning("  LP Token address not found via standard methods")

    # フォールバック: プールアドレス自体でtotalSupplyを試行
    if lp_supply is None:
        try:
            logger.info("  Trying to get totalSupply from pool address...")
            lp_supply = blockchain.get_historical_total_supply(pool_address, block_number)
            if lp_supply:
                logger.info(f"  LP Supply found from pool address: {lp_supply}")
                if not lp_token_addr:
                    lp_token_addr = pool_address
        except Exception as e:
            logger.warning(f"  Failed to get totalSupply from pool address: {e}")
    
    return {
        'coins': coins,
        'balances': balances,
        'decimals': decimals_list,
        'symbols': symbols,
        'lp_token_address': lp_token_addr,
        'lp_supply': int(lp_supply) if lp_supply else None,
        'num_coins': len(coins)
    }


# ---------- ヘルパー関数（TVL変動考慮・フォールバック計算） ----------

def calculate_tvl_adjustment(
    pool_info: dict,
    deposit_amounts_wei: List[int],
    token_prices: Optional[Dict[str, float]],
    lp_tokens_received_wei: int,
    lp_decimals: int = 18
) -> Optional[Dict]:
    """
    TVL変動を考慮した調整後LP価格を計算
    
    Args:
        pool_info: get_pool_infoの結果
        deposit_amounts_wei: デポジット量（wei）
        token_prices: トークン価格（USD）{symbol: price}
        lp_tokens_received_wei: 取得したLPトークン量（wei）
        lp_decimals: LPトークンのdecimals
    
    Returns:
        TVL分析結果 or None
    """
    if not token_prices or not pool_info.get('lp_supply'):
        return None
    
    try:
        symbols = pool_info.get('symbols', [])
        balances = pool_info.get('balances', [])
        decimals = pool_info.get('decimals', [])
        lp_supply = pool_info.get('lp_supply')
        
        # 元のTVL（USD）を計算
        original_tvl_usd = 0.0
        for i, symbol in enumerate(symbols):
            if i < len(balances) and i < len(decimals):
                balance_decimal = float(balances[i]) / (10 ** decimals[i])
                price = token_prices.get(symbol)
                if price is None:
                    logger.warning(f"⚠️ Missing price for {symbol} in TVL calculation. Treating as 0.")
                    price = 0
                original_tvl_usd += balance_decimal * price
        
        # デポジット価値（USD）を計算
        deposit_value_usd = 0.0
        for i, symbol in enumerate(symbols):
            if i < len(deposit_amounts_wei) and i < len(decimals):
                deposit_decimal = float(deposit_amounts_wei[i]) / (10 ** decimals[i])
                price = token_prices.get(symbol, 0)  # デポジット価値計算では0でOK（デポジットしていないトークンは0）
                deposit_value_usd += deposit_decimal * price
        
        # 調整後のTVLとLP供給量
        adjusted_tvl_usd = original_tvl_usd + deposit_value_usd
        lp_supply_decimal = float(lp_supply) / (10 ** lp_decimals)
        lp_received_decimal = float(lp_tokens_received_wei) / (10 ** lp_decimals)
        adjusted_lp_supply = lp_supply_decimal + lp_received_decimal
        
        # LP価格を計算
        original_lp_price = original_tvl_usd / lp_supply_decimal if lp_supply_decimal > 0 else 0
        adjusted_lp_price = adjusted_tvl_usd / adjusted_lp_supply if adjusted_lp_supply > 0 else 0
        
        return {
            "original_tvl_usd": original_tvl_usd,
            "deposit_value_usd": deposit_value_usd,
            "adjusted_tvl_usd": adjusted_tvl_usd,
            "original_lp_supply": lp_supply_decimal,
            "adjusted_lp_supply": adjusted_lp_supply,
            "original_lp_price": original_lp_price,
            "adjusted_lp_price": adjusted_lp_price
        }
    except Exception as e:
        logger.error(f"Error calculating TVL adjustment: {e}")
        return None


def calculate_lp_tokens_fallback(
    deposit_amounts_wei: List[int],
    pool_info: dict,
    token_prices: Optional[Dict[str, float]],
    lp_decimals: int = 18
) -> tuple[int, str]:
    """
    フォールバック計算（calc_token_amount失敗時）
    
    Returns:
        (lp_amount_wei, calculation_method)
        calculation_method: "proportional" | "usd_value"
    """
    # 単一トークンデポジットかどうかを確認
    non_zero_deposits = [amt for amt in deposit_amounts_wei if amt > 0]
    is_single_token = len(non_zero_deposits) == 1
    
    if is_single_token and token_prices and pool_info.get('lp_supply'):
        # USD価値 / LP価格
        symbols = pool_info.get('symbols', [])
        decimals = pool_info.get('decimals', [])
        balances = pool_info.get('balances', [])
        lp_supply = pool_info.get('lp_supply')
        
        # デポジット価値（USD）
        deposit_value_usd = 0.0
        for i, amt_wei in enumerate(deposit_amounts_wei):
            if amt_wei > 0 and i < len(symbols) and i < len(decimals):
                amt_decimal = float(amt_wei) / (10 ** decimals[i])
                price = token_prices.get(symbols[i], 0)
                deposit_value_usd += amt_decimal * price
        
        # 元のLP価格を計算
        original_tvl_usd = 0.0
        for i, symbol in enumerate(symbols):
            if i < len(balances) and i < len(decimals):
                balance_decimal = float(balances[i]) / (10 ** decimals[i])
                price = token_prices.get(symbol, 0)
                original_tvl_usd += balance_decimal * price
        
        lp_supply_decimal = float(lp_supply) / (10 ** lp_decimals)
        lp_price = original_tvl_usd / lp_supply_decimal if lp_supply_decimal > 0 else 1.0
        
        lp_amount_decimal = deposit_value_usd / lp_price if lp_price > 0 else 0
        lp_amount_wei = int(lp_amount_decimal * (10 ** lp_decimals))
        
        return (lp_amount_wei, "usd_value")
    else:
        # 比例計算
        balances = pool_info.get('balances', [])
        lp_supply = pool_info.get('lp_supply')
        decimals = pool_info.get('decimals', [])
        
        if not balances or not lp_supply:
            return (0, "proportional")
        
        # 各トークンについて、投入量に対するLPトークン量を計算し、最小値を取る
        min_lp_tokens = None
        
        for i, amt_wei in enumerate(deposit_amounts_wei):
            if amt_wei > 0 and i < len(balances):
                balance_bn = int(balances[i])
                if balance_bn == 0:
                    continue
                
                # LPトークン量 = (デポジット量 * LP供給量) / 残高
                lp_tokens_bn = (amt_wei * int(lp_supply)) // balance_bn
                
                if min_lp_tokens is None or lp_tokens_bn < min_lp_tokens:
                    min_lp_tokens = lp_tokens_bn
        
        return (min_lp_tokens or 0, "proportional")


# ---------- API Endpoints ----------

@app.get("/")
async def root():
    return {
        "service": "Curve Simulation API",
        "version": "2.0.0",
        "status": "running",
        "implementation": "web3.py direct"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "dynamodb": "connected" if simulations_table else "disconnected",
        "eth_rpc": "configured" if os.getenv('ETH_RPC_URL') else "not configured",
        "library": "web3.py"
    }

@app.post("/simulate/deposit")
async def simulate_deposit(req: DepositRequest):
    """
    デポジットシミュレーション
    指定されたタイムスタンプでのデポジットをシミュレート
    """
    import time
    start_time = time.time()
    
    pool_id = req.poolAddress.lower()
    pool_name = req.poolName or req.poolAddress
    factory_id = req.factoryId or pool_id
    
    try:
        # タイムスタンプからブロック番号を取得
        block_start = time.time()
        block_number = blockchain.get_block_number_by_timestamp(req.timestamp)
        block_time = time.time() - block_start
        logger.info(f"📍 Timestamp {req.timestamp} -> Block {block_number} ({block_time:.2f}s)")
        
        # プール情報を取得
        pool_info_start = time.time()
        pool_info = get_pool_info(req.poolAddress, block_number, req.lpTokenAddress)
        pool_info_time = time.time() - pool_info_start
        
        # デポジット額を配列に変換
        amounts_arr = []
        for i in range(pool_info['num_coins']):
            amount = 0.0
            if str(i) in req.amounts:
                amount = req.amounts[str(i)]
            elif pool_info['symbols'][i] in req.amounts:
                amount = req.amounts[pool_info['symbols'][i]]
            
            amount_wei = int(amount * (10 ** pool_info['decimals'][i]))
            amounts_arr.append(amount_wei)
        
        # calc_token_amountを試行
        calc_start = time.time()
        lp_amount = None
        calc_method = "contract"
        try:
            lp_amount = blockchain.try_calc_token_amount(req.poolAddress, amounts_arr, block_number)
        except Exception as e:
            logger.warning(f"⚠️ calc_token_amount failed: {e}, using fallback")
            # 新しいフォールバック計算を使用
            lp_amount, calc_method = calculate_lp_tokens_fallback(
                amounts_arr,
                pool_info,
                req.tokenPrices
            )
        calc_time = time.time() - calc_start
        
        # レスポンスを構築
        lp_decimals = 18
        lp_amount_decimal = float(lp_amount) / (10 ** lp_decimals) if lp_amount else 0
        
        result = {
            'block_number': block_number,
            'pool_info': {
                'symbols': pool_info['symbols'],
                'balances': pool_info['balances'],
                'lp_supply': pool_info['lp_supply']
            },
            'deposit_amounts_wei': amounts_arr,
            'lp_amount_received': int(lp_amount) if lp_amount else 0,
            'lp_amount_received_decimal': lp_amount_decimal,
            'calculation_method': calc_method
        }
        
        # TVL変動考慮が要求された場合
        if req.calculateAdjustedLpPrice and req.tokenPrices and lp_amount:
            tvl_analysis = calculate_tvl_adjustment(
                pool_info,
                amounts_arr,
                req.tokenPrices,
                int(lp_amount),
                lp_decimals
            )
            if tvl_analysis:
                result['tvl_analysis'] = tvl_analysis
        
        total_time = time.time() - start_time
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=pool_name,
            factory_id=factory_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success",
            diagnostics={
                'execution_time_seconds': round(total_time, 3),
                'block_lookup_time': round(block_time, 3),
                'pool_info_time': round(pool_info_time, 3),
                'calculation_time': round(calc_time, 3)
            }
        )
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        msg = f"❌ デポジットシミュレーションエラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=pool_id,
                pool_name=pool_name,
                factory_id=factory_id,
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={
                    "error": str(e),
                    'execution_time_seconds': round(total_time, 3)
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate/withdraw")
async def simulate_withdraw(req: WithdrawRequest):
    """
    引き出しシミュレーション
    指定されたタイムスタンプでの引き出しをシミュレート
    """
    import time
    start_time = time.time()
    
    pool_id = req.poolAddress.lower()
    pool_name = req.poolName or req.poolAddress
    factory_id = req.factoryId or pool_id
    
    try:
        # タイムスタンプからブロック番号を取得
        block_start = time.time()
        block_number = blockchain.get_block_number_by_timestamp(req.timestamp)
        block_time = time.time() - block_start
        logger.info(f"📍 Timestamp {req.timestamp} -> Block {block_number} ({block_time:.2f}s)")
        
        # プール情報を取得
        pool_info_start = time.time()
        pool_info = get_pool_info(req.poolAddress, block_number, req.lpTokenAddress)
        pool_info_time = time.time() - pool_info_start
        
        lp_amount_wei = int(req.lpAmount * (10 ** 18))  # LPトークンは通常18 decimals
        
        withdraw_result = {}
        calc_method = "contract"
        all_token_amounts = None
        
        calc_start = time.time()
        
        # 全トークンの比例引き出し量を計算（returnAllTokenAmounts用）
        if req.returnAllTokenAmounts and pool_info['lp_supply']:
            all_token_amounts = {}
            for i in range(pool_info['num_coins']):
                amount_wei = (pool_info['balances'][i] * lp_amount_wei) // pool_info['lp_supply']
                symbol = pool_info['symbols'][i]
                decimals = pool_info['decimals'][i]
                all_token_amounts[symbol] = {
                    "wei": str(amount_wei),
                    "decimal": float(amount_wei) / (10 ** decimals)
                }
        
        # withdrawTokensが指定されている場合（複数トークン引き出し）
        if req.withdrawTokens and len(req.withdrawTokens) > 0:
            # 単一トークンかつ全額返却でない場合は、calc_withdraw_one_coinを使用
            if len(req.withdrawTokens) == 1 and not req.returnAllTokenAmounts:
                symbol = req.withdrawTokens[0]
                if symbol in pool_info['symbols']:
                    idx = pool_info['symbols'].index(symbol)
                    try:
                        amount_wei = blockchain.try_calc_withdraw_one_coin(req.poolAddress, lp_amount_wei, idx, block_number)
                        withdraw_result[symbol] = int(amount_wei)
                        calc_method = "one_coin"
                    except Exception as e:
                        logger.warning(f"⚠️ calc_withdraw_one_coin failed: {e}, using fallback")
                        calc_method = "fallback"
                        if pool_info['lp_supply']:
                            amount_wei = (pool_info['balances'][idx] * lp_amount_wei) // pool_info['lp_supply']
                            withdraw_result[symbol] = int(amount_wei)
                        else:
                            withdraw_result[symbol] = 0
                else:
                     logger.warning(f"⚠️ Token {symbol} not found in pool symbols: {pool_info['symbols']}")
            else:
                # 複数トークンまたは全額返却の場合は比例引き出し
                calc_method = "proportional"
                if pool_info['lp_supply'] is None:
                    raise RuntimeError('LP supply required for proportional withdraw')
                
                # 全トークンの比例引き出し量を計算
                all_amounts_wei = {}
                for i in range(pool_info['num_coins']):
                    amount_wei = (pool_info['balances'][i] * lp_amount_wei) // pool_info['lp_supply']
                    all_amounts_wei[pool_info['symbols'][i]] = int(amount_wei)
                
                # 指定されたトークンのみを抽出
                for symbol in req.withdrawTokens:
                    if symbol in all_amounts_wei:
                        withdraw_result[symbol] = all_amounts_wei[symbol]
        
        # withdrawTokenが指定されている場合（単一トークン引き出し - 互換性のため維持）
        elif req.withdrawToken is not None:
            # 単一コイン引き出し
            try:
                idx = int(req.withdrawToken)
                amount_wei = blockchain.try_calc_withdraw_one_coin(req.poolAddress, lp_amount_wei, idx, block_number)
                withdraw_result[pool_info['symbols'][idx]] = int(amount_wei)
            except Exception as e:
                logger.warning(f"⚠️ calc_withdraw_one_coin failed: {e}, using fallback")
                calc_method = "fallback"
                # フォールバック: 比例計算
                if pool_info['lp_supply']:
                    idx = int(req.withdrawToken)
                    amount_wei = (pool_info['balances'][idx] * lp_amount_wei) // pool_info['lp_supply']
                    withdraw_result[pool_info['symbols'][idx]] = int(amount_wei)
                else:
                    withdraw_result[pool_info['symbols'][idx]] = 0
        else:
            # 比例引き出し（全トークン）
            calc_method = "proportional"
            if pool_info['lp_supply'] is None:
                raise RuntimeError('LP supply required for proportional withdraw')
            
            for i in range(pool_info['num_coins']):
                amount_wei = (pool_info['balances'][i] * lp_amount_wei) // pool_info['lp_supply']
                withdraw_result[pool_info['symbols'][i]] = int(amount_wei)
        
        calc_time = time.time() - calc_start
        
        total_time = time.time() - start_time
        
        result = {
            'block_number': block_number,
            'pool_info': {
                'symbols': pool_info['symbols'],
                'balances': pool_info['balances'],
                'lp_supply': pool_info['lp_supply']
            },
            'lp_amount_wei': lp_amount_wei,
            'withdraw_amounts_wei': withdraw_result,
            'calculation_method': calc_method
        }
        
        # withdraw_amounts_decimalを追加
        withdraw_amounts_decimal = {}
        for symbol, amount_wei in withdraw_result.items():
            idx = pool_info['symbols'].index(symbol)
            decimals = pool_info['decimals'][idx]
            withdraw_amounts_decimal[symbol] = float(amount_wei) / (10 ** decimals)
        result['withdraw_amounts_decimal'] = withdraw_amounts_decimal
        
        # 全トークン量を追加（要求された場合）
        if all_token_amounts:
            result['all_token_amounts'] = all_token_amounts
        
        total_time = time.time() - start_time
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=pool_name,
            factory_id=factory_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success",
            diagnostics={
                'execution_time_seconds': round(total_time, 3),
                'block_lookup_time': round(block_time, 3),
                'pool_info_time': round(pool_info_time, 3),
                'calculation_time': round(calc_time, 3)
            }
        )
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        msg = f"❌ 引き出しシミュレーションエラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=pool_id,
                pool_name=pool_name,
                factory_id=factory_id,
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={
                    "error": str(e),
                    'execution_time_seconds': round(total_time, 3)
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))
        
        result = {
            'block_number': block_number,
            'pool_info': {
                'symbols': pool_info['symbols'],
                'balances': pool_info['balances'],
                'lp_supply': pool_info['lp_supply']
            },
            'lp_amount_wei': lp_amount_wei,
            'withdraw_amounts_wei': withdraw_result,
            'calculation_method': calc_method
        }
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=req.poolAddress,
            factory_id=pool_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success"
        )
        
        return result
        
    except Exception as e:
        msg = f"❌ 引き出しシミュレーションエラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=req.poolAddress.lower(),
                pool_name=req.poolAddress,
                factory_id="unknown",
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={"error": str(e)}
            )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate/ideal-ratios")
async def simulate_ideal_ratios(req: IdealRatioRequest):
    """
    理想的な比率を計算
    指定されたタイムスタンプでのプールの理想的なデポジット比率を返す
    """
    import time
    start_time = time.time()
    
    pool_id = req.poolAddress.lower()
    pool_name = req.poolName or req.poolAddress
    factory_id = req.factoryId or pool_id
    
    try:
        # タイムスタンプからブロック番号を取得
        block_start = time.time()
        block_number = blockchain.get_block_number_by_timestamp(req.timestamp)
        block_time = time.time() - block_start
        logger.info(f"📍 Timestamp {req.timestamp} -> Block {block_number} ({block_time:.2f}s)")
        
        # プール情報を取得
        pool_info_start = time.time()
        pool_info = get_pool_info(req.poolAddress, block_number, req.lpTokenAddress)
        pool_info_time = time.time() - pool_info_start
        
        # 理想比率 = 現在のバランス比率（decimalsで正規化）
        calc_start = time.time()
        normalized_balances = []
        for i in range(pool_info['num_coins']):
            normalized = pool_info['balances'][i] / (10 ** pool_info['decimals'][i])
            normalized_balances.append(normalized)
        
        total_value = sum(normalized_balances)
        ratios = {}
        for i in range(pool_info['num_coins']):
            ratio = normalized_balances[i] / total_value if total_value > 0 else 0
            ratios[pool_info['symbols'][i]] = ratio
        calc_time = time.time() - calc_start
        
        total_time = time.time() - start_time
        
        result = {
            'block_number': block_number,
            'pool_info': {
                'symbols': pool_info['symbols'],
                'balances': pool_info['balances'],
                'lp_supply': pool_info['lp_supply']
            },
            'ideal_ratios': ratios
        }
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=pool_name,
            factory_id=factory_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success",
            diagnostics={
                'execution_time_seconds': round(total_time, 3),
                'block_lookup_time': round(block_time, 3),
                'pool_info_time': round(pool_info_time, 3),
                'calculation_time': round(calc_time, 3)
            }
        )
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        msg = f"❌ 理想比率計算エラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=pool_id,
                pool_name=pool_name,
                factory_id=factory_id,
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={
                    "error": str(e),
                    'execution_time_seconds': round(total_time, 3)
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate/impermanent-loss")
async def simulate_impermanent_loss(req: ImpermanentLossRequest):
    """
    インパーマネントロス計算
    デポジット時と引き出し時の価値を比較
    """
    import time
    start_time = time.time()
    
    pool_id = req.poolAddress.lower()
    pool_name = req.poolName or req.poolAddress
    factory_id = req.factoryId or pool_id
    
    try:
        calc_start = time.time()
        # デポジット時の価値計算
        deposit_value_usd = sum(
            req.depositAmounts.get(symbol, 0) * req.priceAtDeposit.get(symbol, 0)
            for symbol in req.depositAmounts.keys()
        )
        
        # 引き出し時のブロック番号を取得
        block_lookup_start = time.time()
        block_number = blockchain.get_block_number_by_timestamp(req.timestamp_withdraw)
        block_time = time.time() - block_lookup_start
        
        pool_info_start = time.time()
        pool_info = get_pool_info(req.poolAddress, block_number, req.lpTokenAddress)
        pool_info_time = time.time() - pool_info_start
        
        # LPトークンを引き出した場合の各コインの量を計算（比例引き出し）
        lp_amount_wei = int(req.lpTokens * (10 ** 18))
        withdraw_amounts = {}
        
        if pool_info['lp_supply']:
            for i in range(pool_info['num_coins']):
                amount_wei = (pool_info['balances'][i] * lp_amount_wei) // pool_info['lp_supply']
                amount = amount_wei / (10 ** pool_info['decimals'][i])
                withdraw_amounts[pool_info['symbols'][i]] = amount
        
        # 引き出し時の価値計算
        withdraw_value_usd = 0.0
        for symbol in withdraw_amounts.keys():
            price = req.priceAtWithdraw.get(symbol)
            if price is None:
                logger.warning(f"⚠️ Missing withdraw price for {symbol}. Treating as 0.")
                price = 0
            withdraw_value_usd += withdraw_amounts.get(symbol, 0) * price
        
        # HODLした場合の価値計算
        hodl_value_usd = sum(
            req.depositAmounts.get(symbol, 0) * req.priceAtWithdraw.get(symbol, 0)
            for symbol in req.depositAmounts.keys()
        )
        
        # インパーマネントロス計算
        il_usd = withdraw_value_usd - hodl_value_usd
        il_percentage = (il_usd / hodl_value_usd * 100) if hodl_value_usd > 0 else 0
        calc_time = (time.time() - calc_start) - block_time - pool_info_time
        
        total_time = time.time() - start_time
        
        result = {
            'block_number': block_number,
            'deposit_value_usd': deposit_value_usd,
            'withdraw_value_usd': withdraw_value_usd,
            'hodl_value_usd': hodl_value_usd,
            'impermanent_loss_usd': il_usd,
            'impermanent_loss_percentage': il_percentage,
            'withdraw_amounts': withdraw_amounts
        }
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=pool_name,
            factory_id=factory_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success",
            diagnostics={
                'execution_time_seconds': round(total_time, 3),
                'block_lookup_time': round(block_time, 3),
                'pool_info_time': round(pool_info_time, 3),
                'calculation_time': round(calc_time, 3)
            }
        )
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        msg = f"❌ インパーマネントロス計算エラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=pool_id,
                pool_name=pool_name,
                factory_id=factory_id,
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={
                    "error": str(e),
                    'execution_time_seconds': round(total_time, 3)
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulate/batch-deposit-withdraw")
async def simulate_batch_deposit_withdraw(req: BatchDepositWithdrawRequest):
    """
    デポジット+引き出しを一括で実行
    運用シミュレーション用の効率的なエンドポイント
    """
    import time
    start_time = time.time()
    
    pool_id = req.poolAddress.lower()
    pool_name = req.poolName or req.poolAddress
    factory_id = req.factoryId or pool_id
    
    try:
        # デポジットシミュレーション
        deposit_block_start = time.time()
        deposit_block_number = blockchain.get_block_number_by_timestamp(req.depositTimestamp)
        deposit_block_time = time.time() - deposit_block_start
        
        deposit_pool_info_start = time.time()
        deposit_pool_info = get_pool_info(req.poolAddress, deposit_block_number, req.lpTokenAddress)
        deposit_pool_info_time = time.time() - deposit_pool_info_start
        
        # デポジット額を配列に変換
        deposit_amounts_arr = []
        for i in range(deposit_pool_info['num_coins']):
            amount = 0.0
            symbol = deposit_pool_info['symbols'][i]
            if str(i) in req.depositAmounts:
                amount = req.depositAmounts[str(i)]
            elif symbol in req.depositAmounts:
                amount = req.depositAmounts[symbol]
            
            amount_wei = int(amount * (10 ** deposit_pool_info['decimals'][i]))
            deposit_amounts_arr.append(amount_wei)
        
        # calc_token_amountを試行
        deposit_calc_start = time.time()
        lp_amount = None
        deposit_calc_method = "contract"
        try:
            lp_amount = blockchain.try_calc_token_amount(req.poolAddress, deposit_amounts_arr, deposit_block_number)
        except Exception as e:
            logger.warning(f"⚠️ calc_token_amount failed: {e}, using fallback")
            lp_amount, deposit_calc_method = calculate_lp_tokens_fallback(
                deposit_amounts_arr,
                deposit_pool_info,
                req.depositTokenPrices
            )
        deposit_calc_time = time.time() - deposit_calc_start
        
        lp_decimals = 18
        lp_amount_decimal = float(lp_amount) / (10 ** lp_decimals) if lp_amount else 0
        
        # TVL変動考慮
        adjusted_lp_price = None
        if req.depositTokenPrices and lp_amount:
            tvl_analysis = calculate_tvl_adjustment(
                deposit_pool_info,
                deposit_amounts_arr,
                req.depositTokenPrices,
                int(lp_amount),
                lp_decimals
            )
            if tvl_analysis:
                adjusted_lp_price = tvl_analysis.get('adjusted_lp_price')
        
        # 引き出しシミュレーション
        withdraw_block_start = time.time()
        withdraw_block_number = blockchain.get_block_number_by_timestamp(req.withdrawTimestamp)
        withdraw_block_time = time.time() - withdraw_block_start
        
        withdraw_pool_info_start = time.time()
        withdraw_pool_info = get_pool_info(req.poolAddress, withdraw_block_number, req.lpTokenAddress)
        withdraw_pool_info_time = time.time() - withdraw_pool_info_start
        
        lp_amount_wei = int(lp_amount) if lp_amount else 0
        
        # 複数トークン引き出し
        withdraw_calc_start = time.time()
        withdraw_result = {}
        withdraw_calc_method = "proportional"
        
        # 単一トークン引き出しの場合（バッチリクエストにはreturnAllTokenAmountsがないため、常に単一トークン指定ならone_coinとみなす）
        if len(req.withdrawTokens) == 1:
            symbol = req.withdrawTokens[0]
            if symbol in withdraw_pool_info['symbols']:
                idx = withdraw_pool_info['symbols'].index(symbol)
                try:
                    amount_wei = blockchain.try_calc_withdraw_one_coin(req.poolAddress, lp_amount_wei, idx, withdraw_block_number)
                    withdraw_result[symbol] = int(amount_wei)
                    withdraw_calc_method = "one_coin"
                except Exception as e:
                    logger.warning(f"⚠️ calc_withdraw_one_coin failed in batch: {e}, using fallback")
                    withdraw_calc_method = "fallback"
                    if withdraw_pool_info['lp_supply']:
                        amount_wei = (withdraw_pool_info['balances'][idx] * lp_amount_wei) // withdraw_pool_info['lp_supply']
                        withdraw_result[symbol] = int(amount_wei)
                    else:
                        withdraw_result[symbol] = 0
            else:
                 logger.warning(f"⚠️ Token {symbol} not found in pool symbols: {withdraw_pool_info['symbols']}")
        
        elif withdraw_pool_info['lp_supply']:
            # 全トークンの比例引き出し量を計算
            all_amounts_wei = {}
            for i in range(withdraw_pool_info['num_coins']):
                amount_wei = (withdraw_pool_info['balances'][i] * lp_amount_wei) // withdraw_pool_info['lp_supply']
                all_amounts_wei[withdraw_pool_info['symbols'][i]] = int(amount_wei)
            
            # 指定されたトークンのみを抽出
            for symbol in req.withdrawTokens:
                if symbol in all_amounts_wei:
                    withdraw_result[symbol] = all_amounts_wei[symbol]
        
        withdraw_calc_time = time.time() - withdraw_calc_start
        
        # withdraw_amounts_decimalを計算
        withdraw_amounts_decimal = {}
        for symbol, amount_wei in withdraw_result.items():
            idx = withdraw_pool_info['symbols'].index(symbol)
            decimals = withdraw_pool_info['decimals'][idx]
            withdraw_amounts_decimal[symbol] = float(amount_wei) / (10 ** decimals)
        
        total_time = time.time() - start_time
        
        result = {
            'deposit': {
                'block_number': deposit_block_number,
                'lp_amount_received': lp_amount_wei,
                'lp_amount_received_decimal': lp_amount_decimal,
                'adjusted_lp_price': adjusted_lp_price,
                'calculation_method': deposit_calc_method
            },
            'withdraw': {
                'block_number': withdraw_block_number,
                'withdraw_amounts_wei': withdraw_result,
                'withdraw_amounts_decimal': withdraw_amounts_decimal,
                'calculation_method': withdraw_calc_method
            },
            'execution_time_seconds': round(total_time, 3)
        }
        
        # DynamoDBに保存
        save_simulation_result(
            pool_id=pool_id,
            pool_name=pool_name,
            factory_id=factory_id,
            request_data=req.model_dump(),
            result_data=result,
            status="success",
            diagnostics={
                'execution_time_seconds': round(total_time, 3),
                'deposit_block_lookup_time': round(deposit_block_time, 3),
                'deposit_pool_info_time': round(deposit_pool_info_time, 3),
                'deposit_calculation_time': round(deposit_calc_time, 3),
                'withdraw_block_lookup_time': round(withdraw_block_time, 3),
                'withdraw_pool_info_time': round(withdraw_pool_info_time, 3),
                'withdraw_calculation_time': round(withdraw_calc_time, 3)
            }
        )
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        msg = f"❌ バッチシミュレーションエラー: {e}\n{traceback.format_exc()}"
        logger.error(msg)
        print(msg)
        
        if simulations_table:
            save_simulation_result(
                pool_id=pool_id,
                pool_name=pool_name,
                factory_id=factory_id,
                request_data=req.model_dump(),
                result_data={},
                status="error",
                diagnostics={
                    "error": str(e),
                    'execution_time_seconds': round(total_time, 3)
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
