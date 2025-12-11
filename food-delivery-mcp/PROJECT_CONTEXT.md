# 美团拼好饭 MCP 服务 - 项目上下文

> 最后更新: 2024-12-04

## 项目概述

基于 uiautomator2 的美团外卖 App 自动化服务，通过 FastAPI 暴露 MCP 接口，支持语音助手调用实现点餐功能。

**技术栈**: Python 3.12 + FastAPI + uiautomator2 + Qwen LLM

**服务端口**: 8765

## 当前实现状态

### ✅ 已完成

| 功能 | 状态 | 说明 |
|------|------|------|
| 启动 App | ✅ | 自动处理开屏弹窗 |
| 进入拼好饭 | ✅ | 自动处理首页弹窗（含 NAF 关闭按钮） |
| 搜索套餐 | ✅ | LLM 解析搜索结果（qwen-flash） |
| 下单到支付页 | ✅ | 停在支付页，不点击极速支付 |
| 弹窗处理 | ✅ | 文字按钮 + NAF 图标 + VL 兜底 |

### 🚧 待开发 Todo List

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | **确认支付** | 点击"极速支付"完成下单 |
| P0 | **订单状态查询** | `check_order_status` 已有框架，需测试完善 |
| P1 | **通知监听** | 骑手状态变更通知，已有 `dumpsys notification` 方案 |
| P1 | **异常恢复** | 网络超时、App 崩溃等情况的自动恢复 |
| P2 | **多地址支持** | 切换收货地址 |
| P2 | **历史订单** | 查看/再来一单 |

## 核心流程

```
启动App → 等"拼好饭"出现 → 点击进入 → 等"拼好饭"消失
    ↓
搜索页 → 输入关键词 → 点击搜索 → 等"历史搜索"出现
    ↓
搜索结果 → LLM提取套餐信息 → 返回列表
    ↓
点击套餐 → 详情页点"马上抢" → 规格页点"马上抢" → 等"极速支付"出现
    ↓
支付页（停在这里，等待 confirm_payment 调用）
```

## 关键技术点

### 页面判断

```python
# 首页 = 拼好饭入口存在
d(text="拼好饭").wait(timeout=3)

# 离开首页 = 拼好饭入口消失
d(text="拼好饭").wait_gone(timeout=3)

# 搜索页 = 历史搜索存在
d(text="历史搜索").wait(timeout=3)

# 支付页 = 极速支付存在
d(text="极速支付").wait(timeout=5)
```

### 弹窗处理

1. **文字按钮**: "我知道了"、"关闭"、"暂不"、"取消"
2. **NAF 关闭按钮**: 无文字的 X 图标，通过 XML 解析找 `clickable=true` 且无 text 的小尺寸 FrameLayout
3. **VL 兜底**: qwen-vl-plus 识别弹窗并返回关闭按钮坐标

弹窗只在两处检测：**启动后进首页** 和 **点击拼好饭后**

### LLM 配置

```yaml
# config.yaml
llm:
  api_key: "sk-xxx"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model: "qwen-flash"  # 搜索结果解析，快且便宜
```

**注意**: LLM 调用必须 `trust_env=False`，避免走代理导致超时

## 文件结构

```
food-delivery-mcp/
├── config.yaml          # LLM 配置
├── src/
│   ├── main.py          # FastAPI 入口，端口 8765
│   ├── automation/
│   │   └── meituan.py   # 核心自动化逻辑
│   └── notification/
│       └── monitor.py   # 通知监听（待完善）
└── scripts/
    ├── snapshot.py      # 调试用截图+XML
    └── test_extract.py  # 测试搜索结果提取
```

## API 接口

```bash
# 健康检查
GET /health

# 列出工具
POST /tools/list

# 调用工具
POST /tools/call
{
  "name": "search_meals",
  "arguments": {"keyword": "麻辣香锅", "max_results": 5}
}

POST /tools/call
{
  "name": "place_order",
  "arguments": {"meal_name": "合椒魂鱼豆腐"}
}
```

## 调试技巧

```bash
# 快速截图+XML
python scripts/snapshot.py <name>

# 检查当前页面文字
python -c "
import uiautomator2 as u2
import re
d = u2.connect()
xml = d.dump_hierarchy()
texts = re.findall(r'text=\"([^\"]+)\"', xml)
print([t for t in texts if t.strip()][:30])
"
```

## 已知问题


## 下次接手注意

1. 启动服务: `cd food-delivery-mcp && source .venv/bin/activate && python -m src.main`
2. 手机需连接 adb，运行 `adb devices` 确认
3. 测试前确保美团 App 已安装且登录
4. 修改代码后需重启服务

