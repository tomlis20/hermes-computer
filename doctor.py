"""Merge-safe doctor. Stdlib only. May be imported by the plugin CLI."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

try:
    from .client import env_client
except ImportError:
    from client import env_client


def _which_process() -> str:
    if os.environ.get("HERMES_GATEWAY") or os.path.exists("/run/s6"):
        return "container-gateway-or-s6"
    if "webui" in os.environ.get("HOSTNAME", "").lower():
        return "webui-or-named-host"
    return f"pid={os.getpid()} host={socket.gethostname()}"


def _load_yaml_platform_toolsets() -> dict[str, list[str]]:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    cfg = home / "config.yaml"
    if not cfg.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        raw = data.get("platform_toolsets") or {}
        return {k: list(v or []) for k, v in raw.items() if isinstance(v, list)}
    except Exception:
        return _parse_toolsets_naive(cfg.read_text(encoding="utf-8"))


def _parse_toolsets_naive(text: str) -> dict[str, list[str]]:
    """Tiny YAML subset if PyYAML is missing: platform_toolsets.KEY: then dashed list."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    in_block = False
    for line in text.splitlines():
        if line.startswith("platform_toolsets:"):
            in_block = True
            continue
        if in_block and line and not line.startswith(" ") and not line.startswith("\t"):
            break
        if not in_block:
            continue
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("-"):
            current = stripped[:-1]
            out[current] = []
        elif stripped.startswith("- ") and current:
            out[current].append(stripped[2:].strip().strip("'\""))
    return out


def merge_commands(toolsets: dict[str, list[str]]) -> list[str]:
    cmds: list[str] = []
    for key, items in toolsets.items():
        if "computer" in items:
            continue
        merged = items + ["computer"]
        rendered = json.dumps(merged)
        cmds.append(f"hermes config set platform_toolsets.{key} '{rendered}'")
    return cmds


def run_doctor() -> str:
    lines = [f"process: {_which_process()}"]
    c = env_client()
    if c is None:
        lines.append("env: MISSING COMPUTER_SUPERVISOR_URL and/or COMPUTER_SUPERVISOR_TOKEN")
    else:
        lines.append(f"env: url={c.base_url} token=***redacted***")
        health = c.health()
        lines.append(f"supervisor /health: {json.dumps(health, separators=(',', ':'))}")
        if health.get("sandbox_default") == "no-sandbox" or (
            isinstance(health.get("sandbox"), str) and "no-sandbox" in health.get("sandbox", "")
        ):
            lines.append("warning: Chromium sandbox fallback --no-sandbox is active")
    toolsets = _load_yaml_platform_toolsets()
    if not toolsets:
        lines.append("platform_toolsets: none readable (doctor cannot merge)")
    else:
        exposed = [k for k, v in toolsets.items() if "computer" in v]
        if exposed:
            lines.append(f"toolset computer present on: {', '.join(exposed)}")
        else:
            lines.append("toolset computer not on any platform_toolsets key")
            for cmd in merge_commands(toolsets):
                lines.append(f"FIX: {cmd}")
    if not os.environ.get("COMPUTER_SUPERVISOR_URL"):
        lines.append("note: missing Docker in this process is not a failure")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(run_doctor())
