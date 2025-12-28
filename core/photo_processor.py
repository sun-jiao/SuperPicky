#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core Photo Processor - 核心照片处理器
提取自 GUI 和 CLI 的共享业务逻辑

职责：
- 文件扫描和 RAW 转换
- 调用 AI 检测
- 调用 RatingEngine 评分
- 写入 EXIF 元数据
- 文件移动和清理
"""

import os
import time
import json
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# 现有模块
from find_bird_util import raw_to_jpeg
from ai_model import load_yolo_model, detect_and_draw_birds
from exiftool_manager import get_exiftool_manager
from advanced_config import get_advanced_config
from core.rating_engine import RatingEngine, create_rating_engine_from_config
from core.keypoint_detector import KeypointDetector, get_keypoint_detector

# 文件夹名称映射（支持所有星级）
RATING_FOLDER_NAMES = {
    3: "3星_优选",
    2: "2星_良好",  # 默认目录
    "2_sharpness": "2星_良好_锐度",  # 锐度达标
    "2_nima": "2星_良好_美学",  # NIMA达标
    1: "1星_普通",
    0: "0星_放弃",  # 0星和-1星都放这里
    -1: "0星_放弃",  # 无鸟照片
}


@dataclass
class ProcessingSettings:
    """处理参数配置"""
    ai_confidence: int = 50
    sharpness_threshold: int = 200   # 头部区域锐度达标阈值
    nima_threshold: float = 4.8
    save_crop: bool = False
    normalization_mode: str = 'log_compression'  # 默认使用log_compression，与GUI一致


@dataclass
class ProcessingCallbacks:
    """回调函数（用于进度更新和日志输出）"""
    log: Optional[Callable[[str, str], None]] = None
    progress: Optional[Callable[[int], None]] = None


@dataclass
class ProcessingResult:
    """处理结果数据"""
    stats: Dict[str, any] = field(default_factory=dict)
    file_ratings: Dict[str, int] = field(default_factory=dict)
    star_3_photos: List[Dict] = field(default_factory=list)
    total_time: float = 0.0
    avg_time: float = 0.0


class PhotoProcessor:
    """
    核心照片处理器
    
    封装所有业务逻辑，GUI 和 CLI 都调用这个类
    """
    
    def __init__(
        self,
        dir_path: str,
        settings: ProcessingSettings,
        callbacks: Optional[ProcessingCallbacks] = None
    ):
        """
        初始化处理器
        
        Args:
            dir_path: 处理目录路径
            settings: 处理参数
            callbacks: 回调函数（进度、日志）
        """
        self.dir_path = dir_path
        self.settings = settings
        self.callbacks = callbacks or ProcessingCallbacks()
        self.config = get_advanced_config()
        
        # 初始化评分引擎
        self.rating_engine = create_rating_engine_from_config(self.config)
        # 使用 UI 设置更新达标阈值
        self.rating_engine.update_thresholds(
            sharpness_threshold=settings.sharpness_threshold,
            nima_threshold=settings.nima_threshold
        )
        
        # DEBUG: 输出参数
        self._log(f"\n🔍 DEBUG - 处理参数:")
        self._log(f"  📊 AI置信度: {settings.ai_confidence}")
        self._log(f"  📏 锐度阈值: {settings.sharpness_threshold}")
        self._log(f"  🎨 NIMA阈值: {settings.nima_threshold}")
        self._log(f"  🔧 归一化模式: {settings.normalization_mode}")
        self._log(f"  ⚙️  高级配置 - min_sharpness: {self.config.min_sharpness}")
        self._log(f"  ⚙️  高级配置 - min_nima: {self.config.min_nima}\n")
        
        # 统计数据（支持 0/1/2/3 星）
        self.stats = {
            'total': 0,
            'star_3': 0,
            'picked': 0,
            'star_2': 0,
            'star_1': 0,  # 普通照片（合格）
            'star_0': 0,  # 普通照片（问题）
            'no_bird': 0,
            'start_time': 0,
            'end_time': 0,
            'total_time': 0,
            'avg_time': 0
        }
        
        # 内部状态
        self.file_ratings = {}
        self.star2_reasons = {}  # 记录2星原因: 'sharpness' 或 'nima'
        self.star_3_photos = []
    
    def _log(self, msg: str, level: str = "info"):
        """内部日志方法"""
        if self.callbacks.log:
            self.callbacks.log(msg, level)
    
    def _progress(self, percent: int):
        """内部进度更新"""
        if self.callbacks.progress:
            self.callbacks.progress(percent)
    
    def process(
        self,
        organize_files: bool = True,
        cleanup_temp: bool = True
    ) -> ProcessingResult:
        """
        主处理流程
        
        Args:
            organize_files: 是否移动文件到分类文件夹
            cleanup_temp: 是否清理临时JPG文件
            
        Returns:
            ProcessingResult 包含统计数据和处理结果
        """
        start_time = time.time()
        self.stats['start_time'] = start_time
        
        # 阶段1: 文件扫描
        raw_dict, jpg_dict, files_tbr = self._scan_files()
        
        # 阶段2: RAW转换
        raw_files_to_convert = self._identify_raws_to_convert(raw_dict, jpg_dict, files_tbr)
        if raw_files_to_convert:
            self._convert_raws(raw_files_to_convert, files_tbr)
        
        # 阶段3: AI检测与评分
        self._process_images(files_tbr, raw_dict)
        
        # 阶段4: 精选旗标计算
        self._calculate_picked_flags()
        
        # 阶段5: 文件组织
        if organize_files:
            self._move_files_to_rating_folders(raw_dict)
        
        # 阶段6: 清理临时文件
        if cleanup_temp:
            self._cleanup_temp_files(files_tbr, raw_dict)
        
        # 记录结束时间
        end_time = time.time()
        self.stats['end_time'] = end_time
        self.stats['total_time'] = end_time - start_time
        self.stats['avg_time'] = (
            self.stats['total_time'] / self.stats['total']
            if self.stats['total'] > 0 else 0
        )
        
        return ProcessingResult(
            stats=self.stats.copy(),
            file_ratings=self.file_ratings.copy(),
            star_3_photos=self.star_3_photos.copy(),
            total_time=self.stats['total_time'],
            avg_time=self.stats['avg_time']
        )
    
    def _scan_files(self) -> Tuple[dict, dict, list]:
        """扫描目录文件"""
        scan_start = time.time()
        
        raw_extensions = ['.nef', '.cr2', '.cr3', '.arw', '.raf', '.orf', 
                         '.rw2', '.pef', '.dng', '.3fr', '.iiq']
        jpg_extensions = ['.jpg', '.jpeg']
        
        raw_dict = {}
        jpg_dict = {}
        files_tbr = []
        
        for filename in os.listdir(self.dir_path):
            if filename.startswith('.'):
                continue
            
            file_prefix, file_ext = os.path.splitext(filename)
            if file_ext.lower() in raw_extensions:
                raw_dict[file_prefix] = file_ext
            if file_ext.lower() in jpg_extensions:
                jpg_dict[file_prefix] = file_ext
                files_tbr.append(filename)
        
        scan_time = (time.time() - scan_start) * 1000
        self._log(f"⏱️  文件扫描耗时: {scan_time:.1f}ms")
        
        return raw_dict, jpg_dict, files_tbr
    
    def _identify_raws_to_convert(self, raw_dict, jpg_dict, files_tbr):
        """识别需要转换的RAW文件"""
        raw_files_to_convert = []
        
        for key, value in raw_dict.items():
            if key in jpg_dict:
                jpg_dict.pop(key)
                continue
            else:
                raw_file_path = os.path.join(self.dir_path, key + value)
                raw_files_to_convert.append((key, raw_file_path))
        
        return raw_files_to_convert
    
    def _convert_raws(self, raw_files_to_convert, files_tbr):
        """并行转换RAW文件"""
        raw_start = time.time()
        import multiprocessing
        max_workers = min(4, multiprocessing.cpu_count())
        
        self._log(f"🔄 开始并行转换 {len(raw_files_to_convert)} 个RAW文件({max_workers}线程)...")
        
        def convert_single(args):
            key, raw_path = args
            try:
                raw_to_jpeg(raw_path)
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_raw = {
                executor.submit(convert_single, args): args 
                for args in raw_files_to_convert
            }
            converted_count = 0
            
            for future in as_completed(future_to_raw):
                key, success, error = future.result()
                if success:
                    files_tbr.append(key + ".jpg")
                    converted_count += 1
                    if converted_count % 5 == 0 or converted_count == len(raw_files_to_convert):
                        self._log(f"  ✅ 已转换 {converted_count}/{len(raw_files_to_convert)} 张")
                else:
                    self._log(f"  ❌ 转换失败: {key} ({error})", "error")
        
        raw_time = time.time() - raw_start
        avg_time = raw_time / len(raw_files_to_convert) if len(raw_files_to_convert) > 0 else 0
        self._log(f"⏱️  RAW转换耗时: {raw_time:.1f}秒 (平均 {avg_time:.1f}秒/张)\n")
    
    def _process_images(self, files_tbr, raw_dict):
        """处理所有图片 - AI检测、关键点检测与评分"""
        # 加载模型
        model_start = time.time()
        self._log("🤖 加载AI模型...")
        model = load_yolo_model()
        model_time = (time.time() - model_start) * 1000
        self._log(f"⏱️  模型加载耗时: {model_time:.0f}ms")
        
        # 加载关键点检测模型
        self._log("👁️  加载关键点模型...")
        keypoint_detector = get_keypoint_detector()
        try:
            keypoint_detector.load_model()
            self._log("✅ 关键点模型加载成功")
            use_keypoints = True
        except FileNotFoundError:
            self._log("⚠️  关键点模型未找到，使用传统锐度计算", "warning")
            use_keypoints = False
        
        total_files = len(files_tbr)
        self._log(f"📁 共 {total_files} 个文件待处理\n")
        
        exiftool_mgr = get_exiftool_manager()
        
        # UI设置转为列表格式
        ui_settings = [
            self.settings.ai_confidence,
            self.settings.sharpness_threshold,
            self.settings.nima_threshold,
            self.settings.save_crop,
            self.settings.normalization_mode
        ]
        
        ai_total_start = time.time()
        
        for i, filename in enumerate(files_tbr, 1):

            filepath = os.path.join(self.dir_path, filename)
            file_prefix, _ = os.path.splitext(filename)
            
            self._log(f"[{i}/{total_files}] {filename}")
            
            # 更新进度
            should_update = (i % 5 == 0 or i == total_files or i == 1)
            if should_update:
                progress = int((i / total_files) * 100)
                self._progress(progress)
            
            # 优化流程：YOLO → 关键点检测(在crop上) → 条件NIMA
            # Phase 1: 先做YOLO检测（跳过NIMA），获取鸟的位置和bbox
            try:
                result = detect_and_draw_birds(
                    filepath, model, None, self.dir_path, ui_settings, None, skip_nima=True
                )
                if result is None:
                    self._log(f"  ⚠️  无法处理(AI推理失败)", "error")
                    continue
            except Exception as e:
                self._log(f"  ❌ 处理异常: {e}", "error")
                continue
            
            # 解构 AI 结果 (包含bbox和图像尺寸用于缩放) - V3.2移除BRISQUE
            detected, _, confidence, sharpness, _, bird_bbox, img_dims = result
            
            # Phase 2: 关键点检测（在裁剪区域上执行，更准确）
            both_eyes_hidden = False
            head_sharpness = 0.0
            has_visible_eye = False
            has_visible_beak = False
            left_eye_vis = 0.0
            right_eye_vis = 0.0
            beak_vis = 0.0
            
            # V3.2优化: 只读取原图一次，在关键点检测和NIMA计算中复用
            orig_img = None  # 原图缓存
            bird_crop_bgr = None  # 裁剪区域缓存（BGR）
            
            if use_keypoints and detected and bird_bbox is not None and img_dims is not None:
                try:
                    import cv2
                    orig_img = cv2.imread(filepath)  # 只读取一次!
                    if orig_img is not None:
                        h_orig, w_orig = orig_img.shape[:2]
                        # 获取YOLO处理时的图像尺寸
                        w_resized, h_resized = img_dims
                        
                        # 计算缩放比例：原图 / 缩放图
                        scale_x = w_orig / w_resized
                        scale_y = h_orig / h_resized
                        
                        # 将bbox从缩放尺寸转换到原图尺寸
                        x, y, w, h = bird_bbox
                        x_orig = int(x * scale_x)
                        y_orig = int(y * scale_y)
                        w_orig_box = int(w * scale_x)
                        h_orig_box = int(h * scale_y)
                        
                        # 确保边界有效
                        x_orig = max(0, min(x_orig, w_orig - 1))
                        y_orig = max(0, min(y_orig, h_orig - 1))
                        w_orig_box = min(w_orig_box, w_orig - x_orig)
                        h_orig_box = min(h_orig_box, h_orig - y_orig)
                        
                        # 裁剪鸟的区域（保存BGR版本供NIMA使用）
                        bird_crop_bgr = orig_img[y_orig:y_orig+h_orig_box, x_orig:x_orig+w_orig_box]
                        if bird_crop_bgr.size > 0:
                            crop_rgb = cv2.cvtColor(bird_crop_bgr, cv2.COLOR_BGR2RGB)
                            # 在裁剪区域上进行关键点检测
                            kp_result = keypoint_detector.detect(crop_rgb, box=(x_orig, y_orig, w_orig_box, h_orig_box))
                            if kp_result is not None:
                                both_eyes_hidden = kp_result.both_eyes_hidden
                                has_visible_eye = kp_result.visible_eye is not None
                                has_visible_beak = kp_result.beak_vis >= 0.5
                                left_eye_vis = kp_result.left_eye_vis
                                right_eye_vis = kp_result.right_eye_vis
                                beak_vis = kp_result.beak_vis
                                head_sharpness = kp_result.head_sharpness
                except Exception as e:
                    self._log(f"  ⚠️  关键点检测失败: {e}", "warning")
            
            # Phase 3: 根据眼睛可见性决定是否计算NIMA
            # V3.2优化: 复用已裁剪的鸟区域，避免重复读取原图
            nima = None
            if detected and not both_eyes_hidden:
                # 双眼可见，需要计算NIMA以进行星级判定
                try:
                    from iqa_scorer import get_iqa_scorer
                    import time as time_module
                    import cv2
                    import tempfile
                    
                    step_start = time_module.time()
                    scorer = get_iqa_scorer(device='mps')
                    
                    # 优化: 直接使用已裁剪的区域（避免重复读取原图）
                    if bird_crop_bgr is not None and bird_crop_bgr.size > 0:
                        # 保存到临时文件供 NIMA 评估
                        crop_temp_path = tempfile.mktemp(suffix='.jpg')
                        cv2.imwrite(crop_temp_path, bird_crop_bgr)
                        nima = scorer.calculate_nima(crop_temp_path)
                        # 清理临时文件
                        if os.path.exists(crop_temp_path):
                            os.remove(crop_temp_path)
                    else:
                        # 回退：没有裁剪区域时用全图
                        nima = scorer.calculate_nima(filepath)
                    
                    nima_time = (time_module.time() - step_start) * 1000
                    if nima is not None:
                        self._log(f"🎨 NIMA 美学评分: {nima:.2f} / 10 (裁剪区域)")
                        self._log(f"  ⏱️  [补充] NIMA评分: {nima_time:.1f}ms")
                except Exception as e:
                    self._log(f"  ⚠️  NIMA计算失败: {e}", "warning")
            elif detected and both_eyes_hidden:
                self._log(f"⚡ NIMA 已跳过（双眼不可见）")
            
            # 使用 RatingEngine 计算评分
            rating_result = self.rating_engine.calculate(
                detected=detected,
                confidence=confidence,
                sharpness=head_sharpness,  # 使用头部锐度
                nima=nima,
                both_eyes_hidden=both_eyes_hidden
            )
            rating_value = rating_result.rating
            pick = rating_result.pick
            reason = rating_result.reason
            
            # 显示结果（使用头部锐度）
            self._log_photo_result(rating_value, reason, confidence, head_sharpness, nima)
            
            # 记录统计
            self._update_stats(rating_value)
            
            # 写入EXIF
            raw_file_path = None
            if file_prefix in raw_dict:
                raw_extension = raw_dict[file_prefix]
                raw_file_path = os.path.join(self.dir_path, file_prefix + raw_extension)
                
                if os.path.exists(raw_file_path):
                    single_batch = [{
                        'file': raw_file_path,
                        'rating': rating_value if rating_value >= 0 else 0,
                        'pick': pick,
                        'sharpness': head_sharpness,  # 使用头部锐度
                        'nima_score': nima
                    }]
                    exiftool_mgr.batch_set_metadata(single_batch)
                    
                    # 更新CSV中的关键点数据
                    self._update_csv_keypoint_data(
                        file_prefix, 
                        head_sharpness, 
                        has_visible_eye, 
                        has_visible_beak,
                        left_eye_vis,
                        right_eye_vis,
                        beak_vis,
                        rating_value
                    )
                    
                    # 收集3星照片
                    if rating_value == 3 and nima is not None:
                        self.star_3_photos.append({
                            'file': raw_file_path,
                            'nima': nima,
                            'sharpness': head_sharpness
                        })
                    
                    # 记录评分
                    self.file_ratings[file_prefix] = rating_value
                    
                    # 记录2星原因（用于分目录）
                    if rating_value == 2:
                        sharpness_ok = head_sharpness >= self.settings.sharpness_threshold
                        nima_ok = nima is not None and nima >= self.settings.nima_threshold
                        if sharpness_ok and not nima_ok:
                            self.star2_reasons[file_prefix] = 'sharpness'
                        elif nima_ok and not sharpness_ok:
                            self.star2_reasons[file_prefix] = 'nima'
                        else:
                            self.star2_reasons[file_prefix] = 'both'  # 两者都达标
        
        ai_total_time = time.time() - ai_total_start
        avg_ai_time = ai_total_time / total_files if total_files > 0 else 0
        self._log(f"\n⏱️  AI检测总耗时: {ai_total_time:.1f}秒 (平均 {avg_ai_time:.1f}秒/张)")
    
    # 注意: _calculate_rating 方法已移至 core/rating_engine.py
    # 现在使用 self.rating_engine.calculate() 替代
    
    def _log_photo_result(
        self, 
        rating: int, 
        reason: str, 
        conf: float, 
        sharp: float, 
        nima: Optional[float]
    ):
        """记录照片处理结果"""
        iqa_text = ""
        if nima is not None:
            iqa_text += f", 美学:{nima:.2f}"
        
        if rating == 3:
            self._log(f"  ⭐⭐⭐ 优选照片 (AI:{conf:.2f}, 锐度:{sharp:.1f}{iqa_text})", "success")
        elif rating == 2:
            self._log(f"  ⭐⭐ 良好照片 (AI:{conf:.2f}, 锐度:{sharp:.1f}{iqa_text})", "info")
        elif rating == 1:
            self._log(f"  ⭐ 普通照片 (AI:{conf:.2f}, 锐度:{sharp:.1f}{iqa_text})", "warning")
        elif rating == 0:
            self._log(f"  普通照片 - {reason}", "warning")
        else:  # -1
            self._log(f"  ❌ 无鸟 - {reason}", "error")
    
    def _update_stats(self, rating: int):
        """更新统计数据"""
        self.stats['total'] += 1
        if rating == 3:
            self.stats['star_3'] += 1
        elif rating == 2:
            self.stats['star_2'] += 1
        elif rating == 1:
            self.stats['star_1'] += 1  # 普通照片（合格）
        elif rating == 0:
            self.stats['star_0'] += 1  # 普通照片（问题）
        else:  # -1
            self.stats['no_bird'] += 1
    
    def _update_csv_keypoint_data(
        self, 
        filename: str, 
        head_sharpness: float,
        has_visible_eye: bool,
        has_visible_beak: bool,
        left_eye_vis: float,
        right_eye_vis: float,
        beak_vis: float,
        rating: int
    ):
        """更新CSV中的关键点数据和评分"""
        import csv
        
        csv_path = os.path.join(self.dir_path, "_tmp", "report.csv")
        if not os.path.exists(csv_path):
            return
        
        try:
            # 读取现有CSV
            rows = []
            fieldnames = None
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                
                # 确保新字段存在
                new_fields = ['head_sharpness', 'left_eye_vis', 'right_eye_vis', 'beak_vis', 'has_visible_eye', 'has_visible_beak']
                for field in new_fields:
                    if field not in fieldnames:
                        # 在 'nima_score' 之前插入新字段
                        if 'nima_score' in fieldnames:
                            idx = fieldnames.index('nima_score')
                            fieldnames.insert(idx, field)
                        else:
                            fieldnames.append(field)
                
                for row in reader:
                    if row.get('filename') == filename:
                        # 更新关键点数据和评分
                        row['head_sharpness'] = f"{head_sharpness:.0f}" if head_sharpness > 0 else "-"
                        row['left_eye_vis'] = f"{left_eye_vis:.2f}"
                        row['right_eye_vis'] = f"{right_eye_vis:.2f}"
                        row['beak_vis'] = f"{beak_vis:.2f}"
                        row['has_visible_eye'] = "yes" if has_visible_eye else "no"
                        row['has_visible_beak'] = "yes" if has_visible_beak else "no"
                        row['rating'] = str(rating)
                    # 为缺失字段设置默认值
                    for field in new_fields:
                        if field not in row:
                            row[field] = "-"
                    rows.append(row)
            
            # 写回CSV（使用新的字段列表）
            if fieldnames and rows:
                with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            self._log(f"  ⚠️  更新CSV失败: {e}", "warning")
    
    def _calculate_picked_flags(self):
        """计算精选旗标 - 3星照片中美学+锐度双排名交集"""
        if len(self.star_3_photos) == 0:
            self._log("\nℹ️  无3星照片，跳过精选旗标计算")
            return
        
        self._log(f"\n🎯 计算精选旗标 (共{len(self.star_3_photos)}张3星照片)...")
        top_percent = self.config.picked_top_percentage / 100.0
        top_count = max(1, int(len(self.star_3_photos) * top_percent))
        
        # 美学排序
        sorted_by_nima = sorted(self.star_3_photos, key=lambda x: x['nima'], reverse=True)
        nima_top_files = set([photo['file'] for photo in sorted_by_nima[:top_count]])
        
        # 锐度排序
        sorted_by_sharpness = sorted(self.star_3_photos, key=lambda x: x['sharpness'], reverse=True)
        sharpness_top_files = set([photo['file'] for photo in sorted_by_sharpness[:top_count]])
        
        # 交集
        picked_files = nima_top_files & sharpness_top_files
        
        if len(picked_files) > 0:
            self._log(f"  📌 美学Top{self.config.picked_top_percentage}%: {len(nima_top_files)}张")
            self._log(f"  📌 锐度Top{self.config.picked_top_percentage}%: {len(sharpness_top_files)}张")
            self._log(f"  ⭐ 双排名交集: {len(picked_files)}张 → 设为精选")
            
            # 调试：显示精选文件路径
            for file_path in picked_files:
                exists = os.path.exists(file_path)
                self._log(f"    🔍 精选: {os.path.basename(file_path)} (存在: {exists})")
            
            # 批量写入
            picked_batch = [{
                'file': file_path,
                'rating': 3,
                'pick': 1
            } for file_path in picked_files]
            
            exiftool_mgr = get_exiftool_manager()
            picked_stats = exiftool_mgr.batch_set_metadata(picked_batch)
            
            if picked_stats['failed'] == 0:
                self._log(f"  ✅ 精选旗标写入成功")
            else:
                self._log(f"  ⚠️  {picked_stats['failed']} 张精选旗标写入失败", "warning")
            
            self.stats['picked'] = len(picked_files) - picked_stats.get('failed', 0)
        else:
            self._log(f"  ℹ️  双排名交集为空，未设置精选旗标")
            self.stats['picked'] = 0
    
    def _move_files_to_rating_folders(self, raw_dict):
        """移动文件到分类文件夹"""
        # 筛选需要移动的文件（包括所有星级，确保原目录为空）
        files_to_move = []
        for prefix, rating in self.file_ratings.items():
            if rating in [-1, 0, 1, 2, 3] and prefix in raw_dict:
                raw_ext = raw_dict[prefix]
                raw_path = os.path.join(self.dir_path, prefix + raw_ext)
                if os.path.exists(raw_path):
                    # 确定目标文件夹
                    if rating == 2 and prefix in self.star2_reasons:
                        reason = self.star2_reasons[prefix]
                        if reason == 'sharpness':
                            folder = RATING_FOLDER_NAMES["2_sharpness"]
                        elif reason == 'nima':
                            folder = RATING_FOLDER_NAMES["2_nima"]
                        else:
                            folder = RATING_FOLDER_NAMES[2]  # both - 用默认
                    else:
                        folder = RATING_FOLDER_NAMES.get(rating, str(rating))
                    
                    files_to_move.append({
                        'filename': prefix + raw_ext,
                        'rating': rating,
                        'folder': folder
                    })
        
        if not files_to_move:
            self._log("\n📂 无需移动文件")
            return
        
        self._log(f"\n📂 移动 {len(files_to_move)} 张照片到分类文件夹...")
        
        # 创建文件夹（使用实际的目录名）
        folders_in_use = set(f['folder'] for f in files_to_move)
        for folder_name in folders_in_use:
            folder_path = os.path.join(self.dir_path, folder_name)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                self._log(f"  📁 创建文件夹: {folder_name}/")
        
        # 移动文件
        moved_count = 0
        for file_info in files_to_move:
            src_path = os.path.join(self.dir_path, file_info['filename'])
            dst_folder = os.path.join(self.dir_path, file_info['folder'])
            dst_path = os.path.join(dst_folder, file_info['filename'])
            
            try:
                if os.path.exists(dst_path):
                    continue
                shutil.move(src_path, dst_path)
                moved_count += 1
            except Exception as e:
                self._log(f"  ⚠️  移动失败: {file_info['filename']} - {e}", "warning")
        
        # 生成manifest
        manifest = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "app_version": "Refactored-Core",
            "original_dir": self.dir_path,
            "folder_structure": RATING_FOLDER_NAMES,
            "files": files_to_move,
            "stats": {"total_moved": moved_count}
        }
        
        manifest_path = os.path.join(self.dir_path, "_superpicky_manifest.json")
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            self._log(f"  ✅ 已移动 {moved_count} 张照片")
            self._log(f"  📋 Manifest: _superpicky_manifest.json")
        except Exception as e:
            self._log(f"  ⚠️  保存manifest失败: {e}", "warning")
    
    def _cleanup_temp_files(self, files_tbr, raw_dict):
        """清理临时JPG文件"""
        self._log("\n🧹 清理临时文件...")
        deleted_count = 0
        for filename in files_tbr:
            file_prefix, file_ext = os.path.splitext(filename)
            if file_prefix in raw_dict and file_ext.lower() in ['.jpg', '.jpeg']:
                jpg_path = os.path.join(self.dir_path, filename)
                try:
                    if os.path.exists(jpg_path):
                        os.remove(jpg_path)
                        deleted_count += 1
                except Exception as e:
                    self._log(f"  ⚠️  删除失败 {filename}: {e}", "warning")
        
        if deleted_count > 0:
            self._log(f"  ✅ 已删除 {deleted_count} 个临时JPG文件")
        else:
            self._log(f"  ℹ️  无临时文件需清理")
