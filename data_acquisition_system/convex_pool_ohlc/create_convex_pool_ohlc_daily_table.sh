#!/bin/bash
# =====================================
# ConvexPoolOHLCDailyテーブル作成スクリプト
# パーティションキー: pool_id_type (pool_id#type形式)
# ソートキー: timestamp (日付形式 YYYY-MM-DD)
# =====================================

aws dynamodb create-table \
    --table-name ConvexPoolOHLCDaily \
    --attribute-definitions \
        AttributeName=pool_id_type,AttributeType=S \
        AttributeName=timestamp,AttributeType=S \
    --key-schema \
        AttributeName=pool_id_type,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --tags \
        Key=Project,Value=ConvexTracker \
        Key=Environment,Value=Production

echo "✅ ConvexPoolOHLCDailyテーブルの作成を開始しました"
echo "📊 テーブルの作成完了を待っています..."

aws dynamodb wait table-exists \
    --table-name ConvexPoolOHLCDaily

echo "✅ ConvexPoolOHLCDailyテーブルの作成が完了しました"
echo ""
echo "📋 テーブル設計:"
echo "   - パーティションキー: pool_id_type (例: 'usdfi+usdaf+ebusd+bold#current_vapr')"
echo "   - ソートキー: timestamp (例: '2025-11-01')"
echo "   - 属性: pool_id, type, Pool, factory_id, open, high, low, close, sample_count, data_source, datetime, created_at, timezone"

