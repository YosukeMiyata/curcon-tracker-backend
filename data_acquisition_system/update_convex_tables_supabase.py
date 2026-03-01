#!/usr/bin/env python3
"""
Supabase上のConvex関連テーブルのfactory_idを一括更新し、
convex_failed_pool_matching をクリアするスクリプト。
GitHub Actions + Supabase 運用で、対応表更新後に手動実行する想定。

対象テーブル: pool_latest, convex_pool_history, convex_pool_ohlc_daily, convex_pool_remarks_history
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
# ローカル用: .env.local があれば読み込む（GitHub Actions では存在しない）
_env_local = Path(__file__).resolve().parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

# リポジトリルートを基準に manual_pool_mapping.json を読む（GitHub Actions でも動作）
SCRIPT_DIR = Path(__file__).resolve().parent
MAPPING_FILE = SCRIPT_DIR / "manual_pool_mapping.json"

SUPABASE_TABLES = [
    ("pool_latest", "pool_id", ["pool_id", "pool_name"], "pool_id"),
    ("convex_pool_history", "pool_id,timestamp", ["pool_id", "timestamp", "pool_name"], "pool_id,timestamp"),
    ("convex_pool_ohlc_daily", "pool_id_type,timestamp", ["pool_id_type", "timestamp", "pool_name", "pool_id"], "pool_id_type,timestamp"),
    ("convex_pool_remarks_history", "pool_id,timestamp", ["pool_id", "timestamp", "pool_name"], "pool_id,timestamp"),
]


def normalize_text(text):
    if not text:
        return ""
    t = (text or "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    return t.strip()


def load_manual_mapping():
    if not MAPPING_FILE.exists():
        print(f"⚠️ 対応表が見つかりません: {MAPPING_FILE}")
        return {}
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def find_factory_id(manual_mapping, pool_name):
    if not pool_name:
        return None
    norm = normalize_text(pool_name)
    if norm in manual_mapping:
        return manual_mapping[norm]
    if pool_name in manual_mapping:
        return manual_mapping[pool_name]
    for name, fid in manual_mapping.items():
        if normalize_text(name) == norm:
            return fid
    return None


def run():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定してください")
        return 1

    manual_mapping = load_manual_mapping()
    print(f"📋 人力対応表エントリ数: {len(manual_mapping)}")
    if not manual_mapping:
        print("⚠️ 対応表が空のためスキップします")
        return 0

    supabase = create_client(url, key)
    total_updated = 0

    for table_name, on_conflict, select_cols, key_cols in SUPABASE_TABLES:
        print(f"\n📊 {table_name} を処理中...")
        try:
            key_list = [c.strip() for c in key_cols.split(",")]
            seen_keys = set()
            rows_to_update = []
            page_size = 1000
            for filter_fn in [
                lambda q: q.is_("factory_id", "null"),
                lambda q: q.eq("factory_id", ""),
            ]:
                offset = 0
                while True:
                    q = supabase.table(table_name).select("*").range(offset, offset + page_size - 1)
                    resp = filter_fn(q).execute()
                    data = resp.data or []
                    for r in data:
                        key_tuple = tuple(r.get(k) for k in key_list)
                        if key_tuple not in seen_keys:
                            seen_keys.add(key_tuple)
                            rows_to_update.append(r)
                    if len(data) < page_size:
                        break
                    offset += page_size
            print(f"   factory_id 未設定: {len(rows_to_update)} 件")

            updated = 0
            for row in rows_to_update:
                pool_name = row.get("pool_name") or row.get("pool_id")
                pool_id_type = row.get("pool_id_type")
                if pool_id_type:
                    search_name = pool_id_type.split("#")[0] if "#" in str(pool_id_type) else pool_id_type
                else:
                    search_name = pool_name
                factory_id = find_factory_id(manual_mapping, search_name or pool_name)
                if not factory_id:
                    continue
                key_list = [c.strip() for c in key_cols.split(",")]
                key_vals = {k: row[k] for k in key_list if k in row}
                if len(key_vals) != len(key_list):
                    continue
                try:
                    supabase.table(table_name).update({"factory_id": factory_id}).match(
                        key_vals
                    ).execute()
                    updated += 1
                    if updated % 20 == 0:
                        print(f"   進捗: {updated} 件更新")
                except Exception as e:
                    print(f"   ❌ 更新エラー {key_vals}: {e}")

            print(f"   ✅ {table_name}: {updated} 件更新")
            total_updated += updated
        except Exception as e:
            print(f"   ❌ {table_name} エラー: {e}")

    # convex_failed_pool_matching をクリア（全件削除）
    print("\n🧹 convex_failed_pool_matching をクリア中...")
    try:
        r = supabase.table("convex_failed_pool_matching").select("pool_name").execute()
        names = [row["pool_name"] for row in (r.data or [])]
        for name in names:
            supabase.table("convex_failed_pool_matching").delete().eq("pool_name", name).execute()
        print(f"   ✅ {len(names)} 件削除しました")
    except Exception as e:
        print(f"   ❌ クリア失敗: {e}")

    print("\n" + "=" * 60)
    print("✅ Supabase Convex factory_id 更新完了")
    print(f"   総更新件数: {total_updated}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(run())
