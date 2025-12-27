#!/usr/bin/env python3
"""
机器人 TTS HTTP 服务

运行在 Unitree G1 机器人上，接收文字并通过 TtsMaker API 播放。

启动方式：
    python3 tts_server.py

API:
    POST /speak - 播放文字
        Body: {"text": "要播放的文字"}
    
    POST /stop - 停止播放
    
    GET /health - 健康检查
"""

import subprocess
import threading
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# 配置
HOST = "0.0.0.0"
PORT = 8080
NETWORK_INTERFACE = "eth0"  # 机器人网络接口

# TTS 可执行文件路径（需要先编译）
TTS_EXECUTABLE = os.path.expanduser("~/robot_tts_service/tts_speak")

# 当前播放进程
current_process = None
process_lock = threading.Lock()


def speak_text(text: str, lang: int = 0) -> dict:
    """
    调用 TTS 播放文字
    
    Args:
        text: 要播放的文字
        lang: 语言 (0=自动, 1=英文)
    
    Returns:
        结果字典
    """
    global current_process
    
    with process_lock:
        # 如果有正在播放的，先停止
        if current_process and current_process.poll() is None:
            current_process.terminate()
            try:
                current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                current_process.kill()
        
        try:
            # 调用 TTS 程序
            current_process = subprocess.Popen(
                [TTS_EXECUTABLE, text, NETWORK_INTERFACE, str(lang)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待完成（最多 30 秒）
            stdout, stderr = current_process.communicate(timeout=30)
            
            if current_process.returncode == 0:
                return {"success": True, "message": "播放完成"}
            else:
                return {
                    "success": False, 
                    "message": f"播放失败: {stderr.decode('utf-8', errors='ignore')}"
                }
                
        except subprocess.TimeoutExpired:
            current_process.kill()
            return {"success": False, "message": "播放超时"}
        except FileNotFoundError:
            return {"success": False, "message": f"TTS 程序不存在: {TTS_EXECUTABLE}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


def stop_speaking() -> dict:
    """停止当前播放"""
    global current_process
    
    with process_lock:
        if current_process and current_process.poll() is None:
            current_process.terminate()
            try:
                current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                current_process.kill()
            return {"success": True, "message": "已停止播放"}
        return {"success": True, "message": "没有正在播放的内容"}


class TTSHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""
    
    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _send_json(self, data: dict, status=200):
        self._set_headers(status)
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self._set_headers(200)
    
    def do_GET(self):
        """处理 GET 请求"""
        if self.path == "/health":
            self._send_json({"status": "healthy", "service": "robot-tts"})
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        """处理 POST 请求"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return
        
        if self.path == "/speak":
            text = data.get("text", "")
            if not text:
                self._send_json({"error": "Missing 'text' field"}, 400)
                return
            
            lang = data.get("lang", 0)
            
            # 在后台线程中执行，避免阻塞
            def speak_async():
                result = speak_text(text, lang)
                print(f"[TTS] {text[:50]}... -> {result}")
            
            thread = threading.Thread(target=speak_async)
            thread.start()
            
            self._send_json({"success": True, "message": "开始播放"})
        
        elif self.path == "/stop":
            result = stop_speaking()
            self._send_json(result)
        
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[HTTP] {self.address_string()} - {format % args}")


def main():
    """主函数"""
    print(f"=" * 50)
    print(f"Robot TTS Service")
    print(f"=" * 50)
    print(f"Listening on http://{HOST}:{PORT}")
    print(f"Network interface: {NETWORK_INTERFACE}")
    print(f"TTS executable: {TTS_EXECUTABLE}")
    print(f"")
    print(f"API Endpoints:")
    print(f"  POST /speak  - Play text")
    print(f"  POST /stop   - Stop playing")
    print(f"  GET  /health - Health check")
    print(f"=" * 50)
    
    server = HTTPServer((HOST, PORT), TTSHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
