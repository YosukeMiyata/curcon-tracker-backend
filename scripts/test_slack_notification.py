#!/usr/bin/env python3
"""
Slack通知のテストスクリプト
.env.local を優先し、SLACK_WEBHOOK_URL を使用してテストメッセージを送信します。
"""
import os
import sys
from pathlib import Path

# プロジェクトルート
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# 環境変数: .env.local を優先
try:
    from dotenv import load_dotenv
    _env = _project_root / '.env'
    _env_local = _project_root / '.env.local'
    if _env.exists():
        load_dotenv(_env)
    if _env_local.exists():
        load_dotenv(_env_local)
except ImportError:
    pass

try:
    from utils.slack_notifier import SlackNotifier

    notifier = SlackNotifier()
    success = notifier.notify_info(
        message="🧪 これはSlack通知のテストメッセージです。正常に届いていれば設定は問題ありません。",
        system_name="CurCon Tracker テスト"
    )
    if success:
        print("✅ Slackにテストメッセージを送信しました。チャンネルを確認してください。")
    else:
        print("❌ Slackへの送信に失敗しました。Webhook URLを確認してください。")
        sys.exit(1)
except Exception as e:
    print(f"❌ エラー: {e}")
    sys.exit(1)
