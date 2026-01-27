#!/usr/bin/env python3
"""批量生成 TTS 语音"""

import requests
import base64
import os

API_URL = "http://localhost:8765/qwen3/tts"
OUTPUT_DIR = "/Users/jameszhenyu/Documents/JamesAPPS/SuperPicky2026/promo_video/audio"

# 创建输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)

# TTS 文案段落
segments = [
    ("01_hook", "拍片一时爽，选片火葬场"),
    ("02_problem", "800张照片，哪张最锐？让AI帮你3分钟搞定"),
    ("03_feature1", "自动检测鸟眼位置"),
    ("04_feature2", "计算头部锐度"),
    ("05_feature3", "识别飞行姿态"),
    ("06_feature4", "一键评分分类"),
    ("07_result", "精选照片，张张能打"),
    ("08_cta", "免费下载 able SuperPicky 慧眼选鸟"),
]

def generate_tts(filename, text):
    """调用 TTS API 生成语音"""
    payload = {
        "text": text,
        "language": "Chinese",
        "speaker": "Vivian",
        "output_format": "wav"
    }

    print(f"生成: {filename} - {text}")

    response = requests.post(API_URL, json=payload)
    result = response.json()

    if result.get("success"):
        # 解码 base64 音频并保存
        audio_data = base64.b64decode(result["audio_base64"])
        output_path = os.path.join(OUTPUT_DIR, f"{filename}.wav")
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"  ✓ 已保存: {output_path} (时长: {result.get('duration', 0):.2f}秒)")
        return result.get("duration", 0)
    else:
        print(f"  ✗ 失败: {result.get('message', 'Unknown error')}")
        return 0

if __name__ == "__main__":
    total_duration = 0

    print("=" * 50)
    print("开始生成 TTS 语音")
    print("=" * 50)

    for filename, text in segments:
        duration = generate_tts(filename, text)
        total_duration += duration

    print("=" * 50)
    print(f"完成! 总时长: {total_duration:.2f}秒")
    print(f"音频文件保存在: {OUTPUT_DIR}")
    print("=" * 50)
