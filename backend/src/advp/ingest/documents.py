"""Extract candidate tables from PDF and Word documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docx
import pdfplumber
import polars as pl

from advp.ingest.files import (
    FileTooLargeError,
    InvalidSourceError,
    UnsupportedFormatError,
    coerce_value,
    unique_headers,
)

MAX_DOCUMENT_BYTES = 200 * 1024 * 1024
MAX_DOCUMENT_TABLES = 50
MAX_PREVIEW_ROWS = 10


@dataclass(slots=True)
class DocumentTable:
    index: int
    source: str
    page: int | None
    table_index: int
    rows: list[list[str]]
    headers: list[str]
    has_header: bool
    row_count: int
    column_count: int
    confidence: float

    @property
    def data_rows(self) -> list[list[str]]:
        return self.rows[1:] if self.has_header and self.rows else self.rows


def _validate(path: Path) -> str:
    if not path.exists():
        raise InvalidSourceError(f"document was not found: {path.name}")
    if not path.is_file():
        raise InvalidSourceError(f"document path is not a file: {path.name}")
    suffix = path.suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise UnsupportedFormatError(
            f"unsupported document format: {suffix or '<none>'}",
            hint="supported formats: PDF and DOCX",
        )
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise FileTooLargeError(
            "document is above the 200 MB limit",
            hint="split the document or extract the table externally",
        )
    return suffix


def _confidence(rows: list[list[str]]) -> float:
    if not rows:
        return 0.0
    width = max(len(row) for row in rows)
    total_cells = sum(len(row) for row in rows) or 1
    filled = sum(1 for row in rows for cell in row if str(cell).strip())
    fill_ratio = filled / total_cells
    consistent = sum(1 for row in rows if len(row) == width) / len(rows)
    header = 1.0 if any(str(cell).strip() for cell in rows[0]) else 0.0
    return round(0.5 * fill_ratio + 0.3 * consistent + 0.2 * header, 3)


def _make_table(
    *,
    index: int,
    source: str,
    page: int | None,
    table_index: int,
    raw_rows: list[list[Any]],
) -> DocumentTable | None:
    rows = [[str(cell).strip() if cell is not None else "" for cell in row] for row in raw_rows]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return None
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    headers = unique_headers(rows[0], width)
    return DocumentTable(
        index=index,
        source=source,
        page=page,
        table_index=table_index,
        rows=rows,
        headers=headers,
        has_header=True,
        row_count=max(len(rows) - 1, 0),
        column_count=width,
        confidence=_confidence(rows),
    )


def _extract_pdf(path: Path) -> list[DocumentTable]:
    tables: list[DocumentTable] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table_index, raw in enumerate(page.extract_tables() or []):
                    table = _make_table(
                        index=len(tables),
                        source="pdf",
                        page=page_number,
                        table_index=table_index,
                        raw_rows=raw,
                    )
                    if table is not None:
                        tables.append(table)
                    if len(tables) >= MAX_DOCUMENT_TABLES:
                        return tables
    except Exception as exc:
        raise InvalidSourceError(f"cannot extract PDF tables: {exc}") from exc
    return tables


def _extract_docx(path: Path) -> list[DocumentTable]:
    tables: list[DocumentTable] = []
    try:
        document = docx.Document(str(path))
        for table_index, table in enumerate(document.tables):
            raw = [[cell.text for cell in row.cells] for row in table.rows]
            candidate = _make_table(
                index=len(tables),
                source="docx",
                page=None,
                table_index=table_index,
                raw_rows=raw,
            )
            if candidate is not None:
                tables.append(candidate)
            if len(tables) >= MAX_DOCUMENT_TABLES:
                break
    except Exception as exc:
        raise InvalidSourceError(f"cannot extract Word tables: {exc}") from exc
    return tables


def extract_document_tables(path_value: str) -> list[DocumentTable]:
    path = Path(path_value).expanduser().resolve()
    suffix = _validate(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    return _extract_docx(path)


def table_summary(table: DocumentTable) -> dict[str, Any]:
    return {
        "index": table.index,
        "source": table.source,
        "page": table.page,
        "table_index": table.table_index,
        "row_count": table.row_count,
        "column_count": table.column_count,
        "confidence": table.confidence,
        "headers": table.headers,
        "preview": table.data_rows[:MAX_PREVIEW_ROWS],
    }


def materialize_document_table(
    path_value: str,
    table_index: int,
    output: Path,
    *,
    has_header: bool,
) -> DocumentTable:
    tables = extract_document_tables(path_value)
    if not tables:
        raise InvalidSourceError(
            "document contains no tables",
            hint=(
                "only tables in PDF/DOCX are supported; "
                "text paragraphs, scanned pages, and images are not extracted"
            ),
        )
    if table_index < 0 or table_index >= len(tables):
        raise InvalidSourceError(
            f"document table index is out of range: {table_index}",
            hint=f"available tables: 0..{len(tables) - 1}",
        )
    table = tables[table_index]
    table.has_header = has_header
    if not has_header:
        table.headers = [f"column_{index + 1}" for index in range(table.column_count)]
    data_rows = table.rows[1:] if has_header and table.rows else table.rows
    records = [
        {
            header: coerce_value(row[index]) if index < len(row) else None
            for index, header in enumerate(table.headers)
        }
        for row in data_rows
    ]
    if records:
        frame = pl.DataFrame(
            records,
            infer_schema_length=max(len(records), 1),
            strict=False,
        )
    else:
        frame = pl.DataFrame({header: [] for header in table.headers})
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(output)
    return table
