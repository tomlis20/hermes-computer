#!/bin/bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:1}"
mkdir -p /home/agent/chrome /home/agent/events /tmp/.X11-unix || true
# stale Chromium locks from a previous container
rm -f /home/agent/chrome/SingletonLock /home/agent/chrome/SingletonCookie /home/agent/chrome/SingletonSocket

Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
sleep 0.4
openbox >/tmp/openbox.log 2>&1 &
x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -nopw -listen 127.0.0.1 >/tmp/x11vnc.log 2>&1 &
websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &

start_chrome() {
  local extra=("$@")
  chromium \
    --user-data-dir=/home/agent/chrome \
    --remote-debugging-port=9222 \
    --remote-debugging-address=127.0.0.1 \
    --no-first-run \
    --disable-gpu \
    --disable-dev-shm-usage \
    --disable-crash-reporter \
    "${extra[@]}" \
    about:blank >/tmp/chromium.log 2>&1 &
  echo $!
}

CHROME_PID=$(start_chrome)
sleep 1
if ! kill -0 "$CHROME_PID" 2>/dev/null || grep -q "No usable sandbox" /tmp/chromium.log; then
  echo "chromium sandbox failed; retrying with --no-sandbox" >&2
  kill "$CHROME_PID" 2>/dev/null || true
  wait "$CHROME_PID" 2>/dev/null || true
  export AGENTD_SANDBOX=no-sandbox
  CHROME_PID=$(start_chrome --no-sandbox)
  sleep 1
else
  export AGENTD_SANDBOX="${AGENTD_SANDBOX:-seccomp}"
fi

if ! kill -0 "$CHROME_PID" 2>/dev/null; then
  echo "chromium failed to start" >&2
  cat /tmp/chromium.log >&2 || true
  exit 1
fi

exec python3 -u /opt/agentd/main.py
