#!/usr/bin/env python3
"""测试 MCP 工具的脚本"""

import asyncio
import httpx
import json


MCP_URL = "http://localhost:8765"


async def call_tool(name: str, arguments: dict) -> dict:
    """调用 MCP 工具"""
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{MCP_URL}/tools/call",
            json={"name": name, "arguments": arguments}
        )
        return response.json()


async def test_search():
    """测试搜索"""
    print("=== 测试 search_meals ===")
    result = await call_tool("search_meals", {"keyword": "奶茶", "max_results": 2})
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def test_place_order():
    """测试下单"""
    print("=== 测试 place_order ===")
    result = await call_tool("place_order", {"meal_name": "奶茶"})
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def test_confirm_payment():
    """测试确认支付"""
    print("=== 测试 confirm_payment ===")
    result = await call_tool("confirm_payment", {})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python test_tools.py <command>")
        print("  search    - 搜索套餐")
        print("  order     - 下单")
        print("  pay       - 确认支付")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "search":
        asyncio.run(test_search())
    elif cmd == "order":
        asyncio.run(test_place_order())
    elif cmd == "pay":
        asyncio.run(test_confirm_payment())
    else:
        print(f"未知命令: {cmd}")

