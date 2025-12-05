# Curve Simulation API

EC2上でCurve Python公式ライブラリを使用した完全なシミュレーションAPI

## 📋 概要

このAPIは、Curve FinanceのプールでのデポジットとWithdrawのシミュレーションを提供します。過去のブロック状態を完全に再現し、正確なLP量、スリッページ、インパーマネントロスを計算します。

## 🚀 機能

- **デポジットシミュレーション** (`POST /simulate/deposit`)
  - LP量計算
  - スリッページ計算
  - ボーナス/ペナルティ計算
  - 理想的な資産比率

- **引き出しシミュレーション** (`POST /simulate/withdraw`)
  - 単一トークン引き出し
  - 比例引き出し

- **理想比率計算** (`POST /simulate/ideal-ratio`)
  - プールの理想的な資産比率を計算

- **インパーマネントロス計算** (`POST /simulate/impermanent-loss`)
  - HODLとの比較
  - 損失率計算

- **DynamoDB統合**
  - 全シミュレーション結果を自動保存
  - TTL 30日間で自動削除

## 📦 インストール

### ローカル環境

```bash
cd curve-sim
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-curve-sim.txt
```

### EC2環境

```bash
cd /home/ubuntu/curve-sim
./deploy.sh --systemd
```

## ⚙️ 設定

`.env`ファイルを作成して以下を設定:

```bash
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
ETH_RPC_URL=https://mainnet.infura.io/v3/your-project-id
LOG_LEVEL=INFO
```

## 🔧 使用方法

### ローカル起動

```bash
uvicorn app:app --reload --port 8001
```

### systemdサービス（EC2）

```bash
# 起動
sudo systemctl start curve-simulation-backend

# 停止
sudo systemctl stop curve-simulation-backend

# 再起動
sudo systemctl restart curve-simulation-backend

# ステータス確認
sudo systemctl status curve-simulation-backend

# ログ確認
sudo journalctl -u curve-simulation-backend -f
```

## 📡 API エンドポイント

### ヘルスチェック

```bash
curl http://localhost:8001/health
```

### デポジットシミュレーション

```bash
curl -X POST http://localhost:8001/simulate/deposit \
  -H "Content-Type: application/json" \
  -d '{
    "poolAddress": "0x...",
    "timestamp": 1234567890,
    "amounts": {"USDC": 1000, "DAI": 1000}
  }'
```

### 引き出しシミュレーション

```bash
curl -X POST http://localhost:8001/simulate/withdraw \
  -H "Content-Type: application/json" \
  -d '{
    "poolAddress": "0x...",
    "timestamp": 1234567890,
    "lpAmount": 100.5,
    "withdrawToken": "USDC"
  }'
```

## 📊 DynamoDB SimulationsHistory テーブル

全シミュレーション結果は自動的にDynamoDBに保存されます:

- **パーティションキー**: `pool_id`
- **ソートキー**: `timestamp` (ISO 8601 JST)
- **TTL**: 30日間（`expires_at`）

## 🔍 API ドキュメント

FastAPIの自動生成ドキュメント:

- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## 📝 ログ

ログは以下の場所に保存されます:

- systemd: `sudo journalctl -u curve-sim`
- アプリケーションログ: 標準出力

## 🛠️ トラブルシューティング

### Curve初期化エラー

```bash
# RPC URLを確認
echo $ETH_RPC_URL

# .envファイルを確認
cat .env
```

### DynamoDB接続エラー

```bash
# AWS認証情報を確認
aws sts get-caller-identity

# テーブルの存在確認
aws dynamodb describe-table --table-name SimulationsHistory
```

## 📈 パフォーマンス

- メモリ使用量: 約100-200MB
- レスポンスタイム: 1-3秒（RPC呼び出し含む）
- 推奨インスタンス: t3.micro以上

## 🔒 セキュリティ

- CORS設定を本番環境用に調整してください
- AWS認証情報は環境変数で管理
- RPC URLは信頼できるプロバイダーを使用

## 📄 ライセンス

MIT License
