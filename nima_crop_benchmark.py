#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量测试 NIMA 对全图 vs 裁剪后鸟区域的分数差异
支持 RAW 文件自动转换
"""

import time
import os
import cv2
import torch
import pyiqa
import glob
import random
import statistics
import tempfile


def batch_test_nima(image_dir: str, num_images: int = 50):
    """批量对比全图和裁剪后的NIMA分数"""
    
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"🖥️  设备: {device}")
    
    # 收集图片 (支持 JPG 和 RAW)
    jpg_files = glob.glob(os.path.join(image_dir, "*.jpg")) + \
                glob.glob(os.path.join(image_dir, "*.jpeg")) + \
                glob.glob(os.path.join(image_dir, "*.JPG")) + \
                glob.glob(os.path.join(image_dir, "*.JPEG"))
    
    raw_files = glob.glob(os.path.join(image_dir, "*.NEF")) + \
                glob.glob(os.path.join(image_dir, "*.nef")) + \
                glob.glob(os.path.join(image_dir, "*.CR2")) + \
                glob.glob(os.path.join(image_dir, "*.cr2")) + \
                glob.glob(os.path.join(image_dir, "*.ARW")) + \
                glob.glob(os.path.join(image_dir, "*.arw"))
    
    all_files = jpg_files + raw_files
    
    if not all_files:
        print(f"❌ 未找到图片: {image_dir}")
        return
    
    # 随机选择
    if len(all_files) > num_images:
        test_files = random.sample(all_files, num_images)
    else:
        test_files = all_files
    
    print(f"📁 测试目录: {image_dir}")
    print(f"📷 共找到: {len(jpg_files)} JPG + {len(raw_files)} RAW")
    print(f"🎯 测试样本: {len(test_files)} 张\n")
    
    # 加载模型
    print("🔄 加载 NIMA 模型...")
    nima = pyiqa.create_metric('nima', device=device)
    
    print("🔄 加载 YOLO 模型...")
    from ai_model import load_yolo_model
    yolo = load_yolo_model()
    
    # RAW 转换工具
    from find_bird_util import raw_to_jpeg
    
    # 收集结果
    results = []
    no_bird_count = 0
    convert_errors = 0
    
    total_start = time.time()
    temp_jpgs = []  # 记录临时生成的JPG以便清理
    
    for i, img_path in enumerate(test_files, 1):
        filename = os.path.basename(img_path)
        print(f"[{i}/{len(test_files)}] {filename}...", end=" ", flush=True)
        
        try:
            # 如果是 RAW，先转换
            ext = os.path.splitext(img_path)[1].lower()
            if ext in ['.nef', '.cr2', '.arw', '.raf', '.orf']:
                jpg_path = img_path.rsplit('.', 1)[0] + '.jpg'
                if not os.path.exists(jpg_path):
                    try:
                        raw_to_jpeg(img_path)
                        temp_jpgs.append(jpg_path)
                    except Exception as e:
                        print(f"RAW转换失败: {str(e)[:20]}")
                        convert_errors += 1
                        continue
                actual_path = jpg_path
            else:
                actual_path = img_path
            
            img = cv2.imread(actual_path)
            if img is None:
                print("❌ 无法读取")
                continue
            
            h, w = img.shape[:2]
            
            # 全图 NIMA
            t1 = time.time()
            full_score = nima(actual_path).item()
            full_time = (time.time() - t1) * 1000
            
            # YOLO 检测
            yolo_results = yolo(actual_path, verbose=False)
            
            if len(yolo_results[0].boxes) == 0:
                print(f"无鸟 (全图: {full_score:.2f})")
                no_bird_count += 1
                continue
            
            # 获取最大置信度的框
            boxes = yolo_results[0].boxes
            best_idx = boxes.conf.argmax().item()
            box = boxes.xyxy[best_idx].cpu().numpy().astype(int)
            conf = boxes.conf[best_idx].item()
            x1, y1, x2, y2 = box
            
            # 裁剪
            bird_crop = img[y1:y2, x1:x2]
            crop_path = "/tmp/bird_crop_test.jpg"
            cv2.imwrite(crop_path, bird_crop)
            
            # 裁剪后 NIMA
            t2 = time.time()
            crop_score = nima(crop_path).item()
            crop_time = (time.time() - t2) * 1000
            
            diff = crop_score - full_score
            speedup = full_time / crop_time if crop_time > 0 else 0
            
            results.append({
                'filename': filename,
                'full_score': full_score,
                'crop_score': crop_score,
                'diff': diff,
                'full_time': full_time,
                'crop_time': crop_time,
                'speedup': speedup,
                'img_size': f"{w}x{h}",
                'crop_size': f"{x2-x1}x{y2-y1}",
                'conf': conf
            })
            
            print(f"全图: {full_score:.2f} → 裁剪: {crop_score:.2f} ({diff:+.2f}) | {speedup:.1f}x")
            
            os.remove(crop_path)
            
        except Exception as e:
            print(f"❌ 错误: {str(e)[:30]}")
    
    total_time = time.time() - total_start
    
    # 清理临时JPG
    print(f"\n🧹 清理 {len(temp_jpgs)} 个临时JPG...")
    for jpg_path in temp_jpgs:
        try:
            if os.path.exists(jpg_path):
                os.remove(jpg_path)
        except:
            pass
    
    # 统计汇总
    if not results:
        print("\n❌ 无有效结果")
        return
    
    print("\n" + "="*70)
    print("📊 批量测试结果汇总")
    print("="*70)
    
    full_scores = [r['full_score'] for r in results]
    crop_scores = [r['crop_score'] for r in results]
    diffs = [r['diff'] for r in results]
    full_times = [r['full_time'] for r in results]
    crop_times = [r['crop_time'] for r in results]
    speedups = [r['speedup'] for r in results]
    
    stdev_full = statistics.stdev(full_scores) if len(full_scores) > 1 else 0
    stdev_crop = statistics.stdev(crop_scores) if len(crop_scores) > 1 else 0
    stdev_diff = statistics.stdev(diffs) if len(diffs) > 1 else 0
    stdev_full_time = statistics.stdev(full_times) if len(full_times) > 1 else 0
    stdev_crop_time = statistics.stdev(crop_times) if len(crop_times) > 1 else 0
    
    print(f"""
