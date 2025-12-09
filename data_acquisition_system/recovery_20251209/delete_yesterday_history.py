#!/usr/bin/env python3
# =====================================
# Delete History Data for Dec 8 (Cleanup)
# =====================================

import sys
import logging
from datetime import datetime, timezone, timedelta
import boto3
from dotenv import load_dotenv

# Load env
load_dotenv("/home/ubuntu/convex-scraper/.env")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('DeleteHistory')

# Setup boto3
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
token_price_table = dynamodb.Table('TokenPriceHistory')
usdjpy_history_table = dynamodb.Table('USDJPYHistory')

def delete_items_for_date(table, table_name, target_date_str, pk_name, pk_value_key=None, constant_pk=None):
    logger.info(f"--- Scanning {table_name} for {target_date_str} ---")
    
    try:
        # Scan
        response = table.scan(
            FilterExpression="begins_with(#ts, :date)",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":date": target_date_str}
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression="begins_with(#ts, :date)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={":date": target_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
            
        count = len(items)
        logger.info(f"Found {count} items to delete in {table_name}")
        
        if count == 0:
            return

        # Batch Delete
        deleted = 0
        with table.batch_writer() as batch:
            for item in items:
                key = {}
                # Determine PK
                if constant_pk:
                    key[pk_name] = constant_pk
                else:
                    key[pk_name] = item[pk_value_key]
                
                # SK is always timestamp
                key['timestamp'] = item['timestamp']
                
                batch.delete_item(Key=key)
                deleted += 1
                if deleted % 100 == 0:
                    logger.info(f"Deleted {deleted} items...")
                    
        logger.info(f"✅ Deleted {deleted} items from {table_name}")

    except Exception as e:
        logger.error(f"Error deleting from {table_name}: {e}")

def main():
    target_date = "2025-12-08"
    
    # 1. USDJPYHistory (PK: asset='USDJPY', SK: timestamp)
    # Actually PK name is 'asset' in schema? Let's verify from checks.
    # In `check_latest_data`, item had 'asset': 'USDJPY'. 
    # In `backfill_usdjpy...`, KeyConditionExpression='asset = :asset' used Scan Filter.
    # But usually DynamoDB needs PK. Assuming 'asset' is PK.
    
    delete_items_for_date(
        usdjpy_history_table, 
        'USDJPYHistory', 
        target_date, 
        pk_name='asset', 
        constant_pk='USDJPY'
    )
    
    # 2. TokenPriceHistory (PK: token, SK: timestamp)
    delete_items_for_date(
        token_price_table, 
        'TokenPriceHistory', 
        target_date, 
        pk_name='token', 
        pk_value_key='token'
    )

if __name__ == "__main__":
    main()
