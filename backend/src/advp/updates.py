"""Unsigned update manifest, download, hash verification, and install chain."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from advp.config import get_settings

MAX_DOWNLOAD_BYTES = 600 * 1024 * 1024


class UpdateError(Exception):
    """An update step cannot be completed."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _parse_version(value: str) -> tuple[int, int, int] | None:
    parts = value.strip().lstrip("v").split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0, or 1 for semver-like versions."""
    a = _parse_version(left)
    b = _parse_version(right)
    if a is None or b is None:
        return 0
    return (a > b) - (a < b)


def fetch_manifest(url: str) -> dict[str, Any]:
    """Fetch the update manifest over HTTPS with a short timeout."""
    response = httpx.get(url, timeout=10.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise UpdateError("invalid_manifest", "update manifest is not an object")
    return payload


def check_for_update(current: str, url: str | None = None) -> dict[str, Any]:
    """Compare the current version with the remote manifest."""
    manifest = fetch_manifest(url or get_settings().update_url)
    latest = str(manifest.get("version") or "")
    available = bool(latest and compare_versions(latest, current) > 0)
    return {
        "available": available,
        "current": current,
        "latest": latest or None,
        "notes_url": manifest.get("notes_url"),
        "downloads": manifest.get("downloads") or {},
        "sha256": manifest.get("sha256"),
        "checked_at": datetime.now(UTC).isoformat(),
    }


def verify_sha256(path: Path, expected: str) -> bool:
    """Return True when the file hash matches the expected digest."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest().lower() == expected.strip().lower()


def download_update(url: str, destination: Path) -> dict[str, Any]:
    """Download an installer with a size cap and return its hash."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with httpx.stream("GET", url, timeout=60.0, follow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    destination.unlink(missing_ok=True)
                    raise UpdateError("download_too_large", "update exceeds the size limit")
                digest.update(chunk)
                handle.write(chunk)
    return {"path": str(destination), "sha256": digest.hexdigest(), "bytes": size}


def install_update(
    installer: Path,
    *,
    expected_sha256: str,
    backup_dir: Path | None = None,
    silent_arguments: list[str] | None = None,
) -> dict[str, Any]:
    """Verify the installer hash and run it silently after backing up state."""
    if not installer.is_file():
        raise UpdateError("installer_missing", "installer file was not found", 404)
    if not verify_sha256(installer, expected_sha256):
        raise UpdateError("hash_mismatch", "installer SHA-256 does not match the manifest")
    backup = backup_dir or (get_settings().resolved_eu2_dir / "update-backup")
    backup.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "installer": str(installer),
        "sha256": expected_sha256,
        "backup_dir": str(backup),
        "started_at": datetime.now(UTC).isoformat(),
    }
    (backup / "last_update.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    arguments = silent_arguments or ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    completed = subprocess.run(
        [str(installer), *arguments],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    record["exit_code"] = completed.returncode
    record["finished_at"] = datetime.now(UTC).isoformat()
    (backup / "last_update.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise UpdateError(
            "installer_failed",
            completed.stderr.strip() or "installer returned a non-zero exit code",
            500,
        )
    return record


def update_status_path() -> Path:
    return get_settings().resolved_eu2_dir / "update.json"


def read_update_status() -> dict[str, Any]:
    path = update_status_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_update_status(payload: dict[str, Any]) -> None:
    path = update_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)
