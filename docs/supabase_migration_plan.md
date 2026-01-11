# Supabase移行計画書

## 📋 概要

このドキュメントは、現在AWS DynamoDBを使用しているCurConTrackerシステムをSupabaseの無料枠内に移行する可能性を評価し、移行計画を提示します。

## 🔍 Supabase無料枠の制限

### 2025年1月時点の制限
- **データベース容量**: 500 MB/プロジェクト
- **ファイルストレージ**: 1 GB/プロジェクト
- **バンド幅（エグレス）**: 5 GB/月/プロジェクト
- **プロジェクト数**: 2プロジェクトまで

## 📊 現在のシステム分析

### DynamoDBテーブル一覧

#### 履歴テーブル（時系列データ）
1. **CvxStakeHistory** - CVXステーキング履歴
   - キー: `token` (HASH), `timestamp` (RANGE)
   - 保存頻度: 60分間隔
   - データ保持: OHLC集約後に削除

2. **CvxCrvStakeHistory** - cvxCRVステーキング履歴
   - キー: `stake` (HASH), `timestamp` (RANGE)
   - 保存頻度: 60分間隔
   - データ保持: OHLC集約後に削除

3. **ConvexPoolHistory** - Convexプール履歴
   - キー: `pool_id` (HASH), `timestamp` (RANGE)
   - 保存頻度: 60分間隔
   - データ保持: OHLC集約後に削除

4. **PriceHistory** - 価格履歴
   - キー: `asset` (HASH), `timestamp` (RANGE)
   - 保存頻度: 15分間隔（推定）

5. **TokenPriceHistory** - トークン価格履歴
   - キー: `symbol` (HASH), `timestamp` (RANGE)

6. **USDJPYHistory** - USD/JPY履歴
   - キー: 未確認（要確認）

#### 最新データテーブル
7. **PoolLatest** - 最新プールデータ
   - キー: `pool_id` (HASH)
   - 更新頻度: 60分間隔
   - データ量: 約64件（プール60件 + ボルト4件）

8. **CvxStakeMetrics** - CVXステーキングメトリクス
9. **CvxCrvStakeMetrics** - cvxCRVステーキングメトリクス
10. **ConvexPoolMetrics** - Convexプールメトリクス

#### OHLC集約テーブル
11. **CvxStakeOHLCDaily** - CVXステーキング日次OHLC
12. **CvxCrvStakeOHLCDaily** - cvxCRVステーキング日次OHLC
13. **ConvexPoolOHLCDaily** - Convexプール日次OHLC
14. **TokenOHLCDaily** - トークン日次OHLC
15. **USDJPYOHLCDaily** - USD/JPY日次OHLC

#### メタデータテーブル
16. **PoolMeta** - プールメタデータ
17. **VaultMeta** - ボルトメタデータ

#### その他
18. **SimulationsHistory** - シミュレーション履歴（TTL: 30日）
19. **DeletionTrackingLogs** - 削除追跡ログ（GSIあり）

### データ量の推定

#### 1日あたりのデータ量
- **履歴データ**: 
  - CvxStakeHistory: 24件/日 × 約500バイト = 12 KB/日
  - CvxCrvStakeHistory: 24件/日 × 約500バイト = 12 KB/日
  - ConvexPoolHistory: 24件/日 × 64プール × 約1 KB = 1.5 MB/日
  - PriceHistory: 96件/日 × 約500バイト = 48 KB/日
  - **合計履歴**: 約1.6 MB/日

- **最新データ**: 
  - PoolLatest: 64件 × 約1 KB = 64 KB（更新のみ）
  - その他メトリクス: 約10 KB
  - **合計最新**: 約74 KB（更新のみ）

- **OHLC集約**: 
  - 日次集約データ: 約100 KB/日

**1日あたり合計**: 約1.7 MB/日

