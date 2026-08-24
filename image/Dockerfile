# DIY computer image (spike default until kasm/linuxserver is timed).
# Contract: shm 1g, uid 1000, chrome user-data, CDP 9222 localhost,
# VNC 6080, agentd 9377, health curl 127.0.0.1:9377/health.
FROM debian:bookworm-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    xvfb openbox \
    x11vnc novnc websockify \
    python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 agent
COPY agentd/ /opt/agentd/
COPY image/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R agent:agent /opt/agentd
USER agent
ENV HOME=/home/agent
ENV DISPLAY=:1
EXPOSE 6080 9377
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
  CMD curl -sf http://127.0.0.1:9377/health || exit 1
ENTRYPOINT ["/entrypoint.sh"]
