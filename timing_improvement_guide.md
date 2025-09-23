# 定期実行の時間精度改善ガイド

## 問題の原因

従来の`schedule`ライブラリを使用した定期実行では、以下の問題により時間がずれていました：

1. **累積誤差**: 各実行に時間がかかると、その分だけ次回実行が遅れる
2. **非効率な待機**: `time.sleep(60)`による1分間隔チェックでCPUリソースを無駄に消費
3. **スケジューリングの制限**: `schedule`ライブラリは実行時間の累積を考慮しない設計

## 改善されたスケジューリング方式

### 新しいアプローチ

```python
# 正確な時間間隔での実行ループ
interval_seconds = interval_minutes * 60
next_execution_time = datetime.now() + timedelta(seconds=interval_seconds)

while True:
    now = datetime.now()
    
    # 実行時間になったら実行
    if now >= next_execution_time:
        execution_start = datetime.now()
        self.run_job()
        execution_duration = (datetime.now() - execution_start).total_seconds()
        
        # 次回実行時間を正確に計算（実行時間を考慮しない）
        next_execution_time = next_execution_time + timedelta(seconds=interval_seconds)
        
        # 実行時間をログに記録
        self.logger.info(f"⏱️ 実行時間: {execution_duration:.1f}秒")
        self.logger.info(f"⏰ 次回実行予定: {next_execution_time}")
    
    time.sleep(1)  # 1秒間隔でチェック
```

### 主な改善点

1. **固定間隔実行**: 実行時間に関係なく、常に指定された間隔で実行
2. **効率的な待機**: 1秒間隔でのチェックでCPU使用率を削減
3. **実行時間の可視化**: 各実行の所要時間をログに記録
4. **次回実行時刻の表示**: 正確な次回実行予定時刻を表示

## 使用方法

### EC2環境での使用

```bash
# 改善されたスクリプトを実行
python convex_ec2_improved.py
```

### Google Colabでの使用

```python
# 60分間隔で実行
start_jst_production_with_prices_60min()

# 15分間隔で実行
start_jst_production_with_prices_15min()
```

## 期待される効果

- **時間精度**: 累積誤差なしで正確な60分間隔実行
- **リソース効率**: CPU使用率の削減
- **可視性**: 実行時間と次回実行時刻の明確な表示
- **安定性**: 長時間実行でも時間のずれが発生しない

## 監視方法

実行中に以下の情報が表示されます：

```
⏱️ 実行時間: 45.2秒
⏰ 次回実行予定: 2024-01-15 14:00:00 JST

📊 実行統計 (2024-01-15 13:30:00 JST):
   経過時間: 2:30:00
   成功: 150回
   エラー: 2回
   成功率: 98.7%
   次回実行予定: 2024-01-15 14:00:00 JST
```

これにより、定期実行の時間精度が大幅に改善され、正確な60分間隔での実行が可能になります。
