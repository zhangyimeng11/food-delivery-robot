"""美团拼好饭 MCP 服务 - FastAPI 主入口"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import get_config, Config
from .schemas import (
    HealthResponse,
    DeviceInfo,
    ToolsListResponse,
    ToolCallRequest,
    ToolCallResponse,
    ContentItem,
)
from .tools.registry import ToolRegistry
from .tools.search_meals import SearchMealsTool
from .tools.place_order import PlaceOrderTool
from .tools.check_order import CheckOrderTool
from .automation.device import get_device_manager
from .notification.monitor import NotificationMonitor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 全局对象
tool_registry = ToolRegistry()
notification_monitor: NotificationMonitor | None = None


def setup_tools() -> None:
    """注册所有工具"""
    tool_registry.register(SearchMealsTool())
    tool_registry.register(PlaceOrderTool())
    tool_registry.register(CheckOrderTool())
    logger.info(f"已注册 {len(tool_registry.list_tools())} 个工具")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global notification_monitor
    
    # 启动时
    logger.info("启动美团拼好饭 MCP 服务")
    
    # 注册工具
    setup_tools()
    
    # 连接设备
    dm = get_device_manager()
    if dm.connect():
        logger.info(f"设备已连接: {dm.device_name}")
    else:
        logger.warning("设备未连接，请检查 USB 连接")
    
    # 启动通知监听（如果配置启用）
    config = get_config()
    if config.notification.enabled:
        notification_monitor = NotificationMonitor(config)
        notification_monitor.start()
        logger.info("通知监听已启动")
    
    yield
    
    # 关闭时
    if notification_monitor:
        notification_monitor.stop()
        logger.info("通知监听已停止")
    
    logger.info("服务已停止")


# 创建 FastAPI 应用
app = FastAPI(
    title="美团拼好饭 MCP 服务",
    description="通过自动化操作手机实现语音点餐",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查接口"""
    dm = get_device_manager()
    
    return HealthResponse(
        status="healthy",
        device=DeviceInfo(
            available=dm.is_connected,
            device_name=dm.device_name,
        ),
    )


@app.post("/tools/list", response_model=ToolsListResponse)
async def list_tools() -> ToolsListResponse:
    """获取工具列表"""
    tools = tool_registry.list_tools()
    return ToolsListResponse(tools=tools)


@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """调用工具"""
    try:
        result = await tool_registry.call(request.name, request.arguments)
        
        return ToolCallResponse(
            content=[
                ContentItem(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False),
                )
            ],
            isError=not result.get("success", True),
        )
        
    except ValueError as e:
        # 工具不存在
        return ToolCallResponse(
            content=[
                ContentItem(
                    type="text",
                    text=json.dumps({"error": str(e)}, ensure_ascii=False),
                )
            ],
            isError=True,
        )
        
    except Exception as e:
        logger.error(f"工具调用失败: {e}")
        return ToolCallResponse(
            content=[
                ContentItem(
                    type="text",
                    text=json.dumps({"error": f"内部错误: {e}"}, ensure_ascii=False),
                )
            ],
            isError=True,
        )


def main() -> None:
    """主函数"""
    config = get_config()
    
    logger.info(f"启动服务: {config.server.host}:{config.server.port}")
    
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

