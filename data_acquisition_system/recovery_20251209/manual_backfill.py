#!/usr/bin/env python3
# =====================================
# Manual Backfill Script for convex_ec2_complete and token_price_tracker
# =====================================

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import logging

# Import original classes
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append("/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker")
from convex_ec2_complete import ConvexEC2Complete
from token_price_tracker import TokenPriceTracker

# Japanese Timezone
JST = timezone(timedelta(hours=9))

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger('ManualBackfill')

logger = setup_logging()

class BackfillConvexEC2(ConvexEC2Complete):
    def __init__(self, target_time):
        self.target_time = target_time
        super().__init__()
        # Disable scheduler loop
        self.is_running = False

    def get_jst_iso_timestamp(self):
        """Override to return target time"""
        return self.target_time.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        
    def get_jst_timestamp(self):
        """Override to return target time"""
        return self.target_time.strftime("%Y-%m-%d %H:%M:%S JST")

    def run_once(self):
        """Run scraping logic once"""
        logger.info(f"=== ConvexEC2Complete Running for {self.target_time} ===")
        
        # 1. Scrape Data
        data = self.scrape_convex_data()
        if not data:
            logger.error("Failed to scrape data")
            return

        # 2. Get Exchange Rate
        usd_jpy_rate = self.get_usd_jpy_rate()
        
        # 3. Save to DynamoDB
        if self.save_to_dynamodb_jst(data):
            logger.info("Successfully saved Convex data")
        
        # 4. Save Exchange Rate
        if self.save_usd_jpy_rate(usd_jpy_rate):
            logger.info("Successfully saved Exchange Rate")


class BackfillTokenTracker(TokenPriceTracker):
    def __init__(self, target_time):
        self.target_time = target_time
        super().__init__()

    # We need to Monkey-patch datetime in the save method or override save_token_prices_to_db
    # Since save_token_prices_to_db uses datetime.now(self.JST) internally, 
    # we'll override the method to inject our timestamp logic.
    
    def save_token_prices_to_db(self, token_info):
        """Override to use target_time"""
        if not token_info:
            return
        
        jst_iso_timestamp = self.target_time.strftime("%Y-%m-%dT23:55:00+09:00") # Align with usual schedule? Or exact? User said 0:00.
        # However, key schema might be just timestamp. 
        # Using exact target time.
        jst_iso_timestamp = self.target_time.isoformat()
        jst_created_at = datetime.now(JST).isoformat()
        
        saved_count = 0
        
        for token, info in token_info.items():
            price = info.get('price')
            if price is None: continue
            
            try:
                from decimal import Decimal
                item = {
                    'token': token,
                    'timestamp': jst_iso_timestamp,
                    'timezone': 'JST',
                    'created_at': jst_created_at,
                    'data_source': 'curve_finance_api_backfill',
                    'price': f"${price:.6f}",
                    'price_numeric': Decimal(str(price))
                }
                
                if info.get('pools'):
                    item['pool_count'] = int(len(info['pools']))
                    item['pools'] = ', '.join(info['pools'])
                
                if info.get('factory_ids'):
                    item['factory_ids'] = ', '.join(info['factory_ids'])
                
                # Filter None
                item = {k: v for k, v in item.items() if v is not None and (k == 'price' or v != '')}
                
                self.token_price_table.put_item(Item=item)
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving {token}: {e}")
                
        logger.info(f"=== TokenPriceTracker Saved {saved_count} items for {self.target_time} ===")

    def run_once(self):
        logger.info(f"=== TokenPriceTracker Running for {self.target_time} ===")
        # 1. Update list from history
        tracked_tokens = self.update_tracked_tokens_from_history()
        # 2. Get prices
        token_info = self.analyze_tracked_tokens(tracked_tokens)
        # 3. Save
        self.save_token_prices_to_db(token_info)


def main():
    # Targets: 
    # Yesterday 0:00 -> 2025-12-08 00:00 ? Or Today 0:00 (since it is 10AM on 9th)?
    # User said "Last night's 0:00 and 0:30" (昨夜の0時と0時30分).
    # If today is Dec 9th. "Last night 0:00" usually means Dec 9th 00:00.
    # But just in case, I will produce for both dates if requested, but user said "Yesterday's".
    # Given the error log was Dec 8th 18:30, the missing data starts from then. 
    # So Dec 9th 00:00 (midnight) is the first missing midnight.
    # Wait, Dec 8th 18:30 failed. So Dec 8th 19:30, 20:30... failed.
    # User specifically asked for "0:00 and 0:30".
    # 0:00 is usually Token Price Tracker.
    # 0:30 is Convex Scraper.
    
    # Let's assume Dec 9th 00:00 (Token) and Dec 9th 00:30 (Convex).
    # (Since Dec 8th 00:00 would be before the error started at 18:30?).
    # No, error started Dec 8th 18:30. So Dec 8th 00:00 was SUCCESSFUL.
    # So the missing one is Dec 9th 00:00.
    
    target_date = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    # This is Dec 9th 00:00:00 JST.
    
    # 1. Token Price Tracker for 00:00
    tracker = BackfillTokenTracker(target_date)
    tracker.run_once()
    
    # 2. Convex Scraper for 00:30
    target_date_scraper = target_date.replace(minute=30)
    scraper = BackfillConvexEC2(target_date_scraper)
    scraper.run_once()
    
    logger.info("Backfill completed.")

if __name__ == "__main__":
    main()
