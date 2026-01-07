#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Focus Point Detector - 对焦点检测器
用于从 Nikon Z8/Z9 RAW 文件中提取对焦点坐标，并验证是否落在鸟的 Bounding Box 内

支持功能：
- 读取 Nikon MakerNotes 中的对焦数据
- 坐标归一化 (0.0-1.0)
- 竖拍旋转处理
- DX 裁切修正
- 与 YOLO Bounding Box 碰撞检测
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import subprocess
import json
import numpy as np


@dataclass
class FocusPointResult:
    """对焦点检测结果"""
    x: float                    # 归一化 X 坐标 (0.0-1.0)
    y: float                    # 归一化 Y 坐标 (0.0-1.0)
    raw_x: int                  # 原始像素 X 坐标
    raw_y: int                  # 原始像素 Y 坐标
    area_width: int             # 对焦区域宽度
    area_height: int            # 对焦区域高度
    af_mode: str                # AF 模式 (AF-C, AF-S 等)
    area_mode: str              # 区域模式 (Auto, 3D-Tracking 等)
    focus_result: any           # 合焦结果 (1=Focus 或 "Focus")
    is_valid: bool              # 是否有效对焦数据
    
    @property
    def is_focused(self) -> bool:
        """是否成功合焦 (FocusResult: 1=Focus, 其他=未合焦)"""
        # ExifTool -n 返回数值: 1 = Focus
        if isinstance(self.focus_result, (int, float)):
            return int(self.focus_result) == 1
        return str(self.focus_result).lower() == 'focus'


class FocusPointDetector:
    """
    对焦点检测器
    
    从 Nikon Z8/Z9 的 NEF 文件中提取对焦点数据
    """
    
    # Nikon Z8/Z9 使用的 EXIF 标签
    EXIF_TAGS = [
        'FocusMode',
        'AFAreaMode',
        'AFAreaXPosition',
        'AFAreaYPosition',
        'AFAreaWidth',
        'AFAreaHeight',
        'AFImageWidth',
        'AFImageHeight',
        'FocusResult',
        'Orientation',
        'CropArea',
    ]
    
    def __init__(self, exiftool_path: str = 'exiftool'):
        """
        初始化检测器
        
        Args:
            exiftool_path: ExifTool 可执行文件路径
        """
        self.exiftool_path = exiftool_path
    
    def detect(self, raw_path: str) -> Optional[FocusPointResult]:
        """
        检测对焦点
        
        Args:
            raw_path: RAW 文件路径 (NEF)
            
        Returns:
            FocusPointResult 或 None (无对焦数据)
        """
        # 读取 EXIF 数据
        exif_data = self._read_exif(raw_path)
        if exif_data is None:
            return None
        
        # 检查是否为 AF 模式
        focus_mode = str(exif_data.get('FocusMode', '')).strip()
        if not focus_mode or 'MF' in focus_mode.upper() or 'MANUAL' in focus_mode.upper():
            return None  # 手动对焦无数据
        
        # 获取对焦坐标
        af_x = exif_data.get('AFAreaXPosition')
        af_y = exif_data.get('AFAreaYPosition')
        af_img_w = exif_data.get('AFImageWidth')
        af_img_h = exif_data.get('AFImageHeight')
        
        if af_x is None or af_y is None or af_img_w is None or af_img_h is None:
            return None  # 缺少关键数据
        
        # 转换为数值
        try:
            raw_x = int(af_x)
            raw_y = int(af_y)
            img_w = int(af_img_w)
            img_h = int(af_img_h)
        except (ValueError, TypeError):
            return None
        
        # 处理 DX 裁切
        raw_x, raw_y, img_w, img_h = self._apply_crop_correction(
            raw_x, raw_y, img_w, img_h, exif_data
        )
        
        # 归一化坐标
        norm_x = raw_x / img_w if img_w > 0 else 0.5
        norm_y = raw_y / img_h if img_h > 0 else 0.5
        
        # 处理竖拍旋转
        orientation = exif_data.get('Orientation', 1)
        norm_x, norm_y = self._apply_orientation_correction(norm_x, norm_y, orientation)
        
        # 获取其他信息
        area_w = int(exif_data.get('AFAreaWidth', 0))
        area_h = int(exif_data.get('AFAreaHeight', 0))
        area_mode = str(exif_data.get('AFAreaMode', 'Unknown'))
        focus_result = exif_data.get('FocusResult', 'Unknown')  # 保持原始类型 (可能是 int 或 str)
        
        return FocusPointResult(
            x=norm_x,
            y=norm_y,
            raw_x=raw_x,
            raw_y=raw_y,
            area_width=area_w,
            area_height=area_h,
            af_mode=focus_mode,
            area_mode=area_mode,
            focus_result=focus_result,
            is_valid=True
        )
    
    def _read_exif(self, file_path: str) -> Optional[dict]:
        """读取 EXIF 数据"""
        cmd = [self.exiftool_path, '-j', '-n']
        for tag in self.EXIF_TAGS:
            cmd.append(f'-{tag}')
        cmd.append(file_path)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            return data[0] if data else None
        except Exception:
            return None
    
    def _apply_crop_correction(
        self, 
        x: int, 
        y: int, 
        img_w: int, 
        img_h: int, 
        exif_data: dict
    ) -> Tuple[int, int, int, int]:
        """
        处理 DX 裁切修正
        
        CropArea 格式: "left top width height"
        """
        crop_area = exif_data.get('CropArea', '')
        if not crop_area:
            return x, y, img_w, img_h
        
        try:
            parts = str(crop_area).split()
            if len(parts) >= 4:
                crop_left = int(parts[0])
                crop_top = int(parts[1])
                crop_w = int(parts[2])
                crop_h = int(parts[3])
                
                # 如果裁切区域与图像尺寸差异大于 5%，才进行修正
                if abs(crop_w - img_w) > img_w * 0.05 or abs(crop_h - img_h) > img_h * 0.05:
                    # DX 模式：坐标需要减去偏移量
                    x = x - crop_left
                    y = y - crop_top
                    img_w = crop_w
                    img_h = crop_h
        except (ValueError, IndexError):
            pass
        
        return x, y, img_w, img_h
    
    def _apply_orientation_correction(
        self, 
        x: float, 
        y: float, 
        orientation: int
    ) -> Tuple[float, float]:
        """
        处理竖拍旋转
        
        Orientation 值:
        - 1: Horizontal (正常)
        - 6: Rotate 90 CW (顺时针旋转 90°)
        - 8: Rotate 270 CW (顺时针旋转 270°)
        """
        if orientation == 6:
            # 顺时针 90°: (x, y) -> (y, 1-x)
            return y, 1.0 - x
        elif orientation == 8:
            # 顺时针 270° (逆时针 90°): (x, y) -> (1-y, x)
            return 1.0 - y, x
        else:
            return x, y


