"""Hermes Computer plugin — tools + skill. Import-light: client.py + stdlib only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from . import client as _client
except ImportError:
    import client as _client  # type: ignore


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _client_or_err() -> tuple[_client.SupervisorClient | None, str | None]:
    c = _client.env_client()
    if c is None:
        return None, "COMPUTER_SUPERVISOR_URL and COMPUTER_SUPERVISOR_TOKEN required"
    return c, None


def _require_name(params: dict[str, Any]) -> str:
    name = str(params.get("name") or "computer").strip() or "computer"
    return _client.validate_name(name)


def _ensure(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    c, err = _client_or_err()
    if c is None:
        return _dump({"ok": False, "error": err or "no_client"})
    try:
        name = _require_name(params)
    except ValueError as exc:
        return _dump({"ok": False, "error": str(exc)})
    return _dump(c.ensure(name))


def _rpc(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    c, err = _client_or_err()
    if c is None:
        return _dump({"ok": False, "error": err or "no_client"})
    try:
        name = _require_name(params)
    except ValueError as exc:
        return _dump({"ok": False, "error": str(exc)})
    method = str(params.get("method") or "").strip()
    if not method:
        return _dump({"ok": False, "error": "method required"})
    extra = params.get("params")
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        return _dump({"ok": False, "error": "params must be an object"})
    return _dump(c.rpc(name, method, extra))


def _events(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    c, err = _client_or_err()
    if c is None:
        return _dump({"ok": False, "error": err or "no_client"})
    try:
        name = _require_name(params)
    except ValueError as exc:
        return _dump({"ok": False, "error": str(exc)})
    return _dump(c.events(name, str(params.get("after") or "")))


def _status(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    c, err = _client_or_err()
    if c is None:
        return _dump({"ok": False, "error": err or "no_client"})
    return _dump(c.list_computers())


def _stop(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    c, err = _client_or_err()
    if c is None:
        return _dump({"ok": False, "error": err or "no_client"})
    try:
        name = _require_name(params)
    except ValueError as exc:
        return _dump({"ok": False, "error": str(exc)})
    return _dump(c.stop(name, destroy=bool(params.get("destroy"))))


def _env_ok() -> bool:
    return _client.env_client() is not None


def register(ctx: Any) -> None:
    skill = Path(__file__).resolve().parent / "skills" / "hermes-computer" / "SKILL.md"
    if skill.is_file():
        try:
            ctx.register_skill("hermes-computer", skill)
        except Exception:
            pass

    tools = [
        (
            "computer_ensure",
            "Create or start the headed computer. Defaults to name=computer.",
            {
                "name": {"type": "string", "description": "Slot name. Default: computer."},
            },
            [],
            _ensure,
        ),
        (
            "computer_rpc",
            "Call one protocol method on a named computer (navigate, observe, act, js, files, resume).",
            {
                "name": {"type": "string", "description": "Computer name."},
                "method": {"type": "string", "description": "Protocol method."},
                "params": {"type": "object", "description": "Method params."},
            },
            ["name", "method"],
            _rpc,
        ),
        (
            "computer_events",
            "Poll events for a named computer after an optional cursor.",
            {
                "name": {"type": "string", "description": "Computer name."},
                "after": {"type": "string", "description": "Event timestamp cursor."},
            },
            ["name"],
            _events,
        ),
        (
            "computer_status",
            "List computers and health known to the supervisor.",
            {},
            [],
            _status,
        ),
        (
            "computer_stop",
            "Pause (default) or destroy a named computer.",
            {
                "name": {"type": "string", "description": "Computer name."},
                "destroy": {"type": "boolean", "description": "If true, wipe volume."},
            },
            ["name"],
            _stop,
        ),
    ]
    for name, desc, props, required, handler in tools:
        ctx.register_tool(
            name=name,
            toolset="computer",
            schema={
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
            handler=handler,
            check_fn=_env_ok,
        )
    try:
        ctx.register_cli_command(
            name="computer",
            help="Hermes Computer supervisor tools",
            setup_fn=_cli_setup,
            handler_fn=_cli_handler,
        )
    except Exception:
        pass


def _cli_setup(parser: Any) -> None:
    sub = parser.add_subparsers(dest="computer_cmd")
    sub.add_parser("doctor")
    sub.add_parser("ls")
    p = sub.add_parser("ensure")
    p.add_argument("name")
    p = sub.add_parser("stop")
    p.add_argument("name")
    p = sub.add_parser("destroy")
    p.add_argument("name")


def _cli_handler(args: Any) -> None:
    try:
        from .doctor import run_doctor
    except ImportError:
        from doctor import run_doctor

    cmd = getattr(args, "computer_cmd", None)
    if cmd == "doctor" or cmd is None:
        print(run_doctor())
        return
    c = _client.env_client()
    if c is None:
        print("set COMPUTER_SUPERVISOR_URL and COMPUTER_SUPERVISOR_TOKEN")
        return
    if cmd == "ls":
        print(json.dumps(c.list_computers(), indent=2))
    elif cmd == "ensure":
        print(json.dumps(c.ensure(args.name), indent=2))
    elif cmd == "stop":
        print(json.dumps(c.stop(args.name, False), indent=2))
    elif cmd == "destroy":
        print(json.dumps(c.stop(args.name, True), indent=2))
