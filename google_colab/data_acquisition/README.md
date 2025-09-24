# Google Colab用データ取得システム

このフォルダには、Google Colab環境で使用するデータ取得・スクレイピング関連のファイルが含まれています。

## ファイル構成

### スクレイピング・データ取得
- **`Convex_Production_JST_WithPrices.py`** - 本番用定期実行版（日本時間対応 + 価格取得）
  - 日本時間15分・60分間隔での定期実行
  - 履歴データ + 最新データ + 価格履歴の保存
  - Google Colab環境での実行に対応

- **`convex_scraper_integrated.py`** - 統合スクレイピングコード
  - Google Colab用のスクレイピングコード
  - CVX、cvxCRV、Curveプールの全情報を抽出
  - CSV出力機能付き

## 使用方法

### Google Colabでの実行

#### 1. 環境セットアップ
```python
# Google Colab環境セットアップ（最初に実行）
setup_colab_environment()
```

#### 2. 定期実行（推奨）
```python
# 日本時間15分間隔実行（価格取得機能付き、推奨）
start_jst_production_with_prices_15min()

# 日本時間60分間隔実行（価格取得機能付き）
start_jst_production_with_prices_60min()
```

#### 3. 一度だけテスト実行
```python
# 日本時間一度だけテスト（価格取得機能付き）
test_jst_with_prices_once()

# 価格取得のみテスト
test_prices_only()
```

#### 4. データ確認
```python
# 価格履歴データ確認
check_price_history()
```

### 統合スクレイピングの実行
```python
# 統合スクレイピング実行
exec(open('convex_scraper_integrated.py').read())
```

## 必要な環境変数（Colab Secrets）

Google Colab環境では、左側パネルの🔑アイコンから以下のSecretsを設定してください：

- **AWS_ACCESS_KEY_ID**: AWS認証情報
- **AWS_SECRET_ACCESS_KEY**: AWS認証情報  
- **AWS_DEFAULT_REGION**: AWSリージョン（デフォルト: ap-northeast-1）
- **ALPHAVANTAGE_API_KEY**: USD/JPY為替レート取得用

## データベーステーブル

### 履歴データ
- **ConvexPoolMetrics**: 全プールの履歴データ
- **CvxStakeMetrics**: CVXのvAPRとTVLデータ
- **CvxCrvStakeMetrics**: cvxCRVのMax vAPRとTVLデータ
- **PriceHistory**: CRV/CVX価格とUSD/JPY為替レート

### 最新データ
- **PoolLatest**: 各プールの最新データのみ

## 特徴

### 日本時間対応
- 全データを日本時間（JST）で保存
- タイムスタンプ: 日本時間ISO形式
- 表示: 全て日本時間で表示

### 価格取得機能
- **CRV/CVX価格**: CoinGecko API（無料、APIキー不要）
- **USD/JPY為替**: AlphaVantage API（要APIキー）
- **JPY価格計算**: USD価格 × 為替レート

### 定期実行機能
- 正確な時間間隔での実行（累積誤差なし）
- 重複実行防止機能
- 実行統計の表示

## 注意事項

- Google Colab環境での実行を前提としています
- 長時間実行時はColabのセッション制限に注意してください
- 必要なAPIキーは事前にColab Secretsに設定してください
