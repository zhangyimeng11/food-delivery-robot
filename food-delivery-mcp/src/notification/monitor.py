"""通知监听模块 - 后台检测外卖送达通知

使用 dumpsys notification 命令后台读取通知，
不需要打开通知栏，不影响 RPA 操作
"""

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Set

import httpx

from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class NotificationInfo:
    """通知信息"""
    package: str
    title: str
    text: str
    when: int
    key: str


def _run_adb(cmd: str, timeout: float = 10.0) -> str:
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
        logger.warning(f"ADB 命令超时: {cmd}")
        return ""
    except Exception as e:
        logger.error(f"ADB 命令失败: {e}")
        return ""


def _parse_notifications_from_dumpsys(output: str) -> list[NotificationInfo]:
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


def get_current_notifications() -> list[NotificationInfo]:
    """获取当前所有通知（后台方式，不影响 RPA）
    
    Returns:
        通知列表
    """
    output = _run_adb("dumpsys notification --noredact", timeout=15)
    return _parse_notifications_from_dumpsys(output)


class NotificationMonitor:
    """通知监听器 - 后台轮询检测，不影响 RPA 操作
    
    使用 dumpsys notification 命令读取通知，
    完全不需要打开通知栏或进行任何 UI 操作
    """
    
    def __init__(self, config: Config):
        self._config = config
        self._running = False
        self._thread: threading.Thread | None = None
        self._seen_keys: Set[str] = set()
        self._max_seen_cache = 100
        self._callbacks: list[Callable[[NotificationInfo], None]] = []
    
    def add_callback(self, callback: Callable[[NotificationInfo], None]) -> None:
        """添加通知回调函数"""
        self._callbacks.append(callback)
    
    def start(self) -> None:
        """启动通知监听（后台线程）"""
        if self._running:
            logger.warning("通知监听已在运行")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("通知监听已启动（后台模式，不影响 RPA）")
    
    def stop(self) -> None:
        """停止通知监听"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("通知监听已停止")
    
    def _monitor_loop(self) -> None:
        """监听主循环"""
        interval = self._config.notification.check_interval
        
        while self._running:
            try:
                self._check_notifications()
            except Exception as e:
                logger.error(f"检查通知失败: {e}")
            
            time.sleep(interval)
    
    def _check_notifications(self) -> None:
        """检查通知（后台方式）"""
        notifications = get_current_notifications()
        
        if not notifications:
            return
        
        keywords = self._config.notification.keywords
        
        for n in notifications:
            # 用 key 去重（如果没有 key 就用 package + when + text 组合）
            unique_key = n.key or f"{n.package}:{n.when}:{n.text[:30]}"
            
            if unique_key in self._seen_keys:
                continue
            
            # 检查关键词匹配
            combined = f"{n.title} {n.text}"
            matched = any(kw in combined for kw in keywords)
            
            if matched:
                logger.info(f"检测到外卖通知: [{n.package}] {n.title}")
                self._seen_keys.add(unique_key)
                self._handle_delivery_notification(n)
                
                # 触发回调
                for callback in self._callbacks:
                    try:
                        callback(n)
                    except Exception as e:
                        logger.error(f"通知回调出错: {e}")
        
        # 清理过期缓存
        if len(self._seen_keys) > self._max_seen_cache:
            self._seen_keys = set(list(self._seen_keys)[-self._max_seen_cache // 2:])
    
    def _handle_delivery_notification(self, n: NotificationInfo) -> None:
        """处理送达通知"""
        timestamp = time.time()
        message = f"{n.title} | {n.text}"
        
        # 通知机器人
        if self._config.robot.enabled:
            self._notify_robot(message, timestamp)
        
        # 通知平台
        if self._config.platform.enabled:
            self._notify_platform(n.text or n.title, timestamp)
    
    def _notify_robot(self, message: str, timestamp: float) -> None:
        """通知机器人 API"""
        config = self._config.robot
        
        try:
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            
            payload = {
                "action": "delivery_arrived",
                "message": message,
                "timestamp": timestamp,
            }
            
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    config.api_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                logger.info(f"已通知机器人: {response.status_code}")
                
        except Exception as e:
            logger.error(f"通知机器人失败: {e}")
    
    def _notify_platform(self, text: str, timestamp: float) -> None:
        """通知平台 Webhook"""
        config = self._config.platform
        
        try:
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            
            payload = {
                "event": "delivery_notification",
                "text": text,
                "timestamp": timestamp,
            }
            
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    config.webhook_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                logger.info(f"已通知平台: {response.status_code}")
                
        except Exception as e:
            logger.error(f"通知平台失败: {e}")
