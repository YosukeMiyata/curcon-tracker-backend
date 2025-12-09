#!/usr/bin/env python3
# =====================================
# Run Aggregations for Dec 9
# =====================================

import sys
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from collections import defaultdict
import boto3
from dotenv import load_dotenv

# Load env
load_dotenv("/home/ubuntu/convex-scraper/.env")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('RunAggregations')

# Setup boto3
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')

# Tables
usdjpy_history_table = dynamodb.Table('USDJPYHistory')
usdjpy_ohlc_table = dynamodb.Table('USDJPYOHLCDaily')

token_price_table = dynamodb.Table('TokenPriceHistory')
token_ohlc_table = dynamodb.Table('TokenOHLCDaily')

JST = timezone(timedelta(hours=9))

def aggregate_usdjpy(target_date_str):
    logger.info(f"--- Aggregating USDJPY for {target_date_str} ---")
    
    try:
        response = usdjpy_history_table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = usdjpy_history_table.scan(
                FilterExpression="begins_with(#ts, :date)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={":date": target_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
            
        logger.info(f"Found {len(items)} USDJPY items for {target_date_str}")
        
        if not items:
            logger.warning("No USDJPY data found")
            return False

        # Sort by timestamp
        items.sort(key=lambda x: x.get('timestamp'))
        
        rates = []
        for item in items:
            r = item.get('rate')
            if r is not None:
                rates.append(float(r))
        
        if not rates:
            logger.warning("No valid rates found.")
            return False

        ohlc = {
            'open': float(items[0]['rate']),
            'high': max(rates),
            'low': min(rates),
            'close': float(items[-1]['rate']),
            'sample_count': len(rates)
        }
        
        # Save
        item = {
            'asset': 'USDJPY',
            'timestamp': target_date_str,
            'timezone': 'JST',
            'open': Decimal(str(ohlc['open'])),
            'high': Decimal(str(ohlc['high'])),
            'low': Decimal(str(ohlc['low'])),
            'close': Decimal(str(ohlc['close'])),
            'sample_count': int(ohlc['sample_count']),
            'data_source': 'RunAggregations',
            'created_at': datetime.now(JST).isoformat()
        }
        
        usdjpy_ohlc_table.put_item(Item=item)
        logger.info(f"✅ Saved USDJPY OHLC: {ohlc}")
        return True

    except Exception as e:
        logger.error(f"Error aggregating USDJPY: {e}")
        return False

def aggregate_token_ohlc(target_date_str):
    logger.info(f"--- Aggregating Token OHLC for {target_date_str} ---")
    
    try:
        response = token_price_table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = token_price_table.scan(
                FilterExpression="begins_with(#ts, :date)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={":date": target_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
            
        logger.info(f"Found {len(items)} Token Price items for {target_date_str}")
        
        if not items:
            logger.warning("No token data found")
            return False

        # Group by token
        grouped = defaultdict(list)
        for item in items:
            token = item.get('token')
            if token:
                grouped[token].append(item)
        
        logger.info(f"Unique tokens found: {len(grouped)}")
        
        saved_count = 0
        for token, token_items in grouped.items():
            token_items.sort(key=lambda x: x.get('timestamp'))
            
            prices = []
            for it in token_items:
                p = it.get('price_numeric')
                if p is None: 
                    p_str = it.get('price')
                    if p_str and p_str.startswith('$'):
                        try:
                            p = float(p_str.replace('$', '').replace(',', ''))
                        except: pass
                if p is not None:
                    prices.append(float(p))
            
            if not prices: continue
            
            ohlc = {
                'open': prices[0],
                'high': max(prices),
                'low': min(prices),
                'close': prices[-1],
                'sample_count': len(prices)
            }
            
            item = {
                'token': token,
                'timestamp': target_date_str,
                'open': Decimal(str(ohlc['open'])),
                'high': Decimal(str(ohlc['high'])),
                'low': Decimal(str(ohlc['low'])),
                'close': Decimal(str(ohlc['close'])),
                'sample_count': int(ohlc['sample_count']),
                'timezone': 'JST',
                'data_source': 'RunAggregations',
                'created_at': datetime.now(JST).isoformat()
            }
            token_ohlc_table.put_item(Item=item)
            saved_count += 1
            
        logger.info(f"✅ Saved OHLC for {saved_count} tokens")
        return saved_count > 0

    except Exception as e:
        logger.error(f"Error aggregating tokens: {e}")
        return False

def delete_history_data(target_date_str):
    logger.info(f"--- Deleting history data for {target_date_str} ---")
    
    try:
        # Delete USDJPY
        response = usdjpy_history_table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = usdjpy_history_table.scan(
                FilterExpression="begins_with(#ts, :date)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={":date": target_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        deleted_usdjpy = 0
        with usdjpy_history_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'asset': 'USDJPY', 'timestamp': item['timestamp']})
                deleted_usdjpy += 1
        
        logger.info(f"✅ Deleted {deleted_usdjpy} items from USDJPYHistory")
        
        # Delete Token Price
        response = token_price_table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = token_price_table.scan(
                FilterExpression="begins_with(#ts, :date)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={":date": target_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        deleted_token = 0
        with token_price_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'token': item['token'], 'timestamp': item['timestamp']})
                deleted_token += 1
                if deleted_token % 100 == 0:
                    logger.info(f"Deleted {deleted_token} items...")
        
        logger.info(f"✅ Deleted {deleted_token} items from TokenPriceHistory")
        
    except Exception as e:
        logger.error(f"Error deleting history data: {e}")

def main():
    target_date = "2025-12-09"
    
    usdjpy_ok = aggregate_usdjpy(target_date)
    token_ok = aggregate_token_ohlc(target_date)
    
    if usdjpy_ok and token_ok:
        logger.info("✅ Aggregation successful, proceeding to delete history data")
        delete_history_data(target_date)
    else:
        logger.error("❌ Aggregation failed, skipping deletion")

if __name__ == "__main__":
    main()
