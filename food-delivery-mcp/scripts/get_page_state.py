#!/usr/bin/env python3
"""获取当前页面状态 - 用于调试分析"""

import asyncio
import json
import os

# 禁用代理
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)


async def get_page_state():
    """获取当前页面状态"""
    from droidrun.tools import AdbTools
    
    tools = AdbTools()
    await tools.connect()
    
    # 获取页面状态
    desc, screenshot_b64, elements, phone_state = await tools.get_state()
    
    print("=" * 60)
    print("页面描述 (desc):")
    print("=" * 60)
    print(desc)
    
    print("\n" + "=" * 60)
    print(f"元素列表 (共 {len(elements)} 个):")
    print("=" * 60)
    
    # 打印所有元素
    for el in elements:
        text = el.get('text', '')
        idx = el.get('index')
        classname = el.get('className', '')
        bounds = el.get('bounds', '')
        
        if text:  # 只打印有文本的元素
            print(f"[{idx:3d}] text='{text}' | class={classname} | bounds={bounds}")
    
    print("\n" + "=" * 60)
    print("手机状态 (phone_state):")
    print("=" * 60)
    print(json.dumps(phone_state, ensure_ascii=False, indent=2))
    
    # 保存完整元素列表到文件
    output_file = "page_elements.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(elements, f, ensure_ascii=False, indent=2)
    print(f"\n完整元素列表已保存到: {output_file}")
    
    return desc, elements


if __name__ == "__main__":
    asyncio.run(get_page_state())
