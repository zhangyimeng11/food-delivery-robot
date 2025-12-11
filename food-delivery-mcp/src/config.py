"""配置加载模块"""

from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8765


class LLMConfig(BaseModel):
    """LLM 配置"""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


class NotificationConfig(BaseModel):
    """通知监听配置"""
    enabled: bool = True
    check_interval: int = 3
    keywords: list[str] = [
        "外卖已送达",
        "订单已完成",
        "骑手已送达",
        "已送达",
        "请取餐",
    ]


class RobotConfig(BaseModel):
    """机器人通知配置"""
    enabled: bool = False
    api_url: str = "http://localhost:8000/robot/notify"
    api_key: str = ""


class PlatformConfig(BaseModel):
    """平台通知配置"""
    enabled: bool = False
    webhook_url: str = ""
    api_key: str = ""


class Config(BaseModel):
    """应用配置"""
    server: ServerConfig = ServerConfig()
    llm: LLMConfig = LLMConfig()
    notification: NotificationConfig = NotificationConfig()
    robot: RobotConfig = RobotConfig()
    platform: PlatformConfig = PlatformConfig()


def load_config(config_path: str | Path | None = None) -> Config:
    """加载配置文件
    
    Args:
        config_path: 配置文件路径，默认为项目根目录的 config.yaml
        
    Returns:
        Config 对象
    """
    if config_path is None:
        # 默认配置文件路径
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        # 配置文件不存在，使用默认配置
        return Config()
    
    with open(config_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    
    return Config(**data)


# 全局配置实例
_config: Config | None = None


def get_config() -> Config:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: str | Path | None = None) -> Config:
    """重新加载配置"""
    global _config
    _config = load_config(config_path)
    return _config

