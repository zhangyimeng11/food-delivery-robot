# 美团拼好饭 MCP 服务

基于 [DroidRun](https://github.com/droidrun/droidrun) Agent 的美团外卖自动化点餐服务。

## 功能

- **search_meals**: 搜索拼好饭套餐
- **place_order**: 下单（到支付页面，不自动支付）
- **confirm_payment**: 确认支付

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

设置 OpenAI API Key：

```bash
export OPENAI_API_KEY="your-api-key"
```

或在 `config.yaml` 中配置：

```yaml
llm:
  api_key: "your-api-key"
```

### 3. 准备手机

1. 安装 [DroidRun Portal](https://github.com/droidrun/droidrun-portal) APK
2. 开启无障碍服务
3. 通过 USB 或 WiFi 连接 ADB

### 4. 启动服务

```bash
python -m src.main
```

服务启动后，MCP 端点：`http://localhost:8765/sse`

## 工具说明

### search_meals

搜索美团拼好饭的餐品。

```json
{
  "keyword": "奶茶",
  "max_results": 3
}
```

### place_order

下单指定餐品（到支付页面）。

```json
{
  "meal_name": "珍珠奶茶"
}
```

### confirm_payment

确认支付（点击极速支付）。

```json
{}
```

## 技术栈

- [FastMCP](https://github.com/jlowin/fastmcp) - MCP 服务框架
- [DroidRun](https://github.com/droidrun/droidrun) - Android 自动化 Agent
- [GPT-4o](https://openai.com) - LLM 驱动 UI 交互
