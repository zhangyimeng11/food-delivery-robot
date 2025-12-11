"""Pydantic 模型定义 - MCP 协议格式"""

from typing import Any
from pydantic import BaseModel, Field


# ============ 工具定义 ============

class ToolInputSchema(BaseModel):
    """工具输入 Schema"""
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    inputSchema: ToolInputSchema


class ToolsListResponse(BaseModel):
    """工具列表响应"""
    tools: list[ToolDefinition]


# ============ 工具调用 ============

class ToolCallRequest(BaseModel):
    """工具调用请求"""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ContentItem(BaseModel):
    """MCP 内容项"""
    type: str = "text"
    text: str


class ToolCallResponse(BaseModel):
    """工具调用响应 (MCP 格式)"""
    content: list[ContentItem]
    isError: bool = False


# ============ 健康检查 ============

class DeviceInfo(BaseModel):
    """设备信息"""
    available: bool
    device_name: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    device: DeviceInfo


# ============ 工具结果 ============

class MealItem(BaseModel):
    """套餐信息"""
    index: int
    name: str
    price: str
    time: str | None = None
    merchant: str | None = None


class SearchMealsResult(BaseModel):
    """搜索套餐结果"""
    success: bool
    meals: list[MealItem] = Field(default_factory=list)
    error: str | None = None


class PlaceOrderResult(BaseModel):
    """下单结果"""
    success: bool
    meal_name: str | None = None
    price: str | None = None
    message: str | None = None
    error: str | None = None


class OrderStatusResult(BaseModel):
    """订单状态结果"""
    success: bool
    status: str | None = None
    progress: str | None = None
    estimated_arrival: str | None = None
    error: str | None = None

