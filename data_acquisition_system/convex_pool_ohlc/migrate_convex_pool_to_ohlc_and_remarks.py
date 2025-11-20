#!/usr/bin/env python3
# =====================================
# ConvexPoolMetricsからConvexPoolOHLCDailyとConvexPoolRemarksHistoryへのデータ移行スクリプト
# ConvexPoolMetricsテーブルのデータ（2025年11月19日まで）を
# 1. ConvexPoolOHLCDailyテーブルのOHLC形式に集約して保存
# 2. ConvexPoolRemarksHistoryテーブルにRemarksが空でないデータを保存
# =====================================

import boto3
from boto3.dynamodb.conditions import Key, Attr
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
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from utils.slack_notifier import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

class ConvexPoolToOHLCAndRemarksMigrator:
    def __init__(self):
        """ConvexPoolMetricsからOHLCとRemarks履歴への移行システムの初期化"""
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
        self.metrics_table = None
        self.ohlc_table = None
        self.remarks_table = None
        self.history_table = None
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
        
        # 終了日（2025年11月19日）
        self.end_date = datetime(2025, 11, 19, 23, 59, 59, tzinfo=self.JST)
        
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
        log_file = Path(__file__).parent / 'migrate_convex_pool_to_ohlc_and_remarks.log'
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
            self.metrics_table = self.dynamodb.Table('ConvexPoolMetrics')
            self.metrics_table.load()
            self.logger.info("✅ ConvexPoolMetricsテーブルに接続しました")
            
            self.ohlc_table = self.dynamodb.Table('ConvexPoolOHLCDaily')
            self.ohlc_table.load()
            self.logger.info("✅ ConvexPoolOHLCDailyテーブルに接続しました")
            
            self.remarks_table = self.dynamodb.Table('ConvexPoolRemarksHistory')
            self.remarks_table.load()
            self.logger.info("✅ ConvexPoolRemarksHistoryテーブルに接続しました")
                    
        except ClientError as e:
            error_msg = f"❌ テーブル接続エラー: {e}"
            self.logger.error(error_msg)
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPool to OHLC and Remarks Migrator",
                    error=e
                )
            raise e
    
    def get_convex_pool_metrics_data(self):
        """ConvexPoolMetricsテーブルからデータを取得（2025年11月19日まで）"""
        try:
            self.logger.info("📊 ConvexPoolMetricsテーブルからデータ取得中...")
            self.logger.info(f"   終了日: {self.end_date.strftime('%Y-%m-%d %H:%M:%S')} JST")
            
            all_items = []
            last_evaluated_key = None
            
            while True:
                scan_params = {}
                
                if last_evaluated_key:
                    scan_params['ExclusiveStartKey'] = last_evaluated_key
                
                response = self.metrics_table.scan(**scan_params)
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
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                        continue
                
                all_items.extend(filtered_items)
                
                # ページネーション
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
                
                if len(all_items) % 1000 == 0:
                    self.logger.info(f"   📊 取得中... {len(all_items)}件")
            
            self.logger.info(f"✅ {len(all_items)}件のデータを取得しました")
            return all_items
            
        except Exception as e:
            error_msg = f"❌ データ取得エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPool to OHLC and Remarks Migrator",
                    error=e
                )
            return []
    
    def aggregate_ohlc_data(self, items: List[Dict], type_name: str) -> Dict[Tuple[str, str], Dict]:
        """
        OHLCデータを日次で集約
        type_name: 'current_vapr', 'projected_vapr', 'tvl', または 'veCRV_boost'
        戻り値: {(pool_id, date_key): ohlc_data}
        """
        if not items:
            self.logger.warning(f"⚠️ {type_name}用の集約するデータがありません")
            return {}
        
        # pool_idと日付ごとにデータをグループ化
        pool_date_data = defaultdict(list)
        
        for item in items:
            pool_id = item.get('pool_id', '')
            timestamp_str = item.get('timestamp', '')
            
            # typeに応じた数値フィールドを取得
            if type_name == 'current_vapr':
                value_numeric = item.get('current_vapr_numeric')
            elif type_name == 'projected_vapr':
                value_numeric = item.get('projected_vapr_numeric')
            elif type_name == 'tvl':
                value_numeric = item.get('tvl_numeric')
            elif type_name == 'veCRV_boost':
                # veCRV_boostは文字列から数値を抽出する必要がある場合がある
                vecrv_boost_str = item.get('veCRV_boost', '')
                if vecrv_boost_str:
                    # "2.5x" のような形式から数値を抽出
                    try:
                        value_numeric = float(str(vecrv_boost_str).replace('x', '').strip())
                    except (ValueError, TypeError):
                        value_numeric = item.get('veCRV_boost_numeric')
                else:
                    value_numeric = item.get('veCRV_boost_numeric')
            else:
                continue
            
            if not pool_id or not timestamp_str or value_numeric is None:
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
                
                pool_date_data[(pool_id, date_key)].append({
                    'timestamp': timestamp_str,
                    'timestamp_jst': timestamp_jst,
                    'value': value,
                    'data_source': item.get('data_source', 'convex_ec2_complete'),
                    'Pool': item.get('Pool', ''),
                    'factory_id': item.get('factory_id', '')
                })
                
            except (ValueError, TypeError) as e:
                self.logger.warning(f"⚠️ タイムスタンプ解析エラー: {timestamp_str} - {e}")
                continue
        
        # OHLCデータを計算
        ohlc_data = {}
        for (pool_id, date_key), values in pool_date_data.items():
            # タイムスタンプでソート
            sorted_values = sorted(values, key=lambda x: x['timestamp'])
            
            if sorted_values:
                # Open, High, Low, Closeを計算
                open_value = sorted_values[0]['value']
                close_value = sorted_values[-1]['value']
                high_value = max(v['value'] for v in sorted_values)
                low_value = min(v['value'] for v in sorted_values)
                sample_count = len(sorted_values)
                
                # データソースとPool、factory_idを取得（最初のアイテムから）
                data_source = sorted_values[0].get('data_source', 'convex_ec2_complete')
                pool_name = sorted_values[0].get('Pool', '')
                factory_id = sorted_values[0].get('factory_id', '')
                
                ohlc_data[(pool_id, date_key)] = {
                    'pool_id': pool_id,
                    'date_key': date_key,
                    'open': open_value,
                    'high': high_value,
                    'low': low_value,
                    'close': close_value,
                    'sample_count': sample_count,
                    'data_source': data_source,
                    'Pool': pool_name,
                    'factory_id': factory_id
                }
        
        self.logger.info(f"✅ {type_name.upper()} OHLC集約完了: {len(ohlc_data)}件の日次データ")
        return ohlc_data
    
    def check_existing_ohlc_data(self, pool_id: str, type_name: str, date_key: str) -> bool:
        """ConvexPoolOHLCDailyテーブルに既存データがあるかチェック"""
        try:
            # 複合パーティションキー: pool_id#type (例: "usdfi+usdaf+ebusd+bold#current_vapr")
            partition_key = f"{pool_id}#{type_name}"
            response = self.ohlc_table.get_item(
                Key={
                    'pool_id_type': partition_key,  # パーティションキー
                    'timestamp': date_key  # ソートキー
                }
            )
            return 'Item' in response
        except Exception as e:
            self.logger.warning(f"⚠️ 既存データチェックエラー (pool_id: {pool_id}, type: {type_name}, timestamp: {date_key}): {e}")
            return False
    
    def save_ohlc_data(self, ohlc_data: Dict[Tuple[str, str], Dict], type_name: str):
        """OHLCデータをConvexPoolOHLCDailyテーブルに保存"""
        if not ohlc_data:
            self.logger.warning(f"⚠️ 保存する{type_name}用のOHLCデータがありません")
            return False
        
        try:
            self.logger.info(f"💾 ConvexPoolOHLCDailyテーブルに{type_name}データ保存中...")
            
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            skipped_count = 0
            failed_count = 0
            
            # pool_idと日付の組み合わせごとに保存
            # テーブル設計ではpool_id_typeがPK（pool_id#type形式）、timestampがSK
            # これにより、同じpool_idとtypeで複数の日付のデータを保存可能
            for (pool_id, date_key), ohlc in ohlc_data.items():
                try:
                    # 既存データチェック（pool_id、type、timestampの組み合わせでチェック）
                    if self.check_existing_ohlc_data(pool_id, type_name, date_key):
                        self.logger.debug(f"⏭️  {type_name} {pool_id} {date_key} は既に存在するためスキップ")
                        skipped_count += 1
                        continue
                    
                    # 日付のdatetimeオブジェクトを作成（JST、0時0分0秒）
                    date_dt = datetime.strptime(date_key, '%Y-%m-%d').replace(
                        hour=0, minute=0, second=0, microsecond=0, tzinfo=self.JST
                    )
                    jst_datetime = date_dt.isoformat()
                    
                    # 複合パーティションキー: pool_id#type (例: "usdfi+usdaf+ebusd+bold#current_vapr")
                    partition_key = f"{pool_id}#{type_name}"
                    
                    item = {
                        'pool_id_type': partition_key,  # パーティションキー（pool_id#type形式）
                        'timestamp': date_key,  # ソートキー（日付形式 YYYY-MM-DD）
                        'pool_id': pool_id,  # 属性（元のpool_id）
                        'type': type_name,  # 属性（current_vapr, projected_vapr, tvl, veCRV_boost）
                        'timezone': 'JST',
                        'Pool': ohlc.get('Pool', ''),
                        'factory_id': ohlc.get('factory_id', ''),
                        'open': Decimal(str(ohlc['open'])),
                        'high': Decimal(str(ohlc['high'])),
                        'low': Decimal(str(ohlc['low'])),
                        'close': Decimal(str(ohlc['close'])),
                        'sample_count': int(ohlc['sample_count']),
                        'data_source': ohlc.get('data_source', 'convex_ec2_complete'),
                        'datetime': jst_datetime,
                        'created_at': jst_created_at
                    }
                    
                    # None値を除去
                    item = {k: v for k, v in item.items() if v is not None and v != ''}
                    
                    self.ohlc_table.put_item(Item=item)
                    saved_count += 1
                    
                    if saved_count % 100 == 0:
                        self.logger.info(
                            f"📊 {type_name.upper()}保存進捗: {saved_count}件保存完了"
                        )
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"❌ {type_name} {date_key} (pool_id: {pool_id}) 保存エラー: {e}")
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
                        system_name="ConvexPool to OHLC and Remarks Migrator"
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
                    system_name="ConvexPool to OHLC and Remarks Migrator",
                    error=e
                )
            return False
    
    def save_remarks_history(self, items: List[Dict]):
        """Remarksが空でないデータをConvexPoolRemarksHistoryテーブルに保存"""
        try:
            self.logger.info("💾 ConvexPoolRemarksHistoryテーブルにRemarksデータ保存中...")
            
            jst_created_at = datetime.now(self.JST).isoformat()
            
            saved_count = 0
            skipped_count = 0
            failed_count = 0
            
            # Remarksが空でないデータをフィルタリング
            remarks_items = []
            for item in items:
                remarks = item.get('Remarks', '')
                if remarks and str(remarks).strip():
                    remarks_items.append(item)
            
            self.logger.info(f"📊 Remarksが空でないデータ: {len(remarks_items)}件")
            
            for item in remarks_items:
                pool_id = item.get('pool_id', '')
                timestamp_str = item.get('timestamp', '')
                
                if not pool_id or not timestamp_str:
                    continue
                
                try:
                    # 既存データチェック
                    response = self.remarks_table.get_item(
                        Key={
                            'pool_id': pool_id,
                            'timestamp': timestamp_str
                        }
                    )
                    if 'Item' in response:
                        skipped_count += 1
                        continue
                    
                    # ISO形式のタイムスタンプをパースしてJSTに変換
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    timestamp_jst = timestamp.astimezone(self.JST)
                    jst_datetime = timestamp_jst.isoformat()
                    
                    remarks_item = {
                        'pool_id': pool_id,
                        'timestamp': timestamp_str,
                        'timezone': 'JST',
                        'Pool': item.get('Pool', ''),
                        'factory_id': item.get('factory_id', ''),
                        'Remarks': item.get('Remarks', ''),
                        'data_source': item.get('data_source', 'convex_ec2_complete'),
                        'datetime': jst_datetime,
                        'created_at': jst_created_at
                    }
                    
                    # None値を除去
                    remarks_item = {k: v for k, v in remarks_item.items() if v is not None and v != ''}
                    
                    self.remarks_table.put_item(Item=remarks_item)
                    saved_count += 1
                    
                    if saved_count % 100 == 0:
                        self.logger.info(f"📊 Remarks保存進捗: {saved_count}件保存完了")
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"❌ Remarks保存エラー (pool_id: {pool_id}, timestamp: {timestamp_str}): {e}")
                    self.logger.error(traceback.format_exc())
            
            self.logger.info(
                f"📊 Remarks保存結果: "
                f"保存={saved_count}件, スキップ={skipped_count}件, 失敗={failed_count}件"
            )
            
            if failed_count > 0:
                error_msg = f"❌ Remarksデータの保存で{failed_count}件失敗しました"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="ConvexPool to OHLC and Remarks Migrator"
                    )
                return False
            
            return True
            
        except Exception as e:
            error_msg = f"❌ Remarksデータ保存エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPool to OHLC and Remarks Migrator",
                    error=e
                )
            return False
    
    def run_migration(self):
        """移行処理を実行"""
        self.logger.info("🚀 ConvexPoolMetricsからOHLCとRemarks履歴への移行開始")
        self.logger.info("=" * 60)
        
        try:
            # 1. ConvexPoolMetricsデータを取得
            items = self.get_convex_pool_metrics_data()
            
            if not items:
                self.logger.warning("⚠️ 取得したデータが1件もありません。処理を終了します。")
                return False
            
            # 2. OHLCデータを集約（current_vapr, projected_vapr, tvl, veCRV_boost）
            self.logger.info("📊 OHLCデータ集約中...")
            
            current_vapr_ohlc = self.aggregate_ohlc_data(items, 'current_vapr')
            projected_vapr_ohlc = self.aggregate_ohlc_data(items, 'projected_vapr')
            tvl_ohlc = self.aggregate_ohlc_data(items, 'tvl')
            vecrv_boost_ohlc = self.aggregate_ohlc_data(items, 'veCRV_boost')
            
            # 3. OHLCデータを保存
            success = True
            
            if current_vapr_ohlc:
                if not self.save_ohlc_data(current_vapr_ohlc, 'current_vapr'):
                    success = False
            else:
                self.logger.warning("⚠️ current_vapr用のOHLCデータがありません")
            
            if projected_vapr_ohlc:
                if not self.save_ohlc_data(projected_vapr_ohlc, 'projected_vapr'):
                    success = False
            else:
                self.logger.warning("⚠️ projected_vapr用のOHLCデータがありません")
            
            if tvl_ohlc:
                if not self.save_ohlc_data(tvl_ohlc, 'tvl'):
                    success = False
            else:
                self.logger.warning("⚠️ tvl用のOHLCデータがありません")
            
            if vecrv_boost_ohlc:
                if not self.save_ohlc_data(vecrv_boost_ohlc, 'veCRV_boost'):
                    success = False
            else:
                self.logger.warning("⚠️ veCRV_boost用のOHLCデータがありません")
            
            # 4. Remarks履歴を保存
            if not self.save_remarks_history(items):
                success = False
            
            if success:
                self.logger.info("=" * 60)
                self.logger.info("✅ 移行処理が正常に完了しました")
                
                if self.slack_notifier:
                    self.slack_notifier.notify_success(
                        message="ConvexPoolMetricsからOHLCとRemarks履歴への移行が完了しました",
                        system_name="ConvexPool to OHLC and Remarks Migrator"
                    )
                
                return True
            else:
                error_msg = "❌ 移行処理の一部が失敗しました"
                self.logger.error(error_msg)
                if self.slack_notifier:
                    self.slack_notifier.notify_error(
                        message=error_msg,
                        system_name="ConvexPool to OHLC and Remarks Migrator"
                    )
                return False
            
        except Exception as e:
            error_msg = f"❌ 移行処理エラー: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            if self.slack_notifier:
                self.slack_notifier.notify_error(
                    message=error_msg,
                    system_name="ConvexPool to OHLC and Remarks Migrator",
                    error=e
                )
            return False


def main():
    """メイン処理"""
    migrator = ConvexPoolToOHLCAndRemarksMigrator()
    success = migrator.run_migration()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

