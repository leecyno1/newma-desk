"""Nuclear test site seismic monitoring source for world-intel-mcp.

Monitors seismic activity near known nuclear test sites using USGS
GeoJSON API. Applies Haversine distance filtering and concern scoring
based on depth, magnitude, distance, and site status.
No API keys required.
"""

import logging
import math
from datetime import datetime, timezone

from ..fetcher import Fetcher
from ..config.countries import NUCLEAR_TEST_SITES

logger = logging.getLogger("world-intel-mcp.sources.nuclear")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BBOX_PADDING_DEG = 1.5  # degrees around each site for initial USGS query
_MAX_DISTANCE_KM = 100.0  # Haversine filter radius


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _concern_score(
    magnitude: float,
    depth_km: float,
    distance_km: float,
    site_status: str,
) -> tuple[float, str]:
    """Score concern level for a seismic event near a test site.

    Returns (score 0-100, level string).
    """
    score = 0.0

    # Magnitude contribution (0-40)
    score += min(40.0, magnitude * 8.0)

    # Shallow depth bonus (nuclear tests are <5km depth) — 0-25
    if depth_km <= 2.0:
        score += 25.0
    elif depth_km <= 5.0:
        score += 20.0
    elif depth_km <= 10.0:
        score += 10.0
    elif depth_km <= 30.0:
        score += 5.0

    # Proximity bonus (0-20)
    if distance_km <= 10.0:
        score += 20.0
    elif distance_km <= 30.0:
        score += 15.0
    elif distance_km <= 50.0:
        score += 10.0
    elif distance_km <= 100.0:
        score += 5.0

    # Active site multiplier (0-15)
    if site_status == "active":
        score += 15.0
    elif site_status == "dormant":
        score += 5.0

    score = min(100.0, score)

    if score >= 70:
        level = "critical"
    elif score >= 50:
        level = "high"
    elif score >= 30:
        level = "elevated"
    else:
        level = "low"

    return round(score, 1), level


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_nuclear_monitor(
    fetcher: Fetcher,
    hours: int = 72,
    *, catalog: dict | None = None,
) -> dict:
    """Monitor seismic activity near known nuclear test sites.

    For each NUCLEAR_TEST_SITE, queries USGS within a bounding box,
    applies Haversine distance filter (<=100km), and scores concern.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        hours: Lookback period in hours (default 72).

    Returns:
        Dict with sites, total_flagged_events, critical_flags,
        flagged_events, source.
    """
    import asyncio
    from .seismology import fetch_catalog, fetch_earthquake_geojson, _number

    if catalog is None and hours <= 720:
        catalog = await fetch_catalog(fetcher)

    now = datetime.now(timezone.utc)

    flagged_events: list[dict] = []
    sites: list[dict] = []

    async def _check_site(site: dict) -> dict:
        lat = site["lat"]
        lon = site["lon"]

        data = await fetch_earthquake_geojson(fetcher, 1.0, hours, 50,
            bbox=(lat - _BBOX_PADDING_DEG, lat + _BBOX_PADDING_DEG, lon - _BBOX_PADDING_DEG, lon + _BBOX_PADDING_DEG),
            catalog=catalog)

        nearby_events: list[dict] = []

        if data is not None:
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})
                coords = geom.get("coordinates", [0, 0, 0])

                eq_lon = coords[0] if len(coords) > 0 else 0
                eq_lat = coords[1] if len(coords) > 1 else 0
                eq_depth = coords[2] if len(coords) > 2 and _number(coords[2]) else None

                distance = _haversine_km(lat, lon, eq_lat, eq_lon)

                if distance > _MAX_DISTANCE_KM:
                    continue

                magnitude = props.get("mag", 0) or 0

                score, level = _concern_score(
                    magnitude=magnitude,
                    depth_km=eq_depth,
                    distance_km=distance,
                    site_status=site["status"],
                ) if eq_depth is not None and data["status"] == "ok" else (None, "not_assessed")

                # Convert time
                epoch_ms = props.get("time")
                eq_time = None
                if epoch_ms is not None:
                    try:
                        eq_time = datetime.fromtimestamp(
                            epoch_ms / 1000, tz=timezone.utc
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except (ValueError, TypeError, OSError):
                        pass

                event = {
                    "id": feature.get("id"),
                    "site": site["name"],
                    "site_country": site["country"],
                    "magnitude": magnitude,
                    "depth_km": round(eq_depth, 1) if eq_depth is not None else None,
                    "distance_km": round(distance, 1),
                    "latitude": eq_lat,
                    "longitude": eq_lon,
                    "time": eq_time,
                    "place": props.get("place"),
                    "concern_score": score,
                    "concern_level": level,
                }
                nearby_events.append(event)

        # Sort by concern_score descending
        nearby_events.sort(key=lambda e: e["concern_score"] if e["concern_score"] is not None else -1, reverse=True)

        return {
            "name": site["name"],
            "country": site["country"],
            "iso3": site["iso3"],
            "lat": lat,
            "lon": lon,
            "status": site["status"],
            "last_test": site["last_test"],
            "events_detected": len(nearby_events) if data["count"] is not None else None,
            "source_status": data["status"],
            "source_updated_at": data.get("source_updated_at"),
            "truncated": data.get("truncated", False),
            "highest_concern": nearby_events[0] if nearby_events else None,
            "events": nearby_events,
        }

    tasks = [_check_site(site) for site in NUCLEAR_TEST_SITES]
    sites = await asyncio.gather(*tasks)

    # Collect all flagged events
    for site_result in sites:
        for ev in site_result.get("events", []):
            flagged_events.append(ev)

    flagged_events.sort(key=lambda e: e["concern_score"] if e["concern_score"] is not None else -1, reverse=True)
    critical_flags = sum(1 for e in flagged_events if e["concern_level"] == "critical")
    available = sum(site["events_detected"] is not None for site in sites)
    complete = all(site["source_status"] == "ok" for site in sites)

    return {
        "sites": list(sites),
        "total_flagged_events": len(flagged_events) if available else None,
        "critical_flags": critical_flags if complete and all(e["concern_score"] is not None for e in flagged_events) else None,
        "status": "unavailable" if not available else "ok" if complete else "partial",
        "coverage": {"available": available, "expected": len(sites)},
        "freshness": (catalog or {}).get("freshness", "unknown"),
        "source_updated_at": (catalog or {}).get("source_updated_at"),
        "collected_at": (catalog or {}).get("collected_at"),
        "cache_expires_at": (catalog or {}).get("cache_expires_at"),
        "truncated": any(site["truncated"] for site in sites) or len(flagged_events) > 20,
        "display_limit": 20,
        "note": "试验场邻近地震目录样本；距离、震级与深度的启发式关注评分不能识别或证实核试验。",
        **({"error": "USGS目录不可用，近场地震数量待核验"} if not available else {}),
        "flagged_events": flagged_events[:20],
        "query": {"hours": hours, "max_distance_km": _MAX_DISTANCE_KM},
        "source": "usgs-nuclear-monitor",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
