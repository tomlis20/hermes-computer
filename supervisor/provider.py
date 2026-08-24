"""Computer provider protocol. Implementations must not be imported by the plugin."""

from __future__ import annotations

from typing import Any, Protocol

from store import Computer


class ComputerOpts:
    def __init__(
        self,
        *,
        allow_private_urls: bool = False,
        shell: bool = False,
        idle_s: int = 1800,
        image: str = "",
        network: str = "hermes-computers",
    ) -> None:
        self.allow_private_urls = allow_private_urls
        self.shell = shell
        self.idle_s = idle_s
        self.image = image
        self.network = network


class Health:
    def __init__(self, ok: bool, sandbox: str = "unknown", detail: str = "") -> None:
        self.ok = ok
        self.sandbox = sandbox
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "sandbox": self.sandbox, "detail": self.detail}


class ComputerProvider(Protocol):
    def create(self, name: str, opts: ComputerOpts) -> Computer: ...
    def start(self, name: str) -> Computer: ...
    def stop(self, name: str) -> Computer: ...
    def destroy(self, name: str) -> None: ...
    def rpc(self, name: str, req: dict[str, Any]) -> dict[str, Any]: ...
    def health(self, name: str) -> Health: ...
    def events(self, name: str, after: str = "") -> dict[str, Any]: ...
    def novnc_upstream(self, name: str) -> str: ...
