# Food Delivery Robot - Docker 部署指南

## Ubuntu 20.04 环境准备

### 1. 安装 Docker
```bash
# 更新包索引
sudo apt-get update

# 安装依赖
sudo apt-get install -y ca-certificates curl gnupg

# 添加 Docker GPG 密钥
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 添加 Docker 源
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 将当前用户添加到 docker 组（免 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

### 2. 克隆项目
```bash
git clone <your-repo-url> food-delivery-robot
cd food-delivery-robot
```

### 3. 配置环境变量
```bash
cp .env.example .env
nano .env  # 编辑填入 OPENAI_API_KEY 等配置
```

## 启动服务

### 生产模式
```bash
docker compose up -d --build
```

### 查看日志
```bash
docker compose logs -f
```

### 停止服务
```bash
docker compose down
```

## 服务端口
- **MCP 服务**: http://localhost:8765 (SSE: /sse)
- **语音客户端**: http://localhost:3001

## 故障排查

### 查看容器状态
```bash
docker compose ps
```

### 查看 MCP 服务日志
```bash
docker compose logs food-delivery-mcp
```

### 进入容器调试
```bash
docker compose exec food-delivery-mcp bash
```

### ADB 连接问题
确保手机和服务器在同一网络，且手机开启了无线调试：
```bash
# 在容器内测试 ADB 连接
docker compose exec food-delivery-mcp adb connect 192.168.124.9:5555
docker compose exec food-delivery-mcp adb devices
```
