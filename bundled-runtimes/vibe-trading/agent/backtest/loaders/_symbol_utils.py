"""Shared symbol-type detection utilities for loaders.

Exchange-listed ETF / LOF prefix codes (same pattern across loaders):
  SH: 50/51/52/56/58 (ETFs), SZ: 15/16 (ETFs + LOFs).
"""

from __future__ import annotations

import re

_ETF_PREFIXES = frozenset({"15", "16", "50", "51", "52", "56", "58"})
_BARE_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$", re.IGNORECASE)
_BARE_HK_CODE_RE = re.compile(r"^\d{1,5}$")


def _is_etf_listed(code: str) -> bool:
    """Detect exchange-listed ETF / LOF symbols (e.g. 510050.SH, 159915.SZ)."""
    upper = code.upper()
    if not upper.endswith((".SH", ".SZ")):
        return False
    digits = upper.split(".")[0]
    if len(digits) != 6 or not digits.isdigit():
        return False
    return digits[:2] in _ETF_PREFIXES


def is_us_equity_symbol(code: str) -> bool:
    """Return whether *code* is a canonical or bare US-equity ticker."""
    cleaned = str(code or "").strip()
    return cleaned.upper().endswith(".US") or bool(_BARE_US_TICKER_RE.fullmatch(cleaned))


def is_hk_equity_symbol(code: str) -> bool:
    """Return whether *code* is a suffixed or unambiguous bare HK code."""
    cleaned = str(code or "").strip()
    return cleaned.upper().endswith(".HK") or bool(_BARE_HK_CODE_RE.fullmatch(cleaned))


def yahoo_project_symbol(code: str) -> str:
    """Return a project symbol that Yahoo can map without losing its market."""
    cleaned = str(code or "").strip().upper()
    if _BARE_HK_CODE_RE.fullmatch(cleaned):
        return f"{cleaned.zfill(5)}.HK"
    return cleaned
