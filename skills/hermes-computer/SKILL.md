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

`computer_ensure` → `computer_rpc` (`navigate`, `observe` a11y, `act`). A11y answers questions; screenshots show the human your screen.

## Showing your screen

`computer_rpc` `observe` `{"mode": "screenshot"}` returns `screenshot_path`. Put `MEDIA:<screenshot_path>` on its own line in your reply and the human sees the desktop in chat. Attach one when it informs the human — after landing somewhere that matters, when reporting progress, when something looks wrong. Not on every message.

## Procedure

1. `computer_ensure`. Done when `{status: running}`.
2. `navigate` then `observe` a11y. Done when facts come from the page.
3. `{paused: true}` or a `needs_human` event → hand over (below), then `resume`.
4. `computer_stop` when idle. `destroy` only to wipe cookies.

## Hand over to the human

When paused (captcha, 2FA, login) — `observe` still works while paused:

1. `observe` `{"mode": "screenshot"}` → reply with the `MEDIA:` line so they see what you see.
2. Re-run `computer_ensure` for a fresh `novnc_url` (links expire ~10 min) and include it: that link is live control of the desktop.
3. One plain line: what to do, and "tell me done".
4. On their confirmation: `computer_rpc` `resume`, then re-observe before acting.

## Pitfalls

- You drive every click. The computer does not act alone.
- Idle stop keeps cookies, not open tabs.
- A `novnc_url` older than ~10 minutes is dead — re-ensure, don't apologise.
- Enabling the plugin is not enough without the toolset. `hermes computer doctor` prints the merge line.

## Verification

Navigate `https://example.com` + observe a11y returns Example Domain from our Chromium.
