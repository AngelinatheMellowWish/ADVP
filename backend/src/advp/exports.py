# ruff: noqa: E501
"""Build offline share packages, PDF files, and code exports."""

from __future__ import annotations

import contextlib
import difflib
import json
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from advp import __version__, code_export
from advp import imaging as imaging_service
from advp.charts import render as render_service
from advp.config import get_settings
from advp.models import ChartSelection, Dataset

ROOT = Path(__file__).resolve().parents[3]


class ExportError(Exception):
    """An export cannot be produced for the selection."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def export_filename(
    session: Session,
    selection: ChartSelection,
    extension: str,
) -> str:
    """Build a safe export name with dataset, chart, version, and timestamp."""
    dataset = session.get(Dataset, selection.dataset_id)
    dataset_name = dataset.name if dataset is not None else "dataset"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw = f"ADVP_{dataset_name}_{selection.selected_chart_id}_v{__version__}_{stamp}.{extension}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)


def build_share_package(
    session: Session,
    selection: ChartSelection,
) -> dict[str, Any]:
    """Build an offline directory containing a share page and manifest."""
    dataset = session.get(Dataset, selection.dataset_id)
    if dataset is None:
        raise ExportError("dataset_not_found", "selection dataset no longer exists", 404)
    sensitive = _sensitive_columns(dataset)
    result = selection.result_json or {}
    fields = {
        str(key): str(value)
        for key, value in (result.get("selected") or {}).get("fields", {}).items()
    }
    used_sensitive = sorted(sensitive & set(fields.values()))
    if used_sensitive:
        raise ExportError(
            "sensitive_field",
            f"export blocked because the chart uses sensitive fields: {', '.join(used_sensitive)}",
        )
    render = render_service.render_selection(session, selection)
    renderer = str(render.get("renderer") or "plotly")
    payload: dict[str, Any] = {
        "selection": result,
        "render": render,
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "kind": dataset.kind,
            "format": dataset.format,
            "row_count": dataset.row_count,
            "sampled": dataset.sampled,
        },
    }
    if render.get("renderer") == "vtk":
        slice_meta = _default_imaging_slice(dataset)
        if slice_meta is not None:
            payload["imaging_slice"] = slice_meta
    settings = get_settings()
    export_dir = settings.workspace_dir / "exports" / dataset.project_id / selection.id
    export_dir.mkdir(parents=True, exist_ok=True)
    bundle_name, bundle_bytes = _copy_share_assets(export_dir, renderer)
    (export_dir / "payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "app_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "selection_id": selection.id,
        "project_id": dataset.project_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "dataset_format": dataset.format,
        "source_sha256": dataset.source_sha256,
        "chart_id": render.get("chart_id"),
        "renderer": render.get("renderer"),
        "fields": fields,
        "style": (result.get("selected") or {}).get("style"),
        "provider_name": selection.provider_name,
        "model": selection.model,
        "prompt_version": selection.prompt_version,
        "row_count": render.get("row_count"),
        "sampled": render.get("sampled"),
        "sensitive_fields_used": used_sensitive,
        "share_bundle": bundle_name,
        "share_bundle_bytes": bundle_bytes,
        "single_file_bytes": None,
    }
    (export_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (export_dir / "index.html").write_text(
        _index_html(payload, selection.id, bundle_name), encoding="utf-8"
    )
    return {
        "directory": str(export_dir),
        "files": sorted(item.name for item in export_dir.iterdir() if item.is_file()),
        "manifest": manifest,
    }


def build_single_file_html(
    session: Session,
    selection: ChartSelection,
) -> Path:
    """Inline the selected renderer bundle, CSS, and payload into one HTML file."""
    package = build_share_package(session, selection)
    directory = Path(package["directory"])
    manifest = package["manifest"]
    bundle_name = str(manifest["share_bundle"])
    bundle_path = directory / bundle_name
    css_path = directory / "share.css"
    payload_path = directory / "payload.json"
    js = bundle_path.read_text(encoding="utf-8") if bundle_path.is_file() else ""
    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    payload_json = payload_path.read_text(encoding="utf-8")
    html = _single_file_html(payload_json, js, css, selection.id)
    output = directory / "single.html"
    output.write_text(html, encoding="utf-8")
    manifest["single_file_bytes"] = len(html.encode("utf-8"))
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def zip_share_package(
    session: Session,
    selection: ChartSelection,
) -> BytesIO:
    """Return the share directory as an in-memory zip."""
    package = build_share_package(session, selection)
    directory = Path(package["directory"])
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in directory.iterdir():
            if item.is_file():
                archive.write(item, arcname=item.name)
    buffer.seek(0)
    return buffer


def build_pdf(session: Session, selection: ChartSelection) -> Path:
    """Print the share page to PDF using Playwright with the system Edge channel."""
    package = build_share_package(session, selection)
    directory = Path(package["directory"])
    pdf_path = directory / "report.pdf"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError(
            "pdf_runtime_unavailable",
            "Playwright is not installed; install backend dependencies first",
            503,
        ) from exc
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                raise ExportError(
                    "pdf_runtime_unavailable",
                    "no Edge/Chromium runtime is available for PDF export",
                    503,
                ) from exc
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto((directory / "index.html").as_uri(), wait_until="load")
            with contextlib.suppress(Exception):
                page.wait_for_function("window.__ADVP_READY__ === true", timeout=15000)
            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
            )
        finally:
            browser.close()
    return pdf_path


def capture_selection_png(
    session: Session,
    selection: ChartSelection,
    output: Path,
) -> Path:
    """Capture the offline share chart as a PNG for report embedding."""
    package = build_share_package(session, selection)
    directory = Path(package["directory"])
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError(
            "chart_capture_unavailable",
            "Playwright is not installed; install backend dependencies first",
            503,
        ) from exc
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                raise ExportError(
                    "chart_capture_unavailable",
                    "no Edge/Chromium runtime is available for chart capture",
                    503,
                ) from exc
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto((directory / "index.html").as_uri(), wait_until="load")
            with contextlib.suppress(Exception):
                page.wait_for_function("window.__ADVP_READY__ === true", timeout=15000)
            page.locator(".share-figure").screenshot(path=str(output))
        finally:
            browser.close()
    return output


def build_report_pdf(html_path: Path) -> Path:
    """Print a standalone HTML report to PDF using Playwright with Edge."""
    pdf_path = html_path.with_suffix(".pdf")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError(
            "pdf_runtime_unavailable",
            "Playwright is not installed; install backend dependencies first",
            503,
        ) from exc
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                raise ExportError(
                    "pdf_runtime_unavailable",
                    "no Edge/Chromium runtime is available for PDF export",
                    503,
                ) from exc
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(html_path.as_uri(), wait_until="load")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
            )
        finally:
            browser.close()
    return pdf_path


def build_python(
    session: Session,
    selection: ChartSelection,
) -> str:
    dataset = session.get(Dataset, selection.dataset_id)
    if dataset is None:
        raise ExportError("dataset_not_found", "selection dataset no longer exists", 404)
    render = render_service.render_selection(session, selection)
    return code_export.build_python_script(dataset=dataset, selection=selection, render=render)


def build_notebook(
    session: Session,
    selection: ChartSelection,
) -> dict[str, Any]:
    return code_export.build_notebook(build_python(session, selection))


def build_code_view(
    session: Session,
    selection: ChartSelection,
) -> dict[str, Any]:
    """Return generated Python alongside a unified diff against its parent."""
    code = build_python(session, selection)
    parent = (
        session.get(ChartSelection, selection.parent_selection_id)
        if selection.parent_selection_id
        else None
    )
    parent_code = build_python(session, parent) if parent is not None else None
    diff = ""
    if parent is not None and parent_code is not None:
        diff = "\n".join(
            difflib.unified_diff(
                parent_code.splitlines(),
                code.splitlines(),
                fromfile=f"selection-{parent.id}.py",
                tofile=f"selection-{selection.id}.py",
                lineterm="",
            )
        )
    return {
        "selection_id": selection.id,
        "language": "python",
        "filename": f"advp-{selection.id}.py",
        "code": code,
        "parent_selection_id": parent.id if parent is not None else None,
        "diff": diff,
        "changed": bool(parent_code is not None and parent_code != code),
    }


def _sensitive_columns(dataset: Dataset) -> set[str]:
    columns = dataset.profile_json.get("columns") or []
    return {
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("sensitive")
    }


def _default_imaging_slice(dataset: Dataset) -> dict[str, Any] | None:
    try:
        meta = imaging_service.imaging_meta(dataset)
        axis = meta.get("default_axis")
        if axis is None:
            axis = 0
        return imaging_service.read_slice(dataset, axis=int(axis), index=0)
    except Exception:
        return None


def _share_dir() -> Path:
    configured = get_settings().share_dir
    candidates = [
        configured,
        Path(sys.executable).resolve().parent.parent / "static-share",
        ROOT / "frontend" / "dist-share",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "share-plotly.js").is_file():
            return candidate
    return ROOT / "frontend" / "dist-share"


def _copy_share_assets(export_dir: Path, renderer: str) -> tuple[str, int]:
    dist = _share_dir()
    bundle_name = f"share-{renderer}.js"
    source_js = dist / bundle_name
    if source_js.is_file():
        shutil.copy2(source_js, export_dir / bundle_name)
        source_css = dist / "share.css"
        if source_css.is_file():
            shutil.copy2(source_css, export_dir / "share.css")
        return bundle_name, (export_dir / bundle_name).stat().st_size
    (export_dir / bundle_name).write_text(
        "window.__ADVP_READY__ = true;\n"
        "document.getElementById('root').textContent = "
        "'Share bundle is missing; run npm run build:share in frontend.';\n",
        encoding="utf-8",
    )
    return bundle_name, (export_dir / bundle_name).stat().st_size


def _index_html(payload: dict[str, Any], selection_id: str, bundle_name: str) -> str:
    encoded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ADVP {selection_id}</title>
  <link rel="stylesheet" href="share.css" />
  <style>
    body {{ margin: 0; background: #081120; color: #e5eefc; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
    main {{ padding: 20px; }}
    #root {{ min-height: 520px; }}
  </style>
</head>
<body>
  <main id="root"></main>
  <script>window.__ADVP_SHARE__ = {encoded};</script>
  <script type="module" src="{bundle_name}"></script>
</body>
</html>
"""


def _single_file_html(payload_json: str, js: str, css: str, selection_id: str) -> str:
    safe_payload = payload_json.replace("</", "<\\/")
    safe_js = js.replace("</script", "<\\/script")
    safe_css = css.replace("</style", "<\\/style")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ADVP {selection_id}</title>
  <style>{safe_css}</style>
  <style>
    body {{ margin: 0; background: #081120; color: #e5eefc; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
    main {{ padding: 20px; }}
    #root {{ min-height: 520px; }}
  </style>
</head>
<body>
  <main id="root"></main>
  <script>window.__ADVP_SHARE__ = {safe_payload};</script>
  <script type="module">{safe_js}</script>
</body>
</html>
"""
