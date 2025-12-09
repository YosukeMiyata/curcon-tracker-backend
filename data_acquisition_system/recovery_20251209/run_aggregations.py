#!/usr/bin/env python3
# =====================================
# Run Aggregations for Dec 8 (Robust Scan Version)
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
        # Scan with filter for efficient-enough data retrieval for one day logic (client side filter)
        # Better: Scan Key('timestamp').begins_with(date) if supported? No, Scan supports FilterExpression.
        # FilterExpression: BEGINS_WITH(timestamp, :date)
        
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
            return

        rates = []
        for item in items:
            # Try 'rate' or 'price'
            r = item.get('rate')
            if r is not None:
                rates.append(float(r))
        
        if not rates:
            logger.warning("No valid rates found.")
            return

        ohlc = {
            'open': rates[0], # approximate sort check needed? Scan order is undefined.
            'high': max(rates),
            'low': min(rates),
            'close': rates[-1],
            'sample_count': len(rates)
        }
        
        # We should sort to be correct on Open/Close
        items.sort(key=lambda x: x.get('timestamp'))
        ohlc['open'] = float(items[0]['rate'])
        ohlc['close'] = float(items[-1]['rate'])
        
        # Save
        item = {
            'asset': 'USDJPY', # Partition Key for OHLC? Need to verify schema. 
                               # usdjpy_ohlc_aggregator.py (Step 199) uses 'asset': 'USDJPY'
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

    except Exception as e:
        logger.error(f"Error aggregating USDJPY: {e}")

def aggregate_token_ohlc(target_date_str):
    logger.info(f"--- Aggregating Token OHLC for {target_date_str} ---")
    
    try:
        # Scan TokenPriceHistory for the date
        response = token_price_table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        # Pagination
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
            return

        # Group by token
        grouped = defaultdict(list)
        for item in items:
            token = item.get('token')
            if token:
                grouped[token].append(item)
        
        logger.info(f"Unique tokens found: {len(grouped)}")
        
        saved_count = 0
        for token, token_items in grouped.items():
            # Sort by timestamp
            token_items.sort(key=lambda x: x.get('timestamp'))
            
            prices = []
            for it in token_items:
                p = it.get('price_numeric')
                if p is None: 
                    # Try parsing 'price' string '$...'
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
            
            # Save
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

    except Exception as e:
        logger.error(f"Error aggregating tokens: {e}")

def main():
    aggregate_usdjpy("2025-12-08")
    aggregate_token_ohlc("2025-12-08")

if __name__ == "__main__":
    main()
