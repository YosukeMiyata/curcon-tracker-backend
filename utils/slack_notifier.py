#!/usr/bin/env python3
"""
Slack通知ユーティリティ
エラーや失敗が発生した際にSlackへ通知を送信する
"""

import requests
import json
import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import os
from pathlib import Path

# 環境変数読み込み（.envファイルから）
try:
    from dotenv import load_dotenv
    # プロジェクトルートの.envファイルを読み込む
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # .envファイルが見つからない場合はカレントディレクトリから探す
        load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

class SlackNotifier:
    """Slack通知を送信するクラス"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Slack通知システムの初期化
        
        Args:
            webhook_url: Slack Webhook URL。Noneの場合は環境変数から取得
        """
        # .envファイルから環境変数を読み込む（まだ読み込まれていない場合）
        if DOTENV_AVAILABLE:
            env_path = Path(__file__).parent.parent / '.env'
            if env_path.exists():
                load_dotenv(env_path, override=False)
            else:
                load_dotenv(override=False)
        
        # Webhook URLを取得（引数 > 環境変数）。.env に SLACK_WEBHOOK_URL を設定すること
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        
        # ログ設定
        self.logger = logging.getLogger(__name__)
        
        # 日本時間の設定
        self.JST = timezone(timedelta(hours=9))
    
    def send_notification(self, 
                         message: str, 
                         level: str = "error",
                         title: Optional[str] = None,
                         system_name: Optional[str] = None,
                         error_details: Optional[str] = None,
                         traceback_info: Optional[str] = None) -> bool:
        """
        Slack通知を送信
        
        Args:
            message: 通知メッセージ
            level: 通知レベル（error, warning, info）
            title: 通知タイトル
            system_name: システム名（例: "Convex EC2 Complete", "Token Price Tracker"）
            error_details: エラー詳細
            traceback_info: トレースバック情報
            
        Returns:
            送信成功時True、失敗時False
        """
        if not self.webhook_url:
            self.logger.warning("Slack Webhook URLが設定されていません。.env に SLACK_WEBHOOK_URL を設定してください。")
            return False

        try:
            # 色の設定（Slackの色コード）
            color_map = {
                "error": "#FF0000",      # 赤
                "warning": "#FFA500",    # オレンジ
                "info": "#36A2EB"        # 青
            }
            color = color_map.get(level, "#808080")
            
            # アイコンの設定
            icon_map = {
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️"
            }
            icon = icon_map.get(level, "📢")
            
            # 日本時間で現在時刻を取得
            jst_now = datetime.now(self.JST)
            timestamp = jst_now.strftime("%Y-%m-%d %H:%M:%S JST")
            
            # システム名が指定されていない場合はファイル名から推測
            if not system_name:
                system_name = "Unknown System"
            
            # タイトルが指定されていない場合はレベルから生成
            if not title:
                title = f"{icon} {level.upper()}: {system_name}"
            
            # Slackメッセージの構築
            blocks = []
            
            # ヘッダー
            blocks.append({
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True
                }
            })
            
            # メッセージ本文
            text_fields = [
                {
                    "type": "mrkdwn",
                    "text": f"*システム:* {system_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*時刻:* {timestamp}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*メッセージ:*\n{message}"
                }
            ]
            
            # エラー詳細があれば追加
            if error_details:
                text_fields.append({
                    "type": "mrkdwn",
                    "text": f"*エラー詳細:*\n```{error_details}```"
                })
            
            # トレースバック情報があれば追加
            if traceback_info:
                # トレースバックは長い可能性があるので、最初の500文字に制限
                traceback_short = traceback_info[:500]
                if len(traceback_info) > 500:
                    traceback_short += "\n...(以下省略)"
                text_fields.append({
                    "type": "mrkdwn",
                    "text": f"*トレースバック:*\n```{traceback_short}```"
                })
            
            blocks.append({
                "type": "section",
                "fields": text_fields
            })
            
            # フッターを追加
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"CurConTracker Backend | {timestamp}"
                    }
                ]
            })
            
            # ペイロードの構築（blocksのみを使用）
            payload = {
                "blocks": blocks,
                "attachments": [
                    {
                        "color": color,
                        "footer": "CurConTracker Backend",
                        "ts": int(jst_now.timestamp())
                    }
                ]
            }
            
            # Slackに送信
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.debug(f"Slack通知送信成功: {message[:50]}...")
                return True
            else:
                self.logger.error(f"Slack通知送信失敗: HTTP {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Slack通知送信エラー（ネットワーク）: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Slack通知送信エラー: {e}")
            return False
    
    def notify_error(self, 
                    message: str,
                    system_name: Optional[str] = None,
                    error: Optional[Exception] = None,
                    traceback_info: Optional[str] = None) -> bool:
        """
        エラー通知を送信（簡易版）
        
        Args:
            message: エラーメッセージ
            system_name: システム名
            error: 例外オブジェクト
            traceback_info: トレースバック情報（Noneの場合は自動取得）
            
        Returns:
            送信成功時True、失敗時False
        """
        error_details = None
        if error:
            error_details = str(error)
        
        if not traceback_info and error:
            traceback_info = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        
        return self.send_notification(
            message=message,
            level="error",
            system_name=system_name,
            error_details=error_details,
            traceback_info=traceback_info
        )
    
    def notify_warning(self, message: str, system_name: Optional[str] = None) -> bool:
        """
        警告通知を送信（簡易版）
        
        Args:
            message: 警告メッセージ
            system_name: システム名
            
        Returns:
            送信成功時True、失敗時False
        """
        return self.send_notification(
            message=message,
            level="warning",
            system_name=system_name
        )
    
    def notify_info(self, message: str, system_name: Optional[str] = None) -> bool:
        """
        情報通知を送信（簡易版）
        
        Args:
            message: 情報メッセージ
            system_name: システム名
            
        Returns:
            送信成功時True、失敗時False
        """
        return self.send_notification(
            message=message,
            level="info",
            system_name=system_name
        )


# グローバルインスタンス（オプション）
_global_notifier = None

def get_notifier(webhook_url: Optional[str] = None) -> SlackNotifier:
    """
    グローバルSlack通知インスタンスを取得
    
    Args:
        webhook_url: Slack Webhook URL（初回のみ有効）
        
    Returns:
        SlackNotifierインスタンス
    """
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = SlackNotifier(webhook_url=webhook_url)
    return _global_notifier

