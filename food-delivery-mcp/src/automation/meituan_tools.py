#!/usr/bin/env python3
"""美团外卖 MCP 工具

基于成功运行的 demo 脚本，提供 3 个 MCP 工具：
1. search_meals - 搜索套餐
2. place_order - 下单到支付页面
3. confirm_payment - 确认支付
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from droidrun.tools import AdbTools

# 禁用代理（避免 SOCKS 代理问题）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

# 美团外卖包名
MEITUAN_PACKAGE = "com.sankuai.meituan.takeoutnew"

# LLM 配置
LLM_CONFIG = {
    "api_key": "sk-8ca63b6b547c429ba348eeb131ae1bd0",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
}

# 调试输出目录
DEBUG_DIR = Path(__file__).parent.parent.parent / "debug_output"


def _save_debug_step(session_id: str, step: str, elements: list, action: str = "", extra: dict = None):
    """保存调试信息
    
    Args:
        session_id: 会话ID（时间戳）
        step: 步骤名称
        elements: 页面元素列表
        action: 执行的动作描述
        extra: 额外信息
    """
    # 每次会话保存到独立的子文件夹
    session_dir = DEBUG_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # 只保留有文本的元素
    elements_with_text = []
    for el in elements:
        text = el.get('text', '')
        if text and len(text.strip()) > 0:
            elements_with_text.append({
                'index': el.get('index'),
                'text': text,
                'bounds': el.get('bounds', ''),
                'className': el.get('className', '')
            })
    
    debug_data = {
        'timestamp': datetime.now().isoformat(),
        'step': step,
        'action': action,
        'elements_count': len(elements_with_text),
        'elements': elements_with_text,
    }
    if extra:
        debug_data.update(extra)
    
    # 保存到子文件夹
    filename = session_dir / f"{step}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(debug_data, f, ensure_ascii=False, indent=2)
    
    print(f"[DEBUG] 已保存: {filename}")


def _run_adb(cmd: str) -> str:
    """执行 ADB 命令"""
    result = subprocess.run(f"adb {cmd}", shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


async def search_meals(keyword: str) -> dict:
    """搜索套餐
    
    流程：关闭美团 → 打开美团 → 等待广告 → 点击拼好饭 → 点击搜索框 → 输入关键词 → 点击搜索 → LLM分析结果
    
    Args:
        keyword: 搜索关键词，如"牛肉面"、"包子"
        
    Returns:
        dict: {
            "success": bool,
            "keyword": str,
            "meals": [
                {
                    "name": "套餐名称",
                    "price": "价格",
                    "delivery_time": "配送时间"
                }
            ]
        }
    """
    tools = AdbTools()
    await tools.connect()
    
    # 生成调试会话ID
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[DEBUG] 搜索会话开始: {session_id}, 关键词: {keyword}")
    
    # 步骤 1: 关闭美团
    _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")
    
    # 步骤 2: 打开美团
    await tools.start_app(MEITUAN_PACKAGE)
    
    # 步骤 3: 等待 5 秒（广告）
    await asyncio.sleep(5)
    
    # 步骤 3.5: 检测并关闭红包弹窗
    desc, _, elements, phone_state = await tools.get_state()
    _save_debug_step(session_id, "01_after_open", elements, "打开美团后", {"keyword": keyword})
    
    popup_closed = False
    for el in elements:
        text = el.get('text', '')
        if '收下' in text:
            # 找到红包弹窗，点击"开心收下"或类似按钮
            await tools.tap(el.get('index'))
            popup_closed = True
            await asyncio.sleep(1)
            break
    
    if popup_closed:
        desc, _, elements, phone_state = await tools.get_state()
        _save_debug_step(session_id, "02_after_popup", elements, "关闭弹窗后")
    
    # 步骤 4: 点击拼好饭
    desc, _, elements, phone_state = await tools.get_state()
    _save_debug_step(session_id, "03_before_phf", elements, "准备点击拼好饭")
    
    phf_index = None
    for el in elements:
        text = el.get('text', '')
        if '拼好饭' in text:
            phf_index = el.get('index')
            break
    
    if phf_index:
        await tools.tap(phf_index)
        _save_debug_step(session_id, "03_click_phf", [], f"点击拼好饭 index={phf_index}")
    
    # 步骤 5: 点击搜索框
    await asyncio.sleep(2)
    desc, _, elements, phone_state = await tools.get_state()
    _save_debug_step(session_id, "04_phf_page", elements, "拼好饭页面")
    
    search_index = None
    for el in elements:
        text = el.get('text', '')
        if text == 'search-input':
            search_index = el.get('index')
            break
    
    if not search_index:
        for el in elements:
            text = el.get('text', '')
            if text == '搜索':
                search_index = el.get('index')
                break
    
    if search_index:
        await tools.tap(search_index)
        _save_debug_step(session_id, "04_click_search", [], f"点击搜索框 index={search_index}")
    
    # 步骤 6: 输入搜索关键词
    await asyncio.sleep(2)
    desc, _, elements, phone_state = await tools.get_state()
    _save_debug_step(session_id, "05_search_input_page", elements, "搜索输入页面")
    
    # 从页面元素中提取搜索按钮的坐标
    search_btn_x = None
    search_btn_y = None
    for el in elements:
        text = el.get('text', '')
        if text == '搜索':
            bounds = el.get('bounds', '')
            if bounds:
                # bounds 格式: "x1,y1,x2,y2"
                try:
                    coords = [int(x) for x in bounds.split(',')]
                    if len(coords) == 4:
                        # 计算中间点坐标
                        search_btn_x = (coords[0] + coords[2]) // 2
                        search_btn_y = (coords[1] + coords[3]) // 2
                        break
                except ValueError:
                    pass
    
    # 如果未找到，使用默认坐标（fallback）
    if search_btn_x is None or search_btn_y is None:
        search_btn_x = 960
        search_btn_y = 173
    
    input_index = None
    for el in elements:
        classname = el.get('className', '')
        if 'EditText' in classname:
            input_index = el.get('index')
            break
    
    if input_index:
        await tools.input_text(keyword, input_index, clear=True)
        _save_debug_step(session_id, "05_input_keyword", [], f"输入关键词 '{keyword}' index={input_index}", 
                        {"search_btn_coords": f"({search_btn_x}, {search_btn_y})"})
    
    # 步骤 7: 点击搜索按钮
    # 使用从步骤 6 提取的搜索按钮坐标点击（避免页面元素获取问题）
    await asyncio.sleep(1)
    await tools.tap_by_coordinates(search_btn_x, search_btn_y)
    _save_debug_step(session_id, "06_click_search_btn", [], f"点击搜索按钮 坐标=({search_btn_x}, {search_btn_y})")
    await asyncio.sleep(2)
    desc, _, elements, phone_state = await tools.get_state()
    
    # 保存搜索结果页面
    _save_debug_step(session_id, "07_search_result", elements, "搜索结果页面")
    
    # 步骤 8: 直接将完整元素信息传给 LLM 分析
    
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
    
    try:
        
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
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        
        if json_match:
            result_json = json.loads(json_match.group())
            return {
                "success": True,
                "keyword": keyword,
                "meals": result_json.get('meals', [])
            }
        else:
            return {
                "success": False,
                "keyword": keyword,
                "error": "无法解析搜索结果"
            }
            
    except Exception as e:
        return {
            "success": False,
            "keyword": keyword,
            "error": str(e)
        }


async def place_order(meal_name: str) -> dict:
    """下单到支付页面
    
    前提：已经在搜索结果页面
    流程：找到套餐 → 点击进入详情 → 点击"马上抢" → 再次点击"马上抢" → 进入支付页面 → 提取最终价格
    
    Args:
        meal_name: 套餐名称或关键词，如"韭菜包子"
        
    Returns:
        dict: {
            "success": bool,
            "meal_name": str,
            "final_price": str  # 如 "¥16.7"
        }
    """
    tools = AdbTools()
    await tools.connect()
    
    # 步骤 1: 查找并点击指定套餐
    desc, _, elements, phone_state = await tools.get_state()
    meal_index = None
    for el in elements:
        text = el.get('text', '')
        if meal_name in text:
            meal_index = el.get('index')
            break
    
    if meal_index:
        await tools.tap(meal_index)
    
    # 步骤 2: 等待详情页加载完成
    await asyncio.sleep(2)
    
    # 步骤 3: 查找并点击"马上抢"按钮
    desc, _, elements, phone_state = await tools.get_state()
    buy_btn_index = None
    for el in elements:
        text = el.get('text', '')
        if '马上抢' in text:
            buy_btn_index = el.get('index')
            break
    
    if buy_btn_index:
        await tools.tap(buy_btn_index)
    
    # 步骤 4: 等待加载完成
    await asyncio.sleep(2)
    
    # 步骤 5: 再次查找并点击"马上抢"按钮
    desc, _, elements, phone_state = await tools.get_state()
    buy_btn_index2 = None
    for el in elements:
        text = el.get('text', '')
        if '马上抢' in text:
            buy_btn_index2 = el.get('index')
            break
    
    if buy_btn_index2:
        await tools.tap(buy_btn_index2)
    
    # 步骤 6: 等待进入支付页面
    await asyncio.sleep(2)
    
    # 步骤 7: 验证到达支付页面并提取最终价格
    desc, _, elements, phone_state = await tools.get_state()
    
    payment_btn_index = None
    for el in elements:
        text = el.get('text', '')
        if text == '极速支付':
            payment_btn_index = el.get('index')
            break
    
    if payment_btn_index:
        # 先找到"¥"的位置
        yuan_index = None
        for el in elements:
            text = el.get('text', '')
            idx = el.get('index')
            if text == '¥' and idx < payment_btn_index:
                yuan_index = idx
        
        if yuan_index:
            # 收集¥和极速支付之间的价格字符
            price_parts = []
            for el in elements:
                idx = el.get('index')
                text = el.get('text', '')
                if yuan_index <= idx < payment_btn_index and text.strip():
                    if text in ['¥', '.'] or text.isdigit():
                        price_parts.append((idx, text))
            
            price_parts.sort(key=lambda x: x[0])
            final_price = ''.join([text for idx, text in price_parts])
            
            return {
                "success": True,
                "meal_name": meal_name,
                "final_price": final_price
            }
    
    return {
        "success": False,
        "meal_name": meal_name,
        "error": "未到达支付页面或无法提取价格"
    }


async def confirm_payment() -> dict:
    """确认支付
    
    前提：已经在支付页面
    流程：找到包含"支付"的按钮 → 点击支付 → 完成
    
    Returns:
        dict: {
            "success": bool,
            "message": str
        }
    """
    tools = AdbTools()
    await tools.connect()
    
    # 步骤 1: 查看当前页面状态
    desc, _, elements, phone_state = await tools.get_state()
    
    # 步骤 2: 查找并点击支付按钮
    # 模糊匹配包含"支付"的元素，选择最后一个（通常是真正的按钮）
    payment_btn_index = None
    payment_btn_text = None
    for el in elements:
        text = el.get('text', '')
        if '支付' in text:
            payment_btn_index = el.get('index')
            payment_btn_text = text
            # 不 break，继续遍历找到最后一个
    
    if payment_btn_index:
        await tools.tap(payment_btn_index)
        
        # 步骤 3: 等待2秒
        await asyncio.sleep(2)
        
        # 步骤 4: 查找"免密支付"按钮
        desc, _, elements, phone_state = await tools.get_state()
        
        mianmi_btn_index = None
        for el in elements:
            text = el.get('text', '')
            if text == '免密支付':
                mianmi_btn_index = el.get('index')
                break
        
        if mianmi_btn_index:
            await tools.tap(mianmi_btn_index)
            # 等待支付完成
            await asyncio.sleep(2)
            # 关闭美团，确保通知栏能显示送达通知
            _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")
            return {
                "success": True,
                "message": f"已点击支付按钮: {payment_btn_text}，并点击免密支付"
            }
        else:
            # 等待支付完成
            await asyncio.sleep(2)
            # 关闭美团，确保通知栏能显示送达通知
            _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")
            return {
                "success": True,
                "message": f"已点击支付按钮: {payment_btn_text}"
            }
    
    return {
        "success": False,
        "error": "未找到支付按钮"
    }


# ============================================================
# 测试代码
# ============================================================

async def _test_search():
    """测试搜索套餐"""
    print("=" * 50)
    print("测试 search_meals")
    print("=" * 50)
    result = await search_meals("牛肉面")
    print(f"结果: {result}")
    return result


async def _test_place_order():
    """测试下单"""
    print("=" * 50)
    print("测试 place_order")
    print("=" * 50)
    result = await place_order("韭菜包子")
    print(f"结果: {result}")
    return result


async def _test_confirm_payment():
    """测试确认支付"""
    print("=" * 50)
    print("测试 confirm_payment")
    print("=" * 50)
    result = await confirm_payment()
    print(f"结果: {result}")
    return result


if __name__ == "__main__":
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "search":
            keyword = sys.argv[2] if len(sys.argv) > 2 else "牛肉面"
            result = asyncio.run(search_meals(keyword))
            print("\n" + "=" * 50)
            print("搜索结果:")
            print("=" * 50)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif cmd == "order":
            meal_name = sys.argv[2] if len(sys.argv) > 2 else "韭菜包子"
            result = asyncio.run(place_order(meal_name))
            print("\n" + "=" * 50)
            print("下单结果:")
            print("=" * 50)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif cmd == "pay":
            result = asyncio.run(confirm_payment())
            print("\n" + "=" * 50)
            print("支付结果:")
            print("=" * 50)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法:")
        print("  python meituan_tools.py search [关键词]")
        print("  python meituan_tools.py order [套餐名]")
        print("  python meituan_tools.py pay")
