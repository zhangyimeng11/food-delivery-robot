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

# ADB 连接配置 - 从配置文件读取
def _get_phone_config():
    """获取手机配置"""
    from src.config import get_config
    config = get_config()
    return config.phone.ip, config.phone.adb_port

# 延迟加载
_phone_ip = None
_adb_port = None

def _get_adb_target():
    """获取 ADB 连接目标"""
    global _phone_ip, _adb_port
    if _phone_ip is None:
        _phone_ip, _adb_port = _get_phone_config()
    return _phone_ip, _adb_port

# LLM 配置
LLM_CONFIG = {
    "api_key": "sk-8ca63b6b547c429ba348eeb131ae1bd0",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
}

# 调试输出目录
DEBUG_DIR = Path(__file__).parent.parent.parent / "debug_output"

# 并发控制：全局锁和当前任务追踪
# 防止多个工具调用同时操作手机 UI
_meituan_lock = asyncio.Lock()
_current_task: asyncio.Task | None = None


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


async def _cancel_current_task():
    """取消当前正在执行的任务"""
    global _current_task
    if _current_task and not _current_task.done():
        _current_task.cancel()
        try:
            await _current_task
        except asyncio.CancelledError:
            pass
        # 确保 App 被关闭，留给下一个任务干净的状态
        _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")


async def _ensure_adb_connection() -> bool:
    """确保 ADB 连接，如果断开则尝试重连"""
    phone_ip, adb_port = _get_adb_target()
    target = f"{phone_ip}:{adb_port}"
    
    try:
        # 1. 检查当前是否已连接
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        if target in result.stdout and "device" in result.stdout:
            return True
            
        print(f"[ADB] 连接断开或未连接，尝试连接 {target}...")
        
        # 2. 尝试重连
        # 先断开可能的僵尸连接
        subprocess.run(["adb", "disconnect", target], capture_output=True)
        # 连接
        connect_res = subprocess.run(["adb", "connect", target], capture_output=True, text=True)
        
        # 3. 验证连接结果
        if f"connected to {target}" in connect_res.stdout or "already connected" in connect_res.stdout:
            # 再次确认 devices 列表
            verify_res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            if target in verify_res.stdout and "device" in verify_res.stdout:
                print(f"[ADB] 重连成功: {target}")
                return True
        
        print(f"[ADB] 重连失败: {connect_res.stdout.strip()}")
        return False
        
    except Exception as e:
        print(f"[ADB] 连接检查出错: {e}")
        return False


