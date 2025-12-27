"""配置加载模块"""

from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8765


class PhoneConfig(BaseModel):
    """手机配置（ADB 连接）"""
    ip: str = "192.168.124.9"
    adb_port: int = 5555


class LLMConfig(BaseModel):
    """LLM 配置"""
    api_key: str = ""  # 留空则使用环境变量 OPENAI_API_KEY


class Config(BaseModel):
    """应用配置"""
    server: ServerConfig = ServerConfig()
    phone: PhoneConfig = PhoneConfig()
    llm: LLMConfig = LLMConfig()


def load_config(config_path: str | Path | None = None) -> Config:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
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
