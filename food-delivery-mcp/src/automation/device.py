"""设备连接管理模块"""

import logging
from typing import Any

import uiautomator2 as u2

logger = logging.getLogger(__name__)


class DeviceManager:
    """Android 设备连接管理器"""
    
    def __init__(self):
        self._device: u2.Device | None = None
        self._device_name: str | None = None
    
    def connect(self, device_serial: str | None = None) -> bool:
        """连接设备
        
        Args:
            device_serial: 设备序列号，为 None 时自动连接第一个设备
            
        Returns:
            是否连接成功
        """
        try:
            if device_serial:
                self._device = u2.connect(device_serial)
            else:
                # 自动连接第一个可用设备
                self._device = u2.connect()
            
            # 获取设备信息
            info = self._device.info
            self._device_name = info.get("productName", "Unknown")
            logger.info(f"已连接设备: {self._device_name}")
            return True
            
        except Exception as e:
            logger.error(f"连接设备失败: {e}")
            self._device = None
            self._device_name = None
            return False
    
    @property
    def device(self) -> u2.Device | None:
        """获取设备实例"""
        return self._device
    
    @property
    def device_name(self) -> str | None:
        """获取设备名称"""
        return self._device_name
    
    @property
    def is_connected(self) -> bool:
        """检查设备是否已连接"""
        if self._device is None:
            return False
        try:
            # 尝试获取设备信息来验证连接
            self._device.info
            return True
        except Exception:
            return False
    
    def get_device_info(self) -> dict[str, Any]:
        """获取设备详细信息"""
        if not self.is_connected:
            return {"available": False}
        
        try:
            info = self._device.info  # type: ignore
            return {
                "available": True,
                "device_name": self._device_name,
                "screen_size": f"{info.get('displayWidth', 0)}x{info.get('displayHeight', 0)}",
                "sdk_version": info.get("sdkInt", 0),
            }
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")
            return {"available": False}
    
    def ensure_connected(self) -> u2.Device:
        """确保设备已连接，返回设备实例
        
        Raises:
            RuntimeError: 设备未连接
        """
        if not self.is_connected:
            # 尝试重新连接
            if not self.connect():
                raise RuntimeError("设备未连接，请检查 USB 连接和 ADB 调试")
        return self._device  # type: ignore
    
    def wake_up(self) -> None:
        """唤醒设备屏幕"""
        device = self.ensure_connected()
        if not device.info.get("screenOn", False):
            device.press("power")
            device.sleep(0.5)
    
    def unlock_screen(self) -> None:
        """解锁屏幕（滑动解锁）"""
        device = self.ensure_connected()
        # 简单滑动解锁
        width = device.info.get("displayWidth", 1080)
        height = device.info.get("displayHeight", 1920)
        device.swipe(width // 2, height * 3 // 4, width // 2, height // 4, duration=0.3)


# 全局设备管理器实例
_device_manager: DeviceManager | None = None


def get_device_manager() -> DeviceManager:
    """获取全局设备管理器实例"""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager

