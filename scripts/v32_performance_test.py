#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3.2 性能测试 - 随机选取 50 张照片
"""

import os
import sys
import time
import random
import shutil

# 添加项目路径
sys.path.insert(0, '/Users/jameszhenyu/PycharmProjects/SuperPicky_SandBox')

from core.photo_processor import PhotoProcessor, ProcessingSettings, ProcessingCallbacks


def main():
    test_dir = '/Users/jameszhenyu/Desktop/2025-08-14'
    temp_test_dir = '/tmp/superpicky_v32_test'
    
    # 获取所有 NEF 文件
    all_nef = [f for f in os.listdir(test_dir) if f.lower().endswith('.nef')]
    print(f"📁 目录共有 {len(all_nef)} 个 NEF 文件")
    
    # 随机选取 50 个
    sample_size = min(50, len(all_nef))
    sample_files = random.sample(all_nef, sample_size)
    print(f"🎲 随机选取 {sample_size} 个文件进行测试\n")
    
    # 创建临时测试目录
    if os.path.exists(temp_test_dir):
        shutil.rmtree(temp_test_dir)
    os.makedirs(temp_test_dir)
    
    # 复制文件到临时目录（使用硬链接节省空间）
    print("📋 复制文件到临时目录...")
    for f in sample_files:
        src = os.path.join(test_dir, f)
        dst = os.path.join(temp_test_dir, f)
        os.link(src, dst)  # 硬链接，不占用额外空间
    print(f"✅ 已复制 {len(sample_files)} 个文件\n")
    
    # 创建处理器
    settings = ProcessingSettings(
        ai_confidence=50,
        sharpness_threshold=500,
        nima_threshold=4.8,
        save_crop=False,
        normalization_mode='log_compression'
    )
    
    logs = []
    def log_callback(msg, level="info"):
        logs.append(msg)
        print(msg)
    
    def progress_callback(value):
        pass
    
    callbacks = ProcessingCallbacks(
        log=log_callback,
        progress=progress_callback
    )
    
    processor = PhotoProcessor(
        dir_path=temp_test_dir,
        settings=settings,
        callbacks=callbacks
    )
    
    # 开始处理
    print("=" * 60)
    print("🚀 开始处理...")
    print("=" * 60)
    
    start_time = time.time()
    result = processor.process(organize_files=False, cleanup_temp=False)
    total_time = time.time() - start_time
    
    # 输出统计
    stats = result.stats
    print("\n" + "=" * 60)
    print("📊 处理结果统计")
    print("=" * 60)
    print(f"   总文件数: {stats['total']}")
    print(f"   ⭐⭐⭐ 3星优选: {stats['star_3']}")
    print(f"   ⭐⭐   2星良好: {stats['star_2']}")
    print(f"   ⭐     1星普通: {stats['star_1']}")
    print(f"   0星问题照片: {stats['star_0']}")
    print(f"   ❌ 无鸟照片: {stats['no_bird']}")
    print()
    print(f"⏱️  总耗时: {total_time:.1f}s")
    print(f"⏱️  平均耗时: {total_time/sample_size*1000:.0f}ms/张")
    
    # 读取 CSV 分析
    csv_path = os.path.join(temp_test_dir, "_tmp", "report.csv")
    if os.path.exists(csv_path):
        import csv
        print("\n" + "=" * 60)
        print("📈 详细数据分析")
        print("=" * 60)
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # 统计有鸟照片
        bird_rows = [r for r in rows if r['has_bird'] == 'yes']
        print(f"\n检测到鸟: {len(bird_rows)} 张")
        
        if bird_rows:
            # NIMA 分析
            nima_values = []
            for r in bird_rows:
                try:
                    if r['nima_score'] != '-':
                        nima_values.append(float(r['nima_score']))
                except:
                    pass
            
            if nima_values:
                print(f"\nNIMA 评分分布 (共{len(nima_values)}张):")
                print(f"   最高: {max(nima_values):.2f}")
                print(f"   最低: {min(nima_values):.2f}")
                print(f"   平均: {sum(nima_values)/len(nima_values):.2f}")
            
            # Head Sharpness 分析
            sharpness_values = []
            for r in bird_rows:
                try:
                    if r['head_sharpness'] != '-':
                        sharpness_values.append(float(r['head_sharpness']))
                except:
                    pass
            
            if sharpness_values:
                print(f"\n头部锐度分布 (共{len(sharpness_values)}张):")
                print(f"   最高: {max(sharpness_values):.0f}")
                print(f"   最低: {min(sharpness_values):.0f}")
                print(f"   平均: {sum(sharpness_values)/len(sharpness_values):.0f}")
            
            # 眼睛可见性
            visible_eye_count = sum(1 for r in bird_rows if r.get('has_visible_eye') == 'yes')
            hidden_eye_count = len(bird_rows) - visible_eye_count
            print(f"\n眼睛可见性:")
            print(f"   眼睛可见: {visible_eye_count} 张")
            print(f"   双眼不可见: {hidden_eye_count} 张")
    
    # 清理
    print("\n🗑️  清理临时目录...")
    shutil.rmtree(temp_test_dir)
    print("✅ 测试完成!")


if __name__ == "__main__":
    main()
