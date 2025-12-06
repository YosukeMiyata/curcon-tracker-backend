#!/usr/bin/env python3
"""
更新されたデータを確認するスクリプト
"""
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
table = dynamodb.Table('ConvexPoolHistory')

# USPD+USDCのデータを確認
pool_id = 'uspd_usdc'
response = table.query(
    KeyConditionExpression=Key('pool_id').eq(pool_id),
    Limit=1
)

if response['Items']:
    item = response['Items'][0]
    print(f"✅ {pool_id}のfactory_id: {item.get('factory_id', 'なし')}")
else:
    print(f"❌ {pool_id}のデータが見つかりません")

# sfrxUSD+frxUSDのデータを確認
pool_id2 = 'sfrxusd_frxusd'
response2 = table.query(
    KeyConditionExpression=Key('pool_id').eq(pool_id2),
    Limit=1
)

if response2['Items']:
    item2 = response2['Items'][0]
    print(f"✅ {pool_id2}のfactory_id: {item2.get('factory_id', 'なし')}")
else:
    print(f"❌ {pool_id2}のデータが見つかりません")
