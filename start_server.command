#!/bin/bash
# 伊莱克斯空调测试查询 - 本地服务器 (双击运行)
export PATH="/usr/sbin:/usr/local/bin:/usr/bin:/bin:$PATH"

IP=$(/usr/sbin/ipconfig getifaddr en0 2>/dev/null)
if [ -z "$IP" ]; then
  IP=$(/usr/sbin/ipconfig getifaddr en1 2>/dev/null)
fi
if [ -z "$IP" ]; then
  IP="本机"
fi

PORT=8080

clear
echo "================================================"
echo "  伊莱克斯空调测试查询 PWA 服务器"
echo "================================================"
echo ""
echo "  在 iPhone 上操作："
echo ""
echo "  1. 确保 iPhone 连接了同一个 Wi-Fi"
echo "  2. 打开 Safari 浏览器"
echo "  3. 访问: http://${IP}:${PORT}"
echo ""
echo "  4. 点底部分享按钮 → 添加到主屏幕"
echo "  5. 完成！桌面图标即 APP"
echo ""
echo "  按 Ctrl+C 停止服务器"
echo "================================================"
echo ""

cd "$(dirname "$0")"
/usr/bin/python3 -m http.server $PORT
