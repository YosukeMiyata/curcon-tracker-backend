# セル2: AWS認証情報設定
from google.colab import userdata
import os

os.environ['AWS_ACCESS_KEY_ID'] = userdata.get('AWS_ACCESS_KEY_ID')
os.environ['AWS_SECRET_ACCESS_KEY'] = userdata.get('AWS_SECRET_ACCESS_KEY')
os.environ['AWS_DEFAULT_REGION'] = userdata.get('AWS_DEFAULT_REGION')

print("✅ AWS認証情報設定が完了しました")

# AlphaVantage APIキーの設定
try:
    alphavantage_key = userdata.get('ALPHAVANTAGE_API_KEY')
    if alphavantage_key:
        os.environ['ALPHAVANTAGE_API_KEY'] = alphavantage_key
        print("✅ AlphaVantage APIキーをColab Secretsから取得しました")
    else:
        print("⚠️ ALPHAVANTAGE_API_KEYがColab Secretsに設定されていません")
except Exception as e:
    print(f"❌ AlphaVantage APIキー設定エラー: {e}")