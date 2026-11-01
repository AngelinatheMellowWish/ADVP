"""Multi-file union and join ingestion."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import polars as pl
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.ingest.files import (
    ImportOptions,
    IngestError,
    frame_to_rows,
    inspect_file,
    sha256_file,
)
from advp.models import Dataset, Project, utcnow

SOURCE_COLUMN = "_source_file"
UNION = "union"
JOIN = "join"
JoinHow = Literal["inner", "left", "right", "full"]
JOIN_HOWS = {"inner", "left", "right", "full"}


class MultiFilePathsError(IngestError):
    """Wrong number of files for the requested mode."""

    code = "multifile_paths"
    status_code = 400


class MultiFileModeError(IngestError):
    """Unsupported multi-file mode or join type."""

    code = "multifile_mode"
    status_code = 400


class MultiFileKeyError(IngestError):
    """Missing or invalid join key."""

    code = "multifile_key"
    status_code = 422


@dataclass(slots=True)
class SourceFrame:
    """One inspected source file ready for combination."""

    path: Path
    frame: pl.DataFrame
    row_count: int
    sampled: bool


def load_sources(
    paths: list[str],
    *,
    mode: str,
    options: ImportOptions | None = None,
) -> list[SourceFrame]:
    """Inspect every source file and keep its sampled frame and row count."""
    if mode not in {UNION, JOIN}:
        raise MultiFileModeError(f"unsupported multi-file mode: {mode}")
    if len(paths) < 2:
        raise MultiFilePathsError("multi-file import needs at least two files")
    if mode == JOIN and len(paths) != 2:
        raise MultiFilePathsError("join supports exactly two files")
    settings = get_settings()
    sources: list[SourceFrame] = []
    for path in paths:
        loaded = inspect_file(
            path,
            options,
            max_file_bytes=settings.max_file_bytes,
            default_sample_rows=settings.profile_sample_rows,
        )
        sources.append(
            SourceFrame(
                path=loaded.path,
                frame=loaded.frame,
                row_count=loaded.row_count,
                sampled=loaded.sampled,
            )
        )
    return sources


def union_frames(sources: list[SourceFrame]) -> pl.DataFrame:
    """Align columns across files, fill gaps with nulls, and tag the source."""
    tagged = [
        source.frame.with_columns(pl.lit(source.path.name).alias(SOURCE_COLUMN))
        for source in sources
    ]
    return pl.concat(tagged, how="diagonal_relaxed")


def join_frames(
    left: pl.DataFrame,
    right: pl.DataFrame,
    *,
    left_key: str,
    right_key: str,
    how: JoinHow,
) -> pl.DataFrame:
    """Join two frames on their keys with a `_right` suffix for conflicts."""
    if how not in JOIN_HOWS:
        raise MultiFileModeError(f"unsupported join type: {how}")
    _require_key(left, left_key, "left")
    _require_key(right, right_key, "right")
    return left.join(
        right,
        left_on=left_key,
        right_on=right_key,
        how=how,
        suffix="_right",
    )


def build_frame(
    sources: list[SourceFrame],
    *,
    mode: str,
    left_key: str | None = None,
    right_key: str | None = None,
    how: JoinHow = "inner",
) -> pl.DataFrame:
    """Combine inspected sources according to the requested mode."""
    if mode == UNION:
        return union_frames(sources)
    if mode != JOIN:
        raise MultiFileModeError(f"unsupported multi-file mode: {mode}")
    if not left_key or not right_key:
        raise MultiFileKeyError("join requires left_key and right_key")
    left, right = sources
    return join_frames(left.frame, right.frame, left_key=left_key, right_key=right_key, how=how)


def preview_multifile(
    paths: list[str],
    *,
    mode: str,
    left_key: str | None = None,
    right_key: str | None = None,
    how: JoinHow = "inner",
    options: ImportOptions | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return row counts, key diagnostics, and a preview without persisting."""
    settings = get_settings()
    sources = load_sources(paths, mode=mode, options=options)
    frame = build_frame(
        sources,
        mode=mode,
        left_key=left_key,
        right_key=right_key,
        how=how,
    )
    conflicts: list[str] = []
    match_rate: float | None = None
    duplicate_keys: dict[str, int] | None = None
    left_rows: int | None = None
    right_rows: int | None = None
    if mode == JOIN:
        left, right = sources
        left_rows = left.row_count
        right_rows = right.row_count
        assert left_key is not None
        assert right_key is not None
        conflicts = sorted(
            (set(left.frame.columns) & set(right.frame.columns)) - {left_key, right_key}
        )
        match_rate = _match_rate(left.frame, right.frame, left_key, right_key)
        duplicate_keys = {
            "left": _duplicate_key_count(left.frame, left_key),
            "right": _duplicate_key_count(right.frame, right_key),
        }
    return {
        "mode": mode,
        "files": [
            {
                "path": str(source.path),
                "name": source.path.name,
                "row_count": source.row_count,
                "column_count": source.frame.width,
                "sampled": source.sampled,
            }
            for source in sources
        ],
        "columns": list(frame.columns),
        "left_rows": left_rows,
        "right_rows": right_rows,
        "result_rows": frame.height,
        "match_rate": match_rate,
        "duplicate_keys": duplicate_keys,
        "conflicts": conflicts,
        "sampled": any(source.sampled for source in sources),
        "preview": frame_to_rows(frame, limit=limit or settings.preview_rows),
    }


