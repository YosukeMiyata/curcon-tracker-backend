# 🚀 CurConTracker Backend

CurConTrackerのバックエンドサービス群。Convexデータのスクレイピング、EC2デプロイメント、監視機能、Google Colabツールを提供します。

## 📋 目次

- [概要](#概要)
- [機能](#機能)
- [セットアップ](#セットアップ)
- [使用方法](#使用方法)
- [デプロイメント](#デプロイメント)
- [監視](#監視)
- [Google Colabツール](#google-colabツール)
- [依存関係](#依存関係)
- [ドキュメント](#ドキュメント)

## 🎯 概要

CurConTrackerは、Convexデータを効率的に収集・処理・監視するための包括的なバックエンドシステムです。AWS EC2での自動デプロイメント、リアルタイム監視、データ分析ツールを提供します。

## ⚡ 機能

### 🔄 データスクレイピング
- **data_acquisition_system/convex_ec2_complete.py**: EC2完全版スクレイパー
- **google_colab/data_acquisition/Convex_Production_JST_WithPrices.py**: Google Colab用本番環境スクレイピング
- **google_colab/data_acquisition/convex_scraper_integrated.py**: Google Colab用統合型スクレイピング

### 🚀 デプロイメント
- **data_acquisition_system/deploy_t3_micro.sh**: t3.microインスタンス用デプロイスクリプト
- **ec2_quick_start.md**: EC2クイックスタートガイド
- **ec2_setup_guide.md**: 詳細セットアップガイド

### 📊 監視・運用
- **data_acquisition_system/monitor_convex.sh**: Convexデータ監視スクリプト
- **production_monitor.sh**: 本番環境監視システム
- **t3_micro_recommendation.md**: t3.micro選択の正当性分析
- **t3_micro_quick_deploy.md**: t3.microクイックデプロイガイド

### 🔧 Google Colabツール
- **google_colab_comprehensive_viewer.py**: 包括的データビューア
- **google_colab_cleanup_tool.py**: データクリーンアップツール

## 🛠️ セットアップ

### 前提条件

```bash
# Python 3.8以上
python --version

# AWS CLI（オプション）
aws --version

# Git
git --version
```

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/YosukeMiyata/curcon-tracker-backend.git
cd curcon-tracker-backend

# 依存関係をインストール
pip install -r requirements.txt

# 環境変数を設定
cp .env.example .env
# .envファイルを編集して必要な値を設定
```

### 必要な環境変数

```bash
# AWS認証情報
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=ap-northeast-1

# AlphaVantage API（為替レート取得用）
ALPHA_VANTAGE_API_KEY=your-api-key

# その他の設定
CONVEX_BASE_URL=your-convex-url
```

## 🚀 使用方法

### 基本的なスクレイピング実行

```bash
# EC2完全版スクレイパー
python data_acquisition_system/convex_ec2_complete.py

# Google Colab用スクレイピング（Colab環境で実行）
# exec(open('google_colab/data_acquisition/Convex_Production_JST_WithPrices.py').read())
# exec(open('google_colab/data_acquisition/convex_scraper_integrated.py').read())
```

### 監視の開始

```bash
# Convexデータ監視
./data_acquisition_system/monitor_convex.sh status
./data_acquisition_system/monitor_convex.sh logs

# 本番環境監視
./production_monitor.sh
```

## 🏗️ デプロイメント

### EC2自動デプロイ

```bash
# t3.microインスタンス用デプロイ
./data_acquisition_system/deploy_t3_micro.sh -h <EC2_IP> -k <SSH_KEY_PATH>
```

### 手動デプロイ手順

1. **EC2インスタンス作成**
   - AMI: Ubuntu 22.04 LTS
   - インスタンスタイプ: t3.micro（推奨）またはt3.small
   - セキュリティグループ: SSH (22) のみ許可

2. **環境設定**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   cd /home/ubuntu
   git clone https://github.com/YosukeMiyata/curcon-tracker-backend.git
   cd curcon-tracker-backend
   pip install -r requirements.txt
   ```

3. **環境変数設定**
   ```bash
   nano .env
   # 必要な環境変数を設定
   ```

4. **サービス開始**
   ```bash
   # スクレイピングサービス開始
   python data_acquisition_system/convex_ec2_complete.py
   
   # 監視サービス開始
   ./monitor_convex.sh
   ```

## 📊 監視

### 監視機能

- **リアルタイムデータ監視**: Convexデータの取得状況を監視
- **パフォーマンス監視**: システムリソース使用量の追跡
- **エラー監視**: スクレイピングエラーの検出と通知
- **ログ管理**: 詳細なログファイルの生成と管理

### 監視スクリプトの使用方法

```bash
# 基本的な監視開始
./monitor_convex.sh

# 詳細監視（ログ出力付き）
./monitor_convex.sh --verbose

# 本番環境監視
./production_monitor.sh
```

## 🔧 Google Colabツール

### 包括的データビューア

```python
# Google Colabで実行
!pip install -r requirements.txt
exec(open('google_colab_comprehensive_viewer.py').read())
```

### データクリーンアップツール

```python
# Google Colabで実行
exec(open('google_colab_cleanup_tool.py').read())
```

## 📦 依存関係

```txt
playwright==1.40.0      # Webスクレイピング
boto3==1.34.144         # AWS SDK
requests==2.31.0        # HTTP リクエスト
beautifulsoup4==4.12.2  # HTML解析
python-dateutil==2.8.2  # 日付処理
```

## 📚 ドキュメント

### セットアップ・デプロイメント
- **[EC2クイックスタートガイド](ec2_deployment/ec2_quick_start.md)**: EC2の迅速なセットアップ
- **[EC2セットアップガイド](ec2_deployment/ec2_setup_guide.md)**: 詳細なEC2設定手順
- **[t3.micro推奨理由](ec2_deployment/t3_micro_recommendation.md)**: t3.micro選択の正当性分析
- **[t3.microクイックデプロイ](ec2_deployment/t3_micro_quick_deploy.md)**: t3.micro用デプロイ手順

### 人力対応表システム
- **[人力対応表システム詳細](docs/manual_pool_mapping_system.md)**: マッチングロジックとJSONファイル管理の完全ガイド
- **[クイックリファレンス](docs/manual_mapping_quick_reference.md)**: よく使うコマンドと運用方法
- **[システムアーキテクチャ](docs/system_architecture.md)**: システム全体の構成とデータフロー

### パフォーマンス・運用
- **[タイミング改善ガイド](docs/timing_improvement_guide.md)**: スクレイピングタイミングの最適化

## 🤝 貢献

1. このリポジトリをフォーク
2. フィーチャーブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add some amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 📞 サポート

問題が発生した場合や質問がある場合は、[Issues](https://github.com/YosukeMiyata/curcon-tracker-backend/issues)で報告してください。

## 🔄 更新履歴

- **v1.1.0**: 人力対応表システム追加
  - JSONファイルベースの人力対応表システム
  - マッチング失敗プールの自動記録
  - リアルタイム更新機能
  - 管理ツール（manual_mapping_manager_json.py）
  - 包括的なドキュメント整備

- **v1.0.0**: 初回リリース
  - Convexデータスクレイピング機能
  - EC2自動デプロイメント
  - 監視システム
  - Google Colabツール

---

**CurConTracker Backend** - 効率的なConvexデータ管理システム
