---
description: 开发测试说明 - Development Setup Guide
---

# SuperPicky 开发环境设置

## 虚拟环境

本项目使用 `.venv` 虚拟环境管理依赖。

### 激活虚拟环境

```bash
# 方式1: 激活虚拟环境后运行
source .venv/bin/activate
python3 your_script.py

# 方式2: 直接使用虚拟环境中的 Python
.venv/bin/python3 your_script.py
```

### 注意事项

- **不要使用系统的 `python3` 或 Conda 的 `python3`**，否则会报模块找不到的错误（如 `ModuleNotFoundError: No module named 'rawpy'`）
- 项目依赖（如 `rawpy`, `PySide6`, `torch` 等）都安装在 `.venv` 中

## 运行应用

```bash
# // turbo
.venv/bin/python3 main.py
```

## 运行验证测试

```bash
# // turbo
.venv/bin/python3 -c "from core.photo_processor import ProcessingSettings; print('OK')"
```

## 安装新依赖

```bash
.venv/bin/pip install <package_name>
```
