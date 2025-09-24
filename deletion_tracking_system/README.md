# 削除追跡システム (Deletion Tracking System)

## 概要
DynamoDBテーブルの削除操作を追跡・記録するシステムです。`DeletionTrackingLogs`テーブルを使用して、すべての削除操作を永続的に記録します。

## 必要なファイル

### 1. コアシステム
- **`final_tracking_system.py`** - メインの追跡システム
- **`tracked_cleanup_tool_final.py`** - 追跡機能付きクリーンアップツール

### 2. EC2デプロイメント
- **`deploy_ec2_final_tracking.sh`** - EC2への自動デプロイスクリプト
- **`monitor_ec2_final_tracking.sh`** - EC2システム監視スクリプト
- **`ec2_final_tracking_setup.py`** - EC2セットアップ用Pythonスクリプト

### 3. インフラストラクチャ
- **`DeletionTrackingLogs_CloudFormation.yaml`** - CloudFormationテンプレート
- **`DeletionTrackingLogs_AWSCLI.md`** - AWS CLIでのテーブル作成手順

### 4. データ分析・管理
- **`google_colab_deletion_tracker_viewer.py`** - Google Colab用データビューア

## システム構成

### ローカル環境
```
deletion_tracking_system/
├── final_tracking_system.py          # メイン追跡システム
├── tracked_cleanup_tool_final.py     # 追跡機能付きクリーンアップツール
├── google_colab_deletion_tracker_viewer.py  # データビューア
└── README.md                         # このファイル
```

### EC2環境
```
/home/ubuntu/deletion-tracking/
├── final_tracking_system.py          # メイン追跡システム
├── tracked_cleanup_tool_final.py     # 追跡機能付きクリーンアップツール
├── tracking_monitor_final.py          # 監視スクリプト（自動生成）
└── deletion-tracker-final.service    # systemdサービス（自動生成）
```

## 使用方法

### 1. 初期セットアップ
```bash
# CloudFormationでテーブル作成
aws cloudformation create-stack --stack-name deletion-tracking-logs --template-body file://DeletionTrackingLogs_CloudFormation.yaml

# またはAWS CLIでテーブル作成
# DeletionTrackingLogs_AWSCLI.mdの手順に従う
```

### 2. EC2デプロイ
```bash
./deploy_ec2_final_tracking.sh
```

### 3. システム監視
```bash
./monitor_ec2_final_tracking.sh
```

### 4. データ分析（Google Colab）
- `google_colab_deletion_tracker_viewer.py`をColabで実行
- ログの表示、分析、CSVダウンロードが可能

## 機能

### 追跡機能
- 削除操作の自動検出
- 呼び出し元情報の記録
- タイムスタンプ付きログ
- テーブル別・操作別分析

### 分析機能
- 包括的なログ分析
- 時間別・日別統計
- テーブル別操作回数
- 最近の操作履歴

### 管理機能
- ログの表示・検索
- CSVエクスポート
- 条件付き削除
- 古いログのクリーンアップ

## テーブル構造

### DeletionTrackingLogs
- **Primary Key**: `log_id` (String), `timestamp` (String)
- **GSIs**:
  - `table-timestamp-index`: テーブル別検索
  - `operation-timestamp-index`: 操作別検索
  - `date-range-index`: 日付範囲検索

## 注意事項

- システムは24時間稼働します
- ログは永続的に保存されます
- 大量のログが蓄積される可能性があります
- 定期的なログクリーンアップを推奨します

## トラブルシューティング

### よくある問題
1. **テーブルが存在しない**: CloudFormationまたはAWS CLIでテーブルを作成
2. **権限エラー**: IAMロールにDynamoDB権限を追加
3. **接続エラー**: AWS認証情報を確認

### ログ確認
```bash
# EC2でのログ確認
ssh -i key.pem ubuntu@ec2-ip "sudo journalctl -u deletion-tracker-final.service -f"
```

## 監視・管理ツール

### monitor_ec2_final_tracking.sh - システム監視スクリプト

#### 目的
EC2上の削除追跡システムの状態を確認・監視するためのスクリプトです。

#### 使用場面
- **定期的なシステム監視**: 毎日・毎週の健全性チェック
- **問題発生時の診断**: システムが動作しない時の原因調査
- **デプロイ後の確認**: 新しいデプロイ後の動作検証

#### 使用方法
```bash
# 基本的な監視
./monitor_ec2_final_tracking.sh

# 問題発生時の診断
./monitor_ec2_final_tracking.sh
```

#### 確認できる情報
- **サービスステータス**: `deletion-tracker-final.service`の状態
- **追跡ログ**: 最新20行のログ内容
- **削除履歴**: 過去1日間の削除操作
- **テーブル状況**: 過去7日間の包括的分析

### ec2_final_tracking_setup.py - インタラクティブセットアップツール

#### 目的
EC2上での削除追跡システムの自動セットアップを行う対話型ツールです。

#### 使用場面
- **初回セットアップ**: 削除追跡システムを初めてEC2に導入する時
- **システム再構築**: 設定をリセットしたい時、システムが壊れた時の修復
- **新しいEC2インスタンスへの移行**: 別のEC2インスタンスに移行する時

#### 使用方法
```bash
# 初回セットアップ
cd deletion_tracking_system/
python3 ec2_final_tracking_setup.py

# 再セットアップ
python3 ec2_final_tracking_setup.py
```

#### 実行される処理
1. **EC2情報の取得**: IPアドレス、ユーザー名の入力
2. **接続テスト**: EC2への接続確認
3. **ファイルアップロード**: 追跡システムファイルの転送
4. **サービス設定**: systemdサービスの設定
5. **デプロイメント検証**: 動作確認
6. **監視スクリプト作成**: 監視用スクリプトの生成

#### アップロードされるファイル
- **`final_tracking_system.py`**: メインの追跡システム
- **`tracked_cleanup_tool_final.py`**: 追跡機能付きクリーンアップツール

## デプロイ方法の選択

### 自動デプロイ（推奨）
```bash
./deploy_ec2_final_tracking.sh
```
- **特徴**: 設定済み、一発実行
- **用途**: 通常のデプロイ、既知の環境

### インタラクティブセットアップ
```bash
python3 ec2_final_tracking_setup.py
```
- **特徴**: 柔軟な設定、エラーハンドリング
- **用途**: 初回セットアップ、カスタム設定、問題解決
