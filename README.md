# Hermes Computer

Self-hosted **computer** for Hermes: a named Linux desktop container (Chromium + VNC + `agentd`) owned by a supervisor that is the only process with `docker.sock`. Hermes stays the brain. No Browser Use, Nous Tool Gateway, or Browserbase.

Container today, hypervisor later. Sharing a computer `name` shares its logins.

## Two artifacts

| | What | How |
|---|---|---|
| Plugin | tools + HMAC client | `hermes plugins install tomlis20/hermes-computer --ref <40-char-sha>` |
| Runtime | supervisor + computer images | `deploy/docker-compose.yml` (pull) |

Plugin install does **not** start a VM. Both are required.

The supervisor + socket is **root-equivalent** on the host. Pin a SHA you trust.

## Install (stranger / same-host Docker)

1. `hermes plugins install tomlis20/hermes-computer --ref <sha>`  
   First install is interactive (`plugin-guard` may say `caution`). `--force` skips confirmation, not the scan.
2. Set `COMPUTER_SUPERVISOR_TOKEN` (compose `.env`) and the same token + `COMPUTER_SUPERVISOR_URL=http://hermes-computer-supervisor:9376` on **both** Hermes gateway and WebUI containers.
3. `cd ~/.hermes/plugins/hermes-computer && docker compose -f deploy/docker-compose.yml up -d`
4. `hermes computer doctor` — **paste the FIX lines** it prints (merge-safe `platform_toolsets`). Do not copy a canned list.
5. `hermes plugins enable hermes-computer` if not enabled. **New chat.**
6. `computer_ensure` name `lab` → navigate `https://example.com` → observe `a11y` → Example Domain.

Takeover: SSH `-L 9376:127.0.0.1:9376` then open the signed `novnc_url` from `ensure`. Re-ensure after 10 minutes.

## Business Hermes-in-Docker

See `deploy/compose.override.hermes-sidecar.yml`. Hermes gets **no** socket. Supervisor is dual-homed: their `hermes-net` + `hermes-computers`. Computers only on `hermes-computers`. `sysctl` ip_forward=0.

```bash
docker exec -it -u hermes <hermes-container> \
  hermes plugins install tomlis20/hermes-computer --ref <40-char-sha>
```

Then doctor FIX lines, enable, restart gateway, new chat.

## Homelab (this WebUI / tailscale netns)

Supervisor on the **host** (`ssh host -- sudo docker compose`). Networks: existing `tailscale_net` + new `hermes-computers`. Agent uses Docker DNS. Takeover via `127.0.0.1:9376` + SSH `-L`.

## Tools

`computer_ensure` (name required), `computer_rpc`, `computer_events`, `computer_status`, `computer_stop`.

Parent LLM drives every click. Default observe is accessibility tree.

## Dev

```bash
pytest -q -m "not integration"
COMPUTER_PROVIDER=fake COMPUTER_SUPERVISOR_TOKEN=dev python supervisor/main.py
```

## License

MIT
