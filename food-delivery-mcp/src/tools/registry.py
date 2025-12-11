"""工具注册表"""

from typing import Any, Callable
from ..schemas import ToolDefinition, ToolInputSchema


class ToolRegistry:
    """工具注册表 - 管理所有可用的 MCP 工具"""
    
    def __init__(self):
        self._tools: dict[str, "BaseTool"] = {}
    
    def register(self, tool: "BaseTool") -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> "BaseTool | None":
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> list[ToolDefinition]:
        """列出所有工具定义"""
        return [tool.get_definition() for tool in self._tools.values()]
    
    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用工具
        
        Args:
            name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
            
        Raises:
            ValueError: 工具不存在
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"工具不存在: {name}")
        return await tool.execute(arguments)


class BaseTool:
    """工具基类"""
    
    name: str = ""
    description: str = ""
    
    def get_input_schema(self) -> ToolInputSchema:
        """获取输入 Schema"""
        return ToolInputSchema()
    
    def get_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            inputSchema=self.get_input_schema(),
        )
    
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具
        
        Args:
            arguments: 输入参数
            
        Returns:
            执行结果
        """
        raise NotImplementedError

