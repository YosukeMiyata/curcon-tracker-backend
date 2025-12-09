#!/usr/bin/env python3
# =====================================
# Check Latest Data in DynamoDB
# =====================================

import boto3
import logging
from botocore.exceptions import ClientError
from datetime import datetime
import sys
from dotenv import load_dotenv
import os

# Load env from absolute path
load_dotenv("/home/ubuntu/convex-scraper/.env")

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

def check_table(table_name, sort_key=None):
    try:
        dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        table = dynamodb.Table(table_name)
        
        logger.info(f"--- Checking {table_name} ---")
        
        # Scan last 50 items (not efficient but simple for checking presence)
        # Better: Query if we know PK. But here we want to see general latest status.
        # We'll just scan and sort by timestamp manually for verification.
        response = table.scan(Limit=1000) 
        items = response.get('Items', [])
        
        if not items:
            logger.info("No items found.")
            return

        # Try to find a timestamp field
        # Most tables use 'timestamp' (ISO string)
        if sort_key:
            sorted_items = sorted(items, key=lambda x: x.get(sort_key, ''), reverse=True)
        else:
            # Try 'timestamp' or 'datetime'
            sorted_items = sorted(items, key=lambda x: x.get('timestamp') or x.get('datetime', ''), reverse=True)

        logger.info(f"Top 5 latest items in {table_name}:")
        for item in sorted_items[:5]:
            ts = item.get('timestamp') or item.get('datetime')
            logger.info(f" - {ts} | {str(item)[:100]}...")
            
    except Exception as e:
        logger.error(f"Error checking {table_name}: {e}")

if __name__ == "__main__":
    check_table('TokenPriceHistory', sort_key='timestamp')
    check_table('USDJPYHistory', sort_key='timestamp')
    check_table('PriceHistory', sort_key='timestamp')
