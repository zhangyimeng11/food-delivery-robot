"""美团外卖自动化 - 基于 DroidRun Agent

使用 DroidRun Agent 处理 UI 交互，更智能更可靠。
"""

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 美团外卖包名
MEITUAN_PACKAGE = "com.sankuai.meituan.takeoutnew"


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


class MeituanAgent:
    """美团外卖 Agent - 使用 DroidRun 处理 UI 交互"""
    
    def __init__(self, openai_api_key: str | None = None):
        """初始化
        
        Args:
            openai_api_key: OpenAI API Key，如果不提供则从环境变量读取
        """
        self._api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._tools = None
        self._last_search_results: list[MealInfo] = []
    
    async def _ensure_tools(self):
        """确保 AdbTools 已初始化"""
        if self._tools is None:
            from droidrun.tools import AdbTools
            self._tools = AdbTools()
            await self._tools.connect()
            logger.info("DroidRun 工具已连接")
    
    async def _run_agent(self, goal: str, timeout: int = 300) -> dict:
        """运行 DroidRun Agent 执行任务
        
        Args:
            goal: 任务目标
            timeout: 超时时间（秒）
            
        Returns:
            执行结果
        """
        from droidrun.agent.droid import DroidAgent
        from llama_index.llms.openai import OpenAI
        
        await self._ensure_tools()
        
        # 创建 LLM
        llm = OpenAI(
            model="gpt-5",
            api_key=self._api_key,
        )
        
        # 创建 Agent
        agent = DroidAgent(
            goal=goal,
            tools=self._tools,
            llms={
                "manager": llm,
                "executor": llm,
                "codeact": llm,
                "app_opener": llm,
            },
            timeout=timeout,
        )
        
        logger.info(f"执行任务: {goal}")
        
        try:
            result = await agent.run()
            return {
                "success": True,
                "result": result,
            }
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def _restart_meituan(self):
        """重启美团外卖 App，等待广告结束"""
        import time
        logger.info("关闭美团外卖...")
        _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")
        time.sleep(1)
        
        logger.info("启动美团外卖...")
        _run_adb(f"shell monkey -p {MEITUAN_PACKAGE} -c android.intent.category.LAUNCHER 1")
        
        logger.info("等待 5 秒（广告时间）...")
        time.sleep(5)
        logger.info("美团外卖已就绪")
    
    async def search_meals(self, keyword: str, max_results: int = 3) -> dict:
        """搜索套餐
        
        Args:
            keyword: 搜索关键词，如"奶茶"、"汉堡"
            max_results: 最大返回结果数
            
        Returns:
            搜索结果
        """
        # 重启美团确保干净状态
        self._restart_meituan()
        
        # 使用 Agent 执行搜索
        goal = f"""
如果有弹窗先关闭，打开拼好饭，搜索{keyword}，等待搜索结果加载完成，并返回json格式的前{max_results}个搜索结果，格式为：
{{
    "success": true,
    "keyword": "{keyword}",
    "result": [
        {{
            "name": "套餐名称",
            "price": "价格",
            "time": "配送时间"
        }}
    ]
}}
"""
        
        result = await self._run_agent(goal, timeout=300)
        
        if result["success"]:
            return {
                "success": True,
                "keyword": keyword,
                "message": result["result"],
            }
        else:
            return {
                "success": False,
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
6. 完成任务，告诉我已经到达支付页面

注意：
- 不要点击"极速支付"！
- 只需要到达支付页面即可
"""
        
        result = await self._run_agent(goal, timeout=180)
        
        if result["success"]:
            return {
                "success": True,
                "meal_name": meal_name,
                "message": "已进入支付页面",
                "detail": result["result"],
            }
        else:
            return {
                "success": False,
                "error": result["error"],
            }
    
    async def confirm_payment(self) -> dict:
        """确认支付
        
        Returns:
            支付结果
        """
        goal = """你现在在美团外卖的支付页面。请完成以下任务：
1. 找到并点击"极速支付"按钮
2. 等待支付完成
3. 完成任务，告诉我支付结果

注意：
- 极速支付按钮通常在页面底部
- 如果需要输入密码，请告诉我
"""
        
        result = await self._run_agent(goal, timeout=60)
        
        if result["success"]:
            return {
                "success": True,
                "message": "支付已发起",
                "detail": result["result"],
            }
        else:
            return {
                "success": False,
                "error": result["error"],
            }


# 测试代码
async def _test():
    """测试 MeituanAgent"""
    agent = MeituanAgent()
    
    print("=== 测试搜索 ===")
    result = await agent.search_meals("奶茶", max_results=3)
    print(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(_test())

