"""Safe copy-on-write cleanup for rebuildable and orphaned artifacts."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import audit
from advp.config import Settings, get_settings
from advp.models import Dataset

logger = logging.getLogger("advp.cleanup")

CATEGORIES: tuple[str, ...] = ("imports", "derived", "logs", "search_index", "cache")
PROTECTED_REASON = "referenced_by_dataset"
_CACHE_GLOBS: tuple[str, ...] = (
    "exports/**/report_*_chart.png",
    "exports/**/*.tmp",
    "exports/**/*.part",
)


class CleanupError(Exception):
    """A cleanup request is invalid or cannot be executed."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        *,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.hint = hint


@dataclass
class Entry:
    """One file discovered by a cleanup category scan."""

    path: Path
    root: Path
    category: str
    relative: str
    size: int
    project_id: str | None = None
    dataset_ids: tuple[str, ...] = ()
    protected: bool = False
    reason: str | None = None


@dataclass
class Plan:
    """One scanned category with totals and optional protected files."""

    key: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    @property
    def protected_entries(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.protected]

    @property
    def protected_bytes(self) -> int:
        return sum(entry.size for entry in self.protected_entries)

    def is_deletable(self, entry: Entry, *, allow_referenced_uploads: bool) -> bool:
        if entry.category == "imports":
            return not entry.protected or allow_referenced_uploads
        if entry.category == "derived":
            return not entry.protected
        return True

    def describe(self, *, allow_referenced_uploads: bool) -> dict[str, Any]:
        deletable = [
            entry
            for entry in self.entries
            if self.is_deletable(entry, allow_referenced_uploads=allow_referenced_uploads)
        ]
        protected = [entry for entry in self.entries if entry not in deletable]
        return {
            "key": self.key,
            "files": len(self.entries),
            "bytes": self.bytes,
            "deletable_files": len(deletable),
            "deletable_bytes": sum(entry.size for entry in deletable),
            "protected_files": len(protected),
            "protected_bytes": sum(entry.size for entry in protected),
            "affected_projects": sorted(
                {entry.project_id for entry in self.entries if entry.project_id}
            ),
            "affected_datasets": sorted(
                {dataset_id for entry in self.entries for dataset_id in entry.dataset_ids}
            ),
            "deletable": [_entry_dict(entry) for entry in deletable],
            "protected": [
                {**_entry_dict(entry), "reason": entry.reason or PROTECTED_REASON}
                for entry in protected
            ],
        }


def normalize_categories(categories: list[str] | None) -> tuple[str, ...]:
    """Validate and order the requested categories."""
    if not categories:
        raise CleanupError(
            "invalid_cleanup_category",
            "at least one cleanup category is required",
            hint=f"choose from {', '.join(CATEGORIES)}",
        )
    requested = {str(item) for item in categories}
    unknown = sorted(requested - set(CATEGORIES))
    if unknown:
        raise CleanupError(
            "invalid_cleanup_category",
            f"unknown cleanup categories: {', '.join(unknown)}",
            hint=f"choose from {', '.join(CATEGORIES)}",
        )
    return tuple(key for key in CATEGORIES if key in requested)


