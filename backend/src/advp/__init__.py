"""ADVP backend package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("advp-backend")
except PackageNotFoundError:  # pragma: no cover - only when running from source
    __version__ = "0.0.0"

__all__ = ["__version__"]
