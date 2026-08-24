---
name: hermes-computer
description: Use when a site needs a real login and has no API.
version: 0.1.0
author: Tomasz (tomlis20), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [computer, browser, sidecar]
---

# Hermes Computer Skill

A headed Chrome that any Hermes profile can drive. The LLM stays here; cookies stay on the computer. No Browser Use, Nous, or Browserbase.

## When to Use

Any bot, not just coding:

- Hoster / DNS / ads / analytics admin UIs
- A login or cookie wall with no API, MCP, or CLI
- You need that login to survive into the next chat

Do not use for: bybsie.com, GitHub (`gh`), Gmail/Sheets via gws, or anything that already has a token. Do not `computer_ensure` "just in case."

## Prerequisites

- Supervisor up. `COMPUTER_SUPERVISOR_URL` + `COMPUTER_SUPERVISOR_TOKEN` on the Hermes process.
- Toolset `computer` on that profile (empty configs inherit default).
- Slot name defaults to `computer`. Another name is another login.

## How to Run

`computer_ensure` → `computer_rpc` (`navigate`, `observe` a11y, `act`). Screenshots only when a11y cannot answer.

## Procedure

1. `computer_ensure`. Done when `{status: running}`.
2. `navigate` then `observe` a11y. Done when facts come from the page.
3. `{paused: true}` → human uses the signed `novnc_url` (SSH `-L 9376`), then `resume`.
4. `computer_stop` when idle. `destroy` only to wipe cookies.

## Pitfalls

- You drive every click. The computer does not act alone.
- Idle stop keeps cookies, not open tabs.
- Enabling the plugin is not enough without the toolset. `hermes computer doctor` prints the merge line.

## Verification

Navigate `https://example.com` + observe a11y returns Example Domain from our Chromium.
