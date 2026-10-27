"""Inspect and read tabular source files without copying them."""

from __future__ import annotations

import codecs
import csv
import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
from charset_normalizer import from_bytes

MAX_SAMPLE_ROWS = 100_000
MAX_PREVIEW_ROWS = 200
EXACT_ROW_COUNT_LIMIT = 200 * 1024 * 1024

FORMAT_BY_SUFFIX = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".xlsx": "excel",
    ".xls": "excel",
}
NULL_VALUES = ["", "NA", "N/A", "null", "NULL", "None", "none"]
NUMERIC_INT = re.compile(r"^[+-]?\d+$")
NUMERIC_FLOAT = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


class IngestError(Exception):
    """Base error with a stable API code and HTTP status."""

    code = "ingest_error"
    status_code = 400

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class SourceNotFoundError(IngestError):
    code = "source_not_found"
    status_code = 404


class InvalidSourceError(IngestError):
    code = "invalid_source"
    status_code = 400


class UnsupportedFormatError(IngestError):
    code = "unsupported_format"
    status_code = 415


class FileTooLargeError(IngestError):
    code = "file_too_large"
    status_code = 413


class CorruptFileError(IngestError):
    code = "corrupt_file"
    status_code = 422


class SourceChangedError(IngestError):
    code = "source_changed"
    status_code = 409


@dataclass(slots=True)
class ImportOptions:
    """User overrides and sampling controls for one import."""

    encoding: str | None = None
    delimiter: str | None = None
    has_header: bool | None = None
    sheet: int | str | None = None
    variable: str | None = None
    shape: list[int] | None = None
    dtype: str | None = None
    byte_order: str | None = None
    raw_offset: int = 0
    sample_rows: int = MAX_SAMPLE_ROWS
    preview_rows: int = 20

    def normalized(self, *, default_sample_rows: int) -> ImportOptions:
        sample_rows = min(max(self.sample_rows, 1), default_sample_rows)
        preview_rows = min(max(self.preview_rows, 1), MAX_PREVIEW_ROWS)
        delimiter = self.delimiter
        if delimiter is not None and len(delimiter) != 1:
            raise InvalidSourceError("delimiter must be a single character")
        return ImportOptions(
            encoding=self.encoding,
            delimiter=delimiter,
            has_header=self.has_header,
            sheet=self.sheet,
            variable=self.variable,
            shape=self.shape,
            dtype=self.dtype,
            byte_order=self.byte_order,
            raw_offset=max(self.raw_offset, 0),
            sample_rows=sample_rows,
            preview_rows=preview_rows,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "has_header": self.has_header,
            "sheet": self.sheet,
            "variable": self.variable,
            "shape": self.shape,
            "dtype": self.dtype,
            "byte_order": self.byte_order,
            "raw_offset": self.raw_offset,
            "sample_rows": self.sample_rows,
            "preview_rows": self.preview_rows,
        }


@dataclass(slots=True)
class LoadedFile:
    """Sampled data plus effective import settings and metadata."""

    path: Path
    format: str
    size_bytes: int
    mtime: float
    frame: pl.DataFrame
    row_count: int
    row_count_estimated: bool
    sampled: bool
    options: dict[str, Any]
    detected: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_source(path: Path) -> str:
    """Hash a file, or a directory as a sorted manifest of file hashes."""
    if not path.is_dir():
        return sha256_file(path)
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def resolve_source(path_value: str, max_file_bytes: int) -> tuple[Path, str, int, float]:
    """Validate a source path and return path, format, size, and mtime."""
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise SourceNotFoundError(
            f"source file was not found: {path.name}",
            hint="check the path or relocate the dataset",
        )
    if not path.is_file():
        raise InvalidSourceError(f"source path is not a file: {path.name}")
    suffix = path.suffix.lower()
    file_format = FORMAT_BY_SUFFIX.get(suffix)
    if file_format is None:
        supported = ", ".join(sorted(FORMAT_BY_SUFFIX))
        raise UnsupportedFormatError(
            f"unsupported file format: {suffix or '<none>'}",
            hint=f"supported formats: {supported}",
        )
    size = path.stat().st_size
    if size > max_file_bytes:
        limit_gb = max_file_bytes / (1024**3)
        raise FileTooLargeError(
            f"file is {size / (1024**3):.2f} GiB, above the {limit_gb:.2f} GiB limit",
            hint="split the file, use a database connector, or raise the configured limit",
        )
    return path, file_format, size, path.stat().st_mtime


