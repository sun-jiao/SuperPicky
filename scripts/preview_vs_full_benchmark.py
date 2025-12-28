#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比测试: 使用 640 预览 vs 全尺寸 JPG 做 YOLO 检测
"""

import os
import sys
import time
import random
import subprocess
import tempfile

import cv2
import numpy as np

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_model import load_yolo_model
from config import config


def extract_preview(nef_path: str, preview_type: str = "PreviewImage") -> np.ndarray:
    """
    从 NEF 提取预览图
    
    Args:
        nef_path: NEF 文件路径
        preview_type: "PreviewImage" (640px) 或 "JpgFromRaw" (全尺寸)
    
    Returns:
        numpy 图像数组
    """
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # 使用 exiftool 提取预览
        cmd = ['exiftool', '-b', f'-{preview_type}', nef_path]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode == 0 and len(result.stdout) > 1000:
            with open(tmp_path, 'wb') as f:
                f.write(result.stdout)
            img = cv2.imread(tmp_path)
            return img
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run_yolo_detection(model, image: np.ndarray) -> dict:
    """
    运行 YOLO 检测
    
    Returns:
        {'found': bool, 'conf': float, 'bbox': (x1,y1,x2,y2), 'time_ms': float}
    """
    start = time.time()
    
    try:
        results = model(image, device='mps')
    except:
        results = model(image, device='cpu')
    
    elapsed_ms = (time.time() - start) * 1000
    
    # 解析结果
    detections = results[0].boxes.xyxy.cpu().numpy()
    confidences = results[0].boxes.conf.cpu().numpy()
    class_ids = results[0].boxes.cls.cpu().numpy()
    
    # 找最大的鸟
    bird_idx = -1
    max_area = 0
    
    for idx, (det, conf, cls_id) in enumerate(zip(detections, confidences, class_ids)):
        if int(cls_id) == config.ai.BIRD_CLASS_ID:
            x1, y1, x2, y2 = det
            area = (x2 - x1) * (y2 - y1)
            if area > max_area:
                max_area = area
                bird_idx = idx
    
    if bird_idx >= 0:
        x1, y1, x2, y2 = detections[bird_idx]
        return {
            'found': True,
            'conf': float(confidences[bird_idx]),
            'bbox': (float(x1), float(y1), float(x2), float(y2)),
            'time_ms': elapsed_ms
        }
    else:
        return {
            'found': False,
            'conf': 0.0,
            'bbox': None,
            'time_ms': elapsed_ms
        }


def normalize_bbox(bbox, img_shape):
    """归一化 bbox 到 0-1 范围"""
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    h, w = img_shape[:2]
    return (x1/w, y1/h, x2/w, y2/h)


def bbox_iou(bbox1, bbox2):
    """计算两个归一化 bbox 的 IoU"""
    if bbox1 is None or bbox2 is None:
        return 0.0
    
    x1_1, y1_1, x2_1, y2_1 = bbox1
    x1_2, y1_2, x2_2, y2_2 = bbox2
    
    # 交集
    xi1 = max(x1_1, x1_2)
    yi1 = max(y1_1, y1_2)
    xi2 = min(x2_1, x2_2)
    yi2 = min(y2_1, y2_2)
    
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    
    inter_area = (xi2 - xi1) * (yi2 - yi1)
    
    # 并集
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union_area = area1 + area2 - inter_area
    
    return inter_area / union_area if union_area > 0 else 0.0


def main():
    # 测试目录
    test_dir = "/Users/jameszhenyu/Desktop/2025-08-14"
    
    if not os.path.exists(test_dir):
        print(f"❌ 测试目录不存在: {test_dir}")
        return
    
    # 获取所有 NEF 文件
    nef_files = [f for f in os.listdir(test_dir) if f.lower().endswith('.nef')]
    
    if len(nef_files) < 10:
        print(f"❌ NEF 文件不足 10 张，只有 {len(nef_files)} 张")
        sample_files = nef_files
    else:
        sample_files = random.sample(nef_files, 10)
    
    print(f"📊 随机选择 {len(sample_files)} 张 NEF 文件进行对比测试\n")
    
    # 加载模型
    print("🔧 加载 YOLO 模型...")
    model = load_yolo_model()
    print("✅ 模型加载完成\n")
    
    # 统计
    results = []
    
    print("=" * 80)
    print(f"{'文件名':<20} {'640预览':<12} {'全尺寸':<12} {'IoU':<8} {'时间差':<10}")
    print("=" * 80)
    
    for filename in sample_files:
        nef_path = os.path.join(test_dir, filename)
        
        # 提取 640 预览
        t0 = time.time()
        preview_img = extract_preview(nef_path, "PreviewImage")
        preview_extract_time = (time.time() - t0) * 1000
        
        # 提取全尺寸 JPG
        t0 = time.time()
        full_img = extract_preview(nef_path, "JpgFromRaw")
        full_extract_time = (time.time() - t0) * 1000
        
        if preview_img is None or full_img is None:
            print(f"{filename:<20} ❌ 提取失败")
            continue
        
        # 全尺寸缩放到 1024
        h, w = full_img.shape[:2]
        scale = 1024 / max(w, h)
        full_resized = cv2.resize(full_img, (int(w * scale), int(h * scale)))
        
        # YOLO 检测
        preview_result = run_yolo_detection(model, preview_img)
        full_result = run_yolo_detection(model, full_resized)
        
        # 归一化 bbox 计算 IoU
        preview_bbox_norm = normalize_bbox(preview_result['bbox'], preview_img.shape)
        full_bbox_norm = normalize_bbox(full_result['bbox'], full_resized.shape)
        iou = bbox_iou(preview_bbox_norm, full_bbox_norm)
        
        # 总时间 (提取 + 推理)
        preview_total = preview_extract_time + preview_result['time_ms']
        full_total = full_extract_time + preview_result['time_ms']  # 用同样的推理时间近似
        time_saved = full_total - preview_total
        
        # 显示结果
        preview_status = f"✅ {preview_result['conf']:.2f}" if preview_result['found'] else "❌ 无鸟"
        full_status = f"✅ {full_result['conf']:.2f}" if full_result['found'] else "❌ 无鸟"
        
        print(f"{filename:<20} {preview_status:<12} {full_status:<12} {iou:.2f}     -{time_saved:.0f}ms")
        
        results.append({
            'filename': filename,
            'preview_found': preview_result['found'],
            'full_found': full_result['found'],
            'preview_conf': preview_result['conf'],
            'full_conf': full_result['conf'],
            'iou': iou,
            'preview_time': preview_extract_time + preview_result['time_ms'],
            'full_time': full_extract_time + full_result['time_ms'],
            'preview_extract_ms': preview_extract_time,
            'full_extract_ms': full_extract_time,
        })
    
    print("=" * 80)
    
    # 汇总统计
    if results:
        print("\n📈 汇总统计:")
        
        # 检测一致性
        same_result = sum(1 for r in results if r['preview_found'] == r['full_found'])
        print(f"   检测一致性: {same_result}/{len(results)} ({same_result/len(results)*100:.0f}%)")
        
        # 平均 IoU (只统计都检测到鸟的)
        both_found = [r for r in results if r['preview_found'] and r['full_found']]
        if both_found:
            avg_iou = sum(r['iou'] for r in both_found) / len(both_found)
            print(f"   平均 IoU: {avg_iou:.3f}")
        
        # 平均提取时间
        avg_preview_extract = sum(r['preview_extract_ms'] for r in results) / len(results)
        avg_full_extract = sum(r['full_extract_ms'] for r in results) / len(results)
        print(f"\n   640预览提取: {avg_preview_extract:.0f}ms")
        print(f"   全尺寸提取: {avg_full_extract:.0f}ms")
        print(f"   🚀 提取节省: {avg_full_extract - avg_preview_extract:.0f}ms/张")
        
        # 平均总时间
        avg_preview_total = sum(r['preview_time'] for r in results) / len(results)
        avg_full_total = sum(r['full_time'] for r in results) / len(results)
        print(f"\n   640方案总耗时: {avg_preview_total:.0f}ms/张")
        print(f"   全尺寸方案总耗时: {avg_full_total:.0f}ms/张")
        print(f"   🚀 总体节省: {avg_full_total - avg_preview_total:.0f}ms/张")


if __name__ == "__main__":
    main()
