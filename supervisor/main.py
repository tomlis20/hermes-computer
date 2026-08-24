"""Supervisor entrypoint. Binds Hermes-facing / loopback only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from fake_provider import FakeProvider  # noqa: E402
from http_app import serve  # noqa: E402
from provider import ComputerOpts  # noqa: E402
from store import Store  # noqa: E402


def build_ctx() -> dict:
    data = Path(os.environ.get("COMPUTER_DATA_DIR", str(ROOT / "var")))
    store = Store(data)
    provider_name = os.environ.get("COMPUTER_PROVIDER", "docker")
    if provider_name == "fake":
        provider = FakeProvider(store)
    else:
        from docker_provider import DockerProvider

        provider = DockerProvider(store)
    deny = os.environ.get("COMPUTER_DENY_CIDRS", "")
    cidrs = [c.strip() for c in deny.split(",") if c.strip()]
    # Default: typical Docker bridge ranges for hermes-computers if set.
    extra = os.environ.get("COMPUTER_NETWORK_CIDR", "").strip()
    if extra:
        cidrs.append(extra)
    return {
        "store": store,
        "provider": provider,
        "secret": os.environ["COMPUTER_SUPERVISOR_TOKEN"],
        "default_opts": ComputerOpts(
            allow_private_urls=os.environ.get("COMPUTER_ALLOW_PRIVATE", "") == "1",
            shell=os.environ.get("COMPUTER_SHELL", "") == "1",
            idle_s=int(os.environ.get("COMPUTER_IDLE_S", "1800")),
            image=os.environ.get("COMPUTER_IMAGE", "ghcr.io/tomlis20/hermes-computer:v0.1.0"),
            network=os.environ.get("COMPUTER_NETWORK", "hermes-computers"),
        ),
        "deny_cidrs": cidrs,
        "public_base": os.environ.get("COMPUTER_PUBLIC_BASE", "http://127.0.0.1:9376"),
        "sandbox_default": "seccomp",
    }


def main() -> None:
    if not os.environ.get("COMPUTER_SUPERVISOR_TOKEN"):
        print("COMPUTER_SUPERVISOR_TOKEN is required", file=sys.stderr)
        sys.exit(2)
    host = os.environ.get("COMPUTER_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("COMPUTER_BIND_PORT", "9376"))
    ctx = build_ctx()
    httpd = serve(ctx, host=host, port=port)
    print(f"hermes-computer supervisor on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
