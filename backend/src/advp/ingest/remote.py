"""Fetch remote HTTP(S) and S3 objects into the local derived workspace."""

from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import boto3  # type: ignore[import-untyped]
import httpx

from advp.ingest.files import (
    FORMAT_BY_SUFFIX,
    FileTooLargeError,
    IngestError,
    InvalidSourceError,
)
from advp.ingest.scientific import SCIENTIFIC_SUFFIXES

CONTENT_SUFFIXES = {
    "text/csv": ".csv",
    "application/json": ".json",
    "application/x-ndjson": ".jsonl",
    "application/parquet": ".parquet",
    "application/vnd.apache.parquet": ".parquet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/x-hdf5": ".h5",
    "application/x-netcdf": ".nc",
    "application/fits": ".fits",
    "image/fits": ".fits",
}
ALLOWED_SUFFIXES = set(FORMAT_BY_SUFFIX) | set(SCIENTIFIC_SUFFIXES) | {".nii.gz"}


class RemoteFetchError(IngestError):
    code = "remote_fetch_failed"
    status_code = 422


@dataclass(slots=True)
class RemoteFetch:
    path: Path
    url: str
    final_url: str
    content_type: str | None
    etag: str | None
    size_bytes: int
    label: str


def redact_label(url: str) -> str:
    parsed = urlparse(url)
    port = f":{parsed.port}" if parsed.port else ""
    host = parsed.hostname or ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


def _filename_from_disposition(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", value, re.IGNORECASE)
    return unquote(match.group(1)) if match else None


def _infer_suffix(
    *,
    url: str,
    filename: str | None,
    content_type: str | None,
    content_disposition: str | None,
) -> str:
    candidate = filename or _filename_from_disposition(content_disposition)
    if not candidate:
        candidate = Path(urlparse(url).path).name
    if candidate:
        lower = candidate.lower()
        if lower.endswith(".nii.gz"):
            return ".nii.gz"
        suffix = Path(lower).suffix
        if suffix in ALLOWED_SUFFIXES:
            return suffix
    if content_type:
        ctype = content_type.split(";")[0].strip().lower()
        if ctype in CONTENT_SUFFIXES:
            return CONTENT_SUFFIXES[ctype]
    raise RemoteFetchError(
        "cannot infer the remote file format",
        hint="pass filename with a supported extension (csv/json/parquet/h5/nc/fits/nii/raw)",
    )


def auth_headers(auth: dict[str, Any] | None) -> dict[str, str]:
    if not auth:
        return {}
    kind = str(auth.get("type", "")).lower()
    if kind == "bearer":
        token = str(auth.get("token", ""))
        if token:
            return {"Authorization": f"Bearer {token}"}
    if kind == "basic":
        username = str(auth.get("username", ""))
        password = str(auth.get("password", ""))
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    if kind in {"api_key", "apikey", "header"}:
        header = str(auth.get("header", ""))
        value = str(auth.get("value", ""))
        if header and value:
            return {header: value}
    raise InvalidSourceError(
        "unsupported remote authentication type",
        hint="use bearer, basic, or api_key with header/value",
    )


def _output_path(output_dir: Path, suffix: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"remote-{uuid.uuid4().hex}{suffix}"


def fetch_http(
    url: str,
    output_dir: Path,
    *,
    headers: dict[str, str] | None = None,
    auth: dict[str, Any] | None = None,
    filename: str | None = None,
    max_bytes: int,
    timeout: float = 30.0,
) -> RemoteFetch:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise InvalidSourceError(
            "only http and https URLs are supported",
            hint="use an HTTP(S) URL or the S3 endpoint",
        )
    request_headers = dict(headers or {})
    request_headers.update(auth_headers(auth))
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=timeout) as client,
            client.stream("GET", url, headers=request_headers) as response,
        ):
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > max_bytes:
                raise FileTooLargeError(
                    f"remote file is {int(declared)} bytes, above the configured limit",
                    hint="raise the limit or use a smaller object",
                )
            suffix = _infer_suffix(
                url=str(response.url),
                filename=filename,
                content_type=content_type,
                content_disposition=response.headers.get("content-disposition"),
            )
            output = _output_path(output_dir, suffix)
            total = 0
            try:
                with output.open("wb") as handle:
                    for chunk in response.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise FileTooLargeError(
                                "remote download exceeded the configured size limit",
                                hint="raise the limit or use a smaller object",
                            )
                        handle.write(chunk)
            except Exception:
                output.unlink(missing_ok=True)
                raise
            return RemoteFetch(
                path=output,
                url=url,
                final_url=str(response.url),
                content_type=content_type,
                etag=response.headers.get("etag"),
                size_bytes=total,
                label=redact_label(url),
            )
    except httpx.HTTPStatusError as exc:
        raise RemoteFetchError(
            f"remote server returned HTTP {exc.response.status_code}",
            hint="check the URL, authentication, and access policy",
        ) from exc
    except httpx.HTTPError as exc:
        raise RemoteFetchError(
            f"remote request failed: {exc}",
            hint="check network access, TLS, and the URL",
        ) from exc


def fetch_s3(
    *,
    bucket: str,
    key: str,
    output_dir: Path,
    endpoint: str | None = None,
    region: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    filename: str | None = None,
    max_bytes: int,
) -> RemoteFetch:
    secret = secret_key or ""
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            region_name=region or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )
        head = client.head_object(Bucket=bucket, Key=key)
        declared = int(head.get("ContentLength", 0))
        if declared > max_bytes:
            raise FileTooLargeError(
                f"S3 object is {declared} bytes, above the configured limit",
                hint="raise the limit or use a smaller object",
            )
        content_type = head.get("ContentType")
        suffix = _infer_suffix(
            url=f"s3://{bucket}/{key}",
            filename=filename or key,
            content_type=content_type,
            content_disposition=None,
        )
        output = _output_path(output_dir, suffix)
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        total = 0
        try:
            with output.open("wb") as handle:
                for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise FileTooLargeError(
                            "S3 download exceeded the configured size limit",
                            hint="raise the limit or use a smaller object",
                        )
                    handle.write(chunk)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            body.close()
        return RemoteFetch(
            path=output,
            url=f"s3://{bucket}/{key}",
            final_url=f"s3://{bucket}/{key}",
            content_type=content_type,
            etag=head.get("ETag") or response.get("ETag"),
            size_bytes=total,
            label=f"s3://{bucket}/{key}",
        )
    except IngestError:
        raise
    except Exception as exc:
        message = str(exc)
        if secret:
            message = message.replace(secret, "***")
        raise RemoteFetchError(
            f"S3 fetch failed: {message}",
            hint="check endpoint, region, bucket, key, and credentials",
        ) from exc
