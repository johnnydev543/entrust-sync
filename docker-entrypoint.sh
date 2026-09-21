#!/usr/bin/env bash
set -euo pipefail

: "${ENTRUST_VNC_PASSWORD:?ENTRUST_VNC_PASSWORD 未設定}"

cleanup() {
    nginx -s quit 2>/dev/null || true
    kill "${NOVNC_PID:-}" "${VNC_PID:-}" "${FLUXBOX_PID:-}" "${XVFB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

rm -f /tmp/.X99-lock
rm -rf /tmp/.X11-unix/X99

Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

for _ in $(seq 1 50); do
    if [ -S /tmp/.X11-unix/X99 ]; then
        break
    fi
    sleep 0.1
done

fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

x11vnc \
    -display :99 \
    -forever \
    -shared \
    -rfbport 5900 \
    -localhost \
    -passwd "$ENTRUST_VNC_PASSWORD" \
    >/tmp/x11vnc.log 2>&1 &
VNC_PID=$!

websockify \
    6081 \
    127.0.0.1:5900 \
    >/tmp/novnc.log 2>&1 &
NOVNC_PID=$!

nginx

exec python /app/api_server.py
