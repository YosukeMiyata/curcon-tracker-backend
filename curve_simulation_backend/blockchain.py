"""
blockchain.py
Web3.pyを使用したブロックチェーンとの直接対話
"""
from web3 import Web3
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

RPC = os.environ.get('ETH_RPC_URL')
if not RPC:
    raise RuntimeError('ETH_RPC_URL not set in env')

w3 = Web3(Web3.HTTPProvider(RPC))

def get_latest_block_number():
    """最新のブロック番号を取得"""
    return w3.eth.block_number

def get_block_number_by_timestamp(timestamp: int, start_block: int | None = None, end_block: int | None = None) -> int:
    """
    二分探索でタイムスタンプに対応するブロック番号を取得
    block.timestamp >= timestamp となる最小のブロック番号を返す
    """
    if start_block is None:
        start_block = 0
    if end_block is None:
        end_block = get_latest_block_number()

    # 境界チェック
    start_ts = w3.eth.get_block(start_block).timestamp
    if start_ts >= timestamp:
        return start_block
    
    end_ts = w3.eth.get_block(end_block).timestamp
    if end_ts < timestamp:
        return end_block

    # 二分探索
    low = start_block
    high = end_block
    while low < high:
        mid = (low + high) // 2
        block = w3.eth.get_block(mid)
        if block.timestamp < timestamp:
            low = mid + 1
        else:
            high = mid
    return low

def call_contract_function(address: str, abi_fragment: list, function_name: str, args: list, block_identifier: int | None = None):
    """コントラクト関数を呼び出す"""
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi_fragment)
    func = getattr(contract.functions, function_name)(*args)
    if block_identifier is None:
        return func.call()
    return func.call(block_identifier=block_identifier)

