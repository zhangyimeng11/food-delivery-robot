"""自由任务执行模块 - 基于 DroidRun Agent

让语音 Agent 能够执行任意任务，不再局限于固定流程。
DroidRun Agent 负责理解屏幕、决策操作、处理异常。
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 禁用代理
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

logger = logging.getLogger(__name__)

# 美团外卖包名
MEITUAN_PACKAGE = "com.sankuai.meituan.takeoutnew"

# ADB 配置 - 从配置文件读取
def _get_phone_config():
    """获取手机配置"""
    from src.config import get_config
    config = get_config()
    return config.phone.ip, config.phone.adb_port

# 延迟加载，避免循环导入
_phone_ip = None
_adb_port = None

def _get_adb_target():
    """获取 ADB 连接目标"""
    global _phone_ip, _adb_port
    if _phone_ip is None:
        _phone_ip, _adb_port = _get_phone_config()
    return _phone_ip, _adb_port

# LLM 配置 - 使用 OpenRouter + Claude Haiku 4.5
LLM_CONFIG = {
    "provider": "openrouter",
    "api_key": os.environ.get("OPENROUTER_API_KEY", "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"),
    "base_url": "https://openrouter.ai/api/v1",
    "model": os.environ.get("LLM_MODEL", "anthropic/claude-haiku-4.5"),
}

# 并发控制
_task_lock = asyncio.Lock()
_current_task: asyncio.Task | None = None


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
    """确保 ADB 连接"""
    phone_ip, adb_port = _get_adb_target()
    target = f"{phone_ip}:{adb_port}"
    
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        if target in result.stdout and "device" in result.stdout:
            return True
            
        logger.info(f"[ADB] 尝试连接 {target}...")
        subprocess.run(["adb", "disconnect", target], capture_output=True)
        connect_res = subprocess.run(["adb", "connect", target], capture_output=True, text=True)
        
        if f"connected to {target}" in connect_res.stdout or "already connected" in connect_res.stdout:
            verify_res = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            if target in verify_res.stdout and "device" in verify_res.stdout:
                logger.info(f"[ADB] 连接成功: {target}")
                return True
        
        logger.warning(f"[ADB] 连接失败")
        return False
        
    except Exception as e:
        logger.error(f"[ADB] 连接出错: {e}")
        return False


async def _cancel_current_task():
    """取消当前正在执行的任务"""
    global _current_task
    if _current_task and not _current_task.done():
        _current_task.cancel()
        try:
            await _current_task
        except asyncio.CancelledError:
            pass
        _run_adb(f"shell am force-stop {MEITUAN_PACKAGE}")


def _create_droidrun_config(max_steps: int = 20, reasoning: bool = False):
    """创建 DroidRun 配置"""
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
    
    agent_config = AgentConfig(
        max_steps=max_steps,
        reasoning=reasoning,  # False = CodeAct 直接执行, 更快
        streaming=True,
        after_sleep_action=1.0,
        wait_for_stable_ui=0.3,
        codeact=CodeActConfig(vision=False),
        manager=ManagerConfig(vision=False),
        executor=ExecutorConfig(vision=False),
    )
    
    device_config = DeviceConfig(
        serial=None,
        use_tcp=False,
        platform="android",
    )
    
    logging_config = LoggingConfig(
        debug=False,
        save_trajectory="none",
    )
    
    return DroidrunConfig(
        agent=agent_config,
        device=device_config,
        logging=logging_config,
        telemetry=TelemetryConfig(enabled=False),
        tracing=TracingConfig(enabled=False),
        tools=ToolsConfig(disabled_tools=[]),
    )


def _create_llm():
    """创建 LLM 实例"""
    from llama_index.llms.openai_like import OpenAILike
    
    return OpenAILike(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        api_base=LLM_CONFIG["base_url"],
        temperature=0.1,
        is_chat_model=True,
    )


def _format_response_for_voice(raw_result: Any, task: str) -> dict:
    """将 Agent 结果格式化为语音友好的输出
    
    语音 Agent 需要的是：
    1. 简洁的成功/失败状态
    2. 可以直接朗读给用户的 message
    3. 结构化的数据（如果有的话）
    """
    response = {
        "success": False,
        "message": "",  # 可直接朗读的消息
        "data": None,   # 结构化数据（可选）
        "task": task,
    }
    
    try:
        # 从 DroidRun Result 提取信息
        if hasattr(raw_result, "success"):
            response["success"] = raw_result.success
        elif isinstance(raw_result, dict):
            response["success"] = raw_result.get("success", False)
        
        # 提取 reason 作为消息
        reason = ""
        if hasattr(raw_result, "reason"):
            reason = raw_result.reason
        elif isinstance(raw_result, dict):
            reason = raw_result.get("reason", "")
        
        # 尝试解析 JSON 数据
        if reason:
            try:
                # 尝试从 reason 中提取 JSON
                json_match = re.search(r'\{[\s\S]*\}', reason)
                if json_match:
                    data = json.loads(json_match.group())
                    response["data"] = data
                    
                    # 根据数据类型生成语音友好的消息
                    if "meals" in data:
                        meals = data["meals"]
                        if meals:
                            msg_parts = [f"找到{len(meals)}个结果"]
                            for i, meal in enumerate(meals[:3], 1):
                                name = meal.get("name", "未知")
                                price = meal.get("price", "")
                                msg_parts.append(f"第{i}个是{name}，{price}")
                            response["message"] = "。".join(msg_parts)
                        else:
                            response["message"] = "没有找到相关的套餐"
                    elif "orders" in data:
                        orders = data["orders"]
                        response["message"] = f"您有{len(orders)}个订单"
                    else:
                        # 通用处理
                        response["message"] = reason[:200]  # 截断太长的内容
                else:
                    # 不是 JSON，直接用 reason
                    response["message"] = reason[:200]
            except (json.JSONDecodeError, Exception):
                response["message"] = reason[:200]
        
        # 如果还没有消息，生成默认消息
        if not response["message"]:
            if response["success"]:
                response["message"] = "任务已完成"
            else:
                response["message"] = "任务执行失败，请重试"
                
    except Exception as e:
        logger.error(f"格式化响应失败: {e}")
        response["message"] = "处理结果时出现错误"
    
    return response


async def execute_task(
    task_description: str,
    app: str = "meituan",
    max_steps: int = 20,
    timeout: int = 300,
) -> dict:
    """执行自由任务
    
    这是一个通用的任务执行接口，语音 Agent 只需要描述任务，
    DroidRun Agent 会自动决定如何操作手机完成任务。
    
    Args:
        task_description: 任务描述，用自然语言说明想做什么
            示例:
            - "打开美团拼好饭，搜索牛肉面，告诉我有哪些选择"
            - "帮我下单第一个搜索结果"
            - "查看我的历史订单"
            - "看看有什么8元以下的套餐"
            - "取消最近的一个订单"
        app: 目标应用，目前支持 "meituan"
        max_steps: 最大操作步数，防止无限循环
        timeout: 超时时间（秒）
        
    Returns:
        dict: {
            "success": bool,        # 是否成功
            "message": str,         # 可朗读的结果消息
            "data": dict | None,    # 结构化数据（如搜索结果）
            "task": str,            # 原始任务描述
        }
    """
    global _current_task
    
    # 取消正在进行的任务
    await _cancel_current_task()
    
    async with _task_lock:
        _current_task = asyncio.current_task()
        
        try:
            return await _execute_task_impl(task_description, app, max_steps, timeout)
        except asyncio.CancelledError:
            return {
                "success": False,
                "message": "操作被取消",
                "data": None,
                "task": task_description,
            }


async def _execute_task_impl(
    task_description: str,
    app: str,
    max_steps: int,
    timeout: int,
) -> dict:
    """执行任务的实际实现"""
    from droidrun.agent.droid import DroidAgent
    from droidrun.tools import AdbTools
    
    # 确保 ADB 连接
    if not await _ensure_adb_connection():
        return {
            "success": False,
            "message": f"无法连接到手机，请检查手机是否开启了 ADB 调试",
            "data": None,
            "task": task_description,
        }
    
    logger.info(f"[ExecuteTask] 开始执行: {task_description}")
    
    # 构建完整的 Agent 目标
    # 包含上下文信息，让 Agent 知道如何操作
    goal = f"""你是一个手机自动化助手，正在操作美团外卖 App。

