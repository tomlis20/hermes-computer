# Protocol v0

JSON request/response. Supervisor never interprets clicks.

```
POST /computers/{name}/rpc
{ "id": "req_1", "method": "navigate", "params": { "url": "https://example.com" } }
```

Methods: `observe` (default mode `a11y`), `act`, `navigate`, `js`, `shell` (create-time opt-in), `files.list`, `files.read`, `resume`.

Events: poll `GET /computers/{name}/events?after=`. Types: `needs_human`, `download`, `crash`, `heartbeat`, `console`.

Auth:

- Hermes → supervisor: HMAC `METHOD\\nPATH\\nTIMESTAMP\\nSHA256(body)`, skew 60s.
- Supervisor → agentd: `Authorization: Bearer <per-computer token>`.
- Human → noVNC: `/computers/{name}/novnc/<exp.hmac>/…` 10 min. Re-`ensure` to mint.

Pause: `needs_human` → further `act`/`navigate` return `{paused: true}` until `resume`.
