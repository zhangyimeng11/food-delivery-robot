# Robot TTS Service

在 Unitree G1 机器人上运行的 TTS HTTP 服务，用于接收前端的文字并通过机器人扬声器播放。

## 文件说明

- `tts_speak.cpp` - C++ 命令行 TTS 程序，调用 Unitree SDK
- `CMakeLists.txt` - CMake 构建配置
- `tts_server.py` - Python HTTP 服务，调用 tts_speak 程序

## 部署步骤

### 1. 复制代码到机器人

```bash
scp -r robot_tts_service unitree@192.168.0.13:~/
```

### 2. 在机器人上编译

```bash
ssh unitree@192.168.0.13
cd ~/robot_tts_service
mkdir -p build && cd build
cmake ..
make
cd ..
ln -sf build/tts_speak tts_speak
```

### 3. 启动服务

```bash
python3 tts_server.py
```

## API

### POST /speak

播放文字。

```bash
curl -X POST http://192.168.0.13:8080/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，外卖到了"}'
```

### POST /stop

停止播放。

```bash
curl -X POST http://192.168.0.13:8080/stop
```

### GET /health

健康检查。

```bash
curl http://192.168.0.13:8080/health
```
