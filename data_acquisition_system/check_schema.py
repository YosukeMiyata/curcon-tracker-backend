
import boto3
from pprint import pprint
from dotenv import load_dotenv
import os
from pathlib import Path

# .envファイルを読み込み
env_path = Path("/home/ubuntu/convex-scraper/.env")
load_dotenv(dotenv_path=env_path)

def check_schema():
    try:
        # リージョンも明示的に指定
        region = os.getenv('AWS_DEFAULT_REGION', 'ap-northeast-1')
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table('ConvexPoolOHLCDaily')
        print(f"Table: {table.table_name}")
        print("Key Schema:")
        pprint(table.key_schema)
        print("\nAttribute Definitions:")
        pprint(table.attribute_definitions)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_schema()
