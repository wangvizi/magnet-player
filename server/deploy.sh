#!/usr/bin/env bash
# 一键部署脚本（Ubuntu 20.04 / 22.04 VPS）
# 用法: sudo bash deploy.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 sudo 运行: sudo bash deploy.sh"
  exit 1
fi

APP_DIR=/opt/magnet-player
DATA_DIR=/var/lib/magnet-player
PORT=8000
RPC_SECRET=$(openssl rand -hex 16)
API_KEY=$(openssl rand -hex 16)

echo "==> 安装系统依赖 (python3 / ffmpeg / aria2)..."
apt-get update
apt-get install -y python3 python3-pip python3-venv ffmpeg aria2 openssl

echo "==> 部署代码到 $APP_DIR ..."
mkdir -p "$APP_DIR" "$DATA_DIR"
cp -r ./* "$APP_DIR/" 2>/dev/null || true
cp -r ./.[!.]* "$APP_DIR/" 2>/dev/null || true

echo "==> 安装 Python 依赖..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> 写入 systemd 服务..."
cat > /etc/systemd/system/magnet-player.service <<EOF
[Unit]
Description=Magnet Player Server
After=network.target

[Service]
WorkingDirectory=$APP_DIR
Environment=DATA_DIR=$DATA_DIR
Environment=RPC_SECRET=$RPC_SECRET
Environment=API_KEY=$API_KEY
Environment=ARIA2_PORT=6800
ExecStart=$APP_DIR/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now magnet-player.service

echo ""
echo "=============================================="
echo " 部署完成！"
echo " 服务地址: http://<你的服务器IP>:$PORT"
echo "=============================================="
echo " API Key  : $API_KEY"
echo "   （在 iPhone App 的「设置」里填入此 API Key）"
echo ""
echo "注意：请在云控制台安全组放行 TCP $PORT 端口。"
echo "若使用 HTTPS，建议在前方加 Nginx 反向代理并配置 SSL 证书。"
