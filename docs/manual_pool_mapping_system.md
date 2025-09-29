# 人力対応表システム（Manual Pool Mapping System）

## 概要

マッチングが困難なプールに対して、人力でfactory_idを設定するシステムです。JSONファイルベースで運用され、定期実行を停止することなくリアルタイムで更新できます。

## システム構成

### ファイル構成
```
/home/ubuntu/convex-scraper/
├── manual_pool_mapping.json      # 人力対応表
├── failed_pool_matching.json     # マッチング失敗プール記録
└── manual_mapping_manager_json.py # 管理ツール
```

### マッチングロジックの流れ

```
1. 人力対応表チェック（最優先）
   ↓ マッチなし
2. 自動トークンベースマッチング
   ↓ マッチなし
3. マッチング失敗プールとして記録
```

## JSONファイル形式

### 人力対応表（manual_pool_mapping.json）

```json
{
  "FRAX+3Crv": {
    "factory_id": "factory-stable-ng-1",
    "description": "FRAXと3Crvの組み合わせプール",
    "created_at": "2025-09-29T12:00:00+09:00",
    "created_by": "manual",
    "status": "active"
  },
  "USDC+WBTC+WETH": {
    "factory_id": "factory-tricrypto-1",
    "description": "3トークン組み合わせプール",
    "created_at": "2025-09-29T12:00:00+09:00",
    "created_by": "manual",
    "status": "active",
    "valid_until": "2025-12-31T23:59:59+09:00"
  }
}
```

#### フィールド説明
- `factory_id`: Curve APIのプールID
- `description`: マッピングの説明
- `created_at`: 作成日時（ISO形式）
- `created_by`: 作成者
- `status`: ステータス（`active`, `inactive`）
- `valid_until`: 有効期限（任意）

### 失敗プール記録（failed_pool_matching.json）

```json
{
  "FRAX+FXB_20241231": {
    "token_symbols": ["FRAX", "FXB_20241231"],
    "first_seen": "2025-09-29T12:58:39.123456",
    "last_seen": "2025-09-29T12:58:39.123456",
    "failure_count": 1,
    "status": "pending"
  }
}
```

#### フィールド説明
- `token_symbols`: プール名から分割されたトークン配列
- `first_seen`: 初回発見日時
- `last_seen`: 最終発見日時
- `failure_count`: 失敗回数
- `status`: ステータス（`pending`, `resolved`, `ignored`）

## 更新方法

### 1. 管理ツールを使用（推奨）

```bash
# EC2に接続
ssh -i /Users/yousuke/.ssh/convex-keypair.pem ubuntu@54.64.254.201

# 管理ツール実行
cd /home/ubuntu/convex-scraper
python3 manual_mapping_manager_json.py
```

#### 管理ツールの機能
1. **マッチング失敗プール一覧表示**
2. **人力対応表一覧表示**
3. **人力対応表に追加**
4. **失敗プールを解決済みマーク**
5. **一括追加（JSON形式）**
6. **ファイルの場所を表示**

### 2. 直接ファイル編集

```bash
# 人力対応表を直接編集
nano /home/ubuntu/convex-scraper/manual_pool_mapping.json

# 失敗プールを確認
cat /home/ubuntu/convex-scraper/failed_pool_matching.json
```

### 3. ローカルからアップロード

```bash
# ローカルで編集後、EC2にアップロード
scp -i /Users/yousuke/.ssh/convex-keypair.pem manual_pool_mapping.json ubuntu@54.64.254.201:/home/ubuntu/convex-scraper/
```

### 4. プログラムからの更新

```python
import json
from datetime import datetime

# 人力対応表を読み込み
with open('/home/ubuntu/convex-scraper/manual_pool_mapping.json', 'r', encoding='utf-8') as f:
    mappings = json.load(f)

# 新しいマッピングを追加
mappings['新しいプール名'] = {
    'factory_id': 'factory-id',
    'description': '説明',
    'created_at': datetime.now().isoformat(),
    'created_by': 'manual',
    'status': 'active'
}

# ファイルに保存
with open('/home/ubuntu/convex-scraper/manual_pool_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(mappings, f, ensure_ascii=False, indent=2)
```

## マッチングロジックの詳細

### 1. 人力対応表チェック

```python
def _check_manual_mapping(self, pool_name, used_factory_ids):
    """人力対応表からfactory_idを検索"""
    # JSONファイルを読み込み
    # プール名で検索
    # 使用済みfactory_idをチェック
    # 有効期限をチェック
    # ステータスをチェック
    return factory_id or None
```

### 2. 自動トークンベースマッチング

```python
def find_factory_id_for_pool(self, pool_name, token_symbols, api_data, used_factory_ids):
    """トークンベースのマッチングでAPIデータのIDを特定"""
    # 1. 人力対応表チェック
    # 2. プールデータから検索
    # 3. Vaultデータから検索
    # 4. 失敗時は失敗プールテーブルに保存
```

