#!/bin/bash
# 依存関係がインストールされたPythonでスクリプトを実行する
# 使い方: ./scripts/run_with_deps.sh python data_acquisition_system/token_price_tracker/token_price_tracker.py --init

cd "$(dirname "$0")/.."

for py in python3.9 python3 python; do
  if command -v $py &>/dev/null && $py -c "import requests" 2>/dev/null; then
    exec $py "$@"
    exit 0
  fi
done

echo "❌ エラー: requests がインストールされていません。"
echo "以下のいずれかを実行してください:"
echo "  pip install -r requirements.txt"
echo "  または（token_price_tracker のみ）:"
echo "  pip install -r requirements-token-tracker.txt"
exit 1
