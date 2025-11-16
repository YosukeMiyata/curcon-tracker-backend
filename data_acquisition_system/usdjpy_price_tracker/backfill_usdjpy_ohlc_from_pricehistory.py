#!/usr/bin/env python3
# =====================================
# USD/JPY OHLC バックフィルスクリプト
# PriceHistory から指定日のUSDJPYデータを集約し、USDJPYOHLCDaily に保存
# =====================================

import boto3
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import sys

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


class USDJPYOHLCBackfill:
    def __init__(self, region: str = 'ap-northeast-1'):
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.price_history = self.dynamodb.Table('PriceHistory')
        self.ohlc_daily = self.dynamodb.Table('USDJPYOHLCDaily')
        self.JST = timezone(timedelta(hours=9))
        self.data_source_fallback = 'PriceHistory'
        self._setup_logging()
        self.slack = None
        if SLACK_AVAILABLE:
            try:
                self.slack = SlackNotifier()
            except Exception:
                self.slack = None

    def _setup_logging(self):
        log_file = Path(__file__).parent / 'backfill_usdjpy_ohlc.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _fetch_usdjpy_for_date(self, target_date: datetime) -> List[dict]:
        date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)
        start_iso = date_start.isoformat()
        end_iso = date_end.isoformat()

        self.logger.info(f"📥 Fetch PriceHistory USDJPY: {start_iso} ~ {end_iso}")

        items: List[dict] = []
        response = self.price_history.scan(
            FilterExpression='asset = :asset',
            ExpressionAttributeValues={':asset': 'USDJPY'}
        )
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = self.price_history.scan(
                FilterExpression='asset = :asset',
                ExpressionAttributeValues={':asset': 'USDJPY'},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        # JST日付範囲でフィルタリング
        filtered = []
        for it in items:
            ts = it.get('timestamp') or ''
            if start_iso <= ts < end_iso:
                filtered.append(it)
        self.logger.info(f"   -> {len(filtered)} items")
        return filtered

    def _aggregate_ohlc(self, items: List[dict]) -> Optional[dict]:
        if not items:
            return None
        # タイムスタンプ順
        items_sorted = sorted(items, key=lambda x: x.get('timestamp', ''))
        rates: List[float] = []
        for it in items_sorted:
            r = it.get('rate')
            if r is None:
                continue
            if isinstance(r, Decimal):
                rates.append(float(r))
            else:
                try:
                    rates.append(float(r))
                except Exception:
                    continue
        if not rates:
            return None
        return {
            'open': rates[0],
            'high': max(rates),
            'low': min(rates),
            'close': rates[-1],
            'sample_count': len(rates)
        }

    def _save_ohlc(self, target_date: datetime, ohlc: dict, source: str):
        date_str = target_date.strftime('%Y-%m-%d')
        jst_created_at = datetime.now(self.JST).isoformat()
        date_mid = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        jst_datetime = date_mid.isoformat()
        item = {
            'asset': 'USDJPY',
            'timestamp': date_str,
            'timezone': 'JST',
            'open': Decimal(str(ohlc['open'])),
            'high': Decimal(str(ohlc['high'])),
            'low': Decimal(str(ohlc['low'])),
            'close': Decimal(str(ohlc['close'])),
            'sample_count': int(ohlc['sample_count']),
            'data_source': source,
            'datetime': jst_datetime,
            'created_at': jst_created_at
        }
        self.ohlc_daily.put_item(Item=item)
        self.logger.info(f"💾 Saved USDJPYOHLCDaily: {date_str}")

    def process_date(self, date_str: str) -> bool:
        try:
            # JST aware date
            dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=self.JST)
            items = self._fetch_usdjpy_for_date(dt)
            if not items:
                self.logger.warning(f"⚠️ No data in PriceHistory for {date_str}")
                return False
            ohlc = self._aggregate_ohlc(items)
            if not ohlc:
                self.logger.warning(f"⚠️ No valid rates to aggregate for {date_str}")
                return False
            # data_source優先: アイテムにsourceがあればそれ、なければfallback
            source = None
            for it in items:
                if it.get('source'):
                    source = it['source']
                    break
            if not source:
                source = self.data_source_fallback
            self._save_ohlc(dt, ohlc, source)
            return True
        except Exception as e:
            self.logger.error(f"❌ Error processing {date_str}: {e}")
            if SLACK_AVAILABLE and self.slack:
                try:
                    self.slack.notify_error(
                        message=f"Backfill error for {date_str}",
                        system_name="USDJPY OHLC Backfill",
                        error=e
                    )
                except Exception:
                    pass
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Backfill USDJPY OHLC from PriceHistory')
    parser.add_argument('dates', nargs='+', help='Dates in YYYY-MM-DD (JST)')
    args = parser.parse_args()

    job = USDJPYOHLCBackfill()
    all_ok = True
    for d in args.dates:
        ok = job.process_date(d)
        all_ok = all_ok and ok
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
