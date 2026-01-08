"""
连拍检测器模块 - V4.0

功能：
1. 读取毫秒级时间戳 (SubSecTimeOriginal)
2. 检测连拍组 (时间差 < 150ms)
3. 组内最佳选择
4. 分组处理 (子目录 + 标签)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Dict
import os
import subprocess
import json


@dataclass
class PhotoTimestamp:
    """照片时间戳信息"""
    filepath: str
    datetime_original: Optional[datetime] = None
    subsec: Optional[str] = None  # 毫秒部分，如 "045"
    precise_time: Optional[float] = None  # 精确时间戳（秒）
    rating: int = 0
    sharpness: float = 0.0
    topiq: float = 0.0
    
    @property
    def has_subsec(self) -> bool:
        """是否有毫秒信息"""
        return self.subsec is not None and self.subsec != ""


@dataclass
class BurstGroup:
    """连拍组"""
    group_id: int
    photos: List[PhotoTimestamp] = field(default_factory=list)
    best_index: int = 0  # 最佳照片在 photos 列表中的索引
    
    @property
    def count(self) -> int:
        return len(self.photos)
    
    @property
    def best_photo(self) -> Optional[PhotoTimestamp]:
        if self.photos and 0 <= self.best_index < len(self.photos):
            return self.photos[self.best_index]
        return None


class BurstDetector:
    """连拍检测器"""
    
    # 检测参数
    TIME_THRESHOLD_MS = 150  # 同一连拍组的最大时间差（毫秒）
    MIN_BURST_COUNT = 3      # 最少连拍张数
    MIN_RATING = 2           # 只处理 >= 2 星的照片
    
    def __init__(self, exiftool_path: str = None):
        """
        初始化连拍检测器
        
        Args:
            exiftool_path: ExifTool 路径
        """
        self.exiftool_path = exiftool_path or self._find_exiftool()
    
    def _find_exiftool(self) -> str:
        """查找 ExifTool 路径"""
        # 优先使用项目内置的 exiftool
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        builtin = os.path.join(project_root, 'exiftool')
        if os.path.exists(builtin):
            return builtin
        # 否则使用系统 exiftool
        return 'exiftool'
    
    def read_timestamps(self, filepaths: List[str]) -> List[PhotoTimestamp]:
        """
        批量读取照片的精确时间戳
        
        Args:
            filepaths: 文件路径列表
            
        Returns:
            PhotoTimestamp 列表
        """
        if not filepaths:
            return []
        
        # 使用 exiftool 批量读取
        cmd = [
            self.exiftool_path,
            '-json',
            '-DateTimeOriginal',
            '-SubSecTimeOriginal',
            '-Rating',
        ] + filepaths
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"⚠️ ExifTool 读取时间戳失败: {result.stderr}")
                return []
            
            exif_data = json.loads(result.stdout)
            return self._parse_exif_timestamps(exif_data)
            
        except subprocess.TimeoutExpired:
            print("⚠️ ExifTool 读取超时")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ 解析 EXIF JSON 失败: {e}")
            return []
    
    def _parse_exif_timestamps(self, exif_data: List[dict]) -> List[PhotoTimestamp]:
        """
        解析 EXIF 数据为 PhotoTimestamp 列表
        
        Args:
            exif_data: ExifTool JSON 输出
            
        Returns:
            PhotoTimestamp 列表
        """
        results = []
        
        for item in exif_data:
            filepath = item.get('SourceFile', '')
            dt_str = item.get('DateTimeOriginal', '')
            subsec = item.get('SubSecTimeOriginal', '')
            rating = item.get('Rating', 0) or 0
            
            # 解析日期时间
            dt = None
            if dt_str:
                try:
                    # 格式: "2024:01:09 10:05:30"
                    dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
            
            # 计算精确时间戳
            precise_time = None
            if dt:
                precise_time = dt.timestamp()
                if subsec:
                    # SubSecTimeOriginal 通常是毫秒部分，如 "045"
                    try:
                        subsec_float = float(f"0.{subsec}")
                        precise_time += subsec_float
                    except ValueError:
                        pass
            
            photo = PhotoTimestamp(
                filepath=filepath,
                datetime_original=dt,
                subsec=str(subsec) if subsec else None,
                precise_time=precise_time,
                rating=rating
            )
            results.append(photo)
        
        return results
    
    def detect_groups(self, photos: List[PhotoTimestamp]) -> List[BurstGroup]:
        """
        检测连拍组
        
        Args:
            photos: PhotoTimestamp 列表
            
        Returns:
            BurstGroup 列表
        """
        # 1. 只处理 >= 2 星的照片
        candidates = [p for p in photos if p.rating >= self.MIN_RATING and p.precise_time is not None]
        
        if len(candidates) < self.MIN_BURST_COUNT:
            return []
        
        # 2. 按精确时间排序
        candidates.sort(key=lambda p: p.precise_time)
        
        # 3. 分组检测
        groups = []
        current_group = [candidates[0]]
        
        for i in range(1, len(candidates)):
            prev = candidates[i - 1]
            curr = candidates[i]
            
            # 计算时间差（毫秒）
            time_diff_ms = (curr.precise_time - prev.precise_time) * 1000
            
            if time_diff_ms <= self.TIME_THRESHOLD_MS:
                # 属于同一组
                current_group.append(curr)
            else:
                # 保存当前组（如果满足最小张数）
                if len(current_group) >= self.MIN_BURST_COUNT:
                    group = BurstGroup(
                        group_id=len(groups) + 1,
                        photos=current_group.copy()
                    )
                    groups.append(group)
                
                # 开始新组
                current_group = [curr]
        
        # 处理最后一组
        if len(current_group) >= self.MIN_BURST_COUNT:
            group = BurstGroup(
                group_id=len(groups) + 1,
                photos=current_group.copy()
            )
            groups.append(group)
        
        return groups
    
    def select_best_in_groups(self, groups: List[BurstGroup]) -> List[BurstGroup]:
        """
        在每个连拍组中选择最佳照片
        
        Args:
            groups: BurstGroup 列表
            
        Returns:
            更新后的 BurstGroup 列表
        """
        for group in groups:
            if not group.photos:
                continue
            
            # 按综合分数排序：锐度 * 0.5 + 美学 * 0.5
            best_score = -1
            best_idx = 0
            
            for i, photo in enumerate(group.photos):
                score = photo.sharpness * 0.5 + photo.topiq * 0.5
                if score > best_score:
                    best_score = score
                    best_idx = i
            
            group.best_index = best_idx
        
        return groups


# 测试函数
def test_burst_detector():
    """测试连拍检测器"""
    detector = BurstDetector()
    
    # 测试目录
    test_dir = '/Users/jameszhenyu/Desktop/Ti'
    
    if not os.path.exists(test_dir):
        print(f"测试目录不存在: {test_dir}")
        return
    
    # 获取所有图片文件
    extensions = {'.nef', '.rw2', '.arw', '.cr2', '.cr3', '.orf', '.jpg', '.jpeg'}
    filepaths = []
    for entry in os.scandir(test_dir):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in extensions:
                filepaths.append(entry.path)
    
    print(f"找到 {len(filepaths)} 个图片文件")
    
    # 读取时间戳
    print("\n读取时间戳...")
    photos = detector.read_timestamps(filepaths)
    
    # 显示结果
    print(f"\n读取到 {len(photos)} 个时间戳：")
    for p in photos[:10]:  # 只显示前 10 个
        subsec_str = f".{p.subsec}" if p.subsec else ""
        dt_str = p.datetime_original.strftime("%Y-%m-%d %H:%M:%S") if p.datetime_original else "无"
        print(f"  {os.path.basename(p.filepath)}: {dt_str}{subsec_str} (评分: {p.rating})")
    
    # 检测连拍组
    print("\n检测连拍组...")
    groups = detector.detect_groups(photos)
    
    print(f"\n发现 {len(groups)} 个连拍组：")
    for group in groups:
        print(f"  组 #{group.group_id}: {group.count} 张照片")
        for p in group.photos:
            print(f"    - {os.path.basename(p.filepath)}")


if __name__ == '__main__':
    test_burst_detector()
