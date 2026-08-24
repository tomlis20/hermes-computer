"""In-memory provider for unit tests. No Docker."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from provider import ComputerOpts, Health
from store import Computer, Store


class FakeProvider:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.calls: list[tuple[str, str]] = []
        self.rpc_impl: dict[str, Any] | None = None
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._paused: set[str] = set()
        self._pages: dict[str, dict[str, Any]] = {}
        self._novnc_url = ""

    def create(self, name: str, opts: ComputerOpts) -> Computer:
        self.calls.append(("create", name))
        rec = Computer(
            name=name,
            status="created",
            created_at=time.time(),
            agentd_token=secrets.token_hex(16),
            extra={
                "allow_private_urls": opts.allow_private_urls,
                "shell": opts.shell,
            },
        )
        return self.store.put(rec)

    def start(self, name: str) -> Computer:
        self.calls.append(("start", name))
        rec = self.store.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "running"
        return self.store.put(rec)

    def stop(self, name: str) -> Computer:
        self.calls.append(("stop", name))
        rec = self.store.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "stopped"
        return self.store.put(rec)

    def destroy(self, name: str) -> None:
        self.calls.append(("destroy", name))
        rec = self.store.get(name)
        if rec is None:
            return
        rec.status = "destroyed"
        self.store.put(rec)

    def health(self, name: str) -> Health:
        rec = self.store.get(name)
        if rec is None or rec.status != "running":
            return Health(False, "unknown", "not_running")
        return Health(True, rec.sandbox or "seccomp", "ok")

    def novnc_upstream(self, name: str) -> str:
        return self._novnc_url or f"http://127.0.0.1:9/{name}"

    def events(self, name: str, after: str = "") -> dict[str, Any]:
        items = self._events.get(name, [])
        if after:
            items = [e for e in items if e.get("ts", "") > after]
        return {"ok": True, "events": items}

    def emit(self, name: str, event: dict[str, Any]) -> None:
        self._events.setdefault(name, []).append(event)
        if event.get("type") == "needs_human":
            self._paused.add(name)

    def rpc(self, name: str, req: dict[str, Any]) -> dict[str, Any]:
        rec = self.store.get(name)
        if rec is None:
            return {"ok": False, "error": "missing"}
        if rec.status != "running":
            return {"ok": False, "error": "not_running"}
        method = req.get("method", "")
        params = req.get("params") or {}
        if name in self._paused and method in {"act", "navigate"}:
            return {"ok": False, "paused": True, "reason": "needs_human"}
        if method == "resume":
            self._paused.discard(name)
            return {"ok": True, "paused": False}
        if method == "navigate":
            url = params.get("url", "")
            if not rec.extra.get("allow_private_urls") and _is_private_url(url):
                return {"ok": False, "error": "private_url"}
            self._pages[name] = {"url": url, "h1": "Example Domain" if "example.com" in url else ""}
            if "captcha" in url.lower() or "challenge" in url.lower():
                self.emit(
                    name,
                    {
                        "ts": f"{time.time():.3f}",
                        "type": "needs_human",
                        "reason": "captcha",
                    },
                )
                return {"ok": False, "paused": True, "reason": "captcha"}
            return {"ok": True, "url": url}
        if method == "observe":
            page = self._pages.get(name, {})
            mode = params.get("mode", "a11y")
            out: dict[str, Any] = {"ok": True, "mode": mode, "url": page.get("url", "")}
            if mode in {"a11y", "both"}:
                out["a11y"] = {"h1": page.get("h1", ""), "title": page.get("h1", "")}
            if mode in {"screenshot", "both"}:
                out["screenshot_path"] = f"/events/{name}.png"
            return out
        if method == "js":
            return {"ok": True, "value": None}
        if method == "act":
            return {"ok": True, "actions": params.get("actions", [])}
        if method == "shell":
            if not rec.extra.get("shell"):
                return {"ok": False, "error": "shell_disabled"}
            return {"ok": True, "stdout": ""}
        if method == "files.list":
            return {"ok": True, "entries": []}
        if method == "files.read":
            return {"ok": False, "error": "not_found"}
        return {"ok": False, "error": f"unknown_method:{method}"}


def _is_private_url(url: str) -> bool:
    u = url.lower()
    needles = (
        "169.254.",
        "127.0.0.1",
        "localhost",
        "10.",
        "192.168.",
        "metadata.google",
        "[::1]",
    )
    return any(n in u for n in needles)