def verify_focus_in_bbox(
    focus: Optional[FocusPointResult], 
    bbox: Tuple[int, int, int, int],
    img_dims: Tuple[int, int],
    seg_mask: np.ndarray = None,
    head_center: Tuple[int, int] = None,
    head_radius: int = None,
) -> float:
    """
    验证对焦点位置，返回锐度权重因子
    
    采用 4 层检测策略：
    1. 头部区域内 → 1.2 (最佳)
    2. SEG 掩码内 → 1.0 (正常)
    3. BBox 内 → 0.8 (轻微惩罚)
    4. BBox 外 → 0.6 (较大惩罚)
    
    Args:
        focus: 对焦点检测结果
        bbox: YOLO 检测的 Bounding Box (x, y, w, h) - 左上角坐标
        img_dims: 图像尺寸 (width, height)
        seg_mask: 分割掩码（原图尺寸），可选
        head_center: 头部圆心 (x, y) 像素坐标，可选
        head_radius: 头部区域半径（像素），可选
        
    Returns:
        权重因子 (乘以锐度值):
        - 1.2: 对焦点在头部区域内
        - 1.0: 对焦点在 SEG 掩码内（但不在头部）
        - 0.8: 对焦点在 BBox 内（但不在 SEG）
        - 0.6: 对焦点在 BBox 外
        - 1.0: 无对焦数据
    """
    if focus is None or not focus.is_valid:
        return 1.0  # 无数据，不影响评分
    
    if not focus.is_focused:
        return 0.8  # 未合焦，轻微惩罚
    
    # 转换对焦点为像素坐标
    img_w, img_h = img_dims
    focus_px = (int(focus.x * img_w), int(focus.y * img_h))
    
    # 检查是否在头部区域内
    if head_center is not None and head_radius is not None:
        dist = np.sqrt((focus_px[0] - head_center[0])**2 + (focus_px[1] - head_center[1])**2)
        if dist <= head_radius:
            return 1.2  # 对焦在头部区域，最佳
    
    # 检查是否在 SEG 掩码内
    if seg_mask is not None:
        # 确保坐标在图像范围内
        fx, fy = focus_px
        if 0 <= fy < seg_mask.shape[0] and 0 <= fx < seg_mask.shape[1]:
            if seg_mask[fy, fx] > 0:
                return 1.0  # 对焦在鸟身上（但不在头部），正常
    
    # 检查是否在 BBox 内
    bx, by, bw, bh = bbox
    in_bbox = (bx <= focus_px[0] <= bx + bw) and (by <= focus_px[1] <= by + bh)
    
    if in_bbox:
        return 0.8  # 对焦在 BBox 内但不在鸟身上（背景），轻微惩罚
    else:
        return 0.6  # 对焦完全在 BBox 外，较大惩罚


# 全局单例
_focus_detector: Optional[FocusPointDetector] = None


def get_focus_detector() -> FocusPointDetector:
    """获取对焦点检测器单例"""
    global _focus_detector
    if _focus_detector is None:
        _focus_detector = FocusPointDetector()
    return _focus_detector
