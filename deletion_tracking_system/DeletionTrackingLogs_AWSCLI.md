# DeletionTrackingLogs テーブル作成手順

## AWS CLI でのテーブル作成

### 1. 基本テーブル作成

```bash
aws dynamodb create-table \
    --table-name DeletionTrackingLogs \
    --attribute-definitions \
        AttributeName=log_id,AttributeType=S \
        AttributeName=timestamp,AttributeType=S \
        AttributeName=table_name,AttributeType=S \
        AttributeName=operation_type,AttributeType=S \
        AttributeName=date,AttributeType=S \
    --key-schema \
        AttributeName=log_id,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --billing-mode PROVISIONED \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
```

### 2. グローバルセカンダリインデックス作成

#### GSI 1: テーブル別検索
```bash
aws dynamodb update-table \
    --table-name DeletionTrackingLogs \
    --global-secondary-index-updates \
        '[{
            "Create": {
                "IndexName": "table-timestamp-index",
                "KeySchema": [
                    {"AttributeName": "table_name", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            }
        }]'
```

#### GSI 2: 操作タイプ別検索
```bash
aws dynamodb update-table \
    --table-name DeletionTrackingLogs \
    --global-secondary-index-updates \
        '[{
            "Create": {
                "IndexName": "operation-timestamp-index",
                "KeySchema": [
                    {"AttributeName": "operation_type", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            }
        }]'
```

#### GSI 3: 日付範囲検索
```bash
aws dynamodb update-table \
    --table-name DeletionTrackingLogs \
    --global-secondary-index-updates \
        '[{
            "Create": {
                "IndexName": "date-range-index",
                "KeySchema": [
                    {"AttributeName": "date", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            }
        }]'
```

### 3. テーブルステータス確認

```bash
aws dynamodb describe-table --table-name DeletionTrackingLogs
```

### 4. テストデータ挿入

```bash
aws dynamodb put-item \
    --table-name DeletionTrackingLogs \
    --item '{
        "log_id": {"S": "550e8400-e29b-41d4-a716-446655440000"},
        "timestamp": {"S": "2025-09-24T13:50:22.325000+00:00"},
        "table_name": {"S": "CvxStakeMetrics"},
        "operation_type": {"S": "cleanup"},
        "function_name": {"S": "clean_cvx_stake_metrics"},
        "caller_info": {"S": "{\"filename\": \"cleanup_tool.py\", \"line_number\": 42}"},
        "created_at": {"S": "2025-09-24T13:50:22.325000+00:00"},
        "date": {"S": "2025-09-24"},
        "log_level": {"S": "INFO"},
        "source": {"S": "cleanup_tool"},
        "status": {"S": "success"}
    }'
```

## テーブル設計の特徴

### パーティションキー: log_id
- **目的**: 各ログエントリの一意識別
- **形式**: UUID
- **メリット**: 分散が均等、重複なし

### ソートキー: timestamp
- **目的**: 時系列ソート
- **形式**: ISO 8601
- **メリット**: 時間順での検索・ソートが容易

### GSI の活用
1. **table-timestamp-index**: 特定テーブルの操作履歴
2. **operation-timestamp-index**: 特定操作タイプの履歴
3. **date-range-index**: 日付範囲での検索

## 使用例

### 特定テーブルの操作履歴を取得
```python
response = table.query(
    IndexName='table-timestamp-index',
    KeyConditionExpression=Key('table_name').eq('CvxStakeMetrics'),
    ScanIndexForward=False
)
```

### 特定操作タイプの履歴を取得
```python
response = table.query(
    IndexName='operation-timestamp-index',
    KeyConditionExpression=Key('operation_type').eq('cleanup'),
    ScanIndexForward=False
)
```

### 日付範囲での検索
```python
response = table.query(
    IndexName='date-range-index',
    KeyConditionExpression=Key('date').eq('2025-09-24'),
    ScanIndexForward=False
)
```
