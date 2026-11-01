"""3D geometry payload endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from advp import geometry3d
from advp import imaging as imaging_service
from advp.api.deps import DbSession
from advp.models import Dataset
from advp.services import projects as project_service

router = APIRouter(prefix="/datasets", tags=["geometry3d"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _raise_geometry(exc: geometry3d.GeometryError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _raise_imaging(exc: imaging_service.ImagingError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/{dataset_id}/3d/geometry")
def get_geometry(
    dataset_id: str,
    session: DbSession,
    mode: str = Query(default="points"),
    x: str | None = None,
    y: str | None = None,
    z: str | None = None,
    value: str | None = None,
    axis: int = Query(default=0, ge=0, le=3),
    index: int = Query(default=0, ge=0),
    volume: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        return geometry3d.build_geometry(
            dataset,
            mode=mode,
            x_field=x,
            y_field=y,
            z_field=z,
            value_field=value,
            axis=axis,
            index=index,
            volume=volume,
        )
    except geometry3d.GeometryError as exc:
        _raise_geometry(exc)


@router.get("/{dataset_id}/3d/volume")
def get_volume_sample(
    dataset_id: str,
    session: DbSession,
    max_elements: int = Query(default=imaging_service.VOLUME_SAMPLE_LIMIT, ge=1, le=50_000_000),
    volume: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        return imaging_service.read_sampled_volume(
            dataset,
            max_elements=max_elements,
            volume=volume,
        )
    except imaging_service.ImagingError as exc:
        _raise_imaging(exc)
