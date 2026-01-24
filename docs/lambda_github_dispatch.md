## Lambda + EventBridge で GitHub Actions を正確に起動する手順

この手順は **EventBridge の cron（JST指定） → Lambda → GitHub Actions workflow_dispatch** の構成です。

---

## 1. Lambda 関数コード（Python・1本化）

EventBridge から `workflow_file` を受け取り、1つのLambdaで分岐します。

```python
import json
import os
import urllib.request


def handler(event, context):
    owner = os.environ["OWNER"]
    repo = os.environ["REPO"]
    ref = os.environ.get("REF", "main")
    token = os.environ["GITHUB_TOKEN"]

    workflows = event.get("workflows")
    if not workflows:
        return {
            "statusCode": 400,
            "body": "Missing workflows in event input"
        }
    results = []
    for workflow_file in workflows:
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches"
        payload = json.dumps({"ref": ref}).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"token {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "lambda-github-dispatch")

        with urllib.request.urlopen(req, timeout=10) as res:
            results.append(f"{workflow_file}:{res.status}")

    return {
        "statusCode": 200,
        "body": f"Dispatched {', '.join(results)} on {ref}"
    }
```

---

## 2. Lambda 環境変数

Lambda の「設定 → 環境変数」に以下を登録：

| 変数名 | 例 |
|---|---|
| `GITHUB_TOKEN` | (作成したPAT) |
| `OWNER` | `YosukeMiyata` |
| `REPO` | `curcon-tracker-backend` |
| `REF` | `main` |

---

## 3. EventBridge ルール作成（JST指定）

EventBridge → ルール作成：

### 例1: 毎日00:00に「日次（Token OHLC）→毎時30分」を**順番に起動**
> 同時実行を避けるため、**1つのルールで順番にdispatch**します。

- スケジュール: `cron(0 0 * * ? *)`
- タイムゾーン: `Asia/Tokyo`
- ターゲット入力（定数 JSON）:
  ```json
  {
    "workflows": [
      "token_ohlc_aggregator.yml",
      "token_price_tracker.yml"
    ]
  }
  ```

### 例2: 毎日00:30に「日次（Convex）→毎時00分」を**順番に起動**
- スケジュール: `cron(30 0 * * ? *)`
- タイムゾーン: `Asia/Tokyo`
- ターゲット入力（定数 JSON）:
  ```json
  {
    "workflows": [
      "convex_daily_aggregation.yml",
      "convex_scraper.yml"
    ]
  }
  ```

### 例3: 毎時00分（※0時30分以外）
> 0時30分は例2で処理済みのため、毎時00分のルールから **0時30分を除外**します。

- スケジュール: `cron(0 1-23 * * ? *)`
- タイムゾーン: `Asia/Tokyo`
- ターゲット入力（定数 JSON）:
  ```json
  { "workflows": ["convex_scraper.yml"] }
  ```

### 例4: 毎時30分（※0時以外）
> 0時は例1で処理済みのため、毎時30分のルールから **0時を除外**します。

- スケジュール: `cron(30 1-23 * * ? *)`
- タイムゾーン: `Asia/Tokyo`
- ターゲット入力（定数 JSON）:
  ```json
  { "workflows": ["token_price_tracker.yml"] }
  ```

---

## 4. 1本化構成のポイント

- Lambdaは **1本だけ** でOK
- EventBridge側の「入力JSON」で `workflows` を切り替える
- 0時/0時30分は **日次 → 毎時** を順番にdispatch

---

## 5. 動作確認

Lambda の「テスト」実行で：
```
Dispatched convex_scraper.yml on main
```
が返れば OK。

GitHub Actions で **workflow_dispatch 由来の実行ログ**が出ます。

---

## 注意点

- PAT は **必ず Secrets として管理**
- 有効期限切れで止まるため、定期的に更新
- GitHub API は呼び出し頻度が高いと制限される（今回の頻度なら問題なし）
