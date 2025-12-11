"""美团外卖 App 自动化操作"""

import json
import logging
import time
import re
from dataclasses import dataclass

import httpx
import uiautomator2 as u2

from .device import DeviceManager, get_device_manager
from ..config import get_config

logger = logging.getLogger(__name__)

# 美团外卖 App 包名
MEITUAN_PACKAGE = "com.sankuai.meituan.takeoutnew"


@dataclass
class MealInfo:
    """套餐信息"""
    index: int
    name: str
    price: str
    time: str | None = None
    merchant: str | None = None


@dataclass
class OrderStatus:
    """订单状态"""
    status: str
    progress: str | None = None
    estimated_arrival: str | None = None


class MeituanAutomation:
    """美团外卖 App 自动化操作"""
    
    def __init__(self, device_manager: DeviceManager | None = None):
        self._dm = device_manager or get_device_manager()
        self._last_search_results: list[MealInfo] = []
    
    @property
    def device(self) -> u2.Device:
        """获取设备实例"""
        return self._dm.ensure_connected()
    
    def _wait(self, seconds: float = 1.0) -> None:
        """等待指定时间"""
        time.sleep(seconds)
    
    def _wait_for_element(
        self,
        timeout: float = 10.0,
        **kwargs
    ) -> u2.UiObject | None:
        """等待元素出现
        
        Args:
            timeout: 超时时间（秒）
            **kwargs: 元素定位参数
            
        Returns:
            找到的元素，超时返回 None
        """
        start = time.time()
        while time.time() - start < timeout:
            element = self.device(**kwargs)
            if element.exists:
                return element
            time.sleep(0.3)
        return None
    
    def _click_if_exists(self, timeout: float = 2.0, **kwargs) -> bool:
        """如果元素存在则点击
        
        Returns:
            是否点击成功
        """
        element = self._wait_for_element(timeout=timeout, **kwargs)
        if element:
            element.click()
            return True
        return False
    
    def _try_dismiss_popup(self) -> bool:
        """尝试关闭弹窗（常见按钮 + NAF 关闭图标）"""
        # 文字按钮
        for text in ["我知道了", "关闭", "暂不", "取消"]:
            if self._click_if_exists(timeout=0.2, text=text):
                logger.debug(f"关闭弹窗: {text}")
                self._wait(0.3)
                return True
        
        # NAF 关闭按钮（无文字的 X 图标，常见于优惠券弹窗）
        # 特征：FrameLayout, clickable, NAF=true, 小尺寸
        try:
            from lxml import etree
            xml = self.device.dump_hierarchy()
            root = etree.fromstring(xml.encode())
            
            for node in root.iter("node"):
                if node.get("clickable") != "true":
                    continue
                if node.get("class") not in ["android.widget.FrameLayout", "android.widget.ImageView"]:
                    continue
                if node.get("text") or node.get("content-desc"):
                    continue  # 有文字的跳过
                
                bounds = node.get("bounds", "")
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if not match:
                    continue
                
                x1, y1, x2, y2 = map(int, match.groups())
                w, h = x2 - x1, y2 - y1
                
                # 小按钮（约 50-150 像素）且在屏幕中央偏下（弹窗关闭按钮位置）
                if 50 <= w <= 200 and 50 <= h <= 200 and y1 > 1000:
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    logger.debug(f"点击 NAF 关闭按钮: ({cx}, {cy})")
                    self.device.click(cx, cy)
                    self._wait(0.3)
                    return True
        except Exception as e:
            logger.debug(f"NAF 关闭检测失败: {e}")
        
        return False
    
    def _dismiss_with_vl(self) -> bool:
        """使用 VL 模型识别并关闭弹窗"""
        config = get_config()
        if not config.llm.api_key:
            return False
        
        try:
            import base64
            import io
            
            screenshot = self.device.screenshot()
            buffer = io.BytesIO()
            screenshot.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            prompt = """这是手机App截图。页面上有弹窗吗？如果有，关闭按钮在哪？
返回JSON：{"has_popup": bool, "close_button": {"x": 数字, "y": 数字} 或 null}"""

            with httpx.Client(timeout=30, trust_env=False) as client:
                response = client.post(
                    f"{config.llm.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.llm.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "qwen-vl-plus",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                                {"type": "text", "text": prompt},
                            ],
                        }],
                    },
                )
                response.raise_for_status()
                
                content = response.json()["choices"][0]["message"]["content"]
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                    if result.get("has_popup") and result.get("close_button"):
                        x, y = result["close_button"]["x"], result["close_button"]["y"]
                        logger.info(f"VL 识别到弹窗，点击 ({x}, {y})")
                        self.device.click(x, y)
                        self._wait(0.5)
                        return True
                        
        except Exception as e:
            logger.warning(f"VL 处理失败: {e}")
        
        return False
    
    def _wait_home(self, timeout: float = 3) -> bool:
        """等待到达首页（拼好饭入口出现）"""
        return self.device(text="拼好饭").wait(timeout=timeout)
    
    def _wait_left_home(self, timeout: float = 3) -> bool:
        """等待离开首页（拼好饭入口消失）"""
        return self.device(text="拼好饭").wait_gone(timeout=timeout)
    
    def _wait_search_page(self, timeout: float = 3) -> bool:
        """等待进入搜索页"""
        return self.device(text="历史搜索").wait(timeout=timeout) or \
               self.device(text="搜索发现").wait(timeout=timeout)
    
    def launch_app(self) -> bool:
        """启动美团外卖 App，等待到首页"""
        logger.info("启动美团外卖 App")
        self.device.app_start(MEITUAN_PACKAGE, stop=True)
        
        if self._wait_home(timeout=3):
            logger.info("已到达首页")
            return True
        
        # 可能有弹窗，尝试关闭
        if self._try_dismiss_popup() or self._dismiss_with_vl():
            if self._wait_home(timeout=2):
                logger.info("已到达首页")
                return True
        
        return False
    
    def go_to_pinhaofan(self) -> bool:
        """点击拼好饭，等待离开首页"""
        self._click_if_exists(timeout=1, text="拼好饭")
        
        if self._wait_left_home(timeout=2):
            logger.info("已进入拼好饭")
            return True
        
        # 可能有弹窗，尝试关闭
        if self._try_dismiss_popup() or self._dismiss_with_vl():
            self._click_if_exists(timeout=1, text="拼好饭")
            if self._wait_left_home(timeout=2):
                logger.info("已进入拼好饭")
                return True
        
        return False
    
    def search_meals(self, keyword: str, max_results: int = 3) -> list[MealInfo]:
        """搜索套餐
        
        Args:
            keyword: 搜索关键词
            max_results: 最大返回结果数
            
        Returns:
            套餐列表
        """
        logger.info(f"搜索套餐: {keyword}")
        
        # 启动 App
        self.launch_app()
        
        # 进入拼好饭
        if not self.go_to_pinhaofan():
            raise RuntimeError("无法进入拼好饭页面")
        
        # 点击搜索框，等待进入搜索页
        self._click_if_exists(timeout=1, textContains="搜索")
        
        if not self._wait_search_page(timeout=3):
            raise RuntimeError("未进入搜索页")
        
        # 输入搜索关键词
        input_field = self._wait_for_element(timeout=2, className="android.widget.EditText")
        if not input_field:
            raise RuntimeError("未找到输入框")
        
        input_field.set_text(keyword)
        self._wait(0.3)
        
        # 点击搜索按钮
        if not self._click_if_exists(timeout=1, text="搜索"):
            self.device.press("enter")
        
        self._wait(1.5)
        
        # 提取搜索结果
        meals = self._extract_search_results(max_results)
        self._last_search_results = meals
        
        return meals
    
    def _extract_search_results(self, max_results: int = 3) -> list[MealInfo]:
        """提取搜索结果 - 使用 LLM 智能解析
        
        Args:
            max_results: 最大结果数
            
        Returns:
            套餐列表
        """
        # 等待搜索结果加载
        self._wait(1)
        
        # 获取页面 XML
        xml = self.device.dump_hierarchy()
        
        # 提取文本
        texts = self._extract_texts_from_xml(xml)
        logger.info(f"提取到 {len(texts)} 个文本元素")
        
        # 使用 LLM 解析
        meals = self._parse_meals_with_llm(texts, max_results)
        
        if not meals:
            logger.warning("LLM 解析失败，使用简化方法")
            meals = self._extract_results_simple(xml, max_results)
        
        logger.info(f"找到 {len(meals)} 个套餐")
        return meals
    
    def _extract_texts_from_xml(self, xml: str) -> list[str]:
        """从 XML 提取搜索结果区域的文本"""
        elements = re.findall(r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]', xml)
        
        texts = []
        skip_words = {'搜索', '历史搜索', '搜索发现', '换一批', '筛选', '排序', '综合排序'}
        
        for text, x, y in elements:
            y = int(y)
            if y > 350 and len(text) > 1:
                if text not in skip_words:
                    if not text.replace('.', '').replace(':', '').isdigit():
                        texts.append(text)
        
        return texts
    
    def _parse_meals_with_llm(self, texts: list[str], max_results: int) -> list[MealInfo]:
        """使用 LLM 解析套餐信息"""
        config = get_config()
        
        if not config.llm.api_key:
            logger.warning("未配置 LLM API key")
            return []
        
        prompt = f"""你是一个外卖信息提取助手。下面是从美团外卖拼好饭搜索结果页面提取的文本列表，请从中识别出套餐信息。

文本列表：
{chr(10).join(texts[:100])}

请提取前 {max_results} 个套餐的信息，每个套餐包含：
- name: 套餐名称（如"珍珠奶茶(中杯)"、"麻辣香锅4荤5素"）
- price: 价格（如"¥4.9"）
- merchant: 商家名称（如"蜜雪冰城（五道口店）"）
- time: 配送时间（如"25分钟"）

请只返回 JSON 数组格式，不要其他内容：
[{{"name": "...", "price": "...", "merchant": "...", "time": "..."}}]"""

        try:
            # 国内 API 不走代理
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
                    meals_data = json.loads(json_match.group())
                    return [
                        MealInfo(
                            index=i,
                            name=m.get("name", ""),
                            price=m.get("price", ""),
                            time=m.get("time"),
                            merchant=m.get("merchant"),
                        )
                        for i, m in enumerate(meals_data)
                    ]
                    
        except Exception as e:
            logger.error(f"LLM 解析失败: {e}")
        
        return []
    
    def _extract_results_simple(self, xml: str, max_results: int) -> list[MealInfo]:
        """简化的结果提取方法（fallback）"""
        meals: list[MealInfo] = []
        
        price_pattern = r'text="[¥￥](\d+\.?\d*)"'
        prices = re.findall(price_pattern, xml)
        
        for i, price in enumerate(prices[:max_results]):
            meals.append(MealInfo(
                index=i,
                name=f"套餐 {i + 1}",
                price=f"¥{price}",
            ))
        
        return meals
    
    def place_order(self, meal_index: int = 0, meal_name: str | None = None) -> dict:
        """下单指定套餐
        
        Args:
            meal_index: 套餐索引（基于上次搜索结果）
            meal_name: 套餐名称（可选，直接按名称点击）
            
        Returns:
            下单结果
        """
        logger.info(f"下单套餐: index={meal_index}, name={meal_name}")
        
        selected_meal: MealInfo | None = None
        
        # 如果提供了名称，尝试直接点击
        if meal_name:
            if self._click_if_exists(timeout=3, textContains=meal_name):
                selected_meal = MealInfo(index=0, name=meal_name, price="")
        else:
            # 使用索引
            if self._last_search_results and meal_index < len(self._last_search_results):
                selected_meal = self._last_search_results[meal_index]
                # 尝试点击套餐
                if selected_meal.name:
                    self._click_if_exists(timeout=3, textContains=selected_meal.name)
            else:
                # 点击第 n 个可点击的卡片
                try:
                    items = self.device(className="android.view.ViewGroup", clickable=True)
                    if len(items) > meal_index:
                        items[meal_index].click()
                        selected_meal = MealInfo(
                            index=meal_index, 
                            name=f"套餐 {meal_index + 1}",
                            price=""
                        )
                except Exception as e:
                    logger.error(f"点击套餐失败: {e}")
        
        if not selected_meal:
            return {
                "success": False,
                "error": "未找到指定套餐",
            }
        
        self._wait(1)
        
        # 点击"马上抢"按钮（详情页）
        if self._click_if_exists(timeout=1, textContains="马上抢"):
            logger.info("点击: 马上抢")
        elif self._click_if_exists(timeout=1, textContains="立即抢"):
            logger.info("点击: 立即抢")
        
        self._wait(1)
        
        # 规格选择页再次点击"马上抢"
        if self._click_if_exists(timeout=1, textContains="马上抢"):
            logger.info("确认规格: 马上抢")
        
        # 等待进入支付页（极速支付出现）
        if self.device(text="极速支付").wait(timeout=5):
            logger.info("已进入支付页")
            
            # 获取最终价格（支付页底部红色价格）
            price = ""
            xml = self.device.dump_hierarchy()
            # 找所有价格，取最后一个（底部的最终价格）
            prices = re.findall(r'text="[¥￥](\d+\.?\d*)"', xml)
            if prices:
                price = f"¥{prices[-1]}"
            
            return {
                "success": True,
                "meal_name": selected_meal.name,
                "price": price,
                "message": "已进入支付页",
            }
        
        return {
            "success": False,
            "meal_name": selected_meal.name,
            "error": "未能进入支付页",
        }
    
    def check_order_status(self) -> OrderStatus:
        """查询最新订单状态
        
        Returns:
            订单状态信息
        """
        logger.info("查询订单状态")
        
        # 启动 App 并进入订单页
        self.launch_app()
        self._try_dismiss_popup()
        
        # 点击"订单"Tab
        order_tab_locators = [
            {"text": "订单"},
            {"description": "订单"},
            {"textContains": "订单"},
        ]
        
        for locator in order_tab_locators:
            if self._click_if_exists(timeout=3, **locator):
                break
        
        self._wait(2)
        self._try_dismiss_popup()
        
        # 提取订单状态
        xml = self.device.dump_hierarchy()
        
        # 订单状态关键词
        status_keywords = {
            "待支付": "待支付",
            "商家接单": "商家接单中",
            "骑手已取餐": "骑手已取餐",
            "配送中": "配送中",
            "已送达": "已送达",
            "已完成": "已完成",
        }
        
        status = "未知"
        progress = None
        estimated_arrival = None
        
        for keyword, status_value in status_keywords.items():
            if keyword in xml:
                status = status_value
                break
        
        # 提取预计送达时间
        time_match = re.search(r'(\d{1,2}:\d{2})\s*送达', xml)
        if time_match:
            estimated_arrival = time_match.group(1)
        
        # 提取进度信息
        progress_patterns = [
            r'(骑手.*?取餐)',
            r'(正在.*?配送)',
            r'(预计.*?送达)',
        ]
        
        for pattern in progress_patterns:
            match = re.search(pattern, xml)
            if match:
                progress = match.group(1)
                break
        
        return OrderStatus(
            status=status,
            progress=progress,
            estimated_arrival=estimated_arrival,
        )
    
    def open_notification_panel(self) -> bool:
        """打开通知栏
        
        Returns:
            是否成功打开
        """
        try:
            self.device.open_notification()
            self._wait(0.5)
            return True
        except Exception as e:
            logger.error(f"打开通知栏失败: {e}")
            return False
    
    def close_notification_panel(self) -> bool:
        """关闭通知栏
        
        Returns:
            是否成功关闭
        """
        try:
            self.device.press("back")
            self._wait(0.3)
            return True
        except Exception as e:
            logger.error(f"关闭通知栏失败: {e}")
            return False
    
    def get_notification_texts(self) -> list[str]:
        """获取通知栏所有文本
        
        Returns:
            通知文本列表
        """
        texts: list[str] = []
        
        if not self.open_notification_panel():
            return texts
        
        try:
            # 获取所有文本元素
            for elem in self.device(className="android.widget.TextView"):
                if elem.exists:
                    text = elem.get_text()
                    if text:
                        texts.append(text)
        except Exception as e:
            logger.error(f"获取通知文本失败: {e}")
        finally:
            self.close_notification_panel()
        
        return texts

