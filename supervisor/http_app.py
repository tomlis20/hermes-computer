"""Supervisor HTTP app. Hermes-facing listeners only. No computer-net bind."""

from __future__ import annotations

import ipaddress
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# Repo root on sys.path when launched as `python supervisor/main.py`
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from client import mint_takeover, validate_name, verify_request, verify_takeover  # noqa: E402


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _peer_ip(handler: BaseHTTPRequestHandler) -> str:
    return handler.client_address[0]


def _in_nets(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for c in cidrs:
        try:
            if addr in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            continue
    return False


def make_handler(ctx: dict[str, Any]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _blocked(self) -> bool:
            return _in_nets(_peer_ip(self), ctx.get("deny_cidrs") or [])

        def _read_body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _auth(self, method: str, path: str, body: bytes) -> bool:
            return verify_request(
                ctx["secret"],
                method,
                path,
                body,
                self.headers.get("X-Computer-Timestamp", ""),
                self.headers.get("X-Computer-Signature", ""),
            )

        def do_GET(self) -> None:  # noqa: N802
            if self._blocked():
                return _json(self, 403, {"ok": False, "error": "denied_source"})
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                return _json(self, 200, {"ok": True, "sandbox_default": ctx.get("sandbox_default", "unknown")})
            if path.startswith("/computers/") and "/novnc/" in path:
                return self._novnc(path)
            if path == "/computers":
                if not self._auth("GET", path, b""):
                    return _json(self, 401, {"ok": False, "error": "unauthorized"})
                items = [c.to_public() for c in ctx["store"].list()]
                return _json(self, 200, {"ok": True, "computers": items})
            if path.startswith("/computers/") and path.endswith("/events"):
                if not self._auth("GET", path, b""):
                    return _json(self, 401, {"ok": False, "error": "unauthorized"})
                name = path.split("/")[2]
                after = parse_qs(parsed.query).get("after", [""])[0]
                try:
                    return _json(self, 200, ctx["provider"].events(name, after))
                except KeyError:
                    return _json(self, 404, {"ok": False, "error": "missing"})
            return _json(self, 404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self._blocked():
                return _json(self, 403, {"ok": False, "error": "denied_source"})
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_body()
            if not self._auth("POST", path, body):
                return _json(self, 401, {"ok": False, "error": "unauthorized"})
            parts = path.strip("/").split("/")
            if len(parts) != 3 or parts[0] != "computers":
                return _json(self, 404, {"ok": False, "error": "not_found"})
            _, name, action = parts
            try:
                name = validate_name(name)
            except ValueError as exc:
                return _json(self, 400, {"ok": False, "error": str(exc)})
            if action == "ensure":
                return _json(self, 200, self._ensure(name))
            if action == "rpc":
                try:
                    req = json.loads(body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    return _json(self, 400, {"ok": False, "error": "invalid_json"})
                rec = ctx["store"].get(name)
                if rec is None:
                    return _json(self, 404, {"ok": False, "error": "missing"})
                result = ctx["provider"].rpc(name, req)
                ctx["store"].touch_rpc(name)
                return _json(self, 200, result)
            if action == "stop":
                try:
                    payload = json.loads(body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    payload = {}
                if payload.get("destroy"):
                    ctx["provider"].destroy(name)
                    return _json(self, 200, {"ok": True, "status": "destroyed"})
                rec = ctx["provider"].stop(name)
                return _json(self, 200, {"ok": True, **rec.to_public()})
            return _json(self, 404, {"ok": False, "error": "not_found"})

        def _ensure(self, name: str) -> dict[str, Any]:
            rec = ctx["store"].get(name)
            if rec is None or rec.status == "destroyed":
                rec = ctx["provider"].create(name, ctx["default_opts"])
            if rec.status != "running":
                rec = ctx["provider"].start(name)
            token, exp = mint_takeover(ctx["secret"], name)
            base = ctx.get("public_base", "http://127.0.0.1:9376")
            return {
                "ok": True,
                "name": rec.name,
                "status": rec.status,
                "age_s": int(time.time() - rec.created_at),
                "novnc_url": f"{base}/computers/{name}/novnc/{token}/",
                "novnc_expires": exp,
                "sandbox": rec.sandbox,
            }

        def _novnc(self, path: str) -> None:
            # /computers/{name}/novnc/{sig}/...
            parts = path.strip("/").split("/")
            if len(parts) < 4:
                return _json(self, 403, {"ok": False, "error": "forbidden"})
            name, sig = parts[1], parts[3]
            if not verify_takeover(ctx["secret"], name, sig):
                return _json(self, 403, {"ok": False, "error": "forbidden"})
            rec = ctx["store"].get(name)
            if rec is None or rec.status != "running":
                return _json(self, 404, {"ok": False, "error": "missing"})
            body = (
                "<!doctype html><title>takeover</title>"
                f"<p>signed takeover for {name}</p>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(
    ctx: dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 9376,
) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(ctx))
    return httpd
