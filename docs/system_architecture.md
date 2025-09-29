# Convex Finance Data Acquisition System - システムアーキテクチャ

## システム概要図

```
┌─────────────────────────────────────────────────────────────────┐
│                    Convex Finance Data Acquisition System       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EC2 Instance  │    │   AWS DynamoDB  │    │  External APIs  │
│  (Ubuntu 22.04) │    │   (ap-northeast-1) │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Python Scraper (convex_ec2_complete.py)     │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Web Scraping  │  │  Price Fetching │  │  Pool Matching  │ │
│  │  (Selenium)     │  │  (Multi APIs)   │  │  (Token-based)  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Manual Mapping  │  │ Failed Pool     │  │  Lock File      │ │
│  │ (JSON Files)    │  │ Tracking        │  │  Management     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## データフロー

```
1. 定期実行開始 (60分間隔)
   ↓
2. 排他ロック取得
   ↓
3. 並列データ取得
   ├── Convex Finance スクレイピング
   ├── 価格データ取得 (CRV, CVX, 為替レート)
   └── Curve API データ取得
   ↓
4. データ処理・正規化
   ↓
5. プールマッチング処理
   ├── 人力対応表チェック (JSON)
   ├── 自動トークンベースマッチング
   └── 失敗プール記録 (JSON)
   ↓
6. DynamoDB保存
   ├── CvxStakeMetrics
   ├── CvxCrvStakeMetrics
   ├── ConvexPoolMetrics
   ├── PoolLatest (factory_id付き)
   └── PriceHistory
   ↓
7. 排他ロック解放
   ↓
8. 次回実行待機 (60分後)
```

## ファイル構成

```
/home/ubuntu/convex-scraper/
├── convex_ec2_complete.py              # メインスクリプト
├── manual_mapping_manager_json.py      # 人力対応表管理ツール
├── manual_pool_mapping.json            # 人力対応表
├── failed_pool_matching.json           # 失敗プール記録
├── .convex_scraper.lock                # 排他ロックファイル
└── logs/
    └── convex_complete.log             # 実行ログ
```

## DynamoDBテーブル構成

### 既存テーブル
- **CvxStakeMetrics**: CVXステーキングメトリクス
- **CvxCrvStakeMetrics**: cvxCRVステーキングメトリクス
- **ConvexPoolMetrics**: Convexプールメトリクス（履歴）
- **PoolLatest**: 最新プールデータ（factory_id付き）
- **PriceHistory**: 価格履歴データ

### JSONファイル（DynamoDB代替）
- **manual_pool_mapping.json**: 人力対応表
- **failed_pool_matching.json**: マッチング失敗プール記録

## マッチングロジック詳細

### 1. 人力対応表チェック
```python
def _check_manual_mapping(pool_name, used_factory_ids):
    # JSONファイル読み込み
    # プール名検索
    # 重複チェック
    # 有効期限チェック
    # ステータスチェック
    return factory_id
```

### 2. 自動トークンベースマッチング
```python
def find_factory_id_for_pool(pool_name, token_symbols, api_data, used_factory_ids):
    # 1. 人力対応表チェック
    # 2. プールデータ検索
    # 3. Vaultデータ検索
    # 4. 失敗時は失敗プール記録
    return factory_id
```

### 3. トークン分割・マッチング
```python
# 検索プール名: "ETH+KP3R" → ["ETH", "KP3R"]
# Convexプール名: "Curve.fi Factory Crypto Pool: KP3R/ETH" → ["KP3R", "ETH"]
# マッチング: 全検索トークンがConvexトークンに含まれているかチェック
```

## 外部API連携

### 価格データ取得
- **CoinGecko**: CRV, CVX価格
- **Alpha Vantage**: USD/JPY為替レート
- **ExchangeRate-API**: バックアップ為替レート
- **Fixer.io**: バックアップ為替レート

### プールデータ取得
- **Curve API (Pools)**: https://curve.convexfinance.com/api/curve/pools
- **Curve API (Vaults)**: https://curve.convexfinance.com/api/curve/lending-vaults

## 運用・監視

### systemdサービス
```bash
# サービス状態確認
sudo systemctl status convex-scraper

# サービス再起動
sudo systemctl restart convex-scraper

# ログ確認
journalctl -u convex-scraper -f
```

### ログ監視
```bash
# リアルタイムログ
tail -f /home/ubuntu/convex-scraper/logs/convex_complete.log

# マッチング成功率確認
grep "PoolLatest更新完了" /home/ubuntu/convex-scraper/logs/convex_complete.log
```

### 排他ロック管理
```bash
# ロックファイル確認
cat /home/ubuntu/convex-scraper/.convex_scraper.lock

# プロセス確認
ps -ef | grep convex
```

## セキュリティ・信頼性

### 排他ロック機構
- **fcntl**によるファイルロック
- 重複実行防止
- 異常終了時の自動ロック解放

### エラーハンドリング
- 各API呼び出しのタイムアウト設定
- 例外処理による継続実行
- 詳細なログ記録

### データ整合性
- 重複factory_id防止
- トランザクション的なデータ保存
- バックアップ・復旧機能

## パフォーマンス

### 現在の実績
- **実行間隔**: 60分
- **実行時間**: 約45-50秒
- **自動マッチング成功率**: 約50%（137/273件）
- **人力対応表**: 任意の数追加可能

### リソース使用量
- **メモリ**: 約400-450MB
- **CPU**: 実行時のみ高負荷
- **ディスク**: ログファイル約1GB/月

## 拡張性

### 水平スケーリング
- 複数EC2インスタンスでの並列実行
- 排他ロックによる重複防止

### 垂直スケーリング
- より高性能なインスタンスタイプへの移行
- メモリ・CPUの増強

### 機能拡張
- 新しいデータソースの追加
- マッチングアルゴリズムの改善
- Webインターフェースの追加

---

**最終更新**: 2025-09-29  
**バージョン**: 1.0  
**作成者**: Convex Finance Data Acquisition System
