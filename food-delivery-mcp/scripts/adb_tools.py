#!/usr/bin/env python3
"""DroidRun ADB 操作工具

提供命令行接口来执行 droidrun 提供的 adb 操作，包括：
- 获取页面状态
- 点击元素
- 输入文本
- 启动应用
- 滑动等操作
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# 禁用代理（避免 SOCKS 代理问题）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

from droidrun.tools import AdbTools


async def get_state(output_file: str = None):
    """获取当前页面状态
    
    Args:
        output_file: 可选，保存元素列表到 JSON 文件
    """
    tools = AdbTools()
    await tools.connect()
    
    desc, screenshot_b64, elements, phone_state = await tools.get_state()
    
    print("=" * 60)
    print("页面描述 (desc):")
    print("=" * 60)
    print(desc)
    
    print("\n" + "=" * 60)
    print(f"元素列表 (共 {len(elements)} 个):")
    print("=" * 60)
    
    # 打印所有有文本的元素
    elements_with_text = []
    for el in elements:
        text = el.get('text', '')
        idx = el.get('index')
        classname = el.get('className', '')
        bounds = el.get('bounds', '')
        
        if text and len(text.strip()) > 0:
            info = f"[{idx:3d}] text='{text}' | class={classname} | bounds={bounds}"
            print(info)
            elements_with_text.append(el)
    
    print("\n" + "=" * 60)
    print("手机状态 (phone_state):")
    print("=" * 60)
    print(json.dumps(phone_state, ensure_ascii=False, indent=2))
    
    # 保存到文件
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(elements, f, ensure_ascii=False, indent=2)
        print(f"\n完整元素列表已保存到: {output_file}")
    elif output_file is None:  # 默认保存
        default_file = "page_elements.json"
        with open(default_file, 'w', encoding='utf-8') as f:
            json.dump(elements, f, ensure_ascii=False, indent=2)
        print(f"\n完整元素列表已保存到: {default_file}")
    
    return desc, elements, phone_state


async def tap(index: int):
    """点击指定 index 的元素
    
    Args:
        index: 元素的 index
    """
    tools = AdbTools()
    await tools.connect()
    
    print(f"点击元素 index={index}")
    await tools.tap(index)
    print("点击完成")
    
    # 等待一下让页面响应
    await asyncio.sleep(1)


async def tap_by_text(text: str, exact: bool = False):
    """通过文本查找并点击元素
    
    Args:
        text: 要查找的文本
        exact: 是否精确匹配（默认 False，部分匹配）
    """
    tools = AdbTools()
    await tools.connect()
    
    desc, _, elements, _ = await tools.get_state()
    
    matched_elements = []
    for el in elements:
        el_text = el.get('text', '')
        if exact:
            if el_text == text:
                matched_elements.append(el)
        else:
            if text in el_text:
                matched_elements.append(el)
    
    if not matched_elements:
        print(f"未找到包含文本 '{text}' 的元素")
        return
    
    print(f"找到 {len(matched_elements)} 个匹配的元素:")
    for el in matched_elements:
        idx = el.get('index')
        el_text = el.get('text', '')
        bounds = el.get('bounds', '')
        print(f"  [{idx}] {el_text} | bounds={bounds}")
    
    if len(matched_elements) == 1:
        idx = matched_elements[0].get('index')
        print(f"\n点击元素 [{idx}]")
        await tools.tap(idx)
        print("点击完成")
        await asyncio.sleep(1)
    else:
        print("\n多个匹配，请输入要点击的 index:")


async def input_text(text: str, index: int = None, clear: bool = True):
    """输入文本到指定元素
    
    Args:
        text: 要输入的文本
        index: 元素的 index，如果不提供则查找第一个 EditText
        clear: 是否先清空输入框（默认 True）
    """
    tools = AdbTools()
    await tools.connect()
    
    if index is None:
        # 查找第一个 EditText
        desc, _, elements, _ = await tools.get_state()
        for el in elements:
            classname = el.get('className', '')
            if 'EditText' in classname:
                index = el.get('index')
                print(f"找到 EditText 元素 index={index}")
                break
        
        if index is None:
            print("未找到 EditText 元素，请手动指定 index")
            return
    
    print(f"输入文本到元素 index={index}: '{text}'")
    await tools.input_text(text, index, clear=clear)
    print("输入完成")
    await asyncio.sleep(0.5)


async def start_app(package_name: str):
    """启动应用
    
    Args:
        package_name: 应用包名，如 "com.sankuai.meituan.takeoutnew"
    """
    tools = AdbTools()
    await tools.connect()
    
    print(f"启动应用: {package_name}")
    await tools.start_app(package_name)
    print("应用启动完成")
    await asyncio.sleep(2)


async def swipe(start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 500):
    """滑动操作
    
    Args:
        start_x: 起始 x 坐标
        start_y: 起始 y 坐标
        end_x: 结束 x 坐标
        end_y: 结束 y 坐标
        duration: 滑动时长（毫秒，默认 500）
    """
    tools = AdbTools()
    await tools.connect()
    
    print(f"滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y}), 时长={duration}ms")
    await tools.swipe(start_x, start_y, end_x, end_y, duration)
    print("滑动完成")
    await asyncio.sleep(1)


async def press_back():
    """按下返回键"""
    tools = AdbTools()
    await tools.connect()
    
    print("按下返回键")
    await tools.press_back()
    print("完成")
    await asyncio.sleep(0.5)


async def press_home():
    """按下 Home 键"""
    tools = AdbTools()
    await tools.connect()
    
    print("按下 Home 键")
    await tools.press_home()
    print("完成")
    await asyncio.sleep(0.5)


def print_usage():
    """打印使用说明"""
    usage = """
