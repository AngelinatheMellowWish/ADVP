"""Deterministic analysis summaries for datasets and the AI pipeline."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.ingest.files import read_preview
from advp.models import Dataset

ANALYSIS_SAMPLE_ROWS = 10_000
MAX_ANALYSIS_ROWS = 100_000
ANALYSIS_VERSION = 1


class AnalysisError(Exception):
    """The dataset cannot produce a useful analysis summary."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def cached_analysis(dataset: Dataset) -> dict[str, Any] | None:
    """Return the cached analysis block, if any."""
    analysis = (dataset.profile_json or {}).get("analysis")
    return analysis if isinstance(analysis, dict) else None


def analyze_dataset(
    dataset: Dataset,
    *,
    force: bool = False,
    sample_rows: int | None = None,
) -> dict[str, Any]:
    """Compute a bounded analysis summary from the dataset preview window."""
    if not force:
        cached = cached_analysis(dataset)
        if cached is not None:
            return cached
    if dataset.kind == "array":
        return _array_analysis(dataset)
    settings = get_settings()
    limit = sample_rows if sample_rows is not None else settings.analysis_sample_rows
    limit = min(max(limit, 1), MAX_ANALYSIS_ROWS)
    rows = read_preview(
        dataset.source_path,
        dataset.options,
        limit=limit,
        offset=0,
        max_file_bytes=settings.max_file_bytes,
        schema=dataset.schema_json,
        max_limit=limit,
    )
    if not rows:
        raise AnalysisError("empty_dataset", "the dataset has no rows to analyze")

    columns = [
        column for column in (dataset.schema_json or {}).get("columns", []) if column.get("name")
    ]
    profile_columns = {
        str(column.get("name")): column
        for column in (dataset.profile_json or {}).get("columns", [])
    }
    numeric = _numeric_analysis(rows, columns)
    correlations = _correlations(rows, numeric)
    temporal = _temporal_analysis(rows, columns)
    geo = _geo_analysis(rows, columns)
    categorical = _categorical_analysis(profile_columns)
    sampled = dataset.sampled or len(rows) < dataset.row_count
    notes = _notes(
        sample_size=len(rows),
        sampled=sampled,
        numeric=numeric,
        correlations=correlations,
        temporal=temporal,
        geo=geo,
    )
    return {
        "version": ANALYSIS_VERSION,
        "computed_at": datetime.now(UTC).isoformat(),
        "sample_size": len(rows),
        "sampled": sampled,
        "numeric_columns": numeric,
        "correlations": correlations,
        "temporal": temporal,
        "geo": geo,
        "categorical": categorical,
        "notes": notes,
        "summary": " ".join(notes),
    }


