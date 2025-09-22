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
        """プールデータを取得"""
        if not self.connection_status:
            return pd.DataFrame()

        try:
            table = self.dynamodb.Table('ConvexPoolMetrics')

            # フィルター条件を構築
            filter_conditions = []

            if min_apr:
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

    def display_data_preview(self, df, title, max_rows=5):
        """データのプレビューを表示"""
        if df.empty:
            print(f"❌ {title}: データがありません")
            return

        print(f"\n📊 {title} (最新{min(max_rows, len(df))}件)")
        print("="*50)

        # 主要列のみ表示
        display_cols = ['timestamp', 'datetime'] if 'datetime' in df.columns else ['timestamp']
        for col in df.columns:
            if col not in display_cols and col not in ['token', 'stake', 'pool_id', 'Pool', 'vapr', 'tvl', 'Current_vAPR', 'TVL', 'symbol', 'price']:
                display_cols.append(col)

        display_cols = [col for col in display_cols if col in df.columns]
        preview_df = df[display_cols].head(max_rows)

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
            subplot_titles=('CVX vAPR トレンド', 'cvxCRV vAPR トレンド', '高APRプール分布', 'TVL分布', 'トークン価格トレンド', '価格分布', 'ドル円レート', 'ドル円レート分布'),
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

        # トークン価格トレンド
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
                # 主要トークンの価格トレンド
                major_tokens = ['CVX', 'CRV', 'USDC', 'ETH', 'BTC', 'WETH']
                colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown']

                for i, token in enumerate(major_tokens):
                    if 'asset' in price_df.columns:
                        token_data = price_df[price_df['asset'] == token].copy()
                    elif 'symbol' in price_df.columns:
                        token_data = price_df[price_df['symbol'] == token].copy()
                    else:
                        # asset/symbolカラムがない場合は、すべてのデータを使用
                        token_data = price_df.copy()

                    if not token_data.empty:
                        # 日時でソート
                        if 'datetime' in token_data.columns:
                            token_data = token_data.sort_values('datetime')
                        elif 'timestamp' in token_data.columns:
                            token_data = token_data.sort_values('timestamp')

                        price_values = pd.to_numeric(token_data[price_column], errors='coerce').fillna(0)
                        price_values = price_values[price_values > 0]  # 正の価格のみ

                        if len(price_values) > 0:
                            x_values = token_data['datetime'] if 'datetime' in token_data.columns else token_data['timestamp']
                            fig.add_trace(
                                go.Scatter(x=x_values, y=price_values,
                                          mode='lines', name=f'{token} Price ({price_column})', line=dict(color=colors[i % len(colors)])),
                                row=3, col=1
                            )
                            print(f"   ✅ {token}: {len(price_values)}件の価格データを追加")
            else:
                print("   ❌ 価格カラムが見つかりません")
        else:
            print("   ❌ PriceHistoryデータが空です")

        # 価格分布（最新データ）
        if not price_df.empty and price_column:
            try:
                # 価格カラムを特定（上記で特定済み）
                if 'asset' in price_df.columns:
                    # assetでグループ化して最新価格を取得
                    latest_prices = price_df.groupby('asset')[price_column].last()
                    latest_prices = pd.to_numeric(latest_prices, errors='coerce').fillna(0)
                    latest_prices = latest_prices[latest_prices > 0]  # 正の価格のみ
                    latest_prices = latest_prices.sort_values(ascending=False).head(10)  # 上位10件
                elif 'symbol' in price_df.columns:
                    # symbolでグループ化して最新価格を取得
                    latest_prices = price_df.groupby('symbol')[price_column].last()
                    latest_prices = pd.to_numeric(latest_prices, errors='coerce').fillna(0)
                    latest_prices = latest_prices[latest_prices > 0]  # 正の価格のみ
                    latest_prices = latest_prices.sort_values(ascending=False).head(10)  # 上位10件
                else:
                    # asset/symbolカラムがない場合は、最新の価格データを直接使用
                    latest_prices = pd.to_numeric(price_df[price_column], errors='coerce').fillna(0)
                    latest_prices = latest_prices[latest_prices > 0]
                    latest_prices = latest_prices.tail(10)  # 最新10件
                    latest_prices.index = [f'Price_{i}' for i in range(len(latest_prices))]

                if len(latest_prices) > 0:
                    fig.add_trace(
                        go.Bar(x=latest_prices.index, y=latest_prices.values,
                               name=f'最新価格 ({price_column})', marker_color='lightblue'),
                        row=3, col=2
                    )
                    print(f"   ✅ 価格分布: {len(latest_prices)}件のデータを表示")
                else:
                    print("   ❌ 表示できる価格データがありません")
            except Exception as e:
                print(f"   ❌ 価格分布作成エラー: {e}")
        else:
            print("   ❌ 価格分布データがありません")

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
                print(f"   📊 PoolLatestデータから価格情報を取得: {len(pool_latest_df)}件")

                # TVLベースの分布を表示
                if 'tvl_numeric' in pool_latest_df.columns:
                    tvl_data = pd.to_numeric(pool_latest_df['tvl_numeric'], errors='coerce').fillna(0)
                    tvl_data = tvl_data[tvl_data > 0].head(10)

                    if len(tvl_data) > 0:
                        pool_names = pool_latest_df['Pool'].head(len(tvl_data)) if 'Pool' in pool_latest_df.columns else [f'Pool_{i}' for i in range(len(tvl_data))]
                        fig.add_trace(
                            go.Bar(x=pool_names, y=tvl_data.values,
                                   name='プールTVL (代替)', marker_color='lightgreen'),
                            row=3, col=2
                        )
                        print(f"   ✅ 代替データ: TVL分布を表示")

                # APRベースの分布を表示
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
        fig.update_xaxes(title_text="トークン", row=3, col=2)
        fig.update_xaxes(title_text="日時", row=4, col=1)
        fig.update_xaxes(title_text="データポイント", row=4, col=2)

        fig.update_yaxes(title_text="vAPR (%)", row=1, col=1)
        fig.update_yaxes(title_text="vAPR (%)", row=1, col=2)
        fig.update_yaxes(title_text="vAPR (%)", row=2, col=1)
        fig.update_yaxes(title_text="TVL (USD)", row=2, col=2)
        fig.update_yaxes(title_text="価格 (USD)", row=3, col=1)
        fig.update_yaxes(title_text="価格 (USD)", row=3, col=2)
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

        # 結果表示
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

    def export_to_csv(self, days=7):
        """データをCSVファイルにエクスポート（Google Colab自動ダウンロード対応）"""
        print(f"📁 過去{days}日間のデータをCSVエクスポート中...")

        # 各データを取得
        cvx_df = self.get_cvx_data(limit=1000, days=days)
        cvxcrv_df = self.get_cvxcrv_data(limit=1000, days=days)
        pools_df = self.get_pools_data(limit=5000, days=days)
        pool_latest_df = self.get_pool_latest_data(limit=1000)
        price_history_df = self.get_price_history_data(limit=5000, days=days)

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
            cvx_df.to_csv(filename, index=False)
            print(f"✅ CVXデータ: {filename} ({len(cvx_df)}件)")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not cvxcrv_df.empty:
            filename = f'cvxcrv_data_{timestamp}.csv'
            cvxcrv_df.to_csv(filename, index=False)
            print(f"✅ cvxCRVデータ: {filename} ({len(cvxcrv_df)}件)")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not pools_df.empty:
            filename = f'pools_data_{timestamp}.csv'
            pools_df.to_csv(filename, index=False)
            print(f"✅ プールデータ: {filename} ({len(pools_df)}件)")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not pool_latest_df.empty:
            filename = f'pool_latest_data_{timestamp}.csv'
            pool_latest_df.to_csv(filename, index=False)
            print(f"✅ PoolLatestデータ: {filename} ({len(pool_latest_df)}件)")
            downloaded_files.append(filename)

            if colab_available:
                files.download(filename)

        if not price_history_df.empty:
            filename = f'price_history_data_{timestamp}.csv'
            price_history_df.to_csv(filename, index=False)
            print(f"✅ PriceHistoryデータ: {filename} ({len(price_history_df)}件)")
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
        else:
            print(f"❌ 不明なテーブルタイプ: {table_type}")
            return

        if not df.empty:
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

        self.display_data_preview(cvx_df, "CVXデータ")
        self.display_data_preview(cvxcrv_df, "cvxCRVデータ")
        self.display_data_preview(pools_df, "プールデータ")
        self.display_data_preview(pool_latest_df, "PoolLatestデータ")
        self.display_data_preview(price_history_df, "PriceHistoryデータ")

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

