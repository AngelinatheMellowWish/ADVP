"""Local FTS5 search index stored in the EU2 sidecar directory."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.eu2_settings import runtime_setting
from advp.models import AuditEvent, Dataset, PipelineRun, PipelineStep, Project

LOGGER = logging.getLogger("advp")
KINDS = ("project", "dataset", "report", "trace", "audit", "text")
_TOKENIZER: str | None = None


def _connect() -> sqlite3.Connection:
    path = get_settings().eu2_search_db
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    global _TOKENIZER
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            object_id TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(kind, object_id)
        )
        """
    )
    tokenizers = (_TOKENIZER,) if _TOKENIZER else ("trigram", "unicode61")
    for tokenizer in tokenizers:
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5("
                "kind UNINDEXED, object_id UNINDEXED, project_id UNINDEXED, "
                f"title, body, url UNINDEXED, tokenize='{tokenizer}')"
            )
            _TOKENIZER = tokenizer
            break
        except sqlite3.OperationalError:
            continue
    else:
        _TOKENIZER = ""
    connection.commit()


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def _excluded() -> set[str]:
    value = runtime_setting(get_settings(), "search_excluded_projects") or []
    return {str(item) for item in value} if isinstance(value, list) else set()


def _raw_content_enabled() -> bool:
    return bool(runtime_setting(get_settings(), "search_raw_content"))


def _sensitive_enabled() -> bool:
    return bool(runtime_setting(get_settings(), "search_sensitive"))


def index_document(
    *,
    kind: str,
    object_id: str,
    project_id: str | None,
    title: str,
    body: str = "",
    url: str = "",
) -> int:
    """Upsert one search document and return its row id."""
    with _connection() as connection:
        connection.execute(
            "DELETE FROM docs WHERE kind = ? AND object_id = ?",
            (kind, object_id),
        )
        connection.execute(
            "DELETE FROM docs_fts WHERE kind = ? AND object_id = ?",
            (kind, object_id),
        )
        cursor = connection.execute(
            "INSERT INTO docs(kind, object_id, project_id, title, body, url, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                kind,
                object_id,
                project_id,
                title,
                body,
                url,
                datetime.now(UTC).isoformat(),
            ),
        )
        row_id = int(cursor.lastrowid or 0)
        connection.execute(
            "INSERT INTO docs_fts(rowid, kind, object_id, project_id, title, body, url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row_id, kind, object_id, project_id, title, body, url),
        )
        connection.commit()
        return row_id


def index_project(session: Session, project: Project) -> int:
    """Index a project name unless the project is excluded."""
    if project.id in _excluded():
        return 0
    return index_document(
        kind="project",
        object_id=project.id,
        project_id=project.id,
        title=project.name,
        body=f"project {project.name}",
        url=f"/projects/{project.id}/data",
    )


def index_dataset(session: Session, dataset: Dataset) -> int:
    """Index dataset metadata, field names, and optional masked samples."""
    if dataset.project_id in _excluded():
        return 0
    columns = [
        column
        for column in (dataset.schema_json or {}).get("columns", [])
        if isinstance(column, dict)
    ]
    parts = [
        dataset.name,
        dataset.kind,
        dataset.format,
        str((dataset.options or {}).get("source_kind") or ""),
    ]
    for column in columns:
        parts.append(str(column.get("name") or ""))
        parts.append(str(column.get("semantic_type") or ""))
    if _raw_content_enabled():
        allow_sensitive = _sensitive_enabled()
        for column in columns:
            if column.get("sensitive") and not allow_sensitive:
                continue
            for value in list(column.get("samples") or [])[:3]:
                parts.append(str(value))
        for row in list(dataset.preview_json or [])[:20]:
            if isinstance(row, dict):
                parts.extend(str(value) for value in row.values())
    return index_document(
        kind="dataset",
        object_id=dataset.id,
        project_id=dataset.project_id,
        title=dataset.name,
        body=" ".join(part for part in parts if part),
        url=f"/projects/{dataset.project_id}/data?dataset={dataset.id}",
    )


def index_report(session: Session, run: PipelineRun, body: str = "") -> int:
    """Index a pipeline report."""
    if run.project_id in _excluded():
        return 0
    dataset = session.get(Dataset, str(run.options.get("working_dataset_id") or run.dataset_id))
    title = f"Report {dataset.name if dataset else run.id}"
    return index_document(
        kind="report",
        object_id=run.id,
        project_id=run.project_id,
        title=title,
        body=body[:200_000],
        url=f"/projects/{run.project_id}/reports?run={run.id}",
    )


def index_trace(session: Session, run: PipelineRun) -> int:
    """Index pipeline run trace metadata."""
    if run.project_id in _excluded():
        return 0
    return index_document(
        kind="trace",
        object_id=run.id,
        project_id=run.project_id,
        title=f"Run {run.id}",
        body=f"{run.status} {run.current_step or ''} {run.error or ''}",
        url=f"/projects/{run.project_id}/trace?run={run.id}",
    )


def index_audit(session: Session, event: AuditEvent) -> int:
    """Index one audit event."""
    if event.project_id and event.project_id in _excluded():
        return 0
    return index_document(
        kind="audit",
        object_id=event.id,
        project_id=event.project_id,
        title=event.event,
        body=json.dumps(event.detail_json or {}, ensure_ascii=False),
        url=(f"/projects/{event.project_id}/trace" if event.project_id else "/settings"),
    )


