# トークン価格追跡システム

ConvexPoolMetricsテーブルからプール構成トークンを抽出し、Curve Finance APIから価格データを取得してTokenPriceHistoryテーブルに保存するシステムです。

## 概要

- **目的**: プールやボルトの詳細表示に必要なトークン価格の推移データを提供
- **実行頻度**: 1時間おき（日本時間17時から開始）
- **データソース**: Curve Finance API (https://api.curve.finance/api/getPools/all/ethereum)
- **保存先**: TokenPriceHistoryテーブル

## ファイル構成

### メインスクリプト
- **`token_price_tracker.py`** - メインの価格追跡スクリプト
- **`token_price_scheduler.py`** - スケジューラー（systemd用）
- **`test_token_price_tracker.py`** - テストスクリプト

### システム設定
- **`token_price_tracker.service`** - systemdサービス定義
- **`token_price_tracker.timer`** - systemdタイマー定義

### デプロイ・監視
- **`deploy_token_price_tracker.sh`** - デプロイスクリプト
- **`monitor_token_price_tracker.sh`** - 監視スクリプト

## データベーステーブル

### TokenPriceHistory
- **パーティションキー**: token (String)
- **ソートキー**: timestamp (String) - 日本時間
- **その他の属性**:
  - timezone: JST
  - created_at: 日本時間
  - data_source: curve_finance_api
  - pool_count: 使用プール数
  - pools: 使用プール（カンマ区切り）
  - factory_ids: 使用factory_id（カンマ区切り）
  - price: $0.335340（$マーク付き）
  - price_numeric: 0.335340（数値のみ）

## 使用方法

### 1. テスト実行
```bash
# ローカル環境でテスト
python3 test_token_price_tracker.py

# 本番スクリプトのテスト実行
python3 token_price_tracker.py
```

### 2. EC2環境でのデプロイ
```bash
# デプロイスクリプトのヘルプ表示
./deploy_token_price_tracker.sh --help

# テスト実行
./deploy_token_price_tracker.sh --test

# サービス開始
./deploy_token_price_tracker.sh --start

# サービス更新・再起動
./deploy_token_price_tracker.sh --update
```

### 3. 監視・管理
```bash
# 監視スクリプトのヘルプ表示
./monitor_token_price_tracker.sh

# サービス状態表示
./monitor_token_price_tracker.sh status

# ログ表示
./monitor_token_price_tracker.sh logs

# 統計情報表示
./monitor_token_price_tracker.sh stats

# ヘルスチェック
./monitor_token_price_tracker.sh health

# リアルタイムログ表示
./monitor_token_price_tracker.sh logs -f
```

### 4. systemdサービス管理
```bash
# サービス状態確認
sudo systemctl status token_price_tracker.timer
sudo systemctl status token_price_tracker.service

# 手動実行
sudo systemctl start token_price_tracker.service

# タイマー制御
sudo systemctl start token_price_tracker.timer
sudo systemctl stop token_price_tracker.timer
sudo systemctl restart token_price_tracker.timer

# ログ表示
sudo journalctl -u token_price_tracker.service -f
```

## 設定

### 実行スケジュール
- **開始時間**: 日本時間17時（UTC 8時）
- **実行間隔**: 1時間おき
- **設定ファイル**: `token_price_tracker.timer`

### ログ設定
- **ログファイル**: `/var/log/token_price_tracker.log`
- **systemdログ**: `journalctl -u token_price_tracker.service`

### 失敗トークン記録
- **ファイル**: `/var/log/failed_tokens_YYYYMMDD_HHMMSS.json`
- **内容**: 価格取得に失敗したトークンの一覧

## 対応トークン

現在、以下の106個のトークンに対応しています：

3Crv, ALCX, ASF, BADGER, BOBO, BOLD, BobrCRV, CJPY, CLEV, COIL, CRV, CTR, CVX, CVX1, DBR, DOLA, DYDX, ETH, ETH+, EURA, EURS, EURT, FRAX, FRAXBP, FXN, FXS, GEAR, GHO, GRAI, INV, IQ, KP3R, LDO, MIM, OETH, PAL, PAXG, PYUSD, RLUSD, ROME, RSUP, RZR, SDT, T, USD3, USDC, USDFI, USDN, USDT, USDaf, USDe, USDf, USR, VSP, VUSD, WACME, WBTC, WETH, XAUt, YFI, afCVX, alUSD, cbBTC, clevCVX, crvUSD, cvgCVX, cvgSDT, cvxCRV, cvxFXN, cvxFXS, deUSD, dgnETH, eUSD, ebUSD, frxETH, frxUSD, fxSAVE, fxUSD, jUSD, msETH, msUSD, pufETH, reUSD, rgUSD, rswETH, sDOLA, sUSD, sUSDS, sUSDe, scrvUSD, sdCRV, sdeUSD, sfrxUSD, sreUSD, stETH, tBTC, tacETH, tacUSD, uniBTC, uniETH, weETH, wstETH, wstUSR, xETH, yCRV, ynETHx

## 注意事項

1. **価格取得失敗**: sreUSDなど、Curve Finance APIに価格データが含まれていないトークンは保存されません
2. **重複実行防止**: 同じタイムスタンプでの重複保存は避けてください
3. **API制限**: Curve Finance APIの制限に注意してください
4. **ログ管理**: ログファイルのサイズが大きくなりすぎないよう定期的にローテーションしてください

## トラブルシューティング

### よくある問題

1. **サービスが開始しない**
   ```bash
   # ログを確認
   sudo journalctl -u token_price_tracker.service -n 50
   
   # 手動実行でエラー確認
   python3 token_price_tracker.py
   ```

2. **価格データが取得できない**
   ```bash
   # Curve Finance APIの接続確認
   curl "https://api.curve.finance/api/getPools/all/ethereum"
   ```

3. **データベース接続エラー**
   ```bash
   # AWS認証情報確認
   aws sts get-caller-identity
   
   # テーブル存在確認
   aws dynamodb describe-table --table-name TokenPriceHistory
   ```

## 開発・カスタマイズ

### 新しいトークン対応
`extract_tokens_from_pool_name`メソッドに特殊ケースを追加してください。

### 価格データソース追加
`fetch_curve_prices`メソッドを拡張して、他のAPIからも価格データを取得できます。

### 実行頻度変更
`token_price_tracker.timer`ファイルの`OnCalendar`設定を変更してください。
