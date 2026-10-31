"""Read-only mode used when another ADVP instance owns the data directory."""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ID = r"[^/]+"
READ_ONLY_POST_ALLOWLIST = tuple(
    re.compile(pattern)
    for pattern in (
        r"/api/system/shutdown",
        r"/api/system/pick-file",
        r"/api/sql/(?:test|tables|columns|preview)",
        rf"/api/projects/{_ID}/datasets/inspect",
        rf"/api/projects/{_ID}/multifile/preview",
        rf"/api/projects/{_ID}/documents/inspect",
        rf"/api/projects/{_ID}/web/inspect",
        rf"/api/providers/{_ID}/(?:test|models)",
        r"/api/charts/candidates",
        rf"/api/datasets/{_ID}/chart-candidates",
        rf"/api/datasets/{_ID}/quality/apply",
        r"/api/streams/(?:websocket|kafka)/preview",
    )
)
_read_only = False


def configure_read_only(enabled: bool) -> None:
    """Set process-wide read-only mode."""
    global _read_only
    _read_only = enabled


def reset_read_only() -> None:
    """Return to normal read-write mode."""
    global _read_only
    _read_only = False


def is_read_only() -> bool:
    """Report whether mutating requests are currently blocked."""
    return _read_only


def is_allowed_read_only_post(path: str) -> bool:
    """Return whether a POST path is explicitly read-only and non-mutating."""
    return any(pattern.fullmatch(path) for pattern in READ_ONLY_POST_ALLOWLIST)


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests while another instance holds the writer lock."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if _read_only and request.method not in SAFE_METHODS:
            if request.method == "POST" and is_allowed_read_only_post(request.url.path):
                return await call_next(request)
            return JSONResponse(
                status_code=423,
                content={
                    "detail": {
                        "code": "read_only",
                        "message": "another ADVP instance is writing to this data directory",
                    }
                },
            )
        return await call_next(request)
