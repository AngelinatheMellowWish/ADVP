"""Shared chart rendering errors."""

from __future__ import annotations


class RenderError(Exception):
    """The selection cannot be rendered from the available preview data."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