#### 月間データ量
- **新規データ**: 1.7 MB/日 × 30日 = **約51 MB/月**
- **累積データ**: 
  - 履歴データはOHLC集約後に削除されるため、累積は少ない
  - OHLCデータのみが累積: 約3 MB/月
  - **推定累積**: 約50-100 MB（OHLCデータのみ）

### バンド幅の推定
- **書き込み**: 1.7 MB/日 × 30日 = 51 MB/月
- **読み込み**: 
  - 定期実行での読み込み: 約10 MB/月
  - クエリ・分析: 約50-100 MB/月（推定）
- **合計**: 約100-150 MB/月

## ✅ 移行可能性の評価

### データ容量: ⚠️ **注意が必要**
- **現在の推定**: 50-100 MB（OHLCデータのみ）
- **無料枠制限**: 500 MB
- **評価**: 現在のデータ量なら問題なし。ただし、履歴データの保持期間を制限する必要がある

### バンド幅: ✅ **問題なし**
- **現在の推定**: 100-150 MB/月
- **無料枠制限**: 5 GB/月
- **評価**: 十分に余裕がある

### 技術的課題: ⚠️ **中程度の複雑さ**

#### 1. NoSQL → PostgreSQL移行
- DynamoDBはNoSQL、SupabaseはPostgreSQL（リレーショナルDB）
- スキーマ設計の変更が必要
- クエリ方法の変更が必要

#### 2. 主な変更点
- **キー構造**: DynamoDBの複合キー → PostgreSQLの主キー+インデックス
- **クエリ**: DynamoDBの`query()`/`scan()` → SQLクエリ
- **バッチ処理**: DynamoDBの`batch_writer()` → PostgreSQLの`INSERT ... ON CONFLICT`
- **GSI**: DynamoDBのGSI → PostgreSQLのインデックス

## 🎯 移行戦略

### 推奨アプローチ: **段階的移行**

#### Phase 1: スキーマ設計と移行ツール作成
1. PostgreSQLスキーマ設計
2. データ移行スクリプト作成
3. テスト環境での検証

#### Phase 2: 読み取り専用テーブルの移行
1. メタデータテーブル（PoolMeta, VaultMeta）
2. OHLC集約テーブル（読み取りが多い）
3. 最新データテーブル（PoolLatest）

#### Phase 3: 書き込みテーブルの移行
1. 履歴テーブル（CvxStakeHistory等）
2. 価格履歴テーブル
3. シミュレーション履歴

#### Phase 4: 完全移行
1. DynamoDBへの書き込み停止
2. 残存データの移行
3. DynamoDBテーブルの削除

## 📐 PostgreSQLスキーマ設計案

### テーブル設計の基本方針
1. **履歴テーブル**: パーティショニングを使用（日付別）
2. **最新データテーブル**: 単一テーブル、UPSERT使用
3. **インデックス**: 時系列クエリ用に最適化

### 例: CvxStakeHistoryテーブル

```sql
CREATE TABLE cvx_stake_history (
    token VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    vapr VARCHAR(50),
    tvl VARCHAR(50),
    vapr_numeric DECIMAL(20, 8),
    tvl_numeric DECIMAL(20, 8),
    created_at TIMESTAMPTZ NOT NULL,
    data_source VARCHAR(100),
    timezone VARCHAR(10),
    datetime TIMESTAMPTZ,
    PRIMARY KEY (token, timestamp)
);

-- 時系列クエリ用インデックス
CREATE INDEX idx_cvx_stake_history_timestamp ON cvx_stake_history(timestamp DESC);
CREATE INDEX idx_cvx_stake_history_datetime ON cvx_stake_history(datetime DESC);
```

### 例: PoolLatestテーブル

