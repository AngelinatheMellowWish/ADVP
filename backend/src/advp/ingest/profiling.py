"""Schema inference, statistics, quality issues, and sensitive-field detection."""

from __future__ import annotations

import math
import re
from typing import Any

import polars as pl

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{7,15}$")
ID_CARD_RE = re.compile(r"^\d{17}[\dXx]$")
ADDRESS_RE = re.compile(r"(省|市|区|县|路|街|号|村|镇|小区|大道)")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)

SENSITIVE_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "email": ("email", "mail", "邮箱", "电子邮件"),
    "phone": ("phone", "mobile", "tel", "手机", "电话", "联系方式"),
    "id_card_number": ("id_card", "身份证", "证件号"),
    "address": ("address", "地址", "住址"),
    "long_text": ("notes", "description", "comment", "remark", "备注", "描述"),
}
LONG_TEXT_THRESHOLD = 200


def _safe_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _string_values(series: pl.Series, limit: int = 200) -> list[str]:
    try:
        casted = series.cast(pl.String)
    except Exception:
        return [str(value) for value in series.drop_nulls().head(limit).to_list()]
    return [str(value) for value in casted.drop_nulls().head(limit).to_list()]


def _ratio(values: list[str], pattern: re.Pattern[str]) -> float:
    if not values:
        return 0.0
    matches = sum(1 for value in values if pattern.fullmatch(value.strip()))
    return matches / len(values)


def _dtype_name(series: pl.Series) -> str:
    return str(series.dtype)


def infer_semantic_type(series: pl.Series, name: str) -> str:
    """Infer a semantic type from the physical dtype and sampled values."""
    dtype = _dtype_name(series)
    rows = max(series.len(), 1)
    lower_name = name.lower()
    if dtype.startswith(("Int", "UInt")):
        if lower_name in {"lat", "latitude", "lon", "lng", "longitude"}:
            return "geo_coordinate"
        return "integer"
    if dtype.startswith(("Float", "Decimal")):
        if lower_name in {"lat", "latitude", "lon", "lng", "longitude"}:
            return "geo_coordinate"
        return "number"
    if dtype.startswith("Boolean"):
        return "boolean"
    if dtype.startswith("Datetime"):
        return "datetime"
    if dtype.startswith("Date"):
        return "date"
    if dtype.startswith("Time"):
        return "time"
    if dtype.startswith("Duration"):
        return "duration"
    if dtype.startswith(("List", "Array")):
        return "array"
    if dtype.startswith("Struct"):
        return "object"
    if dtype.startswith("Binary"):
        return "binary"
    if dtype == "Null":
        return "null"
    if dtype.startswith(("String", "Categorical", "Enum")):
        values = _string_values(series)
        if values:
            if _ratio(values, EMAIL_RE) >= 0.6:
                return "email"
            if _ratio(values, PHONE_RE) >= 0.7:
                return "phone"
            if _ratio(values, ID_CARD_RE) >= 0.7:
                return "id_card_number"
            if _ratio(values, ADDRESS_RE) >= 0.6:
                return "address"
            if sum(1 for value in values if URL_RE.match(value)) / len(values) >= 0.6:
                return "url"
        unique = series.drop_nulls().n_unique()
        if unique <= max(20, int(rows * 0.05)):
            return "categorical"
        return "string"
    return "unknown"


def _sensitive_kind(name: str, semantic_type: str) -> str | None:
    if semantic_type in {"email", "phone", "id_card_number", "address"}:
        return semantic_type
    lower_name = name.lower()
    for kind, hints in SENSITIVE_NAME_HINTS.items():
        if any(hint in lower_name for hint in hints):
            return kind
    return None


def detect_sensitive(series: pl.Series, name: str, semantic_type: str) -> tuple[bool, str | None]:
    """Return whether a column is likely sensitive and its category."""
    kind = _sensitive_kind(name, semantic_type)
    values = _string_values(series)
    if kind is None and values:
        if _ratio(values, EMAIL_RE) >= 0.6:
            kind = "email"
        elif _ratio(values, ID_CARD_RE) >= 0.8:
            kind = "id_card_number"
        elif _ratio(values, PHONE_RE) >= 0.8:
            kind = "phone"
        elif _ratio(values, ADDRESS_RE) >= 0.6:
            kind = "address"
    if kind == "long_text" and values:
        average = sum(len(value) for value in values) / len(values)
        if average < LONG_TEXT_THRESHOLD:
            kind = None
    return kind is not None, kind


def mask_value(value: Any, kind: str | None) -> str:
    """Mask a sensitive value for display in profiles and model context."""
    text = str(value)
    if kind == "email":
        local, _, domain = text.partition("@")
        return f"{local[:1]}***@{domain}" if domain else "***"
    if kind == "phone":
        return f"{text[:3]}****{text[-4:]}" if len(text) >= 7 else "***"
    if kind == "id_card_number":
        return f"{text[:6]}********{text[-4:]}" if len(text) >= 10 else "***"
    if kind == "address":
        return f"{text[:4]}***" if len(text) > 4 else "***"
    if kind == "long_text":
        return f"{text[:20]}..." if len(text) > 20 else text
    return "***"


