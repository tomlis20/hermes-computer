# Threat model

## Assets

- Site cookies on computer volumes
- Supervisor HMAC secret
- Per-computer agentd bearer tokens
- docker.sock on the supervisor (root-equivalent)

## Trust

Hermes (LLM + tokens) is trusted. Computers are not: pages run arbitrary JS.

## Boundaries

- Hermes is not on `hermes-computers`.
- Supervisor has **no listener** on `hermes-computers`; it initiates RPC/event/VNC connections.
- `net.ipv4.ip_forward=0` on the supervisor so it is not a router onto Hermes' network.
- agentd requires a per-computer bearer token (process env only).
- Takeover: loopback publish + signed 10-minute URL. 403 if unsigned/expired.
- Source-address middleware drops peers in `COMPUTER_NETWORK` CIDR on every supervisor listener.

## Residual

- Shared kernel (container ≠ VM). Chromium may fall back to `--no-sandbox`.
- Page JS can often reach `127.0.0.1:9222` CDP in the same container. Prefer debugging pipe when the image spike allows. Documented, not "unpublished."
- Sibling `agentd` ports are reachable on `hermes-computers` (auth wall).
- Internet egress from computers is allowed; public Hermes URLs may be reachable. Private RFC1918 / Docker / tailscale_net Hermes ports must not be.

## Not in scope

CAPTCHA solving, account farming, cloud CDP vendors.
