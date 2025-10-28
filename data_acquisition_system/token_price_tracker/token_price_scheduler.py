#!/usr/bin/env python3
# =====================================
# トークン価格追跡スケジューラー
# 1時間おきにトークン価格追跡を実行するsystemdサービス
# =====================================

import subprocess
import sys
import os
import time
from datetime import datetime, timezone

def run_token_price_tracking():
    """トークン価格追跡を実行"""
    try:
        # スクリプトのディレクトリを取得
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tracker_script = os.path.join(script_dir, 'token_price_tracker.py')
        
        # 実行
        result = subprocess.run([sys.executable, tracker_script], 
                              capture_output=True, text=True, cwd=script_dir)
        
        if result.returncode == 0:
            print(f"✅ {datetime.now().isoformat()} - トークン価格追跡成功")
            print(result.stdout)
        else:
            print(f"❌ {datetime.now().isoformat()} - トークン価格追跡失敗")
            print(f"エラー: {result.stderr}")
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ {datetime.now().isoformat()} - 実行エラー: {e}")
        return False

def main():
    """メイン関数"""
    print(f"🚀 {datetime.now().isoformat()} - トークン価格追跡スケジューラー開始")
    
    success = run_token_price_tracking()
    
    if success:
        print(f"✅ {datetime.now().isoformat()} - スケジューラー正常終了")
        sys.exit(0)
    else:
        print(f"❌ {datetime.now().isoformat()} - スケジューラー異常終了")
        sys.exit(1)

if __name__ == "__main__":
    main()
