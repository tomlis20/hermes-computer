# Image spike (Task 6a)

Time-box: half a day before treating DIY as permanent.

| Option | Status |
|---|---|
| kasmweb/chromium or linuxserver/chromium + agentd | Preferred if ARM works and no `--privileged` |
| debian-slim + xvfb + openbox + chromium + x11vnc + novnc | Shipped as `image/Dockerfile` so we can build without deciding the spike yet |

Run contract is the same either way. Residual: CDP on 127.0.0.1:9222 visible to page JS; prefer `--remote-debugging-pipe` if the chosen base allows it.
