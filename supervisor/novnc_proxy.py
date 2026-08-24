"""Reverse-proxy a computer's noVNC (HTTP + WebSocket). Supervisor-originated only."""

from __future__ import annotations

import select
import socket
from http.server import BaseHTTPRequestHandler
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


def prefix(name: str, sig: str) -> str:
    return f"/computers/{name}/novnc/{sig}"


def vnc_query(name: str, sig: str) -> str:
    return urlencode(
        {
            "autoconnect": "1",
            "reconnect": "1",
            "resize": "scale",
            "path": f"computers/{name}/novnc/{sig}/websockify",
        }
    )


def parse_upstream(url: str) -> tuple[str, int, str]:
    p = urlparse(url)
    host = p.hostname or "127.0.0.1"
    port = p.port or (443 if p.scheme == "https" else 80)
    return host, port, (p.path or "/")


def rest_path(parts: list[str], query: str) -> str:
    rest = "/" + "/".join(parts[4:]) if len(parts) > 4 else "/"
    if not rest.startswith("/"):
        rest = "/" + rest
    if query:
        rest = f"{rest}?{query}"
    return rest


def is_websocket(handler: BaseHTTPRequestHandler) -> bool:
    return handler.headers.get("Upgrade", "").lower() == "websocket"


def proxy_http(handler: BaseHTTPRequestHandler, upstream: str, dest: str) -> None:
    url = upstream.rstrip("/") + dest
    headers = {k: v for k, v in handler.headers.items() if k.lower() not in HOP}
    req = Request(url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read()
            handler.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() in HOP or k.lower() == "content-length":
                    continue
                handler.send_header(k, v)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
    except HTTPError as exc:
        body = exc.read() or b""
        handler.send_response(exc.code)
        handler.send_header("Content-Type", exc.headers.get("Content-Type", "text/plain"))
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except URLError as exc:
        msg = f"novnc upstream unreachable: {exc.reason}".encode()
        handler.send_response(502)
        handler.send_header("Content-Type", "text/plain")
        handler.send_header("Content-Length", str(len(msg)))
        handler.end_headers()
        handler.wfile.write(msg)


def proxy_ws(handler: BaseHTTPRequestHandler, host: str, port: int, dest: str) -> None:
    upstream = socket.create_connection((host, port), timeout=10)
    try:
        lines = [f"GET {dest} HTTP/1.1", f"Host: {host}:{port}"]
        for key, val in handler.headers.items():
            if key.lower() == "host":
                continue
            lines.append(f"{key}: {val}")
        blob = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        upstream.sendall(blob)
        _splice(handler.connection, upstream)
    finally:
        try:
            upstream.close()
        except OSError:
            pass


def _splice(a: socket.socket, b: socket.socket) -> None:
    for s in (a, b):
        s.setblocking(False)
    pair: Iterable[socket.socket] = (a, b)
    try:
        while True:
            r, _, x = select.select([a, b], [], [a, b], 300)
            if x:
                break
            if not r:
                break
            for src in r:
                dst = b if src is a else a
                try:
                    data = src.recv(65536)
                except BlockingIOError:
                    continue
                if not data:
                    return
                dst.sendall(data)
    except OSError:
        return
    finally:
        del pair
