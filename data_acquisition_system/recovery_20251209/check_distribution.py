#!/usr/bin/env python3
# =====================================
# Check Data Distribution in DynamoDB
# =====================================

import boto3
import logging
from botocore.exceptions import ClientError
from collections import defaultdict
from dotenv import load_dotenv
import os

# Load env
load_dotenv("/home/ubuntu/convex-scraper/.env")

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

def check_timestamp_distribution(table_name):
    try:
        dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        table = dynamodb.Table(table_name)
        
        logger.info(f"\n--- Checking {table_name} Distribution ---")
        
        # Scan (Limit 2000 to get a good sample of recent data)
        response = table.scan(Limit=2000)
        items = response.get('Items', [])
        
        timestamps = []
        for item in items:
            ts = item.get('timestamp') or item.get('datetime')
            if ts:
                timestamps.append(ts)
        
        # Group by day/hour
        counts = defaultdict(int)
        for ts in timestamps:
            # Assumes ISO format like 2025-12-09T00:00:00...
            # We want to see YYYY-MM-DD HH
            key = ts[:13] # e.g. 2025-12-09T00
            counts[key] += 1
            
        # Print sorted
        for key in sorted(counts.keys(), reverse=True):
            logger.info(f"{key}: {counts[key]} items")
            
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    check_timestamp_distribution('TokenPriceHistory')
    check_timestamp_distribution('ConvexPoolHistory')
