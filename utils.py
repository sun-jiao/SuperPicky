"""
工具函数模块
提供日志记录和CSV报告功能
"""
import os
import csv
from datetime import datetime


def log_message(message: str, directory: str = None, file_only: bool = False):
    """
    记录日志消息到控制台和日志文件

    Args:
        message: 日志消息
        directory: 工作目录（可选，如果提供则写入该目录/.superpicky/process_log.txt）
        file_only: 仅写入文件，不打印到控制台（避免重复输出）
    """
    # 打印到控制台（除非指定只写文件）
    if not file_only:
        print(message)

    # 如果提供了目录，写入日志文件到_tmp子目录
    if directory:
        # 确保_tmp目录存在
        tmp_dir = os.path.join(directory, ".superpicky")
        os.makedirs(tmp_dir, exist_ok=True)

        log_file = os.path.join(tmp_dir, "process_log.txt")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")


def write_to_csv(data: dict, directory: str, header: bool = False):
    """
    将数据写入CSV报告文件

    Args:
        data: 要写入的数据字典（如果为None且header=True，则只创建文件并写表头）
        directory: 工作目录
        header: 是否写入表头（第一次写入时为True）
    """
    # 确保_tmp目录存在
    tmp_dir = os.path.join(directory, ".superpicky")
    os.makedirs(tmp_dir, exist_ok=True)

    report_file = os.path.join(tmp_dir, "report.csv")

    # 定义CSV列顺序
    # V3.2: 移除 brisque_score, sharpness_raw, sharpness_norm, norm_method（由keypoint_detector计算head_sharpness替代）
    # V3.3: 移除 center_x, center_y, area_ratio, bbox_width, bbox_height, mask_pixels（无实际用途）
    # V3.3: 字段名改为中文
    fieldnames = [
        "文件名",           # 文件名（不含扩展名）
        "有鸟",             # 是否有鸟 (yes/no)
        "置信度",           # AI置信度 (0-1)
        "头部锐度",         # 头部区域锐度（关键点检测）
        "左眼可见",         # 左眼可见性置信度 (0-1)
        "右眼可见",         # 右眼可见性置信度 (0-1)
        "喙可见",           # 喙可见性置信度 (0-1)
        "眼睛可见",         # 是否有可见鸟眼 (yes/no)
        "喙部可见",         # 是否有可见鸟喙 (yes/no)
        "美学评分",         # NIMA美学评分 (1-10)
        "星级"              # 最终评分 (-1/0/1/2/3)
    ]

    try:
        # 如果是初始化表头（data为None）
        if data is None and header:
            with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            return

        file_exists = os.path.exists(report_file)
        mode = 'a' if file_exists else 'w'

        with open(report_file, mode, newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # 如果文件不存在或者明确要求写表头，则写入表头
            if not file_exists or header:
                writer.writeheader()

            if data:
                writer.writerow(data)
    except Exception as e:
        log_message(f"Warning: Could not write to CSV file: {e}", directory)
