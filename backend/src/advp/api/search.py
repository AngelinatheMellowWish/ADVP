"""Local search index endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from advp import search
from advp.api.deps import DbSession

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_all(
    q: str = Query(min_length=1, max_length=200),
    types: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Search projects, datasets, reports, traces, audit, and text facts."""
    kinds = [item.strip() for item in types.split(",") if item.strip()] if types else None
    return search.search_groups(q, kinds=kinds, limit=limit)


@router.post("/rebuild")
def rebuild(session: DbSession) -> dict[str, Any]:
    """Rebuild the local FTS index from the shared SQLite database."""
    counts = search.rebuild_index(session)
    return {"status": "rebuilt", "indexed": counts}
