# =====================================
# DynamoDB全テーブルデータ確認ツール
# Google Colab用 - 包括的ビューアー
# PoolLatest・PriceHistoryテーブル対応版
# =====================================

import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from IPython.display import display, HTML
import warnings
import decimal
warnings.filterwarnings('ignore')

def convert_decimal_to_float(obj):
    """Decimal型をfloat型に変換する再帰関数"""
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_float(item) for item in obj]
    else:
        return obj

# 日本語フォント設定
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.style.use('default')

print("📊 DynamoDB包括的データビューアー準備完了!")
print("🔧 必要なライブラリがインストールされました")

# セル2: データ取得・表示クラス
class DynamoDBComprehensiveViewer:
    def __init__(self):
        """DynamoDBビューアーの初期化"""
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.tables = {
                'CvxStakeMetrics': {
                    'name': 'CVXステーキングデータ',
                    'description': 'CVXトークンのステーキング情報',
                    'key_attr': 'token',
                    'key_value': 'CVX',
                    'sort_key': 'timestamp'
                },
                'CvxCrvStakeMetrics': {
                    'name': 'cvxCRVステーキングデータ',
                    'description': 'cvxCRVトークンのステーキング情報',
                    'key_attr': 'stake',
                    'key_value': 'cvxCRV',
                    'sort_key': 'timestamp'
                },
                'ConvexPoolMetrics': {
                    'name': 'Convexプールデータ',
                    'description': 'Curveプールの収益性情報',
                    'key_attr': 'pool_id',
                    'key_value': None,  # 複数のプールがあるため
                    'sort_key': 'timestamp'
                },
                'PoolLatest': {
                    'name': 'プール最新データ',
                    'description': '各プールの最新状態情報',
                    'key_attr': 'pool_id',
                    'key_value': None,  # 複数のプールがあるため
                    'sort_key': None  # 最新データのみ
                },
                'PriceHistory': {
                    'name': '価格履歴データ',
                    'description': 'トークン価格の履歴情報',
                    'key_attr': 'symbol',
                    'key_value': None,  # 複数のトークンがあるため
                    'sort_key': 'timestamp'
                },
                'PoolMeta': {
                    'name': 'プールメタデータ',
                    'description': 'プールの詳細メタ情報',
                    'key_attr': 'pool_id',
                    'key_value': None,  # 複数のプールがあるため
                    'sort_key': None  # メタデータのみ
                },
                'VaultMeta': {
                    'name': 'ボルトメタデータ',
                    'description': 'ボルトの詳細メタ情報',
                    'key_attr': 'vault_id',
                    'key_value': None,  # 複数のボルトがあるため
                    'sort_key': None  # メタデータのみ
                },
                'TokenPriceHistory': {
                    'name': 'トークン価格履歴データ',
                    'description': 'トークン価格の詳細履歴情報',
                    'key_attr': 'symbol',
                    'key_value': None,  # 複数のトークンがあるため
                    'sort_key': 'timestamp'
                }
            }
            self.connection_status = True
            print("✅ DynamoDB接続成功")
        except Exception as e:
            self.connection_status = False
            print(f"❌ DynamoDB接続エラー: {e}")

    def get_table_summary(self):
        """全テーブルのサマリー情報を取得"""
        if not self.connection_status:
            print("❌ DynamoDBに接続できません")
            return

        print("📊 テーブルサマリー")
        print("="*60)

        summary_data = []

        for table_name, config in self.tables.items():
            try:
                table = self.dynamodb.Table(table_name)

                # 件数取得
                count_response = table.scan(Select='COUNT')
                total_count = count_response['Count']

                # 最新データ取得
                if config['key_value']:
                    latest_response = table.query(
                        KeyConditionExpression=Key(config['key_attr']).eq(config['key_value']),
                        ScanIndexForward=False,
                        Limit=1
                    )
                    latest_item = convert_decimal_to_float(latest_response['Items'][0]) if latest_response['Items'] else None
                    latest_timestamp = latest_item['timestamp'] if latest_item and 'timestamp' in latest_item else 'N/A'
                else:
                    # 複数のレコードがあるテーブルの場合、timestampでソートして最新データを取得
                    try:
                        # PoolLatestテーブルの場合は特別処理
                        if table_name == 'PoolLatest':
                            # PoolLatestテーブルは最新データのみを格納するため、単純にスキャンして最新を取得
                            response = table.scan(Limit=1)
                            if response['Items']:
                                latest_item = convert_decimal_to_float(response['Items'][0])
                                latest_timestamp = latest_item.get('timestamp', 'N/A')
                            else:
                                latest_timestamp = 'N/A'
                        else:
                            # その他のテーブルの場合、timestampフィールドが存在するかチェック
                            # まずサンプルデータを取得してtimestampフィールドの存在を確認
                            sample_response = table.scan(Limit=1)
                            if sample_response['Items'] and 'timestamp' in sample_response['Items'][0]:
                                # 全データをスキャンして最新のtimestampを特定
                                response = table.scan(ProjectionExpression='#ts', ExpressionAttributeNames={'#ts': 'timestamp'})
                                timestamps = [item['timestamp'] for item in response['Items']]

                                # ページネーション対応
                                while 'LastEvaluatedKey' in response:
                                    response = table.scan(
                                        ProjectionExpression='#ts',
                                        ExpressionAttributeNames={'#ts': 'timestamp'},
                                        ExclusiveStartKey=response['LastEvaluatedKey']
                                    )
                                    timestamps.extend([item['timestamp'] for item in response['Items']])

                                # 日時文字列を適切にソートして最新を取得
                                if timestamps:
                                    try:
                                        # ISO8601形式の日時文字列をdatetimeオブジェクトに変換してソート
                                        datetime_objects = []
                                        for ts in timestamps:
                                            try:
                                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                                datetime_objects.append((dt, ts))
                                            except:
                                                # 変換できない場合は文字列として扱う
                                                datetime_objects.append((datetime.min, ts))

                                        # 日時でソートして最新を取得
                                        latest_datetime, latest_timestamp = max(datetime_objects, key=lambda x: x[0])
                                    except Exception as e:
                                        # フォールバック: 文字列の最大値を使用
                                        latest_timestamp = max(timestamps)
                                else:
                                    latest_timestamp = 'N/A'
                            else:
                                # timestampフィールドが存在しない場合は、単純にスキャンして最新を取得
                                response = table.scan(Limit=1)
                                if response['Items']:
                                    latest_item = convert_decimal_to_float(response['Items'][0])
                                    # 利用可能な日時フィールドを探す
                                    for field in ['created_at', 'updated_at', 'datetime']:
                                        if field in latest_item:
                                            latest_timestamp = latest_item[field]
                                            break
                                    else:
                                        latest_timestamp = 'N/A'
                                else:
                                    latest_timestamp = 'N/A'
                    except Exception as e:
                        print(f"⚠️ {table_name}の最新データ取得でエラー: {e}")
                        latest_timestamp = 'エラー'

                summary_data.append({
                    'テーブル名': table_name,
                    '説明': config['name'],
                    '総件数': f"{total_count:,}件",
                    '最新データ': latest_timestamp
                })

                print(f"📈 {config['name']}")
                print(f"   件数: {total_count:,}件")
                print(f"   最新: {latest_timestamp}")
                print()

            except Exception as e:
                print(f"❌ {table_name}: エラー ({e})")
                summary_data.append({
                    'テーブル名': table_name,
                    '説明': config['name'],
                    '総件数': 'エラー',
                    '最新データ': 'エラー'
                })

        # サマリーをDataFrameで表示
        summary_df = pd.DataFrame(summary_data)
        display(summary_df)
        return summary_df

    def get_cvx_data(self, limit=10, days=None):
        """CVXデータを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('CvxStakeMetrics')

            # 条件設定
            query_params = {
                'KeyConditionExpression': Key('token').eq('CVX'),
                'ScanIndexForward': False,
                'Limit': limit
            }

            # daysパラメータはCVXデータでは使用しない（パーティションキー制限のため）

            response = table.query(**query_params)

            if response['Items']:
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in response['Items']]
                df = pd.DataFrame(converted_items)

                # 数値変換（Decimal型対応）
                if 'vapr_numeric' not in df.columns:
                    if 'vapr' in df.columns:
                        df['vapr_numeric'] = pd.to_numeric(df['vapr'].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce')
                else:
                    df['vapr_numeric'] = pd.to_numeric(df['vapr_numeric'], errors='coerce')

                if 'tvl_numeric' not in df.columns:
                    if 'tvl' in df.columns:
                        df['tvl_numeric'] = pd.to_numeric(df['tvl'].astype(str).str.replace('$', '').str.replace(',', '').str.replace('M', '000000').str.replace('B', '000000000'), errors='coerce')
                else:
                    df['tvl_numeric'] = pd.to_numeric(df['tvl_numeric'], errors='coerce')

                # タイムスタンプを日時型に変換（タイムゾーン問題を回避）
                try:
                    # まず文字列として処理してから日時変換
                    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                    # タイムゾーン情報を完全に除去（UTC+09:00などの形式に対応）
                    if df['datetime'].dt.tz is not None:
                        df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                except Exception as e:
                    try:
                        # フォールバック: 文字列から直接変換
                        df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e2:
                        print(f"⚠️ 日時変換でエラー: {e2}")
                        df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                # 日付フィルタリング（データ取得後）
                if days:
                    try:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        # タイムゾーン情報を除去したdatetimeで比較
                        cutoff_date_naive = cutoff_date.replace(tzinfo=None)
                        df = df[df['datetime'] >= cutoff_date_naive]
                        print(f"📊 CVXデータ取得完了: {len(df)}件 (過去{days}日分)")
                    except Exception as e:
                        print(f"⚠️ 日付フィルタリングでエラー: {e}")
                        print(f"📊 CVXデータ取得完了: {len(df)}件")
                else:
                    print(f"📊 CVXデータ取得完了: {len(df)}件")

                return df
            else:
                print("❌ CVXデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ CVXデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_cvxcrv_data(self, limit=10, days=None):
        """cvxCRVデータを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('CvxCrvStakeMetrics')

            query_params = {
                'KeyConditionExpression': Key('stake').eq('cvxCRV'),
                'ScanIndexForward': False,
                'Limit': limit
            }

            # daysパラメータはcvxCRVデータでは使用しない（パーティションキー制限のため）

            response = table.query(**query_params)

            if response['Items']:
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in response['Items']]
                df = pd.DataFrame(converted_items)

                # 数値変換（Decimal型対応）
                for col in ['max_vapr_gov_numeric', 'max_vapr_stable_numeric', 'tvl_numeric']:
                    if col not in df.columns:
                        source_col = col.replace('_numeric', '')
                        if source_col in df.columns:
                            df[col] = pd.to_numeric(df[source_col].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce')
                    else:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                # タイムスタンプを日時型に変換（タイムゾーン問題を回避）
                try:
                    # まず文字列として処理してから日時変換
                    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                    # タイムゾーン情報を完全に除去（UTC+09:00などの形式に対応）
                    if df['datetime'].dt.tz is not None:
                        df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                except Exception as e:
                    try:
                        # フォールバック: 文字列から直接変換
                        df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e2:
                        print(f"⚠️ 日時変換でエラー: {e2}")
                        df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                # 日付フィルタリング（データ取得後）
                if days:
                    try:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        # タイムゾーン情報を除去したdatetimeで比較
                        cutoff_date_naive = cutoff_date.replace(tzinfo=None)
                        df = df[df['datetime'] >= cutoff_date_naive]
                        print(f"📊 cvxCRVデータ取得完了: {len(df)}件 (過去{days}日分)")
                    except Exception as e:
                        print(f"⚠️ 日付フィルタリングでエラー: {e}")
                        print(f"📊 cvxCRVデータ取得完了: {len(df)}件")
                else:
                    print(f"📊 cvxCRVデータ取得完了: {len(df)}件")

                return df
            else:
                print("❌ cvxCRVデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ cvxCRVデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_pools_data(self, limit=100, days=None, min_apr=None):
        """プールデータを取得（ページネーション対応）"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('ConvexPoolMetrics')

            # フィルター条件を構築
            filter_conditions = []

            if min_apr:
                filter_conditions.append(Attr('current_vapr_numeric').gte(min_apr))

            # ページネーション対応のスキャン処理
            all_items = []
            scan_params = {'Limit': min(limit, 1000)}  # DynamoDBの1回のスキャン上限
            
            if filter_conditions:
                scan_params['FilterExpression'] = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    scan_params['FilterExpression'] = scan_params['FilterExpression'] & condition

            print(f"🔍 ConvexPoolMetricsテーブルに接続中... (limit: {limit})")
            response = table.scan(**scan_params)
            
            # 最初のページのデータを追加
            all_items.extend(response['Items'])
            
            # ページネーション処理
            while 'LastEvaluatedKey' in response and len(all_items) < limit:
                remaining_limit = limit - len(all_items)
                if remaining_limit <= 0:
                    break
                    
                scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                scan_params['Limit'] = min(remaining_limit, 1000)
                
                response = table.scan(**scan_params)
                all_items.extend(response['Items'])
                
                print(f"   📊 取得中... {len(all_items)}件")
            
            # 指定されたlimitで切り詰め
            all_items = all_items[:limit]

            if all_items:
                print(f"   📊 ConvexPoolMetricsデータ取得: {len(all_items)}件")
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in all_items]
                df = pd.DataFrame(converted_items)

                # 数値変換（Decimal型対応）
                numeric_columns = ['current_vapr_numeric', 'projected_vapr_numeric', 'tvl_numeric']
                for col in numeric_columns:
                    if col not in df.columns:
                        source_col = col.replace('_numeric', '')
                        if source_col in df.columns:
                            # 文字列から数値への変換
                            df[col] = pd.to_numeric(df[source_col].astype(str).str.replace('%', '').str.replace(',', '').str.replace('$', '').str.replace('M', '000000').str.replace('B', '000000000'), errors='coerce')
                    else:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                # タイムスタンプを日時型に変換（タイムゾーン問題を回避）
                try:
                    # まず文字列として処理してから日時変換
                    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                    # タイムゾーン情報を完全に除去（UTC+09:00などの形式に対応）
                    if df['datetime'].dt.tz is not None:
                        df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                except Exception as e:
                    try:
                        # フォールバック: 文字列から直接変換
                        df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e2:
                        print(f"⚠️ 日時変換でエラー: {e2}")
                        df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                # 日付フィルタリング（データ取得後）
                if days:
                    try:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        # タイムゾーン情報を除去したdatetimeで比較
                        cutoff_date_naive = cutoff_date.replace(tzinfo=None)
                        df = df[df['datetime'] >= cutoff_date_naive]
                        print(f"📊 プールデータ取得完了: {len(df)}件 (過去{days}日分)")
                    except Exception as e:
                        print(f"⚠️ 日付フィルタリングでエラー: {e}")
                        print(f"📊 プールデータ取得完了: {len(df)}件")
                else:
                    print(f"📊 プールデータ取得完了: {len(df)}件")

                return df
            else:
                print("❌ プールデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ プールデータ取得エラー: {e}")
            print(f"   詳細: {type(e).__name__}: {str(e)}")
            return pd.DataFrame()

    def get_pool_latest_data(self, limit=100, min_apr=None):
        """PoolLatestテーブルの最新データを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('PoolLatest')

            # フィルター条件を構築
            filter_conditions = []

            if min_apr:
                # PoolLatestテーブルのAPR関連フィールドを確認してフィルタリング
                filter_conditions.append(Attr('current_vapr_numeric').gte(min_apr))

            scan_params = {'Limit': limit}
            if filter_conditions:
                scan_params['FilterExpression'] = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    scan_params['FilterExpression'] = scan_params['FilterExpression'] & condition

            response = table.scan(**scan_params)

            if response['Items']:
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in response['Items']]
                df = pd.DataFrame(converted_items)

                # 数値変換（Decimal型対応）
                numeric_columns = ['current_vapr_numeric', 'projected_vapr_numeric', 'tvl_numeric']
                for col in numeric_columns:
                    if col not in df.columns:
                        source_col = col.replace('_numeric', '')
                        if source_col in df.columns:
                            # 文字列から数値への変換
                            df[col] = pd.to_numeric(df[source_col].astype(str).str.replace('%', '').str.replace(',', '').str.replace('$', '').str.replace('M', '000000').str.replace('B', '000000000'), errors='coerce')
                    else:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                print(f"📊 PoolLatestデータ取得完了: {len(df)}件")
                return df
            else:
                print("❌ PoolLatestデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ PoolLatestデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_price_history_data(self, limit=1000, days=None, symbol=None):
        """PriceHistoryテーブルの価格履歴データを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('PriceHistory')

            # フィルター条件を構築
            filter_conditions = []

            if symbol:
                # assetカラムでフィルタリング（PriceHistoryテーブルにはassetカラムがある）
                filter_conditions.append(Attr('asset').eq(symbol))

            scan_params = {'Limit': limit}
            if filter_conditions:
                scan_params['FilterExpression'] = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    scan_params['FilterExpression'] = scan_params['FilterExpression'] & condition

            print(f"🔍 PriceHistoryテーブルに接続中... (limit: {limit})")
            response = table.scan(**scan_params)

            if response['Items']:
                print(f"   📊 PriceHistoryデータ取得: {len(response['Items'])}件")
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in response['Items']]
                df = pd.DataFrame(converted_items)

                print(f"   📋 カラム一覧: {list(df.columns)}")

                # 数値変換（Decimal型対応）
                numeric_columns = ['price', 'price_usd', 'price_jpy', 'market_cap', 'volume_24h', 'market_cap_numeric', 'price_numeric', 'rate']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"   ✅ {col}を数値変換")

                # タイムスタンプを日時型に変換（タイムゾーン問題を回避）
                try:
                    # まず文字列として処理してから日時変換
                    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                    # タイムゾーン情報を完全に除去（UTC+09:00などの形式に対応）
                    if df['datetime'].dt.tz is not None:
                        df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                except Exception as e:
                    try:
                        # フォールバック: 文字列から直接変換
                        df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e2:
                        print(f"⚠️ 日時変換でエラー: {e2}")
                        df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                # 日付フィルタリング（データ取得後）
                if days:
                    try:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        # タイムゾーン情報を除去したdatetimeで比較
                        cutoff_date_naive = cutoff_date.replace(tzinfo=None)
                        df = df[df['datetime'] >= cutoff_date_naive]
                        print(f"📊 PriceHistoryデータ取得完了: {len(df)}件 (過去{days}日分)")
                    except Exception as e:
                        print(f"⚠️ 日付フィルタリングでエラー: {e}")
                        print(f"📊 PriceHistoryデータ取得完了: {len(df)}件")
                else:
                    print(f"📊 PriceHistoryデータ取得完了: {len(df)}件")

                return df
            else:
                print("❌ PriceHistoryデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ PriceHistoryデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_pool_meta_data(self, limit=5000):
        """PoolMetaテーブルのメタデータを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('PoolMeta')

            # 大量データ対応のため、ページネーション処理を追加
            all_items = []
            scan_params = {'Limit': min(limit, 1000)}  # DynamoDBの1回のスキャン上限
            
            print(f"🔍 PoolMetaテーブルに接続中... (limit: {limit})")
            response = table.scan(**scan_params)
            
            # 最初のページのデータを追加
            all_items.extend(response['Items'])
            
            # ページネーション処理
            while 'LastEvaluatedKey' in response and len(all_items) < limit:
                remaining_limit = limit - len(all_items)
                if remaining_limit <= 0:
                    break
                    
                scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                scan_params['Limit'] = min(remaining_limit, 1000)
                
                response = table.scan(**scan_params)
                all_items.extend(response['Items'])
                
                print(f"   📊 取得中... {len(all_items)}件")
            
            # 指定されたlimitで切り詰め
            all_items = all_items[:limit]

            if all_items:
                print(f"   📊 PoolMetaデータ取得: {len(all_items)}件")
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in all_items]
                df = pd.DataFrame(converted_items)

                print(f"   📋 カラム一覧: {list(df.columns)}")

                # 数値変換（Decimal型対応）
                # pool_idは文字列IDなので数値変換から除外
                numeric_columns = ['tvl', 'apr', 'apy', 'fee', 'volume_24h']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"   ✅ {col}を数値変換")

                # タイムスタンプを日時型に変換（存在する場合）
                if 'timestamp' in df.columns:
                    try:
                        df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e:
                        try:
                            df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                            if df['datetime'].dt.tz is not None:
                                df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                        except Exception as e2:
                            print(f"⚠️ 日時変換でエラー: {e2}")
                            df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                print(f"📊 PoolMetaデータ取得完了: {len(df)}件")
                return df
            else:
                print("❌ PoolMetaデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ PoolMetaデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_vault_meta_data(self, limit=5000):
        """VaultMetaテーブルのメタデータを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('VaultMeta')

            # 大量データ対応のため、ページネーション処理を追加
            all_items = []
            scan_params = {'Limit': min(limit, 1000)}  # DynamoDBの1回のスキャン上限
            
            print(f"🔍 VaultMetaテーブルに接続中... (limit: {limit})")
            response = table.scan(**scan_params)
            
            # 最初のページのデータを追加
            all_items.extend(response['Items'])
            
            # ページネーション処理
            while 'LastEvaluatedKey' in response and len(all_items) < limit:
                remaining_limit = limit - len(all_items)
                if remaining_limit <= 0:
                    break
                    
                scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                scan_params['Limit'] = min(remaining_limit, 1000)
                
                response = table.scan(**scan_params)
                all_items.extend(response['Items'])
                
                print(f"   📊 取得中... {len(all_items)}件")
            
            # 指定されたlimitで切り詰め
            all_items = all_items[:limit]

            if all_items:
                print(f"   📊 VaultMetaデータ取得: {len(all_items)}件")
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in all_items]
                df = pd.DataFrame(converted_items)

                print(f"   📋 カラム一覧: {list(df.columns)}")

                # 数値変換（Decimal型対応）
                # vault_idは文字列IDなので数値変換から除外（再作成後はvault_idがプライマリキー）
                numeric_columns = ['tvl', 'apr', 'apy', 'fee', 'volume_24h', 'total_supply']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"   ✅ {col}を数値変換")

                # タイムスタンプを日時型に変換（存在する場合）
                if 'timestamp' in df.columns:
                    try:
                        df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    except Exception as e:
                        try:
                            df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                            if df['datetime'].dt.tz is not None:
                                df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                        except Exception as e2:
                            print(f"⚠️ 日時変換でエラー: {e2}")
                            df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')

                print(f"📊 VaultMetaデータ取得完了: {len(df)}件")
                return df
            else:
                print("❌ VaultMetaデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ VaultMetaデータ取得エラー: {e}")
            return pd.DataFrame()

    def get_token_price_history_data(self, limit=1000, days=None, symbol=None):
        """TokenPriceHistoryテーブルの価格履歴データを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('TokenPriceHistory')

            # フィルター条件を構築
            filter_conditions = []

            if symbol:
                # symbolカラムでフィルタリング
                filter_conditions.append(Attr('symbol').eq(symbol))

            scan_params = {'Limit': limit}
            if filter_conditions:
                scan_params['FilterExpression'] = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    scan_params['FilterExpression'] = scan_params['FilterExpression'] & condition

            print(f"🔍 TokenPriceHistoryテーブルに接続中... (limit: {limit})")
            response = table.scan(**scan_params)

            if response['Items']:
                print(f"   📊 TokenPriceHistoryデータ取得: {len(response['Items'])}件")
                # Decimal型をfloat型に変換
                converted_items = [convert_decimal_to_float(item) for item in response['Items']]
                df = pd.DataFrame(converted_items)

                print(f"   📋 カラム一覧: {list(df.columns)}")

                # 数値変換（Decimal型対応）
                numeric_columns = ['price_usd', 'price_jpy', 'market_cap', 'volume_24h', 'market_cap_numeric', 'price_numeric', 'rate', 'pool_count']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        print(f"   ✅ {col}を数値変換")
                
                # pool_countを整数に変換
                if 'pool_count' in df.columns:
                    df['pool_count'] = df['pool_count'].astype('Int64')
                    print(f"   ✅ pool_countを整数に変換")

                # タイムスタンプを日時型に変換（タイムゾーン問題を回避）
                try:
                    # まず文字列として処理してから日時変換
                    df['datetime'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                    # タイムゾーン情報を完全に除去（UTC+09:00などの形式に対応）
                    if df['datetime'].dt.tz is not None:
                        df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                    print(f"   ✅ datetimeカラム作成完了")
                except Exception as e:
                    print(f"⚠️ 日時変換でエラー: {e}")
                    try:
                        # フォールバック: 文字列から直接変換
                        df['datetime'] = pd.to_datetime(df['timestamp'].astype(str), errors='coerce')
                        if df['datetime'].dt.tz is not None:
                            df['datetime'] = df['datetime'].dt.tz_convert('UTC').dt.tz_localize(None)
                        print(f"   ✅ datetimeカラム作成完了（フォールバック）")
                    except Exception as e2:
                        print(f"⚠️ 日時変換でエラー: {e2}")
                        df['datetime'] = pd.to_datetime(df['timestamp'], errors='coerce')
                        print(f"   ✅ datetimeカラム作成完了（最終フォールバック）")
                
                # TokenPriceHistoryデータのカラム順序を整理（datetimeカラム作成後）
                print(f"🔧 カラム順序整理実行前: {list(df.columns)}")
                df = self.organize_token_price_history_columns(df)

                # 日付フィルタリング（データ取得後）
                if days:
                    try:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        # タイムゾーン情報を除去したdatetimeで比較
                        cutoff_date_naive = cutoff_date.replace(tzinfo=None)
                        df = df[df['datetime'] >= cutoff_date_naive]
                        # 日付フィルタリング後にカラム順序を再度整理
                        df = self.organize_token_price_history_columns(df)
                        print(f"📊 TokenPriceHistoryデータ取得完了: {len(df)}件 (過去{days}日分)")
                    except Exception as e:
                        print(f"⚠️ 日付フィルタリングでエラー: {e}")
                        print(f"📊 TokenPriceHistoryデータ取得完了: {len(df)}件")
                else:
                    print(f"📊 TokenPriceHistoryデータ取得完了: {len(df)}件")

                return df
            else:
                print("❌ TokenPriceHistoryデータが見つかりません")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ TokenPriceHistoryデータ取得エラー: {e}")
            return pd.DataFrame()

    def display_data_preview(self, df, title, max_rows=5):
        """データのプレビューを表示（CSV出力と同じ項目順序）"""
        if df.empty:
            print(f"❌ {title}: データがありません")
            return

        print(f"\n📊 {title} (最新{min(max_rows, len(df))}件)")
        print("="*50)

        # テーブルタイプに応じてカラム順序を整理
        if 'token' in df.columns and df['token'].iloc[0] == 'CVX':
            # CVXデータ
            df = self.organize_cvx_columns(df)
        elif 'stake' in df.columns and df['stake'].iloc[0] == 'cvxCRV':
            # cvxCRVデータ
            df = self.organize_cvxcrv_columns(df)
        elif 'Pool' in df.columns and 'pool_id' in df.columns:
            # ConvexPoolMetricsデータ
            df = self.organize_pool_metrics_columns(df)
        elif 'Pool' in df.columns and 'pool_id' in df.columns and title == 'PoolLatestデータ':
            # PoolLatestデータ
            df = self.organize_pool_latest_columns(df)
        elif 'asset' in df.columns or 'rate' in df.columns:
            # PriceHistoryデータ
            df = self.organize_price_history_columns(df)
        elif 'symbol' in df.columns and title == 'TokenPriceHistoryデータ':
            # TokenPriceHistoryデータ
            df = self.organize_token_price_history_columns(df)
        elif 'pool_id' in df.columns and title == 'PoolMetaデータ':
            # PoolMetaデータ
            df = self.organize_pool_meta_columns(df)
        elif 'vault_id' in df.columns and title == 'VaultMetaデータ':
            # VaultMetaデータ
            df = self.organize_vault_meta_columns(df)

        preview_df = df.head(max_rows)
        display(preview_df)

    def create_trend_charts(self):
        """トレンドチャートを作成"""
        print("📈 トレンド分析チャート作成中...")

        # CVXデータ取得（より多くのデータを取得してからフィルタリング）
        cvx_df = self.get_cvx_data(limit=1000, days=30)

        # cvxCRVデータ取得（より多くのデータを取得してからフィルタリング）
        cvxcrv_df = self.get_cvxcrv_data(limit=1000, days=30)

        # プールデータ取得（最新）
        pools_df = self.get_pools_data(limit=300)

        # PoolLatestデータ取得（最新のプール状態）
        pool_latest_df = self.get_pool_latest_data(limit=300)

        # PriceHistoryデータ取得
        price_df = self.get_price_history_data(limit=1000, days=30)

        # サブプロット作成（4x2レイアウト）
        fig = make_subplots(
            rows=4, cols=2,
            subplot_titles=('CVX vAPR トレンド', 'cvxCRV vAPR トレンド', '高APRプール分布', 'TVL分布', 'CRV価格トレンド', 'CVX価格トレンド', 'ドル円レート', 'ドル円レート分布'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )

        # CVX vAPRトレンド
        if not cvx_df.empty and 'vapr_numeric' in cvx_df.columns:
            vapr_values = pd.to_numeric(cvx_df['vapr_numeric'], errors='coerce').fillna(0)
            if len(vapr_values) > 0:
                fig.add_trace(
                    go.Scatter(x=cvx_df['datetime'], y=vapr_values,
                              mode='lines+markers', name='CVX vAPR', line=dict(color='blue')),
                    row=1, col=1
                )

        # cvxCRV vAPRトレンド
        if not cvxcrv_df.empty and 'max_vapr_gov_numeric' in cvxcrv_df.columns:
            gov_vapr_values = pd.to_numeric(cvxcrv_df['max_vapr_gov_numeric'], errors='coerce').fillna(0)
            if len(gov_vapr_values) > 0:
                fig.add_trace(
                    go.Scatter(x=cvxcrv_df['datetime'], y=gov_vapr_values,
                              mode='lines+markers', name='cvxCRV Gov vAPR', line=dict(color='green')),
                    row=1, col=2
                )

        # 高APRプール分布（PoolLatestデータを使用）
        if not pool_latest_df.empty and 'current_vapr_numeric' in pool_latest_df.columns:
            # PoolLatestデータは既に最新データなので、そのまま使用
            pool_latest_df['current_vapr_numeric'] = pd.to_numeric(pool_latest_df['current_vapr_numeric'], errors='coerce').fillna(0)
            top_pools = pool_latest_df.nlargest(20, 'current_vapr_numeric')

            fig.add_trace(
                go.Bar(x=top_pools['Pool'], y=top_pools['current_vapr_numeric'],
                       name='プール vAPR (最新)', marker_color='orange'),
                row=2, col=1
            )
        elif not pools_df.empty and 'current_vapr_numeric' in pools_df.columns:
            # フォールバック: ConvexPoolMetricsデータを使用
            latest_timestamp = pools_df['timestamp'].max()
            latest_pools = pools_df[pools_df['timestamp'] == latest_timestamp]
            latest_pools['current_vapr_numeric'] = pd.to_numeric(latest_pools['current_vapr_numeric'], errors='coerce').fillna(0)
            top_pools = latest_pools.nlargest(20, 'current_vapr_numeric')

            fig.add_trace(
                go.Bar(x=top_pools['Pool'], y=top_pools['current_vapr_numeric'],
                       name='プール vAPR (履歴)', marker_color='orange'),
                row=2, col=1
            )

        # TVL分布（PoolLatestデータを使用）
        if not pool_latest_df.empty and 'tvl_numeric' in pool_latest_df.columns:
            # PoolLatestデータは既に最新データなので、そのまま使用
            pool_latest_df['tvl_numeric'] = pd.to_numeric(pool_latest_df['tvl_numeric'], errors='coerce').fillna(0)
            top_tvl_pools = pool_latest_df.nlargest(15, 'tvl_numeric')

            fig.add_trace(
                go.Bar(x=top_tvl_pools['Pool'], y=top_tvl_pools['tvl_numeric'],
                       name='プール TVL (最新)', marker_color='purple'),
                row=2, col=2
            )
        elif not pools_df.empty and 'tvl_numeric' in pools_df.columns:
            # フォールバック: ConvexPoolMetricsデータを使用
            latest_pools = pools_df[pools_df['timestamp'] == pools_df['timestamp'].max()]
            latest_pools['tvl_numeric'] = pd.to_numeric(latest_pools['tvl_numeric'], errors='coerce').fillna(0)
            top_tvl_pools = latest_pools.nlargest(15, 'tvl_numeric')

            fig.add_trace(
                go.Bar(x=top_tvl_pools['Pool'], y=top_tvl_pools['tvl_numeric'],
                       name='プール TVL (履歴)', marker_color='purple'),
                row=2, col=2
            )

        # CRV価格トレンド
        print(f"🔍 PriceHistoryデータ確認: {len(price_df)}件")
        if not price_df.empty:
            print(f"   PriceHistoryカラム: {list(price_df.columns)}")

            # 価格カラムを特定
            price_column = None
            if 'price_usd' in price_df.columns:
                price_column = 'price_usd'
                print("   💰 USD価格を使用")
            elif 'price_jpy' in price_df.columns:
                price_column = 'price_jpy'
                print("   💰 JPY価格を使用")
            elif 'price' in price_df.columns:
                price_column = 'price'
                print("   💰 標準価格を使用")
            elif 'rate' in price_df.columns:
                price_column = 'rate'
                print("   💰 レートを使用")

            if price_column:
                # CRV価格トレンド
                if 'asset' in price_df.columns:
                    crv_data = price_df[price_df['asset'] == 'CRV'].copy()
                elif 'symbol' in price_df.columns:
                    crv_data = price_df[price_df['symbol'] == 'CRV'].copy()
                else:
                    crv_data = pd.DataFrame()

                if not crv_data.empty:
                    # 日時でソート
                    if 'datetime' in crv_data.columns:
                        crv_data = crv_data.sort_values('datetime')
                    elif 'timestamp' in crv_data.columns:
                        crv_data = crv_data.sort_values('timestamp')

                    crv_prices = pd.to_numeric(crv_data[price_column], errors='coerce').fillna(0)
                    crv_prices = crv_prices[crv_prices > 0]  # 正の価格のみ

                    if len(crv_prices) > 0:
                        x_values = crv_data['datetime'] if 'datetime' in crv_data.columns else crv_data['timestamp']
                        fig.add_trace(
                            go.Scatter(x=x_values, y=crv_prices,
                                      mode='lines+markers', name='CRV Price', line=dict(color='red')),
                            row=3, col=1
                        )
                        print(f"   ✅ CRV: {len(crv_prices)}件の価格データを追加")
                    else:
                        print("   ❌ CRVの有効な価格データがありません")
                else:
                    print("   ❌ CRVデータが見つかりません")
            else:
                print("   ❌ 価格カラムが見つかりません")
        else:
            print("   ❌ PriceHistoryデータが空です")

        # CVX価格トレンド
        if not price_df.empty and price_column:
            # CVX価格トレンド
            if 'asset' in price_df.columns:
                cvx_data = price_df[price_df['asset'] == 'CVX'].copy()
            elif 'symbol' in price_df.columns:
                cvx_data = price_df[price_df['symbol'] == 'CVX'].copy()
            else:
                cvx_data = pd.DataFrame()

            if not cvx_data.empty:
                # 日時でソート
                if 'datetime' in cvx_data.columns:
                    cvx_data = cvx_data.sort_values('datetime')
                elif 'timestamp' in cvx_data.columns:
                    cvx_data = cvx_data.sort_values('timestamp')

                cvx_prices = pd.to_numeric(cvx_data[price_column], errors='coerce').fillna(0)
                cvx_prices = cvx_prices[cvx_prices > 0]  # 正の価格のみ

                if len(cvx_prices) > 0:
                    x_values = cvx_data['datetime'] if 'datetime' in cvx_data.columns else cvx_data['timestamp']
                    fig.add_trace(
                        go.Scatter(x=x_values, y=cvx_prices,
                                  mode='lines+markers', name='CVX Price', line=dict(color='blue')),
                        row=3, col=2
                    )
                    print(f"   ✅ CVX: {len(cvx_prices)}件の価格データを追加")
                else:
                    print("   ❌ CVXの有効な価格データがありません")
            else:
                print("   ❌ CVXデータが見つかりません")
        else:
            print("   ❌ CVX価格データがありません")

        # ドル円レートのグラフを追加
        print("💱 ドル円レートデータを確認中...")
        if not price_df.empty:
            # ドル円レートデータを取得（USDJPYまたはJPYレート）
            usdjpy_data = None
            if 'asset' in price_df.columns:
                # assetカラムでUSDJPYまたはJPYを検索
                usdjpy_data = price_df[price_df['asset'].isin(['USDJPY', 'JPY', 'USD/JPY'])]
            elif 'symbol' in price_df.columns:
                # symbolカラムでUSDJPYまたはJPYを検索
                usdjpy_data = price_df[price_df['symbol'].isin(['USDJPY', 'JPY', 'USD/JPY'])]

            if usdjpy_data is not None and not usdjpy_data.empty:
                print(f"   💱 ドル円レートデータ: {len(usdjpy_data)}件")

                # レートカラムを特定
                rate_column = None
                if 'rate' in usdjpy_data.columns:
                    rate_column = 'rate'
                elif 'price' in usdjpy_data.columns:
                    rate_column = 'price'
                elif 'price_jpy' in usdjpy_data.columns:
                    rate_column = 'price_jpy'

                if rate_column:
                    # 日時でソート
                    if 'datetime' in usdjpy_data.columns:
                        usdjpy_data = usdjpy_data.sort_values('datetime')
                    elif 'timestamp' in usdjpy_data.columns:
                        usdjpy_data = usdjpy_data.sort_values('timestamp')

                    rate_values = pd.to_numeric(usdjpy_data[rate_column], errors='coerce').fillna(0)
                    rate_values = rate_values[rate_values > 0]  # 正のレートのみ

                    if len(rate_values) > 0:
                        x_values = usdjpy_data['datetime'] if 'datetime' in usdjpy_data.columns else usdjpy_data['timestamp']

                        # ドル円レートトレンド
                        fig.add_trace(
                            go.Scatter(x=x_values, y=rate_values,
                                      mode='lines+markers', name='ドル円レート', line=dict(color='red')),
                            row=4, col=1
                        )
                        print(f"   ✅ ドル円レートトレンド: {len(rate_values)}件のデータを追加")

                        # ドル円レート分布（最新データ）
                        latest_rates = rate_values.tail(20)  # 最新20件
                        if len(latest_rates) > 0:
                            fig.add_trace(
                                go.Bar(x=[f'Rate_{i}' for i in range(len(latest_rates))], y=latest_rates.values,
                                       name='ドル円レート分布', marker_color='lightcoral'),
                                row=4, col=2
                            )
                            print(f"   ✅ ドル円レート分布: {len(latest_rates)}件のデータを表示")
                    else:
                        print("   ❌ 表示できるドル円レートデータがありません")
                else:
                    print("   ❌ ドル円レートカラムが見つかりません")
            else:
                print("   ❌ ドル円レートデータが見つかりません")
        else:
            print("   ❌ PriceHistoryデータが空です")

        # PriceHistoryデータが空の場合の代替表示
        if price_df.empty:
            print("   🔄 PriceHistoryデータが空のため、代替データを表示します...")

            # 代替案1: 既に取得済みのPoolLatestデータを使用
            if not pool_latest_df.empty:
                print(f"   📊 PoolLatestデータから代替情報を取得: {len(pool_latest_df)}件")

                # TVLベースの分布を表示（CVX価格の代替）
                if 'tvl_numeric' in pool_latest_df.columns:
                    tvl_data = pd.to_numeric(pool_latest_df['tvl_numeric'], errors='coerce').fillna(0)
                    tvl_data = tvl_data[tvl_data > 0].head(10)

                    if len(tvl_data) > 0:
                        pool_names = pool_latest_df['Pool'].head(len(tvl_data)) if 'Pool' in pool_latest_df.columns else [f'Pool_{i}' for i in range(len(tvl_data))]
                        fig.add_trace(
                            go.Bar(x=pool_names, y=tvl_data.values,
                                   name='プールTVL (代替)', marker_color='lightblue'),
                            row=3, col=2
                        )
                        print(f"   ✅ 代替データ: TVL分布を表示")

                # APRベースの分布を表示（CRV価格の代替）
                if 'current_vapr_numeric' in pool_latest_df.columns:
                    apr_data = pd.to_numeric(pool_latest_df['current_vapr_numeric'], errors='coerce').fillna(0)
                    apr_data = apr_data[apr_data > 0].head(10)

                    if len(apr_data) > 0:
                        pool_names = pool_latest_df['Pool'].head(len(apr_data)) if 'Pool' in pool_latest_df.columns else [f'Pool_{i}' for i in range(len(apr_data))]
                        fig.add_trace(
                            go.Bar(x=pool_names, y=apr_data.values,
                                   name='プールAPR (代替)', marker_color='lightcoral'),
                            row=3, col=1
                        )
                        print(f"   ✅ 代替データ: APR分布を表示")

        # レイアウト設定
        fig.update_layout(
            height=1600,  # 4行に増加したため高さを調整
            title_text="Convex Finance 包括的データ分析ダッシュボード",
            showlegend=True
        )

        # 軸ラベル設定
        fig.update_xaxes(title_text="日時", row=1, col=1)
        fig.update_xaxes(title_text="日時", row=1, col=2)
        fig.update_xaxes(title_text="プール名", row=2, col=1)
        fig.update_xaxes(title_text="プール名", row=2, col=2)
        fig.update_xaxes(title_text="日時", row=3, col=1)
        fig.update_xaxes(title_text="日時", row=3, col=2)
        fig.update_xaxes(title_text="日時", row=4, col=1)
        fig.update_xaxes(title_text="データポイント", row=4, col=2)

        fig.update_yaxes(title_text="vAPR (%)", row=1, col=1)
        fig.update_yaxes(title_text="vAPR (%)", row=1, col=2)
        fig.update_yaxes(title_text="vAPR (%)", row=2, col=1)
        fig.update_yaxes(title_text="TVL (USD)", row=2, col=2)
        fig.update_yaxes(title_text="CRV価格 (USD)", row=3, col=1)
        fig.update_yaxes(title_text="CVX価格 (USD)", row=3, col=2)
        fig.update_yaxes(title_text="レート (JPY)", row=4, col=1)
        fig.update_yaxes(title_text="レート (JPY)", row=4, col=2)

        fig.show()

    def find_best_opportunities(self, min_apr=15, min_tvl=1000000):
        """最高の投資機会を発見（PoolLatestデータを使用）"""
        print(f"🔍 投資機会分析 (vAPR > {min_apr}%, TVL > ${min_tvl:,})")
        print("="*60)

        # PoolLatestデータを優先使用
        pool_latest_df = self.get_pool_latest_data(limit=500)

        if not pool_latest_df.empty:
            print("📊 PoolLatestテーブルから最新データを取得")
            opportunities = pool_latest_df.copy()
        else:
            # フォールバック: ConvexPoolMetricsデータを使用
            print("📊 PoolLatestデータが利用できないため、ConvexPoolMetricsデータを使用")
            pools_df = self.get_pools_data(limit=500, min_apr=min_apr)

            if pools_df.empty:
                print("❌ 条件に合うプールが見つかりません")
                return

            # 最新データのみ
            latest_timestamp = pools_df['timestamp'].max()
            opportunities = pools_df[pools_df['timestamp'] == latest_timestamp]

        # APR条件でフィルタリング
        if 'current_vapr_numeric' in opportunities.columns:
            opportunities['current_vapr_numeric'] = pd.to_numeric(opportunities['current_vapr_numeric'], errors='coerce').fillna(0)
            opportunities = opportunities[opportunities['current_vapr_numeric'] >= min_apr]

        # TVL条件でフィルタリング
        if 'tvl_numeric' in opportunities.columns:
            opportunities['tvl_numeric'] = pd.to_numeric(opportunities['tvl_numeric'], errors='coerce').fillna(0)
            opportunities = opportunities[opportunities['tvl_numeric'] >= min_tvl]

        if opportunities.empty:
            print(f"❌ 条件に合うプールが見つかりません (vAPR > {min_apr}%, TVL > ${min_tvl:,})")
            return

        # スコア計算（vAPR * log(TVL)）- Decimal型対応
        if 'current_vapr_numeric' in opportunities.columns and 'tvl_numeric' in opportunities.columns:
            # Decimal型をfloat型に変換してから計算
            vapr_values = pd.to_numeric(opportunities['current_vapr_numeric'], errors='coerce').fillna(0)
            tvl_values = pd.to_numeric(opportunities['tvl_numeric'], errors='coerce').fillna(1)
            # log(0)やlog(負の値)を避けるため、最小値を1に設定
            tvl_values = tvl_values.clip(lower=1)
            opportunities['score'] = vapr_values * np.log(tvl_values)
            opportunities = opportunities.sort_values('score', ascending=False)

        print(f"🎯 発見された投資機会: {len(opportunities)}件")
        print()

        # 結果表示（カラム順序を整理）
        opportunities = self.organize_pool_latest_columns(opportunities)
        print(f"📋 表示カラム順序: {list(opportunities.columns)}")
        
        display_cols = ['Pool', 'Current_vAPR', 'TVL', 'veCRV_boost']
        if 'current_vapr_numeric' in opportunities.columns:
            display_cols.append('current_vapr_numeric')
        if 'tvl_numeric' in opportunities.columns:
            display_cols.append('tvl_numeric')

        display_cols = [col for col in display_cols if col in opportunities.columns]

        for i, (_, row) in enumerate(opportunities.head(10).iterrows(), 1):
            print(f"🏆 ランク {i}: {row.get('Pool', 'Unknown')}")
            print(f"   Current vAPR: {row.get('Current_vAPR', 'N/A')}")
            print(f"   TVL: {row.get('TVL', 'N/A')}")
            print(f"   veCRV Boost: {row.get('veCRV_boost', 'N/A')}")
            if 'Remarks' in row and pd.notna(row['Remarks']) and row['Remarks']:
                print(f"   備考: {row['Remarks']}")
            print()

    def organize_cvx_columns(self, df):
        """CVXデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト
        desired_columns = [
            'timezone', 'timestamp', 'token', 'vapr', 'tvl', 
            'vapr_numeric', 'tvl_numeric', 'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_cvxcrv_columns(self, df):
        """cvxCRVデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト
        desired_columns = [
            'timezone', 'timestamp', 'pool', 'stake', 'max_vapr_gov_token_rewards', 
            'max_vapr_stablecoin_rewards', 'tvl', 'max_vapr_gov_numeric', 
            'max_vapr_stable_numeric', 'tvl_numeric', 'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_pool_metrics_columns(self, df):
        """ConvexPoolMetricsデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト
        desired_columns = [
            'timezone', 'timestamp', 'Pool', 'pool_id', 'factory_id', 'Current_vAPR', 
            'Projected_vAPR', 'TVL', 'veCRV_boost', 'Remarks', 
            'current_vapr_numeric', 'projected_vapr_numeric', 'tvl_numeric', 
            'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_pool_latest_columns(self, df):
        """PoolLatestデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト（PoolLatest用）
        desired_columns = [
            'timezone', 'timestamp', 'Pool', 'pool_id', 'Current_vAPR', 
            'Projected_vAPR', 'TVL', 'veCRV_boost', 'Remarks', 
            'current_vapr_numeric', 'projected_vapr_numeric', 'tvl_numeric', 
            'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_token_price_history_columns(self, df):
        """TokenPriceHistoryデータのカラム順序を整理"""
        if df.empty:
            return df
        
        print(f"🔧 カラム順序整理前: {list(df.columns)}")
        
        # 指定された順序のカラムリスト（TokenPriceHistory用）
        desired_columns = [
            'timezone', 'timestamp', 'token', 'price', 'price_numeric', 
            'pool_count', 'pools', 'factory_ids', 'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        print(f"🔧 カラム順序整理後: {final_columns}")
        
        return df[final_columns]

    def organize_price_history_columns(self, df):
        """PriceHistoryデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト（PriceHistory用）
        desired_columns = [
            'timezone', 'timestamp', 'asset', 'rate', 'price_usd', 
            'price_jpy', 'source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_pool_meta_columns(self, df):
        """PoolMetaデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト（PoolMeta用）
        desired_columns = [
            'timezone', 'timestamp', 'pool_id', 'name', 'symbol', 'tvl', 
            'apr', 'apy', 'fee', 'volume_24h', 'tokens', 'description', 
            'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def organize_vault_meta_columns(self, df):
        """VaultMetaデータのカラム順序を整理"""
        if df.empty:
            return df
        
        # 指定された順序のカラムリスト（VaultMeta用 - vault_idがプライマリキー）
        desired_columns = [
            'timezone', 'timestamp', 'vault_id', 'name', 'symbol', 'tvl', 
            'apr', 'apy', 'fee', 'volume_24h', 'total_supply', 'underlying_asset', 
            'strategy', 'description', 'data_source', 'datetime', 'created_at'
        ]
        
        # 存在するカラムのみを選択
        existing_columns = [col for col in desired_columns if col in df.columns]
        
        # 存在しないカラムを最後に追加
        missing_columns = [col for col in df.columns if col not in desired_columns]
        
        # 最終的なカラム順序
        final_columns = existing_columns + missing_columns
        
        return df[final_columns]

    def export_to_csv(self, days=7):
        """データをCSVファイルにエクスポート（Google Colab自動ダウンロード対応）"""
        print(f"📁 過去{days}日間のデータをCSVエクスポート中...")

        # 各データを取得
        cvx_df = self.get_cvx_data(limit=1000, days=days)
        cvxcrv_df = self.get_cvxcrv_data(limit=1000, days=days)
        pools_df = self.get_pools_data(limit=5000, days=days)
        pool_latest_df = self.get_pool_latest_data(limit=1000)
        price_history_df = self.get_price_history_data(limit=5000, days=days)
        token_price_history_df = self.get_token_price_history_data(limit=5000, days=days)
        pool_meta_df = self.get_pool_meta_data(limit=5000)
        vault_meta_df = self.get_vault_meta_data(limit=5000)

        # CSVファイル保存（Google Colab用）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        downloaded_files = []

        try:
            # Google Colabのfilesモジュールをインポート
            from google.colab import files
            colab_available = True
        except ImportError:
            colab_available = False
            print("⚠️ Google Colab環境ではありません。ファイルはローカルに保存されます。")

        if not cvx_df.empty:
            filename = f'cvx_data_{timestamp}.csv'
            # CVXデータのカラム順序を整理
            cvx_df_organized = self.organize_cvx_columns(cvx_df)
            cvx_df_organized.to_csv(filename, index=False)
            print(f"✅ CVXデータ: {filename} ({len(cvx_df)}件)")
            print(f"📋 CVXカラム順序: {list(cvx_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not cvxcrv_df.empty:
            filename = f'cvxcrv_data_{timestamp}.csv'
            # cvxCRVデータのカラム順序を整理
            cvxcrv_df_organized = self.organize_cvxcrv_columns(cvxcrv_df)
            cvxcrv_df_organized.to_csv(filename, index=False)
            print(f"✅ cvxCRVデータ: {filename} ({len(cvxcrv_df)}件)")
            print(f"📋 cvxCRVカラム順序: {list(cvxcrv_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not pools_df.empty:
            filename = f'pools_data_{timestamp}.csv'
            # プールデータのカラム順序を整理
            pools_df_organized = self.organize_pool_metrics_columns(pools_df)
            pools_df_organized.to_csv(filename, index=False)
            print(f"✅ プールデータ: {filename} ({len(pools_df)}件)")
            print(f"📋 プールデータカラム順序: {list(pools_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not pool_latest_df.empty:
            filename = f'pool_latest_data_{timestamp}.csv'
            # PoolLatestデータのカラム順序を整理
            pool_latest_df_organized = self.organize_pool_latest_columns(pool_latest_df)
            pool_latest_df_organized.to_csv(filename, index=False)
            print(f"✅ PoolLatestデータ: {filename} ({len(pool_latest_df)}件)")
            print(f"📋 PoolLatestカラム順序: {list(pool_latest_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not price_history_df.empty:
            filename = f'price_history_data_{timestamp}.csv'
            # PriceHistoryデータのカラム順序を整理
            price_history_df_organized = self.organize_price_history_columns(price_history_df)
            price_history_df_organized.to_csv(filename, index=False)
            print(f"✅ PriceHistoryデータ: {filename} ({len(price_history_df)}件)")
            print(f"📋 PriceHistoryカラム順序: {list(price_history_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not token_price_history_df.empty:
            filename = f'token_price_history_data_{timestamp}.csv'
            # TokenPriceHistoryデータのカラム順序を整理
            token_price_history_df_organized = self.organize_token_price_history_columns(token_price_history_df)
            token_price_history_df_organized.to_csv(filename, index=False)
            print(f"✅ TokenPriceHistoryデータ: {filename} ({len(token_price_history_df)}件)")
            print(f"📋 TokenPriceHistoryカラム順序: {list(token_price_history_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not pool_meta_df.empty:
            filename = f'pool_meta_data_{timestamp}.csv'
            # PoolMetaデータのカラム順序を整理
            pool_meta_df_organized = self.organize_pool_meta_columns(pool_meta_df)
            pool_meta_df_organized.to_csv(filename, index=False)
            print(f"✅ PoolMetaデータ: {filename} ({len(pool_meta_df)}件)")
            print(f"📋 PoolMetaカラム順序: {list(pool_meta_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not vault_meta_df.empty:
            filename = f'vault_meta_data_{timestamp}.csv'
            # VaultMetaデータのカラム順序を整理
            vault_meta_df_organized = self.organize_vault_meta_columns(vault_meta_df)
            vault_meta_df_organized.to_csv(filename, index=False)
            print(f"✅ VaultMetaデータ: {filename} ({len(vault_meta_df)}件)")
            print(f"📋 VaultMetaカラム順序: {list(vault_meta_df_organized.columns)}")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if downloaded_files:
            if colab_available:
                print("📊 CSVエクスポート完了! 以下のファイルが自動ダウンロードされました:")
            else:
                print("📊 CSVエクスポート完了! 以下のファイルが保存されました:")
            for file in downloaded_files:
                print(f"   📄 {file}")
        else:
            print("❌ エクスポートするデータがありませんでした。")

    def export_single_table(self, table_type, days=7):
        """単一テーブルのデータをエクスポート"""
        print(f"📁 {table_type}データをCSVエクスポート中...")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        try:
            from google.colab import files
            colab_available = True
        except ImportError:
            colab_available = False
            print("⚠️ Google Colab環境ではありません。ファイルはローカルに保存されます。")

        if table_type.lower() == 'cvx':
            df = self.get_cvx_data(limit=1000, days=days)
            filename = f'cvx_data_{timestamp}.csv'
        elif table_type.lower() == 'cvxcrv':
            df = self.get_cvxcrv_data(limit=1000, days=days)
            filename = f'cvxcrv_data_{timestamp}.csv'
        elif table_type.lower() in ['pools', 'pool']:
            df = self.get_pools_data(limit=5000, days=days)
            filename = f'pools_data_{timestamp}.csv'
        elif table_type.lower() in ['poollatest', 'pool_latest']:
            df = self.get_pool_latest_data(limit=1000)
            filename = f'pool_latest_data_{timestamp}.csv'
        elif table_type.lower() in ['pricehistory', 'price_history']:
            df = self.get_price_history_data(limit=5000, days=days)
            filename = f'price_history_data_{timestamp}.csv'
        elif table_type.lower() in ['tokenpricehistory', 'token_price_history']:
            df = self.get_token_price_history_data(limit=5000, days=days)
            filename = f'token_price_history_data_{timestamp}.csv'
        elif table_type.lower() in ['poolmeta', 'pool_meta']:
            df = self.get_pool_meta_data(limit=5000)
            filename = f'pool_meta_data_{timestamp}.csv'
        elif table_type.lower() in ['vaultmeta', 'vault_meta']:
            df = self.get_vault_meta_data(limit=5000)
            filename = f'vault_meta_data_{timestamp}.csv'
        else:
            print(f"❌ 不明なテーブルタイプ: {table_type}")
            return

        if not df.empty:
            # CVXデータの場合はカラム順序を整理
            if table_type.lower() == 'cvx':
                df = self.organize_cvx_columns(df)
                print(f"📋 CVXカラム順序: {list(df.columns)}")
            # cvxCRVデータの場合はカラム順序を整理
            elif table_type.lower() == 'cvxcrv':
                df = self.organize_cvxcrv_columns(df)
                print(f"📋 cvxCRVカラム順序: {list(df.columns)}")
            # プールデータの場合はカラム順序を整理
            elif table_type.lower() in ['pools', 'pool']:
                df = self.organize_pool_metrics_columns(df)
                print(f"📋 プールデータカラム順序: {list(df.columns)}")
            # PoolLatestデータの場合はカラム順序を整理
            elif table_type.lower() in ['poollatest', 'pool_latest']:
                df = self.organize_pool_latest_columns(df)
                print(f"📋 PoolLatestカラム順序: {list(df.columns)}")
            # PriceHistoryデータの場合はカラム順序を整理
            elif table_type.lower() in ['pricehistory', 'price_history']:
                df = self.organize_price_history_columns(df)
                print(f"📋 PriceHistoryカラム順序: {list(df.columns)}")
            # TokenPriceHistoryデータの場合は既にget_token_price_history_data内でカラム順序を整理済み
            elif table_type.lower() in ['tokenpricehistory', 'token_price_history']:
                print(f"📋 TokenPriceHistoryカラム順序: {list(df.columns)}")
            # PoolMetaデータの場合はカラム順序を整理
            elif table_type.lower() in ['poolmeta', 'pool_meta']:
                df = self.organize_pool_meta_columns(df)
                print(f"📋 PoolMetaカラム順序: {list(df.columns)}")
            # VaultMetaデータの場合はカラム順序を整理
            elif table_type.lower() in ['vaultmeta', 'vault_meta']:
                df = self.organize_vault_meta_columns(df)
                print(f"📋 VaultMetaカラム順序: {list(df.columns)}")
            
            df.to_csv(filename, index=False)
            print(f"✅ {table_type}データ: {filename} ({len(df)}件)")

            if colab_available:
                files.download(filename)
                print(f"📊 {table_type}データのダウンロードが完了しました!")
            else:
                print(f"📊 {table_type}データが{filename}に保存されました!")
        else:
            print(f"❌ {table_type}データが見つかりませんでした。")

    def comprehensive_analysis(self):
        """包括的分析を実行"""
        print("🔍 DynamoDB包括的分析を開始します...")
        print("="*60)

        # 1. テーブルサマリー
        self.get_table_summary()

        # 2. データプレビュー
        cvx_df = self.get_cvx_data(limit=5)
        cvxcrv_df = self.get_cvxcrv_data(limit=5)
        pools_df = self.get_pools_data(limit=10)
        pool_latest_df = self.get_pool_latest_data(limit=10)
        price_history_df = self.get_price_history_data(limit=10)
        token_price_history_df = self.get_token_price_history_data(limit=10)
        pool_meta_df = self.get_pool_meta_data(limit=10)
        vault_meta_df = self.get_vault_meta_data(limit=10)

        self.display_data_preview(cvx_df, "CVXデータ")
        self.display_data_preview(cvxcrv_df, "cvxCRVデータ")
        self.display_data_preview(pools_df, "プールデータ")
        self.display_data_preview(pool_latest_df, "PoolLatestデータ")
        self.display_data_preview(price_history_df, "PriceHistoryデータ")
        self.display_data_preview(token_price_history_df, "TokenPriceHistoryデータ")
        self.display_data_preview(pool_meta_df, "PoolMetaデータ")
        self.display_data_preview(vault_meta_df, "VaultMetaデータ")

        # 3. 投資機会分析
        self.find_best_opportunities()

        # 4. トレンドチャート
        self.create_trend_charts()

        print("\n✅ 包括的分析完了!")

# セル3: 実行用関数
def quick_overview():
    """クイック概要表示"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.get_table_summary()

def full_analysis():
    """完全分析実行"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.comprehensive_analysis()

def find_high_apr_pools(min_apr=20):
    """高APRプール検索"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.find_best_opportunities(min_apr=min_apr)

def export_recent_data(days=7):
    """最近のデータをCSVエクスポート（自動ダウンロード）"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_to_csv(days=days)

def export_cvx_data(days=7):
    """CVXデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('cvx', days=days)

def export_cvxcrv_data(days=7):
    """cvxCRVデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('cvxcrv', days=days)

def export_pools_data(days=7):
    """プールデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('pools', days=days)

def export_pool_latest_data():
    """PoolLatestデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('pool_latest')

def export_price_history_data(days=7):
    """PriceHistoryデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('price_history', days=days)

def export_token_price_history_data(days=7):
    """TokenPriceHistoryデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('token_price_history', days=days)

def show_trends():
    """トレンドチャート表示"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.create_trend_charts()

def show_pool_latest_data(limit=20):
    """PoolLatestデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pool_latest_data(limit=limit)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_pool_latest_columns(df)
        print(f"📋 PoolLatestカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "PoolLatestデータ", max_rows=limit)

def show_price_history_data(limit=20, symbol=None):
    """PriceHistoryデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_price_history_data(limit=limit, symbol=symbol)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_price_history_columns(df)
        print(f"📋 PriceHistoryカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "PriceHistoryデータ", max_rows=limit)

def show_token_price_history_data(limit=20, symbol=None):
    """TokenPriceHistoryデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_token_price_history_data(limit=limit, symbol=symbol)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_token_price_history_columns(df)
        print(f"📋 TokenPriceHistoryカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "TokenPriceHistoryデータ", max_rows=limit)

def show_pool_meta_data(limit=100):
    """PoolMetaデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pool_meta_data(limit=limit)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_pool_meta_columns(df)
        print(f"📋 PoolMetaカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "PoolMetaデータ", max_rows=min(limit, 20))

def show_vault_meta_data(limit=20):
    """VaultMetaデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_vault_meta_data(limit=limit)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_vault_meta_columns(df)
        print(f"📋 VaultMetaカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "VaultMetaデータ", max_rows=limit)

def export_pool_meta_data():
    """PoolMetaデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('pool_meta')

def export_vault_meta_data():
    """VaultMetaデータのみをエクスポート"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.export_single_table('vault_meta')

def get_all_pool_meta_data():
    """PoolMetaテーブルの全データを取得（制限なし）"""
    viewer = DynamoDBComprehensiveViewer()
    return viewer.get_pool_meta_data(limit=999999)

def get_all_vault_meta_data():
    """VaultMetaテーブルの全データを取得（制限なし）"""
    viewer = DynamoDBComprehensiveViewer()
    return viewer.get_vault_meta_data(limit=999999)

def export_all_pool_meta_data():
    """PoolMetaテーブルの全データをエクスポート（制限なし）"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pool_meta_data(limit=999999)
    
    if not df.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'pool_meta_all_data_{timestamp}.csv'
        
        # カラム順序を整理
        df = viewer.organize_pool_meta_columns(df)
        df.to_csv(filename, index=False)
        print(f"✅ PoolMeta全データ: {filename} ({len(df)}件)")
        
        try:
            from google.colab import files
            files.download(filename)
            print(f"📊 PoolMeta全データのダウンロードが完了しました!")
        except ImportError:
            print(f"📊 PoolMeta全データが{filename}に保存されました!")
    else:
        print("❌ PoolMetaデータが見つかりませんでした。")

def export_all_vault_meta_data():
    """VaultMetaテーブルの全データをエクスポート（制限なし）"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_vault_meta_data(limit=999999)
    
    if not df.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'vault_meta_all_data_{timestamp}.csv'
        
        # カラム順序を整理
        df = viewer.organize_vault_meta_columns(df)
        df.to_csv(filename, index=False)
        print(f"✅ VaultMeta全データ: {filename} ({len(df)}件)")
        
        try:
            from google.colab import files
            files.download(filename)
            print(f"📊 VaultMeta全データのダウンロードが完了しました!")
        except ImportError:
            print(f"📊 VaultMeta全データが{filename}に保存されました!")
    else:
        print("❌ VaultMetaデータが見つかりませんでした。")

def export_all_convex_pool_metrics_data():
    """ConvexPoolMetricsテーブルの全データをエクスポート（制限なし）"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pools_data(limit=999999)
    
    if not df.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'convex_pool_metrics_all_data_{timestamp}.csv'
        
        # カラム順序を整理
        df = viewer.organize_pool_metrics_columns(df)
        df.to_csv(filename, index=False)
        print(f"✅ ConvexPoolMetrics全データ: {filename} ({len(df)}件)")
        
        try:
            from google.colab import files
            files.download(filename)
            print(f"📊 ConvexPoolMetrics全データのダウンロードが完了しました!")
        except ImportError:
            print(f"📊 ConvexPoolMetrics全データが{filename}に保存されました!")
    else:
        print("❌ ConvexPoolMetricsデータが見つかりませんでした。")

def show_convex_pool_metrics_data(limit=100):
    """ConvexPoolMetricsデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pools_data(limit=limit)
    # カラム順序を整理してから表示
    if not df.empty:
        df = viewer.organize_pool_metrics_columns(df)
        print(f"📋 ConvexPoolMetricsカラム順序: {list(df.columns)}")
    viewer.display_data_preview(df, "ConvexPoolMetricsデータ", max_rows=limit)

def analyze_table_fields():
    """全テーブルのフィールド構造を分析"""
    viewer = DynamoDBComprehensiveViewer()
    
    print("🔍 テーブルフィールド構造分析")
    print("="*60)
    
    # 各テーブルからサンプルデータを取得してフィールドを確認
    tables_to_analyze = [
        ('PoolMeta', viewer.get_pool_meta_data, viewer.organize_pool_meta_columns),
        ('VaultMeta', viewer.get_vault_meta_data, viewer.organize_vault_meta_columns),
        ('PoolLatest', viewer.get_pool_latest_data, viewer.organize_pool_latest_columns),
        ('PriceHistory', lambda limit: viewer.get_price_history_data(limit=limit), viewer.organize_price_history_columns),
        ('ConvexPoolMetrics', lambda limit: viewer.get_pools_data(limit=limit), viewer.organize_pool_metrics_columns),
        ('CvxStakeMetrics', lambda limit: viewer.get_cvx_data(limit=limit), viewer.organize_cvx_columns),
        ('CvxCrvStakeMetrics', lambda limit: viewer.get_cvxcrv_data(limit=limit), viewer.organize_cvxcrv_columns)
    ]
    
    for table_name, get_func, organize_func in tables_to_analyze:
        print(f"\n📊 {table_name}テーブル")
        print("-" * 40)
        
        try:
            # サンプルデータを取得
            df = get_func(limit=5)
            
            if not df.empty:
                # カラム順序を整理
                df_organized = organize_func(df)
                
                print(f"   総フィールド数: {len(df_organized.columns)}")
                print(f"   フィールド一覧:")
                
                for i, col in enumerate(df_organized.columns, 1):
                    # データ型を確認
                    sample_value = df_organized[col].iloc[0] if len(df_organized) > 0 else None
                    data_type = type(sample_value).__name__ if sample_value is not None else 'None'
                    
                    # 非null値の数を確認
                    non_null_count = df_organized[col].notna().sum()
                    total_count = len(df_organized)
                    
                    print(f"     {i:2d}. {col:<25} ({data_type:<10}) 非null: {non_null_count}/{total_count}")
                
                # サンプルデータの最初の行を表示
                if len(df_organized) > 0:
                    print(f"   サンプルデータ（最初の行）:")
                    for col in df_organized.columns[:5]:  # 最初の5フィールドのみ表示
                        value = df_organized[col].iloc[0]
                        if isinstance(value, str) and len(str(value)) > 50:
                            value = str(value)[:47] + "..."
                        print(f"     {col}: {value}")
                    if len(df_organized.columns) > 5:
                        print(f"     ... 他{len(df_organized.columns) - 5}フィールド")
            else:
                print(f"   ❌ データが見つかりません")
                
        except Exception as e:
            print(f"   ❌ エラー: {e}")

def check_pool_meta_fields():
    """PoolMetaテーブルのフィールド詳細確認"""
    viewer = DynamoDBComprehensiveViewer()
    
    print("🔍 PoolMetaテーブル フィールド詳細分析")
    print("="*50)
    
    df = viewer.get_pool_meta_data(limit=10)
    
    if not df.empty:
        print(f"📊 取得データ: {len(df)}件")
        print(f"📋 全フィールド数: {len(df.columns)}")
        print(f"📋 フィールド一覧:")
        
        for i, col in enumerate(df.columns, 1):
            # データ型とサンプル値を確認
            sample_values = df[col].dropna().head(3).tolist()
            data_type = df[col].dtype
            non_null_count = df[col].notna().sum()
            
            print(f"  {i:2d}. {col:<20} | 型: {str(data_type):<15} | 非null: {non_null_count}/{len(df)}")
            
            if sample_values:
                print(f"      サンプル値: {sample_values}")
            else:
                print(f"      サンプル値: [全てnull]")
            print()
        
        # カラム順序整理後の確認
        df_organized = viewer.organize_pool_meta_columns(df)
        print(f"📋 整理後のフィールド順序:")
        for i, col in enumerate(df_organized.columns, 1):
            print(f"  {i:2d}. {col}")
    else:
        print("❌ PoolMetaデータが見つかりません")

def check_vault_meta_fields():
    """VaultMetaテーブルのフィールド詳細確認"""
    viewer = DynamoDBComprehensiveViewer()
    
    print("🔍 VaultMetaテーブル フィールド詳細分析")
    print("="*50)
    
    df = viewer.get_vault_meta_data(limit=10)
    
    if not df.empty:
        print(f"📊 取得データ: {len(df)}件")
        print(f"📋 全フィールド数: {len(df.columns)}")
        print(f"📋 フィールド一覧:")
        
        for i, col in enumerate(df.columns, 1):
            # データ型とサンプル値を確認
            sample_values = df[col].dropna().head(3).tolist()
            data_type = df[col].dtype
            non_null_count = df[col].notna().sum()
            
            print(f"  {i:2d}. {col:<20} | 型: {str(data_type):<15} | 非null: {non_null_count}/{len(df)}")
            
            if sample_values:
                print(f"      サンプル値: {sample_values}")
            else:
                print(f"      サンプル値: [全てnull]")
            print()
        
        # カラム順序整理後の確認
        df_organized = viewer.organize_vault_meta_columns(df)
        print(f"📋 整理後のフィールド順序:")
        for i, col in enumerate(df_organized.columns, 1):
            print(f"  {i:2d}. {col}")
    else:
        print("❌ VaultMetaデータが見つかりません")

def test_pool_id_display():
    """pool_idフィールドの表示テスト（修正確認用）"""
    viewer = DynamoDBComprehensiveViewer()
    
    print("🔍 PoolMetaのpool_idフィールド表示テスト")
    print("="*50)
    
    df = viewer.get_pool_meta_data(limit=20)
    
    if not df.empty:
        print(f"📊 取得データ: {len(df)}件")
        
        # pool_idカラムの確認
        if 'pool_id' in df.columns:
            print(f"✅ pool_idカラムが存在します")
            
            # pool_idの値とデータ型を確認
            pool_ids = df['pool_id'].dropna()
            print(f"📋 pool_idの値（最初の10件）:")
            for i, pool_id in enumerate(pool_ids.head(10), 1):
                data_type = type(pool_id).__name__
                print(f"  {i:2d}. {pool_id} (型: {data_type})")
            
            # 数値と文字列のpool_idを分類
            numeric_ids = []
            string_ids = []
            
            for pool_id in pool_ids:
                try:
                    float(pool_id)
                    numeric_ids.append(pool_id)
                except (ValueError, TypeError):
                    string_ids.append(pool_id)
            
            print(f"\n📊 pool_idの分類:")
            print(f"   数値型のpool_id: {len(numeric_ids)}件")
            print(f"   文字列型のpool_id: {len(string_ids)}件")
            
            if string_ids:
                print(f"   文字列型の例: {string_ids[:5]}")
            if numeric_ids:
                print(f"   数値型の例: {numeric_ids[:5]}")
                
        else:
            print("❌ pool_idカラムが見つかりません")
    else:
        print("❌ PoolMetaデータが見つかりません")

# セル4: 実行コマンド例
print("🚀 DynamoDB包括的ビューアー準備完了!")
print("\n📋 利用可能なコマンド:")
print("   - quick_overview()                    # クイック概要")
print("   - full_analysis()                     # 完全分析（推奨）")
print("   - find_high_apr_pools(25)             # 高APRプール検索")
print("   - show_trends()                       # トレンドチャート")
print("   - export_recent_data(30)              # 全データエクスポート（自動ダウンロード）")
print("   - export_cvx_data(7)                  # CVXデータのみエクスポート")
print("   - export_cvxcrv_data(7)               # cvxCRVデータのみエクスポート")
print("   - export_pools_data(7)                # プールデータのみエクスポート")
print("   - export_pool_latest_data()           # PoolLatestデータのみエクスポート")
print("   - export_price_history_data(7)        # PriceHistoryデータのみエクスポート")
print("   - export_token_price_history_data(7)  # TokenPriceHistoryデータのみエクスポート")
print("   - export_pool_meta_data()             # PoolMetaデータのみエクスポート")
print("   - export_vault_meta_data()            # VaultMetaデータのみエクスポート")
print("   - export_all_pool_meta_data()         # PoolMeta全データエクスポート（制限なし）")
print("   - export_all_vault_meta_data()        # VaultMeta全データエクスポート（制限なし）")
print("   - export_all_convex_pool_metrics_data() # ConvexPoolMetrics全データエクスポート（制限なし）")
print("   - show_pool_latest_data(20)           # PoolLatestデータを表示")
print("   - show_price_history_data(20, 'CVX')  # PriceHistoryデータを表示（シンボル指定可能）")
print("   - show_token_price_history_data(20, 'CVX') # TokenPriceHistoryデータを表示（シンボル指定可能）")
print("   - show_pool_meta_data(100)            # PoolMetaデータを表示")
print("   - show_vault_meta_data(20)            # VaultMetaデータを表示")
print("   - show_convex_pool_metrics_data(100)  # ConvexPoolMetricsデータを表示")
print("   - analyze_table_fields()              # 全テーブルのフィールド構造分析")
print("   - check_pool_meta_fields()            # PoolMetaフィールド詳細確認")
print("   - check_vault_meta_fields()           # VaultMetaフィールド詳細確認")
print("   - test_pool_id_display()              # pool_idフィールド表示テスト（修正確認用）")
print("\n💡 使用例:")
print("   # 基本的な分析")
print("   full_analysis()")
print("\n   # 高APRプール検索")
print("   find_high_apr_pools(20)")
print("\n   # 過去30日の全データを自動ダウンロード")
print("   export_recent_data(30)")
print("\n   # PoolLatestデータを確認")
print("   show_pool_latest_data(50)")
print("\n   # PoolMetaデータを確認（大量データ対応）")
print("   show_pool_meta_data(500)")
print("\n   # ConvexPoolMetricsデータを確認")
print("   show_convex_pool_metrics_data(100)")
print("\n   # CVXの価格履歴を確認")
print("   show_price_history_data(100, 'CVX')")
print("   show_token_price_history_data(100, 'CVX')")
print("\n   # 特定のテーブルデータのみをダウンロード")
print("   export_pool_latest_data()")
print("   export_price_history_data(30)")
print("   export_token_price_history_data(30)")
print("   export_pool_meta_data()")
print("   export_vault_meta_data()")
print("\n   # 全データをエクスポート（制限なし）")
print("   export_all_pool_meta_data()")
print("   export_all_vault_meta_data()")
print("   export_all_convex_pool_metrics_data()")
print("\n   # フィールド構造の確認")
print("   analyze_table_fields()")
print("   check_pool_meta_fields()")
print("   check_vault_meta_fields()")
print("   test_pool_id_display()  # pool_id表示テスト")
print("\n📁 エクスポート機能:")
print("   Google Colabでは自動的にダウンロードが開始されます")
print("   ローカル環境ではファイルが保存されます")
print("\n🆕 新機能:")
print("   - PoolLatestテーブル: 各プールの最新状態データ")
print("   - PriceHistoryテーブル: トークン価格の履歴データ")
print("   - PoolMetaテーブル: プールの詳細メタ情報（全件取得対応）")
print("   - VaultMetaテーブル: ボルトの詳細メタ情報（全件取得対応）")
print("   - 包括的なトレンド分析チャート（6つのサブプロット）")
print("   - 全データエクスポート機能（制限なし）")
print("   - フィールド構造分析機能（全フィールド確認）")
print("   - pool_id/vault_idフィールドの文字列ID対応（修正済み）")
print("   - VaultMetaテーブル再作成対応（vault_idがプライマリキー）")
print("   - ConvexPoolMetrics全データエクスポート機能（制限なし）")
print("   - ConvexPoolMetricsデータ表示機能")
