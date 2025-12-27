"""MCP 反向连接客户端 - 主动连接服务器 Relay"""
import asyncio
import json
import logging
import signal
import sys
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

try:
    import websockets
except ImportError:
    print("请安装 websockets: pip install websockets")
    sys.exit(1)

from .config import get_config

# 导入工具函数
from .automation.meituan_tools import search_meals, place_order, confirm_payment
from .automation.execute_task import execute_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# 工具定义
TOOLS = [
    {
        "name": "search_meals",
        "description": "搜索美团拼好饭的餐品。流程：打开美团 → 进入拼好饭 → 搜索关键词 → 返回前3个套餐信息",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，如\"牛肉面\"、\"包子\"、\"奶茶\""
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "place_order",
        "description": "下单购买指定餐品（到支付页面，不自动支付）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meal_name": {
                    "type": "string",
                    "description": "餐品名称或关键词"
                }
            },
            "required": ["meal_name"]
        }
    },
    {
        "name": "confirm_payment",
        "description": "确认支付（点击支付按钮）",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "execute_task",
        "description": "执行自由任务 - 让 AI Agent 自主操作手机完成任务。适用于搜索、下单、查看历史订单、查看优惠券等任何美团 App 内的操作。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "任务描述，用自然语言说明想做什么"
                }
            },
            "required": ["task_description"]
        }
    }
]

# 工具函数映射
TOOL_HANDLERS: Dict[str, Callable[..., Awaitable[Any]]] = {
    "search_meals": lambda args: search_meals(args["keyword"]),
    "place_order": lambda args: place_order(args["meal_name"]),
    "confirm_payment": lambda args: confirm_payment(),
    "execute_task": lambda args: execute_task(args["task_description"]),
}


class MCPReverseClient:
    """MCP 反向连接客户端"""
    
    def __init__(self, relay_url: str, device_id: str = "food-delivery-mcp"):
        """
        初始化反向连接客户端
        
        Args:
            relay_url: 服务器 Relay WebSocket URL，例如 ws://api.example.com/api/v1/mcp/ws/food-delivery-mcp
            device_id: 设备标识
        """
        self.relay_url = relay_url
        self.device_id = device_id
        self.websocket = None
        self._running = False
        self._reconnect_delay = 5  # 重连延迟（秒）
    
    async def connect(self):
        """连接到服务器 Relay"""
        logger.info(f"🔌 正在连接服务器: {self.relay_url}")
        
        try:
            self.websocket = await websockets.connect(
                self.relay_url,
                ping_interval=30,
                ping_timeout=10
            )
            
            # 发送注册消息
            register_message = {
                "type": "register",
                "tools": TOOLS
            }
            await self.websocket.send(json.dumps(register_message))
            
            # 等待注册确认
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "registered":
                logger.info(f"✅ 注册成功! 设备ID: {response_data.get('device_id')}, 工具数: {response_data.get('tools_count')}")
                return True
            else:
                logger.error(f"❌ 注册失败: {response_data}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            return False
    
    async def handle_message(self, message: str):
        """处理服务器发来的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "call":
                # 工具调用请求
                request_id = data.get("request_id")
                tool_name = data.get("tool")
                args = data.get("args", {})
                
                logger.info(f"🔧 收到工具调用: {tool_name} (request_id={request_id})")
                
                try:
                    handler = TOOL_HANDLERS.get(tool_name)
                    if not handler:
                        raise ValueError(f"未知工具: {tool_name}")
                    
                    result = await handler(args)
                    
                    # 发送成功响应
                    response = {
                        "type": "result",
                        "request_id": request_id,
                        "success": True,
                        "data": result
                    }
                    logger.info(f"✅ 工具调用成功: {tool_name}")
                    
                except Exception as e:
                    # 发送错误响应
                    response = {
                        "type": "result",
                        "request_id": request_id,
                        "success": False,
                        "error": str(e)
                    }
                    logger.error(f"❌ 工具调用失败: {tool_name} - {e}")
                
                await self.websocket.send(json.dumps(response))
            
            elif msg_type == "pong":
                # 心跳响应
                pass
            
            else:
                logger.debug(f"收到其他消息: {msg_type}")
                
        except json.JSONDecodeError:
            logger.warning(f"⚠️ 无效的 JSON 消息")
        except Exception as e:
            logger.error(f"❌ 处理消息失败: {e}")
    
    async def run(self):
        """运行客户端（含自动重连）"""
        self._running = True
        
        while self._running:
            try:
                if await self.connect():
                    # 开始接收消息
                    async for message in self.websocket:
                        await self.handle_message(message)
                        
                        # 定期发送心跳
                        # 注：websockets 库会自动处理 ping/pong，这里我们发送应用层心跳
                        
            except websockets.ConnectionClosed as e:
                logger.warning(f"⚠️ 连接断开: {e}")
            except Exception as e:
                logger.error(f"❌ 运行错误: {e}")
            
            if self._running:
                logger.info(f"🔄 {self._reconnect_delay}秒后重连...")
                await asyncio.sleep(self._reconnect_delay)
    
    async def stop(self):
        """停止客户端"""
        self._running = False
        if self.websocket:
            await self.websocket.close()
            logger.info("🔌 连接已关闭")


async def main():
    """主函数"""
    config = get_config()
    
    # 从配置或环境变量获取 Relay URL
    import os
    relay_url = os.getenv("MCP_RELAY_URL", "ws://100.86.205.14:8000/api/v1/mcp/ws/food-delivery-mcp")
    
    logger.info("=" * 50)
    logger.info("🤖 MCP 反向连接客户端启动")
    logger.info(f"📡 Relay URL: {relay_url}")
    logger.info("=" * 50)
    
    client = MCPReverseClient(relay_url)
    
    # 设置信号处理
    def signal_handler():
        logger.info("收到退出信号...")
        asyncio.create_task(client.stop())
    
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