用法: python adb_tools.py <command> [args...]

命令列表:

  1. get_state [output_file]
     获取当前页面状态
     示例: python adb_tools.py get_state
            python adb_tools.py get_state elements.json

  2. tap <index>
     点击指定 index 的元素
     示例: python adb_tools.py tap 42

  3. tap_text <text> [exact]
     通过文本查找并点击元素
     示例: python adb_tools.py tap_text "搜索"
            python adb_tools.py tap_text "搜索" exact

  4. input <text> [index] [--no-clear]
     输入文本到指定元素
     示例: python adb_tools.py input "牛肉面"
            python adb_tools.py input "牛肉面" 15
            python adb_tools.py input "牛肉面" 15 --no-clear

  5. start_app <package_name>
     启动应用
     示例: python adb_tools.py start_app com.sankuai.meituan.takeoutnew

  6. swipe <start_x> <start_y> <end_x> <end_y> [duration]
     滑动操作
     示例: python adb_tools.py swipe 500 1500 500 500

  7. back
     按下返回键
     示例: python adb_tools.py back

  8. home
     按下 Home 键
     示例: python adb_tools.py home

常用应用包名:
  - 美团外卖: com.sankuai.meituan.takeoutnew
"""
    print(usage)


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "get_state":
            output_file = sys.argv[2] if len(sys.argv) > 2 else None
            await get_state(output_file)
        
        elif command == "tap":
            if len(sys.argv) < 3:
                print("错误: 需要提供 index")
                print("用法: python adb_tools.py tap <index>")
                return
            index = int(sys.argv[2])
            await tap(index)
        
        elif command == "tap_text":
            if len(sys.argv) < 3:
                print("错误: 需要提供文本")
                print("用法: python adb_tools.py tap_text <text> [exact]")
                return
            text = sys.argv[2]
            exact = len(sys.argv) > 3 and sys.argv[3].lower() == "exact"
            await tap_by_text(text, exact)
        
        elif command == "input":
            if len(sys.argv) < 3:
                print("错误: 需要提供文本")
                print("用法: python adb_tools.py input <text> [index] [--no-clear]")
                return
            text = sys.argv[2]
            index = None
            clear = True
            if len(sys.argv) > 3:
                if sys.argv[3] == "--no-clear":
                    clear = False
                else:
                    index = int(sys.argv[3])
            if len(sys.argv) > 4 and sys.argv[-1] == "--no-clear":
                clear = False
            await input_text(text, index, clear)
        
        elif command == "start_app":
            if len(sys.argv) < 3:
                print("错误: 需要提供包名")
                print("用法: python adb_tools.py start_app <package_name>")
                return
            package_name = sys.argv[2]
            await start_app(package_name)
        
        elif command == "swipe":
            if len(sys.argv) < 6:
                print("错误: 需要提供坐标")
                print("用法: python adb_tools.py swipe <start_x> <start_y> <end_x> <end_y> [duration]")
                return
            start_x = int(sys.argv[2])
            start_y = int(sys.argv[3])
            end_x = int(sys.argv[4])
            end_y = int(sys.argv[5])
            duration = int(sys.argv[6]) if len(sys.argv) > 6 else 500
            await swipe(start_x, start_y, end_x, end_y, duration)
        
        elif command == "back":
            await press_back()
        
        elif command == "home":
            await press_home()
        
        else:
            print(f"错误: 未知命令 '{command}'")
            print_usage()
    
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