```sql
CREATE TABLE pool_latest (
    pool_id VARCHAR(255) PRIMARY KEY,
    pool_name VARCHAR(255),
    factory_id VARCHAR(100),
    current_vapr VARCHAR(50),
    projected_vapr VARCHAR(50),
    tvl VARCHAR(50),
    vecrv_boost VARCHAR(50),
    remarks TEXT,
    current_vapr_numeric DECIMAL(20, 8),
    projected_vapr_numeric DECIMAL(20, 8),
    tvl_numeric DECIMAL(20, 8),
    vecrv_boost_numeric DECIMAL(20, 8),
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    data_source VARCHAR(100),
    timezone VARCHAR(10),
    datetime TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- factory_id検索用インデックス
CREATE INDEX idx_pool_latest_factory_id ON pool_latest(factory_id);
```

## 🔧 コード変更の必要箇所

### 1. データアクセス層の抽象化
```python
# 現在: boto3直接使用
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('PoolLatest')
table.put_item(Item=item)

# 移行後: 抽象化レイヤー
from database import get_database
db = get_database()  # Supabase or DynamoDB
db.put_item('pool_latest', item)
```

### 2. クエリの変更
```python
# 現在: DynamoDB query
response = table.query(
    KeyConditionExpression=Key('token').eq('CVX')
)

# 移行後: SQLクエリ
response = db.query(
    "SELECT * FROM cvx_stake_history WHERE token = %s",
    ('CVX',)
)
```

### 3. バッチ処理の変更
```python
# 現在: DynamoDB batch_writer
with table.batch_writer() as batch:
    for item in items:
        batch.put_item(Item=item)

# 移行後: PostgreSQL bulk insert
db.bulk_insert('cvx_stake_history', items)
```

## 📝 移行手順（詳細）

### Step 1: Supabaseプロジェクト作成
1. Supabaseアカウント作成
2. 新規プロジェクト作成
3. データベース接続情報の取得

### Step 2: スキーマ作成
1. SQLスキーマファイル作成
2. Supabase SQL Editorで実行
3. インデックス作成

### Step 3: データ移行スクリプト作成
```python
# migrate_dynamodb_to_supabase.py
import boto3
from supabase import create_client

# DynamoDBからデータ取得
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('PoolLatest')
items = table.scan()['Items']

# Supabaseに書き込み
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
for item in items:
    supabase.table('pool_latest').upsert(item).execute()
```

### Step 4: アプリケーションコードの変更
1. データアクセス層の作成
2. 既存コードの段階的置き換え
3. テスト実行

### Step 5: 並行運用期間
1. DynamoDBとSupabaseの両方に書き込み
2. 読み取りはSupabaseから
3. データ整合性の確認

### Step 6: 完全移行
1. DynamoDBへの書き込み停止
2. 残存データの移行
3. DynamoDBテーブル削除

## ⚠️ 注意事項とリスク

### 1. データ容量の監視
- **リスク**: 履歴データが累積すると500MBを超える可能性
- **対策**: 
  - 履歴データの自動削除（OHLC集約後）
  - データ保持期間の制限（例: 90日）
  - 定期的な容量監視

### 2. パフォーマンス
- **リスク**: PostgreSQLはDynamoDBより遅い可能性
- **対策**: 
  - 適切なインデックス設計
  - パーティショニングの活用
  - クエリの最適化

### 3. バンド幅
- **リスク**: 大量のデータ読み込みで制限超過
- **対策**: 
  - クエリ結果のページネーション
  - キャッシュの活用
  - 不要なデータ取得の削減

### 4. ロックイン
- **リスク**: Supabaseに依存
- **対策**: 
  - データアクセス層の抽象化
  - 将来的な移行を考慮した設計

## 💰 コスト比較

### 現在（DynamoDB）
- **無料枠**: 25 GBストレージ、2.5M読み取り/月、2.5M書き込み/月
- **超過時**: 従量課金
- **推定コスト**: 無料枠内（推定）

### Supabase無料枠
- **データベース**: 500 MB
- **バンド幅**: 5 GB/月
- **コスト**: 無料

### 評価
- **現在の使用量**: DynamoDB無料枠内
- **移行メリット**: 
  - 無料枠の制限が明確
  - PostgreSQLの柔軟性
  - SQLクエリの利便性
