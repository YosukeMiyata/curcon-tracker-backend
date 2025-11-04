#!/usr/bin/env python3
"""
Slack通知機能のテストスクリプト
エラー、警告、情報の3種類の通知を送信して動作確認します
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# プロジェクトルートをパスに追加
# まずEC2上のパスを試す（/home/ubuntu/convex-scraper）
if Path('/home/ubuntu/convex-scraper/utils/slack_notifier.py').exists():
    sys.path.insert(0, '/home/ubuntu/convex-scraper')
    from utils.slack_notifier import SlackNotifier
else:
    # ローカル環境または他のパス
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from utils.slack_notifier import SlackNotifier
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from utils.slack_notifier import SlackNotifier

def test_slack_notifications():
    """Slack通知のテストを実行"""
    print("🧪 Slack通知機能のテストを開始します...")
    print("=" * 60)
    
    # Slack通知インスタンスを作成
    try:
        notifier = SlackNotifier()
        print("✅ SlackNotifierの初期化に成功しました")
    except Exception as e:
        print(f"❌ SlackNotifierの初期化に失敗しました: {e}")
        return False
    
    # テスト1: 情報通知
    print("\n📢 テスト1: 情報通知を送信中...")
    try:
        result = notifier.notify_info(
            message="これはSlack通知機能のテストです。\n情報レベルの通知が正常に動作しています。",
            system_name="Convex EC2 Complete - テスト"
        )
        if result:
            print("✅ 情報通知の送信に成功しました")
        else:
            print("❌ 情報通知の送信に失敗しました")
    except Exception as e:
        print(f"❌ 情報通知の送信中にエラーが発生しました: {e}")
    
    import time
    time.sleep(2)  # 通知間の間隔
    
    # テスト2: 警告通知
    print("\n⚠️  テスト2: 警告通知を送信中...")
    try:
        result = notifier.notify_warning(
            message="これは警告レベルのテスト通知です。\nシステムは正常に動作していますが、注意が必要な状況をシミュレートしています。",
            system_name="Convex EC2 Complete - テスト"
        )
        if result:
            print("✅ 警告通知の送信に成功しました")
        else:
            print("❌ 警告通知の送信に失敗しました")
    except Exception as e:
        print(f"❌ 警告通知の送信中にエラーが発生しました: {e}")
    
    time.sleep(2)  # 通知間の間隔
    
    # テスト3: エラー通知（詳細情報付き）
    print("\n❌ テスト3: エラー通知を送信中...")
    try:
        # テスト用の例外を作成
        test_error = Exception("これはテスト用のエラーです。実際のエラーではありません。")
        
        result = notifier.notify_error(
            message="これはエラーレベルのテスト通知です。\nエラー通知機能が正常に動作していることを確認しています。",
            system_name="Convex EC2 Complete - テスト",
            error=test_error
        )
        if result:
            print("✅ エラー通知の送信に成功しました")
        else:
            print("❌ エラー通知の送信に失敗しました")
    except Exception as e:
        print(f"❌ エラー通知の送信中にエラーが発生しました: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 テスト完了！")
    print("📱 Slackチャンネルで通知が受信されているか確認してください。")
    print("   - 情報通知（青）")
    print("   - 警告通知（オレンジ）")
    print("   - エラー通知（赤）")
    
    return True

if __name__ == "__main__":
    try:
        test_slack_notifications()
    except Exception as e:
        print(f"❌ テスト実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

