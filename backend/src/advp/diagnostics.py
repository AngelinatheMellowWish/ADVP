"""Redacted diagnostic bundle for issue reports."""

from __future__ import annotations

import json
import platform
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from advp import __version__
from advp.config import Settings, get_settings
from advp.logging_config import redact


def build_bundle(settings: Settings | None = None) -> BytesIO:
    """Build a zip with environment, redacted settings, and recent logs."""
    settings = settings or get_settings()
    log_dir = settings.log_dir or (settings.workspace_dir / "logs")
    info = {
        "app_version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "settings": redact(
            {
                "host": settings.host,
                "port": settings.port,
                "database_path": str(settings.database_path),
                "backup_dir": str(settings.backup_dir),
                "workspace_dir": str(settings.workspace_dir),
                "log_dir": str(log_dir),
                "max_file_bytes": settings.max_file_bytes,
                "profile_sample_rows": settings.profile_sample_rows,
                "analysis_sample_rows": settings.analysis_sample_rows,
                "render_sample_rows": settings.render_sample_rows,
                "three_d_max_elements": settings.three_d_max_elements,
                "log_level": settings.log_level,
                "auth_token": settings.auth_token,
            }
        ),
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics.json",
            json.dumps(info, ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "README.txt",
            "ADVP diagnostics bundle. Secrets and absolute paths are redacted.\n",
        )
        log_path = log_dir / "advp.jsonl"
        if log_path.is_file():
            archive.write(log_path, arcname="logs/advp.jsonl")
        for rotated in sorted(log_dir.glob("advp.jsonl.*"))[-3:]:
            archive.write(rotated, arcname=f"logs/{rotated.name}")
    buffer.seek(0)
    return buffer


def redacted_paths(settings: Settings | None = None) -> dict[str, Any]:
    """Expose redacted settings for tests and diagnostics."""
    settings = settings or get_settings()
    result: dict[str, Any] = redact(
        {
            "database_path": str(settings.database_path),
            "workspace_dir": str(settings.workspace_dir),
            "auth_token": settings.auth_token,
        }
    )
    return result


def log_directory(settings: Settings | None = None) -> Path:
    """Return the resolved log directory."""
    settings = settings or get_settings()
    return settings.log_dir or (settings.workspace_dir / "logs")
