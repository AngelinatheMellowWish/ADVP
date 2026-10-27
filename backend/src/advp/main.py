"""FastAPI application entry point."""

import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from advp import __version__, render3d
from advp.api.audit import router as audit_router
from advp.api.charts import router as charts_router
from advp.api.cleaning import router as cleaning_router
from advp.api.costs import router as costs_router
from advp.api.datasets import router as datasets_router
from advp.api.diagnostics import router as diagnostics_router
from advp.api.export_jobs import router as export_jobs_router
from advp.api.exports import router as exports_router
from advp.api.geometry3d import router as geometry3d_router
from advp.api.health import router as health_router
from advp.api.imaging import router as imaging_router
from advp.api.live import router as live_router
from advp.api.pipelines import router as pipelines_router
from advp.api.projects import router as projects_router
from advp.api.providers import router as providers_router
from advp.api.render3d import router as render3d_router
from advp.api.scenes import router as scenes_router
from advp.api.selections import router as selections_router
from advp.api.session import router as session_router
from advp.api.sql import router as sql_router
from advp.api.streams import router as streams_router
from advp.api.system import router as system_router
from advp.api.trame3d import router as trame3d_router
from advp.config import get_settings
from advp.db import configure_database, get_session, init_db
from advp.logging_config import configure_logging
from advp.security import SecurityMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and release process-wide resources."""
    settings = get_settings()
    settings.ensure_database_dir()
    configure_database(settings.database_path)
    init_db()
    with get_session() as session:
        render3d.recover_jobs(session)
    logging.getLogger("advp").info(
        "service_started",
        extra={"version": __version__, "host": settings.host, "port": settings.port},
    )
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    configure_logging(settings)
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.add_middleware(SecurityMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(session_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
    app.include_router(diagnostics_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(datasets_router, prefix="/api")
    app.include_router(charts_router, prefix="/api")
    app.include_router(geometry3d_router, prefix="/api")
    app.include_router(imaging_router, prefix="/api")
    app.include_router(cleaning_router, prefix="/api")
    app.include_router(costs_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")
    app.include_router(render3d_router, prefix="/api")
    app.include_router(scenes_router, prefix="/api")
    app.include_router(selections_router, prefix="/api")
    app.include_router(exports_router, prefix="/api")
    app.include_router(export_jobs_router, prefix="/api")
    app.include_router(sql_router, prefix="/api")
    app.include_router(streams_router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(trame3d_router, prefix="/api")
    static_dir = _resolve_static_dir(settings.static_dir)
    if static_dir is not None:
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404)
            candidate = (static_dir / full_path).resolve()
            if candidate.is_file() and static_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            index = static_dir / "index.html"
            if index.is_file():
                return FileResponse(index, media_type="text/html")
            raise HTTPException(status_code=404)

    return app


def _resolve_static_dir(configured: Path | None) -> Path | None:
    root = Path(__file__).resolve().parents[3]
    candidates = [
        configured,
        root / "backend" / "static",
        root / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


app = create_app()


def run() -> None:
    """Run the local service with uvicorn."""
    settings = get_settings()
    uvicorn.run("advp.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
