# データ取得・DB書き込みシステム

このフォルダには、スクレイピングやAPIでデータを取得してDBに書き込むシステムのファイル群が含まれています。

## ファイル構成

### メインスクレイパー
- **`convex_ec2_complete.py`** - EC2完全版スクレイパー
  - Webスクレイピング + 価格取得 + 全テーブル対応
  - 重複実行防止機能付き
  - 正確な60分間隔実行
  - DynamoDB保存（履歴 + 最新データ + 価格履歴）

### フロントエンド・表示関連
- **`pool_latest_frontend_strategy.py`** - フロントエンド表示戦略
  - PoolLatestデータのフロントエンド表示
  - アクティブ・非アクティブプールの適切な表示
  - APIレスポンス生成機能

## 機能概要

### データ取得機能
- **Webスクレイピング**: Convex Financeサイトからデータを取得
- **API価格取得**: CoinGecko APIからCRV/CVX価格を取得
- **為替レート取得**: AlphaVantage APIからUSD/JPY為替レートを取得

### データベース保存機能
- **履歴データ**: ConvexPoolMetricsテーブルに全履歴を保存
- **最新データ**: PoolLatestテーブルに最新データのみ保存
- **価格履歴**: PriceHistoryテーブルに価格データを保存

### 実行環境
- **EC2環境**: `convex_ec2_complete.py` - 本番環境用

## 使用方法

### EC2環境での実行
```bash
python convex_ec2_complete.py
```


### フロントエンド表示
```python
strategy = PoolLatestFrontendStrategy()
pools = strategy.get_pools_for_frontend()
```

## 必要な環境変数

- `AWS_ACCESS_KEY_ID`: AWS認証情報
- `AWS_SECRET_ACCESS_KEY`: AWS認証情報
- `AWS_DEFAULT_REGION`: AWSリージョン（デフォルト: ap-northeast-1）
- `ALPHAVANTAGE_API_KEY`: USD/JPY為替レート取得用
- `COINGECKO_API_KEY`: CoinGecko APIキー（オプション）

## データベーステーブル

### ConvexPoolMetrics（履歴データ）
- パーティションキー: pool_id
- ソートキー: timestamp
- 全プールの履歴データを保存

### PoolLatest（最新データ）
- パーティションキー: pool_id
- 各プールの最新データのみ保存

### PriceHistory（価格履歴）
- パーティションキー: asset
- ソートキー: timestamp
- CRV/CVX価格とUSD/JPY為替レートを保存

### CvxStakeMetrics（CVXデータ）
- パーティションキー: token
- ソートキー: timestamp
- CVXのvAPRとTVLデータを保存

### CvxCrvStakeMetrics（cvxCRVデータ）
- パーティションキー: stake
- ソートキー: timestamp
- cvxCRVのMax vAPRとTVLデータを保存
