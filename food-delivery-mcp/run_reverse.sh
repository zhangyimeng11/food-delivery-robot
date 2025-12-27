#!/bin/bash
# MCP 反向连接客户端启动脚本
#
# 使用方法：
#   ./run_reverse.sh                    # 使用默认服务器
#   ./run_reverse.sh ws://your-server   # 指定服务器地址

cd "$(dirname "$0")"

# 设置 Relay URL（默认连接到平台服务器）
export MCP_RELAY_URL="${1:-ws://100.86.205.14:8000/api/v1/mcp/ws/food-delivery-mcp}"

echo "========================================"
echo "🍜 美团外卖 MCP 反向连接客户端"
echo "========================================"
echo "📡 服务器: $MCP_RELAY_URL"
echo ""
echo "按 Ctrl+C 停止"
echo ""

# 运行反向连接客户端
python -m src.reverse_client
