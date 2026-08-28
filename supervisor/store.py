"""On-disk computer records. No Docker imports."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Status = Literal["missing", "created", "running", "stopped", "destroyed"]
TRANSITIONS = {
    "created": {"running", "destroyed"},
    "running": {"stopped", "destroyed"},
    "stopped": {"running", "destroyed"},
}


@dataclass
class Computer:
    name: str
    status: str
    created_at: float
    last_rpc_at: float | None = None
    agentd_token: str = ""
    persist: bool = True
    sandbox: str = "unknown"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("agentd_token", None)
        return d


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "computers").mkdir(exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / "computers" / f"{name}.json"

    def _write(self, rec: Computer) -> None:
        path = self._path(rec.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(rec), separators=(",", ":")).encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            os.write(fd, data)
            os.close(fd)
            os.replace(tmp, path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, name: str) -> Computer | None:
        path = self._path(name)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        extra = raw.pop("extra", {}) or {}
        return Computer(**raw, extra=extra)

    def list(self) -> list[Computer]:
        out: list[Computer] = []
        for p in sorted((self.root / "computers").glob("*.json")):
            rec = self.get(p.stem)
            if rec and rec.status != "destroyed":
                out.append(rec)
        return out

    def put(self, rec: Computer) -> Computer:
        existing = self.get(rec.name)
        if existing and existing.status != rec.status:
            if existing.status == "destroyed":
                pass
            else:
                allowed = TRANSITIONS.get(existing.status, set())
                if rec.status != "destroyed" and rec.status not in allowed and rec.status != existing.status:
                    raise ValueError(f"illegal transition {existing.status}->{rec.status}")
        self._write(rec)
        return rec

    def touch_rpc(self, name: str) -> None:
        rec = self.get(name)
        if rec:
            rec.last_rpc_at = time.time()
            self._write(rec)

    def _desktop_ids(self) -> tuple[int, int]:
        def one(env: str) -> int:
            try:
                return int(os.environ.get(env, "1000"))
            except ValueError:
                return 1000

        return one("COMPUTER_DESKTOP_UID"), one("COMPUTER_DESKTOP_GID")

    def home_dir(self, name: str) -> Path:
        p = self.root / "homes" / name
        p.mkdir(parents=True, exist_ok=True)
        # The supervisor runs as root, so the dir above lands root:root. The desktop
        # container runs as uid 1000 (image/Dockerfile: useradd -m -u 1000 agent) and
        # bind-mounts this at /home/agent/chrome -- left root-owned, Chromium cannot
        # create SingletonLock and the container dies on the first spawn of a new slot.
        # Run on every call, not just on creation, so root-owned dirs self-heal.
        # Only the dir itself: profiles run to 100MB+ and this is on the ensure hot
        # path, so a slot with root-owned *contents* from a partial run still needs a
        # manual recursive chown.
        if os.geteuid() == 0:
            uid, gid = self._desktop_ids()
            try:
                os.chown(p, uid, gid)
            except OSError:
                pass
        return p

    def events_path(self, name: str) -> Path:
        p = self.root / "events"
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{name}.jsonl"
