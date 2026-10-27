"""Extract tables from static HTML pages and materialize them as CSV."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd  # type: ignore[import-untyped]

from advp.ingest.files import (
    InvalidSourceError,
    unique_headers,
)
from advp.ingest.remote import RemoteFetchError, auth_headers

MAX_WEB_BYTES = 50 * 1024 * 1024
MAX_WEB_TABLES = 50
MAX_PREVIEW_ROWS = 10


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


def _fetch_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise InvalidSourceError(
            "only http and https URLs are supported",
            hint="use an HTTP(S) page URL",
        )
    request_headers = dict(headers or {})
    request_headers.update(auth_headers(auth))
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=timeout) as client,
            client.stream("GET", url, headers=request_headers) as response,
        ):
            response.raise_for_status()
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


def fetch_web_tables(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> list[WebTable]:
    html = _fetch_html(url, headers=headers, auth=auth, timeout=timeout)
    try:
        frames = pd.read_html(io.StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise InvalidSourceError(
            "no HTML tables were found on the page",
            hint="the page may need JavaScript; dynamic rendering is not enabled in this build",
        ) from exc
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
    if not tables:
        raise InvalidSourceError(
            "no usable HTML tables were found on the page",
            hint="the page may need JavaScript; dynamic rendering is not enabled in this build",
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