def compute_and_store(
    session: Session,
    dataset: Dataset,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Compute and persist the analysis block in the dataset profile JSON."""
    analysis = analyze_dataset(dataset, force=force)
    dataset.profile_json = {**(dataset.profile_json or {}), "analysis": analysis}
    session.commit()
    session.refresh(dataset)
    return analysis


def _numeric_analysis(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for column in columns:
        if column.get("semantic_type") not in {"integer", "number"}:
            continue
        name = str(column.get("name"))
        values = _numeric(_values(rows, name))
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            continue
        std = float(np.std(finite))
        skewness = float(np.mean(((finite - np.mean(finite)) / std) ** 3)) if std > 0 else 0.0
        result.append(
            {
                "name": name,
                "count": int(finite.size),
                "mean": round(float(np.mean(finite)), 6),
                "median": round(float(np.median(finite)), 6),
                "std": round(std, 6),
                "min": round(float(np.min(finite)), 6),
                "max": round(float(np.max(finite)), 6),
                "skewness": round(skewness, 6),
            }
        )
    return result[:20]


def _correlations(
    rows: list[dict[str, Any]],
    numeric: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = [str(item["name"]) for item in numeric]
    if len(names) < 2:
        return []
    vectors = {name: _numeric(_values(rows, name)) for name in names}
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            x = vectors[left]
            y = vectors[right]
            mask = np.isfinite(x) & np.isfinite(y)
            if int(np.count_nonzero(mask)) < 3:
                continue
            if float(np.std(x[mask])) == 0 or float(np.std(y[mask])) == 0:
                continue
            coefficient = float(np.corrcoef(x[mask], y[mask])[0, 1])
            if not math.isfinite(coefficient) or abs(coefficient) < 0.5:
                continue
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "r": round(coefficient, 4),
                    "strength": "strong" if abs(coefficient) >= 0.75 else "moderate",
                }
            )
    pairs.sort(key=lambda item: abs(item["r"]), reverse=True)
    return pairs[:10]


def _temporal_analysis(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for column in columns:
        if column.get("semantic_type") not in {"datetime", "date", "time"}:
            continue
        name = str(column.get("name"))
        parsed = []
        for value in _values(rows, name):
            moment = _parse_datetime(value)
            if moment is not None:
                parsed.append(moment)
        if len(parsed) < 2:
            continue
        parsed.sort()
        gaps = [
            (parsed[index + 1] - parsed[index]).total_seconds() for index in range(len(parsed) - 1)
        ]
        finite_gaps = [gap for gap in gaps if gap >= 0]
        result.append(
            {
                "name": name,
                "count": len(parsed),
                "start": parsed[0].isoformat(),
                "end": parsed[-1].isoformat(),
                "span_seconds": round((parsed[-1] - parsed[0]).total_seconds(), 3),
                "median_gap_seconds": (
                    round(float(np.median(finite_gaps)), 3) if finite_gaps else None
                ),
                "max_gap_seconds": round(max(finite_gaps), 3) if finite_gaps else None,
            }
        )
    return result[:10]


def _geo_analysis(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> dict[str, Any] | None:
    geo_columns = [
        str(column.get("name"))
        for column in columns
        if column.get("semantic_type") == "geo_coordinate"
    ]
    if not geo_columns:
        return None
    lat_name = next((name for name in geo_columns if "lat" in name.lower()), geo_columns[0])
    lon_name = next(
        (name for name in geo_columns if name != lat_name and "lon" in name.lower()),
        next((name for name in geo_columns if name != lat_name), None),
    )
    lat_values = _numeric(_values(rows, lat_name))
    lat_values = lat_values[np.isfinite(lat_values)]
    result: dict[str, Any] = {
        "columns": geo_columns,
        "latitude": {
            "name": lat_name,
            "min": round(float(np.min(lat_values)), 6),
            "max": round(float(np.max(lat_values)), 6),
        }
        if lat_values.size
        else None,
    }
    if lon_name:
        lon_values = _numeric(_values(rows, lon_name))
        lon_values = lon_values[np.isfinite(lon_values)]
        if lon_values.size:
            result["longitude"] = {
                "name": lon_name,
                "min": round(float(np.min(lon_values)), 6),
                "max": round(float(np.max(lon_values)), 6),
            }
            result["center"] = [
                round(float(np.mean(lat_values)), 6) if lat_values.size else None,
                round(float(np.mean(lon_values)), 6),
            ]
    return result


def _categorical_analysis(
    profile_columns: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for name, column in profile_columns.items():
        if column.get("semantic_type") not in {"categorical", "boolean", "string"}:
            continue
        top_values = column.get("top_values") or []
        result.append(
            {
                "name": name,
                "cardinality": column.get("cardinality"),
                "sensitive": bool(column.get("sensitive", False)),
                "top": [
                    {"value": item.get("value"), "count": item.get("count")}
                    for item in top_values[:3]
                    if isinstance(item, dict)
                ],
            }
        )
    return result[:10]


def _notes(
    *,
    sample_size: int,
    sampled: bool,
    numeric: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
    temporal: list[dict[str, Any]],
    geo: dict[str, Any] | None,
) -> list[str]:
    notes = [f"分析基于 {sample_size} 行{'采样' if sampled else ''}。"]
    if numeric:
        skewed = [str(item["name"]) for item in numeric if abs(float(item["skewness"])) >= 1.0]
        notes.append(f"发现 {len(numeric)} 个数值列。")
        if skewed:
            notes.append(f"偏度绝对值 ≥ 1 的列：{'、'.join(skewed[:5])}。")
    else:
        notes.append("未发现数值列。")
    if correlations:
        strongest = correlations[0]
        notes.append(f"最强相关：{strongest['left']} 与 {strongest['right']}，r={strongest['r']}。")
    else:
        notes.append("未发现 |r| ≥ 0.5 的数值列相关。")
    if temporal:
        first = temporal[0]
        notes.append(
            f"时间列 {first['name']} 从 {first['start']} 到 {first['end']}，"
            f"最大间隔约 {first['max_gap_seconds']} 秒。"
        )
    if geo and geo.get("latitude") and geo.get("longitude"):
        notes.append(
            f"地理范围：纬度 {geo['latitude']['min']}–{geo['latitude']['max']}，"
            f"经度 {geo['longitude']['min']}–{geo['longitude']['max']}。"
        )
    return notes


def _array_analysis(dataset: Dataset) -> dict[str, Any]:
    schema = dataset.schema_json or {}
    shape = schema.get("shape") or []
    return {
        "version": ANALYSIS_VERSION,
        "computed_at": datetime.now(UTC).isoformat(),
        "sample_size": int(dataset.profile_json.get("sample_rows") or 0),
        "sampled": bool(dataset.sampled),
        "array": {
            "shape": shape,
            "dims": schema.get("dims") or [],
            "dtype": schema.get("dtype"),
            "units": schema.get("units"),
            "stats": (dataset.profile_json.get("array") or {}).get("stats") or {},
        },
        "numeric_columns": [],
        "correlations": [],
        "temporal": [],
        "geo": None,
        "categorical": [],
        "notes": ["科学数组分析摘要包含形状、维度、类型、单位与采样统计。"],
        "summary": "科学数组分析摘要包含形状、维度、类型、单位与采样统计。",
    }


def _values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row.get(field) for row in rows]


def _numeric(values: list[Any]) -> np.ndarray:
    result = []
    for value in values:
        if value is None or value == "" or isinstance(value, bool):
            result.append(np.nan)
            continue
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            result.append(np.nan)
    return np.asarray(result, dtype=float)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
