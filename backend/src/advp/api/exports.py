"""Chart selection export endpoints."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from advp import exports as export_service
from advp import sandbox
from advp.api.deps import DbSession
from advp.charts import selection as selection_service
from advp.models import ChartSelection

router = APIRouter(prefix="/chart-selections", tags=["exports"])


def _row_or_404(session: Session, selection_id: str) -> ChartSelection:
    row = selection_service.get_selection(session, selection_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "chart_selection_not_found",
                "message": f"chart selection was not found: {selection_id}",
            },
        )
    return row


def _raise_export(exc: export_service.ExportError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/{selection_id}/export/manifest")
def export_manifest(selection_id: str, session: DbSession) -> dict[str, Any]:
    row = _row_or_404(session, selection_id)
    try:
        manifest: dict[str, Any] = export_service.build_share_package(session, row)["manifest"]
        return manifest
    except export_service.ExportError as exc:
        _raise_export(exc)


@router.get("/{selection_id}/export/html")
def export_html(selection_id: str, session: DbSession) -> Response:
    row = _row_or_404(session, selection_id)
    try:
        buffer = export_service.zip_share_package(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="' + export_service.export_filename(session, row, "zip") + '"'
            ),
        },
    )


@router.get("/{selection_id}/export/html-file")
def export_html_file(selection_id: str, session: DbSession) -> Response:
    row = _row_or_404(session, selection_id)
    try:
        path = export_service.build_single_file_html(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": (
                'attachment; filename="'
                + export_service.export_filename(session, row, "html")
                + '"'
            ),
        },
    )


@router.get("/{selection_id}/export/pdf")
def export_pdf(selection_id: str, session: DbSession) -> FileResponse:
    row = _row_or_404(session, selection_id)
    try:
        path = export_service.build_pdf(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=export_service.export_filename(session, row, "pdf"),
    )


@router.get("/{selection_id}/code")
def selection_code(selection_id: str, session: DbSession) -> dict[str, Any]:
    row = _row_or_404(session, selection_id)
    try:
        return export_service.build_code_view(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)


@router.post("/{selection_id}/code/run")
def run_selection_code(selection_id: str, session: DbSession) -> dict[str, Any]:
    row = _row_or_404(session, selection_id)
    try:
        code = export_service.build_python(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return sandbox.run_python(code).to_dict()


@router.get("/{selection_id}/export/python")
def export_python(selection_id: str, session: DbSession) -> Response:
    row = _row_or_404(session, selection_id)
    try:
        script = export_service.build_python(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return Response(
        content=script,
        media_type="text/x-python",
        headers={
            "Content-Disposition": (
                'attachment; filename="' + export_service.export_filename(session, row, "py") + '"'
            ),
        },
    )


@router.get("/{selection_id}/export/notebook")
def export_notebook(selection_id: str, session: DbSession) -> Response:
    row = _row_or_404(session, selection_id)
    try:
        notebook = export_service.build_notebook(session, row)
    except export_service.ExportError as exc:
        _raise_export(exc)
    return Response(
        content=json.dumps(notebook, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="'
                + export_service.export_filename(session, row, "ipynb")
                + '"'
            ),
        },
    )
