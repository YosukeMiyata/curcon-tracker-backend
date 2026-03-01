#!/usr/bin/env python3
"""
Supabase の convex_failed_pool_matching を参照し、
pending の失敗プール一覧を表示するスクリプト。
GitHub Actions やローカルで「失敗プール確認」に利用する。
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def run():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定してください")
        return 1

    supabase = create_client(url, key)
    status = os.getenv("FAILED_POOL_STATUS", "pending")

    resp = (
        supabase.table("convex_failed_pool_matching")
        .select("*")
        .eq("status", status)
        .order("failure_count", desc=True)
        .execute()
    )
    rows = resp.data or []

    if not rows:
        print("✅ 未解決の失敗プールはありません。")
        return 0

    print(f"📋 未解決の失敗プール（status={status}）: {len(rows)} 件\n")
    for r in rows:
        print(f"  - {r.get('pool_name')}")
        print(f"    失敗回数: {r.get('failure_count', 0)}, 初回: {r.get('first_seen')}, 最終: {r.get('last_seen')}")
    print("\n対応表（manual_pool_mapping.json）に factory_id を追加後、")
    print("GitHub Actions の「Update Convex factory_id (Supabase)」ワークフローを実行してください。")
    return 0


if __name__ == "__main__":
    exit(run())
