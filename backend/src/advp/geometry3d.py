"""3D geometry payloads and LOD sampling for VTK.js and server renderers."""

from __future__ import annotations

import math
from typing import Any

from advp import imaging as imaging_service
from advp.config import get_settings
from advp.eu2_settings import runtime_setting
from advp.ingest.files import read_preview
from advp.models import Dataset

POINT_LIMIT = 100_000
VOLUME_INLINE_LIMIT = 2_000_000


class GeometryError(Exception):
    """3D geometry cannot be produced for the dataset."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def build_geometry(
    dataset: Dataset,
    *,
    mode: str,
    x_field: str | None = None,
    y_field: str | None = None,
    z_field: str | None = None,
    value_field: str | None = None,
    axis: int = 0,
    index: int = 0,
    volume: int = 0,
) -> dict[str, Any]:
    """Build a 3D payload for points, surface, slice, volume, or isosurface."""
    if mode not in {"points", "surface", "slice", "volume", "isosurface"}:
        raise GeometryError("invalid_geometry", f"unsupported 3D mode {mode!r}")
    if mode in {"points", "surface"}:
        if dataset.kind != "table":
            raise GeometryError("geometry_kind_mismatch", f"{mode} requires a table dataset")
        return _points_payload(
            dataset,
            mode=mode,
            x_field=x_field,
            y_field=y_field,
            z_field=z_field,
            value_field=value_field,
        )
    if dataset.kind != "array":
        raise GeometryError("geometry_kind_mismatch", f"{mode} requires an array dataset")
    if mode == "slice":
        return _slice_payload(dataset, axis=axis, index=index, volume=volume)
    if mode in {"volume", "isosurface"}:
        return _volume_payload(dataset, mode=mode, volume=volume)
    raise GeometryError("invalid_geometry", f"unsupported 3D mode {mode!r}")


def _points_payload(
    dataset: Dataset,
    *,
    mode: str,
    x_field: str | None,
    y_field: str | None,
    z_field: str | None,
    value_field: str | None,
) -> dict[str, Any]:
    columns = [
        str(column.get("name"))
        for column in (dataset.schema_json or {}).get("columns", [])
        if isinstance(column, dict)
        and column.get("name")
        and column.get("semantic_type") in {"integer", "number", "duration"}
    ]
    if len(columns) < 2:
        raise GeometryError(
            "insufficient_numeric_fields",
            "3D points require at least two numeric columns",
        )
    x_field = x_field or columns[0]
    y_field = y_field or columns[1]
    z_field = z_field or (columns[2] if len(columns) >= 3 else None)
    value_field = value_field or (columns[3] if len(columns) >= 4 else None)
    available = {
        str(column.get("name"))
        for column in (dataset.schema_json or {}).get("columns", [])
        if isinstance(column, dict)
    }
    for name in (x_field, y_field, z_field, value_field):
        if name and name not in available:
            raise GeometryError("unknown_field", f"field {name!r} does not exist")

    settings = get_settings()
    render_rows = int(runtime_setting(settings, "render_sample_rows"))
    rows = read_preview(
        dataset.source_path,
        dataset.options,
        limit=render_rows,
        offset=0,
        max_file_bytes=settings.max_file_bytes,
        schema=dataset.schema_json,
        max_limit=render_rows,
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        x_value = _number(row.get(x_field))
        y_value = _number(row.get(y_field))
        z_value = _number(row.get(z_field)) if z_field else 0.0
        if x_value is None or y_value is None or z_value is None:
            continue
        item: dict[str, Any] = {"position": [x_value, y_value, z_value]}
        if value_field:
            value = _number(row.get(value_field))
            if value is not None:
                item["value"] = value
        points.append(item)
    if not points:
        raise GeometryError("empty_geometry", "no rows contain valid 3D coordinates")

    source_points = len(points)
    target = min(POINT_LIMIT, max(1, len(points)))
    stride = max(1, math.ceil(len(points) / target))
    display = points[::stride]
    values = [item["value"] for item in display if "value" in item]
    return {
        "mode": mode,
        "dataset_id": dataset.id,
        "fields": {
            "x": x_field,
            "y": y_field,
            "z": z_field,
            "value": value_field,
        },
        "source_shape": [dataset.row_count],
        "display_shape": [len(display)],
        "sampled": dataset.sampled or stride > 1 or source_points < dataset.row_count,
        "lod": stride,
        "points": display,
        "range": [min(values), max(values)] if values else None,
        "unit": None,
    }


def _slice_payload(
    dataset: Dataset,
    *,
    axis: int,
    index: int,
    volume: int,
) -> dict[str, Any]:
    try:
        result = imaging_service.read_slice(
            dataset,
            axis=axis,
            index=index,
            volume=volume,
        )
    except imaging_service.ImagingError as exc:
        raise GeometryError(exc.code, str(exc), exc.status_code) from exc
    return {
        "mode": "slice",
        "dataset_id": dataset.id,
        "axis": result["axis"],
        "index": result["index"],
        "axis_name": result["axis_name"],
        "rows": result["rows"],
        "cols": result["cols"],
        "values": result["values"],
        "range": [result["vmin"], result["vmax"]],
        "source_shape": result["shape"],
        "display_shape": [result["rows"], result["cols"]],
        "sampled": dataset.sampled,
        "lod": 1,
    }


def _volume_payload(dataset: Dataset, *, mode: str, volume: int) -> dict[str, Any]:
    schema = dataset.schema_json or {}
    shape = [int(size) for size in schema.get("shape", [])]
    if len(shape) not in (2, 3, 4):
        raise GeometryError("invalid_geometry", "volume requires a 2D-4D array")
    settings = get_settings()
    max_elements = min(
        max(1, settings.three_d_max_elements),
        VOLUME_INLINE_LIMIT,
    )
    try:
        sampled = imaging_service.read_sampled_volume(
            dataset,
            max_elements=max_elements,
            volume=volume,
        )
    except imaging_service.ImagingError as exc:
        raise GeometryError(exc.code, str(exc), exc.status_code) from exc
    stats = (dataset.profile_json.get("array") or {}).get("stats") or {}
    value_range = sampled.get("range") or []
    if not value_range or value_range[0] is None or value_range[1] is None:
        value_range = [stats.get("min"), stats.get("max")]
    return {
        "mode": mode,
        "dataset_id": dataset.id,
        "variable": sampled["variable"],
        "shape": sampled["shape"],
        "source_shape": sampled["source_shape"],
        "dims": sampled["dims"],
        "dtype": sampled["dtype"],
        "units": sampled["units"],
        "spacing": sampled["spacing"],
        "origin": sampled["origin"],
        "range": value_range,
        "display_shape": sampled["display_shape"],
        "sampled": sampled["sampled"],
        "lod": sampled["lod"],
        "volume": sampled["volume"],
        "volume_count": sampled["volume_count"],
        "values": sampled["values"],
    }


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