def detect_encoding(path: Path) -> str:
    """Detect text encoding from BOM, UTF-8 validity, then charset-normalizer."""
    raw = path.open("rb").read(65536)
    for bom, encoding in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if raw.startswith(bom):
            return encoding
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    best = from_bytes(raw).best()
    if best is not None and best.encoding:
        encoding = best.encoding.lower()
        if encoding in {"ascii", "utf_8", "utf-8"}:
            return "utf-8"
        if encoding.startswith("utf_16"):
            return "utf-16"
        return encoding
    return "utf-8"


def read_text_sample(path: Path, encoding: str, size: int = 1024 * 1024) -> str:
    """Read a decoded prefix for delimiter and header detection."""
    try:
        with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
            return handle.read(size)
    except LookupError as exc:
        raise InvalidSourceError(f"unknown encoding: {encoding}") from exc


def detect_delimiter(text: str, suffix: str) -> str:
    """Detect a CSV delimiter, honoring the TSV suffix."""
    if suffix.lower() == ".tsv":
        return "\t"
    sample = "\n".join(line for line in text.splitlines()[:30] if line.strip())
    if sample:
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            pass
        first = sample.splitlines()[0]
        counts = {candidate: first.count(candidate) for candidate in ",;\t|"}
        best = max(counts, key=lambda item: counts[item])
        if counts[best] > 0:
            return best
    return ","


def detect_header(text: str, delimiter: str) -> bool:
    """Use csv.Sniffer for header detection with a safe default."""
    sample = "\n".join(line for line in text.splitlines()[:30] if line.strip())
    if not sample:
        return True
    try:
        return bool(csv.Sniffer().has_header(sample))
    except csv.Error:
        return True


def unique_headers(raw: list[str], width: int) -> list[str]:
    """Normalize empty or duplicate headers and pad to the data width."""
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        base = raw[index].strip() if index < len(raw) and raw[index].strip() else ""
        if not base:
            base = f"column_{index + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        headers.append(base if count == 1 else f"{base}_{count}")
    return headers


def coerce_value(value: str) -> Any:
    """Convert a CSV string to a conservative Python scalar."""
    stripped = value.strip()
    if stripped in NULL_VALUES:
        return None
    if NUMERIC_INT.fullmatch(stripped):
        digits = stripped.lstrip("+-")
        if len(digits) > 1 and digits.startswith("0"):
            return stripped
        try:
            return int(stripped)
        except ValueError:
            return stripped
    if NUMERIC_FLOAT.fullmatch(stripped) and any(char in stripped for char in ".eE"):
        try:
            return float(stripped)
        except ValueError:
            return stripped
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    try:
        if len(stripped) == 10:
            return date.fromisoformat(stripped)
        if "T" in stripped or " " in stripped:
            return datetime.fromisoformat(stripped)
    except ValueError:
        pass
    return stripped


