#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IQA Model Benchmark - 对比 NIMA vs MUSIQ-AVA vs NIMA-KonIQ 性能
测试推理时间和评分差异
"""

import time
import os
import pyiqa
import torch
from PIL import Image
import glob
import traceback


def resize_for_model(img_path: str, max_size: int = 1024) -> torch.Tensor:
    """
    缩放图片以适应模型内存限制
    MUSIQ 的 Attention 机制对大图非常消耗内存
    """
    img = Image.open(img_path).convert('RGB')
    w, h = img.size
    
    # 如果图片太大，缩放到 max_size
    if max(w, h) > max_size:
        scale = max_size / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # 转换为 tensor
    import torchvision.transforms as T
    transform = T.ToTensor()
    return transform(img).unsqueeze(0)


def test_model(model_name: str, model, test_files: list, device: str, use_resize: bool = False, max_size: int = 1024):
    """测试单个模型的性能"""
    scores = []
    times = []
    
    for i, img_path in enumerate(test_files, 1):
        try:
            start = time.time()
            
            if use_resize:
                # 对于 MUSIQ，需要缩放图片
                img_tensor = resize_for_model(img_path, max_size).to(device)
                score = model(img_tensor).item()
            else:
                score = model(img_path).item()
            
            elapsed = time.time() - start
            scores.append(score)
            times.append(elapsed)
            print(f"  [{i}/{len(test_files)}] {os.path.basename(img_path)}: {score:.3f} ({elapsed*1000:.0f}ms)")
        except Exception as e:
            print(f"  [{i}/{len(test_files)}] {os.path.basename(img_path)}: ❌ 错误 - {str(e)[:50]}")
            scores.append(None)
            times.append(None)
    
    valid_times = [t for t in times if t is not None]
    valid_scores = [s for s in scores if s is not None]
    
    avg_time = sum(valid_times) / len(valid_times) if valid_times else 0
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    
    return {
        'scores': scores,
        'times': times,
        'avg_time': avg_time,
        'avg_score': avg_score,
        'success_rate': len(valid_scores) / len(test_files)
    }


def benchmark_models(image_dir: str, num_images: int = 10):
    """
    对比测试 NIMA, MUSIQ-AVA 和 NIMA-KonIQ 模型
    """
    device = 'mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"🖥️  使用设备: {device}")
    
    # 收集测试图片
    jpg_files = glob.glob(os.path.join(image_dir, "*.jpg")) + \
                glob.glob(os.path.join(image_dir, "*.jpeg")) + \
                glob.glob(os.path.join(image_dir, "*.JPG"))
    
    if not jpg_files:
        print(f"❌ 未找到测试图片，请检查目录: {image_dir}")
        return
    
    test_files = jpg_files[:num_images]
    print(f"📁 测试图片: {len(test_files)} 张")
    
    for f in test_files:
        img = Image.open(f)
        print(f"   - {os.path.basename(f)}: {img.size[0]}x{img.size[1]}")
    print()
    
    results = {}
    
    # ==========================================
    # 测试 1: NIMA (当前使用 - InceptionV2 backbone)
    # ==========================================
    print("=" * 60)
    print("📊 模型 1: NIMA (InceptionV2 backbone) - 你目前使用的")
    print("=" * 60)
    
    load_start = time.time()
    nima_model = pyiqa.create_metric('nima', device=device)
    nima_load_time = time.time() - load_start
    print(f"⏱️  模型加载时间: {nima_load_time:.2f}s")
    
    results['nima'] = test_model('nima', nima_model, test_files, device)
    results['nima']['load_time'] = nima_load_time
    
    print(f"\n🎯 NIMA 平均推理时间: {results['nima']['avg_time']*1000:.0f}ms")
    print(f"🎯 NIMA 平均分数: {results['nima']['avg_score']:.3f}")
    
    del nima_model
    if device == 'mps':
        torch.mps.empty_cache()
    
    # ==========================================
    # 测试 2: NIMA-KonIQ (技术质量评估)
    # ==========================================
    print("\n" + "=" * 60)
    print("📊 模型 2: NIMA-KonIQ (技术质量评估 - InceptionV2)")
    print("=" * 60)
    
    load_start = time.time()
    koniq_model = pyiqa.create_metric('nima-koniq', device=device)
    koniq_load_time = time.time() - load_start
    print(f"⏱️  模型加载时间: {koniq_load_time:.2f}s")
    
    results['nima-koniq'] = test_model('nima-koniq', koniq_model, test_files, device)
    results['nima-koniq']['load_time'] = koniq_load_time
    
    print(f"\n🎯 NIMA-KonIQ 平均推理时间: {results['nima-koniq']['avg_time']*1000:.0f}ms")
    print(f"🎯 NIMA-KonIQ 平均分数: {results['nima-koniq']['avg_score']:.3f}")
    
    del koniq_model
    if device == 'mps':
        torch.mps.empty_cache()
    
    # ==========================================
    # 测试 3: MUSIQ-AVA (多尺度 Transformer) - 需要缩放
    # ==========================================
    print("\n" + "=" * 60)
    print("📊 模型 3: MUSIQ-AVA (Multi-scale Transformer)")
    print("⚠️  注意: 对高分辨率图片需要缩放 (max 1024px)")
    print("=" * 60)
    
    load_start = time.time()
    musiq_model = pyiqa.create_metric('musiq-ava', device=device)
    musiq_load_time = time.time() - load_start
    print(f"⏱️  模型加载时间: {musiq_load_time:.2f}s")
    
    results['musiq-ava'] = test_model('musiq-ava', musiq_model, test_files, device, use_resize=True, max_size=1024)
    results['musiq-ava']['load_time'] = musiq_load_time
    
    print(f"\n🎯 MUSIQ-AVA 平均推理时间: {results['musiq-ava']['avg_time']*1000:.0f}ms")
    print(f"🎯 MUSIQ-AVA 平均分数: {results['musiq-ava']['avg_score']:.3f}")
    
    del musiq_model
    if device == 'mps':
        torch.mps.empty_cache()
    
    # ==========================================
    # 对比总结
    # ==========================================
    print("\n" + "=" * 60)
    print("📈 性能对比总结")
    print("=" * 60)
    
    nima_time = results['nima']['avg_time'] * 1000
    koniq_time = results['nima-koniq']['avg_time'] * 1000
    musiq_time = results['musiq-ava']['avg_time'] * 1000
    
    print(f"""
