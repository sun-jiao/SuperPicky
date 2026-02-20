#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 img/icon.png 生成 Windows 用 icon.ico（多尺寸：16, 32, 48, 256）。
运行方式：在项目根目录执行 python scripts_dev/make_icon_ico.py
"""
import os
import sys

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(base, "img", "icon.png")
    dst = os.path.join(base, "img", "icon.ico")
    if not os.path.exists(src):
        print("ERROR: not found:", src)
        return 1
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow required. pip install Pillow")
        return 1
    sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
    img = Image.open(src).convert("RGBA")
    img.save(dst, format="ICO", sizes=sizes)
    print("Created:", dst)
    return 0

if __name__ == "__main__":
    sys.exit(main())