def _numeric_stats(series: pl.Series) -> dict[str, Any]:
    try:
        values = series.drop_nulls()
        values = values.filter(values.is_finite())
    except Exception:
        values = series.drop_nulls()
    if values.len() == 0:
        return {}
    q1 = _safe_number(values.quantile(0.25))
    q3 = _safe_number(values.quantile(0.75))
    outlier_count = 0
    if q1 is not None and q3 is not None:
        spread = q3 - q1
        if spread > 0:
            lower = q1 - 1.5 * spread
            upper = q3 + 1.5 * spread
            outlier_count = int(values.filter((values < lower) | (values > upper)).len())
    return {
        "min": _safe_number(values.min()),
        "max": _safe_number(values.max()),
        "mean": _safe_number(values.mean()),
        "median": _safe_number(values.median()),
        "std": _safe_number(values.std()),
        "q1": q1,
        "q3": q3,
        "outlier_count": outlier_count,
    }


def _temporal_stats(series: pl.Series) -> dict[str, Any]:
    values = series.drop_nulls()
    if values.len() == 0:
        return {}
    return {
        "min": _json_scalar(values.min()),
        "max": _json_scalar(values.max()),
    }


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _safe_number(value) if isinstance(value, (int, float)) else str(value)


def _string_stats(series: pl.Series) -> dict[str, Any]:
    try:
        lengths = series.cast(pl.String).str.len_chars().drop_nulls()
    except Exception:
        return {}
    if lengths.len() == 0:
        return {}
    minimum = _safe_number(lengths.min())
    maximum = _safe_number(lengths.max())
    average = _safe_number(lengths.mean())
    return {
        "min_length": int(minimum or 0),
        "max_length": int(maximum or 0),
        "avg_length": round(average or 0, 2),
    }


def _top_values(series: pl.Series, kind: str | None, sensitive: bool) -> list[dict[str, Any]]:
    try:
        counts = series.cast(pl.String).drop_nulls().value_counts(sort=True).head(5)
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for row in counts.iter_rows(named=True):
        items = list(row.items())
        if not items:
            continue
        value = items[0][1]
        count = items[-1][1]
        result.append(
            {
                "value": mask_value(value, kind) if sensitive else _json_scalar(value),
                "count": int(count) if isinstance(count, int) else _safe_number(count),
            }
        )
    return result


def _type_conflict(series: pl.Series) -> bool:
    if not _dtype_name(series).startswith(("String", "Categorical", "Enum")):
        return False
    values = _string_values(series, limit=500)
    if len(values) < 5:
        return False
    numeric = sum(1 for value in values if NUMBER_RE.fullmatch(value.strip()))
    ratio = numeric / len(values)
    return 0.05 <= ratio <= 0.95 and numeric >= 2 and len(values) - numeric >= 2


def _column_profile(series: pl.Series, name: str) -> dict[str, Any]:
    rows = series.len()
    null_count = int(series.null_count())
    unique_count = int(series.drop_nulls().n_unique())
    semantic_type = infer_semantic_type(series, name)
    sensitive, kind = detect_sensitive(series, name, semantic_type)
    dtype = _dtype_name(series)
    stats: dict[str, Any] = {}
    if dtype.startswith(("Int", "UInt", "Float", "Decimal")):
        stats = _numeric_stats(series)
    elif dtype.startswith(("Datetime", "Date", "Time")):
        stats = _temporal_stats(series)
    elif dtype.startswith(("String", "Categorical", "Enum")):
        stats = _string_stats(series)
    value_range = None
    if "min" in stats or "max" in stats:
        value_range = [stats.get("min"), stats.get("max")]
    if dtype.startswith(("String", "Categorical", "Enum")):
        values = _string_values(series, limit=3)
        if sensitive:
            samples = [mask_value(value, kind) for value in values]
        else:
            samples = [_json_scalar(value) for value in values]
    else:
        samples = [_json_scalar(value) for value in series.drop_nulls().head(3).to_list()]
    return {
        "name": name,
        "dtype": dtype,
        "semantic_type": semantic_type,
        "nullable": null_count > 0,
        "null_count": null_count,
        "null_rate": round(null_count / rows, 4) if rows else 0.0,
        "n_unique": unique_count,
        "cardinality": unique_count,
        "value_range": value_range,
        "unit": None,
        "source_column": name,
        "sensitive": sensitive,
        "sensitive_kind": kind,
        "stats": stats,
        "top_values": _top_values(series, kind, sensitive),
        "samples": samples,
    }


def _append_issue(
    issues: list[dict[str, Any]],
    *,
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    column: str | None = None,
    affected_rows: int | None = None,
) -> None:
    issues.append(
        {
            "code": code,
            "severity": severity,
            "message": message,
            "suggestion": suggestion,
            "column": column,
            "affected_rows": affected_rows,
        }
    )


