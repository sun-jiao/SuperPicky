# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SuperPicky (慧眼选鸟) 是一款智能鸟类照片筛选工具，使用多模型AI自动识别、评分和组织鸟类照片。支持 macOS (Apple Silicon/Intel) 和 Windows，提供 GUI (PySide6) 和 CLI 两种界面。

**核心技术栈**: Python 3.12+, PySide6, YOLO11, TOPIQ, PyTorch, OpenCV, ExifTool

## Development Commands

```bash
# 环境设置
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 运行应用
python main.py                                      # GUI 模式
python superpicky_cli.py process ~/Photos/Birds    # CLI 处理
python superpicky_cli.py reset ~/Photos/Birds      # 重置评分
python superpicky_cli.py burst ~/Photos/Birds      # 连拍检测

# macOS 构建与发布
./build_release.sh --test      # 测试构建（跳过公证）
./build_release.sh --release   # 完整发布（签名+公证）
```

## Architecture

### 目录结构
- `core/` - 业务逻辑层，无 UI 依赖
- `ui/` - PySide6 GUI 组件
- `main.py` - GUI 入口
- `superpicky_cli.py` - CLI 入口

### 核心处理流程 (`core/photo_processor.py`)
1. **文件扫描** - 识别 RAW/JPEG，必要时转换 RAW
2. **YOLO 检测** - 鸟类检测与分割 (`ai_model.py`)
3. **关键点检测** - 鸟眼位置、锐度计算 (`keypoint_detector.py`)
4. **TOPIQ 评分** - 美学质量评估 (`topiq_model.py`)
5. **飞版检测** - 飞行姿态识别，额外加分 (`flight_detector.py`)
6. **曝光检测** - 过曝/欠曝检测 (`exposure_detector.py`)
7. **对焦验证** - 对焦点与鸟区域重叠验证 (`focus_point_detector.py`)
8. **连拍检测** - 时间/pHash 分组，选最佳 (`burst_detector.py`)
9. **评分计算** - 0-3星评分 (`rating_engine.py`)
10. **EXIF 写入** - 元数据注入 (`exiftool_manager.py`)
11. **文件整理** - 按星级移动到子文件夹

### 关键设计模式
- **分离关注点**: `core/` 纯业务逻辑，`ui/` 纯界面
- **单一职责**: 每个检测器（Keypoint, Flight, Exposure, Burst, Focus）独立处理一个功能
- **PyInstaller 兼容**: 使用 `get_resource_path()` 获取资源路径，打包时回退到 `sys._MEIPASS`
- **并发处理**: GUI 使用 `WorkerThread`，批量处理使用 `ThreadPoolExecutor`

### 配置管理
- `config.py` - 静态配置类
- `advanced_config.py` - 用户可调设置
- `i18n.py` - 国际化（中/英文）

## Key Files

| 文件 | 用途 |
|------|------|
| `core/photo_processor.py` | 主处理编排器 |
| `exiftool_manager.py` | EXIF 元数据操作 |
| `ui/main_window.py` | 主窗口 GUI |
| `constants.py` | 全局常量、版本号 |
| `SuperPicky.spec` | PyInstaller 打包配置 |
| `build_release.sh` | macOS 构建/签名/公证脚本 |

## Development Notes

### 修改功能时
1. 先改 `core/` 的业务逻辑
2. 用 CLI 测试: `python superpicky_cli.py process test_dir/`
3. 再更新 UI 和 CLI 输出

### EXIF 元数据
所有 EXIF 操作必须通过 `exiftool_manager.py`，支持的字段包括:
- `Rating` (0-5 星)
- `XMP:Pick` (Lightroom 旗标)
- `XMP:Label` (颜色标签)
- 自定义字段: Sharpness, Aesthetic, Species 等

### 国际化
用户界面文本使用 `i18n.get_i18n()` 获取，翻译文件在 `locales/` 目录

### RAW 文件支持
支持格式: NEF, CR2, CR3, ARW, RAF, ORF, RW2, PEF, DNG, 3FR, IIQ

### 打包注意事项
- 模型文件通过 Git LFS 管理 (`.gitattributes`)
- ExifTool 打包在 `exiftool_bundle/` 目录
- macOS 需要签名和公证才能分发
