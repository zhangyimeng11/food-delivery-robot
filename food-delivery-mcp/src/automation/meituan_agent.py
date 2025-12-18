"""美团外卖自动化 - 基于 DroidRun Agent v0.4.16

使用 DroidRun Agent 处理 UI 交互，更智能更可靠。
支持 OpenAI API (GPT-4o / GPT-5)
"""

import os

# 禁用代理（避免 SOCKS 代理问题）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 美团外卖包名
MEITUAN_PACKAGE = "com.sankuai.meituan.takeoutnew"

# ADB 连接配置
PHONE_IP = os.environ.get("PHONE_IP", "192.168.1.200")
ADB_PORT = int(os.environ.get("ADB_PORT", "5555"))


@dataclass
class MealInfo:
    """套餐信息"""
    index: int
    name: str
    price: str
    merchant: str | None = None


def _run_adb(cmd: str, timeout: float = 10.0) -> str:
    """执行 ADB 命令"""
    try:
        result = subprocess.run(
            f"adb {cmd}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout + result.stderr
    except Exception as e:
        logger.error(f"ADB 命令失败: {e}")
        return ""


async def _ensure_adb_connection() -> bool:
    """确保 ADB 连接，如果断开则尝试重连"""
    target = f"{PHONE_IP}:{ADB_PORT}"
    
    try:
        # 1. 检查当前是否已连接
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        if target in result.stdout and "device" in result.stdout:
            return True
            
        logger.info(f"[ADB] 连接断开或未连接，尝试连接 {target}...")
        
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
                logger.info(f"[ADB] 重连成功: {target}")
                return True
        
        logger.warning(f"[ADB] 重连失败: {connect_res.stdout.strip()}")
        return False
        
    except Exception as e:
        logger.error(f"[ADB] 连接检查出错: {e}")
        return False


class MeituanAgent:
    """美团外卖 Agent - 使用 DroidRun v0.4.16 处理 UI 交互
    
    通过 OpenRouter 调用 Claude Haiku 4.5 模型
    """
    
    def __init__(
        self, 
        api_key: str | None = None, 
        model: str = "anthropic/claude-haiku-4.5",
    ):
        """初始化
        
        Args:
            api_key: OpenRouter API Key，如果不提供则从环境变量 OPENROUTER_API_KEY 读取
            model: OpenRouter 模型名称，如 anthropic/claude-haiku-4.5, anthropic/claude-sonnet-4.5 等
        """
        self._model = model
        self._tools = None
        self._last_search_results: list[MealInfo] = []
        
        # 获取 OpenRouter API Key
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError("必须提供 OPENROUTER_API_KEY")
    
    async def _ensure_tools(self):
        """确保 AdbTools 已初始化"""
        if self._tools is None:
            from droidrun.tools import AdbTools
            self._tools = AdbTools()
            await self._tools.connect()
            logger.info("DroidRun 工具已连接")
    
    def _create_config(self, max_steps: int = 15, reasoning: bool = True):
        """创建 DroidRun 配置
        
        Args:
            max_steps: 最大步数
            reasoning: 是否启用推理模式 (Manager+Executor)
        """
        from droidrun.config_manager.config_manager import (
            AgentConfig,
            CodeActConfig,
            ManagerConfig,
            ExecutorConfig,
            DroidrunConfig,
            DeviceConfig,
            LoggingConfig,
            TelemetryConfig,
            TracingConfig,
            ToolsConfig,
        )
        
        # Agent 配置
        agent_config = AgentConfig(
            max_steps=max_steps,
            reasoning=reasoning,
            streaming=True,
            after_sleep_action=1.0,
            wait_for_stable_ui=0.3,
            codeact=CodeActConfig(vision=False),
            manager=ManagerConfig(vision=False),
            executor=ExecutorConfig(vision=False),
        )
        
        # 设备配置
        device_config = DeviceConfig(
            serial=None,  # 自动检测
            use_tcp=False,
            platform="android",
        )
        
        # 日志配置
        logging_config = LoggingConfig(
            debug=True,
            save_trajectory="none",
        )
        
        # 遥测配置
        telemetry_config = TelemetryConfig(enabled=False)
        
        # 追踪配置
        tracing_config = TracingConfig(enabled=False)
        
        # 工具配置
        tools_config = ToolsConfig(disabled_tools=[])
        
        return DroidrunConfig(
            agent=agent_config,
            device=device_config,
            logging=logging_config,
            telemetry=telemetry_config,
            tracing=tracing_config,
            tools=tools_config,
        )
    
    def _create_llm(self):
        """创建 OpenRouter LLM 实例"""
        from llama_index.llms.openai_like import OpenAILike
        return OpenAILike(
            model=self._model,
            api_key=self._api_key,
            api_base="https://openrouter.ai/api/v1",
            temperature=0.1,
            is_chat_model=True,
        )
    
    async def _run_agent(self, goal: str, max_steps: int = 15, timeout: int = 300) -> dict:
        """运行 DroidRun Agent 执行任务
        
        Args:
            goal: 任务目标
            max_steps: 最大步数
            timeout: 超时时间（秒）
            
        Returns:
            执行结果
        """
        from droidrun.agent.droid import DroidAgent
        
        await self._ensure_tools()
        
        # 创建配置
        config = self._create_config(max_steps=max_steps, reasoning=False)
        
        # 创建 LLM
        llm = self._create_llm()
        
        # 创建 Agent - 使用新版 API
        agent = DroidAgent(
            goal=goal,
            config=config,
            llms=llm,  # 单个 LLM，所有 agent 共用
            tools=self._tools,
            timeout=timeout,
        )
        
        logger.info(f"执行任务: {goal}")
        
        try:
            # 新版 API 返回的是 handler
            handler = agent.run()
            result = await handler
            
            return {
                "success": True,
                "result": result,
            }
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _restart_meituan(self):
        """重启美团外卖 App，等待广告结束"""
        import time
        
        # 先确保 ADB 已连接
        if not await _ensure_adb_connection():
            logger.error("ADB 连接失败，无法重启美团外卖")
            return False
        
        logger.info("关闭美团外卖...")
        _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")
        time.sleep(1)
        
        logger.info("启动美团外卖...")
        _run_adb(f"shell monkey -p {MEITUAN_PACKAGE} -c android.intent.category.LAUNCHER 1")
        
        logger.info("等待 5 秒（广告时间）...")
        time.sleep(5)
        logger.info("美团外卖已就绪")
        return True
    
    async def search_meals(self, keyword: str, max_results: int = 3) -> dict:
        """搜索套餐
        
        Args:
            keyword: 搜索关键词，如"奶茶"、"汉堡"
            max_results: 最大返回结果数
            
        Returns:
            搜索结果
        """
        # 重启美团确保干净状态
        if not await self._restart_meituan():
            return {
                "success": False,
                "keyword": keyword,
                "error": f"无法连接到手机 ({PHONE_IP}:{ADB_PORT})，请检查网络或手机状态",
            }
        
        # 使用 Agent 执行搜索
        goal = f"""你现在在美团外卖首页。请完成以下任务：

1. 如果有弹窗（如红包、广告），先关闭它
2. 找到并点击"拼好饭"入口
3. 在拼好饭页面，点击搜索框进入搜索页
4. 【优先】在搜索页查找"历史搜索"或"搜索发现"区域，寻找与"{keyword}"匹配或相关的关键词并点击
5. 【备选】如果步骤4找不到匹配的关键词，则需要手动输入搜索（按以下步骤严格执行）：
   a. 【先记住坐标】在输入前，找到"搜索"按钮并用 remember() 记住它的中心坐标（从 bounds 计算中心点）
   b. 点击搜索输入框（EditText），输入"{keyword}"
   c. 等待 1-2 秒让页面更新
   d. 【用坐标点击】由于 click() 不支持坐标，使用 swipe 同点滑动模拟点击：swipe(coordinate=[x, y], coordinate2=[x, y], duration=0.1)
6. 等待搜索结果加载完成（页面会刷新显示与"{keyword}"相关的套餐）
7. 【重要】只从最终搜索结果页面提取前{max_results}个套餐信息

⚠️ 注意事项：
- 搜索框内的滚动提示词是历史记录预览，不是当前输入，请忽略
- 优先点击搜索页下方的推荐词（历史搜索/搜索发现），这样更快更准确
- 在点击搜索/推荐词之前的页面显示的是推荐套餐，不是搜索结果！
- 必须在触发搜索后，等待页面刷新，才能从新页面提取结果
- 搜索结果中的套餐名称通常会包含或关联关键词"{keyword}"
- 【关键】输入文字后页面元素的 index 会变化！所以必须在输入前记住搜索按钮的坐标，然后用 swipe 同点滑动模拟点击！

完成后，请以 JSON 格式返回搜索结果：
{{
    "success": true,
    "keyword": "{keyword}",
    "meals": [
        {{
            "name": "套餐名称",
            "price": "价格",
            "delivery_time": "配送时间"
        }}
    ]
}}
"""
        
        result = await self._run_agent(goal, max_steps=20, timeout=300)
        
        if result["success"]:
            # 尝试解析 Agent 返回的 JSON 结果，提取 meals 数组
            try:
                import json
                if hasattr(result["result"], "reason"):
                    data = json.loads(result["result"].reason)
                    meals = data.get("meals", [])
                    # 统一字段名：将 time 转换为 delivery_time
                    for meal in meals:
                        if "time" in meal and "delivery_time" not in meal:
                            meal["delivery_time"] = meal.pop("time")
                    return {
                        "success": True,
                        "keyword": keyword,
                        "meals": meals,
                    }
            except Exception:
                pass
            # 解析失败时返回原始结果
            return {
                "success": True,
                "keyword": keyword,
                "meals": [],  # 无法解析时返回空数组
            }
        else:
            return {
                "success": False,
                "keyword": keyword,
                "error": result["error"],
            }
    
    async def place_order(self, meal_name: str) -> dict:
        """下单指定套餐（到支付页面，不支付）
        
        Args:
            meal_name: 套餐名称
            
        Returns:
            下单结果
        """
        goal = f"""你现在在美团外卖拼好饭的搜索结果页面。请完成以下任务：

1. 找到并点击名称包含"{meal_name}"的套餐，进入详情页
2. 在详情页点击右下角的"马上抢"或"立即购买"按钮
3. 如果弹出规格选择，再次点击"马上抢"确认
4. 等待进入支付页面（看到"极速支付"按钮）
5. 停在支付页面，不要点击支付！

⚠️ 重要：不要点击"极速支付"！只需要到达支付页面即可。

完成后告诉我已经到达支付页面。
"""
        
        result = await self._run_agent(goal, max_steps=15, timeout=180)
        
        if result["success"]:
            # TODO: 解析最终价格（目前 Agent 不返回价格，需要额外处理）
            return {
                "success": True,
                "meal_name": meal_name,
                "final_price": "",  # Agent 暂不提取价格
            }
        else:
            return {
                "success": False,
                "meal_name": meal_name,
                "error": result["error"],
            }
    
    async def confirm_payment(self) -> dict:
        """确认支付
        
        Returns:
            支付结果
        """
        goal = """你现在在美团外卖的支付页面。请完成以下任务：

1. 找到并点击"极速支付"按钮
2. 如果弹出支付确认，点击"免密支付"或输入密码
3. 等待支付完成

完成后告诉我支付结果。
"""
        
        result = await self._run_agent(goal, max_steps=10, timeout=60)
        
        if result["success"]:
            return {
                "success": True,
                "message": "支付已发起",
            }
        else:
            return {
                "success": False,
                "error": result["error"],
            }


# 测试代码
async def _test():
    """测试 MeituanAgent：搜索 + 下单，统计时间"""
    import time
    
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    # 使用 OpenRouter + Claude Haiku 4.5
    agent = MeituanAgent(
        api_key="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",
        model="anthropic/claude-haiku-4.5",
    )
    
    # 步骤1：搜索炒面
    print("=== 步骤1：搜索炒面 ===")
    start_time = time.time()
    search_result = await agent.search_meals("炒面", max_results=3)
    search_time = time.time() - start_time
    print(f"搜索结果: {search_result}")
    print(f"⏱️ 搜索耗时: {search_time:.1f} 秒")
    
    if not search_result.get("success"):
        print("搜索失败，无法继续下单测试")
        return
    
    # 从结果中提取第一个套餐名称（新格式直接有 meals 数组）
    meals = search_result.get("meals", [])
    if meals:
        first_meal = meals[0].get("name", "炒面")
        print(f"\n第一个套餐: {first_meal}")
    else:
        first_meal = "炒面"  # 备选
        print(f"\n未找到套餐，使用关键词: {first_meal}")
    
    # 步骤2：下单第一个套餐（不点支付）
    print(f"\n=== 步骤2：下单套餐 ===")
    print(f"准备下单: {first_meal}")
    start_time = time.time()
    order_result = await agent.place_order(first_meal)
    order_time = time.time() - start_time
    print(f"下单结果: {order_result}")
    print(f"⏱️ 下单耗时: {order_time:.1f} 秒")
    
    # 总结
    print("\n" + "=" * 50)
    print("📊 时间统计")
    print("=" * 50)
    print(f"搜索耗时: {search_time:.1f} 秒")
    print(f"下单耗时: {order_time:.1f} 秒")
    print(f"总耗时: {search_time + order_time:.1f} 秒")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(_test())