def read_csv_fallback(
    path: Path,
    encoding: str,
    delimiter: str,
    has_header: bool,
    sample_rows: int,
) -> tuple[pl.DataFrame, int, bool, bool]:
    """Read a CSV sample with the stdlib for non-UTF-8 encodings."""
    try:
        with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            raw_rows: list[list[str]] = []
            target = sample_rows + (1 if has_header else 0)
            for row in reader:
                raw_rows.append(row)
                if len(raw_rows) >= target:
                    break
            exhausted = len(raw_rows) < target
            if not exhausted:
                try:
                    next(reader)
                except StopIteration:
                    exhausted = True
    except LookupError as exc:
        raise InvalidSourceError(f"unknown encoding: {encoding}") from exc
    except OSError as exc:
        raise CorruptFileError(f"cannot read CSV: {exc}") from exc

    header_raw = raw_rows[0] if has_header and raw_rows else []
    data_rows = raw_rows[1:] if has_header and raw_rows else raw_rows
    width = max(
        [len(header_raw)] + [len(row) for row in data_rows] + [0],
    )
    headers = unique_headers(header_raw, width)
    records: list[dict[str, Any]] = []
    for row in data_rows[:sample_rows]:
        padded = list(row) + [""] * (width - len(row))
        records.append(
            {header: coerce_value(padded[index]) for index, header in enumerate(headers)}
        )
    if not records:
        frame = pl.DataFrame({header: [] for header in headers})
    else:
        frame = pl.DataFrame(
            records,
            infer_schema_length=len(records),
            strict=False,
        )
    if exhausted:
        return frame, len(records), False, True
    row_bytes = path.stat().st_size / max(len(records) + (1 if has_header else 0), 1)
    estimated = max(len(records), int(math.ceil(path.stat().st_size / row_bytes)))
    return frame, estimated, True, False


def _polars_csv_options(
    delimiter: str,
    has_header: bool,
    sample_rows: int,
) -> dict[str, Any]:
    return {
        "separator": delimiter,
        "has_header": has_header,
        "encoding": "utf8",
        "infer_schema_length": sample_rows,
        "try_parse_dates": True,
        "null_values": NULL_VALUES,
        "truncate_ragged_lines": True,
    }


def read_csv_polars(
    path: Path,
    delimiter: str,
    has_header: bool,
    sample_rows: int,
) -> tuple[pl.DataFrame, int, bool, bool]:
    """Read a UTF-8 CSV sample and estimate or count rows."""
    options = _polars_csv_options(delimiter, has_header, sample_rows)
    try:
        frame = pl.read_csv(path, n_rows=sample_rows, **options)
    except Exception as exc:
        raise CorruptFileError(f"cannot parse CSV: {exc}") from exc

    size = path.stat().st_size
    if size <= EXACT_ROW_COUNT_LIMIT:
        try:
            lazy = pl.scan_csv(path, **options)
            row_count = int(lazy.select(pl.len()).collect().item())
        except Exception as exc:
            raise CorruptFileError(f"cannot count CSV rows: {exc}") from exc
        return frame, row_count, row_count > frame.height, False

    estimated_size = frame.estimated_size()
    avg_row = estimated_size / max(frame.height, 1)
    estimated = max(frame.height, int(math.ceil(size / max(avg_row, 1))))
    return frame, estimated, True, True


def _read_other_format(
    path: Path,
    file_format: str,
    sheet: int | str | None,
    sample_rows: int,
) -> tuple[pl.DataFrame, int, bool, bool]:
    if file_format == "json":
        try:
            full = pl.read_json(path)
        except Exception as exc:
            raise CorruptFileError(f"cannot parse JSON: {exc}") from exc
        row_count = full.height
        return full.head(sample_rows), row_count, row_count > sample_rows, False
    if file_format == "jsonl":
        try:
            lazy = pl.scan_ndjson(path, infer_schema_length=min(sample_rows, 10000))
            frame = lazy.head(sample_rows).collect()
            row_count = int(lazy.select(pl.len()).collect().item())
        except Exception as exc:
            raise CorruptFileError(f"cannot parse JSONL: {exc}") from exc
        return frame, row_count, row_count > frame.height, False
    if file_format == "parquet":
        try:
            lazy = pl.scan_parquet(path)
            frame = lazy.head(sample_rows).collect()
            row_count = int(lazy.select(pl.len()).collect().item())
        except Exception as exc:
            raise CorruptFileError(f"cannot parse Parquet: {exc}") from exc
        return frame, row_count, row_count > frame.height, False
    if file_format == "excel":
        try:
            if isinstance(sheet, str):
                full = pl.read_excel(path, sheet_name=sheet, engine="calamine")
            else:
                full = pl.read_excel(
                    path, sheet_id=sheet if sheet is not None else 0, engine="calamine"
                )
        except Exception as exc:
            raise CorruptFileError(
                f"cannot parse Excel workbook: {exc}",
                hint="check the sheet name and that the file is not encrypted",
            ) from exc
        if isinstance(full, dict):
            full = next(iter(full.values()))
        row_count = full.height
        return full.head(sample_rows), row_count, row_count > sample_rows, False
    raise UnsupportedFormatError(f"unsupported file format: {file_format}")


