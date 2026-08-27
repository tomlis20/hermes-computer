# Security

**Supervisor + `docker.sock` is root on the host.** Recipients must trust the `--ref` SHA and image digests they pin. Never mount the socket into the Hermes / WebUI container.

## Auth

- Hermes → supervisor: HMAC, 60s skew. Token only in environment, never `config.yaml` or git.
- Supervisor → agentd: per-computer bearer, process env only, never under Chromium's user-data-dir.
- Human VNC: 10-minute signed URL. Unsigned/expired → 403.

## Takeover exposure

A valid signed `novnc_url` grants desktop control to anyone who can reach the
9376 listener until the token expires (~10 min). Every other supervisor route
stays HMAC-authenticated regardless of where 9376 is published. If
`COMPUTER_PUBLIC_BASE` points beyond loopback (NerdCow: tailnet-only), a chat
transcript containing the link is effectively a takeover credential while it
lives — per-person slot names remain the wall for logged-in sessions.

## Network

- Computers are only on `hermes-computers`. Hermes is not.
- Supervisor has **no listener** on `hermes-computers`; it dials agentd/VNC.
- `net.ipv4.ip_forward=0` on the supervisor so dual-home cannot route a pwned page onto Hermes.
- Residual: sibling `agentd` ports (token wall); internet egress; same-container `127.0.0.1:9222` CDP may be reachable from page JS (prefer debugging pipe later).

## ToS

Operator's own admin UIs. No CAPTCHA-as-a-service, no account farming, no LinkedIn blast.

## Topology test

From inside a computer, RFC1918 / Docker-bridge / `tailscale_net` Hermes ports are unreachable. A public Hermes URL being reachable is expected.
