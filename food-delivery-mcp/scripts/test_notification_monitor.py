#!/usr/bin/env python3
"""测试脚本：后台检测 Android 通知的各种方法

不需要打开通知栏，不影响 RPA 操作
"""

import subprocess
import re
import time
import threading
from dataclasses import dataclass
from typing import Callable


def run_adb(cmd: str, timeout: float = 10.0) -> str:
    """执行 ADB 命令"""
    try:
        result = subprocess.run(
            f"adb shell {cmd}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""


@dataclass
class NotificationInfo:
    """通知信息"""
    package: str
    title: str
    text: str
    when: int
    key: str


# ============================================================
# 方法1: dumpsys notification（推荐）
# ============================================================

def parse_notifications_from_dumpsys(output: str) -> list[NotificationInfo]:
    """解析 dumpsys notification 输出
    
    格式示例：
    NotificationRecord(0x05165c57: pkg=android ...
      ...
      notification=
        ...
        extras={
          android.title=String (标题内容)
          android.text=String (文本内容)
        }
    """
    notifications: list[NotificationInfo] = []
    
    # 找到 Notification List 部分
    list_match = re.search(r'Notification List:\s*\n(.*?)(?=\n  \w|\Z)', output, re.DOTALL)
    if not list_match:
        return notifications
    
    list_section = list_match.group(1)
    
    # 按 NotificationRecord 分割
    records = re.split(r'(?=NotificationRecord\()', list_section)
    
    for record in records:
        if not record.strip() or 'NotificationRecord(' not in record:
            continue
        
        # 提取包名
        pkg_match = re.search(r'pkg=(\S+)', record)
        if not pkg_match:
            continue
        pkg = pkg_match.group(1)
        
        # 提取 key
        key_match = re.search(r'key=([^\s:]+)', record)
        key = key_match.group(1) if key_match else ""
        
        # 提取 when (时间戳)
        when_match = re.search(r'when=(\d+)', record)
        when = int(when_match.group(1)) if when_match else 0
        
        # 提取标题 - android.title=String (xxx)
        title_match = re.search(r'android\.title=String \(([^)]*)\)', record)
        title = title_match.group(1) if title_match else ""
        
        # 提取文本 - android.text=String (xxx)
        text_match = re.search(r'android\.text=String \(([^)]*)\)', record)
        text = text_match.group(1) if text_match else ""
        
        # 也尝试 tickerText
        if not title:
            ticker_match = re.search(r'tickerText=([^\n]+)', record)
            if ticker_match:
                title = ticker_match.group(1).strip()
        
        notifications.append(NotificationInfo(
            package=pkg,
            title=title,
            text=text,
            when=when,
            key=key,
        ))
    
    return notifications


def method_dumpsys_notification() -> list[NotificationInfo]:
    """使用 dumpsys notification 获取当前通知列表
    
    优点：
    - 不需要打开通知栏
    - 可以获取详细的通知信息
    - 不影响 RPA 操作
    
    Returns:
        通知列表
    """
    output = run_adb("dumpsys notification --noredact", timeout=15)
    return parse_notifications_from_dumpsys(output)


def test_method_dumpsys():
    """测试 dumpsys notification 方法"""
    print("\n" + "=" * 60)
    print("方法1: dumpsys notification (推荐)")
    print("=" * 60)
    
    notifications = method_dumpsys_notification()
    
    print(f"共找到 {len(notifications)} 条活跃通知\n")
    
    # 过滤外卖相关
    keywords = ["外卖", "送达", "取餐", "美团", "骑手", "meituan", "sankuai", "饿了么", "ele"]
    
    delivery_notifications = []
    for n in notifications:
        combined = f"{n.title} {n.text} {n.package}".lower()
        if any(kw.lower() in combined for kw in keywords):
            delivery_notifications.append(n)
    
    if delivery_notifications:
        print("🔔 外卖相关通知:")
        for n in delivery_notifications:
            print(f"  - [{n.package}]")
            print(f"    标题: {n.title}")
            print(f"    内容: {n.text}")
    else:
        print("未找到外卖相关通知")
    
    # 显示所有通知
    print(f"\n📋 所有活跃通知 ({len(notifications)} 条):")
    for n in notifications:
        print(f"  - [{n.package}] {n.title or '(无标题)'}")
        if n.text:
            print(f"    {n.text[:50]}{'...' if len(n.text) > 50 else ''}")


# ============================================================
# 方法2: logcat 监听（实时流）
# ============================================================

def method_logcat_stream(
    callback: Callable[[str], None],
    keywords: list[str] | None = None,
    timeout: float = 30.0,
):
    """使用 logcat 实时监听通知
    
    优点：
    - 实时性好
    - 可以捕获通知的创建事件
    
    缺点：
    - 需要持续运行
    - 日志格式可能因系统版本不同而变化
    
    Args:
        callback: 检测到通知时的回调函数
        keywords: 过滤关键词
        timeout: 监听超时时间
    """
    keywords = keywords or ["NotificationService", "美团", "外卖", "送达", "posted"]
    
    # 清空之前的日志
    subprocess.run("adb logcat -c", shell=True)
    
    # 启动 logcat 监听 - 过滤通知相关
    process = subprocess.Popen(
        "adb logcat -v time NotificationService:* *:S",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                continue
            
            # 检查关键词
            if any(kw in line for kw in keywords):
                callback(line.strip())
                
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()


def test_method_logcat():
    """测试 logcat 方法"""
    print("\n" + "=" * 60)
    print("方法2: logcat 实时监听")
    print("=" * 60)
    print("监听 10 秒钟，请在手机上触发一些通知...")
    
    found_notifications = []
    
    def on_notification(line: str):
        found_notifications.append(line)
        print(f"  🔔 {line[:100]}...")
    
    # 在单独线程中运行
    thread = threading.Thread(
        target=method_logcat_stream,
        args=(on_notification,),
        kwargs={"timeout": 10.0},
    )
    thread.start()
    thread.join()
    
    print(f"\n共捕获 {len(found_notifications)} 条相关日志")


# ============================================================
# 推荐方案：基于 dumpsys 的轮询监控（不影响 RPA）
# ============================================================

class BackgroundNotificationMonitor:
    """后台通知监控器 - 基于 dumpsys，完全不影响 RPA"""
    
    def __init__(
        self,
        check_interval: float = 3.0,
        keywords: list[str] | None = None,
    ):
        self.check_interval = check_interval
        self.keywords = keywords or ["外卖", "送达", "取餐", "骑手", "美团", "饿了么"]
        self._running = False
        self._thread: threading.Thread | None = None
        self._seen_keys: set[str] = set()
        self._callbacks: list[Callable[[NotificationInfo], None]] = []
    
    def add_callback(self, callback: Callable[[NotificationInfo], None]):
        """添加通知回调"""
        self._callbacks.append(callback)
    
    def start(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _monitor_loop(self):
        """监控主循环"""
        while self._running:
            try:
                self._check_notifications()
            except Exception as e:
                print(f"检查通知出错: {e}")
            
            time.sleep(self.check_interval)
    
    def _check_notifications(self):
        """检查新通知"""
        notifications = method_dumpsys_notification()
        
        for n in notifications:
            # 用 key 去重（如果没有 key 就用 package + title + text）
            unique_key = n.key or f"{n.package}:{n.title}:{n.text}"
            
            if unique_key in self._seen_keys:
                continue
            
            # 检查关键词
            combined = f"{n.title} {n.text}"
            if any(kw in combined for kw in self.keywords):
                self._seen_keys.add(unique_key)
                
                # 触发回调
                for callback in self._callbacks:
                    try:
                        callback(n)
                    except Exception as e:
                        print(f"回调出错: {e}")
        
        # 清理过期的 seen_keys（保持最多 100 个）
        if len(self._seen_keys) > 100:
            # 简单清理
            self._seen_keys = set(list(self._seen_keys)[-50:])


def test_background_monitor():
    """测试后台监控器"""
    print("\n" + "=" * 60)
    print("推荐方案: 后台轮询监控器 (基于 dumpsys)")
    print("=" * 60)
    print("监控 20 秒，请在手机上触发美团/外卖通知...")
    print("（这个过程不会打开通知栏，不影响 RPA）\n")
    
    monitor = BackgroundNotificationMonitor(check_interval=2.0)
    
    detected_count = [0]  # 用列表包装以便在闭包中修改
    
    def on_delivery_notification(n: NotificationInfo):
        detected_count[0] += 1
        print(f"🔔 [{detected_count[0]}] 检测到外卖通知!")
        print(f"   包名: {n.package}")
        print(f"   标题: {n.title}")
        print(f"   内容: {n.text}")
        print()
    
    monitor.add_callback(on_delivery_notification)
    monitor.start()
    
    # 等待并显示进度
    for i in range(20):
        time.sleep(1)
        print(f"\r⏱ 已监控 {i+1}/20 秒，检测到 {detected_count[0]} 条通知...", end="", flush=True)
    
    print()  # 换行
    monitor.stop()
    print(f"\n监控结束，共检测到 {detected_count[0]} 条外卖相关通知")


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("Android 后台通知检测方法测试")
    print("=" * 60)
    
    # 检查设备连接
    devices = subprocess.run(
        "adb devices",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    
    print(f"连接的设备:\n{devices}")
    
    if "device" not in devices or devices.count("\n") < 3:
        print("错误: 未检测到 Android 设备")
        return
    
    # 测试主要方法
    test_method_dumpsys()
    
    print("\n" + "-" * 60)
    print("\n选择要测试的功能:")
    print("  1. 测试 logcat 实时监听 (10秒)")
    print("  2. 测试后台监控器 (20秒)")
    print("  3. 退出")
    
    try:
        choice = input("\n请选择 (1/2/3): ").strip()
        
        if choice == "1":
            test_method_logcat()
        elif choice == "2":
            test_background_monitor()
    except EOFError:
        # 非交互模式，直接退出
        pass
    
    print("\n" + "=" * 60)
    print("结论:")
    print("  ✅ 推荐使用 dumpsys notification 方法")
    print("  - 不需要打开通知栏")
    print("  - 不影响任何 RPA 操作")
    print("  - 可以获取完整通知信息（包名、标题、内容）")
    print("  - 通过轮询实现监控")
    print("=" * 60)


if __name__ == "__main__":
    main()
