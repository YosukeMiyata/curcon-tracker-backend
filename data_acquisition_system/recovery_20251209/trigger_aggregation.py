#!/usr/bin/env python3
# =====================================
# Trigger Daily Aggregation
# =====================================

import sys
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load env
load_dotenv("/home/ubuntu/convex-scraper/.env")

# Fix path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from convex_ec2_complete import ConvexEC2Complete

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('TriggerAggregation')

def main():
    logger.info("Initializing ConvexEC2Complete...")
    scraper = ConvexEC2Complete()
    
    # Force aggregation for "Yesterday"
    # Since today is Dec 9, "Yesterday" is Dec 8.
    # The methods aggregate `Yesterday`.
    
    logger.info("--- 1. Aggregating CVX OHLC (Dec 8) ---")
    if scraper.aggregate_yesterday_ohlc_and_clear_history():
        logger.info("✅ CVX Aggregation Success")
    else:
        logger.warning("⚠️ CVX Aggregation Failed or No Data")

    logger.info("--- 2. Aggregating cvxCRV OHLC (Dec 8) ---")
    if scraper.aggregate_yesterday_cvxcrv_ohlc_and_clear_history():
        logger.info("✅ cvxCRV Aggregation Success")
    else:
        logger.warning("⚠️ cvxCRV Aggregation Failed or No Data")

    logger.info("--- 3. Aggregating Convex Pools OHLC & Remarks (Dec 8) ---")
    if scraper.aggregate_yesterday_convex_pool_ohlc_and_remarks():
        logger.info("✅ Convex Pools Aggregation Success")
    else:
        logger.warning("⚠️ Convex Pools Aggregation Failed or No Data")
        
    logger.info("Done.")

if __name__ == "__main__":
    main()
