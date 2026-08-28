"""Docker CLI provider. Supervisor process only — never imported by the plugin."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from provider import ComputerOpts, Health
from store import Computer, Store


class DockerProvider:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.image = os.environ.get("COMPUTER_IMAGE", "ghcr.io/tomlis20/hermes-computer:v0.1.2")
        self.network = os.environ.get("COMPUTER_NETWORK", "hermes-computers")
        self.prefix = os.environ.get("COMPUTER_CONTAINER_PREFIX", "hermes-computer-")
        # docker.sock bind mounts are host paths
        self.host_data = os.environ.get(
            "COMPUTER_HOST_DATA_DIR",
            os.environ.get("COMPUTER_DATA_DIR", "/var/lib/hermes-computer"),
        )

    def _cname(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
        if check and proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"docker_failed:{proc.returncode}:{err[:800]}")
        return proc

    def create(self, name: str, opts: ComputerOpts) -> Computer:
        token = secrets.token_hex(16)
        self.store.home_dir(name)
        host_home = f"{self.host_data.rstrip('/')}/homes/{name}"
        cname = self._cname(name)
        image = opts.image or self.image
        network = opts.network or self.network
        self._run(["docker", "rm", "-f", cname], check=False)
        args = [
            "docker",
            "run",
            "-d",
            "--name",
            cname,
            "--label",
            "hermes.computer=1",
            "--label",
            f"hermes.computer.name={name}",
            "--network",
            network,
            "--shm-size=1g",
            "--sysctl",
            "net.ipv4.ip_forward=0",
            "-e",
            f"AGENTD_TOKEN={token}",
            "-e",
            f"AGENTD_ALLOW_PRIVATE={'1' if opts.allow_private_urls else '0'}",
            "-e",
            f"AGENTD_SHELL={'1' if opts.shell else '0'}",
            "-v",
            f"{host_home}:/home/agent/chrome",
            image,
        ]
        self._run(args)
        rec = Computer(
            name=name,
            status="running",
            created_at=time.time(),
            agentd_token=token,
            extra={"allow_private_urls": opts.allow_private_urls, "shell": opts.shell},
        )
        return self.store.put(rec)

    def start(self, name: str) -> Computer:
        rec = self.store.get(name)
        if rec is None:
            raise KeyError(name)
        self._run(["docker", "start", self._cname(name)])
        rec.status = "running"
        return self.store.put(rec)

    def stop(self, name: str) -> Computer:
        rec = self.store.get(name)
        if rec is None:
            raise KeyError(name)
        self._run(["docker", "stop", self._cname(name)], check=False)
        rec.status = "stopped"
        return self.store.put(rec)

    def destroy(self, name: str) -> None:
        self._run(["docker", "rm", "-f", self._cname(name)], check=False)
        rec = self.store.get(name)
        if rec:
            rec.status = "destroyed"
            self.store.put(rec)

    def _agentd(self, name: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        rec = self.store.get(name)
        if rec is None:
            return {"ok": False, "error": "missing"}
        url = f"http://{self._cname(name)}:9377{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {rec.agentd_token}")
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {"ok": False, "error": f"agentd_http_{exc.code}"}
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"agentd_unreachable:{exc.reason}"}

    def rpc(self, name: str, req: dict[str, Any]) -> dict[str, Any]:
        return self._agentd(name, "POST", "/rpc", req)

    def events(self, name: str, after: str = "") -> dict[str, Any]:
        q = f"?after={after}" if after else ""
        return self._agentd(name, "GET", f"/events{q}")

    def health(self, name: str) -> Health:
        data = self._agentd(name, "GET", "/health")
        ok = bool(data.get("ok"))
        sandbox = str(data.get("sandbox") or "unknown")
        rec = self.store.get(name)
        if rec:
            rec.sandbox = sandbox
            self.store.put(rec)
        return Health(ok, sandbox, "" if ok else str(data.get("error") or "down"))

    def novnc_upstream(self, name: str) -> str:
        return f"http://{self._cname(name)}:6080/"
