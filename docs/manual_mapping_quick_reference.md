# 人力対応表システム クイックリファレンス

## 🚀 よく使うコマンド

### 管理ツール起動
```bash
ssh -i /Users/yousuke/.ssh/convex-keypair.pem ubuntu@54.64.254.201
cd /home/ubuntu/convex-scraper
python3 manual_mapping_manager_json.py
```

### ファイルの場所確認
```bash
# 人力対応表
cat /home/ubuntu/convex-scraper/manual_pool_mapping.json

# 失敗プール一覧
cat /home/ubuntu/convex-scraper/failed_pool_matching.json
```

### システム状態確認
```bash
sudo systemctl status convex-scraper
tail -f /home/ubuntu/convex-scraper/logs/convex_complete.log
```

## 📝 人力対応表の追加方法

### 1. 管理ツールで追加
```bash
python3 manual_mapping_manager_json.py
# 選択: 3
# プール名: 例) FRAX+FXB_20241231
# factory_id: 例) factory-stable-ng-44
# 説明: 例) FRAX FXB 債券プール
```

### 2. 直接編集
```bash
nano /home/ubuntu/convex-scraper/manual_pool_mapping.json
```

### 3. 一括追加（JSON形式）
```json
[
  {
    "pool_name": "FRAX+FXB_20241231",
    "factory_id": "factory-stable-ng-44",
    "description": "FRAX FXB 債券プール"
  }
]
```

## 🔍 失敗プールの確認

### 失敗プール一覧
```bash
python3 manual_mapping_manager_json.py
# 選択: 1 (マッチング失敗プール一覧表示)
```

### 特定のプールを解決済みマーク
```bash
python3 manual_mapping_manager_json.py
# 選択: 4
# プール名: 解決済みのプール名
```

## 📊 JSONファイル形式

### 人力対応表
```json
{
  "プール名": {
    "factory_id": "factory-id",
    "description": "説明",
    "created_at": "2025-09-29T12:00:00+09:00",
    "created_by": "manual",
    "status": "active"
  }
}
```

### 失敗プール記録
```json
{
  "プール名": {
    "token_symbols": ["TOKEN1", "TOKEN2"],
    "first_seen": "2025-09-29T12:00:00+09:00",
    "last_seen": "2025-09-29T12:00:00+09:00",
    "failure_count": 1,
    "status": "pending"
  }
}
```

## ⚡ 重要なポイント

- **定期実行は継続**: システムを停止せずにファイル更新可能
- **即座に反映**: 次回のマッチング処理から新しい設定が使用される
- **バックアップ推奨**: 更新前にファイルのコピーを作成

## 🛠️ トラブルシューティング

### JSON構文エラー
```bash
python3 -m json.tool /home/ubuntu/convex-scraper/manual_pool_mapping.json
```

### ログ確認
```bash
# 人力対応表マッチングの成功ログ
grep "人力対応表マッチング成功" /home/ubuntu/convex-scraper/logs/convex_complete.log

# 失敗プールの記録ログ
grep "マッチング失敗プールを記録" /home/ubuntu/convex-scraper/logs/convex_complete.log
```

### システム再起動（必要な場合のみ）
```bash
sudo systemctl restart convex-scraper
```

## 📈 現在の状況

- **自動マッチング成功率**: 約50%（137/273件）
- **システム状態**: 正常動作中
- **更新方法**: リアルタイム（ファイル保存後即反映）

---

**💡 ヒント**: 失敗回数の多いプールから優先的に人力対応表に追加すると効率的です！
