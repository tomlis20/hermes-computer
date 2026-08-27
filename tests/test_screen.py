"""Unit tests for screen-in-chat — no network, no Docker."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agentd"))

import cdp as agentd_cdp  # noqa: E402
import main as agentd_main  # noqa: E402


def _load_plugin():
    spec = importlib.util.spec_from_file_location("hermes_computer_plugin_screen", ROOT / "__init__.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_computer_plugin_screen"] = mod
    spec.loader.exec_module(mod)
    return mod


PLUGIN = _load_plugin()


class FakeSock:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.sent = b""

    def recv(self, n: int) -> bytes:
        out, self.data = self.data[:n], self.data[n:]
        return out

    def sendall(self, raw: bytes) -> None:
        self.sent += raw

    def settimeout(self, _t: float) -> None:  # production _WS raises the read timeout
        pass


def _frame(opcode: int, payload: bytes, fin: bool = True) -> bytes:
    b1 = (0x80 if fin else 0x00) | opcode
    n = len(payload)
    if n < 126:
        return bytes([b1, n]) + payload
    if n < 65536:
        return bytes([b1, 126]) + n.to_bytes(2, "big") + payload
    return bytes([b1, 127]) + n.to_bytes(8, "big") + payload


def _ws(data: bytes) -> tuple[agentd_cdp._WS, FakeSock]:
    ws = agentd_cdp._WS.__new__(agentd_cdp._WS)
    sock = FakeSock(data)
    ws.sock = sock
    ws._buf = b""
    return ws, sock


def test_ws_fragmented_with_interleaved_ping():
    stream = (
        _frame(0x1, b"hel", fin=False)
        + _frame(0x9, b"pingme")  # control frame mid-fragment (RFC 6455)
        + _frame(0x0, b"lo wo", fin=False)
        + _frame(0x0, b"rld", fin=True)
    )
    ws, sock = _ws(stream)
    assert ws.recv_text() == "hello world"
    assert sock.sent[0] == 0x8A  # pong went out
    assert len(sock.sent) == 2 + 4 + 6  # header + mask + masked payload


def test_ws_single_frame_64bit_length():
    payload = b"x" * 70000
    ws, _ = _ws(_frame(0x1, payload))
    assert ws.recv_text() == payload.decode()


def test_ws_continuation_without_start():
    ws, _ = _ws(_frame(0x0, b"orphan", fin=True))
    with pytest.raises(agentd_cdp.CdpError):
        ws.recv_text()


def test_observe_screenshot_via_cdp():
    class StubCdp:
        def screenshot(self, fmt: str = "jpeg", quality: int = 80) -> str:
            return "ZmFrZQ=="

        def a11y(self):
            return {"title": "t", "h1": "h"}

    st = agentd_main.AgentState()
    st.cdp = StubCdp()
    out = agentd_main.handle_rpc(st, "observe", {"mode": "both"})
    assert out["screenshot_b64"] == "ZmFrZQ=="
    assert out["screenshot_format"] == "jpeg"
    assert "screenshot_path" not in out

    class BrokenCdp(StubCdp):
        def screenshot(self, fmt: str = "jpeg", quality: int = 80) -> str:
            raise RuntimeError("boom")

    st.cdp = BrokenCdp()
    out = agentd_main.handle_rpc(st, "observe", {"mode": "screenshot"})
    assert out["ok"] is True
    assert "capture_failed" in out["screenshot_error"]
    assert "screenshot_b64" not in out


def test_observe_screenshot_stub_without_cdp():
    st = agentd_main.AgentState()
    out = agentd_main.handle_rpc(st, "observe", {"mode": "screenshot"})
    assert out["screenshot_path"] == "/home/agent/events/last.png"
    assert "screenshot_b64" not in out


def test_rpc_persists_screenshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw = b"fake-jpeg-bytes"

    class Stub:
        def rpc(self, name, method, params=None):
            return {
                "ok": True,
                "screenshot_b64": base64.b64encode(raw).decode("ascii"),
                "screenshot_format": "jpeg",
            }

    monkeypatch.setattr(PLUGIN._client, "env_client", lambda: Stub())
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    out = json.loads(PLUGIN._rpc({"name": "qa", "method": "observe", "params": {"mode": "screenshot"}}))
    assert out["ok"] is True
    assert "screenshot_b64" not in out
    path = Path(out["screenshot_path"])
    assert path.is_file()
    assert path.read_bytes() == raw
    assert path.parent == tmp_path / "screenshots"
    assert path.name.startswith("computer-qa-")
    assert path.suffix == ".jpg"
    assert out["media_hint"] == f"include MEDIA:{path} in your reply to show this screenshot in chat"


def test_prune_keeps_50_newest(tmp_path: Path):
    dest = tmp_path / "screenshots"
    dest.mkdir()
    names = [f"computer-qa-20260101T{i:06d}Z.jpg" for i in range(60)]
    for n in names:
        (dest / n).write_bytes(b"x")
    (dest / "computer-other-20260101T000000Z.jpg").write_bytes(b"x")
    PLUGIN._prune_screenshots(dest, "qa")
    left = sorted(p.name for p in dest.glob("computer-qa-*.jpg"))
    assert left == sorted(names)[10:]
    assert (dest / "computer-other-20260101T000000Z.jpg").is_file()


def test_prune_ignores_sibling_slot(tmp_path: Path):
    # FIX 1: prune("qa") anchors to computer-qa-<stamp> and must never touch a
    # sibling slot whose name starts with "qa-" (e.g. qa-x), nor delete the
    # just-written qa file that a loose glob would sweep in.
    dest = tmp_path / "screenshots"
    dest.mkdir()
    siblings = [f"computer-qa-x-20260101T{i:06d}Z.jpg" for i in range(50)]
    for n in siblings:
        (dest / n).write_bytes(b"x")
    fresh = dest / "computer-qa-20260101T120000Z.jpg"
    fresh.write_bytes(b"x")
    PLUGIN._prune_screenshots(dest, "qa")
    assert fresh.is_file()  # the just-written qa file survives
    assert all((dest / n).is_file() for n in siblings)  # qa-x slot untouched

    # And genuine qa files still prune to the 50 newest, sibling slot untouched.
    other = tmp_path / "genuine"
    other.mkdir()
    for n in siblings:
        (other / n).write_bytes(b"x")
    genuine = [f"computer-qa-20260101T{i:06d}Z.jpg" for i in range(60)]
    for n in genuine:
        (other / n).write_bytes(b"x")
    PLUGIN._prune_screenshots(other, "qa")
    left = sorted(p.name for p in other.glob("computer-qa-2*.jpg"))
    assert left == sorted(genuine)[10:]
    assert all((other / n).is_file() for n in siblings)