def inspect_file(
    path_value: str,
    options: ImportOptions | None,
    *,
    max_file_bytes: int,
    default_sample_rows: int,
) -> LoadedFile:
    """Inspect a tabular file and return a sampled frame plus metadata."""
    effective = (options or ImportOptions()).normalized(default_sample_rows=default_sample_rows)
    path, file_format, size, mtime = resolve_source(path_value, max_file_bytes)
    detected: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []

    if file_format in {"csv", "tsv"}:
        encoding = effective.encoding or detect_encoding(path)
        text = read_text_sample(path, encoding)
        delimiter = effective.delimiter or detect_delimiter(text, path.suffix)
        has_header = (
            effective.has_header
            if effective.has_header is not None
            else detect_header(text, delimiter)
        )
        if effective.encoding is None:
            detected["encoding"] = encoding
        if effective.delimiter is None:
            detected["delimiter"] = delimiter
        if effective.has_header is None:
            detected["has_header"] = has_header

        with path.open("rb") as probe:
            has_bom = probe.read(3) == codecs.BOM_UTF8
        if encoding.lower() in {"utf-8", "ascii"} and not has_bom:
            frame, row_count, sampled, estimated = read_csv_polars(
                path, delimiter, has_header, effective.sample_rows
            )
        else:
            frame, row_count, sampled, estimated = read_csv_fallback(
                path, encoding, delimiter, has_header, effective.sample_rows
            )
        if encoding.lower() not in {"utf-8", "utf-8-sig", "ascii"}:
            issues.append(
                {
                    "code": "non_utf8_encoding",
                    "severity": "info",
                    "message": (
                        f"file decoded as {encoding}; preview may replace invalid characters"
                    ),
                }
            )
        effective.encoding = encoding
        effective.delimiter = delimiter
        effective.has_header = has_header
    else:
        frame, row_count, sampled, estimated = _read_other_format(
            path, file_format, effective.sheet, effective.sample_rows
        )
        if file_format == "excel":
            detected["sheet"] = effective.sheet if effective.sheet is not None else 0

    if size > 1024**3:
        issues.append(
            {
                "code": "large_file",
                "severity": "info",
                "message": "large file: profiling uses a sample and marks results as sampled",
            }
        )
    if sampled:
        issues.append(
            {
                "code": "sampled",
                "severity": "info",
                "message": f"profile uses the first {frame.height} of {row_count} rows",
            }
        )
    if estimated:
        issues.append(
            {
                "code": "estimated_row_count",
                "severity": "info",
                "message": "row count is estimated from file size",
            }
        )

    return LoadedFile(
        path=path,
        format=file_format,
        size_bytes=size,
        mtime=mtime,
        frame=frame,
        row_count=row_count,
        row_count_estimated=estimated,
        sampled=sampled,
        options=effective.as_dict(),
        detected=detected,
        issues=issues,
    )


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def frame_to_rows(frame: pl.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    """Convert a DataFrame slice into JSON-safe records."""
    selected = frame.head(limit) if limit is not None else frame
    return [
        {str(key): _json_safe(value) for key, value in row.items()}
        for row in selected.iter_rows(named=True)
    ]


def _dtype_from_name(physical: str) -> Any:
    if physical.startswith("Datetime"):
        return pl.Datetime
    if physical.startswith("String"):
        return pl.String
    if physical.startswith("Categorical"):
        return pl.Categorical
    if physical.startswith("Decimal"):
        return pl.Float64
    if physical in {
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Float32",
        "Float64",
        "Boolean",
        "Date",
        "Time",
    }:
        return getattr(pl, physical)
    return None


def _schema_overrides(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not schema:
        return {}
    overrides: dict[str, Any] = {}
    for column in schema.get("columns", []):
        name = column.get("name")
        physical = str(column.get("physical_type", ""))
        if not name:
            continue
        dtype = _dtype_from_name(physical)
        if dtype is not None:
            overrides[str(name)] = dtype
    return overrides


def read_preview(
    path_value: str,
    options: dict[str, Any],
    *,
    limit: int,
    offset: int,
    max_file_bytes: int,
    schema: dict[str, Any] | None = None,
    max_limit: int = MAX_PREVIEW_ROWS,
) -> list[dict[str, Any]]:
    """Read a page of rows directly from the source file."""
    limit = min(max(limit, 1), max_limit)
    offset = max(offset, 0)
    effective = ImportOptions(
        encoding=options.get("encoding"),
        delimiter=options.get("delimiter"),
        has_header=options.get("has_header"),
        sheet=options.get("sheet"),
        sample_rows=max(offset + limit, 1),
        preview_rows=limit,
    ).normalized(default_sample_rows=max(offset + limit, 1))
    path, file_format, _size, _mtime = resolve_source(path_value, max_file_bytes)
    if file_format in {"csv", "tsv"}:
        encoding = effective.encoding or "utf-8"
        delimiter = effective.delimiter or ("," if file_format == "csv" else "\t")
        has_header = effective.has_header if effective.has_header is not None else True
        if encoding.lower() in {"utf-8", "ascii"}:
            options_polars = _polars_csv_options(delimiter, has_header, offset + limit)
            overrides = _schema_overrides(schema)
            if overrides:
                options_polars["schema_overrides"] = overrides
            if has_header:
                options_polars["skip_rows_after_header"] = offset
            else:
                options_polars["skip_rows"] = offset
            try:
                frame = pl.read_csv(path, n_rows=limit, **options_polars)
            except Exception as exc:
                raise CorruptFileError(f"cannot parse CSV preview: {exc}") from exc
            return frame_to_rows(frame)
        headers: list[str] = []
        try:
            with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                raw: list[list[str]] = []
                for index, row in enumerate(reader):
                    if has_header and index == 0:
                        headers = unique_headers(row, len(row))
                        continue
                    if index < offset + (1 if has_header else 0):
                        continue
                    raw.append(row)
                    if len(raw) >= limit:
                        break
        except LookupError as exc:
            raise InvalidSourceError(f"unknown encoding: {encoding}") from exc
        if not has_header:
            headers = unique_headers([], max((len(row) for row in raw), default=0))
        records = []
        for row in raw:
            padded = list(row) + [""] * (len(headers) - len(row))
            records.append(
                {header: coerce_value(padded[index]) for index, header in enumerate(headers)}
            )
        return frame_to_rows(pl.DataFrame(records) if records else pl.DataFrame())

    if file_format == "jsonl":
        return frame_to_rows(pl.scan_ndjson(path).slice(offset, limit).collect())
    if file_format == "json":
        return frame_to_rows(pl.read_json(path).slice(offset, limit))
    if file_format == "parquet":
        return frame_to_rows(pl.scan_parquet(path).slice(offset, limit).collect())
    if file_format == "excel":
        sheet = effective.sheet
        if isinstance(sheet, str):
            frame = pl.read_excel(path, sheet_name=sheet, engine="calamine")
        else:
            frame = pl.read_excel(
                path, sheet_id=sheet if sheet is not None else 0, engine="calamine"
            )
        if isinstance(frame, dict):
            frame = next(iter(frame.values()))
        return frame_to_rows(frame.slice(offset, limit))
    raise UnsupportedFormatError(f"unsupported file format: {file_format}")