┌───────────────────┬─────────────┬─────────────┬─────────────┐
│ 指标              │ NIMA (AVA)  │ NIMA-KonIQ  │ MUSIQ-AVA   │
├───────────────────┼─────────────┼─────────────┼─────────────┤
│ 模型加载时间      │ {results['nima']['load_time']:>8.2f}s   │ {results['nima-koniq']['load_time']:>8.2f}s   │ {results['musiq-ava']['load_time']:>8.2f}s   │
│ 平均推理时间      │ {nima_time:>8.0f}ms  │ {koniq_time:>8.0f}ms  │ {musiq_time:>8.0f}ms  │
│ 平均分数          │ {results['nima']['avg_score']:>8.3f}    │ {results['nima-koniq']['avg_score']:>8.3f}    │ {results['musiq-ava']['avg_score']:>8.3f}    │
│ 成功率            │ {results['nima']['success_rate']*100:>7.0f}%   │ {results['nima-koniq']['success_rate']*100:>7.0f}%   │ {results['musiq-ava']['success_rate']*100:>7.0f}%   │
├───────────────────┼─────────────┼─────────────┼─────────────┤
│ 评估维度          │ 美学质量    │ 技术失真    │ 美学质量    │
│ 架构              │ CNN/Incep   │ CNN/Incep   │ Transformer │
│ 输入需求          │ 原图        │ 原图        │ 需缩放      │
└───────────────────┴─────────────┴─────────────┴─────────────┘
""")
    
    # 建议
    print("💡 建议:")
    if musiq_time > nima_time * 2:
        print(f"  ⚠️  MUSIQ-AVA 比 NIMA 慢 {musiq_time/nima_time:.1f}x，需要缩放高分辨率图片")
        print(f"  ✅ 建议保持 NIMA (AVA) 作为美学评估")
    else:
        print(f"  ✅ MUSIQ-AVA 性能可接受，可考虑切换")
    
    if koniq_time < nima_time * 1.5:
        print(f"  💡 NIMA-KonIQ 可替代 BRISQUE 评估技术失真 (同架构，更准确)")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python benchmark_iqa_models.py <图片目录> [测试数量]")
        print("示例: python benchmark_iqa_models.py /path/to/bird/photos 10")
        sys.exit(1)
    
    image_dir = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    benchmark_models(image_dir, num_images)
