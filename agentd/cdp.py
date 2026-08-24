"""Minimal CDP client (stdlib WebSocket). Used only inside the computer image."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import time
import urllib.request
from typing import Any
from urllib.parse import urlparse


class CdpError(RuntimeError):
    pass


def _ws_key() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


class _WS:
    def __init__(self, url: str, timeout: float = 15.0) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        raw = socket.create_connection((host, port), timeout=timeout)
        sock: socket.socket | ssl.SSLSocket = raw
        if parsed.scheme == "wss":
            sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = _ws_key()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise CdpError("ws handshake eof")
            buf += chunk
        header, rest = buf.split(b"\r\n\r\n", 1)
        if b"101" not in header.split(b"\r\n", 1)[0]:
            raise CdpError(f"ws handshake failed: {header[:120]!r}")
        expected = base64.b64encode(hashlib.sha1(key.encode() + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()).decode()
        if expected.encode() not in header:
            raise CdpError("ws accept mismatch")
        self.sock = sock
        self._buf = rest

    def send_text(self, text: str) -> None:
        data = text.encode("utf-8")
        header = bytearray([0x81])
        n = len(data)
        mask = os.urandom(4)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(n.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(n.to_bytes(8, "big"))
        header.extend(mask)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(header + payload)

    def recv_text(self) -> str:
        while True:
            opcode, data = self._read_frame()
            if opcode == 0x1:
                return data.decode("utf-8")
            if opcode == 0x8:
                raise CdpError("ws closed")
            if opcode == 0x9:
                self._pong(data)

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise CdpError("ws eof")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_frame(self) -> tuple[int, bytes]:
        b1, b2 = self._read_exact(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        n = b2 & 0x7F
        if n == 126:
            n = int.from_bytes(self._read_exact(2), "big")
        elif n == 127:
            n = int.from_bytes(self._read_exact(8), "big")
        mask = self._read_exact(4) if masked else b""
        data = self._read_exact(n)
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return opcode, data

    def _pong(self, data: bytes) -> None:
        header = bytearray([0x8A, 0x80 | len(data)])
        mask = os.urandom(4)
        header.extend(mask)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(header + payload)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Cdp:
    def __init__(self, endpoint: str = "http://127.0.0.1:9222") -> None:
        self.endpoint = endpoint.rstrip("/")
        self._ws: _WS | None = None
        self._id = 0

    def connect(self) -> None:
        pages = json.loads(urllib.request.urlopen(self.endpoint + "/json/list", timeout=5).read().decode("utf-8"))
        page = next((p for p in pages if p.get("type") == "page" and p.get("webSocketDebuggerUrl")), None)
        if page is None:
            info = json.loads(urllib.request.urlopen(self.endpoint + "/json/version", timeout=5).read().decode("utf-8"))
            url = info.get("webSocketDebuggerUrl")
        else:
            url = page["webSocketDebuggerUrl"]
        if not url:
            raise CdpError("no debugger url")
        self._ws = _WS(url)

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
        if self._ws is None:
            self.connect()
        assert self._ws is not None
        self._id += 1
        msg_id = self._id
        self._ws.send_text(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            payload = json.loads(self._ws.recv_text())
            if payload.get("id") == msg_id:
                if "error" in payload:
                    raise CdpError(str(payload["error"]))
                return payload.get("result")
        raise CdpError(f"timeout {method}")

    def navigate(self, url: str) -> dict[str, Any]:
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        time.sleep(0.4)
        title = self.js("document.title")
        return {"url": url, "title": title}

    def js(self, expression: str) -> Any:
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return (result or {}).get("result", {}).get("value")

    def a11y(self) -> dict[str, Any]:
        title = self.js("document.title") or ""
        h1 = self.js("document.querySelector('h1') ? document.querySelector('h1').innerText : ''") or ""
        return {"title": title, "h1": h1}


def wait_cdp(endpoint: str = "http://127.0.0.1:9222", timeout: float = 30.0) -> Cdp:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            c = Cdp(endpoint)
            c.connect()
            return c
        except Exception as exc:
            last = exc
            time.sleep(0.3)
    raise CdpError(f"cdp not ready: {last}")
