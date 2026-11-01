"""Manage isolated trame SciView sessions."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from advp import geometry3d, render3d
from advp.config import get_settings
from advp.models import Dataset, SceneDocumentRow

TRAME_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "trame_viewer.py"


class TrameError(Exception):
    """A trame SciView session cannot be started."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class TrameSession:
    id: str
    scene_id: str
    dataset_id: str
    port: int
    token: str
    url: str
    process: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


SESSIONS: dict[str, TrameSession] = {}
LOCK = threading.Lock()


def start_session(scene: SceneDocumentRow, dataset: Dataset) -> TrameSession:
    cleanup()
    python = render3d.renderer_python()
    if not TRAME_SCRIPT.is_file():
        raise TrameError("trame_unavailable", "trame_viewer.py is missing")
    scene_json = scene.scene_json or {}
    geometry_type = str((scene_json.get("geometry") or {}).get("type") or "volume")
    try:
        geometry = geometry3d.build_geometry(
            dataset,
            mode=geometry_type
            if geometry_type in {"points", "surface", "slice", "volume", "isosurface"}
            else "volume",
            axis=int((scene_json.get("geometry") or {}).get("axis") or 0),
            index=int((scene_json.get("geometry") or {}).get("index") or 0),
        )
    except geometry3d.GeometryError as exc:
        raise TrameError(exc.code, str(exc), exc.status_code) from exc
    settings = get_settings()
    session_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    port = _free_port()
    output_dir = settings.workspace_dir / "exports" / "3d" / "trame" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    job_path = output_dir / "scene.json"
    job_path.write_text(
        json.dumps({"scene": scene_json, "geometry": geometry}, ensure_ascii=False),
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [
            str(python),
            str(TRAME_SCRIPT),
            "--scene",
            str(job_path),
            "--port",
            str(port),
            "--token",
            token,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not _wait_port(port, timeout=20.0):
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stderr = ""
        raise TrameError(
            "trame_unavailable",
            stderr.strip() or "trame session did not start",
        )
    session = TrameSession(
        id=session_id,
        scene_id=scene.id,
        dataset_id=dataset.id,
        port=port,
        token=token,
        url=f"http://127.0.0.1:{port}/?token={token}",
        process=process,
    )
    with LOCK:
        SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> TrameSession:
    with LOCK:
        session = SESSIONS.get(session_id)
    if session is None:
        raise TrameError("trame_session_not_found", "trame session was not found", 404)
    return session


def stop_session(session_id: str) -> None:
    with LOCK:
        session = SESSIONS.pop(session_id, None)
    if session is not None:
        _terminate(session)


def detail(session: TrameSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "scene_id": session.scene_id,
        "dataset_id": session.dataset_id,
        "url": session.url,
        "port": session.port,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def cleanup(ttl_seconds: float = 1800.0) -> None:
    now = time.time()
    expired: list[TrameSession] = []
    with LOCK:
        for session_id, session in list(SESSIONS.items()):
            if now - session.updated_at > ttl_seconds or session.process.poll() is not None:
                expired.append(session)
                SESSIONS.pop(session_id, None)
    for session in expired:
        _terminate(session)


def _terminate(session: TrameSession) -> None:
    if session.process.poll() is None:
        session.process.terminate()
        try:
            session.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            session.process.kill()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False
