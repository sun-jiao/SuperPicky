#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SuperPicky - 更新检测器
检查 GitHub Releases 获取最新版本，支持 Mac/Windows 分平台下载
"""

import sys
import urllib.request
import json
import re
from typing import Optional, Tuple, Dict
from packaging import version


# 当前版本号（与 main_window.py 保持一致）
CURRENT_VERSION = "3.9.5"

# GitHub API 配置
GITHUB_REPO = "jamesphotography/SuperPicky"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

# 平台对应的 Asset 文件名模式
PLATFORM_PATTERNS = {
    'darwin': ['.dmg', '-mac', '_mac', 'macos', 'osx'],
    'win32': ['.exe', '.msi', '-win', '_win', 'windows', '-setup'],
}


class UpdateChecker:
    """更新检测器"""
    
    def __init__(self, current_version: str = CURRENT_VERSION):
        self.current_version = current_version
        self._latest_info: Optional[Dict] = None
    
    def check_for_updates(self, timeout: int = 10) -> Tuple[bool, Optional[Dict]]:
        """
        检查是否有更新
        
        Args:
            timeout: 请求超时时间（秒）
            
        Returns:
            (has_update, update_info) - update_info 包含:
                - version: 最新版本号
                - download_url: 当前平台的下载链接
                - release_notes: 发布说明
                - release_url: GitHub Release 页面链接
        """
        try:
            # 请求 GitHub API
            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': f'SuperPicky/{self.current_version}'
                }
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            self._latest_info = data
            
            # 解析版本号
            latest_version = data.get('tag_name', '').lstrip('vV')
            if not latest_version:
                return False, None
            
            # 比较版本
            try:
                has_update = version.parse(latest_version) > version.parse(self.current_version)
            except Exception:
                # 简单字符串比较作为回退
                has_update = latest_version != self.current_version
            
            if not has_update:
                return False, None
            
            # 获取当前平台的下载链接
            download_url = self._find_platform_download(data.get('assets', []))
            
            update_info = {
                'version': latest_version,
                'download_url': download_url,
                'release_notes': data.get('body', ''),
                'release_url': data.get('html_url', GITHUB_RELEASES_URL),
                'published_at': data.get('published_at', ''),
            }
            
            return True, update_info
            
        except urllib.error.URLError as e:
            print(f"⚠️ 检查更新失败 (网络错误): {e}")
            return False, None
        except json.JSONDecodeError as e:
            print(f"⚠️ 检查更新失败 (解析错误): {e}")
            return False, None
        except Exception as e:
            print(f"⚠️ 检查更新失败: {e}")
            return False, None
    
    def _find_platform_download(self, assets: list) -> Optional[str]:
        """
        根据当前平台查找对应的下载链接
        
        Args:
            assets: GitHub Release 的 assets 列表
            
        Returns:
            下载链接或 None
        """
        if not assets:
            return None
        
        # 确定当前平台的模式
        platform_key = 'darwin' if sys.platform == 'darwin' else 'win32'
        patterns = PLATFORM_PATTERNS.get(platform_key, [])
        
        # 遍历 assets 查找匹配
        for asset in assets:
            name = asset.get('name', '').lower()
            download_url = asset.get('browser_download_url', '')
            
            for pattern in patterns:
                if pattern.lower() in name:
                    return download_url
        
        # 如果没有找到平台特定的，返回第一个（可能是通用包）
        if assets:
            return assets[0].get('browser_download_url')
        
        return None
    
    @staticmethod
    def get_platform_name() -> str:
        """获取当前平台名称（用于UI显示）"""
        if sys.platform == 'darwin':
            return 'macOS'
        elif sys.platform.startswith('win'):
            return 'Windows'
        else:
            return 'Linux'


def check_update_async(callback, current_version: str = CURRENT_VERSION):
    """
    异步检查更新（在后台线程执行）
    
    Args:
        callback: 回调函数，签名 callback(has_update: bool, update_info: Optional[Dict])
        current_version: 当前版本号
    """
    import threading
    
    def _check():
        checker = UpdateChecker(current_version)
        has_update, update_info = checker.check_for_updates()
        callback(has_update, update_info)
    
    thread = threading.Thread(target=_check, daemon=True)
    thread.start()


# 测试代码
if __name__ == "__main__":
    print("=== SuperPicky 更新检测器测试 ===\n")
    print(f"当前版本: {CURRENT_VERSION}")
    print(f"当前平台: {UpdateChecker.get_platform_name()}\n")
    
    checker = UpdateChecker()
    has_update, info = checker.check_for_updates()
    
    if has_update:
        print(f"✅ 发现新版本: {info['version']}")
        print(f"📦 下载链接: {info['download_url']}")
        print(f"🔗 Release 页面: {info['release_url']}")
        print(f"\n📝 发布说明:\n{info['release_notes'][:500]}...")
    else:
        print("✅ 已是最新版本")