用户的需求是：{task_description}

请完成这个任务。操作时注意：
1. 如果遇到弹窗（红包、广告、更新提示），先关闭它
2. 如果需要打开美团，它的包名是 {MEITUAN_PACKAGE}
3. 拼好饭入口通常在首页
4. 完成任务后，请用 JSON 格式返回结果，让我能提取关键信息

如果任务涉及搜索，返回格式：
{{
    "success": true,
    "meals": [
        {{"name": "套餐名", "price": "¥xx", "delivery_time": "xx分钟"}}
    ]
}}

如果任务涉及订单操作，返回格式：
{{
    "success": true,
    "action": "下单/取消/查看",
    "message": "操作结果描述"
}}

如果无法完成任务，返回：
{{
    "success": false,
    "error": "失败原因"
}}
"""
    
    try:
        # 初始化工具
        tools = AdbTools()
        await tools.connect()
        
        # 创建配置和 LLM
        config = _create_droidrun_config(max_steps=max_steps, reasoning=False)
        llm = _create_llm()
        
        # 创建并运行 Agent
        agent = DroidAgent(
            goal=goal,
            config=config,
            llms=llm,
            tools=tools,
            timeout=timeout,
        )
        
        logger.info(f"[ExecuteTask] Agent 开始运行...")
        handler = agent.run()
        result = await handler
        
        logger.info(f"[ExecuteTask] Agent 执行完成")
        
        # 格式化为语音友好的输出
        return _format_response_for_voice(result, task_description)
        
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "操作超时，请稍后重试",
            "data": None,
            "task": task_description,
        }
    except Exception as e:
        logger.error(f"[ExecuteTask] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"执行出错：{str(e)[:100]}",
            "data": None,
            "task": task_description,
        }


# ============================================================
# 测试代码
# ============================================================

async def _test():
    """测试 execute_task"""
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    test_cases = [
        "打开美团拼好饭，搜索炒面，告诉我前3个结果",
        # "看看有什么10元以下的套餐",
        # "查看我的历史订单",
    ]
    
    for task in test_cases:
        print(f"\n{'='*60}")
        print(f"任务: {task}")
        print('='*60)
        
        start = time.time()
        result = await execute_task(task)
        elapsed = time.time() - start
        
        print(f"\n结果:")
        print(f"  成功: {result['success']}")
        print(f"  消息: {result['message']}")
        print(f"  数据: {json.dumps(result['data'], ensure_ascii=False, indent=2) if result['data'] else 'None'}")
        print(f"  耗时: {elapsed:.1f}秒")


if __name__ == "__main__":
    asyncio.run(_test())
