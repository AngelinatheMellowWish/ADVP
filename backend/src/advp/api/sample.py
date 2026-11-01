"""Sample project creation endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from advp import sample, search
from advp.api.deps import DbSession
from advp.api.schemas import ProjectDetail
from advp.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["sample"])


@router.post("/sample", response_model=ProjectDetail, status_code=201)
def create_sample_project(session: DbSession) -> dict[str, object]:
    """Create a deterministic project with table, array, and text datasets."""
    project = sample.create_sample_project(session)
    search.safe_index_project(session, project)
    return project_service.project_detail(project)