def preview(
    session: Session,
    categories: list[str] | None,
    *,
    allow_referenced_uploads: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return a dry-run report with bytes, projects, and protected items."""
    settings = settings or get_settings()
    keys = normalize_categories(categories)
    references = _references(session)
    plans = [_build_plan(session, key, settings, references) for key in keys]
    return {
        "dry_run": True,
        "allow_referenced_uploads": allow_referenced_uploads,
        "categories": [
            plan.describe(allow_referenced_uploads=allow_referenced_uploads) for plan in plans
        ],
        "totals": _totals(plans, allow_referenced_uploads=allow_referenced_uploads),
    }


def execute(
    session: Session,
    categories: list[str] | None,
    *,
    confirm: bool,
    allow_referenced_uploads: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Delete the selected, non-protected artifacts and audit the result."""
    if not confirm:
        raise CleanupError(
            "confirmation_required",
            "cleanup requires confirm=true",
            400,
            hint="preview the impact first, then confirm the deletion",
        )
    settings = settings or get_settings()
    keys = normalize_categories(categories)
    references = _references(session)
    results: list[dict[str, Any]] = []
    for key in keys:
        plan = _build_plan(session, key, settings, references)
        deleted = 0
        deleted_bytes = 0
        protected = 0
        protected_bytes = 0
        errors: list[dict[str, str]] = []
        for entry in plan.entries:
            if not plan.is_deletable(
                entry,
                allow_referenced_uploads=allow_referenced_uploads,
            ):
                protected += 1
                protected_bytes += entry.size
                continue
            removed = _remove(entry)
            if removed is None:
                errors.append({"relative": entry.relative, "reason": "delete_failed"})
                continue
            deleted += 1
            deleted_bytes += removed
        results.append(
            {
                "key": key,
                "deleted_files": deleted,
                "deleted_bytes": deleted_bytes,
                "protected_files": protected,
                "protected_bytes": protected_bytes,
                "errors": errors,
            }
        )
    totals = {
        "deleted_files": sum(item["deleted_files"] for item in results),
        "deleted_bytes": sum(item["deleted_bytes"] for item in results),
        "protected_files": sum(item["protected_files"] for item in results),
        "protected_bytes": sum(item["protected_bytes"] for item in results),
        "errors": sum(len(item["errors"]) for item in results),
    }
    audit.record_event(
        session,
        "cleanup_performed",
        target_type="cleanup",
        detail={
            "categories": sorted(keys),
            **totals,
            "allow_referenced_uploads": allow_referenced_uploads,
        },
    )
    logger.info(
        "cleanup_performed",
        extra={
            "categories": sorted(keys),
            "deleted_files": totals["deleted_files"],
            "deleted_bytes": totals["deleted_bytes"],
            "protected_files": totals["protected_files"],
        },
    )
    return {
        "dry_run": False,
        "allow_referenced_uploads": allow_referenced_uploads,
        "categories": results,
        "totals": totals,
    }


def _build_plan(
    session: Session,
    key: str,
    settings: Settings,
    references: list[tuple[Path, str]],
) -> Plan:
    plan = Plan(key=key)
    if key == "imports":
        root = settings.resolved_imports_dir
        for path in _iter_files(root):
            relative = _relative(path, root)
            plan.entries.append(
                _entry(path, root, key, relative, references, project=_project_from(relative))
            )
    elif key == "derived":
        root = settings.workspace_dir / "derived"
        for path in _iter_files(root):
            relative = _relative(path, root)
            plan.entries.append(
                _entry(path, root, key, relative, references, project=_project_from(relative))
            )
    elif key == "logs":
        root = settings.log_dir or (settings.workspace_dir / "logs")
        for path in _iter_files(root):
            plan.entries.append(_entry(path, root, key, _relative(path, root), references))
    elif key == "search_index":
        root = settings.resolved_eu2_dir
        base = settings.eu2_search_db
        for path in (base, Path(f"{base}-wal"), Path(f"{base}-shm")):
            if path.is_file() and not path.is_symlink():
                plan.entries.append(_entry(path, root, key, path.name, references))
    elif key == "cache":
        workspace = settings.workspace_dir
        seen: set[Path] = set()
        for folder in (workspace / "exports" / "3d", workspace / "sandbox"):
            for path in _iter_files(folder):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                relative = _relative(path, workspace)
                plan.entries.append(
                    _entry(
                        path,
                        workspace,
                        key,
                        relative,
                        references,
                        project=_cache_project(relative),
                    )
                )
        for pattern in _CACHE_GLOBS:
            for path in sorted(workspace.glob(pattern)):
                if not path.is_file() or path.is_symlink():
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                relative = _relative(path, workspace)
                plan.entries.append(
                    _entry(
                        path,
                        workspace,
                        key,
                        relative,
                        references,
                        project=_cache_project(relative),
                    )
                )
    else:  # pragma: no cover - guarded by normalize_categories
        raise CleanupError("invalid_cleanup_category", f"unknown category: {key}")
    return plan


def _entry(
    path: Path,
    root: Path,
    key: str,
    relative: str,
    references: list[tuple[Path, str]],
    *,
    project: str | None = None,
) -> Entry:
    resolved = path.resolve()
    matches = [dataset_id for reference, dataset_id in references if _matches(resolved, reference)]
    protected = bool(matches) and key in {"imports", "derived"}
    return Entry(
        path=path,
        root=root,
        category=key,
        relative=relative,
        size=_size(path),
        project_id=project,
        dataset_ids=tuple(sorted(set(matches))),
        protected=protected,
        reason=PROTECTED_REASON if protected else None,
    )


def _references(session: Session) -> list[tuple[Path, str]]:
    references: list[tuple[Path, str]] = []
    for dataset in session.scalars(select(Dataset)).all():
        try:
            references.append((Path(dataset.source_path).resolve(), dataset.id))
        except OSError:  # pragma: no cover - defensive
            continue
    return references


def _matches(path: Path, reference: Path) -> bool:
    return path == reference or path.is_relative_to(reference)


def _iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    try:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                continue
            if path.is_file():
                files.append(path)
    except OSError:  # pragma: no cover - transient filesystem errors
        return files
    return files


def _relative(path: Path, root: Path) -> str:
    with contextlib.suppress(ValueError):
        return path.relative_to(root).as_posix()
    return path.name


def _project_from(relative: str) -> str | None:
    parts = relative.split("/")
    return parts[0] if len(parts) > 1 and parts[0] else None


def _cache_project(relative: str) -> str | None:
    parts = relative.split("/")
    if parts[:2] == ["exports", "3d"]:
        if len(parts) >= 4 and parts[2] not in {"cache", "trame"}:
            return parts[2]
        return None
    if parts[:1] == ["exports"] and len(parts) >= 3:
        return parts[1]
    return None


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:  # pragma: no cover - transient filesystem errors
        return 0


def _remove(entry: Entry) -> int | None:
    """Delete one file and return the freed bytes, or None on failure."""
    if not _safe_path(entry.path, entry.root):
        return None
    size = _size(entry.path)
    try:
        entry.path.unlink()
    except FileNotFoundError:
        return 0
    except PermissionError:
        if entry.category != "logs":
            return None
        try:
            entry.path.write_bytes(b"")
        except OSError:
            return None
    except OSError:
        return None
    _prune(entry.path.parent, entry.root)
    return size


def _safe_path(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
    except OSError:  # pragma: no cover - defensive
        return False
    return resolved == root_resolved or resolved.is_relative_to(root_resolved)


def _prune(directory: Path, root: Path) -> None:
    try:
        root_resolved = root.resolve()
    except OSError:  # pragma: no cover - defensive
        return
    current = directory
    while True:
        try:
            current_resolved = current.resolve()
        except OSError:  # pragma: no cover - defensive
            return
        if current_resolved == root_resolved or not current_resolved.is_relative_to(root_resolved):
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _totals(plans: list[Plan], *, allow_referenced_uploads: bool) -> dict[str, int]:
    files = 0
    total_bytes = 0
    deletable_files = 0
    deletable_bytes = 0
    protected_files = 0
    protected_bytes = 0
    for plan in plans:
        described = plan.describe(allow_referenced_uploads=allow_referenced_uploads)
        files += described["files"]
        total_bytes += described["bytes"]
        deletable_files += described["deletable_files"]
        deletable_bytes += described["deletable_bytes"]
        protected_files += described["protected_files"]
        protected_bytes += described["protected_bytes"]
    return {
        "files": files,
        "bytes": total_bytes,
        "deletable_files": deletable_files,
        "deletable_bytes": deletable_bytes,
        "protected_files": protected_files,
        "protected_bytes": protected_bytes,
    }


def _entry_dict(entry: Entry) -> dict[str, Any]:
    return {
        "relative": entry.relative,
        "bytes": entry.size,
        "project_id": entry.project_id,
        "dataset_ids": list(entry.dataset_ids),
    }