### 3. トークン分割ロジック

#### 検索プール名の分割
```python
def _split_pool_name(self, pool_name):
    # "ETH+KP3R" → ["ETH", "KP3R"]
    tokens = pool_name.split('+')
    return [token.strip().upper() for token in tokens]
```

#### Convexプール名の分割
```python
def _split_convex_name(self, convex_name):
    # "Curve.fi Factory Crypto Pool: KP3R/ETH" → ["KP3R", "ETH"]
    # ノイズワード除去: curve, fi, factory, pool, crypto, stable, v2, v3, ng等
    tokens = re.split(r'[/\s\-:]+', convex_name)
    return [token.upper() for token in tokens if token and token.lower() not in skip_words]
```

### 4. マッチング判定

```python
def _tokens_match_improved(self, search_tokens, convex_tokens):
    """改善されたトークンマッチング"""
    # 検索トークンがすべてConvexトークンに含まれている必要がある
    convex_tokens_set = set(convex_tokens)
    for search_token in search_tokens:
        if search_token not in convex_tokens_set:
            return False
    return True
```

## 運用フロー

### 1. マッチング失敗の確認

```bash
# 失敗プール一覧を確認
python3 manual_mapping_manager_json.py
# 選択: 1 (マッチング失敗プール一覧表示)
```

### 2. 人力対応表への追加

```bash
# 管理ツールで追加
python3 manual_mapping_manager_json.py
# 選択: 3 (人力対応表に追加)
# プール名: FRAX+FXB_20241231
# factory_id: factory-stable-ng-44
# 説明: FRAX FXB 2024年12月31日満期債券
```

### 3. 解決済みマーク

```bash
# 失敗プールを解決済みとしてマーク
python3 manual_mapping_manager_json.py
# 選択: 4 (失敗プールを解決済みマーク)
# プール名: FRAX+FXB_20241231
```

### 4. 一括追加

```json
[
  {
    "pool_name": "FRAX+FXB_20241231",
    "factory_id": "factory-stable-ng-44",
    "description": "FRAX FXB 2024年12月31日満期債券"
  },
  {
    "pool_name": "USDC+WBTC+WETH",
    "factory_id": "factory-tricrypto-1",
    "description": "3トークン組み合わせプール"
  }
]
```

## 重要なポイント

### 定期実行との関係
- **定期実行は継続**: システムを停止する必要はありません
- **即座に反映**: ファイル更新後、次回のマッチング処理から反映
- **安全な更新**: ファイルの読み書きは排他的に行われる

### データの整合性
- **重複防止**: 同じfactory_idが複数のプールに割り当てられない
- **有効期限**: 設定可能な有効期限による自動無効化
- **ステータス管理**: active/inactiveによる柔軟な管理

### バックアップとバージョン管理
- **ファイルバックアップ**: 更新前にファイルのコピーを作成
- **Git管理**: JSONファイルをGitでバージョン管理可能
- **ロールバック**: 問題発生時の簡単な復旧

## トラブルシューティング

### よくある問題

#### 1. JSONファイルの構文エラー
```bash
# JSONの構文チェック
python3 -m json.tool /home/ubuntu/convex-scraper/manual_pool_mapping.json
```

#### 2. ファイルの権限問題
```bash
# ファイルの権限確認
ls -la /home/ubuntu/convex-scraper/*.json

# 権限修正（必要に応じて）
chmod 644 /home/ubuntu/convex-scraper/*.json
```

#### 3. マッチングが反映されない
- JSONファイルの構文を確認
- プール名の完全一致を確認
- ステータスが`active`であることを確認

### ログの確認

```bash
# 最新のログを確認
tail -f /home/ubuntu/convex-scraper/logs/convex_complete.log

# 人力対応表マッチングのログを確認
grep "人力対応表マッチング成功" /home/ubuntu/convex-scraper/logs/convex_complete.log
```

## パフォーマンス

### 現在の状況
- **自動マッチング成功率**: 約50%（137/273件）
- **人力対応表**: 任意の数追加可能
- **更新頻度**: リアルタイム（ファイル保存後即反映）

### 最適化のヒント
- **頻繁に失敗するプールを優先**: 失敗回数の多いプールから対応
- **類似プールのパターン把握**: 同じパターンのプールを一括対応
- **定期的な見直し**: 不要になったマッピングの削除

## 今後の拡張

### 予定されている機能
- **自動マッチング精度の向上**: より柔軟なマッチングロジック
- **Webインターフェース**: ブラウザでの管理画面
- **API連携**: 外部システムからの更新
- **統計・分析**: マッチング成功率の詳細分析

---

**最終更新**: 2025-09-29  
**バージョン**: 1.0  
**作成者**: Convex Finance Data Acquisition System
