#!/usr/bin/env python3
"""
SuperPicky BirdID 服务器管理器
管理 API 服务器的生命周期：启动、停止、状态检查
支持守护进程模式，使服务器可以独立于 GUI 运行
"""

import os
import sys
import signal
import socket
import subprocess
import time
import json

# PID 文件位置
def get_pid_file_path():
    """获取 PID 文件路径"""
    if sys.platform == 'darwin':
        pid_dir = os.path.expanduser('~/Library/Application Support/SuperPicky')
    else:
        pid_dir = os.path.expanduser('~/.superpicky')
    os.makedirs(pid_dir, exist_ok=True)
    return os.path.join(pid_dir, 'birdid_server.pid')


def get_server_script_path():
    """获取服务器脚本路径"""
    # 支持开发模式和打包模式
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'birdid_server.py')


def is_port_in_use(port, host='127.0.0.1'):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def check_server_health(port=5156, host='127.0.0.1', timeout=2):
    """检查服务器健康状态"""
    try:
        import urllib.request
        url = f'http://{host}:{port}/health'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('status') == 'ok'
    except Exception:
        pass
    return False


def read_pid():
    """读取 PID 文件"""
    pid_file = get_pid_file_path()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            pass
    return None


def write_pid(pid):
    """写入 PID 文件"""
    pid_file = get_pid_file_path()
    with open(pid_file, 'w') as f:
        f.write(str(pid))


def remove_pid():
    """删除 PID 文件"""
    pid_file = get_pid_file_path()
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
        except OSError:
            pass


def is_process_running(pid):
    """检查进程是否存在"""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # 发送信号 0 检查进程是否存在
        return True
    except (OSError, ProcessLookupError):
        return False


def get_server_status(port=5156):
    """
    获取服务器状态
    
    Returns:
        dict: {
            'running': bool,
            'pid': int or None,
            'healthy': bool,
            'port': int
        }
    """
    pid = read_pid()
    process_running = is_process_running(pid)
    port_in_use = is_port_in_use(port)
    healthy = check_server_health(port)
    
    return {
        'running': process_running or port_in_use,
        'pid': pid if process_running else None,
        'healthy': healthy,
        'port': port
    }


def start_server_daemon(port=5156, log_callback=None):
    """
    以守护进程模式启动服务器
    
    Args:
        port: 监听端口
        log_callback: 日志回调函数
        
    Returns:
        tuple: (success: bool, message: str, pid: int or None)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
    
    # 检查是否已经运行
    status = get_server_status(port)
    if status['healthy']:
        log(f"✅ 服务器已在端口 {port} 运行")
        return True, "服务器已运行", status['pid']
    
    # 如果端口被占用但不健康，可能是僵尸进程
    if status['running'] and not status['healthy']:
        log("⚠️ 检测到僵尸进程，尝试清理...")
        stop_server()
        time.sleep(1)
    
    # 获取脚本路径
    server_script = get_server_script_path()
    if not os.path.exists(server_script):
        return False, f"服务器脚本不存在: {server_script}", None
    
    # 获取 Python 解释器路径
    python_exe = sys.executable
    
    # 构建启动命令
    cmd = [python_exe, server_script, '--port', str(port)]
    
    log(f"🚀 启动守护进程: {' '.join(cmd)}")
    
    try:
        # 以守护进程方式启动（分离子进程）
        if sys.platform == 'darwin':
            # macOS: 使用 start_new_session 分离进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # 创建新会话，脱离父进程
                close_fds=True
            )
        else:
            # Windows/Linux
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0,
                start_new_session=True if sys.platform != 'win32' else False
            )
        
        # 记录 PID
        write_pid(process.pid)
        log(f"📝 服务器 PID: {process.pid}")
        
        # 等待服务器启动
        for i in range(10):  # 最多等待 5 秒
            time.sleep(0.5)
            if check_server_health(port):
                log(f"✅ 服务器已启动，端口 {port}")
                return True, "服务器启动成功", process.pid
        
        # 检查进程是否还在
        if is_process_running(process.pid):
            log("⚠️ 服务器进程已启动，但健康检查未通过")
            return True, "服务器启动中", process.pid
        else:
            log("❌ 服务器进程已退出")
            remove_pid()
            return False, "服务器启动失败", None
            
    except Exception as e:
        log(f"❌ 启动失败: {e}")
        return False, str(e), None


def stop_server(log_callback=None):
    """
    停止服务器
    
    Returns:
        tuple: (success: bool, message: str)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
    
    pid = read_pid()
    
    if pid and is_process_running(pid):
        log(f"🛑 停止服务器 (PID: {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
            
            # 等待进程退出
            for i in range(10):
                time.sleep(0.3)
                if not is_process_running(pid):
                    break
            
            # 如果还没退出，强制终止
            if is_process_running(pid):
                log("⚠️ 进程未响应，强制终止...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
            
            remove_pid()
            log("✅ 服务器已停止")
            return True, "服务器已停止"
            
        except (ProcessLookupError, PermissionError) as e:
            log(f"⚠️ 停止进程失败: {e}")
            remove_pid()
            return False, str(e)
    else:
        # 清理可能的僵尸 PID 文件
        remove_pid()
        log("ℹ️ 服务器未运行")
        return True, "服务器未运行"


def restart_server(port=5156, log_callback=None):
    """重启服务器"""
    stop_server(log_callback)
    time.sleep(1)
    return start_server_daemon(port, log_callback)


# 命令行入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='BirdID 服务器管理器')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'],
                        help='操作: start/stop/restart/status')
    parser.add_argument('--port', type=int, default=5156, help='端口号')
    
    args = parser.parse_args()
    
    if args.action == 'start':
        success, msg, pid = start_server_daemon(args.port)
        print(msg)
        sys.exit(0 if success else 1)
        
    elif args.action == 'stop':
        success, msg = stop_server()
        print(msg)
        sys.exit(0 if success else 1)
        
    elif args.action == 'restart':
        success, msg, pid = restart_server(args.port)
        print(msg)
        sys.exit(0 if success else 1)
        
    elif args.action == 'status':
        status = get_server_status(args.port)
        print(f"运行状态: {'运行中' if status['running'] else '未运行'}")
        print(f"健康状态: {'正常' if status['healthy'] else '异常'}")
        print(f"PID: {status['pid'] or 'N/A'}")
        print(f"端口: {status['port']}")
        sys.exit(0 if status['healthy'] else 1)
