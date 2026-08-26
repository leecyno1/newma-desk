"""Shared monkeypatch compatibility layer for extracted API modules.

Tests monkeypatch ``api_server._API_KEY`` (and similar).  Route modules
resolve dependencies via ``sys.modules["api_server"]``, so the patched
value lives on the *host* module, not on the extracted module.
"""

from __future__ import annotations

import sys
from typing import Any


def host_attr(name: str, fallback: Any) -> Any:
    """Read a compatibility attribute from ``api_server`` when present."""
    host = sys.modules.get("api_server")
    if host is not None and hasattr(host, name):
        return getattr(host, name)
    return fallback


def set_host_attr(name: str, value: Any) -> None:
    """Write a compatibility attribute onto ``api_server`` when present."""
    host = sys.modules.get("api_server")
    if host is not None:
        setattr(host, name, value)
