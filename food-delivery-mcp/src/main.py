"""美团拼好饭 MCP 服务 - 使用官方 FastMCP 实现"""

import json
import logging
import asyncio
from contextlib import asynccontextmanager

from mcp.server import FastMCP
from starlette.responses import JSONResponse
from starlette.requests import Request

from .config import get_config, Config
from .automation.device import get_device_manager
from .notification.monitor import NotificationMonitor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 全局对象
notification_monitor: NotificationMonitor | None = None

# 创建 FastMCP 服务器
mcp = FastMCP(
    name="美团拼好饭 MCP 服务",
    instructions="通过自动化操作手机实现语音点餐",
    host="0.0.0.0",
    port=8765,
    sse_path="/sse",
    message_path="/messages/",
)


# ========== 工具定义 ==========

@mcp.tool()
async def search_meals(keyword: str, price_max: float = 30.0) -> dict:
    """
    搜索美团拼好饭的餐品
    
    Args:
        keyword: 搜索关键词，如"黄焖鸡"、"麻辣烫"
        price_max: 最高价格限制，默认30元
    
    Returns:
        搜索结果列表，包含餐品名称、价格、店铺等信息
    """
    from .tools.search_meals import SearchMealsTool
    tool = SearchMealsTool()
    result = await tool.execute({"keyword": keyword, "price_max": price_max})
    return result


@mcp.tool()
async def place_order(meal_id: str, quantity: int = 1) -> dict:
    """
    下单购买指定餐品
    
    Args:
        meal_id: 餐品ID（从搜索结果中获取）
        quantity: 购买数量，默认1份
    
    Returns:
        下单结果，包含订单号、预计送达时间等
    """
    from .tools.place_order import PlaceOrderTool
    tool = PlaceOrderTool()
    result = await tool.execute({"meal_id": meal_id, "quantity": quantity})
    return result


@mcp.tool()
async def check_order(order_id: str = "") -> dict:
    """
    查看订单状态
    
    Args:
        order_id: 订单号（可选，不填则查看最近订单）
    
    Returns:
        订单状态信息，包含配送进度、骑手信息等
    """
    from .tools.check_order import CheckOrderTool
    tool = CheckOrderTool()
    result = await tool.execute({"order_id": order_id})
    return result


# ========== 自定义路由 ==========

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查接口"""
    dm = get_device_manager()
    return JSONResponse({
        "status": "healthy",
        "device": {
            "available": dm.is_connected,
            "device_name": dm.device_name,
        }
    })


# ========== 兼容旧 API ==========
# 保留旧的 /tools/list 和 /tools/call 端点用于向后兼容

@mcp.custom_route("/tools/list", methods=["POST"])
async def list_tools_legacy(request: Request) -> JSONResponse:
    """兼容旧的工具列表接口"""
    tools = [
        {
            "name": "search_meals",
            "description": "搜索美团拼好饭的餐品",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "price_max": {"type": "number", "description": "最高价格限制"}
                },
                "required": ["keyword"]
            }
        },
        {
            "name": "place_order", 
            "description": "下单购买指定餐品",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "meal_id": {"type": "string", "description": "餐品ID"},
                    "quantity": {"type": "integer", "description": "购买数量"}
                },
                "required": ["meal_id"]
            }
        },
        {
            "name": "check_order",
            "description": "查看订单状态",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号"}
                }
            }
        }
    ]
    return JSONResponse({"tools": tools})


@mcp.custom_route("/tools/call", methods=["POST"])
async def call_tool_legacy(request: Request) -> JSONResponse:
    """兼容旧的工具调用接口"""
    body = await request.json()
    name = body.get("name")
    arguments = body.get("arguments", {})
    
    try:
        if name == "search_meals":
            result = await search_meals(**arguments)
        elif name == "place_order":
            result = await place_order(**arguments)
        elif name == "check_order":
            result = await check_order(**arguments)
        else:
            return JSONResponse({
                "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {name}"})}],
                "isError": True
            })
        
        return JSONResponse({
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "isError": not result.get("success", True)
        })
    except Exception as e:
        return JSONResponse({
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
            "isError": True
        })


def main() -> None:
    """主函数"""
    global notification_monitor
    
    config = get_config()
    logger.info(f"启动服务: {config.server.host}:{config.server.port}")
    
    # 连接设备
    dm = get_device_manager()
    if dm.connect():
        logger.info(f"设备已连接: {dm.device_name}")
    else:
        logger.warning("设备未连接，请检查 USB 连接")
    
    # 启动通知监听（如果配置启用）
    if config.notification.enabled:
        notification_monitor = NotificationMonitor(config)
        notification_monitor.start()
        logger.info("通知监听已启动")
    
    logger.info(f"MCP 服务已启动，SSE 端点: http://{config.server.host}:{config.server.port}/sse")
    
    # 使用 FastMCP 的 SSE 模式运行
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