def import_multifile(
    session: Session,
    project: Project,
    *,
    paths: list[str],
    mode: str,
    left_key: str | None = None,
    right_key: str | None = None,
    how: JoinHow = "inner",
    name: str | None = None,
    options: ImportOptions | None = None,
) -> Dataset:
    """Materialize a combined file and register it as a derived dataset."""
    from advp.services import projects as project_service

    settings = get_settings()
    sources = load_sources(paths, mode=mode, options=options)
    frame = build_frame(
        sources,
        mode=mode,
        left_key=left_key,
        right_key=right_key,
        how=how,
    )
    files = [
        {
            "path": str(source.path),
            "name": source.path.name,
            "sha256": sha256_file(source.path),
            "row_count": source.row_count,
            "sampled": source.sampled,
        }
        for source in sources
    ]
    conflicts = (
        sorted(
            (set(sources[0].frame.columns) & set(sources[1].frame.columns)) - {left_key, right_key}
        )
        if mode == JOIN
        else []
    )
    derived_dir = settings.workspace_dir / "derived" / project.id
    derived_dir.mkdir(parents=True, exist_ok=True)
    output = derived_dir / f"{uuid.uuid4().hex}.parquet"
    frame.write_parquet(output)
    dataset = project_service.import_dataset(
        session,
        project,
        path=str(output),
        name=name or f"{mode} of {len(sources)} files",
        options=ImportOptions(
            sample_rows=settings.profile_sample_rows,
            preview_rows=settings.preview_rows,
        ),
    )
    dataset.options = {
        **dataset.options,
        "source_kind": "multifile",
        "multifile": {
            "mode": mode,
            "files": files,
            "keys": {"left": left_key, "right": right_key, "how": how},
            "conflicts": conflicts,
            "truncated": any(source.sampled for source in sources),
        },
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def _require_key(frame: pl.DataFrame, key: str, side: str) -> None:
    if key not in frame.columns:
        raise MultiFileKeyError(f"{side} join key is not a column: {key}")


def _match_rate(
    left: pl.DataFrame,
    right: pl.DataFrame,
    left_key: str,
    right_key: str,
) -> float:
    _require_key(left, left_key, "left")
    _require_key(right, right_key, "right")
    left_keys = set(left.get_column(left_key).to_list())
    if not left_keys:
        return 0.0
    right_keys = set(right.get_column(right_key).to_list())
    return len(left_keys & right_keys) / len(left_keys)


def _duplicate_key_count(frame: pl.DataFrame, key: str) -> int:
    counts = frame.get_column(key).value_counts()
    count_column = counts.columns[-1]
    return counts.filter(pl.col(count_column) > 1).height
