"""3D render jobs and renderer probe endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from advp import render3d
from advp.api.deps import DbSession
from advp.models import Dataset, RenderJob, SceneDocumentRow
from advp.services import projects as project_service

router = APIRouter(tags=["render3d"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _scene_or_404(session: Session, scene_id: str) -> SceneDocumentRow:
    scene = session.get(SceneDocumentRow, scene_id)
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "scene_not_found", "message": f"scene was not found: {scene_id}"},
        )
    return scene


def _job_or_404(session: Session, job_id: str) -> RenderJob:
    job = session.get(RenderJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "render_job_not_found", "message": f"job was not found: {job_id}"},
        )
    return job


def _raise_render(exc: render3d.Render3DError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/render3d/probe")
def renderer_probe() -> dict[str, Any]:
    try:
        return render3d.probe_renderer()
    except render3d.Render3DError as exc:
        _raise_render(exc)


@router.post("/scenes/{scene_id}/render")
def create_render(
    scene_id: str,
    payload: dict[str, Any],
    session: DbSession,
) -> dict[str, Any]:
    scene = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, scene.dataset_id)
    try:
        job = render3d.create_render_job(
            session,
            scene,
            dataset,
            mode=payload.get("mode"),
            width=int(payload.get("width") or 1280),
            height=int(payload.get("height") or 720),
            isovalue=float(payload.get("isovalue") or 0.5),
            volume=int(payload.get("volume") or 0),
            animation=payload.get("animation")
            if isinstance(payload.get("animation"), dict)
            else None,
        )
    except (render3d.Render3DError, ValueError) as exc:
        if isinstance(exc, render3d.Render3DError):
            _raise_render(exc)
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_render_options", "message": str(exc)},
        ) from exc
    return render3d.job_detail(job)


@router.get("/scenes/{scene_id}/render-jobs")
def list_render_jobs(scene_id: str, session: DbSession) -> list[dict[str, Any]]:
    _scene_or_404(session, scene_id)
    from sqlalchemy import select

    rows = list(
        session.scalars(
            select(RenderJob)
            .where(RenderJob.scene_id == scene_id)
            .order_by(RenderJob.created_at.desc())
            .limit(20)
        ).all()
    )
    return [render3d.job_detail(row) for row in rows]


@router.get("/render-jobs/{job_id}")
def get_render_job(job_id: str, session: DbSession) -> dict[str, Any]:
    return render3d.job_detail(_job_or_404(session, job_id))


@router.post("/render-jobs/{job_id}/cancel")
def cancel_render_job(job_id: str, session: DbSession) -> dict[str, Any]:
    return render3d.job_detail(render3d.cancel_render_job(session, _job_or_404(session, job_id)))


@router.get("/render-jobs/{job_id}/download")
def download_render_job(job_id: str, session: DbSession) -> FileResponse:
    job = _job_or_404(session, job_id)
    try:
        path = render3d.output_path(job)
    except render3d.Render3DError as exc:
        _raise_render(exc)
    return FileResponse(path, filename=f"advp-{job.id}{path.suffix}")
