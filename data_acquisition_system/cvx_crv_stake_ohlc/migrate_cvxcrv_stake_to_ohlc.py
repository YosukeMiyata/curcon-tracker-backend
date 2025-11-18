#!/usr/bin/env python3
# =====================================
# CvxCrvStakeMetricsからCvxCrvStakeOHLCDailyへのデータ移行スクリプト
# CvxCrvStakeMetricsテーブルのデータ（2025年11月17日まで）を
# CvxCrvStakeOHLCDailyテーブルのOHLC形式に集約して保存
# gov、stablecoin、tvlの3つのtypeでそれぞれ集約
# =====================================

import boto3
from boto3.dynamodb.conditions import Key
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from botocore.exceptions import ClientError
from decimal import Decimal
import sys
from pathlib import Path
import traceback
from typing import List, Dict, Optional, Tuple

# Slack通知のインポート
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class CvxCrvStakeToOHLCMigrator:
    def __init__(self):
        """CvxCrvStakeMetricsからCvxCrvStakeOHLCDailyへの移行システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.cvxcrv_stake_table = None
        self.ohlc_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # 終了日（2025年11月17日）
        self.end_date = datetime(2025, 11, 17, 23, 59, 59, tzinfo=self.JST)
        
        # ログ設定
        self.setup_logging()
        
        # Slack通知の初期化
        if SLACK_AVAILABLE:
            try:
                self.slack_notifier = SlackNotifier()
                self.logger.info("✅ Slack通知機能が有効です")
            except Exception as e:
                self.logger.warning(f"⚠️ Slack通知初期化エラー: {e}")
                self.slack_notifier = None
        else:
            self.slack_notifier = None
            self.logger.warning("⚠️ Slack通知モジュールが利用できません")
        
        # テーブル接続
        self.setup_tables()
    
    def setup_logging(self):
        """ログ設定"""
        log_file = Path(__file__).parent / 'migrate_cvxcrv_stake_to_ohlc.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_tables(self):
        """DynamoDBテーブルに接続"""
        try:
            self.cvxcrv_stake_table = self.dynamodb.Table('CvxCrvStakeMetrics')
            self.cvxcrv_stake_table.load()
            self.logger.info("✅ CvxCrvStakeMetricsテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('CvxCrvStakeOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ CvxCrvStakeOHLCDailyテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="CvxCrvStake to OHLC Migrator",
                    error=e
                )
            raise e
    
    def get_cvxcrv_stake_data(self):
        """CvxCrvStakeMetricsテーブルからcvxCRVのデータを取得（2025年11月17日まで）"""
        try:
            self.logger.info("📊 CvxCrvStakeMetricsテーブルからデータ取得中...")
            self.logger.info(f"   終了日: {self.end_date.strftime('%Y-%m-%d %H:%M:%S')} JST")
            
            all_items = []
            last_evaluated_key = None
            
            while True:
                query_params = {
                    'KeyConditionExpression': Key('stake').eq('cvxCRV'),
                    'ScanIndexForward': False  # 新しい順（降順）
                }
                
                if last_evaluated_key:
                    query_params['ExclusiveStartKey'] = last_evaluated_key
                
                response = self.cvxcrv_stake_table.query(**query_params)
                items = response.get('Items', [])
                
                # 終了日までのデータのみ取得
                filtered_items = []
                for item in items:
                    timestamp_str = item.get('timestamp', '')
                    if not timestamp_str:
                        continue
                    
                    try:
                        # ISO形式のタイムスタンプをパース
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        
                        # JSTに変換
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                        timestamp_jst = timestamp.astimezone(self.JST)
                        
                        # 終了日までのデータのみ
                        if timestamp_jst <= self.end_date:
                            filtered_items.append(item)
                        else:
                            # 新しいデータはスキップ
                            continue
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                        continue
                
                all_items.extend(filtered_items)
                
                # 終了日を超えたデータが見つかった場合、それ以降は処理しない
                if filtered_items and len(filtered_items) < len(items):
                    break
                
                # ページネーション
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
            
            self.logger.info(f"✅ {len(all_items)}件のデータを取得しました")
            return all_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="CvxCrvStake to OHLC Migrator",
                    error=e
                )
            return []
    
    def aggregate_ohlc_data(self, items: List[Dict], type_name: str) -> Dict[str, Dict]:
        """
        OHLCデータを日次で集約
        type_name: 'gov', 'stablecoin', または 'tvl'
        """
        if not items:
            self.logger.warning(f"⚠️ {type_name}用の集約するデータがありません")
            return {}
        
        # 日付ごとにデータをグループ化
        date_data = defaultdict(list)
        
        for item in items:
            timestamp_str = item.get('timestamp', '')
            
            # typeに応じた数値フィールドを取得
            if type_name == 'gov':
                value_numeric = item.get('max_vapr_gov_numeric')
            elif type_name == 'stablecoin':
                value_numeric = item.get('max_vapr_stable_numeric')
            elif type_name == 'tvl':
                value_numeric = item.get('tvl_numeric')
            else:
                continue
            
            if not timestamp_str or value_numeric is None:
                continue
            
            try:
                # ISO形式のタイムスタンプをパース
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                # JSTに変換
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp_jst = timestamp.astimezone(self.JST)
                
                # 日付キー（YYYY-MM-DD形式）
                date_key = timestamp_jst.strftime('%Y-%m-%d')
                
                # Decimal型をfloat型に変換
                if isinstance(value_numeric, Decimal):
                    value = float(value_numeric)
                else:
                    try:
                        value = float(value_numeric)
                    except (ValueError, TypeError):
                        continue
                
                date_data[date_key].append({
                    'timestamp': timestamp_str,
                    'timestamp_jst': timestamp_jst,
                    'value': value,
                    'data_source': item.get('data_source', 'convex_ec2_complete')
                })
                
            except (ValueError, TypeError) as e:
                self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                continue
        
        # OHLCデータを計算
        ohlc_data = {}
        for date_key, values in date_data.items():
            # タイムスタンプでソート
            sorted_values = sorted(values, key=lambda x: x['timestamp'])
            
            if sorted_values:
                # Open, High, Low, Closeを計算
                open_value = sorted_values[0]['value']
                close_value = sorted_values[-1]['value']
                high_value = max(v['value'] for v in sorted_values)
                low_value = min(v['value'] for v in sorted_values)
                sample_count = len(sorted_values)
                
                # データソースを取得（最初のアイテムから）
                data_source = sorted_values[0].get('data_source', 'convex_ec2_complete')
                
                ohlc_data[date_key] = {
                    'open': open_value,
                    'high': high_value,
                    'low': low_value,
                    'close': close_value,
                    'sample_count': sample_count,
                    'data_source': data_source
                }
                
                self.logger.info(
                    f"✅ {type_name.upper()} {date_key} OHLC集約: "
                    f"Open={open_value:.6f}, High={high_value:.6f}, "
                    f"Low={low_value:.6f}, Close={close_value:.6f}, Samples={sample_count}"
                )
        
        return ohlc_data
    
    def check_existing_data(self, type_name: str, date_key: str) -> bool:
        """CvxCrvStakeOHLCDailyテーブルに既存データがあるかチェック"""
        try:
            response = self.ohlc_table.get_item(
                Key={
                    'type': type_name,
                    'timestamp': date_key
                }
            )
            return 'Item' in response
        except Exception as e:
            self.logger.warning(f"⚠️ 既存データチェックエラー ({type_name}, {date_key}): {e}")
            return False
    
    def save_ohlc_data(self, ohlc_data: Dict[str, Dict], type_name: str):
        """OHLCデータをCvxCrvStakeOHLCDailyテーブルに保存"""
        if not ohlc_data:
            self.logger.warning(f"⚠️ 保存する{type_name}用のOHLCデータがありません")
            return False
        
        try:
            self.logger.info(f"💾 CvxCrvStakeOHLCDailyテーブルに{type_name}データ保存中...")
            
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            skipped_count = 0
            failed_count = 0
            
            for date_key, ohlc in ohlc_data.items():
                # 既存データチェック
                if self.check_existing_data(type_name, date_key):
                    self.logger.debug(f"⏭️  {type_name} {date_key} は既に存在するためスキップ")
                    skipped_count += 1
                    continue
                
                try:
                    # 日付のdatetimeオブジェクトを作成（JST、0時0分0秒）
                    date_dt = datetime.strptime(date_key, '%Y-%m-%d').replace(
                        hour=0, minute=0, second=0, microsecond=0, tzinfo=self.JST
                    )
                    jst_datetime = date_dt.isoformat()
                    
                    item = {
                        'type': type_name,
                        'timestamp': date_key,
                        'timezone': 'JST',
                        'pool': 'CRV',
                        'stake': 'cvxCRV',
                        'open': Decimal(str(ohlc['open'])),
                        'high': Decimal(str(ohlc['high'])),
                        'low': Decimal(str(ohlc['low'])),
                        'close': Decimal(str(ohlc['close'])),
                        'sample_count': int(ohlc['sample_count']),
                        'data_source': ohlc.get('data_source', 'convex_ec2_complete'),
                        'datetime': jst_datetime,
                        'created_at': jst_created_at
                    }
                    
                    self.ohlc_table.put_item(Item=item)
                    saved_count += 1
                    
                    self.logger.info(
                        f"✅ {type_name.upper()} {date_key} 保存完了: "
                        f"O={ohlc['open']:.6f}, H={ohlc['high']:.6f}, "
                        f"L={ohlc['low']:.6f}, C={ohlc['close']:.6f}"
                    )
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"❌ {type_name} {date_key} 保存エラー: {e}")
                    self.logger.error(traceback.format_exc())
            
            self.logger.info(
                f"📊 {type_name.upper()}保存結果: "
                f"保存={saved_count}件, スキップ={skipped_count}件, 失敗={failed_count}件"
            )
            
            if failed_count > 0:
                error_msg = f"❌ {type_name}データの保存で{failed_count}件失敗しました"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="CvxCrvStake to OHLC Migrator"
                    )
                return False
            
            return True
            
        except Exception as e:
            error_msg = f"❌ {type_name}データ保存エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="CvxCrvStake to OHLC Migrator",
                    error=e
                )
            return False
    
    def run_migration(self):
        """移行処理を実行"""
        self.logger.info("🚀 CvxCrvStakeMetricsからCvxCrvStakeOHLCDailyへの移行開始")
        self.logger.info("=" * 60)
        
        try:
            # 1. CvxCrvStakeMetricsデータを取得
            items = self.get_cvxcrv_stake_data()
            
            if not items:
                self.logger.warning("⚠️ 取得したデータが1件もありません。処理を終了します。")
                return False
            
            # 2. gov、stablecoin、tvlの3つのtypeでOHLCデータを集約
            self.logger.info("📊 OHLCデータ集約中...")
            
            gov_ohlc_data = self.aggregate_ohlc_data(items, 'gov')
            stablecoin_ohlc_data = self.aggregate_ohlc_data(items, 'stablecoin')
            tvl_ohlc_data = self.aggregate_ohlc_data(items, 'tvl')
            
            if not gov_ohlc_data and not stablecoin_ohlc_data and not tvl_ohlc_data:
                error_msg = "❌ OHLCデータ集約に失敗しました。処理を中止します。"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="CvxCrvStake to OHLC Migrator"
                    )
                return False
            
            # 3. govデータを保存
            if gov_ohlc_data:
                if not self.save_ohlc_data(gov_ohlc_data, 'gov'):
                    error_msg = "❌ gov OHLCデータ保存に失敗しました。"
                    self.logger.error(error_msg)
                    if self.slack_notifier:
                        self.slack_notifier.notify_error(
                            message=error_msg,
                            system_name="CvxCrvStake to OHLC Migrator"
                        )
                    return False
            else:
                self.logger.warning("⚠️ gov用のOHLCデータがありません")
            
            # 4. stablecoinデータを保存
            if stablecoin_ohlc_data:
                if not self.save_ohlc_data(stablecoin_ohlc_data, 'stablecoin'):
                    error_msg = "❌ stablecoin OHLCデータ保存に失敗しました。"
                    self.logger.error(error_msg)
                    if self.slack_notifier:
                        self.slack_notifier.notify_error(
                            message=error_msg,
                            system_name="CvxCrvStake to OHLC Migrator"
                        )
                    return False
            else:
                self.logger.warning("⚠️ stablecoin用のOHLCデータがありません")
            
            # 5. tvlデータを保存
            if tvl_ohlc_data:
                if not self.save_ohlc_data(tvl_ohlc_data, 'tvl'):
                    error_msg = "❌ tvl OHLCデータ保存に失敗しました。"
                    self.logger.error(error_msg)
                    if self.slack_notifier:
                        self.slack_notifier.notify_error(
                            message=error_msg,
                            system_name="CvxCrvStake to OHLC Migrator"
                        )
                    return False
            else:
                self.logger.warning("⚠️ tvl用のOHLCデータがありません")
            
            self.logger.info("=" * 60)
            self.logger.info("✅ 移行処理が正常に完了しました")
            
            if self.slack_notifier:
                self.slack_notifier.notify_success(
                    message="CvxCrvStakeMetricsからCvxCrvStakeOHLCDailyへの移行が完了しました",
                    system_name="CvxCrvStake to OHLC Migrator"
                )
            
            return True
            
        except Exception as e:
            error_msg = f"❌ 移行処理エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="CvxCrvStake to OHLC Migrator",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    migrator = CvxCrvStakeToOHLCMigrator()
    success = migrator.run_migration()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

