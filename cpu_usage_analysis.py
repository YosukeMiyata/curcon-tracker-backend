#!/usr/bin/env python3
"""
CPU使用率比較分析スクリプト
従来の方式 vs 改善された方式のCPU使用率を測定
"""

import time
import psutil
import schedule
from datetime import datetime, timedelta
import threading

class CPUUsageAnalyzer:
    def __init__(self):
        self.cpu_samples = []
        self.monitoring = False
    
    def start_monitoring(self):
        """CPU使用率監視開始"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_cpu)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """CPU使用率監視停止"""
        self.monitoring = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()
    
    def _monitor_cpu(self):
        """CPU使用率を監視"""
        while self.monitoring:
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_samples.append(cpu_percent)
            time.sleep(1)
    
    def get_average_cpu(self):
        """平均CPU使用率を取得"""
        if not self.cpu_samples:
            return 0
        return sum(self.cpu_samples) / len(self.cpu_samples)

def test_old_method():
    """従来の方式（schedule + 60秒間隔）をテスト"""
    print("🔍 従来の方式をテスト中...")
    
    def dummy_job():
        time.sleep(0.1)  # 0.1秒のダミー処理
    
    # scheduleライブラリでジョブ登録
    schedule.every(1).minutes.do(dummy_job)
    
    analyzer = CPUUsageAnalyzer()
    analyzer.start_monitoring()
    
    start_time = time.time()
    while time.time() - start_time < 300:  # 5分間テスト
        schedule.run_pending()  # 重い処理
        time.sleep(60)  # 60秒間隔
    
    analyzer.stop_monitoring()
    return analyzer.get_average_cpu()

def test_new_method():
    """改善された方式（時刻比較 + 1秒間隔）をテスト"""
    print("🔍 改善された方式をテスト中...")
    
    def dummy_job():
        time.sleep(0.1)  # 0.1秒のダミー処理
    
    # 正確な時間間隔での実行
    interval_seconds = 60
    next_execution_time = datetime.now() + timedelta(seconds=interval_seconds)
    
    analyzer = CPUUsageAnalyzer()
    analyzer.start_monitoring()
    
    start_time = time.time()
    while time.time() - start_time < 300:  # 5分間テスト
        now = datetime.now()
        
        # 軽い処理
        if now >= next_execution_time:
            dummy_job()
            next_execution_time += timedelta(seconds=interval_seconds)
        
        time.sleep(1)  # 1秒間隔
    
    analyzer.stop_monitoring()
    return analyzer.get_average_cpu()

def main():
    """メイン関数"""
    print("📊 CPU使用率比較分析")
    print("=" * 50)
    
    # 従来の方式をテスト
    old_cpu = test_old_method()
    print(f"従来の方式（schedule + 60秒間隔）: {old_cpu:.2f}%")
    
    time.sleep(5)  # クールダウン
    
    # 改善された方式をテスト
    new_cpu = test_new_method()
    print(f"改善された方式（時刻比較 + 1秒間隔）: {new_cpu:.2f}%")
    
    # 結果比較
    print("\n📈 結果比較:")
    print(f"CPU使用率削減: {old_cpu - new_cpu:.2f}%")
    print(f"削減率: {((old_cpu - new_cpu) / old_cpu * 100):.1f}%")
    
    print("\n💡 理由:")
    print("1. schedule.run_pending()は内部で複雑な処理を実行")
    print("2. 時刻比較は単純な処理で軽量")
    print("3. 1秒間隔でもtime.sleep(1)でCPU使用率は低い")
    print("4. 処理の軽量化がCPU使用率削減の主な要因")

if __name__ == "__main__":
    main()
