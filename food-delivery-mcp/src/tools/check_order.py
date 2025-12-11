"""查询订单状态工具"""

import asyncio
import logging
from typing import Any

from ..schemas import ToolInputSchema
from ..automation.meituan import MeituanAutomation
from ..automation.device import get_device_manager
from .registry import BaseTool

logger = logging.getLogger(__name__)


class CheckOrderTool(BaseTool):
    """查询订单状态工具"""
    
    name = "check_order_status"
    description = "查询最新订单的配送状态"
    
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
            properties={},
            required=[],
        )
    
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行查询
        
        Args:
            arguments: {} (无参数)
            
        Returns:
            {"success": bool, "status": str?, "progress": str?, "estimated_arrival": str?, "error": str?}
        """
        try:
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                self.automation.check_order_status
            )
            
            return {
                "success": True,
                "status": status.status,
                "progress": status.progress,
                "estimated_arrival": status.estimated_arrival,
            }
            
        except Exception as e:
            logger.error(f"查询订单状态失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