async def search_meals(keyword: str) -> dict:
    """搜索套餐
    
    流程：关闭美团 → 打开美团 → 等待广告 → 点击拼好饭 → 点击搜索框 → 输入关键词 → 点击搜索 → LLM分析结果
    
    注意：如果有其他工具调用正在进行，会自动取消之前的任务
    
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
    global _current_task
    
    # 取消正在进行的任务
    await _cancel_current_task()
    
    async with _meituan_lock:
        _current_task = asyncio.current_task()
        
        try:
            return await _search_meals_impl(keyword)
        except asyncio.CancelledError:
            # 被取消时返回取消信息
            return {
                "success": False,
                "keyword": keyword,
                "error": "操作被新的请求取消"
            }


async def _search_meals_impl(keyword: str) -> dict:
    """搜索套餐的实际实现"""
    # 确保 ADB 连接
    if not await _ensure_adb_connection():
        return {
            "success": False, 
            "keyword": keyword, 
            "error": f"无法连接到手机，请检查网络或手机状态"
        }

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
    
    # 步骤 3.5: 检测并关闭弹窗 (红包或更新弹窗)
    desc, _, elements, phone_state = await tools.get_state()
    _save_debug_step(session_id, "01_after_open", elements, "打开美团后", {"keyword": keyword})
    
    popup_closed = False
    for el in elements:
        text = el.get('text', '')
        resource_id = el.get('resourceId', '')
        
        # 情况1: 红包弹窗
        if '收下' in text:
            # 找到红包弹窗，点击"开心收下"或类似按钮
            await tools.tap(el.get('index'))
            popup_closed = True
            print(f"[DEBUG] 检测到红包弹窗，已点击关闭")
            await asyncio.sleep(1)
            break
            
        # 情况2: 版本更新弹窗 (根据用户提供的 page_elements.json)
        # 查找关闭按钮: com.sankuai.meituan.takeoutnew:id/btn_close
        if 'btn_close' in resource_id:
            await tools.tap(el.get('index'))
            popup_closed = True
            print(f"[DEBUG] 检测到更新弹窗，已点击关闭按钮 (id={resource_id})")
            await asyncio.sleep(1)
            break
            
        # 情况2备选: 如果找不到ID，通过"立即安装"判断是否存在弹窗，然后找关闭按钮
    
    # 如果没通过 ID 找到关闭按钮，但看到了"立即安装"，尝试找一下关闭按钮（防止 id 变动）
    if not popup_closed:
        has_update_popup = False
        for el in elements:
            if '立即安装' in el.get('text', ''):
                has_update_popup = True
                break
        
        if has_update_popup:
            # 尝试通过位置或层级找关闭按钮 (通常在右上角)
            # 这里简单起见，如果刚才没找到 btn_close，可能需要更复杂的逻辑，
            # 但根据 page_elements.json，btn_close 是存在的。
            # 为了稳健，我们可以遍历找一下 className 为 Button 且 bounds 在右上角的
            pass

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
    # 固定使用已知的搜索按钮坐标（index=12, bounds=921,144,999,201）
    # 中心点: (921+999)/2=960, (144+201)/2=172
    SEARCH_BTN_X = 960
    SEARCH_BTN_Y = 172
    
    input_index = None
    for el in elements:
        classname = el.get('className', '')
        if 'EditText' in classname:
            input_index = el.get('index')
            break
    
    if input_index:
        await tools.input_text(keyword, input_index, clear=True)
        _save_debug_step(session_id, "05_input_keyword", [], f"输入关键词 '{keyword}' index={input_index}", 
                        {"search_btn_coords": f"({SEARCH_BTN_X}, {SEARCH_BTN_Y})"})
    
    # 步骤 7: 点击搜索按钮（使用固定坐标）
    await asyncio.sleep(1)
    await tools.tap_by_coordinates(SEARCH_BTN_X, SEARCH_BTN_Y)
    _save_debug_step(session_id, "06_click_search_btn", [], f"点击搜索按钮 坐标=({SEARCH_BTN_X}, {SEARCH_BTN_Y})")
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
    
    注意：如果有其他工具调用正在进行，会自动取消之前的任务
    
    Args:
        meal_name: 套餐名称或关键词，如"韭菜包子"
        
    Returns:
        dict: {
            "success": bool,
            "meal_name": str,
            "final_price": str  # 如 "¥16.7"
        }
    """
    global _current_task
    
    # 取消正在进行的任务
    await _cancel_current_task()
    
    async with _meituan_lock:
        _current_task = asyncio.current_task()
        
        try:
            return await _place_order_impl(meal_name)
        except asyncio.CancelledError:
            return {
                "success": False,
                "meal_name": meal_name,
                "error": "操作被新的请求取消"
            }


async def _place_order_impl(meal_name: str) -> dict:
    """下单的实际实现"""
    # 确保 ADB 连接
    if not await _ensure_adb_connection():
        return {
            "success": False, 
            "meal_name": meal_name, 
            "error": "无法连接到手机，请检查网络或手机状态"
        }

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
    
    注意：如果有其他工具调用正在进行，会自动取消之前的任务
    
    Returns:
        dict: {
            "success": bool,
            "message": str
        }
    """
    global _current_task
    
    # 取消正在进行的任务
    await _cancel_current_task()
    
    async with _meituan_lock:
        _current_task = asyncio.current_task()
        
        try:
            return await _confirm_payment_impl()
        except asyncio.CancelledError:
            return {
                "success": False,
                "error": "操作被新的请求取消"
            }


async def _confirm_payment_impl() -> dict:
    """确认支付的实际实现"""
    # 确保 ADB 连接
    if not await _ensure_adb_connection():
        return {
            "success": False, 
            "error": "无法连接到手机，请检查网络或手机状态"
        }

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