def get_historical_balance(pool_address: str, index: int, block_number: int) -> int:
    """指定ブロックでのプールのコインバランスを取得"""
    # uint256を先に試行（新しいプールで一般的）
    try:
        abi = [{'name': 'balances', 'type': 'function', 'inputs': [{'type': 'uint256'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'balances', [index], block_identifier=block_number)
    except Exception:
        pass
    
    # int128を試行（古いプール）
    try:
        abi = [{'name': 'balances', 'type': 'function', 'inputs': [{'type': 'int128'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'balances', [index], block_identifier=block_number)
    except Exception:
        raise RuntimeError(f"balances({index}) not found with any known signature")

def get_historical_total_supply(token_address: str, block_number: int) -> int:
    """指定ブロックでのLPトークンの総供給量を取得"""
    abi = [{'name': 'totalSupply', 'type': 'function', 'inputs': [], 'outputs': [{'type': 'uint256'}]}]
    return call_contract_function(token_address, abi, 'totalSupply', [], block_identifier=block_number)

def get_lp_token_address(pool_address: str, block_number: int) -> str | None:
    """プールからLPトークンアドレスを取得（複数のメソッド名を試行）"""
    methods = ['token', 'lp_token', 'minter']
    for method in methods:
        try:
            abi = [{'name': method, 'type': 'function', 'inputs': [], 'outputs': [{'type': 'address'}]}]
            addr = call_contract_function(pool_address, abi, method, [], block_identifier=block_number)
            if addr and addr != '0x0000000000000000000000000000000000000000':
                return addr
        except Exception:
            continue
            
    # Registry経由で試行（古いプール用）
    REGISTRY_ADDRESS = '0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5'
    try:
        abi = [{'name': 'get_lp_token', 'type': 'function', 'inputs': [{'type': 'address'}], 'outputs': [{'type': 'address'}]}]
        addr = call_contract_function(REGISTRY_ADDRESS, abi, 'get_lp_token', [pool_address], block_identifier=block_number)
        if addr and addr != '0x0000000000000000000000000000000000000000':
            return addr
    except Exception:
        pass
        
    return None

def get_coin_address(pool_address: str, index: int, block_number: int) -> str:
    """プールの指定インデックスのコインアドレスを取得"""
    # uint256を先に試行（新しいプールで一般的）
    try:
        abi = [{'name': 'coins', 'type': 'function', 'inputs': [{'type': 'uint256'}], 'outputs': [{'type': 'address'}]}]
        return call_contract_function(pool_address, abi, 'coins', [index], block_identifier=block_number)
    except Exception:
        pass
    
    # int128を試行（古いプール）
    try:
        abi = [{'name': 'coins', 'type': 'function', 'inputs': [{'type': 'int128'}], 'outputs': [{'type': 'address'}]}]
        return call_contract_function(pool_address, abi, 'coins', [index], block_identifier=block_number)
    except Exception:
        raise RuntimeError(f"coins({index}) not found with any known signature")

def get_coin_decimals(token_address: str, block_number: int) -> int:
    """トークンのdecimalsを取得"""
    abi = [{'name': 'decimals', 'type': 'function', 'inputs': [], 'outputs': [{'type': 'uint8'}]}]
    return call_contract_function(token_address, abi, 'decimals', [], block_identifier=block_number)

def get_coin_symbol(token_address: str, block_number: int) -> str:
    """トークンのシンボルを取得"""
    abi = [{'name': 'symbol', 'type': 'function', 'inputs': [], 'outputs': [{'type': 'string'}]}]
    return call_contract_function(token_address, abi, 'symbol', [], block_identifier=block_number)

def try_calc_token_amount(pool_address: str, amounts: list[int], block_number: int) -> int:
    """
    calc_token_amountを複数のABI署名で試行
    TypeScriptの実装と同様に、動的配列、固定配列、deposit引数の有無を試す
    """
    # 動的配列 + deposit引数
    try:
        abi = [{'name': 'calc_token_amount', 'type': 'function', 'inputs': [{'type': 'uint256[]'}, {'type': 'bool'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'calc_token_amount', [amounts, True], block_identifier=block_number)
    except Exception:
        pass
    
    # 動的配列のみ
    try:
        abi = [{'name': 'calc_token_amount', 'type': 'function', 'inputs': [{'type': 'uint256[]'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'calc_token_amount', [amounts], block_identifier=block_number)
    except Exception:
        pass
    
    # 固定配列を試行（2〜8コイン）
    for n in range(2, 9):
        try:
            # deposit引数あり
            abi = [{'name': 'calc_token_amount', 'type': 'function', 'inputs': [{'type': f'uint256[{n}]'}, {'type': 'bool'}], 'outputs': [{'type': 'uint256'}]}]
            padded = list(amounts) + [0] * max(0, n - len(amounts))
            padded = padded[:n]
            return call_contract_function(pool_address, abi, 'calc_token_amount', [padded, True], block_identifier=block_number)
        except Exception:
            pass
        
        try:
            # deposit引数なし
            abi = [{'name': 'calc_token_amount', 'type': 'function', 'inputs': [{'type': f'uint256[{n}]'}], 'outputs': [{'type': 'uint256'}]}]
            padded = list(amounts) + [0] * max(0, n - len(amounts))
            padded = padded[:n]
            return call_contract_function(pool_address, abi, 'calc_token_amount', [padded], block_identifier=block_number)
        except Exception:
            pass
    
    raise RuntimeError('calc_token_amount not found with any known signature')

def try_calc_withdraw_one_coin(pool_address: str, lp_amount: int, index: int, block_number: int) -> int:
    """
    calc_withdraw_one_coinを複数のABI署名で試行
    int128とuint256の両方を試す
    """
    # int128
    try:
        abi = [{'name': 'calc_withdraw_one_coin', 'type': 'function', 'inputs': [{'type': 'uint256'}, {'type': 'int128'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'calc_withdraw_one_coin', [lp_amount, index], block_identifier=block_number)
    except Exception:
        pass
    
    # uint256
    try:
        abi = [{'name': 'calc_withdraw_one_coin', 'type': 'function', 'inputs': [{'type': 'uint256'}, {'type': 'uint256'}], 'outputs': [{'type': 'uint256'}]}]
        return call_contract_function(pool_address, abi, 'calc_withdraw_one_coin', [lp_amount, index], block_identifier=block_number)
    except Exception:
        pass
    
    raise RuntimeError('calc_withdraw_one_coin not found with any known signature')
