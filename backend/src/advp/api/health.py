"""Health endpoint used by the frontend and local diagnostics."""

from fastapi import APIRouter
from pydantic import BaseModel

from advp import __version__
from advp.db import check_database

router = APIRouter()


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str
    version: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service, version, and database health."""
    database_ok = check_database()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version=__version__,
        database="ok" if database_ok else "error",
    )