测试样本: {len(results)} 张有效 / {len(test_files)} 张总计
未检测到鸟: {no_bird_count} | RAW转换失败: {convert_errors}
总耗时: {total_time:.1f}s

┌───────────────────┬─────────────┬─────────────┐
│ 指标              │ 全图        │ 裁剪后      │
├───────────────────┼─────────────┼─────────────┤
│ 平均 NIMA 分数    │ {statistics.mean(full_scores):>8.3f}    │ {statistics.mean(crop_scores):>8.3f}    │
│ 分数标准差        │ {stdev_full:>8.3f}    │ {stdev_crop:>8.3f}    │
│ 最高分            │ {max(full_scores):>8.3f}    │ {max(crop_scores):>8.3f}    │
│ 最低分            │ {min(full_scores):>8.3f}    │ {min(crop_scores):>8.3f}    │
├───────────────────┼─────────────┼─────────────┤
│ 平均推理时间      │ {statistics.mean(full_times):>8.0f}ms  │ {statistics.mean(crop_times):>8.0f}ms  │
│ 推理时间标准差    │ {stdev_full_time:>8.0f}ms  │ {stdev_crop_time:>8.0f}ms  │
└───────────────────┴─────────────┴─────────────┘

📈 分数差异分析 (裁剪 - 全图):
   平均差异: {statistics.mean(diffs):+.3f}
   标准差: {stdev_diff:.3f}
   最大增加: {max(diffs):+.3f}
   最大减少: {min(diffs):+.3f}
   裁剪分高于全图的比例: {sum(1 for d in diffs if d > 0)/len(diffs)*100:.1f}%

⚡ 加速统计:
   平均加速: {statistics.mean(speedups):.1f}x
   最大加速: {max(speedups):.1f}x
   最小加速: {min(speedups):.1f}x
""")
    
    # 显示分数差异最大的样本
    print("📋 分数差异最大的5个样本 (裁剪 vs 全图):")
    sorted_by_diff = sorted(results, key=lambda x: abs(x['diff']), reverse=True)[:5]
    for r in sorted_by_diff:
        print(f"   {r['filename']}: {r['full_score']:.2f} → {r['crop_score']:.2f} ({r['diff']:+.2f})")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python nima_crop_benchmark.py <图片目录> [测试数量]")
        print("示例: python nima_crop_benchmark.py /path/to/photos 50")
        sys.exit(1)
    
    image_dir = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    batch_test_nima(image_dir, num_images)
