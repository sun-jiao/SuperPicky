#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析 NIMA 分数差异最大的图片
生成全图 vs 裁剪对比图
"""

import os
import sys
# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import torch
import pyiqa
import numpy as np
from PIL import Image

# 准备测试的图片
test_cases = [
    # 分数下降最多的
    {"file": "_Z9W8663.NEF", "full": 6.19, "crop": 4.33, "diff": -1.86},
    {"file": "_Z9W8676.NEF", "full": 6.22, "crop": 4.67, "diff": -1.55},
    {"file": "_Z9W8659.NEF", "full": 6.12, "crop": 4.81, "diff": -1.31},
    # 分数上升最多的
    {"file": "_Z9W8853.NEF", "full": 5.45, "crop": 5.96, "diff": +0.51},
    {"file": "_Z9W8644.NEF", "full": 4.59, "crop": 5.08, "diff": +0.49},
    {"file": "_Z9W9305.NEF", "full": 5.40, "crop": 5.74, "diff": +0.35},
]

def analyze_images():
    base_dir = "/Users/jameszhenyu/Desktop/2025-08-14"
    output_dir = "/Users/jameszhenyu/PycharmProjects/SuperPicky_SandBox/scripts/analysis_output"
    os.makedirs(output_dir, exist_ok=True)
    
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"🖥️  设备: {device}")
    
    # 加载模型
    nima = pyiqa.create_metric('nima', device=device)
    from ai_model import load_yolo_model
    from find_bird_util import raw_to_jpeg
    yolo = load_yolo_model()
    
    print("\n" + "="*70)
    print("📊 分析 NIMA 分数差异最大的图片")
    print("="*70)
    
    for i, case in enumerate(test_cases, 1):
        filename = case['file']
        raw_path = os.path.join(base_dir, filename)
        
        if not os.path.exists(raw_path):
            print(f"❌ 文件不存在: {filename}")
            continue
        
        print(f"\n[{i}/{len(test_cases)}] {filename}")
        print(f"   预期分数: 全图 {case['full']:.2f} → 裁剪 {case['crop']:.2f} ({case['diff']:+.2f})")
        
        # 转换 RAW
        jpg_path = raw_path.rsplit('.', 1)[0] + '.jpg'
        if not os.path.exists(jpg_path):
            raw_to_jpeg(raw_path)
        
        # 读取图片
        img = cv2.imread(jpg_path)
        h, w = img.shape[:2]
        print(f"   图片尺寸: {w}x{h}")
        
        # YOLO 检测
        results = yolo(jpg_path, verbose=False)
        if len(results[0].boxes) == 0:
            print("   ❌ 未检测到鸟")
            continue
        
        boxes = results[0].boxes
        best_idx = boxes.conf.argmax().item()
        box = boxes.xyxy[best_idx].cpu().numpy().astype(int)
        x1, y1, x2, y2 = box
        
        crop_w, crop_h = x2 - x1, y2 - y1
        crop_ratio = (crop_w * crop_h) / (w * h) * 100
        print(f"   裁剪区域: {crop_w}x{crop_h} (占全图 {crop_ratio:.1f}%)")
        
        # 计算实际分数
        full_score = nima(jpg_path).item()
        
        bird_crop = img[y1:y2, x1:x2]
        crop_path = "/tmp/crop_analysis.jpg"
        cv2.imwrite(crop_path, bird_crop)
        crop_score = nima(crop_path).item()
        
        print(f"   实际分数: 全图 {full_score:.2f} → 裁剪 {crop_score:.2f} ({crop_score-full_score:+.2f})")
        
        # 生成对比图
        # 在全图上画检测框
        img_with_box = img.copy()
        cv2.rectangle(img_with_box, (x1, y1), (x2, y2), (0, 255, 0), 5)
        
        # 在全图上添加分数标注
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img_with_box, f"FULL: {full_score:.2f}", (50, 150), font, 4, (0, 255, 0), 8)
        
        # 将裁剪区域放大到可比较的尺寸
        crop_display = cv2.resize(bird_crop, (int(w*0.4), int(crop_h * (w*0.4) / crop_w)))
        
        # 创建信息面板
        info_text = f"Full: {full_score:.2f} | Crop: {crop_score:.2f} | Diff: {crop_score-full_score:+.2f}"
        
        # 保存全图（带框）
        full_output = os.path.join(output_dir, f"{i}_{filename.replace('.NEF', '')}_full.jpg")
        # 缩小全图到合理尺寸
        scale = 1500 / max(w, h)
        img_small = cv2.resize(img_with_box, (int(w*scale), int(h*scale)))
        cv2.imwrite(full_output, img_small)
        
        # 保存裁剪图
        crop_output = os.path.join(output_dir, f"{i}_{filename.replace('.NEF', '')}_crop.jpg")
        cv2.imwrite(crop_output, bird_crop)
        
        print(f"   ✅ 已保存: {os.path.basename(full_output)}, {os.path.basename(crop_output)}")
        
        # 清理临时 JPG
        if os.path.exists(jpg_path):
            os.remove(jpg_path)
    
    print(f"\n📁 对比图已保存到: {output_dir}")
    print("\n" + "="*70)
    print("💡 分析结论")
    print("="*70)
    print("""
分数下降的情况 (裁剪后更低):
  - 通常发生在背景很美的照片（虚化光斑、暖色调夕阳等）
  - 全图的整体构图和氛围提升了美学分数
  - 单独看鸟时，可能鸟本身姿态或清晰度一般

分数上升的情况 (裁剪后更高):
  - 通常发生在背景杂乱或不美观的照片
  - 鸟本身姿态优美、眼神清晰
  - 裁剪后聚焦于主体，排除了背景干扰
""")


if __name__ == "__main__":
    analyze_images()
