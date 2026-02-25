# 🚀 CurConTracker Backend

CurConTrackerのバックエンドサービス群。**GitHub Actions + Supabase** を中心に、Convex/Curveデータのスクレイピング、集約、監視通知を行います。

## 📋 目次
- [概要](#概要)
- [現行アーキテクチャ](#現行アーキテクチャ)
- [実行スケジュール](#実行スケジュール)
- [主要スクリプト](#主要スクリプト)
- [セットアップ（ローカル実行）](#セットアップローカル実行)
- [環境変数](#環境変数)
- [データ格納（Supabase）](#データ格納supabase)
- [運用上の注意](#運用上の注意)
- [ドキュメント](#ドキュメント)
- [旧構成（EC2/DynamoDB）](#旧構成ec2dynamodb)

## 🎯 概要
Convex/Curveのデータを定期取得し、Supabaseに保存・日次集約します。  
定期実行は GitHub Actions（`workflow_dispatch`）を使用し、EventBridge + Lambda でJST時間に合わせてトリガーします。

## 🧭 現行アーキテクチャ
- **実行基盤**: GitHub Actions（`workflow_dispatch`）
- **DB**: Supabase（PostgreSQL）
- **時間精度**: EventBridge Scheduler + Lambda で正確なJST起動
- **通知**: Slack Webhook（任意）

## ⏰ 実行スケジュール
※ EventBridge から `workflow_dispatch` を実行（JST基準）
- **毎時 :30**: Convex Scraper  
- **毎時 :00**: Token Price Tracker  
- **毎日 00:00**: Token OHLC Aggregator  
- **毎日 00:30**: Convex Daily Aggregation

## 🧩 主要スクリプト
- `data_acquisition_system/convex_ec2_complete.py`  
  Convex/Curveのスクレイピング、PoolLatest/History保存、日次集約対応
- `data_acquisition_system/token_price_tracker/token_price_tracker.py`  
  ConvexPoolHistoryからトークン抽出、TokenPriceHistory保存
- `data_acquisition_system/token_price_tracker/token_ohlc_aggregator.py`  
  TokenPriceHistoryから日次OHLC集約、TokenOHLCDaily保存
- `data_acquisition_system/manual_pool_mapping.json`  
  factory_id補完用の人力対応表

## 🛠️ セットアップ（ローカル実行）
```bash
git clone https://github.com/YosukeMiyata/curcon-tracker-backend.git
cd curcon-tracker-backend
pip install -r requirements.txt
```

**ローカル実行時の環境変数**: `.env.local` が存在する場合、`.env` より優先して読み込まれます（Supabase 等のローカル用設定に便利）。

**ModuleNotFoundError が出る場合**: `python` と `pip` で異なる Python が使われている可能性があります。`pip install -r requirements.txt` でインストールした Python で実行するか、`./scripts/run_with_deps.sh python <スクリプト>` を試してください。

## 🔐 環境変数
```bash
# Supabase
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# 外部API
ALPHAVANTAGE_API_KEY=your-api-key
COINGECKO_API_KEY=your-api-key

# 通知（任意）
SLACK_WEBHOOK_URL=your-webhook-url
```

## 🗃️ データ格納（Supabase）
主要テーブル（抜粋）
- `convex_pool_history` / `convex_pool_ohlc_daily`
- `convex_pool_remarks_history`
- `pool_latest`
- `token_price_history` / `token_ohlc_daily`
- `usdjpy_history` / `usdjpy_ohlc_daily`

スキーマは `docs/supabase_schema.sql` に記載。

## ✅ 運用上の注意
- **Convex Daily Aggregation** は前日分の集約後、`convex_pool_history` の対象分のみ削除します。
- **Token OHLC Aggregator** は **昨日分のみ削除**し、今日のデータは保持します。
- スクレイパー実行中は `manual_pool_mapping.json` を参照して `factory_id` を補完します。

## 📚 ドキュメント
- **[Supabase移行プラン](docs/supabase_migration_plan.md)**
- **[Supabaseスキーマ](docs/supabase_schema.sql)**
- **[DynamoDB→Supabase移行スクリプト](docs/migrate_dynamodb_to_supabase.py)**
- **[Lambdaでworkflow_dispatch](docs/lambda_github_dispatch.md)**
- **[人力対応表システム詳細](docs/manual_pool_mapping_system.md)**
- **[クイックリファレンス](docs/manual_mapping_quick_reference.md)**

## 🏚️ 旧構成（EC2/DynamoDB）
EC2/DynamoDB運用時のドキュメントは以下に残しています（現行運用では利用しません）。
- `ec2_deployment/`
- `check_duplicate/`
- `deletion_tracking_system/`

---
**CurConTracker Backend** - Convex/Curveデータの定期取得・集約基盤
