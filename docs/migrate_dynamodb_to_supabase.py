#!/usr/bin/env python3
"""
Migrate DynamoDB tables to Supabase (PostgreSQL).

Usage:
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
  AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=ap-northeast-1 \
  python docs/migrate_dynamodb_to_supabase.py --tables ConvexPoolHistory,PoolLatest
"""

import argparse
import os
import time
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List

import boto3
from supabase import create_client


def normalize_decimal(value: Decimal) -> Any:
    if value % 1 == 0:
        return int(value)
    return float(value)


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return normalize_decimal(value)
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in value.items()}
    return value


def normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        if value and isinstance(value[0], dict) and "S" in value[0]:
            return [v.get("S") for v in value if isinstance(v, dict)]
        return [str(v) for v in value]
    return [str(value)]


def parse_date(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    return value


def build_item_with_raw(item: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_value(item)


def map_convex_pool_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id": item.get("pool_id"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool_name": item.get("Pool"),
        "factory_id": item.get("factory_id"),
        "current_vapr": item.get("Current_vAPR"),
        "projected_vapr": item.get("Projected_vAPR"),
        "tvl": item.get("TVL"),
        "vecrv_boost": item.get("veCRV_boost"),
        "remarks": item.get("Remarks"),
        "current_vapr_numeric": normalize_value(item.get("current_vapr_numeric")),
        "projected_vapr_numeric": normalize_value(item.get("projected_vapr_numeric")),
        "tvl_numeric": normalize_value(item.get("tvl_numeric")),
        "vecrv_boost_numeric": normalize_value(item.get("veCRV_boost_numeric")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_convex_pool_ohlc_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id_type": item.get("pool_id_type"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool_name": item.get("Pool"),
        "pool_id": item.get("pool_id"),
        "factory_id": item.get("factory_id"),
        "type": item.get("type"),
        "open": normalize_value(item.get("open")),
        "high": normalize_value(item.get("high")),
        "low": normalize_value(item.get("low")),
        "close": normalize_value(item.get("close")),
        "sample_count": normalize_value(item.get("sample_count")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_convex_pool_remarks_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id": item.get("pool_id"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool_name": item.get("Pool"),
        "factory_id": item.get("factory_id"),
        "remarks": item.get("Remarks"),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_cvx_crv_stake_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stake": item.get("stake"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool": item.get("pool"),
        "max_vapr_gov_token_rewards": item.get("max_vapr_gov_token_rewards"),
        "max_vapr_stablecoin_rewards": item.get("max_vapr_stablecoin_rewards"),
        "tvl": item.get("tvl"),
        "max_vapr_gov_numeric": normalize_value(item.get("max_vapr_gov_numeric")),
        "max_vapr_stable_numeric": normalize_value(item.get("max_vapr_stable_numeric")),
        "tvl_numeric": normalize_value(item.get("tvl_numeric")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_cvx_crv_stake_ohlc_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": item.get("type"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool": item.get("pool"),
        "stake": item.get("stake"),
        "open": normalize_value(item.get("open")),
        "high": normalize_value(item.get("high")),
        "low": normalize_value(item.get("low")),
        "close": normalize_value(item.get("close")),
        "sample_count": normalize_value(item.get("sample_count")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_cvx_stake_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "token": item.get("token"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "vapr": item.get("vapr"),
        "tvl": item.get("tvl"),
        "vapr_numeric": normalize_value(item.get("vapr_numeric")),
        "tvl_numeric": normalize_value(item.get("tvl_numeric")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_cvx_stake_ohlc_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": item.get("type"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "token": item.get("token"),
        "open": normalize_value(item.get("open")),
        "high": normalize_value(item.get("high")),
        "low": normalize_value(item.get("low")),
        "close": normalize_value(item.get("close")),
        "sample_count": normalize_value(item.get("sample_count")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_deletion_tracking_logs(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "log_id": item.get("log_id"),
        "timestamp": item.get("timestamp"),
        "additional_data": normalize_value(item.get("additional_data")),
        "caller_info": normalize_value(item.get("caller_info")),
        "created_at": item.get("created_at"),
        "date": parse_date(item.get("date")),
        "function_name": item.get("function_name"),
        "log_level": item.get("log_level"),
        "operation_type": item.get("operation_type"),
        "source": item.get("source"),
        "status": item.get("status"),
        "table_name": item.get("table_name"),
    }


def map_pool_latest(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id": item.get("pool_id"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "pool_name": item.get("Pool"),
        "current_vapr": item.get("Current_vAPR"),
        "projected_vapr": item.get("Projected_vAPR"),
        "tvl": item.get("TVL"),
        "vecrv_boost": item.get("veCRV_boost"),
        "remarks": item.get("Remarks"),
        "current_vapr_numeric": normalize_value(item.get("current_vapr_numeric")),
        "projected_vapr_numeric": normalize_value(item.get("projected_vapr_numeric")),
        "tvl_numeric": normalize_value(item.get("tvl_numeric")),
        "data_source": item.get("data_source"),
        "is_vault": item.get("is_vault"),
        "updated_at": item.get("updated_at"),
        "token_symbols": normalize_string_list(item.get("token_symbols")),
        "factory_id": item.get("factory_id"),
        "search_tokens": normalize_string_list(item.get("search_tokens")),
        "normalized_name": item.get("normalized_name"),
    }


def map_pool_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id": item.get("pool_id"),
        "name": item.get("name"),
        "symbol": item.get("symbol"),
        "timezone": item.get("timezone"),
        "timestamp": item.get("timestamp"),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "raw": build_item_with_raw(item),
    }


def map_simulations_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pool_id": item.get("pool_id"),
        "timestamp": item.get("timestamp"),
        "created_at": item.get("created_at"),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "diagnostics": normalize_value(item.get("diagnostics")),
        "expires_at": normalize_value(item.get("expires_at")),
        "factory_id": item.get("factory_id"),
        "pool": item.get("pool"),
        "request": normalize_value(item.get("request")),
        "result": normalize_value(item.get("result")),
        "simulation_id": item.get("simulation_id"),
        "status": item.get("status"),
        "timezone": item.get("timezone"),
    }


def map_token_ohlc_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "token": item.get("token"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "open": normalize_value(item.get("open")),
        "high": normalize_value(item.get("high")),
        "low": normalize_value(item.get("low")),
        "close": normalize_value(item.get("close")),
        "sample_count": normalize_value(item.get("sample_count")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_token_price_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "token": item.get("token"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "price": item.get("price"),
        "price_numeric": normalize_value(item.get("price_numeric")),
        "pool_count": normalize_value(item.get("pool_count")),
        "pools": item.get("pools"),
        "factory_ids": item.get("factory_ids"),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_usdjpy_history(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "asset": item.get("asset"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "rate": normalize_value(item.get("rate")),
        "source": item.get("source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_usdjpy_ohlc_daily(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "asset": item.get("asset"),
        "timestamp": item.get("timestamp"),
        "timezone": item.get("timezone"),
        "open": normalize_value(item.get("open")),
        "high": normalize_value(item.get("high")),
        "low": normalize_value(item.get("low")),
        "close": normalize_value(item.get("close")),
        "sample_count": normalize_value(item.get("sample_count")),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
    }


def map_vault_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "vault_id": item.get("vault_id"),
        "name": item.get("name"),
        "timezone": item.get("timezone"),
        "timestamp": item.get("timestamp"),
        "data_source": item.get("data_source"),
        "datetime": item.get("datetime"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "raw": build_item_with_raw(item),
    }


TABLE_MAPPINGS = {
    "ConvexPoolHistory": {
        "supabase_table": "convex_pool_history",
        "on_conflict": "pool_id,timestamp",
        "mapper": map_convex_pool_history,
    },
    "ConvexPoolOHLCDaily": {
        "supabase_table": "convex_pool_ohlc_daily",
        "on_conflict": "pool_id_type,timestamp",
        "mapper": map_convex_pool_ohlc_daily,
    },
    "ConvexPoolRemarksHistory": {
        "supabase_table": "convex_pool_remarks_history",
        "on_conflict": "pool_id,timestamp",
        "mapper": map_convex_pool_remarks_history,
    },
    "CvxCrvStakeHistory": {
        "supabase_table": "cvx_crv_stake_history",
        "on_conflict": "stake,timestamp",
        "mapper": map_cvx_crv_stake_history,
    },
    "CvxCrvStakeOHLCDaily": {
        "supabase_table": "cvx_crv_stake_ohlc_daily",
        "on_conflict": "type,timestamp",
        "mapper": map_cvx_crv_stake_ohlc_daily,
    },
    "CvxStakeHistory": {
        "supabase_table": "cvx_stake_history",
        "on_conflict": "token,timestamp",
        "mapper": map_cvx_stake_history,
    },
    "CvxStakeOHLCDaily": {
        "supabase_table": "cvx_stake_ohlc_daily",
        "on_conflict": "type,timestamp",
        "mapper": map_cvx_stake_ohlc_daily,
    },
    "DeletionTrackingLogs": {
        "supabase_table": "deletion_tracking_logs",
        "on_conflict": "log_id,timestamp",
        "mapper": map_deletion_tracking_logs,
    },
    "PoolLatest": {
        "supabase_table": "pool_latest",
        "on_conflict": "pool_id",
        "mapper": map_pool_latest,
    },
    "PoolMeta": {
        "supabase_table": "pool_meta",
        "on_conflict": "pool_id",
        "mapper": map_pool_meta,
    },
    "SimulationsHistory": {
        "supabase_table": "simulations_history",
        "on_conflict": "pool_id,timestamp",
        "mapper": map_simulations_history,
    },
    "TokenOHLCDaily": {
        "supabase_table": "token_ohlc_daily",
        "on_conflict": "token,timestamp",
        "mapper": map_token_ohlc_daily,
    },
    "TokenPriceHistory": {
        "supabase_table": "token_price_history",
        "on_conflict": "token,timestamp",
        "mapper": map_token_price_history,
    },
    "USDJPYHistory": {
        "supabase_table": "usdjpy_history",
        "on_conflict": "asset,timestamp",
        "mapper": map_usdjpy_history,
    },
    "USDJPYOHLCDaily": {
        "supabase_table": "usdjpy_ohlc_daily",
        "on_conflict": "asset,timestamp",
        "mapper": map_usdjpy_ohlc_daily,
    },
    "VaultMeta": {
        "supabase_table": "vault_meta",
        "on_conflict": "vault_id",
        "mapper": map_vault_meta,
    },
}


def chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def migrate_table(
    dynamodb,
    supabase,
    table_name: str,
    mapping: Dict[str, Any],
    batch_size: int,
) -> None:
    table = dynamodb.Table(table_name)
    mapper = mapping["mapper"]
    supabase_table = mapping["supabase_table"]
    on_conflict = mapping["on_conflict"]

    total = 0
    last_evaluated_key = None

    while True:
        if last_evaluated_key:
            response = table.scan(ExclusiveStartKey=last_evaluated_key)
        else:
            response = table.scan()

        items = response.get("Items", [])
        mapped_items = [mapper(item) for item in items]

        for batch in chunked(mapped_items, batch_size):
            if not batch:
                continue
            supabase.table(supabase_table).upsert(batch, on_conflict=on_conflict).execute()
            total += len(batch)

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

        time.sleep(0.2)

    print(f"✅ {table_name} -> {supabase_table}: {total} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="DynamoDB -> Supabase migration")
    parser.add_argument(
        "--tables",
        default=",".join(TABLE_MAPPINGS.keys()),
        help="Comma-separated DynamoDB table names to migrate",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("SUPABASE_BATCH_SIZE", "500")),
        help="Upsert batch size (default: 500)",
    )
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    aws_region = os.getenv("AWS_REGION", "ap-northeast-1")

    if not supabase_url or not supabase_key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    supabase = create_client(supabase_url, supabase_key)
    dynamodb = boto3.resource("dynamodb", region_name=aws_region)

    table_list = [t.strip() for t in args.tables.split(",") if t.strip()]

    for table_name in table_list:
        mapping = TABLE_MAPPINGS.get(table_name)
        if not mapping:
            print(f"⚠️ Skip unknown table: {table_name}")
            continue
        migrate_table(dynamodb, supabase, table_name, mapping, args.batch_size)


if __name__ == "__main__":
    main()
