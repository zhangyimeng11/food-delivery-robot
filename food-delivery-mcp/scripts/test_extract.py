#!/usr/bin/env python3
"""测试搜索结果提取 - LLM 版本

使用 LLM 智能解析搜索结果页面
"""

import sys
import re
import json
from datetime import datetime
from pathlib import Path
import httpx
import uiautomator2 as u2

# 添加 src 到路径，复用主项目配置
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import get_config

DEBUG_DIR = Path(__file__).parent / "debug_output"
DEBUG_DIR.mkdir(exist_ok=True)


def extract_texts_from_xml(xml: str) -> list[str]:
    """从 XML 提取搜索结果区域的文本"""
    # 提取文本和 y 坐标
    elements = re.findall(r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]', xml)
    
    # 只保留搜索结果区域的文本 (y > 350)
    texts = []
    skip_words = {'搜索', '历史搜索', '搜索发现', '换一批', '筛选', '排序', '综合排序'}
    
    for text, x, y in elements:
        y = int(y)
        if y > 350 and len(text) > 1:  # 排除顶部搜索栏
            if text not in skip_words:
                if not text.replace('.', '').replace(':', '').isdigit():
                    texts.append(text)
    
    return texts


def call_llm(texts: list[str], max_results: int = 5) -> list[dict]:
    """调用 LLM 解析套餐信息"""
    config = get_config()
    
    prompt = f"""你是一个外卖信息提取助手。下面是从美团外卖拼好饭搜索结果页面提取的文本列表，请从中识别出套餐信息。

文本列表：
{chr(10).join(texts[:100])}

请提取前 {max_results} 个套餐的信息，每个套餐包含：
- name: 套餐名称（如"珍珠奶茶(中杯)"、"麻辣香锅4荤5素"）
- price: 价格（如"¥4.9"）
- merchant: 商家名称（如"蜜雪冰城（五道口店）"）
- time: 配送时间（如"25分钟"）

请只返回 JSON 数组格式：
[{{"name": "...", "price": "...", "merchant": "...", "time": "..."}}]"""

    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.post(
                f"{config.llm.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.llm.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 提取 JSON
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                meals = json.loads(json_match.group())
                # 添加 index
                for i, meal in enumerate(meals):
                    meal['index'] = i
                return meals
            
    except Exception as e:
        print(f"  LLM 调用失败: {e}")
    
    return []


def save_debug_files(device: u2.Device, xml: str, suffix: str = ""):
    """保存调试文件"""
    ts = datetime.now().strftime('%H%M%S')
    name = f"{ts}_extract{suffix}"
    
    screenshot_path = DEBUG_DIR / f"{name}.png"
    device.screenshot(str(screenshot_path))
    
    xml_path = DEBUG_DIR / f"{name}.xml"
    xml_path.write_text(xml, encoding='utf-8')
    
    print(f"  📁 已保存: {name}.png / {name}.xml")


def main():
    config = get_config()
    
    print("连接设备...")
    d = u2.connect()
    print(f"已连接: {d.info.get('productName')}")
    print(f"调试目录: {DEBUG_DIR}")
    print(f"LLM: {config.llm.model}\n")
    
    count = 0
    while True:
        input("按回车提取当前页面...")
        count += 1
        
        print("  获取页面内容...")
        xml = d.dump_hierarchy()
        save_debug_files(d, xml, f"_{count}")
        
        print("  提取文本...")
        texts = extract_texts_from_xml(xml)
        print(f"  共 {len(texts)} 个文本元素")
        
        print("  调用 LLM 解析...")
        meals = call_llm(texts)
        
        if meals:
            print(f"\n✓ 提取到 {len(meals)} 个套餐:\n")
            for m in meals:
                print(f"  [{m.get('index', '?')}] {m.get('name', '?')}")
                print(f"      价格: {m.get('price', '?')}  商家: {m.get('merchant', '?')}  时间: {m.get('time', '?')}")
            print()
        else:
            print("\n✗ 未提取到套餐\n")
        
        print("-" * 50)


if __name__ == "__main__":
    main()
