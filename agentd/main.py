"""agentd — runs inside the computer. Token in process env only."""

from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

PRIVATE_RE = re.compile(
    r"(?i)(127\.0\.0\.1|localhost|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"169\.254\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|\[::1\]|"
    r"metadata\.google|169\.254\.169\.254)"
)
CAPTCHA_RE = re.compile(r"(?i)captcha|challenge|verify you are human|totp|2fa")


class AgentState:
    def __init__(self) -> None:
        self.token = os.environ.get("AGENTD_TOKEN", "")
        self.allow_private = os.environ.get("AGENTD_ALLOW_PRIVATE", "") == "1"
        self.shell = os.environ.get("AGENTD_SHELL", "") == "1"
        self.paused = False
        self.pause_reason = ""
        self.page: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.sandbox = os.environ.get("AGENTD_SANDBOX", "unknown")
        self.cdp: Any = None

    def emit(self, typ: str, **kw: Any) -> dict[str, Any]:
        ev = {"ts": f"{time.time():.6f}", "type": typ, **kw}
        self.events.append(ev)
        if typ == "needs_human":
            self.paused = True
            self.pause_reason = str(kw.get("reason") or "needs_human")
        return ev


def _auth(handler: BaseHTTPRequestHandler, token: str) -> bool:
    hdr = handler.headers.get("Authorization", "")
    if hdr.startswith("Bearer "):
        return hdr[7:] == token and bool(token)
    return handler.headers.get("X-Agentd-Token", "") == token and bool(token)


def make_handler(state: AgentState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                return self._json(
                    200,
                    {"ok": True, "sandbox": state.sandbox, "paused": state.paused},
                )
            if not _auth(self, state.token):
                return self._json(401, {"ok": False, "error": "unauthorized"})
            if parsed.path == "/events":
                after = parse_qs(parsed.query).get("after", [""])[0]
                items = [e for e in state.events if e["ts"] > after] if after else list(state.events)
                return self._json(200, {"ok": True, "events": items})
            return self._json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if not _auth(self, state.token):
                return self._json(401, {"ok": False, "error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b"{}"
            try:
                req = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return self._json(400, {"ok": False, "error": "invalid_json"})
            method = req.get("method", "")
            params = req.get("params") or {}
            if method == "resume":
                state.paused = False
                state.pause_reason = ""
                return self._json(200, {"ok": True, "paused": False})
            if state.paused and method in {"act", "navigate"}:
                return self._json(200, {"ok": False, "paused": True, "reason": state.pause_reason})
            try:
                return self._json(200, handle_rpc(state, method, params))
            except Exception as exc:
                return self._json(200, {"ok": False, "error": f"rpc_failed:{exc}"})

    return Handler


def handle_rpc(state: AgentState, method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "resume":
        state.paused = False
        state.pause_reason = ""
        return {"ok": True, "paused": False}
    if state.paused and method in {"act", "navigate"}:
        return {"ok": False, "paused": True, "reason": state.pause_reason}
    if method == "navigate":
        url = str(params.get("url") or "")
        if not state.allow_private and PRIVATE_RE.search(url):
            return {"ok": False, "error": "private_url"}
        title = ""
        if state.cdp is not None:
            result = state.cdp.navigate(url)
            title = str(result.get("title") or "")
        else:
            title = "Example Domain" if "example.com" in url else url
        state.page = {"url": url, "title": title, "h1": title}
        if CAPTCHA_RE.search(url) or CAPTCHA_RE.search(title):
            state.emit("needs_human", reason="captcha", screenshot="")
            return {"ok": False, "paused": True, "reason": "captcha"}
        return {"ok": True, "url": url, "title": title}
    if method == "observe":
        mode = params.get("mode") or "a11y"
        out: dict[str, Any] = {"ok": True, "mode": mode, "url": state.page.get("url", "")}
        if mode in {"a11y", "both"}:
            if state.cdp is not None:
                out["a11y"] = state.cdp.a11y()
            else:
                out["a11y"] = {"h1": state.page.get("h1", ""), "title": state.page.get("title", "")}
        if mode in {"screenshot", "both"}:
            if state.cdp is not None:
                try:
                    out["screenshot_b64"] = state.cdp.screenshot()
                    out["screenshot_format"] = "jpeg"
                except Exception as exc:
                    out["screenshot_error"] = f"capture_failed:{exc}"
            else:
                out["screenshot_path"] = "/home/agent/events/last.png"
        return out
    if method == "js":
        expr = str(params.get("expression") or "")
        if state.cdp is not None:
            return {"ok": True, "value": state.cdp.js(expr)}
        return {"ok": True, "value": None}
    if method == "act":
        actions = params.get("actions") or []
        done: list[dict[str, Any]] = []
        for raw in actions:
            typ = str(raw.get("type") or "")
            if state.cdp is None:
                done.append({"type": typ, "ok": True, "note": "no_cdp"})
                continue
            if typ == "click":
                if raw.get("selector"):
                    box = state.cdp.click_selector(str(raw["selector"]))
                    done.append({"type": "click", "ok": True, **box})
                elif "x" in raw and "y" in raw:
                    state.cdp.click_xy(float(raw["x"]), float(raw["y"]))
                    done.append({"type": "click", "ok": True, "x": raw["x"], "y": raw["y"]})
                else:
                    done.append({"type": "click", "ok": False, "error": "need selector or x,y"})
            elif typ == "type":
                state.cdp.type_text(str(raw.get("text") or ""), raw.get("selector"))
                done.append({"type": "type", "ok": True})
            elif typ == "press":
                state.cdp.press(str(raw.get("key") or "Enter"))
                done.append({"type": "press", "ok": True})
            else:
                done.append({"type": typ, "ok": False, "error": "unknown_action"})
        return {"ok": True, "actions": done}
    if method == "shell":
        if not state.shell:
            return {"ok": False, "error": "shell_disabled"}
        return {"ok": False, "error": "not_implemented"}
    if method == "files.list":
        return {"ok": True, "entries": []}
    if method == "files.read":
        return {"ok": False, "error": "not_found"}
    return {"ok": False, "error": f"unknown_method:{method}"}


def main() -> None:
    state = AgentState()
    if not state.token:
        raise SystemExit("AGENTD_TOKEN required")
    try:
        from cdp import wait_cdp

        state.cdp = wait_cdp(timeout=20.0)
        print("cdp connected", flush=True)
    except Exception as exc:
        print(f"cdp unavailable: {exc}", flush=True)
    host = os.environ.get("AGENTD_BIND", "0.0.0.0")
    port = int(os.environ.get("AGENTD_PORT", "9377"))
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"agentd on {host}:{port} sandbox={state.sandbox}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
