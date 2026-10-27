"""Structured JSON Lines logging with redaction and 14-day rotation."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from advp.config import Settings

SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "authorization",
    "credential",
}
_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|/(?:home|Users)/[^\s\"']+)")
_SECRET_TEXT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b(\s*[=:]\s*)([^\s,;]+)"
)
_STANDARD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in SECRET_KEYS
        or lowered.endswith("_secret")
        or lowered.endswith("_password")
        or lowered.endswith("_api_key")
        or lowered.endswith("_token")
    )


def redact(value: Any) -> Any:
    """Recursively redact secrets and absolute paths."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _is_secret_key(str(key)):
                result[key] = "***"
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    """Replace secrets and absolute home/drive paths in free text."""
    redacted = _SECRET_TEXT_PATTERN.sub(r"\1\2***", value)
    return _PATH_PATTERN.sub("<path>", redacted)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON with redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                if _is_secret_key(key):
                    payload[key] = "***"
                else:
                    payload[key] = redact(value)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> Path:
    """Install JSONL and console handlers once per process."""
    log_dir = settings.log_dir or (settings.workspace_dir / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if any(getattr(handler, "_advp_jsonl", False) for handler in root.handlers):
        return log_dir
    handler = TimedRotatingFileHandler(
        log_dir / "advp.jsonl",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
        delay=True,
    )
    handler._advp_jsonl = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    console = logging.StreamHandler()
    console._advp_jsonl = True  # type: ignore[attr-defined]
    console.setFormatter(JsonFormatter())
    root.addHandler(console)
    return log_dir
