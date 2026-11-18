"""USGS official seismic catalogue with explicit query and source coverage."""

import math
from datetime import datetime, timezone, timedelta

from ..fetcher import Fetcher
from ..source_time import source_cache_timing

_USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_USGS_MONTH = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/1.0_month.geojson"
_CATALOG_KEY = "seismology:usgs:1.0_month:v1"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _epoch_iso(value):
    if not _number(value):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, OSError):
        return None


async def fetch_catalog(fetcher: Fetcher) -> dict:
    """One official M1+ / 30-day summary; consumers retain their own filters."""
    data = await fetcher.get_json(_USGS_MONTH, source="usgs", cache_key=_CATALOG_KEY, cache_ttl=300)
    timing = source_cache_timing(fetcher.cache, _CATALOG_KEY)
    base = {**timing, "source": "usgs", "source_url": _USGS_MONTH, "catalog_basis": "usgs-m1-month"}
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        return {**base, "status": "unavailable", "error": "USGS目录未取得或格式异常；不能据此判断无地震", "features": None}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    generated = metadata.get("generated")
    updated = _epoch_iso(generated)
    age = datetime.now(timezone.utc).timestamp() - generated / 1000 if updated else None
    freshness = "unknown" if age is None or age < 0 else "stale" if age > 1800 or timing["freshness"] == "stale" else timing["freshness"]
    complete = metadata.get("count") == len(data["features"])
    return {**base, "features": data["features"], "source_updated_at": updated, "freshness": freshness,
            "status": "stale" if freshness == "stale" else "ok" if complete and freshness == "fresh" else "partial",
            "catalog_complete": complete}


async def fetch_earthquake_geojson(fetcher: Fetcher, min_magnitude=4.5, hours=24, limit=50, *, bbox=None, catalog=None) -> dict:
    """Filter the full shared catalogue; custom ranges retain the FDSN API."""
    if not _number(hours) or hours <= 0 or not _number(min_magnitude) or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("hours and limit must be positive; magnitude must be finite")
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    query = {"min_magnitude": min_magnitude, "hours": hours, "limit": limit, "bbox": bbox}
    if hours <= 720 and min_magnitude >= 1:
        data = catalog if catalog is not None else await fetch_catalog(fetcher)
        timing = {key: data.get(key) for key in ("source_updated_at", "collected_at", "cache_expires_at", "checked_at", "freshness", "source_url", "catalog_basis")}
        status = data.get("status", "unavailable")
        features = data.get("features")
    else:
        params = {"format": "geojson", "minmagnitude": min_magnitude, "orderby": "time", "limit": limit,
                  "starttime": start.strftime("%Y-%m-%dT%H:%M:%S")}
        if bbox:
            params.update(dict(zip(("minlatitude", "maxlatitude", "minlongitude", "maxlongitude"), bbox)))
        # Query identity includes limit and coordinates; different requests cannot share truncated results.
        key = f"seismology:query:v2:{min_magnitude}:{hours}:{limit}:{bbox}"
        data = await fetcher.get_json(_USGS_ENDPOINT, source="usgs", cache_key=key, cache_ttl=300, params=params)
        timing = {**source_cache_timing(fetcher.cache, key), "source_url": _USGS_ENDPOINT, "catalog_basis": "fdsn-bounded-query"}
        features = data.get("features") if isinstance(data, dict) and data.get("type") == "FeatureCollection" else None
        status = "stale" if timing["freshness"] == "stale" else "ok"
    base = {**timing, "source": "usgs", "query": query, "timestamp": timing.get("collected_at")}
    if not isinstance(features, list) or (isinstance(data, dict) and data.get("error")):
        return {**base, "status": "unavailable", "features": [], "count": None,
                "error": "USGS数据暂时不可用，不能据此判断当前无地震"}
    selected, invalid = {}, 0
    for feature in features:
        if not isinstance(feature, dict):
            invalid += 1
            continue
        props, geom = feature.get("properties"), feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geom, dict):
            invalid += 1
            continue
        epoch, magnitude = props.get("time"), props.get("mag")
        coords = geom.get("coordinates")
        if not _epoch_iso(epoch) or not _number(magnitude) or not isinstance(coords, list) or len(coords) < 2 or not all(_number(n) for n in coords[:2]):
            invalid += 1
            continue
        if not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
            invalid += 1
            continue
        if not start.timestamp() * 1000 <= epoch <= now.timestamp() * 1000 or magnitude < min_magnitude:
            continue
        if bbox and not (bbox[0] <= coords[1] <= bbox[1] and bbox[2] <= coords[0] <= bbox[3]):
            continue
        identity = feature.get("id") or (epoch, coords[0], coords[1], magnitude)
        selected[identity] = feature
    rows = sorted(selected.values(), key=lambda item: item["properties"]["time"], reverse=True)
    truncated = len(rows) > limit or (timing["catalog_basis"] == "fdsn-bounded-query" and len(features) >= limit)
    if invalid or truncated:
        status = "partial" if status != "stale" else status
    rows = rows[:limit]
    return {**base, "status": status, "features": rows, "count": len(rows) if rows or not invalid else None,
            "invalid_records": invalid, "truncated": truncated,
            "note": "USGS目录样本，不代表所有地震或实际灾损；来源时间、查询窗口与样本上限分别保留。"}


async def fetch_earthquakes(fetcher: Fetcher, min_magnitude: float = 4.5, hours: int = 24, limit: int = 50, *, catalog=None) -> dict:
    data = await fetch_earthquake_geojson(fetcher, min_magnitude, hours, limit, catalog=catalog)
    rows = data.pop("features")
    earthquakes = []
    for feature in rows:
        props, coords = feature["properties"], feature["geometry"]["coordinates"]
        earthquakes.append({
            "id": feature.get("id"), "magnitude": props.get("mag"), "place": props.get("place"),
            "time": _epoch_iso(props.get("time")), "updated_at": _epoch_iso(props.get("updated")),
            "event_type": props.get("type"),
            "depth_km": coords[2] if len(coords) > 2 and _number(coords[2]) else None,
            "latitude": coords[1], "longitude": coords[0],
            "tsunami_alert": props.get("tsunami"), "felt_reports": props.get("felt"),
            "alert_level": props.get("alert"), "url": props.get("url"),
        })
    return {**data, "earthquakes": earthquakes}
