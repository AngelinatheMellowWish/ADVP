"""trame SciView session endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from advp import trame3d
from advp.api.deps import DbSession
from advp.models import Dataset, SceneDocumentRow
from advp.services import projects as project_service

router = APIRouter(tags=["trame"])


def _scene_or_404(session: Session, scene_id: str) -> SceneDocumentRow:
    scene = session.get(SceneDocumentRow, scene_id)
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "scene_not_found", "message": f"scene was not found: {scene_id}"},
        )
    return scene


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _raise_trame(exc: trame3d.TrameError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/scenes/{scene_id}/trame")
def start_trame(scene_id: str, session: DbSession) -> dict[str, Any]:
    scene = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, scene.dataset_id)
    try:
        created = trame3d.start_session(scene, dataset)
    except trame3d.TrameError as exc:
        _raise_trame(exc)
    return trame3d.detail(created)


@router.get("/trame/{session_id}")
def get_trame(session_id: str) -> dict[str, Any]:
    try:
        return trame3d.detail(trame3d.get_session(session_id))
    except trame3d.TrameError as exc:
        _raise_trame(exc)


@router.delete("/trame/{session_id}")
def stop_trame(session_id: str) -> dict[str, Any]:
    try:
        trame3d.get_session(session_id)
    except trame3d.TrameError as exc:
        _raise_trame(exc)
    trame3d.stop_session(session_id)
    return {"stopped": True, "session_id": session_id}
