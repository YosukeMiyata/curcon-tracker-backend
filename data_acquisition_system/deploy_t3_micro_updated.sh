#!/bin/bash

# =====================================
# EC2上でのConvex Financeスクレイパーデプロイ
# 修正版コードの簡単デプロイ
# =====================================

echo "🚀 EC2 Convex Financeスクレイパーデプロイ開始"
echo "========================================"

# 設定変数（実際の値に変更してください）
EC2_USER="ubuntu"
EC2_IP="54.64.254.201"  # 実際のEC2のIPアドレス
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"       # SSHキーファイルのパス
SCRAPER_PATH="/home/ubuntu/convex-scraper"

echo "📋 デプロイ設定:"
echo "   EC2 IP: $EC2_IP"
echo "   ユーザー: $EC2_USER"
echo "   キーファイル: $KEY_FILE"
echo "   スクレイパーパス: $SCRAPER_PATH"
echo ""

# 1. 修正されたスクレイパーファイルをEC2にアップロード
echo "1. 修正されたスクレイパーファイルをアップロード中..."
scp -i $KEY_FILE data_acquisition_system/convex_ec2_complete.py $EC2_USER@$EC2_IP:$SCRAPER_PATH/
if [ $? -eq 0 ]; then
    echo "   ✅ convex_ec2_complete.py アップロード完了"
else
    echo "   ❌ convex_ec2_complete.py アップロード失敗"
    exit 1
fi

# 2. 既存サービスを停止
echo ""
echo "2. 既存サービスを停止中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP "sudo systemctl stop convex-scraper" 2>/dev/null || {
    echo "   ⚠️ サービス停止スキップ（サービスが実行中でない可能性）"
}

# 3. 新しいコードでサービスを再起動
echo ""
echo "3. 新しいコードでサービスを再起動中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# サービスを再起動
sudo systemctl start convex-scraper

# サービス状態を確認
sleep 5
if sudo systemctl is-active --quiet convex-scraper; then
    echo "   ✅ サービス再起動成功"
else
    echo "   ❌ サービス再起動失敗"
    exit 1
fi

# サービス状態を表示
echo "   📊 サービス状態:"
sudo systemctl status convex-scraper --no-pager | head -10
EOF

# 4. デプロイ後の確認
echo ""
echo "4. デプロイ後の確認中..."
ssh -i $KEY_FILE $EC2_USER@$EC2_IP << 'EOF'
# プロセス確認
echo "   📊 実行中プロセス:"
ps aux | grep -E '(convex|python.*convex)' | grep -v grep

# ロックファイル確認
echo "   🔒 排他ロックファイル:"
if [ -f /home/ubuntu/convex-scraper/.convex_scraper.lock ]; then
    echo "   ✅ ロックファイル存在"
    echo "   📄 ロック内容:"
    cat /home/ubuntu/convex-scraper/.convex_scraper.lock
else
    echo "   ⚠️ ロックファイルなし"
fi

# 最新ログの確認
echo "   📋 最新ログ（最後の20行）:"
if [ -f /home/ubuntu/convex-scraper/logs/convex_complete.log ]; then
    tail -20 /home/ubuntu/convex-scraper/logs/convex_complete.log | grep -E "(プールデータ検索項目追加|Vaultデータとして保存|✅|❌)" || echo "   検索項目関連のログなし"
else
    echo "   ログファイルが見つかりません"
fi
EOF

echo ""
echo "✅ EC2 Convex Financeスクレイパーデプロイ完了"
echo "=========================================="
echo "📋 利用可能なコマンド:"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl status convex-scraper'  # サービス状態確認"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'sudo systemctl restart convex-scraper'  # サービス再起動"
echo "   ssh -i $KEY_FILE $EC2_USER@$EC2_IP 'tail -f /home/ubuntu/convex-scraper/logs/convex_complete.log'  # リアルタイムログ監視"
echo ""
echo "💡 新機能:"
echo "   - PoolLatestテーブルに検索用項目追加"
echo "   - token_symbols: トークンシンボル配列"
echo "   - normalized_name: 正規化された名前"
echo "   - search_tokens: 検索用トークン配列"
echo "   - is_vault: Vaultデータ判定フラグ"
echo "   - 重複実行防止機能（排他ロック）"
