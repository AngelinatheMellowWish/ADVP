"""Packaged local launcher: random port, one-time token, browser bootstrap."""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote


def free_port() -> int:
    """Ask the OS for an unused loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _install_root() -> Path:
    return Path(sys.executable).resolve().parent.parent


def _find_static(explicit: Path | None) -> Path | None:
    candidates = [
        explicit,
        _install_root() / "static",
        Path.cwd() / "static",
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
        Path(__file__).resolve().parents[3] / "backend" / "static",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def _find_share() -> Path | None:
    candidates = [
        _install_root() / "static-share",
        Path.cwd() / "static-share",
        Path(__file__).resolve().parents[3] / "frontend" / "dist-share",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "share-plotly.js").is_file():
            return candidate.resolve()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="advp-launcher")
    parser.add_argument("--port", type=int, default=0, help="0 chooses a free port")
    parser.add_argument("--static-dir", type=Path, help="frontend build directory")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    port = args.port or free_port()
    token = secrets.token_urlsafe(32)
    os.environ["ADVP_HOST"] = "127.0.0.1"
    os.environ["ADVP_PORT"] = str(port)
    os.environ["ADVP_AUTH_TOKEN"] = token
    os.environ["ADVP_ALLOW_SHUTDOWN"] = "1"
    static = _find_static(args.static_dir)
    if static is not None:
        os.environ["ADVP_STATIC_DIR"] = str(static)
    share = _find_share()
    if share is not None:
        os.environ["ADVP_SHARE_DIR"] = str(share)

    url = f"http://127.0.0.1:{port}/?token={quote(token)}"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    import uvicorn

    from advp import lifecycle

    server = uvicorn.Server(
        uvicorn.Config(
            "advp.main:app",
            host="127.0.0.1",
            port=port,
            reload=False,
        )
    )
    lifecycle.configure_shutdown(
        enabled=True,
        mode="launcher",
        callback=lambda: setattr(server, "should_exit", True),
    )
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
