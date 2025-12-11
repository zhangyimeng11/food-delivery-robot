# 美团拼好饭 MCP 服务

通过自动化操作手机上的美团外卖 App，实现语音点餐功能的 MCP 服务。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 连接手机

- 开启手机的 USB 调试
- 用 USB 连接手机到电脑
- 确认连接：`adb devices`

### 3. 修改配置

编辑 `config.yaml` 配置文件。

### 4. 启动服务

```bash
python -m src.main
```

服务将在 `http://localhost:8765` 启动。

## API 接口

### 健康检查

```bash
curl http://localhost:8765/health
```

### 搜索套餐

```bash
curl -X POST http://localhost:8765/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "search_meals", "arguments": {"keyword": "奶茶"}}'
```

### 下单

```bash
curl -X POST http://localhost:8765/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "place_order", "arguments": {"meal_index": 0}}'
```

### 查询订单

```bash
curl -X POST http://localhost:8765/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "check_order_status", "arguments": {}}'
```

## 工具列表

| 工具名 | 描述 |
|--------|------|
| search_meals | 搜索拼好饭套餐 |
| place_order | 下单指定套餐 |
| check_order_status | 查询最新订单状态 |

## 注意事项

- 手机需保持屏幕解锁
- 美团外卖 App 需已登录
- 下单操作不会自动支付，会停在确认页面

