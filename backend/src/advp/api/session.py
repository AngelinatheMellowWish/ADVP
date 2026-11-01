"""Session bootstrap for the packaged same-origin application."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, Response

from advp.config import get_settings

router = APIRouter(tags=["session"])


@router.get("/session")
def create_session(
    request: Request,
    response: Response,
    token: str | None = None,
) -> dict[str, object]:
    """Set an HttpOnly session cookie when a local token is configured."""
    settings = get_settings()
    if not settings.auth_token:
        return {"ok": True, "auth_required": False}
    supplied = (
        token
        or request.headers.get("x-advp-token")
        or _bearer(request)
        or request.cookies.get(settings.session_cookie)
    )
    if not supplied or not hmac.compare_digest(supplied, settings.auth_token):
        raise HTTPException(
            status_code=401,
            detail={"code": "auth_required", "message": "a valid ADVP token is required"},
        )
    response.set_cookie(
        settings.session_cookie,
        settings.auth_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return {"ok": True, "auth_required": True}


def _bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return None
