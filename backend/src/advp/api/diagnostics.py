"""Diagnostic bundle endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from advp import diagnostics

router = APIRouter(tags=["diagnostics"])


@router.get("/diagnostics/bundle")
def diagnostics_bundle() -> Response:
    buffer = diagnostics.build_bundle()
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="advp-diagnostics.zip"'},
    )