def delete_project(project_id: str) -> int:
    """Remove every indexed document for a project."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id FROM docs WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        connection.execute("DELETE FROM docs WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM docs_fts WHERE project_id = ?", (project_id,))
        connection.commit()
        return len(rows)


def search_documents(
    query: str,
    *,
    kinds: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search the local index with FTS5 and a LIKE fallback for short queries."""
    term = query.strip()
    if not term:
        return []
    allowed = {kind for kind in (kinds or KINDS) if kind in KINDS}
    results = _fts_search(term, allowed, limit)
    if not results:
        results = _like_search(term, allowed, limit)
    return results


def _fts_search(term: str, kinds: set[str], limit: int) -> list[dict[str, Any]]:
    quoted = '"' + term.replace('"', '""') + '"'
    try:
        with _connection() as connection:
            rows = connection.execute(
                "SELECT d.kind, d.object_id, d.project_id, d.title, "
                "snippet(docs_fts, 4, '[', ']', '...', 12) AS snippet, d.url "
                "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid "
                "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
                (quoted, limit * 2),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return _filter_rows(rows, kinds, limit)


def _like_search(term: str, kinds: set[str], limit: int) -> list[dict[str, Any]]:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with _connection() as connection:
        rows = connection.execute(
            "SELECT kind, object_id, project_id, title, body, url "
            "FROM docs WHERE (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\') "
            "ORDER BY updated_at DESC LIMIT ?",
            (pattern, pattern, limit * 2),
        ).fetchall()
    results = []
    for row in rows:
        snippet = _snippet(str(row["body"] or row["title"]), term)
        results.append({**dict(row), "snippet": snippet})
    return _filter_rows(results, kinds, limit)


def _filter_rows(rows: list[Any], kinds: set[str], limit: int) -> list[dict[str, Any]]:
    results = []
    for row in rows:
        item = dict(row)
        if item.get("kind") not in kinds:
            continue
        item.pop("body", None)
        item["snippet"] = item.get("snippet") or _snippet(str(item.get("title") or ""), "")
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _snippet(text: str, term: str) -> str:
    if not text:
        return ""
    position = text.lower().find(term.lower()) if term else -1
    if position < 0:
        return text[:160]
    start = max(0, position - 60)
    end = min(len(text), position + len(term) + 100)
    return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


def search_groups(query: str, *, kinds: list[str] | None = None, limit: int = 50) -> dict[str, Any]:
    """Return grouped search results for the API."""
    hits = search_documents(query, kinds=kinds, limit=limit)
    groups: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    for hit in hits:
        groups.setdefault(str(hit["kind"]), []).append(hit)
    return {
        "query": query,
        "groups": groups,
        "total": len(hits),
        "raw_content_enabled": _raw_content_enabled(),
    }


def rebuild_index(session: Session) -> dict[str, int]:
    """Rebuild the local index from projects, datasets, runs, and audit events."""
    counts = {kind: 0 for kind in KINDS}
    with _connection() as connection:
        connection.execute("DELETE FROM docs")
        connection.execute("DELETE FROM docs_fts")
        connection.commit()
    for project in session.scalars(select(Project)).all():
        if index_project(session, project):
            counts["project"] += 1
    for dataset in session.scalars(select(Dataset)).all():
        if (dataset.options or {}).get("source_kind") == "text_stats":
            if _index_text_dataset(dataset):
                counts["text"] += 1
        elif index_dataset(session, dataset):
            counts["dataset"] += 1
    for run in session.scalars(select(PipelineRun)).all():
        if index_trace(session, run):
            counts["trace"] += 1
        report_step = session.scalars(
            select(PipelineStep).where(
                PipelineStep.run_id == run.id,
                PipelineStep.key == "report",
                PipelineStep.status == "succeeded",
            )
        ).first()
        if report_step is not None:
            path = Path(str((report_step.output_json or {}).get("path") or ""))
            body = path.read_text(encoding="utf-8") if path.is_file() else ""
            if index_report(session, run, body):
                counts["report"] += 1
    for event in session.scalars(select(AuditEvent)).all():
        if index_audit(session, event):
            counts["audit"] += 1
    return counts


def _index_text_dataset(dataset: Dataset) -> int:
    if dataset.project_id in _excluded():
        return 0
    facts = (dataset.options or {}).get("text_stats") or {}
    body = f"{dataset.name} text stats {json.dumps(facts, ensure_ascii=False)}"
    return index_document(
        kind="text",
        object_id=dataset.id,
        project_id=dataset.project_id,
        title=dataset.name,
        body=body,
        url=f"/projects/{dataset.project_id}/data?dataset={dataset.id}",
    )


def safe_index_project(session: Session, project: Project) -> None:
    """Best-effort project indexing that never breaks the main request."""
    try:
        index_project(session, project)
    except Exception:
        LOGGER.warning("search_index_failed", extra={"kind": "project"})


def safe_index_dataset(session: Session, dataset: Dataset) -> None:
    """Best-effort dataset indexing that never breaks the main request."""
    try:
        index_dataset(session, dataset)
    except Exception:
        LOGGER.warning("search_index_failed", extra={"kind": "dataset"})


def safe_index_report(session: Session, run: PipelineRun, body: str) -> None:
    """Best-effort report indexing."""
    try:
        index_report(session, run, body)
    except Exception:
        LOGGER.warning("search_index_failed", extra={"kind": "report"})


def safe_delete_project(project_id: str) -> None:
    """Best-effort project index deletion."""
    try:
        delete_project(project_id)
    except Exception:
        LOGGER.warning("search_delete_failed", extra={"kind": "project"})