def profile_frame(
    frame: pl.DataFrame,
    *,
    sampled: bool,
    sample_rows: int,
    row_count: int,
    row_count_estimated: bool,
) -> dict[str, Any]:
    """Build column statistics and a severity-classified quality report."""
    issues: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    duplicate_rows = int(frame.is_duplicated().sum()) if frame.height else 0

    if frame.height == 0:
        _append_issue(
            issues,
            code="empty_dataset",
            severity="blocking",
            message="the file contains no data rows",
            suggestion="check the delimiter, header setting, or encoding",
        )
    if frame.width == 0:
        _append_issue(
            issues,
            code="no_columns",
            severity="blocking",
            message="no columns were detected",
            suggestion="verify the file format and header row",
        )

    for name in frame.columns:
        series = frame[name]
        profile = _column_profile(series, name)
        columns.append(profile)
        if frame.height and profile["null_count"] == frame.height:
            _append_issue(
                issues,
                code="all_null_column",
                severity="warning",
                message=f"column {name!r} has no values",
                suggestion="drop the column or fix the source mapping",
                column=name,
                affected_rows=profile["null_count"],
            )
        elif profile["null_count"] > 0:
            _append_issue(
                issues,
                code="missing_values",
                severity="warning",
                message=f"column {name!r} has {profile['null_count']} missing values",
                suggestion="fill, drop, or impute missing values before analysis",
                column=name,
                affected_rows=profile["null_count"],
            )
        if frame.height and profile["n_unique"] <= 1 and profile["null_count"] < frame.height:
            _append_issue(
                issues,
                code="constant_column",
                severity="info",
                message=f"column {name!r} is constant",
                suggestion="consider dropping the column from charts",
                column=name,
            )
        outlier_count = profile["stats"].get("outlier_count")
        if isinstance(outlier_count, int) and outlier_count > 0:
            _append_issue(
                issues,
                code="numeric_outliers",
                severity="warning",
                message=f"column {name!r} has {outlier_count} IQR outliers",
                suggestion="review outliers; do not delete them silently",
                column=name,
                affected_rows=outlier_count,
            )
        if _type_conflict(series):
            _append_issue(
                issues,
                code="type_conflict",
                severity="warning",
                message=f"column {name!r} mixes numeric and text-like values",
                suggestion="choose a target type or clean inconsistent values",
                column=name,
                affected_rows=frame.height,
            )
        if profile["sensitive"]:
            _append_issue(
                issues,
                code="sensitive_field",
                severity="info",
                message=f"column {name!r} looks like {profile['sensitive_kind']} data",
                suggestion="keep masking enabled before sending samples to a model",
                column=name,
                affected_rows=frame.height,
            )
    if duplicate_rows > 0:
        _append_issue(
            issues,
            code="duplicate_rows",
            severity="warning",
            message=f"{duplicate_rows} duplicate rows detected",
            suggestion="review duplicates before aggregation",
            affected_rows=duplicate_rows,
        )
    if sampled:
        _append_issue(
            issues,
            code="sampled_profile",
            severity="info",
            message=f"profile is based on {sample_rows} sampled rows",
            suggestion="use a larger sample if distributions look unstable",
        )
    if row_count_estimated:
        _append_issue(
            issues,
            code="estimated_row_count",
            severity="info",
            message="row count is estimated from file size",
            suggestion="a full count is available after a complete import",
        )

    counts = {"blocking": 0, "warning": 0, "info": 0}
    for issue in issues:
        severity = str(issue["severity"])
        counts[severity] = counts.get(severity, 0) + 1
    penalty = counts["blocking"] * 40 + counts["warning"] * 8 + counts["info"] * 1
    quality_score = 0 if counts["blocking"] else max(0, 100 - min(80, penalty))
    sensitive_columns = [column["name"] for column in columns if column["sensitive"]]
    missing_cells = sum(int(column["null_count"]) for column in columns)
    return {
        "quality_score": quality_score,
        "sampled": sampled,
        "sample_rows": frame.height,
        "total_rows": row_count,
        "row_count_estimated": row_count_estimated,
        "duplicate_rows": duplicate_rows,
        "columns": columns,
        "issues": issues,
        "summary": {
            "missing_cells": missing_cells,
            "sensitive_columns": sensitive_columns,
            "issue_counts": counts,
        },
    }


def schema_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Project a profile into the Tabular Schema data contract."""
    columns = []
    for column in profile.get("columns", []):
        columns.append(
            {
                "name": column["name"],
                "physical_type": column["dtype"],
                "semantic_type": column["semantic_type"],
                "nullable": column["nullable"],
                "cardinality": column["cardinality"],
                "value_range": column["value_range"],
                "unit": column["unit"],
                "source_column": column["source_column"],
            }
        )
    return {"version": 1, "columns": columns}
