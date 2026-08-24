"""Stdlib HMAC HTTP client and signing helpers.

Imported by the Hermes plugin AND by the supervisor process (via sys.path).
Must not import supervisor/ or agentd/.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urljoin


SKEW_S = 60
TAKEOVER_TTL_S = 600
NAME_RE_OK = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"


def validate_name(name: str) -> str:
    if not name or not all(c in NAME_RE_OK for c in name) or name[0] == "-":
        raise ValueError("computer name must be [A-Za-z0-9_-]+ and not start with -")
    if len(name) > 64:
        raise ValueError("computer name too long")
    return name


def _canon(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{digest}".encode("utf-8")


def sign_request(secret: str, method: str, path: str, body: bytes, timestamp: str | None = None) -> tuple[str, str]:
    ts = timestamp if timestamp is not None else str(int(time.time()))
    sig = hmac.new(secret.encode("utf-8"), _canon(method, path, ts, body), hashlib.sha256).hexdigest()
    return ts, sig


def verify_request(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    timestamp: str,
    signature: str,
    now: int | None = None,
) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - ts) > SKEW_S:
        return False
    _, expected = sign_request(secret, method, path, body, timestamp=timestamp)
    return hmac.compare_digest(expected, signature or "")


def mint_takeover(secret: str, name: str, ttl_s: int = TAKEOVER_TTL_S, now: int | None = None) -> tuple[str, int]:
    exp = (int(time.time()) if now is None else now) + ttl_s
    msg = f"novnc\n{name}\n{exp}".encode("utf-8")
    token = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{exp}.{token}", exp


def verify_takeover(secret: str, name: str, signed: str, now: int | None = None) -> bool:
    try:
        exp_s, token = signed.split(".", 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    current = int(time.time()) if now is None else now
    if current > exp:
        return False
    msg = f"novnc\n{name}\n{exp}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, token)


class SupervisorClient:
    def __init__(self, base_url: str, token: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout_s = timeout_s

    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ts, sig = sign_request(self.token, method, path, body)
        url = urljoin(self.base_url, path.lstrip("/"))
        req = urllib.request.Request(url, data=body or None, method=method)
        req.add_header("X-Computer-Timestamp", ts)
        req.add_header("X-Computer-Signature", sig)
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {"ok": False, "error": f"http_{exc.code}"}
            data.setdefault("ok", False)
            return data
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"unreachable: {exc.reason}"}
        if not raw:
            return {"ok": True}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid_json"}

    def health(self) -> dict[str, Any]:
        return self._call("GET", "/health")

    def list_computers(self) -> dict[str, Any]:
        return self._call("GET", "/computers")

    def ensure(self, name: str) -> dict[str, Any]:
        return self._call("POST", f"/computers/{quote(name, safe='')}/ensure", {})

    def rpc(self, name: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._call(
            "POST",
            f"/computers/{quote(name, safe='')}/rpc",
            {"id": f"req_{int(time.time() * 1000)}", "method": method, "params": params or {}},
        )

    def events(self, name: str, after: str = "") -> dict[str, Any]:
        q = f"?after={quote(after)}" if after else ""
        return self._call("GET", f"/computers/{quote(name, safe='')}/events{q}")

    def stop(self, name: str, destroy: bool = False) -> dict[str, Any]:
        return self._call("POST", f"/computers/{quote(name, safe='')}/stop", {"destroy": destroy})


def env_client() -> SupervisorClient | None:
    url = os.environ.get("COMPUTER_SUPERVISOR_URL", "").strip()
    token = os.environ.get("COMPUTER_SUPERVISOR_TOKEN", "").strip()
    if not url or not token:
        return None
    return SupervisorClient(url, token)
