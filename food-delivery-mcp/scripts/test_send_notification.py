#!/usr/bin/env python3
"""测试脚本：发送模拟通知到 Android 设备

使用 Termux:API 或 ADB 广播发送模拟通知
"""

import subprocess
import sys
import time


def run_adb(cmd: str) -> str:
    """执行 ADB 命令"""
    result = subprocess.run(
        f"adb shell {cmd}",
        shell=True,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def method_1_toast():
    """方法1：发送 Toast 消息（不是通知，但可以测试 ADB 连接）"""
    print("方法1: 发送 Toast 消息...")
    
    # 使用 am broadcast 发送 toast（需要特定 App 支持）
    cmd = 'am broadcast -a android.intent.action.MAIN -e message "外卖已送达，请取餐"'
    result = run_adb(cmd)
    print(f"结果: {result}")


def method_2_termux_notification():
    """方法2：通过 Termux:API 发送通知（需要安装 Termux 和 Termux:API）"""
    print("\n方法2: 通过 Termux:API 发送通知...")
    print("需要先在手机上安装 Termux 和 Termux:API")
    
    # Termux 命令
    cmd = '''
    termux-notification \
        --title "美团外卖" \
        --content "外卖已送达，请及时取餐" \
        --id "meituan_test"
    '''
    result = run_adb(cmd.strip().replace('\n', ' '))
    print(f"结果: {result}")


def method_3_activity_notification():
    """方法3：启动一个会产生通知的 Activity"""
    print("\n方法3: 模拟美团 App 通知...")
    
    # 尝试发送一个系统广播来模拟通知场景
    # 这个方法不太可行，因为需要特权
    
    # 替代方案：可以创建一个简单的 Android App 专门用于发送测试通知
    print("此方法需要自定义 App，暂时跳过")


def method_4_write_notification_file():
    """方法4：在设备上写入一个文件，让监控脚本读取"""
    print("\n方法4: 写入测试文件到设备...")
    
    # 在 /sdcard/ 下创建一个测试文件
    test_content = f"外卖已送达|{int(time.time())}"
    cmd = f'echo "{test_content}" > /sdcard/meituan_notification_test.txt'
    result = run_adb(cmd)
    print(f"已写入测试文件: {result or '成功'}")
    
    # 验证
    verify = run_adb("cat /sdcard/meituan_notification_test.txt")
    print(f"文件内容: {verify}")


def main():
    print("=" * 50)
    print("Android 模拟通知测试")
    print("=" * 50)
    
    # 检查设备连接
    devices = subprocess.run(
        "adb devices",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    
    print(f"连接的设备:\n{devices}")
    
    if "device" not in devices or devices.count("\n") < 3:
        print("错误: 未检测到 Android 设备，请检查 USB 连接")
        sys.exit(1)
    
    # 测试各种方法
    method_1_toast()
    method_4_write_notification_file()
    
    print("\n" + "=" * 50)
    print("提示: 真实的模拟通知需要以下方式之一:")
    print("1. 安装 Termux + Termux:API")
    print("2. 安装自定义的测试 App")
    print("3. 使用 dumpsys notification 读取现有通知")
    print("=" * 50)


if __name__ == "__main__":
    main()

