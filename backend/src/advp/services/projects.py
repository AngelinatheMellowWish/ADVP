"""Project persistence, import orchestration, and schema migration."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import __version__
from advp.config import get_settings
from advp.ingest.documents import (
    extract_document_tables,
    materialize_document_table,
    table_summary,
)
from advp.ingest.files import (
    ImportOptions,
    InvalidSourceError,
    SourceChangedError,
    UnsupportedFormatError,
    frame_to_rows,
    inspect_file,
    read_preview,
    sha256_source,
)
from advp.ingest.profiling import profile_frame, schema_from_profile
from advp.ingest.remote import fetch_http, fetch_s3, redact_label
from advp.ingest.scientific import inspect_scientific, is_scientific_source
from advp.ingest.sql import materialize_query, normalize_url
from advp.ingest.streams import collect_kafka, collect_websocket, materialize_stream
from advp.ingest.text_readers import (
    TEXT_SUFFIXES,
    TextDocumentEmptyError,
    read_text_document,
)
from advp.ingest.textstats import (
    TextFactInvalidError,
    TextSourceChangedError,
    extract_facts,
)
from advp.ingest.web import (
    fetch_web_tables,
    materialize_web_table,
)
from advp.ingest.web import (
    table_summary as web_table_summary,
)
from advp.models import Dataset, Project, utcnow

CURRENT_PROJECT_SCHEMA_VERSION = 1
DEFAULT_PROJECT_SETTINGS: dict[str, Any] = {
    "language": "zh-CN",
    "default_provider": None,
    "budget_usd": None,
    "sample_rows": 2000,
    "render_backend": "auto",
}


@dataclass(slots=True)
class LoadedDataset:
    path: Path
    kind: str
    format: str
    size_bytes: int
    mtime: float
    schema: dict[str, Any]
    profile: dict[str, Any]
    preview: list[dict[str, Any]]
    row_count: int
    column_count: int
    sampled: bool
    row_count_estimated: bool
    options: dict[str, Any]
    detected: dict[str, Any]
    issues: list[dict[str, Any]]
    variables: list[dict[str, Any]] = field(default_factory=list)


def _load_dataset(path: str, options: ImportOptions | None) -> LoadedDataset:
    settings = get_settings()
    if is_scientific_source(path):
        inspection = inspect_scientific(
            path,
            options,
            max_file_bytes=settings.max_file_bytes,
            default_sample_rows=settings.profile_sample_rows,
        )
        return LoadedDataset(
            path=inspection.path,
            kind="array",
            format=inspection.format,
            size_bytes=inspection.size_bytes,
            mtime=inspection.mtime,
            schema=inspection.schema,
            profile=inspection.profile,
            preview=inspection.preview,
            row_count=inspection.row_count,
            column_count=inspection.column_count,
            sampled=inspection.sampled,
            row_count_estimated=False,
            options=inspection.options,
            detected=inspection.detected,
            issues=inspection.issues,
            variables=inspection.variables,
        )
    loaded = inspect_file(
        path,
        options,
        max_file_bytes=settings.max_file_bytes,
        default_sample_rows=settings.profile_sample_rows,
    )
    profile = profile_frame(
        loaded.frame,
        sampled=loaded.sampled,
        sample_rows=loaded.frame.height,
        row_count=loaded.row_count,
        row_count_estimated=loaded.row_count_estimated,
    )
    schema = schema_from_profile(profile)
    preview = frame_to_rows(
        loaded.frame,
        limit=int(loaded.options.get("preview_rows", settings.preview_rows)),
    )
    return LoadedDataset(
        path=loaded.path,
        kind="table",
        format=loaded.format,
        size_bytes=loaded.size_bytes,
        mtime=loaded.mtime,
        schema=schema,
        profile=profile,
        preview=preview,
        row_count=loaded.row_count,
        column_count=loaded.frame.width,
        sampled=loaded.sampled,
        row_count_estimated=loaded.row_count_estimated,
        options=loaded.options,
        detected=loaded.detected,
        issues=loaded.issues,
    )


def new_id() -> str:
    """Return a compact random identifier."""
    return uuid.uuid4().hex


def create_project(session: Session, name: str) -> Project:
    project = Project(
        id=new_id(),
        name=name.strip(),
        schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
        settings=dict(DEFAULT_PROJECT_SETTINGS),
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def list_projects(session: Session, *, include_archived: bool = False) -> list[Project]:
    statement = select(Project).order_by(Project.updated_at.desc())
    if not include_archived:
        statement = statement.where(Project.archived.is_(False))
    return list(session.scalars(statement))


def update_project(
    session: Session,
    project: Project,
    *,
    name: str | None = None,
    archived: bool | None = None,
) -> Project:
    if name is not None:
        project.name = name.strip()
    if archived is not None:
        project.archived = archived
    project.updated_at = utcnow()
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project: Project) -> None:
    derived = get_settings().workspace_dir / "derived" / project.id
    session.delete(project)
    session.commit()
    if derived.exists():
        shutil.rmtree(derived, ignore_errors=True)


def dataset_quality_score(dataset: Dataset) -> int:
    return int((dataset.profile_json or {}).get("quality_score", 0))


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    return {
        "id": dataset.id,
        "project_id": dataset.project_id,
        "name": dataset.name,
        "version": dataset.version,
        "kind": dataset.kind,
        "format": dataset.format,
        "source_path": dataset.source_path,
        "source_sha256": dataset.source_sha256,
        "source_size": dataset.source_size,
        "row_count": dataset.row_count,
        "row_count_estimated": dataset.row_count_estimated,
        "column_count": dataset.column_count,
        "sampled": dataset.sampled,
        "quality_score": dataset_quality_score(dataset),
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def dataset_detail(dataset: Dataset) -> dict[str, Any]:
    return {
        **dataset_summary(dataset),
        "options": dataset.options,
        "schema_definition": dataset.schema_json,
        "profile": dataset.profile_json,
        "preview": dataset.preview_json,
    }


def project_summary(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "schema_version": project.schema_version,
        "archived": project.archived,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "dataset_count": len(project.datasets),
    }


def project_detail(project: Project, migration: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **project_summary(project),
        "settings": project.settings,
        "datasets": [dataset_summary(dataset) for dataset in project.datasets],
        "migration": migration,
    }


def project_snapshot(project: Project) -> dict[str, Any]:
    return {
        "schemaVersion": project.schema_version,
        "id": project.id,
        "name": project.name,
        "archived": project.archived,
        "settings": project.settings,
        "createdAt": project.created_at.isoformat(),
        "updatedAt": project.updated_at.isoformat(),
        "datasets": [
            {
                **dataset_summary(dataset),
                "source_path": dataset.source_path,
                "options": dataset.options,
                "schema": dataset.schema_json,
                "profile": dataset.profile_json,
                "preview": dataset.preview_json,
            }
            for dataset in project.datasets
        ],
    }


def migrate_project(session: Session, project: Project, backup_dir: Path) -> dict[str, Any] | None:
    """Back up and migrate a project whose schemaVersion is older."""
    if project.schema_version >= CURRENT_PROJECT_SCHEMA_VERSION:
        return None
    original = project.schema_version
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"project-{project.id}-v{original}-{stamp}.json"
    backup.write_text(
        json.dumps(project_snapshot(project), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    applied: list[str] = []
    while project.schema_version < CURRENT_PROJECT_SCHEMA_VERSION:
        if project.schema_version == 0:
            project.settings = {**DEFAULT_PROJECT_SETTINGS, **(project.settings or {})}
            project.schema_version = 1
            applied.append("0->1")
        else:
            break
    project.updated_at = utcnow()
    session.commit()
    session.refresh(project)
    return {
        "from": original,
        "to": project.schema_version,
        "applied": applied,
        "backup": backup.name,
    }


def project_manifest(project: Project) -> dict[str, Any]:
    return {
        "manifestVersion": 1,
        "appVersion": __version__,
        "project": {
            "id": project.id,
            "name": project.name,
            "schemaVersion": project.schema_version,
            "createdAt": project.created_at.isoformat(),
            "updatedAt": project.updated_at.isoformat(),
            "settings": project.settings,
        },
        "datasets": [
            {
                "id": dataset.id,
                "name": dataset.name,
                "version": dataset.version,
                "format": dataset.format,
                "path": dataset.source_path,
                "sha256": dataset.source_sha256,
                "sizeBytes": dataset.source_size,
                "modifiedAt": dataset.source_mtime,
                "rowCount": dataset.row_count,
                "columnCount": dataset.column_count,
                "sampled": dataset.sampled,
                "options": dataset.options,
            }
            for dataset in project.datasets
        ],
    }


def inspect_source(path: str, options: ImportOptions | None) -> dict[str, Any]:
    loaded = _load_dataset(path, options)
    return {
        "kind": loaded.kind,
        "path": str(loaded.path),
        "format": loaded.format,
        "size_bytes": loaded.size_bytes,
        "mtime": loaded.mtime,
        "row_count": loaded.row_count,
        "column_count": loaded.column_count,
        "row_count_estimated": loaded.row_count_estimated,
        "sampled": loaded.sampled,
        "options": loaded.options,
        "detected": loaded.detected,
        "schema_definition": loaded.schema,
        "profile": loaded.profile,
        "preview": loaded.preview,
        "issues": [*loaded.profile["issues"], *loaded.issues],
        "variables": loaded.variables,
    }


def import_dataset(
    session: Session,
    project: Project,
    *,
    path: str,
    name: str | None,
    options: ImportOptions | None,
) -> Dataset:
    loaded = _load_dataset(path, options)
    digest = sha256_source(loaded.path)
    variable = loaded.options.get("variable")
    prior_versions = [
        dataset.version
        for dataset in project.datasets
        if Path(dataset.source_path) == loaded.path
        and (dataset.options or {}).get("variable") == variable
    ]
    version = max(prior_versions, default=0) + 1
    dataset = Dataset(
        id=new_id(),
        project_id=project.id,
        name=(name or loaded.path.stem).strip(),
        version=version,
        kind=loaded.kind,
        format=loaded.format,
        source_path=str(loaded.path),
        source_sha256=digest,
        source_size=loaded.size_bytes,
        source_mtime=loaded.mtime,
        row_count=loaded.row_count,
        row_count_estimated=loaded.row_count_estimated,
        column_count=loaded.column_count,
        sampled=loaded.sampled,
        options=loaded.options,
        schema_json=loaded.schema,
        profile_json={**loaded.profile, "import_issues": loaded.issues},
        preview_json=loaded.preview,
    )
    session.add(dataset)
    project.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    session.refresh(project)
    return dataset


def import_sql_dataset(
    session: Session,
    project: Project,
    *,
    url: str,
    query: str,
    name: str | None,
    max_rows: int,
) -> Dataset:
    settings = get_settings()
    normalized = normalize_url(url)
    derived_dir = settings.workspace_dir / "derived" / project.id
    derived_dir.mkdir(parents=True, exist_ok=True)
    output = derived_dir / f"{new_id()}.parquet"
    materialized = materialize_query(normalized, query, output, max_rows=max_rows)
    dataset = import_dataset(
        session,
        project,
        path=str(output),
        name=(name or f"SQL {materialized.dialect}").strip(),
        options=ImportOptions(
            sample_rows=settings.profile_sample_rows,
            preview_rows=settings.preview_rows,
        ),
    )
    dataset.options = {
        **dataset.options,
        "source_kind": "sql",
        "sql_dialect": materialized.dialect,
        "sql_label": materialized.label,
        "sql_query": query,
        "sql_row_limit": max_rows,
        "sql_truncated": materialized.truncated,
    }
    if materialized.truncated:
        issues = list(dataset.profile_json.get("issues") or [])
        issues.append(
            {
                "code": "sql_row_limit",
                "severity": "warning",
                "message": f"SQL result truncated to {max_rows} rows",
                "suggestion": "narrow the query or raise max_rows",
                "column": None,
                "affected_rows": None,
            }
        )
        summary = dict(dataset.profile_json.get("summary") or {})
        counts = dict(summary.get("issue_counts") or {})
        counts["warning"] = counts.get("warning", 0) + 1
        summary["issue_counts"] = counts
        dataset.profile_json = {
            **dataset.profile_json,
            "issues": issues,
            "summary": summary,
            "quality_score": max(0, int(dataset.profile_json.get("quality_score", 100)) - 8),
        }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def import_remote_dataset(
    session: Session,
    project: Project,
    *,
    url: str,
    name: str | None,
    filename: str | None,
    headers: dict[str, str] | None,
    auth: dict[str, Any] | None,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    remote = fetch_http(
        url,
        output_dir,
        headers=headers,
        auth=auth,
        filename=filename,
        max_bytes=settings.max_file_bytes,
    )
    default_name = Path(remote.label).name or "Remote dataset"
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(remote.path),
            name=(name or default_name).strip(),
            options=options,
        )
    except Exception:
        remote.path.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "remote",
        "remote_label": remote.label,
        "remote_content_type": remote.content_type,
        "remote_etag": remote.etag,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def import_s3_dataset(
    session: Session,
    project: Project,
    *,
    bucket: str,
    key: str,
    endpoint: str | None,
    region: str | None,
    access_key: str | None,
    secret_key: str | None,
    name: str | None,
    filename: str | None,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    remote = fetch_s3(
        bucket=bucket,
        key=key,
        output_dir=output_dir,
        endpoint=endpoint,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        filename=filename,
        max_bytes=settings.max_file_bytes,
    )
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(remote.path),
            name=(name or Path(key).name or "S3 dataset").strip(),
            options=options,
        )
    except Exception:
        remote.path.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "s3",
        "remote_label": remote.label,
        "remote_content_type": remote.content_type,
        "remote_etag": remote.etag,
        "s3_bucket": bucket,
        "s3_key": key,
        "s3_endpoint": endpoint,
        "s3_region": region,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def resolve_document_path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise InvalidSourceError(f"document was not found: {resolved.name}")
    return resolved


def inspect_document(path: str, *, force_text: bool = False) -> dict[str, Any]:
    resolved = resolve_document_path(path)
    suffix = resolved.suffix.lower()
    if suffix in {".pdf", ".docx"}:
        tables = extract_document_tables(path)
    elif suffix in TEXT_SUFFIXES:
        tables = []
    else:
        raise UnsupportedFormatError(
            f"unsupported document format: {suffix or '<none>'}",
            hint="supported formats: TXT, DOCX, PDF, Markdown, RTF, HTML",
        )
    payload: dict[str, Any] = {
        "path": str(resolved),
        "format": _document_format(suffix),
        "source_sha256": sha256_source(resolved),
        "tables": [table_summary(table) for table in tables],
        "text": None,
    }
    settings = get_settings()
    try:
        document = read_text_document(resolved, max_chars=settings.text_max_chars)
    except UnsupportedFormatError:
        return payload
    except TextDocumentEmptyError:
        if suffix in {".pdf", ".docx"} and tables:
            return payload
        raise

    has_numbers = bool(
        re.search(
            r"\d",
            "".join(line.text for block in document.blocks for line in block.lines),
        )
    )
    paragraph_count = sum(
        (1 if block.heading else 0) + len(block.lines) for block in document.blocks
    )
    extract = force_text or not tables
    extraction = extract_facts(document, max_facts=settings.text_max_facts) if extract else None
    warnings = list(extraction.warnings) if extraction is not None else []
    if document.truncated:
        warnings.append(
            {
                "code": "text_truncated",
                "severity": "warning",
                "message": f"text was truncated to {settings.text_max_chars} characters",
            }
        )
    long_preview = {
        "facts": [fact.as_dict() for fact in extraction.facts] if extraction else [],
        "rows": list(extraction.long_rows) if extraction else [],
        "warnings": warnings,
    }
    wide_preview = {
        "headers": list(extraction.wide_headers) if extraction else [],
        "rows": list(extraction.wide_rows) if extraction else [],
        "warnings": warnings,
    }
    payload["text"] = {
        "char_count": document.char_count,
        "paragraph_count": paragraph_count,
        "has_numbers": has_numbers,
        "truncated": document.truncated,
        "extractor": {"version": "textstats-v1", "method": "rules"},
        "long": long_preview,
        "wide": wide_preview,
    }
    return payload


def _document_format(suffix: str) -> str:
    mapping = {".htm": "html", ".txt": "txt", ".md": "md", ".rtf": "rtf"}
    return mapping.get(suffix, suffix.lstrip("."))


def import_document_dataset(
    session: Session,
    project: Project,
    *,
    path: str,
    table_index: int,
    name: str | None,
    has_header: bool,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"document-{new_id()}.parquet"
    table = materialize_document_table(path, table_index, output, has_header=has_header)
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or f"{Path(path).stem} table {table_index}").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "document",
        "document_path": str(Path(path).expanduser().resolve()),
        "document_format": table.source,
        "document_table_index": table_index,
        "document_has_header": has_header,
        "document_confidence": table.confidence,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def import_text_stats_dataset(
    session: Session,
    project: Project,
    *,
    path: str,
    source_sha256: str,
    shape: str,
    name: str | None,
    facts: list[dict[str, Any]],
    ai: dict[str, Any] | None,
    options: ImportOptions | None,
) -> Dataset:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise InvalidSourceError(f"document was not found: {resolved.name}")
    actual_sha256 = sha256_source(resolved)
    if actual_sha256 != source_sha256:
        raise TextSourceChangedError(
            "source document changed after inspection",
            hint="run the document check again before importing",
        )
    selected = [fact for fact in facts if bool(fact.get("include", True))]
    if not selected:
        raise TextFactInvalidError("no text statistics facts were selected")
    records = [_text_fact_row(fact) for fact in selected]
    output_dir = get_settings().workspace_dir / "derived" / project.id
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"text-stats-{new_id()}.parquet"
    frame = _text_stats_frame(records, shape)
    frame.write_parquet(output)
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or f"{resolved.stem} text statistics").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    manifest_dir = get_settings().workspace_dir / "exports" / project.id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"text_stats_{dataset.id}.json"
    manifest = {
        "version": 1,
        "app_version": __version__,
        "source_path": str(resolved),
        "source_sha256": actual_sha256,
        "shape": shape,
        "extractor": {"version": "textstats-v1", "rule_version": "rules-v1"},
        "ai": ai,
        "facts": selected,
        "edit_stats": {
            "input_count": len(facts),
            "selected_count": len(selected),
            "edited_count": sum(1 for fact in selected if bool(fact.get("edited"))),
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    dataset.options = {
        **dataset.options,
        "source_kind": "text_stats",
        "text_stats": {
            "shape": shape,
            "extractor_version": "textstats-v1",
            "rule_version": "rules-v1",
            "source_path": str(resolved),
            "source_sha256": actual_sha256,
            "ai_used": ai is not None,
            "selected_count": len(selected),
            "manifest_path": str(manifest_path),
        },
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def _text_fact_row(fact: dict[str, Any]) -> dict[str, Any]:
    subject = str(fact.get("subject_path") or "").strip()
    metric = str(fact.get("metric") or "").strip()
    if not subject or not metric:
        raise TextFactInvalidError("every text fact needs a subject and a metric")
    value = _text_fact_number(fact)
    if value is None:
        raise TextFactInvalidError(f"text fact has no numeric value: {subject} / {metric}")
    return {
        "主体": subject,
        "指标": metric,
        "数值": value,
        "单位": str(fact.get("unit") or ""),
        "备注": str(fact.get("note") or ""),
    }


def _text_fact_number(fact: dict[str, Any]) -> float | None:
    value = fact.get("value_number")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    low = fact.get("value_low")
    high = fact.get("value_high")
    if low is not None and high is not None:
        try:
            return (float(low) + float(high)) / 2
        except (TypeError, ValueError):
            return None
    text = str(fact.get("value_text") or "")
    match = re.search(r"\d[\d,]*(?:\.\d+)?(?:万|亿)?", text)
    if match is None:
        return None
    token = match.group(0)
    multiplier = 1
    if token.endswith("亿"):
        multiplier = 100_000_000
        token = token[:-1]
    elif token.endswith("万"):
        multiplier = 10_000
        token = token[:-1]
    try:
        return float(token.replace(",", "")) * multiplier
    except ValueError:
        return None


def _text_stats_frame(records: list[dict[str, Any]], shape: str) -> pl.DataFrame:
    if shape == "long":
        return pl.DataFrame(records, infer_schema_length=max(len(records), 1))
    subjects: list[str] = []
    for record in records:
        if record["主体"] not in subjects:
            subjects.append(record["主体"])
    rows: list[dict[str, Any]] = []
    index: dict[tuple[object, object], dict[str, Any]] = {}
    for record in records:
        key = (record["指标"], record["单位"])
        row = index.get(key)
        if row is None:
            row = {"指标": record["指标"], "单位": record["单位"]}
            for subject in subjects:
                row[subject] = None
            index[key] = row
            rows.append(row)
        row[record["主体"]] = record["数值"]
    return pl.DataFrame(rows, infer_schema_length=max(len(rows), 1))


def inspect_web(
    url: str,
    *,
    headers: dict[str, str] | None,
    auth: dict[str, Any] | None,
) -> dict[str, Any]:
    tables = fetch_web_tables(url, headers=headers, auth=auth)
    return {
        "url": redact_label(url),
        "format": "html",
        "tables": [web_table_summary(table) for table in tables],
    }


def import_web_dataset(
    session: Session,
    project: Project,
    *,
    url: str,
    table_index: int,
    name: str | None,
    headers: dict[str, str] | None,
    auth: dict[str, Any] | None,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"web-{new_id()}.csv"
    table = materialize_web_table(
        url,
        table_index,
        output,
        headers=headers,
        auth=auth,
    )
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or f"Web table {table_index}").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "web",
        "web_url": redact_label(url),
        "web_table_index": table_index,
        "web_confidence": table.confidence,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def preview_websocket(
    url: str,
    *,
    headers: dict[str, str] | None,
    auth: dict[str, Any] | None,
    max_messages: int,
    timeout: float,
) -> dict[str, Any]:
    records = collect_websocket(
        url,
        max_messages=max_messages,
        timeout=timeout,
        headers=headers,
        auth=auth,
    )
    return {"records": records, "count": len(records), "source": "websocket"}


def import_websocket_dataset(
    session: Session,
    project: Project,
    *,
    url: str,
    name: str | None,
    headers: dict[str, str] | None,
    auth: dict[str, Any] | None,
    max_messages: int,
    timeout: float,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    output = output_dir / f"stream-{new_id()}.parquet"
    records = collect_websocket(
        url,
        max_messages=max_messages,
        timeout=timeout,
        headers=headers,
        auth=auth,
    )
    materialize_stream(records, output)
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or "WebSocket stream").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "websocket",
        "stream_url": redact_label(url.replace("ws://", "http://").replace("wss://", "https://")),
        "stream_message_count": len(records),
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def import_stream_snapshot(
    session: Session,
    project: Project,
    records: list[dict[str, Any]],
    *,
    source_kind: str,
    label: str | None,
    name: str | None,
    options: ImportOptions | None = None,
) -> Dataset:
    """Materialize a live session snapshot as a normal derived dataset."""
    if not records:
        raise InvalidSourceError(
            "live session has no records to save",
            hint="wait for messages or resume the session",
        )
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    output = output_dir / f"stream-{new_id()}.parquet"
    materialize_stream(records, output)
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or f"{source_kind} live snapshot").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": source_kind,
        "stream_message_count": len(records),
        "stream_live_label": label,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def preview_kafka(
    *,
    bootstrap: str,
    topic: str,
    group: str | None,
    max_messages: int,
    timeout: float,
    auto_offset_reset: str,
    security_protocol: str | None,
    sasl_mechanism: str | None,
    sasl_username: str | None,
    sasl_password: str | None,
    ssl_ca_location: str | None,
) -> dict[str, Any]:
    records = collect_kafka(
        bootstrap,
        topic,
        group=group,
        max_messages=max_messages,
        timeout=timeout,
        auto_offset_reset=auto_offset_reset,
        security_protocol=security_protocol,
        sasl_mechanism=sasl_mechanism,
        sasl_username=sasl_username,
        sasl_password=sasl_password,
        ssl_ca_location=ssl_ca_location,
    )
    return {"records": records, "count": len(records), "source": "kafka"}


def import_kafka_dataset(
    session: Session,
    project: Project,
    *,
    bootstrap: str,
    topic: str,
    group: str | None,
    name: str | None,
    max_messages: int,
    timeout: float,
    auto_offset_reset: str,
    security_protocol: str | None,
    sasl_mechanism: str | None,
    sasl_username: str | None,
    sasl_password: str | None,
    ssl_ca_location: str | None,
    options: ImportOptions | None,
) -> Dataset:
    settings = get_settings()
    output_dir = settings.workspace_dir / "derived" / project.id
    output = output_dir / f"stream-{new_id()}.parquet"
    records = collect_kafka(
        bootstrap,
        topic,
        group=group,
        max_messages=max_messages,
        timeout=timeout,
        auto_offset_reset=auto_offset_reset,
        security_protocol=security_protocol,
        sasl_mechanism=sasl_mechanism,
        sasl_username=sasl_username,
        sasl_password=sasl_password,
        ssl_ca_location=ssl_ca_location,
    )
    materialize_stream(records, output)
    try:
        dataset = import_dataset(
            session,
            project,
            path=str(output),
            name=(name or f"Kafka {topic}").strip(),
            options=options,
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise
    dataset.options = {
        **dataset.options,
        "source_kind": "kafka",
        "stream_bootstrap": bootstrap,
        "stream_topic": topic,
        "stream_group": group,
        "stream_message_count": len(records),
        "stream_security_protocol": security_protocol,
    }
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def get_dataset(session: Session, dataset_id: str) -> Dataset | None:
    return session.get(Dataset, dataset_id)


def reprofile_dataset(session: Session, dataset: Dataset) -> Dataset:
    loaded = _load_dataset(dataset.source_path, ImportOptions(**dataset.options))
    dataset.kind = loaded.kind
    dataset.format = loaded.format
    dataset.source_sha256 = sha256_source(loaded.path)
    dataset.source_size = loaded.size_bytes
    dataset.source_mtime = loaded.mtime
    dataset.row_count = loaded.row_count
    dataset.row_count_estimated = loaded.row_count_estimated
    dataset.column_count = loaded.column_count
    dataset.sampled = loaded.sampled
    dataset.options = loaded.options
    dataset.schema_json = loaded.schema
    dataset.profile_json = {**loaded.profile, "import_issues": loaded.issues}
    dataset.preview_json = loaded.preview
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def relocate_dataset(
    session: Session,
    dataset: Dataset,
    *,
    path: str,
    force: bool,
) -> Dataset:
    loaded = _load_dataset(path, ImportOptions(**dataset.options))
    digest = sha256_source(loaded.path)
    changed = digest != dataset.source_sha256
    if changed and not force:
        raise SourceChangedError(
            "relocated file content differs from the original",
            hint="pass force=true to accept the new content as a new dataset version",
        )
    dataset.source_path = str(loaded.path)
    dataset.source_size = loaded.size_bytes
    dataset.source_mtime = loaded.mtime
    if changed:
        dataset.kind = loaded.kind
        dataset.source_sha256 = digest
        dataset.format = loaded.format
        dataset.row_count = loaded.row_count
        dataset.row_count_estimated = loaded.row_count_estimated
        dataset.column_count = loaded.column_count
        dataset.sampled = loaded.sampled
        dataset.options = loaded.options
        dataset.schema_json = loaded.schema
        dataset.profile_json = {**loaded.profile, "import_issues": loaded.issues}
        dataset.preview_json = loaded.preview
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return dataset


def preview_dataset(dataset: Dataset, *, limit: int, offset: int) -> dict[str, Any]:
    if dataset.kind == "array":
        rows = dataset.preview_json[offset : offset + limit]
        dtype = str((dataset.schema_json or {}).get("dtype", "unknown"))
        columns = [
            {
                "name": "index",
                "physical_type": "Int64",
                "semantic_type": "integer",
                "nullable": False,
                "cardinality": dataset.row_count,
                "value_range": None,
                "unit": None,
                "source_column": "index",
            },
            {
                "name": "value",
                "physical_type": dtype,
                "semantic_type": "number" if dtype.startswith("float") else "integer",
                "nullable": True,
                "cardinality": dataset.row_count,
                "value_range": None,
                "unit": (dataset.schema_json or {}).get("units"),
                "source_column": dataset.name,
            },
        ]
        return {
            "rows": rows,
            "columns": columns,
            "limit": limit,
            "offset": offset,
            "total_rows": dataset.row_count,
            "sampled": dataset.sampled,
        }
    settings = get_settings()
    rows = read_preview(
        dataset.source_path,
        dataset.options,
        limit=limit,
        offset=offset,
        max_file_bytes=settings.max_file_bytes,
        schema=dataset.schema_json,
    )
    columns = (dataset.schema_json or {}).get("columns", [])
    return {
        "rows": rows,
        "columns": columns,
        "limit": limit,
        "offset": offset,
        "total_rows": dataset.row_count,
        "sampled": dataset.sampled,
    }
