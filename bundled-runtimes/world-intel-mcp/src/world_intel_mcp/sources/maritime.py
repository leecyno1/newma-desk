"""NGA Maritime Safety Information source for world-intel-mcp.

Provides navigational warnings from the National Geospatial-Intelligence Agency
(NGA) Maritime Safety Information (MSI) broadcast warnings API.
No API key required.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

from ..fetcher import Fetcher
from ..source_time import source_cache_timing

logger = logging.getLogger("world-intel-mcp.sources.maritime")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NGA_WARNINGS_URL = "https://msi.nga.mil/api/publications/broadcast-warn?output=json"

NAVAREAS = {
    "I": "UK (NE Atlantic, North Sea)",
    "II": "France (Bay of Biscay, W Africa)",
    "III": "Spain (Mediterranean W)",
    "IV": "United States (W Atlantic, Caribbean, Gulf of Mexico)",
    "V": "Brazil (SW Atlantic)",
    "VI": "Argentina (SE Atlantic)",
    "VII": "South Africa (Indian Ocean W)",
    "VIII": "India (Indian Ocean N)",
    "IX": "Pakistan (Arabian Sea, Persian Gulf)",
    "X": "Australia (Indian Ocean S)",
    "XI": "Japan (NW Pacific)",
    "XII": "United States (NE Pacific)",
    "XIII": "Russia (Arctic)",
    "XIV": "New Zealand (SW Pacific)",
    "XV": "Chile (SE Pacific)",
    "XVI": "Peru (E Pacific)",
}

_AREA_NUMBERS = "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI".split()


def _navarea(value: str | int) -> str:
    area = str(value).strip().upper()
    if area.isdigit() and 1 <= int(area) <= len(_AREA_NUMBERS):
        return _AREA_NUMBERS[int(area) - 1]
    return area


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_active(warning: dict) -> bool:
    """Return True if the warning has no cancelDate (i.e. still active)."""
    cancel = warning.get("cancelDate")
    return not cancel and str(warning.get("status") or "A").upper() in {"A", "ACTIVE"}


_COORD_RE = re.compile(
    r"(\d{1,3})-(\d{1,2}(?:\.\d+)?)\s*([NS])\s+"
    r"(\d{1,3})-(\d{1,2}(?:\.\d+)?)\s*([EW])",
    re.I,
)


def _extract_coords(text: str) -> tuple[float | None, float | None]:
    """Extract first lat/lon pair from NGA warning text.

    Parses formats like '22-16.65N 097-44.48W' into decimal degrees.
    """
    points = _all_coords(text)
    return (points[0]["lat"], points[0]["lon"]) if points else (None, None)


def _all_coords(text: str) -> list[dict]:
    points = []
    for m in _COORD_RE.finditer(text.upper()):
        if float(m[2]) >= 60 or float(m[5]) >= 60:
            continue
        lat, lon = int(m[1]) + float(m[2]) / 60, int(m[4]) + float(m[5]) / 60
        if lat > 90 or lon > 180:
            continue
        points.append({"lat": round(-lat if m[3] == "S" else lat, 4),
                       "lon": round(-lon if m[6] == "W" else lon, 4)})
    return points


def _parse_warning(warning: dict) -> dict:
    """Extract structured fields from a single NGA broadcast warning."""
    msg_year = warning.get("msgYear", "")
    msg_number = warning.get("msgNumber", "")
    warning_id = f"{msg_year}-{msg_number}" if msg_year and msg_number else None

    cancel_date = warning.get("cancelDate")
    status = "active" if _is_active(warning) else "cancelled"

    text = warning.get("text", "") or ""
    coordinates = _all_coords(text)
    first = coordinates[0] if coordinates else {}
    area = _navarea(warning.get("navArea", ""))
    authority = warning.get("authority") or ""
    origin = re.search(r"\bNAVAREA\s+([IVX]+|\d+)\b", authority, re.I)

    return {
        "id": warning_id,
        "navarea": area,
        "broadcast_area": warning.get("navArea", ""),
        "broadcast_label": {"P": "HYDROPAC", "A": "HYDROLANT", "C": "HYDROARC"}.get(area, f"NAVAREA {area}"),
        "origin_navarea": _navarea(origin[1]) if origin else area if area in _AREA_NUMBERS else None,
        "subregion": warning.get("subregion", ""),
        "status": status,
        "issue_date": _issue_date_iso(warning.get("issueDate")),
        "issue_date_raw": warning.get("issueDate"),
        "cancel_date": cancel_date if cancel_date else None,
        "text": text,
        "authority": authority,
        "source_status": warning.get("status"),
        "coordinates": coordinates,
        "lat": first.get("lat"),
        "lon": first.get("lon"),
    }


def _issue_date_iso(value: str | None) -> str | None:
    """NGA date-time groups, e.g. 081653Z MAY 2024, are explicitly UTC."""
    if not value:
        return None
    try:
        match = re.fullmatch(r"(\d{2})(\d{2})(\d{2})Z\s+([A-Z]{3})\s+(\d{4})", value.strip().upper())
        if match:
            day, hour, minute, month, year = match.groups()
            month_number = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split().index(month) + 1
            parsed = datetime(int(year), month_number, int(day), int(hour), int(minute), tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_nav_warnings(
    fetcher: Fetcher,
    navarea: str | None = None,
) -> dict:
    """Fetch active navigational warnings from NGA Maritime Safety Information.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        navarea: Optional NAVAREA identifier (e.g. "IV", "XII") to filter by.

    Returns:
        Dict with warnings list, count, per-navarea breakdown, NAVAREA
        definitions, source, and timestamp.
    """
    # One upstream URL, one cache entry; filtering must not trigger another fetch.
    cache_key = "maritime:warnings:all"

    try:
        async with asyncio.timeout(12):
            data = await fetcher.get_json(
                url=_NGA_WARNINGS_URL,
                source="nga-msi",
                cache_key=cache_key,
                cache_ttl=3600,
            )
    except TimeoutError:
        data = fetcher.cache.get_stale(cache_key)

    source_timing = source_cache_timing(fetcher.cache, cache_key)
    source_timing["timestamp"] = source_timing["collected_at"]

    if isinstance(data, list):
        raw_warnings = data
    elif isinstance(data, dict):
        raw_warnings = data.get("broadcast-warn", data.get("data"))
        if isinstance(raw_warnings, dict):
            raw_warnings = [raw_warnings]
    else:
        raw_warnings = None

    if not isinstance(raw_warnings, list) or any(not isinstance(w, dict) for w in raw_warnings):
        logger.warning("NGA MSI API returned no data")
        return {
            "warnings": [],
            "count": 0,
            "by_navarea": {},
            "navareas": NAVAREAS,
            "source": "nga-msi",
            **source_timing,
            "error": "NGA 航行警告暂时不可用，不能据此判断当前无警告",
        }

    # Filter to active warnings only
    active_raw = [w for w in raw_warnings if _is_active(w)]

    warnings = [_parse_warning(w) for w in active_raw]

    # Broadcast areas (e.g. P / HYDROPAC) can relay a different NAVAREA.
    if navarea is not None:
        area = _navarea(navarea)
        warnings = [
            w for w in warnings
            if w["navarea"] == area or w["origin_navarea"] == area
        ]

    # Sort by issue date descending (most recent first)
    def _issue_sort_key(w: dict) -> str:
        return w.get("issue_date") or ""

    warnings.sort(key=_issue_sort_key, reverse=True)

    # Summary stats: count per navarea
    by_navarea: dict[str, int] = {}
    for w in warnings:
        na = w.get("navarea", "UNKNOWN")
        by_navarea[na] = by_navarea.get(na, 0) + 1

    return {
        "warnings": warnings,
        "count": len(warnings),
        "by_navarea": by_navarea,
        "navareas": NAVAREAS,
        "source": "nga-msi",
        **source_timing,
    }
