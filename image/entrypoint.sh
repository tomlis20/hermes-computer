#!/bin/bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:1}"
mkdir -p /home/agent/chrome /home/agent/events
# X + WM
Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
sleep 0.3
openbox >/tmp/openbox.log 2>&1 &
# VNC
x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -nopw -listen 127.0.0.1 >/tmp/x11vnc.log 2>&1 &
websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
# Chromium — CDP on localhost only. Page JS may still reach 127.0.0.1:9222 (residual).
CHROME_FLAGS=(
  --user-data-dir=/home/agent/chrome
  --remote-debugging-port=9222
  --remote-debugging-address=127.0.0.1
  --no-first-run
  --disable-gpu
  --disable-dev-shm-usage
)
if [ "${CHROME_NO_SANDBOX:-}" = "1" ]; then
  CHROME_FLAGS+=(--no-sandbox)
  export AGENTD_SANDBOX=no-sandbox
else
  export AGENTD_SANDBOX="${AGENTD_SANDBOX:-seccomp}"
fi
chromium "${CHROME_FLAGS[@]}" about:blank >/tmp/chromium.log 2>&1 &
# agentd last — healthcheck target
exec python3 -u /opt/agentd/main.py
