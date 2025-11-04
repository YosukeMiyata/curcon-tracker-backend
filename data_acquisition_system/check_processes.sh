#!/bin/bash
# =====================================
# convex_ec2_complete.py の稼働プロセス数を確認
# =====================================

echo "=========================================="
echo "🔍 convex_ec2_complete.py プロセス確認"
echo "=========================================="
echo ""

# プロセス名で検索
PROCESS_COUNT=$(pgrep -f "convex_ec2_complete.py" 2>/dev/null | wc -l | tr -d ' ')
echo "📊 稼働中のプロセス数: $PROCESS_COUNT"
echo ""

if [ "$PROCESS_COUNT" -eq 0 ]; then
    echo "⚠️ プロセスが見つかりませんでした"
    echo ""
    echo "確認方法:"
    echo "  1. systemdサービスが実行中か確認:"
    echo "     systemctl status convex-scraper"
    echo ""
    echo "  2. Pythonプロセス全体を確認:"
    echo "     ps aux | grep python"
    echo ""
    echo "  3. ロックファイルの存在を確認:"
    echo "     ls -la /home/ubuntu/convex-scraper/.convex_scraper.lock"
else
    echo "✅ プロセスが実行中です"
    echo ""
    echo "詳細情報:"
    pgrep -f "convex_ec2_complete.py" | while read pid; do
        echo "  PID: $pid"
        ps -p $pid -o pid,ppid,%cpu,%mem,vsz,rss,start,time,cmd --no-headers
        echo ""
    done
fi

echo "=========================================="
echo "📋 関連プロセス情報"
echo "=========================================="
echo ""

# systemdサービス状態
echo "🔧 systemdサービス状態:"
if systemctl is-active --quiet convex-scraper 2>/dev/null; then
    echo "  ✅ convex-scraper: 実行中"
elif systemctl is-enabled --quiet convex-scraper 2>/dev/null; then
    echo "  ⚠️ convex-scraper: 停止中（有効化済み）"
else
    echo "  ❌ convex-scraper: サービスが見つかりません"
fi
echo ""

# Pythonプロセス全体
echo "🐍 Pythonプロセス一覧:"
PYTHON_COUNT=$(pgrep -f python 2>/dev/null | wc -l | tr -d ' ')
echo "  Pythonプロセス数: $PYTHON_COUNT"
if [ "$PYTHON_COUNT" -gt 0 ]; then
    ps aux | grep python | grep -v grep | head -5
fi
echo ""

# ロックファイル確認
echo "🔒 ロックファイル確認:"
LOCK_FILE="/home/ubuntu/convex-scraper/.convex_scraper.lock"
if [ -f "$LOCK_FILE" ]; then
    echo "  ✅ ロックファイルが存在します: $LOCK_FILE"
    echo "  作成日時: $(stat -c %y "$LOCK_FILE" 2>/dev/null || stat -f "%Sm" "$LOCK_FILE" 2>/dev/null)"
else
    echo "  ⚠️ ロックファイルが見つかりません"
fi
echo ""

# ログファイル確認
echo "📄 最新ログ確認:"
LOG_FILE="/home/ubuntu/convex-scraper/logs/convex.log"
if [ -f "$LOG_FILE" ]; then
    echo "  ログファイル: $LOG_FILE"
    echo "  最新の実行時刻:"
    tail -20 "$LOG_FILE" | grep -E "(次回実行予定|実行時間|⏰)" | tail -3
else
    echo "  ⚠️ ログファイルが見つかりません"
fi
echo ""

echo "=========================================="
