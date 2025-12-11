"""下单工具"""

import asyncio
import logging
from typing import Any

from ..schemas import ToolInputSchema
from ..automation.meituan import MeituanAutomation
from ..automation.device import get_device_manager
from .registry import BaseTool

logger = logging.getLogger(__name__)


class PlaceOrderTool(BaseTool):
    """下单工具"""
    
    name = "place_order"
    description = "下单指定的套餐（需要先搜索）"
    
    def __init__(self):
        self._automation: MeituanAutomation | None = None
    
    @property
    def automation(self) -> MeituanAutomation:
        if self._automation is None:
            self._automation = MeituanAutomation(get_device_manager())
        return self._automation
    
    def get_input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            type="object",
            properties={
                "meal_index": {
                    "type": "integer",
                    "description": "套餐索引，默认 0（第一个）",
                    "default": 0,
                },
                "meal_name": {
                    "type": "string",
                    "description": "套餐名称（可选，直接按名称点击）",
                },
            },
            required=[],
        )
    
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行下单
        
        Args:
            arguments: {"meal_index": 0, "meal_name": "xxx"}
            
        Returns:
            {"success": bool, "meal_name": str?, "price": str?, "message": str?, "error": str?}
        """
        meal_index = arguments.get("meal_index", 0)
        meal_name = arguments.get("meal_name")
        
        try:
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.automation.place_order(
                    meal_index=meal_index,
                    meal_name=meal_name,
                )
            )
            
            return result
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

