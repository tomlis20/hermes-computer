# Security

**Supervisor + `docker.sock` is root on the host.** Recipients must trust the `--ref` SHA and image digests they pin. Never mount the socket into the Hermes / WebUI container.

## Auth

- Hermes → supervisor: HMAC, 60s skew. Token only in environment, never `config.yaml` or git.
- Supervisor → agentd: per-computer bearer, process env only, never under Chromium's user-data-dir.
- Human VNC: 10-minute signed URL. Unsigned/expired → 403.

## Takeover exposure

The signed `novnc_url` is a stateless HMAC bearer token over `novnc\n{name}\n{exp}`.
Nothing revokes it: resume, stop, and destroy do not invalidate it, so it grants
desktop control for its full ~10-min TTL even after the human finishes. Treat the
link like a short-lived password.

With `COMPUTER_PUBLIC_BASE` on the tailnet (NerdCow), port 9376 is a tailnet-wide
VNC ingress reachable by every tailnet node — a deliberate new path that widens the
"Computers are only on `hermes-computers`" isolation below. Every other supervisor
route stays HMAC-authenticated regardless of where 9376 is published.

Slot discipline (ensure/rpc, HMAC-gated) only governs which desktop a bot opens, not
who reaches a leaked link: anyone who sees the URL controls that desktop until it
expires. The real mitigations are the HMAC signature, the ~10-min TTL, and
tailnet-only ingress — but a leaked link inside that window is a live credential.

## Network

- Computers are only on `hermes-computers`. Hermes is not.
- Supervisor has **no listener** on `hermes-computers`; it dials agentd/VNC.
- `net.ipv4.ip_forward=0` on the supervisor so dual-home cannot route a pwned page onto Hermes.
- Residual: sibling `agentd` ports (token wall); internet egress; same-container `127.0.0.1:9222` CDP may be reachable from page JS (prefer debugging pipe later).

## ToS

Operator's own admin UIs. No CAPTCHA-as-a-service, no account farming, no LinkedIn blast.

## Topology test

From inside a computer, RFC1918 / Docker-bridge / `tailscale_net` Hermes ports are unreachable. A public Hermes URL being reachable is expected.
