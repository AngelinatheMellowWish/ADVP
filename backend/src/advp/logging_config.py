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
_PATH_PATTERN = re.compile(
    r"(?:"
    r"[A-Za-z]:[\\/](?![\\/])[^\s\"'<>]+"
    r"|\\\\[^\s\"'<>]+"
    r"|(?<![\w.])/(?:tmp|var|home|Users|opt|root|etc|usr|mnt|srv|private)(?:/[^\s\"'<>]*)?"
    r")"
)
_WINDOWS_SPACED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"
    r"(?:[^\\/\r\n\"'<>|]*[\\/])*[^\\/\s\r\n\"'<>|]*(?:\.[A-Za-z0-9]{1,8})?"
)
_PATH_FRAGMENT_PATTERN = re.compile(r"(<path>)(?:\\[^\\/\r\n\"'<>|]+)+")
_SECRET_TEXT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)\b"
    r"(\s*[=:]\s*)((?:Bearer|Basic|Token)\s+)?([^\s,;\"']+)"
)
_SECRET_SPACE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key)\s+"
    r"(?!(?:[:=]|is\b|was\b|required\b|missing\b|invalid\b|not\b|must\b|should\b|"
    r"and\b|or\b|the\b|a\b|an\b))([^\s,;\"']+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(postgres(?:ql)?|mysql)://[^\s:/@]+:[^\s@/]+@([^\s,;\"']+)"
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
    """Replace secrets and absolute paths in free text."""
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1://***@\2", value)
    redacted = _SECRET_TEXT_PATTERN.sub(r"\1\2\3***", redacted)
    redacted = _SECRET_SPACE_PATTERN.sub(r"\1 ***", redacted)
    redacted = _WINDOWS_SPACED_PATH_PATTERN.sub("<path>", redacted)
    redacted = _PATH_PATTERN.sub("<path>", redacted)
    return _PATH_FRAGMENT_PATTERN.sub(r"\1", redacted)


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


def configure_logging(settings: Settings, file_logging: bool = True) -> Path:
    """Install JSONL file and console handlers, or console only in read-only mode."""
    log_dir = settings.log_dir or (settings.workspace_dir / "logs")
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    file_handlers = [handler for handler in root.handlers if getattr(handler, "_advp_file", False)]
    if file_logging:
        log_dir.mkdir(parents=True, exist_ok=True)
        if not file_handlers:
            handler = TimedRotatingFileHandler(
                log_dir / "advp.jsonl",
                when="midnight",
                backupCount=14,
                encoding="utf-8",
                delay=True,
            )
            handler._advp_jsonl = True  # type: ignore[attr-defined]
            handler._advp_file = True  # type: ignore[attr-defined]
            handler.setFormatter(JsonFormatter())
            root.addHandler(handler)
    else:
        for file_handler in file_handlers:
            root.removeHandler(file_handler)
            file_handler.close()
    if not any(getattr(handler, "_advp_console", False) for handler in root.handlers):
        console = logging.StreamHandler()
        console._advp_jsonl = True  # type: ignore[attr-defined]
        console._advp_console = True  # type: ignore[attr-defined]
        console.setFormatter(JsonFormatter())
        root.addHandler(console)
    return log_dir
