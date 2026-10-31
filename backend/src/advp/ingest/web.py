"""Extract tables from static or JavaScript-rendered HTML pages."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd  # type: ignore[import-untyped]

from advp.config import get_settings
from advp.ingest.files import (
    InvalidSourceError,
    unique_headers,
)
from advp.ingest.remote import RemoteFetchError, auth_headers
from advp.ingest.url_guard import validate_public_address, validate_public_url

MAX_WEB_BYTES = 50 * 1024 * 1024
MAX_WEB_TABLES = 50
MAX_PREVIEW_ROWS = 10
MAX_REDIRECTS = 5


class RenderUnavailable(RuntimeError):
    """Headless browser rendering is unavailable or failed."""


@dataclass(slots=True)
class WebTable:
    index: int
    url: str
    row_count: int
    column_count: int
    confidence: float
    headers: list[str]
    preview: list[list[str]]
    frame: pd.DataFrame


def fetch_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
    allow_private: bool = False,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise InvalidSourceError(
            "only http and https URLs are supported",
            hint="use an HTTP(S) page URL",
        )
    request_headers = dict(headers or {})
    request_headers.update(auth_headers(auth))
    current = url
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", current, headers=request_headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise RemoteFetchError(
                                "web redirect has no location header",
                                hint="check the URL or fetch the final page directly",
                            )
                        current = _redirect_target(
                            current,
                            location,
                            allow_private=allow_private,
                        )
                        continue
                    response.raise_for_status()
                    _check_peer(response, allow_private=allow_private)
                    declared = response.headers.get("content-length")
                    if declared is not None and int(declared) > MAX_WEB_BYTES:
                        raise InvalidSourceError(
                            "web page is above the 50 MB limit",
                            hint="use a smaller page or a direct data URL",
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_WEB_BYTES:
                            raise InvalidSourceError(
                                "web page exceeded the 50 MB limit",
                                hint="use a smaller page or a direct data URL",
                            )
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    return b"".join(chunks).decode(encoding, errors="replace")
            raise RemoteFetchError(
                "web page redirected too many times",
                hint="check the URL or fetch the final page directly",
            )
    except httpx.HTTPStatusError as exc:
        raise RemoteFetchError(
            f"web page returned HTTP {exc.response.status_code}",
            hint="check the URL and access policy",
        ) from exc
    except httpx.HTTPError as exc:
        raise RemoteFetchError(
            f"web request failed: {exc}",
            hint="check network access, TLS, and the URL",
        ) from exc


def _redirect_target(current: str, location: str, *, allow_private: bool) -> str:
    target = urljoin(current, location)
    validate_public_url(target, allow_private=allow_private)
    return target


def _check_peer(response: httpx.Response, *, allow_private: bool) -> None:
    if allow_private:
        return
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    try:
        peer = stream.get_extra_info("server_addr")
    except Exception:
        return
    if peer:
        validate_public_address(str(peer[0]))


def _render_request_allowed(url: str, *, allow_private: bool) -> bool:
    if urlparse(url).scheme in {"data", "blob", "about"}:
        return True
    try:
        validate_public_url(url, allow_private=allow_private)
    except ValueError:
        return False
    return True


def render_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
    allow_private: bool | None = None,
) -> str:
    if allow_private is None:
        allow_private = get_settings().allow_private_web
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderUnavailable("Playwright is not installed") from exc
    request_headers = dict(headers or {})
    request_headers.update(auth_headers(auth))

    def _route(route: Any) -> None:
        if _render_request_allowed(route.request.url, allow_private=bool(allow_private)):
            route.continue_()
        else:
            route.abort()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            try:
                context = browser.new_context(extra_http_headers=request_headers)
                context.route("**/*", _route)
                page = context.new_page()
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                html = page.content()
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise RenderUnavailable(f"dynamic rendering failed: {exc}") from exc
    if len(html.encode("utf-8")) > MAX_WEB_BYTES:
        raise RenderUnavailable("rendered page exceeded the 50 MB limit")
    return html


def extract_tables(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
    allow_private: bool | None = None,
) -> dict[str, Any]:
    """Fetch a page, falling back to headless rendering when it has no tables."""
    if allow_private is None:
        allow_private = get_settings().allow_private_web
    validate_public_url(url, allow_private=allow_private)
    started = time.perf_counter()
    html = fetch_html(
        url,
        headers=headers,
        auth=auth,
        timeout=timeout,
        allow_private=allow_private,
    )
    tables = _parse_tables(url, html)
    source: Literal["static", "rendered"] = "static"
    warning: str | None = None
    if not tables:
        try:
            rendered = render_html(
                url,
                headers=headers,
                auth=auth,
                timeout=timeout,
                allow_private=allow_private,
            )
        except RenderUnavailable as exc:
            warning = str(exc)
        else:
            tables = _parse_tables(url, rendered)
            source = "rendered"
            if not tables:
                warning = "no tables were found after dynamic rendering"
    return {
        "url": url,
        "source": source,
        "tables": tables,
        "warning": warning,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def fetch_web_tables(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> list[WebTable]:
    result = extract_tables(url, headers=headers, auth=auth, timeout=timeout)
    tables: list[WebTable] = result["tables"]
    if not tables:
        raise InvalidSourceError(
            "no usable HTML tables were found on the page",
            hint=result["warning"]
            or "the page may need JavaScript; dynamic rendering found no tables",
        )
    return tables


def _parse_tables(url: str, html: str) -> list[WebTable]:
    try:
        frames = pd.read_html(io.StringIO(html), flavor="lxml")
    except ValueError:
        return []
    tables: list[WebTable] = []
    for index, frame in enumerate(frames[:MAX_WEB_TABLES]):
        if frame.empty:
            continue
        table_headers = unique_headers([str(column) for column in frame.columns], frame.shape[1])
        fill = float(frame.notna().to_numpy().mean()) if frame.size else 0.0
        unnamed = sum(1 for column in frame.columns if str(column).startswith("Unnamed"))
        header_quality = 1.0 - (unnamed / max(frame.shape[1], 1))
        confidence = round(0.7 * fill + 0.3 * header_quality, 3)
        preview = frame.head(MAX_PREVIEW_ROWS).fillna("").astype(str).values.tolist()
        tables.append(
            WebTable(
                index=index,
                url=url,
                row_count=int(frame.shape[0]),
                column_count=int(frame.shape[1]),
                confidence=confidence,
                headers=table_headers,
                preview=preview,
                frame=frame,
            )
        )
    return tables


def table_summary(table: WebTable) -> dict[str, Any]:
    return {
        "index": table.index,
        "row_count": table.row_count,
        "column_count": table.column_count,
        "confidence": table.confidence,
        "headers": table.headers,
        "preview": table.preview,
    }


def materialize_web_table(
    url: str,
    table_index: int,
    output: Path,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> WebTable:
    tables = fetch_web_tables(url, headers=headers, auth=auth, timeout=timeout)
    if table_index < 0 or table_index >= len(tables):
        raise InvalidSourceError(
            f"web table index is out of range: {table_index}",
            hint=f"available tables: 0..{max(len(tables) - 1, 0)}",
        )
    table = tables[table_index]
    output.parent.mkdir(parents=True, exist_ok=True)
    table.frame.to_csv(output, index=False, encoding="utf-8")
    return table
