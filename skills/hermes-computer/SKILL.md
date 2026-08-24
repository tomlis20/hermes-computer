---
name: hermes-computer
description: Drive a named self-hosted computer for no-API sites.
version: 0.1.0
author: Tomasz (tomlis20), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [computer, browser, sidecar]
---

# Hermes Computer Skill

Own a headed Linux computer (container) and drive it from Hermes. The LLM stays here; the computer holds only site cookies. No Browser Use, Nous, or Browserbase.

## When to Use

- A site has no API, MCP, or CLI and you need to click or read a live page.
- You need a login to persist on a named computer across chats.

Do not use for: bybsie.com, GitHub, Gmail, Sheets, or any tool that already has a token here. Do not `computer_ensure` "just in case."

## Prerequisites

- Supervisor up. Env: `COMPUTER_SUPERVISOR_URL`, `COMPUTER_SUPERVISOR_TOKEN` in **both** gateway and WebUI compose.
- Toolset visible: run `hermes computer doctor` and paste the FIX lines it prints (`platform_toolsets` merge). New chat after that.
- `name` is required. Sharing a name shares that computer's logins.

## How to Run

Use tools `computer_ensure`, `computer_rpc`, `computer_events`, `computer_status`, `computer_stop`. Default `observe` mode is `a11y`. Screenshots only when a11y cannot answer.

## Procedure

1. `computer_ensure` with an explicit `name` (e.g. `lab`). Completion: `{status: running, novnc_url}`.
2. `computer_rpc` `navigate` then `observe` (`a11y`). Completion: facts from the page, not invented.
3. On `{paused: true}` open the signed `novnc_url` via SSH `-L` (loopback). Then `resume`.
4. `computer_stop` when idle. `destroy` only to wipe cookies.

## Pitfalls

- Parent LLM drives every click. The computer does not act alone.
- Idle `docker stop` keeps cookies, not in-memory tabs.
- Hostile pages cannot reach Hermes private nets; they can probe sibling computers (token-gated).
- Enabling the plugin does not add the toolset. Doctor must merge `computer` into existing `platform_toolsets` keys.

## Verification

`computer_rpc` navigate `https://example.com` + observe a11y returns Example Domain from **our** Chromium, not a cloud browser.
