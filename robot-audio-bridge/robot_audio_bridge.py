#!/usr/bin/env python3
"""
Robot Audio Bridge - 机器人音频桥接服务

接收来自电脑的 PCM 音频流，通过 Unitree SDK 播放到机器人扬声器。
保持与 Agent TTS 设置一致的音色。

启动方式：
    python3 robot_audio_bridge.py

WebSocket API:
    ws://192.168.0.13:8765
    - 发送二进制 PCM 数据（16kHz, 单声道, 16bit）
    - 发送 JSON 控制命令: {"type": "stop"} 或 {"type": "finish"}
"""

import asyncio
import json
import ctypes
import signal
import sys
from ctypes import c_void_p, c_char_p, c_uint8, c_size_t, c_int, POINTER
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: pip3 install websockets")
    sys.exit(1)

# 配置
HOST = "0.0.0.0"
PORT = 8765
NETWORK_INTERFACE = "eth0"  # Unitree SDK 使用的网络接口

# 音频播放器库路径
LIB_PATH = Path("/home/unitree/robot_tts_service/build/libaudio_player_api.so")


class AudioPlayer:
    """音频播放器封装"""
    
    def __init__(self, network_interface: str = "eth0"):
        self.lib = None
        self.player = None
        self.network_interface = network_interface
        self.stream_counter = 0
        self.current_stream_id = None
        
    def initialize(self) -> bool:
        """初始化播放器"""
        if not LIB_PATH.exists():
            print(f"[ERROR] Library not found: {LIB_PATH}")
            return False
        
        try:
            self.lib = ctypes.CDLL(str(LIB_PATH))
            
            # 定义函数签名
            self.lib.audio_player_create.argtypes = [c_char_p]
            self.lib.audio_player_create.restype = c_void_p
            
            self.lib.audio_player_start_stream.argtypes = [c_void_p, c_char_p]
            self.lib.audio_player_start_stream.restype = c_int
            
            self.lib.audio_player_play_chunk.argtypes = [c_void_p, c_char_p, POINTER(c_uint8), c_size_t]
            self.lib.audio_player_play_chunk.restype = c_int
            
            self.lib.audio_player_finish.argtypes = [c_void_p]
            self.lib.audio_player_finish.restype = c_int
            
            self.lib.audio_player_stop.argtypes = [c_void_p]
            self.lib.audio_player_stop.restype = c_int
            
            self.lib.audio_player_destroy.argtypes = [c_void_p]
            self.lib.audio_player_destroy.restype = None
            
            self.lib.audio_player_set_chunk_size.argtypes = [c_void_p, c_size_t]
            self.lib.audio_player_set_chunk_size.restype = None
            
            # 创建播放器实例
            self.player = self.lib.audio_player_create(self.network_interface.encode('utf-8'))
            if not self.player:
                print("[ERROR] Failed to create audio player")
                return False
            
            # 设置较小的分块大小以降低延迟（约 0.25 秒）
            self.lib.audio_player_set_chunk_size(self.player, 8000)
            
            print(f"[AudioPlayer] Initialized, interface: {self.network_interface}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to load library: {e}")
            return False
    
    def start_stream(self) -> str:
        """开始新的音频流"""
        self.stream_counter += 1
        self.current_stream_id = f"agent_audio_{self.stream_counter}"
        
        if self.lib and self.player:
            self.lib.audio_player_start_stream(
                self.player, 
                self.current_stream_id.encode('utf-8')
            )
        
        print(f"[AudioPlayer] Started stream: {self.current_stream_id}")
        return self.current_stream_id
    
    def play_chunk(self, pcm_data: bytes) -> int:
        """播放 PCM 数据块"""
        if not self.lib or not self.player or not self.current_stream_id:
            return -1
        
        # 转换为 ctypes 数组
        data_array = (c_uint8 * len(pcm_data)).from_buffer_copy(pcm_data)
        
        return self.lib.audio_player_play_chunk(
            self.player,
            self.current_stream_id.encode('utf-8'),
            data_array,
            len(pcm_data)
        )
    
    def finish(self) -> int:
        """完成当前流"""
        if self.lib and self.player:
            ret = self.lib.audio_player_finish(self.player)
            print(f"[AudioPlayer] Finished stream: {self.current_stream_id}")
            return ret
        return -1
    
    def stop(self) -> int:
        """停止播放"""
        if self.lib and self.player:
            ret = self.lib.audio_player_stop(self.player)
            print("[AudioPlayer] Stopped")
            return ret
        return -1
    
    def cleanup(self):
        """清理资源"""
        if self.lib and self.player:
            self.lib.audio_player_destroy(self.player)
            self.player = None
            print("[AudioPlayer] Cleaned up")


# 全局播放器实例
player = AudioPlayer(NETWORK_INTERFACE)


async def handle_client(websocket, path):
    """处理 WebSocket 连接"""
    client_addr = websocket.remote_address
    print(f"[WebSocket] Client connected: {client_addr}")
    
    # 开始新的音频流
    stream_id = player.start_stream()
    bytes_received = 0
    
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # 接收 PCM 数据
                ret = player.play_chunk(message)
                bytes_received += len(message)
                
                # 每 100KB 打印一次进度
                if bytes_received % 102400 < len(message):
                    print(f"[WebSocket] Received {bytes_received / 1024:.1f} KB")
                    
            elif isinstance(message, str):
                # 处理控制命令
                try:
                    cmd = json.loads(message)
                    cmd_type = cmd.get('type')
                    
                    if cmd_type == 'stop':
                        player.stop()
                        await websocket.send(json.dumps({"status": "stopped"}))
                        
                    elif cmd_type == 'finish':
                        player.finish()
                        await websocket.send(json.dumps({"status": "finished"}))
                        
                    elif cmd_type == 'new_stream':
                        # 开始新流（用于打断）
                        player.stop()
                        stream_id = player.start_stream()
                        await websocket.send(json.dumps({"status": "new_stream", "stream_id": stream_id}))
                        
                    elif cmd_type == 'ping':
                        await websocket.send(json.dumps({"status": "pong"}))
                        
                except json.JSONDecodeError:
                    pass
                    
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[WebSocket] Client disconnected: {e}")
    finally:
        # 完成当前流
        player.finish()
        print(f"[WebSocket] Session ended, total received: {bytes_received / 1024:.1f} KB")


async def main():
    """主函数"""
    print("=" * 50)
    print("  Robot Audio Bridge")
    print("  接收 Agent 音频并播放到机器人扬声器")
    print("=" * 50)
    
    # 初始化播放器
    if not player.initialize():
        print("[ERROR] Failed to initialize audio player")
        return
    
    print(f"[Server] Starting WebSocket server on ws://{HOST}:{PORT}")
    
    # 启动 WebSocket 服务器
    async with websockets.serve(handle_client, HOST, PORT):
        print(f"[Server] Ready! Connect to ws://192.168.0.13:{PORT}")
        print("=" * 50)
        
        # 等待直到收到终止信号
        stop = asyncio.Event()
        
        def signal_handler():
            print("\n[Server] Shutting down...")
            stop.set()
        
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
        
        await stop.wait()
    
    # 清理
    player.cleanup()
    print("[Server] Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] Interrupted")
        player.cleanup()
