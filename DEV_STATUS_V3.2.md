# SuperPicky 开发状态文档 (V3.2)

**最后更新日期**: 2025-12-28
**当前版本**: V3.2.1

## 🚧 项目概述
SuperPicky 是一个 AI 驱动的鸟类摄影选片工具，利用 YOLOv11-pose 和 NIMA 模型自动筛选和评分。

**核心功能**:
- RAW (NEF) 快速预览提取与转换
- YOLOv11 鸟类检测与关键点识别 (眼睛/喙)
- 头部区域锐度计算 (Head Sharpness)
- NIMA 美学评分 (排除背景干扰)
- 自动星级评定 (Rating) 与 精选 (Pick)
- EXIF 元数据回写 (兼容 Lightroom)

---

## ✅ 已完成功能 (V3.2)

### 1. 核心流程优化 (Photo Processor)
- **RAW 内嵌 JPEG 提取**: 使用 `rawpy.extract_thumb()` 提取 RAW 文件内嵌的高分辨率 JPEG（通常为全尺寸或接近全尺寸），确保锐度计算的准确性。
- **YOLO 快速推理**: 提取的 JPEG 在 YOLO 推理前会缩放至 640px（由 `config.ai.TARGET_IMAGE_SIZE` 控制），以加速检测。
- **单次读取**: 原图只读取一次，在内存中裁剪后分别传给 Keypoint Detector 和 NIMA Scorer，避免重复 IO。
- **并行处理**: RAW 转换与 AI 推理流水线作业，榨干 CPU/GPU 性能。

### 2. 评分引擎 (Rating Engine)
- **移除了 BRISQUE**: 彻底移除旧的 BRISQUE 算法及其依赖。
- **移除了全局锐度**: 不再计算全图拉普拉斯方差，改用 **Head Sharpness** (关键点区域)。
- **NIMA 优化**: 仅在鸟眼可见时计算 NIMA，且仅计算**鸟类裁剪区域**，大幅提高准确性并减少计算量。
- **阈值体系**:
  - **默认锐度阈值**: 500 (头部区域，由 GUI 滑块控制)
  - **默认 NIMA 阈值**: 5.0 (裁剪区域，由 GUI 滑块控制)
  - **最低置信度**: 0.50 (低于此值判定为 0 星)
  - **最低 NIMA**: 4.0 (低于此值判定为 0 星)
  - **最低锐度**: 250 (低于此值判定为 0 星)
  - **精选旗标**: Top 25% (美学+锐度双排名交集)
  - **星级规则**: 
    - 3星: 锐度 ≥ GUI阈值 **且** NIMA ≥ 5.0
    - 2星: 锐度 ≥ GUI阈值 **或** NIMA ≥ 5.0
    - 1星: 通过最低标准但都不达标
    - 0星: 置信度低 / 美学太差 / 锐度太低 / 双眼不可见
    - -1星: 未检测到鸟
  - **多鸟处理**: 选择置信度最高的检测框进行评分

### 3. 工程化与清理
- **死代码移除**: 清理了 `ai_model.py` 中未使用的评分逻辑。
- **参数解耦**: `advanced_config.py` 管理底层参数，`main.py` 管理用户交互参数。
- **重置功能**: 完善了目录重置和 EXIF 清除功能。

---

## ⚠️ 待办事项 / 已知问题 (Handover Notes)

### 1. 优先级高 (High Priority)
- **主界面设置持久化**: 目前主界面上的阈值 (锐度/NIMA/置信度) **重启后会重置**。需要实现 `QSettings` 或 JSON 保存逻辑（类似 `AdvancedSettingsDialog`）。
- **小鸟检测稳定性**: 在 640px 预览图上，极小的鸟 (<2% 面积) 可能漏检。需评估是否需要"二次回退"机制（即 640 没检测到时尝试原图）。

### 2. 优化建议 (Improvements)
- **NIMA 模型加载**: 目前 NIMA 模型在第一次推理时加载，导致第一张图处理慢 (~2s)。可以改为在 App 启动时预加载。
- **多语言支持**: i18n 框架已搭建，但部分新加的日志还是硬编码中文，需要抽离到 `locales/*.json`。

### 3. 代码结构
- **ai_model.py**: 现在的职责只剩下 YOLO 推理。建议重命名为 `yolo_detector.py`。
- **utils.py**: 里面残留了一些旧的 CSV 字段定义注释，可以进一步清理。

---

## 🔧 开发调试指南

### 关键文件
- `core/photo_processor.py`: 核心业务流程 (Process Loop)
- `core/rating_engine.py`: 评分规则逻辑
- `core/keypoint_detector.py`: 关键点检测与头部裁剪
- `ai_model.py`: YOLO 模型封装

### 调试脚本
- `scripts/v32_performance_test.py`: 随机抽取 50 张图进行全流程性能测试。
- `scripts/preview_vs_full_benchmark.py`: 对比 640px vs 全尺寸检测效果。

### 常用命令
```bash
# 运行性能测试
python scripts/v32_performance_test.py

# 重置测试目录 (慎用)
python -c "from find_bird_util import reset; reset('/path/to/dir')"
```

---

**致接手者**: 
V3.2 版本已经是一个性能和效果都非常平衡的稳定版本。主要的工作重心可以转向 UI 体验优化（设置保存、进度显示细节）以及边缘情况（极小目标、特殊光照）的测试。祝你好运！🚀
