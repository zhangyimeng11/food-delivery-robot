#!/usr/bin/env python3
"""测试搜索流程 - 调试版本

步骤：打开美团 → 拼好饭 → 搜索 → 提取结果
每一步都保存页面 XML 便于分析
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import uiautomator2 as u2

# 创建 debug 输出目录
DEBUG_DIR = Path(__file__).parent / "debug_output"
DEBUG_DIR.mkdir(exist_ok=True)


def save_xml(device: u2.Device, step_name: str) -> str:
    """保存页面 XML"""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{timestamp}_{step_name}.xml"
    filepath = DEBUG_DIR / filename
    
    xml = device.dump_hierarchy()
    filepath.write_text(xml, encoding="utf-8")
    print(f"  📄 已保存 XML: {filepath}")
    return xml


def save_screenshot(device: u2.Device, step_name: str) -> None:
    """保存截图"""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{timestamp}_{step_name}.png"
    filepath = DEBUG_DIR / filename
    
    device.screenshot(str(filepath))
    print(f"  📷 已保存截图: {filepath}")


def wait_and_save(device: u2.Device, step_name: str, wait_seconds: float = 2.0):
    """等待并保存状态"""
    print(f"\n⏳ 等待 {wait_seconds} 秒...")
    time.sleep(wait_seconds)
    save_screenshot(device, step_name)
    return save_xml(device, step_name)


def click_if_exists(device: u2.Device, timeout: float = 3.0, **kwargs) -> bool:
    """如果元素存在则点击"""
    elem = device(**kwargs)
    if elem.wait(timeout=timeout):
        elem.click()
        return True
    return False


def extract_meal_cards(device: u2.Device, max_results: int = 5) -> list[dict]:
    """提取套餐卡片信息
    
    基于 UI 结构提取套餐名、价格、商家、配送时间
    """
    import re
    
    meals = []
    xml = device.dump_hierarchy()
    
    # 方法1: 基于 clickable 卡片容器提取
    # 找所有可点击的区域（bounds 在搜索结果区域 y > 240）
    card_pattern = r'clickable="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    
    # 提取所有文本元素
    text_elements = re.findall(r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    
    # 按 y 坐标分组，找出套餐卡片
    # 每个卡片大约 400px 高
    card_y_positions = []
    
    # 找价格元素位置作为卡片锚点
    for text, x1, y1, x2, y2 in text_elements:
        if text.startswith('¥') or text.startswith('￥'):
            y = int(y1)
            if y > 240:  # 排除搜索栏
                card_y_positions.append(y)
    
    # 对每个价格位置，提取该区域的套餐信息
    for idx, price_y in enumerate(card_y_positions[:max_results]):
        # 定义卡片区域（价格上方约 300px 到价格下方约 50px）
        y_min = price_y - 350
        y_max = price_y + 80
        
        # 收集该区域的所有文本
        card_texts = []
        for text, x1, y1, x2, y2 in text_elements:
            y = int(y1)
            if y_min <= y <= y_max and text.strip():
                card_texts.append(text)
        
        # 从收集的文本中提取信息
        meal_info = {
            'index': idx,
            'name': '',
            'price': '',
            'merchant': '',
            'time': '',
        }
        
        for text in card_texts:
            # 价格
            if (text.startswith('¥') or text.startswith('￥')) and not meal_info['price']:
                meal_info['price'] = text
            # 配送时间
            elif '分钟' in text and not meal_info['time']:
                meal_info['time'] = text
            # 商家（包含"店"字，且不是标签文字）
            elif ('店' in text or '餐厅' in text) and len(text) > 3 and not meal_info['merchant']:
                meal_info['merchant'] = text
            # 套餐名（第一个较长的非标签文本）
            elif len(text) > 2 and not meal_info['name'] and not any(x in text for x in ['已拼', '分钟', '¥', '￥', '收录', '免拼', 'km', '连锁']):
                meal_info['name'] = text
        
        if meal_info['name'] and meal_info['price']:
            meals.append(meal_info)
    
    return meals


def dismiss_popups(device: u2.Device, max_attempts: int = 3):
    """关闭弹窗"""
    popup_buttons = [
        {"text": "我知道了"},
        {"text": "关闭"},
        {"text": "取消"},
        {"text": "暂不"},
        {"text": "以后再说"},
        {"text": "下次再说"},
        {"text": "不用了"},
        {"textContains": "知道了"},
        {"description": "关闭"},
    ]
    
    for _ in range(max_attempts):
        dismissed = False
        for btn in popup_buttons:
            if click_if_exists(device, timeout=0.5, **btn):
                print(f"  ✓ 关闭弹窗: {btn}")
                dismissed = True
                time.sleep(0.3)
                break
        if not dismissed:
            break


def main():
    keyword = "奶茶"  # 默认搜索词
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
    
    print("=" * 60)
    print("美团拼好饭搜索流程测试")
    print(f"搜索关键词: {keyword}")
    print(f"调试输出目录: {DEBUG_DIR}")
    print("=" * 60)
    
    # 连接设备
    print("\n[1/6] 连接设备...")
    try:
        d = u2.connect()
        info = d.info
        print(f"  ✓ 已连接: {info.get('productName', 'Unknown')}")
        print(f"  屏幕: {info.get('displayWidth')}x{info.get('displayHeight')}")
    except Exception as e:
        print(f"  ✗ 连接失败: {e}")
        return
    
    # 美团外卖包名
    MEITUAN_PKG = "com.sankuai.meituan.takeoutnew"
    
    # Step 1: 启动美团外卖
    print("\n[2/6] 启动美团外卖 App...")
    d.app_start(MEITUAN_PKG, stop=True)
    wait_and_save(d, "01_app_launched", 3)
    dismiss_popups(d)
    wait_and_save(d, "01_after_popups", 1)
    
    # Step 2: 点击拼好饭入口
    print("\n[3/6] 寻找并点击拼好饭入口...")
    
    # 尝试多种定位方式
    pinhaofan_found = False
    locators = [
        {"text": "拼好饭"},
        {"textContains": "拼好饭"},
        {"description": "拼好饭"},
        {"textMatches": ".*拼好饭.*"},
    ]
    
    for loc in locators:
        print(f"  尝试定位: {loc}")
        if click_if_exists(d, timeout=2, **loc):
            print(f"  ✓ 点击成功: {loc}")
            pinhaofan_found = True
            break
    
    if not pinhaofan_found:
        print("  ✗ 未找到拼好饭入口，保存当前页面分析...")
        wait_and_save(d, "02_pinhaofan_not_found", 1)
        
        # 打印页面上的文本元素帮助分析
        print("\n  页面上的文本元素:")
        for elem in d(className="android.widget.TextView"):
            try:
                text = elem.get_text()
                if text and len(text) < 30:
                    print(f"    - {text}")
            except:
                pass
        return
    
    wait_and_save(d, "02_pinhaofan_entered", 2)
    dismiss_popups(d)
    
    # Step 3: 点击搜索框
    print("\n[4/6] 点击搜索框...")
    
    search_found = False
    search_locators = [
        {"text": "搜索"},
        {"textContains": "搜索"},
        {"textContains": "想吃"},
        {"resourceIdMatches": ".*search.*"},
        {"className": "android.widget.EditText"},
    ]
    
    for loc in search_locators:
        print(f"  尝试定位: {loc}")
        if click_if_exists(d, timeout=2, **loc):
            print(f"  ✓ 点击成功: {loc}")
            search_found = True
            break
    
    if not search_found:
        print("  ✗ 未找到搜索框，保存当前页面分析...")
        wait_and_save(d, "03_search_not_found", 1)
        return
    
    wait_and_save(d, "03_search_clicked", 1.5)
    
    # Step 4: 输入搜索词
    print(f"\n[5/6] 输入搜索词: {keyword}")
    
    # 找输入框
    input_field = d(className="android.widget.EditText")
    if input_field.wait(timeout=3):
        input_field.set_text(keyword)
        print(f"  ✓ 已输入: {keyword}")
    else:
        print("  ✗ 未找到输入框")
        wait_and_save(d, "04_input_not_found", 1)
        return
    
    wait_and_save(d, "04_keyword_entered", 1)
    
    # 点击搜索按钮
    print("  点击搜索按钮...")
    if d(text="搜索").exists:
        d(text="搜索").click()
        print("  ✓ 已点击搜索")
    else:
        print("  ✗ 未找到搜索按钮")
    
    wait_and_save(d, "05_search_submitted", 3)
    dismiss_popups(d)
    wait_and_save(d, "05_after_popups", 1)
    
    # Step 5: 提取搜索结果
    print("\n[6/6] 提取搜索结果...")
    
    import re
    
    meals = extract_meal_cards(d)
    
    if meals:
        print(f"\n  ✓ 成功提取 {len(meals)} 个套餐:")
        for i, meal in enumerate(meals[:5]):
            print(f"\n    [{i}] {meal['name']}")
            print(f"        价格: {meal['price']}")
            print(f"        商家: {meal['merchant']}")
            print(f"        时间: {meal['time']}")
    else:
        print("\n  ✗ 未能提取到套餐信息，使用 fallback 方法...")
        xml = d.dump_hierarchy()
        prices = re.findall(r'text="[¥￥](\d+\.?\d*)"', xml)
        print(f"    找到 {len(prices)} 个价格: {prices[:5]}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print(f"调试文件已保存到: {DEBUG_DIR}")
    print("请查看 XML 文件分析 UI 结构，优化定位器")
    print("=" * 60)


if __name__ == "__main__":
    main()

