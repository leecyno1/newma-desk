"""NASA FIRMS wildfire data source for world-intel-mcp.

Provides real-time active fire detections from the VIIRS/SNPP sensor
via the NASA Fire Information for Resource Management System (FIRMS) API.
Requires a NASA FIRMS API key (env: NASA_FIRMS_API_KEY).
"""

import asyncio
import csv
import io
import logging
import math
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher
from ..source_time import source_cache_timing

logger = logging.getLogger("world-intel-mcp.sources.wildfire")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Bounding boxes: west,south,east,north
REGIONS = {
    "north_america": "-170,15,-50,75",
    "south_america": "-85,-60,-30,15",
    "europe": "-25,35,45,72",
    "africa": "-20,-37,55,38",
    "middle_east": "25,10,65,45",
    "south_asia": "60,5,100,40",
    "east_asia": "95,15,150,55",
    "southeast_asia": "90,-15,155,25",
    "oceania": "105,-50,180,-5",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_regions(data: dict) -> dict[str, dict]:
    """Only regions with explicit current collection evidence are usable now."""
    if (not isinstance(data, dict) or data.get("error") or data.get("_stale")
            or data.get("status") not in {"ok", "partial"} or data.get("freshness") == "stale"):
        return {}
    regions = data.get("fires_by_region")
    if not isinstance(regions, dict):
        return {}
    now = datetime.now(timezone.utc)
    def is_current(region: dict) -> bool:
        try:
            collected = datetime.fromisoformat(region["collected_at"].replace("Z", "+00:00"))
            expires = datetime.fromisoformat(region["cache_expires_at"].replace("Z", "+00:00"))
            return collected.tzinfo is not None and expires.tzinfo is not None and collected <= now < expires
        except (KeyError, AttributeError, TypeError, ValueError):
            return False
    return {name: region for name, region in regions.items()
            if isinstance(region, dict) and not region.get("error")
            and region.get("status") in {"ok", "partial"}
            and region.get("freshness") == "fresh"
            and is_current(region)
            and isinstance(region.get("top_clusters"), list)}


def _parse_fires_csv(csv_text: str) -> tuple[list[dict], int]:
    """Return validated non-low detections and invalid-row count; reject non-CSV responses."""
    if not isinstance(csv_text, str):
        raise ValueError("missing CSV response")
    reader = csv.DictReader(io.StringIO(csv_text), strict=True)
    if not reader.fieldnames:
        raise ValueError("missing CSV header")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    if not {"latitude", "longitude", "confidence"}.issubset(reader.fieldnames):
        raise ValueError("invalid CSV header")
    fires: list[dict] = []
    invalid = 0
    for row in reader:
        try:
            confidence = (row.get("confidence") or "").strip().lower()
            if confidence in ("low", "l"):
                continue
            if confidence not in ("nominal", "n", "high", "h"):
                raise ValueError("unknown confidence")
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("invalid coordinates")
            def optional_number(name: str) -> float | None:
                value = (row.get(name) or "").strip()
                result = float(value) if value else None
                if result is not None and not math.isfinite(result):
                    raise ValueError("invalid measurement")
                return result
            fires.append({"latitude": lat, "longitude": lon, "brightness": optional_number("bright_ti4"),
                "frp": optional_number("frp"), "confidence": confidence,
                **{name: (row.get(name) or "").strip() for name in ("acq_date", "acq_time", "daynight", "satellite")}})
        except (ValueError, TypeError, KeyError):
            invalid += 1
    return fires, invalid


def _cluster_fires(fires: list[dict], top_n: int = 20) -> list[dict]:
    """Group fires by a 0.5-degree grid and return the top N clusters by count."""
    grid: dict[tuple[float, float], list[dict]] = {}

    for fire in fires:
        # Round to nearest 0.5 degrees
        grid_lat = round(fire["latitude"] * 2) / 2
        grid_lon = round(fire["longitude"] * 2) / 2
        key = (grid_lat, grid_lon)

        if key not in grid:
            grid[key] = []
        grid[key].append(fire)

    # Sort clusters by fire count descending
    sorted_clusters = sorted(grid.items(), key=lambda item: len(item[1]), reverse=True)

    clusters: list[dict] = []
    for (lat, lon), cell_fires in sorted_clusters[:top_n]:
        max_frp = max((f["frp"] for f in cell_fires if f["frp"] is not None), default=None)
        clusters.append({
            "lat": lat,
            "lon": lon,
            "fire_count": len(cell_fires),
            "max_frp": max_frp,
        })

    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_wildfires(
    fetcher: Fetcher,
    region: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Fetch non-low-confidence FIRMS detections for the requested two-day window.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        region: Region name (key from REGIONS dict). None fetches all regions.
        api_key: NASA FIRMS API key. Falls back to NASA_FIRMS_API_KEY env var.

    Returns:
        Dict with fires_by_region, total_fires, source, and timestamp.
    """
    key = api_key or os.environ.get("NASA_FIRMS_API_KEY")
    if not key:
        return {"error": "NASA_FIRMS_API_KEY not configured"}

    if region is not None:
        bbox = REGIONS.get(region)
        if bbox is None:
            return {
                "error": f"Unknown region '{region}'. Valid: {', '.join(REGIONS.keys())}",
            }
        regions_to_fetch: dict[str, str] = {region: bbox}
    else:
        regions_to_fetch = dict(REGIONS)

    async def _fetch_region(region_name: str, bbox: str) -> tuple[str, dict]:
        url = f"{_FIRMS_BASE_URL}/{key}/VIIRS_SNPP_NRT/{bbox}/2"
        cache_key = f"wildfire:csv:{region_name}"
        try:
            csv_text = await fetcher.get_text(url=url, source="nasa-firms", cache_key=cache_key, cache_ttl=1800)
            timing = source_cache_timing(fetcher.cache, cache_key)
            fires, invalid = _parse_fires_csv(csv_text)
        except (ValueError, TypeError, csv.Error):
            return region_name, {"status": "unavailable", "count": None, "sample_count": None,
                "top_clusters": [], "error": "FIRMS 响应缺失或格式无效"}
        except Exception as exc:
            logger.warning("FIRMS region %s failed: %s", region_name, type(exc).__name__)
            return region_name, {"status": "unavailable", "count": None, "sample_count": None,
                "top_clusters": [], "error": "FIRMS 请求失败"}
        clusters = _cluster_fires(fires)
        truncated = len(_cluster_fires(fires, top_n=21)) > 20
        status = "stale" if timing["freshness"] == "stale" else "partial" if invalid or timing["freshness"] != "fresh" else "ok"
        return region_name, {"status": status, "count": len(fires) if status == "ok" else None,
            "sample_count": len(fires), "invalid_rows": invalid, "top_clusters": clusters,
            "clusters_truncated": truncated, **timing}

    # Fetch all requested regions in parallel
    tasks = [
        _fetch_region(name, bbox)
        for name, bbox in regions_to_fetch.items()
    ]
    results = await asyncio.gather(*tasks)

    # Assemble response
    fires_by_region = dict(results)
    available = [row for row in fires_by_region.values() if row["status"] in {"ok", "partial"}]
    complete = len(available) == len(fires_by_region) and all(row["status"] == "ok" for row in available)
    cluster_complete = complete and not any(row["clusters_truncated"] for row in available)
    status = "ok" if cluster_complete else "partial" if available else "unavailable"
    generated_at = _utc_now_iso()
    result = {
        "status": status,
        "fires_by_region": fires_by_region,
        "total_fires": sum(row["count"] for row in available) if complete else None,
        "sample_detections": sum(row["sample_count"] for row in available) if available else None,
        "coverage": {"available": len(available), "requested": len(fires_by_region)},
        "freshness": "fresh" if complete else "unknown",
        "note": "VIIRS SNPP 两日非低置信度探测样本，不等同独立火灾；区域范围重叠，相加可能重复，每区仅展示前20个网格。",
        "source": "nasa-firms", "timestamp": generated_at,
        **({"error": "FIRMS 未取得可用区域"} if not available else {}),
    }
    cache_label = region if region is not None else "global"
    fetcher.cache.set(f"wildfire:fires:{cache_label}", result, 1800)
    return result
