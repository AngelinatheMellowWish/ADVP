"""Scene JSON persistence and validation endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from advp import code_export
from advp import scene as scene_service
from advp.api.deps import DbSession
from advp.models import Dataset, SceneDocumentRow
from advp.services import projects as project_service

router = APIRouter(tags=["scenes"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _scene_or_404(session: Session, scene_id: str) -> SceneDocumentRow:
    row = session.get(SceneDocumentRow, scene_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "scene_not_found", "message": f"scene was not found: {scene_id}"},
        )
    return row


def _raise_scene(exc: scene_service.SceneError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _detail(row: SceneDocumentRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "project_id": row.project_id,
        "version": row.version,
        "scene": row.scene_json,
        "scene_hash": row.scene_hash,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("/datasets/{dataset_id}/scenes")
def create_scene(
    dataset_id: str,
    payload: dict[str, Any],
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        scene = scene_service.normalize_scene(payload, dataset)
    except scene_service.SceneError as exc:
        _raise_scene(exc)
    row = SceneDocumentRow(
        id=uuid.uuid4().hex,
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        version=scene.version,
        scene_json=scene.model_dump(),
        scene_hash=scene_service.scene_hash(scene),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _detail(row)


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: str, session: DbSession) -> dict[str, Any]:
    return _detail(_scene_or_404(session, scene_id))


@router.patch("/scenes/{scene_id}")
def update_scene(
    scene_id: str,
    payload: dict[str, Any],
    session: DbSession,
) -> dict[str, Any]:
    row = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, row.dataset_id)
    try:
        scene = scene_service.normalize_scene(payload, dataset)
    except scene_service.SceneError as exc:
        _raise_scene(exc)
    row.version = scene.version
    row.scene_json = scene.model_dump()
    row.scene_hash = scene_service.scene_hash(scene)
    row.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    return _detail(row)


@router.post("/scenes/{scene_id}/validate")
def validate_scene(scene_id: str, session: DbSession) -> dict[str, Any]:
    row = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, row.dataset_id)
    try:
        scene = scene_service.normalize_scene(row.scene_json, dataset)
    except scene_service.SceneError as exc:
        _raise_scene(exc)
    return {
        "valid": True,
        "scene": scene.model_dump(),
        "manifest": scene_service.scene_manifest(scene, dataset),
    }


@router.get("/scenes/{scene_id}/manifest")
def get_scene_manifest(scene_id: str, session: DbSession) -> dict[str, Any]:
    row = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, row.dataset_id)
    scene = scene_service.SceneDocument.model_validate(row.scene_json)
    return scene_service.scene_manifest(scene, dataset)


@router.get("/scenes/{scene_id}/export/python")
def export_scene_python(scene_id: str, session: DbSession) -> Response:
    row = _scene_or_404(session, scene_id)
    dataset = _dataset_or_404(session, row.dataset_id)
    script = code_export.build_scene_python_script(dataset, row.scene_json)
    return Response(
        content=script,
        media_type="text/x-python",
        headers={
            "Content-Disposition": f'attachment; filename="advp-scene-{scene_id}.py"',
        },
    )


@router.get("/scenes/{scene_id}/export/json")
def export_scene_json(scene_id: str, session: DbSession) -> Response:
    row = _scene_or_404(session, scene_id)
    return Response(
        content=json.dumps(row.scene_json, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="advp-scene-{scene_id}.json"',
        },
    )
