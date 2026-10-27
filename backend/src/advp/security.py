"""Local-service security middleware: token, CSRF, and response headers."""

from __future__ import annotations

import hmac
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from advp.config import Settings

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SecurityMiddleware(BaseHTTPMiddleware):
    """Enforce optional local token, browser-origin checks, and safe headers."""

    def __init__(self, app: object, *, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        is_api = path.startswith("/api")
        exempt = path in {"/api/health", "/api/session"}
        if is_api and not exempt and request.method != "OPTIONS":
            if self.settings.auth_token:
                supplied = (
                    request.headers.get("x-advp-token")
                    or _bearer(request)
                    or request.cookies.get(self.settings.session_cookie)
                )
                if not supplied or not hmac.compare_digest(supplied, self.settings.auth_token):
                    return _error(401, "auth_required", "a valid ADVP token is required")
            if request.method in MUTATING_METHODS:
                origin = request.headers.get("origin")
                if origin and not _origin_allowed(origin, self.settings):
                    return _error(403, "origin_not_allowed", "request origin is not allowed")
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            _api_csp() if is_api else _static_csp(),
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def _origin_allowed(origin: str, settings: Settings) -> bool:
    if origin in settings.cors_origins:
        return True
    host = urlparse(origin).hostname
    return host in {"127.0.0.1", "localhost"}


def _api_csp() -> str:
    return "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def _static_csp() -> str:
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "worker-src 'self' blob:; "
        "frame-src 'self' http://127.0.0.1:* http://localhost:*; "
        "frame-ancestors 'none'; base-uri 'none'"
    )


def _bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})
