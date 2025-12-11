"""搜索套餐工具"""

import asyncio
import logging
from typing import Any

from ..schemas import ToolInputSchema, MealItem
from ..automation.meituan import MeituanAutomation
from ..automation.device import get_device_manager
from .registry import BaseTool

logger = logging.getLogger(__name__)


class SearchMealsTool(BaseTool):
    """搜索套餐工具"""
    
    name = "search_meals"
    description = "在美团外卖拼好饭搜索套餐"
    
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
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，如\"奶茶\"、\"汉堡\"",
                }
            },
            required=["keyword"],
        )
    
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行搜索
        
        Args:
            arguments: {"keyword": "搜索关键词"}
            
        Returns:
            {"success": bool, "meals": [...], "error": str?}
        """
        keyword = arguments.get("keyword", "")
        if not keyword:
            return {
                "success": False,
                "meals": [],
                "error": "请提供搜索关键词",
            }
        
        try:
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            meals = await loop.run_in_executor(
                None,
                lambda: self.automation.search_meals(keyword, max_results=3)
            )
            
            return {
                "success": True,
                "meals": [
                    MealItem(
                        index=m.index,
                        name=m.name,
                        price=m.price,
                        time=m.time,
                        merchant=m.merchant,
                    ).model_dump()
                    for m in meals
                ],
            }
            
        except Exception as e:
            logger.error(f"搜索套餐失败: {e}")
            return {
                "success": False,
                "meals": [],
                "error": str(e),
            }

