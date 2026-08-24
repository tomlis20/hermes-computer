# Hermes Computer

Self-hosted **computer** for Hermes: a named Linux desktop (Chromium + VNC + `agentd`) owned by a supervisor that is the only process with `docker.sock`. Hermes stays the brain. No Browser Use, Nous, or Browserbase.

The default slot is called `computer`. Another name is another login.

## Two artifacts

| | What | How |
|---|---|---|
| Plugin | tools + HMAC client | `hermes plugins install tomlis20/hermes-computer --ref <40-char-sha>` |
| Runtime | supervisor + computer images | `deploy/docker-compose.yml` (pull, not build) |

Plugin install does **not** start a computer. Both are required.

Supervisor + socket is **root-equivalent** on the host. Pin a SHA you trust.

## Install

1. `hermes plugins install tomlis20/hermes-computer --ref <sha>`  
   First install is interactive (`plugin-guard` may say `caution`). `--force` skips confirmation, not the scan.
2. Same `COMPUTER_SUPERVISOR_TOKEN` on the supervisor **and** every Hermes process, plus  
   `COMPUTER_SUPERVISOR_URL=http://hermes-computer-supervisor:9376`
3. `docker compose -f deploy/docker-compose.yml up -d` from the plugin dir (or merge `deploy/compose.override.hermes-sidecar.yml`). Hermes gets **no** socket. `ip_forward=0` stays on.
4. `hermes computer doctor` — paste the FIX lines it prints. Do not copy a canned toolset list.
5. `hermes plugins enable hermes-computer` if needed. **New chat.**
6. `computer_ensure` → navigate `https://example.com` → observe `a11y` → Example Domain.

Watch: `ssh -N -L 9376:127.0.0.1:9376` to that Docker host, then open the signed `novnc_url` from `ensure`. Re-ensure after 10 minutes.

Hermes-in-Docker elsewhere: same overlay, swap `hermes-net` for their existing network. Computers stay only on `hermes-computers`.

## Tools

`computer_ensure`, `computer_rpc`, `computer_events`, `computer_status`, `computer_stop`.

Parent LLM drives every click. Default observe is the accessibility tree. If a site already has an API/MCP/CLI, do not open a computer.

## Dev

```bash
pytest -q -m "not integration"
COMPUTER_PROVIDER=fake COMPUTER_SUPERVISOR_TOKEN=dev python supervisor/main.py
```

## License

MIT
