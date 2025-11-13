# USD/JPY Price Tracker

USD/JPY為替レートの履歴データとOHLC日次データを管理するシステムです。

## ファイル構成

- `usdjpy_ohlc_aggregator.py` - USDJPYHistoryテーブルからOHLCデータを集約し、USDJPYOHLCDailyテーブルに保存
- `usdjpy_ohlc_aggregator.service` - systemdサービスファイル
- `usdjpy_ohlc_aggregator.timer` - systemdタイマー（毎日0:30 JST実行）
- `migrate_pricehistory_to_usdjpyhistory.py` - PriceHistoryテーブルからUSDJPYHistoryテーブルへの移行スクリプト
- `import_alphavantage_usdjpy.py` - Alpha Vantageから取得したJSONデータをUSDJPYOHLCDailyテーブルにインポート
- `deploy_usdjpy_system.sh` - USD/JPY関連システムのデプロイスクリプト

## テーブル構成

### USDJPYHistoryテーブル
- **パーティションキー**: asset (String) - "USDJPY"
- **ソートキー**: timestamp (String) - ISO形式のタイムスタンプ
- **属性**: timezone (JST), timestamp, asset (USDJPY), rate, source, datetime, created_at

### USDJPYOHLCDailyテーブル
- **パーティションキー**: asset (String) - "USDJPY"
- **ソートキー**: timestamp (String) - 日付形式（例: "2025-11-01"）
- **属性**: timezone (JST), timestamp, asset (USDJPY), open, high, low, close, sample_count, data_source, datetime, created_at

## 動作フロー

### 毎時30分（JST）
- `convex_ec2_complete.py`がUSD/JPY為替レートを取得し、USDJPYHistoryテーブルに保存

### 毎日0:30（JST）
1. `usdjpy_ohlc_aggregator.py`が実行される
2. 前日のUSDJPYHistoryデータからOHLC（始値、高値、安値、終値）を集約
3. USDJPYOHLCDailyテーブルに保存
4. USDJPYHistoryテーブルを全件クリア
5. `convex_ec2_complete.py`の`run_complete_job()`を呼び出し、今日の最初のUSD/JPYレートをUSDJPYHistoryテーブルに保存

## 使用方法

### 移行スクリプトの実行
```bash
python3 migrate_pricehistory_to_usdjpyhistory.py 2025-11-13
```

### systemdサービスの管理
```bash
# タイマーの状態確認
sudo systemctl status usdjpy_ohlc_aggregator.timer

# タイマーの有効化
sudo systemctl enable usdjpy_ohlc_aggregator.timer

# タイマーの開始
sudo systemctl start usdjpy_ohlc_aggregator.timer

# 手動実行（テスト用）
sudo systemctl start usdjpy_ohlc_aggregator.service
```

## ログファイル

- `/home/ubuntu/curcon-tracker/data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.log`

