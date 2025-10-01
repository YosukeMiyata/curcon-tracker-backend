#!/bin/bash

# ConvexPoolMetrics既存データ更新スクリプトのデプロイ
# 使用方法: ./deploy_factory_id_update.sh -h <EC2_IP> -k <SSH_KEY_PATH>

set -e

# デフォルト値
EC2_HOST=""
SSH_KEY=""
DRY_RUN=false

# ヘルプ表示
show_help() {
    echo "使用方法: $0 -h <EC2_IP> -k <SSH_KEY_PATH> [オプション]"
    echo ""
    echo "オプション:"
    echo "  -h, --host HOST        EC2インスタンスのIPアドレス"
    echo "  -k, --key KEY          SSH秘密鍵のパス"
    echo "  -d, --dry-run          ドライラン（実際の実行はしない）"
    echo "  --help                 このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 -h 54.64.254.201 -k ~/.ssh/convex-keypair.pem"
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            EC2_HOST="$2"
            shift 2
            ;;
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "❌ 不明なオプション: $1"
            show_help
            exit 1
            ;;
    esac
done

# 必須パラメータの確認
if [[ -z "$EC2_HOST" || -z "$SSH_KEY" ]]; then
    echo "❌ エラー: EC2_HOSTとSSH_KEYは必須です"
    show_help
    exit 1
fi

# SSH鍵の存在確認
if [[ ! -f "$SSH_KEY" ]]; then
    echo "❌ エラー: SSH鍵が見つかりません: $SSH_KEY"
    exit 1
fi

echo "🚀 ConvexPoolMetrics既存データ更新スクリプトのデプロイ"
echo "="*60
echo "📋 設定:"
echo "   - EC2 Host: $EC2_HOST"
echo "   - SSH Key: $SSH_KEY"
echo "   - Dry Run: $DRY_RUN"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo "🔍 ドライラン: 実際の実行は行いません"
    echo ""
    echo "実行予定のコマンド:"
    echo "  scp -i $SSH_KEY update_existing_convex_pool_metrics.py ubuntu@$EC2_HOST:/home/ubuntu/convex-scraper/"
    echo "  scp -i $SSH_KEY manual_pool_mapping.json ubuntu@$EC2_HOST:/home/ubuntu/convex-scraper/"
    echo "  ssh -i $SSH_KEY ubuntu@$EC2_HOST 'cd /home/ubuntu/convex-scraper && python update_existing_convex_pool_metrics.py'"
    exit 0
fi

# ファイルの存在確認
if [[ ! -f "update_existing_convex_pool_metrics.py" ]]; then
    echo "❌ エラー: update_existing_convex_pool_metrics.pyが見つかりません"
    exit 1
fi

if [[ ! -f "manual_pool_mapping.json" ]]; then
    echo "❌ エラー: manual_pool_mapping.jsonが見つかりません"
    exit 1
fi

echo "📤 ファイルをEC2にアップロード中..."

# ファイルをEC2にアップロード
scp -i "$SSH_KEY" update_existing_convex_pool_metrics.py ubuntu@$EC2_HOST:/home/ubuntu/convex-scraper/
if [[ $? -eq 0 ]]; then
    echo "✅ update_existing_convex_pool_metrics.py アップロード完了"
else
    echo "❌ update_existing_convex_pool_metrics.py アップロード失敗"
    exit 1
fi

scp -i "$SSH_KEY" manual_pool_mapping.json ubuntu@$EC2_HOST:/home/ubuntu/convex-scraper/
if [[ $? -eq 0 ]]; then
    echo "✅ manual_pool_mapping.json アップロード完了"
else
    echo "❌ manual_pool_mapping.json アップロード失敗"
    exit 1
fi

echo ""
echo "🔄 EC2で更新スクリプトを実行中..."

# EC2でスクリプトを実行
ssh -i "$SSH_KEY" ubuntu@$EC2_HOST << 'EOF'
cd /home/ubuntu/convex-scraper

echo "🔍 現在のディレクトリ内容:"
ls -la

echo ""
echo "🐍 Python環境確認:"
python3 --version

echo ""
echo "📦 必要なパッケージ確認:"
python3 -c "import boto3; print('✅ boto3:', boto3.__version__)"

echo ""
echo "🚀 ConvexPoolMetrics更新スクリプト実行:"
python3 update_existing_convex_pool_metrics.py
EOF

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✅ 更新スクリプト実行完了"
    echo ""
    echo "📊 結果確認方法:"
    echo "   ssh -i $SSH_KEY ubuntu@$EC2_HOST 'cd /home/ubuntu/convex-scraper && python3 -c \"import boto3; table=boto3.resource(\"dynamodb\").Table(\"ConvexPoolMetrics\"); response=table.scan(); print(f\"総件数: {len(response[\"Items\"])}\"); items_with_factory_id=[item for item in response[\"Items\"] if item.get(\"factory_id\")]; print(f\"factory_idあり: {len(items_with_factory_id)}\")\"'"
else
    echo "❌ 更新スクリプト実行失敗"
    exit 1
fi

echo ""
echo "🎉 デプロイ完了!"
