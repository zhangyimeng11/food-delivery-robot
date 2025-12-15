"""美团拼好饭 MCP 服务 - 基于 DroidRun 实现"""

import logging
import os

from mcp.server import FastMCP
from starlette.responses import JSONResponse
from starlette.requests import Request

from .config import get_config

# 禁用代理（避免 SOCKS 代理问题）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 创建 FastMCP 服务器
mcp = FastMCP(
    name="美团拼好饭 MCP 服务",
    instructions="通过 DroidRun 自动化操作手机实现语音点餐",
    host="0.0.0.0",
    port=8765,
    sse_path="/sse",
    message_path="/messages/",
)


# ========== MCP 工具定义 ==========

@mcp.tool()
async def search_meals(keyword: str) -> dict:
    """
    搜索美团拼好饭的餐品
    
    流程：打开美团 → 进入拼好饭 → 搜索关键词 → 返回前3个套餐信息
    
    Args:
        keyword: 搜索关键词，如"牛肉面"、"包子"、"奶茶"
    
    Returns:
        搜索结果，包含前3个套餐的名称、价格、配送时间
    """
    from .automation.meituan_tools import search_meals as _search_meals
    result = await _search_meals(keyword)
    return result


@mcp.tool()
async def place_order(meal_name: str) -> dict:
    """
    下单购买指定餐品（到支付页面，不自动支付）
    
    前提：需要先调用 search_meals 进入搜索结果页面
    流程：点击套餐 → 点击马上抢 → 进入支付页面 → 返回最终价格
    
    Args:
        meal_name: 餐品名称或关键词（从搜索结果中获取）
    
    Returns:
        下单结果，包含最终价格
    """
    from .automation.meituan_tools import place_order as _place_order
    result = await _place_order(meal_name)
    return result


@mcp.tool()
async def confirm_payment() -> dict:
    """
    确认支付（点击支付按钮）
    
    前提：需要先调用 place_order 进入支付页面
    流程：点击包含"支付"的按钮 → 完成支付
    
    Returns:
        支付结果
    """
    from .automation.meituan_tools import confirm_payment as _confirm_payment
    result = await _confirm_payment()
    return result


# ========== 自定义路由 ==========

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查接口"""
    return JSONResponse({
        "status": "healthy",
        "agent": "DroidRun",
    })


def main() -> None:
    """主函数"""
    config = get_config()
    logger.info(f"启动服务: {config.server.host}:{config.server.port}")
    logger.info("使用 DroidRun 进行 UI 自动化")
    logger.info(f"MCP 服务已启动，SSE 端点: http://{config.server.host}:{config.server.port}/sse")
    
    # 使用 FastMCP 的 SSE 模式运行
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
