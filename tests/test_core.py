"""Unit tests — no network, no Docker."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "supervisor"))
sys.path.insert(0, str(ROOT / "agentd"))

from client import (  # noqa: E402
    SupervisorClient,
    mint_takeover,
    sign_request,
    validate_name,
    verify_request,
    verify_takeover,
)
from doctor import merge_commands  # noqa: E402
from fake_provider import FakeProvider  # noqa: E402
from http_app import serve  # noqa: E402
from provider import ComputerOpts  # noqa: E402
from store import Store  # noqa: E402

import main as agentd_main  # noqa: E402


def test_validate_name():
    assert validate_name("lab") == "lab"
    with pytest.raises(ValueError):
        validate_name("")
    with pytest.raises(ValueError):
        validate_name("../x")


def test_hmac_roundtrip():
    secret = "s3cret"
    body = b'{"a":1}'
    ts, sig = sign_request(secret, "POST", "/computers/lab/rpc", body)
    assert verify_request(secret, "POST", "/computers/lab/rpc", body, ts, sig)
    assert not verify_request(secret, "GET", "/computers/lab/rpc", body, ts, sig)
    assert not verify_request(secret, "POST", "/computers/lab/rpc", body, ts, "deadbeef")
    assert not verify_request(secret, "POST", "/computers/lab/rpc", body, str(int(time.time()) - 120), sig)


def test_takeover_ttl():
    secret = "s3cret"
    tok, exp = mint_takeover(secret, "lab", ttl_s=10, now=1000)
    assert verify_takeover(secret, "lab", tok, now=1005)
    assert not verify_takeover(secret, "lab", tok, now=1011)
    assert not verify_takeover(secret, "other", tok, now=1005)
    assert not verify_takeover(secret, "lab", "nope", now=1005)


def test_store_transitions(tmp_path: Path):
    st = Store(tmp_path)
    rec = st.put(
        __import__("store", fromlist=["Computer"]).Computer(
            name="lab", status="created", created_at=1.0, agentd_token="t"
        )
    )
    rec.status = "running"
    st.put(rec)
    rec.status = "stopped"
    st.put(rec)
    rec.status = "destroyed"
    st.put(rec)
    assert st.get("lab").status == "destroyed"
    pub = st.get("lab").to_public()
    assert "agentd_token" not in pub


def test_fake_provider_flow(tmp_path: Path):
    st = Store(tmp_path)
    p = FakeProvider(st)
    rec = p.create("lab", ComputerOpts())
    rec = p.start("lab")
    assert rec.status == "running"
    nav = p.rpc("lab", {"method": "navigate", "params": {"url": "https://example.com"}})
    assert nav["ok"] is True
    obs = p.rpc("lab", {"method": "observe", "params": {"mode": "a11y"}})
    assert "Example Domain" in json.dumps(obs)
    bad = p.rpc("lab", {"method": "navigate", "params": {"url": "http://169.254.169.254/"}})
    assert bad["ok"] is False
    cap = p.rpc("lab", {"method": "navigate", "params": {"url": "https://example.com/captcha"}})
    assert cap.get("paused") is True
    blocked = p.rpc("lab", {"method": "act", "params": {"actions": []}})
    assert blocked.get("paused") is True
    p.rpc("lab", {"method": "resume", "params": {}})
    ok = p.rpc("lab", {"method": "act", "params": {"actions": []}})
    assert ok["ok"] is True


def test_supervisor_http(tmp_path: Path):
    st = Store(tmp_path)
    provider = FakeProvider(st)
    secret = "tok"
    ctx = {
        "store": st,
        "provider": provider,
        "secret": secret,
        "default_opts": ComputerOpts(),
        "deny_cidrs": ["10.200.0.0/16"],
        "public_base": "http://127.0.0.1:9376",
    }
    httpd = serve(ctx, host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        cli = SupervisorClient(f"http://127.0.0.1:{port}", secret)
        ens = cli.ensure("lab")
        assert ens["ok"] is True
        assert ens["name"] == "lab"
        assert "/novnc/" in ens["novnc_url"]
        obs = cli.rpc("lab", "navigate", {"url": "https://example.com"})
        assert obs["ok"] is True
        a11y = cli.rpc("lab", "observe", {"mode": "a11y"})
        assert a11y["ok"] is True
        # unsigned takeover
        import urllib.error
        import urllib.request

        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/computers/lab/novnc/not-a-sig/", timeout=3)
        assert ei.value.code == 403
        # signed works
        from urllib.parse import urlparse

        path = urlparse(ens["novnc_url"]).path
        urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3)
        # deny cidr: simulate by constructing handler is unit-tested via _in_nets separately
    finally:
        httpd.shutdown()


def test_deny_cidr():
    from http_app import _in_nets

    assert _in_nets("10.200.0.5", ["10.200.0.0/16"])
    assert not _in_nets("172.20.0.9", ["10.200.0.0/16"])


def test_agentd_auth_and_private():
    st = agentd_main.AgentState()
    st.token = "abc"
    st.allow_private = False
    assert agentd_main.handle_rpc(st, "navigate", {"url": "http://169.254.169.254/"})["ok"] is False
    ok = agentd_main.handle_rpc(st, "navigate", {"url": "https://example.com"})
    assert ok["ok"] is True
    paused = agentd_main.handle_rpc(st, "navigate", {"url": "https://x/captcha"})
    assert paused.get("paused") is True
    blocked = agentd_main.handle_rpc(st, "act", {"actions": []})
    assert blocked.get("paused") is True
    agentd_main.handle_rpc(st, "resume", {})
    # resume is handled in HTTP layer; simulate
    st.paused = False
    assert agentd_main.handle_rpc(st, "act", {"actions": []})["ok"] is True
    assert agentd_main.handle_rpc(st, "shell", {"cmd": "id"})["error"] == "shell_disabled"


def test_import_graph():
    spec = importlib.util.spec_from_file_location("hermes_computer_plugin", ROOT / "__init__.py")
    assert spec and spec.loader
    before = set(sys.modules)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_computer_plugin"] = mod
    spec.loader.exec_module(mod)
    added = set(sys.modules) - before
    leak = [m for m in added if m.startswith("supervisor") or m.startswith("agentd") or "docker_provider" in m]
    assert leak == []
    class Ctx:
        def __init__(self):
            self.tools = []
            self.skill = None

        def register_skill(self, name, path):
            self.skill = (name, path)

        def register_tool(self, **kw):
            self.tools.append(kw)

        def register_cli_command(self, **kw):
            return None

    ctx = Ctx()
    mod.register(ctx)
    names = [t["name"] for t in ctx.tools]
    assert "computer_ensure" in names
    assert all(t["toolset"] == "computer" for t in ctx.tools)


def test_doctor_merge_does_not_drop_existing():
    cmds = merge_commands({"cli": ["hermes-cli"], "telegram": ["hermes-telegram"]})
    assert any("hermes-cli" in c and "computer" in c for c in cmds)
    assert any("hermes-telegram" in c for c in cmds)
    assert merge_commands({"cli": ["hermes-cli", "computer"]}) == []
