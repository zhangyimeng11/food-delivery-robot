#!/system/bin/sh
# ADB WiFi Auto Start - Magisk Module
# 开机自动启用 ADB WiFi 在端口 5555

MODDIR=${0%/*}

# 等待系统完全启动
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 1
done

# 额外等待 10 秒确保网络就绪
sleep 10

# 设置 ADB TCP 端口为 5555
setprop service.adb.tcp.port 5555

# 重启 ADB 服务使设置生效
stop adbd
start adbd

# 记录日志
echo "$(date): ADB WiFi started on port 5555" >> /data/local/tmp/adb_wifi.log