- **移行デメリット**: 
  - データ容量制限が厳しい（500MB）
  - 移行作業の工数

## 🎯 推奨事項

### 移行を推奨する場合
1. ✅ 現在のデータ量が100MB以下
2. ✅ 履歴データの自動削除が機能している
3. ✅ PostgreSQL/SQLの利点を活用したい
4. ✅ 将来的な拡張性を重視する

### 移行を見送る場合
1. ❌ データ量が既に300MB以上
2. ❌ 履歴データを長期保持する必要がある
3. ❌ 移行作業のリソースがない
4. ❌ DynamoDBのNoSQL特性が必要

## 📚 参考資料

- [Supabase Pricing](https://supabase.com/pricing)
- [Supabase PostgreSQL Documentation](https://supabase.com/docs/guides/database)
- [DynamoDB to PostgreSQL Migration Guide](https://supabase.com/docs/guides/database/migrating-from-dynamodb)

## 🖥️ EC2定期実行部分の移行可能性

### 現在のEC2実行環境

#### 実行内容
- **スクリプト**: `convex_ec2_complete.py`
- **実行間隔**: 60分間隔（毎時30分実行）
- **実行時間**: 約45-50秒
- **実行方式**: systemdサービスとして常時実行

#### 実行処理の詳細
1. **Webスクレイピング** (Selenium + Chrome)
   - Convex Financeサイトからデータ取得
   - Chrome/ChromeDriverを使用
   - ページ読み込み待機（約30秒）

2. **外部API呼び出し**
   - AlphaVantage API（USD/JPY為替レート）
   - CoinGecko API（CRV/CVX価格）
   - Curve API（プールデータ）

3. **データベース操作**
   - DynamoDBへのデータ保存
   - 履歴データと最新データの両方

4. **特別処理**
   - 午前0時30分: OHLC集約処理
   - 排他ロックによる重複実行防止

### Supabase Edge Functionsでの代替可能性

#### ⚠️ **制限事項**

**1. Selenium/ChromeDriverの実行不可**
- Edge Functionsはサーバーレス環境
- Chrome/ChromeDriverのインストール不可
- ヘッドレスブラウザの実行環境なし
- **結論**: Webスクレイピング部分は**移行不可**

**2. 実行時間制限**
- **Wall Clock Duration**: 無料プランで150秒
- **CPU Time**: 2秒/リクエスト
- **現在の実行時間**: 45-50秒
- **評価**: 実行時間は問題なし（ただしSeleniumが使えないため実質不可）

**3. メモリ制限**
- **メモリ**: 256MB
- **Chrome/ChromeDriver**: 通常100MB以上必要
- **評価**: Seleniumが使えないため問題にならない

#### ✅ **代替可能な部分**

**1. API呼び出し部分**
```typescript
// Supabase Edge Functionsで実装可能
const response = await fetch('https://api.alphavantage.co/query?...');
const data = await response.json();
```

**2. データベース操作部分**
```typescript
// Supabaseクライアントで実装可能
const { data, error } = await supabase
  .from('pool_latest')
  .upsert(item);
```

**3. 定期実行スケジューリング**
- Supabase Edge FunctionsはHTTPトリガーのみ
- 外部cronサービスが必要

### 代替実行環境の選択肢

#### Option 1: GitHub Actions（推奨）
**メリット**:
- ✅ 無料（公開リポジトリ）
- ✅ 60分間隔のcron実行可能
- ✅ Selenium実行可能（Ubuntuランナー）
- ✅ ログと実行履歴が確認可能

**デメリット**:
- ❌ 実行時間制限あり（無料プラン: 6時間/月）
- ❌ プライベートリポジトリは有料

**実装例**:
```yaml
# .github/workflows/convex-scraper.yml
name: Convex Scraper
on:
  schedule:
    - cron: '30 * * * *'  # 毎時30分
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install selenium beautifulsoup4 supabase requests
      - name: Run scraper
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python convex_scraper.py
```

#### Option 2: Vercel Cron Jobs
**メリット**:
- ✅ 無料プランあり
- ✅ 簡単な設定
- ✅ Edge Functionsと統合可能

**デメリット**:
- ❌ Selenium実行不可（サーバーレス環境）
- ❌ 実行時間制限（10秒）

**評価**: Webスクレイピングが必要なため**不適切**

#### Option 3: Render Cron Jobs
**メリット**:
- ✅ 無料プランあり
- ✅ Dockerコンテナ実行可能
- ✅ Selenium実行可能

**デメリット**:
- ❌ 無料プランは15分でスリープ
- ❌ 実行時間が不安定

**評価**: 60分間隔実行には**不適切**

#### Option 4: Railway / Fly.io
**メリット**:
- ✅ Dockerコンテナ実行可能
- ✅ Selenium実行可能
- ✅ 常時実行可能

**デメリット**:
- ❌ 無料プランは制限あり
- ❌ コストが発生する可能性

#### Option 5: 既存EC2の継続使用（推奨）
**メリット**:
- ✅ 現在の環境をそのまま使用
- ✅ 追加コストなし（既存のEC2）
- ✅ 安定した実行環境

**デメリット**:
- ❌ EC2のコストが継続（ただしt3.microは無料枠あり）

### 推奨アプローチ: **ハイブリッド構成**

#### 構成案
```
┌─────────────────────────────────────────┐
│  GitHub Actions (定期実行)              │
│  - Seleniumスクレイピング               │
│  - 外部API呼び出し                      │
│  - Supabaseへのデータ保存               │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  Supabase (データベース)                │
│  - PostgreSQLテーブル                    │
│  - データ保存・クエリ                   │
└─────────────────────────────────────────┘
```

#### 移行手順
1. **Phase 1**: DynamoDB → Supabase（データベース移行）
2. **Phase 2**: EC2スクリプト → GitHub Actions（実行環境移行）
3. **Phase 3**: boto3 → Supabaseクライアント（コード変更）

### GitHub Actions移行の詳細計画

#### 必要な変更点

**1. スクリプトの修正**
```python
# 現在: boto3使用
import boto3
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('PoolLatest')
table.put_item(Item=item)

# 移行後: Supabase使用
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase.table('pool_latest').upsert(item).execute()
```

**2. 環境変数の設定**
- GitHub Secretsに以下を設定:
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `ALPHAVANTAGE_API_KEY`
  - `SLACK_WEBHOOK_URL`（オプション）

**3. ログとエラー通知**
- GitHub Actionsのログを使用
- Slack通知は既存のコードをそのまま使用可能

#### 実行時間の見積もり
- **現在**: 45-50秒
- **GitHub Actions**: 同程度（同じ環境）
- **評価**: 問題なし

#### コスト比較

**現在（EC2 t3.micro）**:
- **無料枠**: 750時間/月（1年間）
- **超過時**: 約$0.0104/時間
- **月間コスト**: 無料枠内なら$0

**GitHub Actions**:
- **無料**: 2,000分/月（公開リポジトリ）
- **60分間隔**: 24回/日 × 30日 = 720回/月
- **1回あたり**: 約1分 = 720分/月
- **評価**: 無料枠内

### 結論: EC2定期実行の移行可能性

#### ✅ **移行可能**
- **データベース**: DynamoDB → Supabase
- **実行環境**: EC2 → GitHub Actions
- **コスト**: 両方とも無料枠内

#### ⚠️ **注意事項**
1. **Selenium環境**: GitHub ActionsのUbuntuランナーで実行可能
2. **実行時間**: 現在の45-50秒は問題なし
3. **ログ管理**: GitHub Actionsのログを使用
4. **エラー通知**: 既存のSlack通知を継続使用可能

#### 🎯 **推奨移行計画**
1. **Step 1**: Supabaseデータベース移行（DynamoDB → Supabase）
2. **Step 2**: スクリプト修正（boto3 → Supabaseクライアント）
3. **Step 3**: GitHub Actions設定（.github/workflows/）
4. **Step 4**: テスト実行と検証
5. **Step 5**: 本番移行（EC2停止）

## 💰 AWS常時無料（Always Free）サービスとその他の選択肢

### AWS Always Free Tierの現状（2025年1月）

#### ⚠️ **重要な変更点**

**EC2インスタンス**:
- **旧制度**: 新規アカウントで12ヶ月間、t2.micro/t3.microが750時間/月無料
- **新制度（2025年7月15日以降）**: 
  - 12ヶ月無料枠は廃止
  - 新規アカウントに$100クレジット付与（6ヶ月有効）
  - 追加で$100クレジット獲得可能（EC2やBedrockの利用で）
  - **常時無料枠はなし**

**DynamoDB**:
- ✅ **常時無料枠あり**（永続的）
  - 25 GBストレージ（Standardテーブルクラス）
  - 2.5M読み取り/月（DynamoDB Streams）
  - 1 GB転送/月（初年度は15 GB/月）
- ✅ **無期限で利用可能**

#### AWS Always Free Tierでの運用可能性

**現在のシステム**:
- **EC2 t3.micro**: 常時実行が必要
- **DynamoDB**: 複数テーブル使用

**評価**:
- ✅ **DynamoDB**: 常時無料枠内で運用可能
- ⚠️ **EC2**: 2025年7月15日以降の新規アカウントは常時無料なし
- ⚠️ **既存アカウント**: 12ヶ月無料期間が終了すると課金開始

**結論**: DynamoDBは常時無料枠で運用可能だが、EC2はクレジット制限があるため、長期的にはコストが発生する可能性がある。

### その他の無料/低コスト選択肢

#### 1. GitHub Actions（推奨度: ⭐⭐⭐⭐⭐）

**無料枠**:
- 公開リポジトリ: 2,000分/月無料
- プライベートリポジトリ: 2,000分/月無料（制限あり）

**特徴**:
- ✅ Selenium実行可能（Ubuntuランナー）
- ✅ Cron実行可能（60分間隔）
- ✅ ログと実行履歴が確認可能
- ✅ 無料枠で十分（720分/月使用）

**制限**:
- ❌ 実行時間: 6時間/ジョブ（無料プラン）
- ❌ プライベートリポジトリは有料プラン推奨

**コスト**: **$0/月**（公開リポジトリ）

---

#### 2. Railway（推奨度: ⭐⭐⭐⭐）

**無料枠**:
- 新規ユーザー: $5クレジット
- 500MB RAM
- 共有vCPU

**特徴**:
- ✅ Dockerコンテナ実行可能
- ✅ Selenium実行可能
- ✅ PostgreSQLデータベース利用可能
- ✅ 環境変数管理
- ✅ ログ確認可能

**制限**:
- ⚠️ $5クレジット消費後は従量課金
- ⚠️ 無料プランはスリープする可能性

**コスト**: **$0-5/月**（クレジット消費後は従量課金）

---

#### 3. Fly.io（推奨度: ⭐⭐⭐⭐）

**無料枠**:
- 3つの共有CPU
- 256MB VM
- 3GB永続ストレージ
- 160GB転送/月

**特徴**:
- ✅ Dockerコンテナ実行可能
- ✅ Selenium実行可能
- ✅ グローバルデプロイ
- ✅ PostgreSQL利用可能

**制限**:
- ⚠️ メモリが少ない（256MB）
- ⚠️ 無料プランは制限あり

**コスト**: **$0/月**（無料枠内）

---

#### 4. Render（推奨度: ⭐⭐⭐）

**無料枠**:
- 750時間/月
- 無料PostgreSQL（90日で削除）

**特徴**:
- ✅ Dockerコンテナ実行可能
- ✅ Selenium実行可能
- ✅ PostgreSQL利用可能

**制限**:
- ❌ 15分非アクティブでスリープ
- ❌ 再起動に最大30秒かかる
- ❌ PostgreSQLは90日で削除

**コスト**: **$0/月**（無料枠内）

**評価**: 60分間隔実行には**不適切**（スリープ問題）

---

#### 5. Cyclic（推奨度: ⭐⭐⭐⭐）

**無料枠**:
- 10,000 APIリクエスト/月
- 1GBランタイムメモリ
- 1GBオブジェクトストレージ
- 3つのcronタスク/アプリ
- 7日間ログ保持

**特徴**:
- ✅ スリープなし（無料プランでも）
- ✅ Cron実行可能
- ✅ サーバーレス関数

**制限**:
- ⚠️ Selenium実行は制限あり
- ⚠️ メモリが少ない（1GB）

**コスト**: **$0/月**（無料枠内）

---

#### 6. Deta Space（推奨度: ⭐⭐⭐）

**無料枠**:
- 無制限（現在）

**特徴**:
- ✅ 完全無料
- ✅ Python、Node.js、Go、Rust対応
- ✅ データベース利用可能

**制限**:
- ⚠️ Selenium実行の可否不明
- ⚠️ ベータ版（将来の変更可能性）

**コスト**: **$0/月**

---

#### 7. Google Cloud Run（推奨度: ⭐⭐⭐）

**無料枠**:
- 2百万リクエスト/月
- 360,000 GB秒のメモリ
- 180,000 vCPU秒

**特徴**:
- ✅ サーバーレス
- ✅ Dockerコンテナ実行可能
- ✅ Cloud Schedulerで定期実行可能

**制限**:
- ⚠️ Selenium実行は制限あり（メモリ制限）
- ⚠️ 実行時間制限（60分）

**コスト**: **$0/月**（無料枠内）

---

#### 8. Azure Container Instances（推奨度: ⭐⭐⭐）

**無料枠**:
- 制限あり

**特徴**:
- ✅ Dockerコンテナ実行可能
- ✅ Azure Logic Appsで定期実行可能

**制限**:
- ⚠️ 無料枠は限定的
- ⚠️ 複雑な設定

**コスト**: **$0-5/月**

---

### 選択肢比較表

| サービス | 無料枠 | Selenium | Cron実行 | データベース | スリープ | コスト/月 | 推奨度 |
|---------|--------|----------|----------|-------------|---------|----------|--------|
| **GitHub Actions** | 2,000分 | ✅ | ✅ | ❌ | ❌ | **$0** | ⭐⭐⭐⭐⭐ |
| **Railway** | $5クレジット | ✅ | ✅ | ✅ | ⚠️ | **$0-5** | ⭐⭐⭐⭐ |
| **Fly.io** | 256MB VM | ✅ | ✅ | ✅ | ❌ | **$0** | ⭐⭐⭐⭐ |
| **Render** | 750時間 | ✅ | ✅ | ✅ | ❌ | **$0** | ⭐⭐⭐ |
| **Cyclic** | 10Kリクエスト | ⚠️ | ✅ | ✅ | ❌ | **$0** | ⭐⭐⭐⭐ |
| **Deta Space** | 無制限 | ❓ | ✅ | ✅ | ❌ | **$0** | ⭐⭐⭐ |
| **AWS EC2** | クレジット制 | ✅ | ✅ | ❌ | ❌ | **$0-10** | ⭐⭐⭐ |
| **AWS DynamoDB** | 25GB | N/A | N/A | ✅ | N/A | **$0** | ⭐⭐⭐⭐ |
| **Supabase** | 500MB DB | ❌ | ❌ | ✅ | N/A | **$0** | ⭐⭐⭐⭐ |

### 推奨構成パターン

#### Pattern 1: GitHub Actions + Supabase（最推奨）

```
GitHub Actions (定期実行)
  ↓
Seleniumスクレイピング + API呼び出し
  ↓
Supabase (PostgreSQL)
```

**メリット**:
- ✅ 完全無料
- ✅ Selenium実行可能
- ✅ 安定した実行環境
- ✅ PostgreSQLの柔軟性

**コスト**: **$0/月**

---

#### Pattern 2: Railway + Railway PostgreSQL

```
Railway (定期実行 + PostgreSQL)
  ↓
Seleniumスクレイピング + API呼び出し
  ↓
Railway PostgreSQL
```

**メリット**:
- ✅ シンプルな構成
- ✅ 一元管理
- ✅ Selenium実行可能

**コスト**: **$0-5/月**（クレジット消費後は従量課金）

---

#### Pattern 3: Fly.io + Supabase

```
Fly.io (定期実行)
  ↓
Seleniumスクレイピング + API呼び出し
  ↓
Supabase (PostgreSQL)
```

**メリット**:
- ✅ 完全無料
- ✅ グローバルデプロイ
- ✅ PostgreSQLの柔軟性

**コスト**: **$0/月**

**注意**: メモリ制限（256MB）に注意

---

#### Pattern 4: AWS EC2 + DynamoDB（現状維持）

```
AWS EC2 t3.micro (定期実行)
  ↓
Seleniumスクレイピング + API呼び出し
  ↓
AWS DynamoDB (Always Free)
```

**メリット**:
- ✅ 現在の環境をそのまま使用
- ✅ DynamoDBは常時無料
- ✅ 安定した実行環境

**コスト**: 
- **EC2**: $0/月（12ヶ月無料期間中）→ その後 $7.5-10/月
- **DynamoDB**: $0/月（常時無料枠内）

**評価**: 短期間は問題なし、長期的にはコスト発生

---

### 最終推奨

#### 🥇 **最推奨: GitHub Actions + Supabase**

**理由**:
1. ✅ **完全無料**: 両方とも無料枠内で運用可能
2. ✅ **Selenium実行可能**: UbuntuランナーでChrome/ChromeDriver使用可能
3. ✅ **安定性**: GitHubのインフラで高い可用性
4. ✅ **柔軟性**: PostgreSQLのSQLクエリが使える
5. ✅ **拡張性**: 将来的な機能追加が容易

**コスト**: **$0/月**

#### 🥈 **次点: Railway + Railway PostgreSQL**

**理由**:
1. ✅ **シンプル**: 1つのプラットフォームで完結
2. ✅ **Selenium実行可能**: Dockerコンテナで実行
3. ⚠️ **コスト**: クレジット消費後は従量課金

**コスト**: **$0-5/月**

#### 🥉 **現状維持: AWS EC2 + DynamoDB**

**理由**:
1. ✅ **現状の環境をそのまま使用**
2. ✅ **DynamoDBは常時無料**
3. ⚠️ **EC2**: 12ヶ月無料期間終了後は課金

**コスト**: **$0-10/月**（期間による）

---

### AWS Always Free Tierでの運用可能性まとめ

#### ✅ **可能な部分**
- **DynamoDB**: 常時無料枠（25GB）で運用可能
- **S3**: 5GBストレージ無料
- **Lambda**: 100万リクエスト/月無料

#### ⚠️ **制限がある部分**
- **EC2**: 2025年7月15日以降の新規アカウントは常時無料なし
- **既存アカウント**: 12ヶ月無料期間終了後は課金

#### 💡 **推奨アプローチ**
1. **短期（1年以内）**: AWS EC2 + DynamoDBを継続
2. **長期（1年以上）**: GitHub Actions + Supabaseに移行

---

## 🔄 次のステップ

1. **現状確認**: 実際のデータ量とバンド幅使用量の測定
2. **AWSアカウント確認**: 無料期間の残り期間を確認
3. **プロトタイプ**: GitHub Actions + Supabaseでテスト
4. **評価**: パフォーマンスとコストの評価
5. **決定**: 移行の可否判断

---

**作成日**: 2025-01-XX  
**最終更新**: 2025-01-XX  
**作成者**: CurConTracker Migration Team
