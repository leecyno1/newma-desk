from __future__ import annotations

"""Checkout-safe compatibility exports for robust cycle research helpers."""

from importlib import import_module
from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_DIRECTORY = _ROOT / "src"
if str(_SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIRECTORY))

_discovery = import_module("seven_cycle_platform.cycles.discovery")
for _name in _discovery.__all__:
    globals()[_name] = getattr(_discovery, _name)

__all__ = list(_discovery.__all__)
