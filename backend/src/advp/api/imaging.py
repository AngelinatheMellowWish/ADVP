"""Imaging metadata and slice endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from advp import imaging as imaging_service
from advp.api.deps import DbSession
from advp.models import Dataset
from advp.services import projects as project_service

router = APIRouter(prefix="/datasets", tags=["imaging"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _raise_imaging(exc: imaging_service.ImagingError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/{dataset_id}/imaging/meta")
def get_imaging_meta(dataset_id: str, session: DbSession) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        return imaging_service.imaging_meta(dataset)
    except imaging_service.ImagingError as exc:
        _raise_imaging(exc)


@router.get("/{dataset_id}/imaging/slice")
def get_imaging_slice(
    dataset_id: str,
    session: DbSession,
    axis: int = Query(default=0, ge=0, le=3),
    index: int = Query(default=0, ge=0),
    volume: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        return imaging_service.read_slice(dataset, axis=axis, index=index, volume=volume)
    except imaging_service.ImagingError as exc:
        _raise_imaging(exc)
