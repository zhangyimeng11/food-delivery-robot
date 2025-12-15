# Simple Voice Client

简单的语音助手客户端，用于调用部署的 Agent。

## 配置

修改 `src/App.tsx` 中的配置：

```typescript
const CONFIG = {
  // 部署标识（slug）
  DEPLOYMENT_SLUG: '外卖助手-1765760043207',
  // 后端 API 地址
  API_BASE_URL: '/api/v1',
}
```

## 启动

```bash
# 安装依赖
npm install

# 启动开发服务器（端口 3001）
npm run dev
```

然后访问 http://localhost:3001

## 前提条件

确保以下服务正在运行：
- Backend: http://localhost:8000
- LiveKit: ws://localhost:7880
- Worker: 已启动

## 功能

- 🎤 一键开始语音对话
- 📊 实时显示助手状态（听、思考、说）
- 🔊 音频波形可视化
- 🔄 支持重新开始会话

