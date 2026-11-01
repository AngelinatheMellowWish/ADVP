"""Spawn and track independent VTK/Mayavi 3D render jobs."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import geometry3d
from advp.config import get_settings
from advp.db import get_session
from advp.models import Dataset, RenderJob, SceneDocumentRow

WORKER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "render3d_worker.py"
RUNNING: dict[str, subprocess.Popen[str]] = {}
LOCK = threading.Lock()
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True)
class VtkTransferFunction:
    """Renderer-neutral transfer function ready for the VTK worker."""

    color_points: tuple[tuple[float, float, float, float], ...]
    opacity_points: tuple[tuple[float, float], ...]
    interpolation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "colorPoints": [
                {"x": x, "rgb": [red, green, blue]} for x, red, green, blue in self.color_points
            ],
            "opacityPoints": [{"x": x, "opacity": opacity} for x, opacity in self.opacity_points],
            "interpolation": self.interpolation,
        }


def build_vtk_transfer_function(scene: dict[str, Any]) -> VtkTransferFunction:
    """Map Scene JSON 1.1 color/opacity points to normalized RGB curves."""
    transfer = scene.get("transferFunction") or {}
    raw_colors = transfer.get("colorPoints") or [
        {"x": 0.0, "color": "#000000"},
        {"x": 1.0, "color": "#ffffff"},
    ]
    raw_opacities = transfer.get("opacityPoints") or [
        {"x": 0.0, "opacity": 0.0},
        {"x": 1.0, "opacity": 1.0},
    ]
    colors: list[tuple[float, float, float, float]] = []
    for point in raw_colors:
        x = float(point.get("x", 0))
        color = str(point.get("color", "#000000"))
        if not HEX_COLOR.match(color):
            raise Render3DError("invalid_transfer_function", f"invalid color: {color}")
        colors.append(
            (
                x,
                int(color[1:3], 16) / 255,
                int(color[3:5], 16) / 255,
                int(color[5:7], 16) / 255,
            )
        )
    opacities: list[tuple[float, float]] = []
    for point in raw_opacities:
        opacities.append((float(point.get("x", 0)), float(point.get("opacity", 0))))
    colors.sort(key=lambda item: item[0])
    opacities.sort(key=lambda item: item[0])
    if len(colors) < 2 or len(opacities) < 2:
        raise Render3DError(
            "invalid_transfer_function",
            "transfer functions require at least two color and opacity points",
        )
    for curve in (colors, opacities):
        if any(left[0] >= right[0] for left, right in zip(curve, curve[1:], strict=False)):
            raise Render3DError(
                "invalid_transfer_function",
                "transfer points must be strictly increasing",
            )
    interpolation = str(transfer.get("interpolation") or "linear")
    if interpolation not in {"linear", "smooth"}:
        raise Render3DError(
            "invalid_transfer_function",
            f"unsupported interpolation: {interpolation}",
        )
    return VtkTransferFunction(
        color_points=tuple(colors),
        opacity_points=tuple(opacities),
        interpolation=interpolation,
    )


class Render3DError(Exception):
    """A 3D render job cannot be created or executed."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def renderer_python() -> Path:
    settings = get_settings()
    if settings.render_python:
        path = Path(settings.render_python).expanduser()
        if path.is_file():
            return path
        raise Render3DError(
            "renderer_unavailable",
            f"ADVP_RENDER_PYTHON does not exist: {path}",
            503,
        )
    candidates = [
        Path(__file__).resolve().parents[2] / ".venv-3d" / "Scripts" / "python.exe",
        Path(__file__).resolve().parents[2] / ".venv-3d" / "bin" / "python",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise Render3DError(
        "renderer_unavailable",
        "no 3D renderer Python is configured; set ADVP_RENDER_PYTHON",
        503,
    )


def probe_renderer() -> dict[str, Any]:
    python = renderer_python()
    if not WORKER_PATH.is_file():
        raise Render3DError("renderer_unavailable", "render3d_worker.py is missing", 503)
    result = subprocess.run(
        [str(python), str(WORKER_PATH), "--probe"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        payload: dict[str, Any] = dict(json.loads(result.stdout.strip().splitlines()[-1]))
    except (IndexError, json.JSONDecodeError, TypeError) as exc:
        raise Render3DError(
            "renderer_probe_failed",
            result.stderr.strip() or "renderer probe returned no JSON",
            503,
        ) from exc
    if not payload.get("ok"):
        raise Render3DError(
            "renderer_probe_failed",
            str(payload.get("vtk_error") or "renderer probe failed"),
            503,
        )
    return payload


def create_render_job(
    session: Session,
    scene: SceneDocumentRow,
    dataset: Dataset,
    *,
    mode: str | None = None,
    width: int = 1280,
    height: int = 720,
    isovalue: float = 0.5,
    volume: int = 0,
    animation: dict[str, Any] | None = None,
) -> RenderJob:
    settings = get_settings()
    scene_json = scene.scene_json or {}
    transfer_function = build_vtk_transfer_function(scene_json).to_dict()
    geometry_type = mode or str((scene_json.get("geometry") or {}).get("type") or "points")
    scene_animation = scene_json.get("animation") or {}
    animation_payload = {**scene_animation, **(animation or {})}
    try:
        geometry = geometry3d.build_geometry(
            dataset,
            mode=geometry_type,
            axis=int((scene_json.get("geometry") or {}).get("axis") or 0),
            index=int((scene_json.get("geometry") or {}).get("index") or 0),
            volume=volume,
        )
    except geometry3d.GeometryError as exc:
        raise Render3DError(exc.code, str(exc), exc.status_code) from exc
    job_id = uuid.uuid4().hex
    output_dir = settings.workspace_dir / "exports" / "3d" / dataset.project_id / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    job_payload = {
        "scene": scene_json,
        "geometry": geometry,
        "transferFunction": transfer_function,
        "output_dir": str(output_dir),
        "result_path": str(output_dir / "result.json"),
        "width": width,
        "height": height,
        "isovalue": isovalue,
        "animation": animation_payload,
    }
    job_path = output_dir / "job.json"
    job_path.write_text(json.dumps(job_payload, ensure_ascii=False), encoding="utf-8")
    renderer_version = _renderer_version()
    cache_key = _cache_key(
        dataset.source_sha256,
        scene.scene_hash,
        geometry_type,
        width,
        height,
        isovalue,
        volume,
        json.dumps(animation_payload, ensure_ascii=False, sort_keys=True),
        renderer_version,
    )
    cache_path = settings.workspace_dir / "exports" / "3d" / "cache" / f"{cache_key}.png"
    cached = cache_path.is_file()
    row = RenderJob(
        id=job_id,
        scene_id=scene.id,
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        status="succeeded" if cached else "pending",
        mode=geometry_type,
        options_json={
            "job_path": str(job_path),
            "output_dir": str(output_dir),
            "result_path": str(output_dir / "result.json"),
            "width": width,
            "height": height,
            "isovalue": isovalue,
            "volume": volume,
            "animation": animation_payload,
            "cache_key": cache_key,
            "cache_path": str(cache_path),
        },
        output_json=(
            {
                "ok": True,
                "outputs": [
                    {"kind": "png", "path": str(cache_path), "bytes": cache_path.stat().st_size}
                ],
                "cached": True,
            }
            if cached
            else {}
        ),
        progress=100 if cached else 0,
        finished_at=datetime.now(UTC) if cached else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    if not cached:
        thread = threading.Thread(
            target=execute_render_job,
            args=(job_id,),
            daemon=True,
            name=f"advp-render3d-{job_id[:8]}",
        )
        thread.start()
    return row


def execute_render_job(job_id: str) -> None:
    session = get_session()
    try:
        job = session.get(RenderJob, job_id)
        if job is None:
            return
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            session.commit()
            return
        job.status = "running"
        job.progress = 5
        job.started_at = datetime.now(UTC)
        session.commit()
        try:
            python = renderer_python()
            options = job.options_json or {}
            process = subprocess.Popen(
                [str(python), str(WORKER_PATH), "--job", str(options.get("job_path"))],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with LOCK:
                RUNNING[job_id] = process
            job.progress = 25
            session.commit()
            try:
                stdout, stderr = process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise Render3DError(
                    "render_timeout",
                    "3D render exceeded 600 seconds",
                ) from None
            finally:
                with LOCK:
                    RUNNING.pop(job_id, None)
            session.refresh(job)
            if job.cancel_requested:
                job.status = "cancelled"
                job.finished_at = datetime.now(UTC)
                session.commit()
                return
            result = _read_result(options.get("result_path"), stdout)
            if not result.get("ok"):
                raise Render3DError(
                    "render_failed",
                    str(result.get("error") or stderr.strip() or "renderer failed"),
                )
            outputs = result.get("outputs") or []
            _cache_first_png(options, outputs)
            job.status = "succeeded"
            job.progress = 100
            job.output_json = result
            job.finished_at = datetime.now(UTC)
            session.commit()
        except (Render3DError, OSError, ValueError) as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            session.commit()
    finally:
        session.close()


def recover_jobs(session: Session, *, requeue_pending: bool = True) -> dict[str, int]:
    """Recover render jobs orphaned by a process restart.

    Running jobs have lost their worker process and are marked failed. Pending
    jobs are re-queued when their job file survived; otherwise they are marked
    failed so clients do not poll forever.
    """
    rows = list(
        session.scalars(select(RenderJob).where(RenderJob.status.in_(["running", "pending"]))).all()
    )
    failed = 0
    requeued: list[str] = []
    now = datetime.now(UTC)
    for job in rows:
        options = job.options_json or {}
        job_path = Path(str(options.get("job_path") or ""))
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = now
            failed += 1
        elif job.status == "running":
            job.status = "failed"
            job.error = "renderer process restarted before the job completed"
            job.finished_at = now
            failed += 1
        elif not requeue_pending:
            continue
        elif job_path.is_file():
            requeued.append(job.id)
        else:
            job.status = "failed"
            job.error = "render job cannot be recovered: job file is missing"
            job.finished_at = now
            failed += 1
    session.commit()
    for job_id in requeued:
        thread = threading.Thread(
            target=execute_render_job,
            args=(job_id,),
            daemon=True,
            name=f"advp-render3d-recover-{job_id[:8]}",
        )
        thread.start()
    return {
        "recovered": len(rows),
        "requeued": len(requeued),
        "failed": failed,
    }


def cancel_render_job(session: Session, job: RenderJob) -> RenderJob:
    job.cancel_requested = True
    if job.status in {"pending", "running"}:
        with LOCK:
            process = RUNNING.get(job.id)
            if process is not None:
                process.terminate()
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
    session.commit()
    session.refresh(job)
    return job


def job_detail(job: RenderJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "scene_id": job.scene_id,
        "dataset_id": job.dataset_id,
        "project_id": job.project_id,
        "status": job.status,
        "mode": job.mode,
        "progress": job.progress,
        "output": job.output_json,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def output_path(job: RenderJob) -> Path:
    outputs = (job.output_json or {}).get("outputs") or []
    if not outputs:
        raise Render3DError("render_output_missing", "render job has no output", 404)
    path = Path(str(outputs[0].get("path") or ""))
    workspace = get_settings().workspace_dir.resolve()
    try:
        path.resolve().relative_to(workspace)
    except ValueError as exc:
        raise Render3DError(
            "render_output_missing", "render output is outside workspace", 404
        ) from exc
    if not path.is_file():
        raise Render3DError("render_output_missing", "render output file is missing", 404)
    return path


def _renderer_version() -> str:
    try:
        probe = probe_renderer()
    except Render3DError:
        return "unknown"
    return f"vtk-{probe.get('vtk')}-mayavi-{probe.get('mayavi')}"


def _cache_key(*parts: Any) -> str:
    encoded = "|".join(str(part) for part in parts)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_result(result_path: str | None, stdout: str) -> dict[str, Any]:
    if result_path and Path(result_path).is_file():
        return dict(json.loads(Path(result_path).read_text(encoding="utf-8")))
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {"ok": False, "error": "renderer produced no result"}
    return dict(json.loads(lines[-1]))


def _cache_first_png(options: dict[str, Any], outputs: list[dict[str, Any]]) -> None:
    cache_path = options.get("cache_path")
    if not cache_path:
        return
    for output in outputs:
        if output.get("kind") == "png":
            source = Path(str(output.get("path")))
            if source.is_file():
                target = Path(str(cache_path))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            return
