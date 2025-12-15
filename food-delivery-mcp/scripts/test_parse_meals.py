#!/usr/bin/env python3
"""测试套餐解析逻辑"""

import asyncio
import json
import os
import re

# 禁用代理
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

# LLM 配置
LLM_CONFIG = {
    "api_key": "sk-8ca63b6b547c429ba348eeb131ae1bd0",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-max",
}


async def test_parse():
    """测试解析当前页面的套餐信息"""
    from droidrun.tools import AdbTools
    
    tools = AdbTools()
    await tools.connect()
    
    # 获取页面状态
    desc, screenshot_b64, elements, phone_state = await tools.get_state()
    
    keyword = "辣椒炒肉"
    
    # 构建完整的元素列表（包含所有信息）
    elements_for_llm = []
    for el in elements:
        text = el.get('text', '')
        bounds = el.get('bounds', '')
        idx = el.get('index', 0)
        # 保留所有有文本的元素
        if text and len(text.strip()) > 0:
            elements_for_llm.append({
                'index': idx,
                'text': text,
                'bounds': bounds
            })
    
    print("=" * 60)
    print(f"共 {len(elements_for_llm)} 个有文本的元素")
    print("=" * 60)
    
    # 转为 JSON 字符串
    elements_json = json.dumps(elements_for_llm, ensure_ascii=False, indent=2)
    
    prompt = f"""你是一个美团外卖搜索结果分析助手。下面是搜索"{keyword}"后的页面元素列表，每个元素包含 index（序号）、text（文本）、bounds（位置坐标 x1,y1,x2,y2）。

页面元素：
{elements_json}

请分析并提取前3个与"{keyword}"相关的套餐信息。

分析技巧：
1. 套餐名称通常包含搜索关键词"{keyword}"，如"农耕记辣椒炒肉盖码饭"
2. 价格由多个相邻元素组成：¥ 符号 + 整数部分 + 小数部分（如 ¥ + 24 + .8 = ¥24.8）
3. 配送时间格式为 "XX分钟"
4. 同一套餐的元素 bounds 的 y1 坐标相近（在同一个卡片区域内，通常 y 差值在 300 以内）
5. 忽略以 "android." 或 "mmp-" 开头的系统文本

请以 JSON 格式返回前3个套餐，格式如下：
{{
  "meals": [
    {{
      "name": "套餐名称",
      "price": "价格（如 ¥24.8）",
      "delivery_time": "配送时间（如 27分钟）"
    }}
  ]
}}

注意：
- 只返回JSON格式，不要其他说明文字
- 仔细根据 bounds 坐标判断每个价格和配送时间属于哪个套餐
- 价格要完整组合（¥ + 整数 + 小数）
"""
    
    print("\n" + "=" * 60)
    print("发送给 LLM 的 Prompt (截断):")
    print("=" * 60)
    print(prompt[:1000] + "...\n[内容已截断]")
    
    # 调用 LLM
    from openai import OpenAI
    
    client = OpenAI(
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
    )
    
    response = client.chat.completions.create(
        model=LLM_CONFIG["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    
    result_text = response.choices[0].message.content
    
    print("\n" + "=" * 60)
    print("LLM 返回结果:")
    print("=" * 60)
    print(result_text)
    
    # 解析 JSON
    json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
    if json_match:
        result_json = json.loads(json_match.group())
        print("\n" + "=" * 60)
        print("解析后的套餐信息:")
        print("=" * 60)
        for i, meal in enumerate(result_json.get('meals', []), 1):
            print(f"{i}. {meal.get('name', '未知')}")
            print(f"   价格: {meal.get('price', '未知')}")
            print(f"   配送时间: {meal.get('delivery_time', '未知')}")
            print()


if __name__ == "__main__":
    asyncio.run(test_parse())
