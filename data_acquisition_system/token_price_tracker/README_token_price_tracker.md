# トークン価格追跡システム

ConvexPoolHistoryテーブルからプール構成トークンを抽出し、Curve Finance APIから価格データを取得してTokenPriceHistoryテーブルに保存するシステムです。

## 概要

- **目的**: プールやボルトの詳細表示に必要なトークン価格の推移データを提供
- **実行頻度**: 1時間おき（日本時間の毎時00分）
- **データソース**: Curve Finance API (https://api.curve.finance/api/getPools/all/ethereum)
- **保存先**: TokenPriceHistoryテーブル
- **追跡対象トークン管理**: ファイルA（tracked_tokens.json）に保存

## 処理の流れ

### 初回セットアップ（手動実行）

1. **ConvexPoolOHLCDailyからトークン抽出**
   - ConvexPoolOHLCDailyテーブルから全プールデータを取得
   - プール名からトークンを抽出
   - ファイルA（tracked_tokens.json）に保存

### 定期実行（毎時00分）

1. **ConvexPoolHistoryからトークン抽出**
   - ConvexPoolHistoryテーブルから全プールデータを取得
   - プール名からトークンを抽出
   - **ConvexPoolHistoryが空の場合**（例: Convex Scraper未実行）: ファイルAが存在しなければ、pool_latest → manual_pool_mapping.json → ConvexPoolOHLCDaily の順でフォールバックしてトークン抽出

2. **ファイルAの更新**
   - ファイルAから既存のトークンを読み込み
   - 新規トークンがあればファイルAに追加保存

3. **価格取得・保存**
   - ファイルAに含まれる全トークンについて、Curve Finance APIから価格を取得
   - TokenPriceHistoryテーブルに保存
   - 価格取得に失敗したトークンをJSONファイルに保存

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

### ConvexPoolOHLCDaily
- **用途**: 初回セットアップ時にトークンを抽出
- **パーティションキー**: pool_id_type (String)
- **ソートキー**: timestamp (String)
- **主要属性**: Pool, pool_id, factory_id, type

### ConvexPoolHistory
- **用途**: 定期実行時にトークンを抽出
- **パーティションキー**: pool_id (String)
- **ソートキー**: timestamp (String)
- **主要属性**: Pool, pool_id, factory_id

### TokenPriceHistory
- **パーティションキー**: token (String)
- **ソートキー**: timestamp (String) - 日本時間
- **その他の属性**:
  - timezone: JST
  - created_at: 日本時間
  - data_source: curve_finance_api
  - price: $0.335340（$マーク付き）
  - price_numeric: 0.335340（数値のみ）
  - pool_count: 使用プール数（オプション）
  - pools: 使用プール（カンマ区切り、オプション）
  - factory_ids: 使用factory_id（カンマ区切り、オプション）

## ファイルA（tracked_tokens.json）

追跡対象トークンのリストを保存するファイルです。

### 用途

- **定期実行時**: ConvexPoolHistoryから抽出したトークンとマージし、新規トークンを追加
- **フォールバック時**: ConvexPoolHistoryが空の場合、pool_latest または ConvexPoolOHLCDaily からトークンを抽出して新規作成

### 使い方

| 実行環境 | ファイルの有無 | 動作 |
|----------|----------------|------|
| **EC2/ローカル** | 存在する | 既存トークンとConvexPoolHistoryの新規トークンをマージして更新 |
| **EC2/ローカル** | 存在しない | ConvexPoolHistoryから抽出して新規作成 |
| **GitHub Actions** | 毎回存在しない | ConvexPoolHistoryから抽出して新規作成。Historyが空の場合は pool_latest → manual_pool_mapping.json → ConvexPoolOHLCDaily の順でフォールバック |

### ファイル形式

- **パス**: `/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/tracked_tokens.json`（EC2）  
  または `data_acquisition_system/token_price_tracker/tracked_tokens.json`（GitHub Actions / ローカル）
- **形式**: JSON
- **内容（新形式）**:
  ```json
  {
    "generated_at": "2025-01-20T10:00:00+09:00",
    "total_tokens": 106,
    "tokens": {
      "CRV": { "symbol": "CRV", "pool_count": 5, "pools": ["pool1", "pool2"], "factory_ids": ["123"], "price": 0.33 },
      "CVX": { "symbol": "CVX", "pool_count": 3, "pools": ["pool1"], "factory_ids": ["123"], "price": 2.5 }
    }
  }
  ```
- **内容（旧形式・互換）**:
  ```json
  {
    "generated_at": "2025-01-20T10:00:00+09:00",
    "tokens": ["CRV", "CVX", "ETH", ...],
    "count": 106
  }
  ```

### 初回セットアップ（手動）

```bash
# ConvexPoolOHLCDailyからトークンを抽出してファイルAを初期化
python3 token_price_tracker.py --init
```

このコマンドは初回のみ実行します。生成された `tracked_tokens.json` をリポジトリにコミットしておくと、GitHub Actions 実行時に ConvexPoolHistory が空でも追跡を継続できます（任意）。

### tracked_tokens.json の定期更新タイミング

| タイミング | 推奨度 | 理由 |
|------------|--------|------|
| **Convex Scraper 実行後** | ◎ | 新規プールが ConvexPoolHistory に追加された直後。Token Price Tracker の定期実行（毎時00分）で自動マージされるため、通常は不要 |
| **manual_pool_mapping.json 更新後** | ◎ | 人力対応表に新規プールを追加した場合、次回の Token Price Tracker 実行で ConvexPoolHistory から検出されマージされる。History が空の場合は manual_pool_mapping からフォールバックされる |
| **月1回の手動 `--init`** | △ | 運用安定後は不要。ConvexPoolOHLCDaily の構成が大きく変わった場合のみ検討 |
| **リポジトリにコミット** | ◎ | 初回セットアップ後、`tracked_tokens.json` をコミットしておくと、GitHub Actions の fresh 環境でもフォールバック時に確実にトークン一覧を利用できる |

**結論**: 通常は **Token Price Tracker の定期実行に任せる** で十分。ConvexPoolHistory から新規トークンが自動検出・マージされる。手動更新は、初回セットアップ時や `tracked_tokens.json` をリポジトリに含めたい場合のみ。

## 使用方法

### 1. 初回セットアップ（ファイルAの初期化）

上記「初回セットアップ（手動）」を参照。

### 2. テスト実行
```bash
# ローカル環境でテスト
python3 test_token_price_tracker.py

# 本番スクリプトのテスト実行（定期実行と同じ処理）
python3 token_price_tracker.py
```

### 3. EC2環境でのデプロイ
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

### 4. 監視・管理
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

### 5. systemdサービス管理
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

### ファイルA（追跡対象トークン）
- **ファイル**: `/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/tracked_tokens.json`
- **内容**: 追跡対象トークンの一覧

### 失敗トークン記録
- **ファイル**: `/home/ubuntu/curcon-tracker/data_acquisition_system/token_price_tracker/failed_tokens_YYYYMMDD_HHMMSS.json`
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
`extract_tokens_from_pool_name`メソッドに特殊ケースを追加してください。新しいプールがConvexPoolHistoryに追加されると、自動的にファイルAに追加されます。

### 価格データソース追加
`fetch_curve_prices`メソッドを拡張して、他のAPIからも価格データを取得できます。

### 実行頻度変更
`token_price_tracker.timer`ファイルの`OnCalendar`設定を変更してください。

### ファイルAの手動更新
ファイルAを手動で編集することも可能です。JSON形式で保存されているため、直接編集してトークンを追加・削除できます。
