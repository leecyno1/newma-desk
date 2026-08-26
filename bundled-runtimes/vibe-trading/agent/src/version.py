"""Lightweight application version lookup shared by every entry point."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Final


def _version_from_pyproject() -> str:
    """Read the repository version when package metadata is unavailable."""
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        return str(
            tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        )
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


def resolve_application_version() -> str:
    """Resolve installed metadata without importing the heavyweight CLI."""
    try:
        return package_version("vibe-trading-ai")
    except PackageNotFoundError:
        return _version_from_pyproject()


__version__: Final[str] = resolve_application_version()

__all__ = ["__version__", "resolve_application_version"]