def show_trends():
    """トレンドチャート表示"""
    viewer = DynamoDBComprehensiveViewer()
    viewer.create_trend_charts()

def show_pool_latest_data(limit=20):
    """PoolLatestデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_pool_latest_data(limit=limit)
    viewer.display_data_preview(df, "PoolLatestデータ", max_rows=limit)

def show_price_history_data(limit=20, symbol=None):
    """PriceHistoryデータを表示"""
    viewer = DynamoDBComprehensiveViewer()
    df = viewer.get_price_history_data(limit=limit, symbol=symbol)
    viewer.display_data_preview(df, "PriceHistoryデータ", max_rows=limit)

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
print("   - show_pool_latest_data(20)           # PoolLatestデータを表示")
print("   - show_price_history_data(20, 'CVX')  # PriceHistoryデータを表示（シンボル指定可能）")
print("\n💡 使用例:")
print("   # 基本的な分析")
print("   full_analysis()")
print("\n   # 高APRプール検索")
print("   find_high_apr_pools(20)")
print("\n   # 過去30日の全データを自動ダウンロード")
print("   export_recent_data(30)")
print("\n   # PoolLatestデータを確認")
print("   show_pool_latest_data(50)")
print("\n   # CVXの価格履歴を確認")
print("   show_price_history_data(100, 'CVX')")
print("\n   # 特定のテーブルデータのみをダウンロード")
print("   export_pool_latest_data()")
print("   export_price_history_data(30)")
print("\n📁 エクスポート機能:")
print("   Google Colabでは自動的にダウンロードが開始されます")
print("   ローカル環境ではファイルが保存されます")
print("\n🆕 新機能:")
print("   - PoolLatestテーブル: 各プールの最新状態データ")
print("   - PriceHistoryテーブル: トークン価格の履歴データ")
print("   - 包括的なトレンド分析チャート（6つのサブプロット）")
