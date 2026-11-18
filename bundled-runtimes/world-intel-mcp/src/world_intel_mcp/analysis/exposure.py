"""Population exposure analysis near active events.

Estimates population at risk by finding major cities within a radius of
active earthquakes, wildfires, and conflict events. Uses Haversine formula
for distance calculation and a static dataset of ~120 major cities.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.analysis.exposure")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


async def _safe(coro, label: str) -> dict:
    try:
        return await coro
    except Exception as exc:
        logger.warning("Exposure: %s failed: %s", label, exc)
        return {"status": "unavailable", "error": type(exc).__name__}


def _find_exposed_cities(
    events: list[dict],
    cities: list[dict],
    radius_km: float,
) -> list[dict]:
    """Find cities within radius_km of any event. Returns unique cities with nearest event."""
    exposed: dict[str, dict] = {}  # city_name -> info

    for event in events:
        elat = event.get("lat")
        elon = event.get("lon")
        if elat is None or elon is None:
            continue

        for city in cities:
            dist = _haversine_km(elat, elon, city["lat"], city["lon"])
            if dist <= radius_km:
                cname = city["name"]
                if cname not in exposed or dist < exposed[cname]["distance_km"]:
                    exposed[cname] = {
                        "city": cname,
                        "country": city["country"],
                        "lat": city["lat"],
                        "lon": city["lon"],
                        "population": city["pop"],
                        "distance_km": round(dist, 1),
                        "nearest_event": event.get("type", "unknown"),
                        "event_detail": event.get("detail", ""),
                    }

    return sorted(exposed.values(), key=lambda c: c["distance_km"])


async def fetch_population_exposure(
    fetcher,
    radius_km: float = 200.0,
    event_types: list[str] | None = None,
    *, catalog: dict | None = None, inputs=None,
) -> dict:
    """Estimate population exposure near active events.

    Gathers active earthquakes (M4.5+), wildfires, and conflict events,
    then finds major cities within radius_km of each event.

    Args:
        fetcher: Shared HTTP fetcher.
        radius_km: Search radius in km (default 200).
        event_types: Filter to specific types: earthquake, wildfire, conflict.
                     Default: all three.
    """
    from ..config.population import MAJOR_CITIES
    from ..sources import seismology, wildfire, conflict

    types = set(event_types or ["earthquake", "wildfire", "conflict"])

    coros = {}
    if "earthquake" in types:
        async def earthquakes():
            shared = await inputs.get("seismic_catalog") if inputs is not None else catalog
            return await seismology.fetch_earthquakes(fetcher, min_magnitude=4.5, hours=48, limit=50, catalog=shared)
        coros["earthquake"] = earthquakes()
    if "wildfire" in types:
        coros["wildfire"] = wildfire.fetch_wildfires(fetcher)
    if "conflict" in types:
        coros["conflict"] = conflict.fetch_acled_events(fetcher, days=7, limit=200)

    results = {}
    if coros:
        fetched = await asyncio.gather(
            *[_safe(c, k) for k, c in coros.items()]
        )
        for key, data in zip(coros.keys(), fetched):
            results[key] = data

    source_times = {key: {field: data.get(field) for field in ("source_updated_at", "collected_at", "cache_expires_at", "timestamp", "freshness")} for key, data in results.items()}
    coverage = {key: "unavailable" if not data or data.get("error") or data.get("freshness") == "stale" or ("count" in data and data["count"] is None)
                else data.get("status", "partial") for key, data in results.items()}
    fire_data = results.get("wildfire", {})
    fire_regions = wildfire.current_regions(fire_data)
    if "wildfire" in coverage:
        all_regions = fire_data.get("fires_by_region")
        if not fire_regions or coverage["wildfire"] in {"unavailable", "stale", "error"}:
            coverage["wildfire"] = "unavailable"
            fire_regions = {}
        elif (coverage["wildfire"] != "ok" or fire_data.get("freshness") != "fresh"
              or not isinstance(all_regions, dict) or len(fire_regions) != len(all_regions)):
            coverage["wildfire"] = "partial"
    results = {key: data for key, data in results.items() if coverage[key] not in {"unavailable", "stale"}}
    # Normalize available samples; missing sources do not become zero exposure.
    events: list[dict] = []

    # Earthquakes
    for eq in results.get("earthquake", {}).get("earthquakes", []):
        lat = eq.get("latitude", eq.get("lat"))
        lon = eq.get("longitude", eq.get("lon"))
        if lat is not None and lon is not None:
            events.append({
                "lat": float(lat),
                "lon": float(lon),
                "type": "earthquake",
                "detail": f"M{eq.get('magnitude', '?')} {eq.get('place', '')}",
            })

    # Wildfires (fires_by_region is a dict keyed by region name)
    for region_name, region_data in fire_regions.items():
        for cluster in region_data.get("top_clusters", []):
            lat = cluster.get("lat")
            lon = cluster.get("lon")
            if lat is not None and lon is not None:
                events.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": "wildfire",
                    "detail": f"Satellite thermal detections: {cluster.get('fire_count', '?')} in {region_name}; not verified fires",
                })

    # Conflict
    for ev in results.get("conflict", {}).get("events", []):
        lat = ev.get("latitude", ev.get("lat"))
        lon = ev.get("longitude", ev.get("lon"))
        if lat is not None and lon is not None:
            events.append({
                "lat": float(lat),
                "lon": float(lon),
                "type": "conflict",
                "detail": f"{ev.get('event_type', 'conflict')}: {ev.get('location', ev.get('admin1', ''))}",
            })

    # Find exposed cities
    exposed_cities = _find_exposed_cities(events, MAJOR_CITIES, radius_km)
    total_exposed_pop = sum(c["population"] for c in exposed_cities)

    # Group by event type
    by_type: dict[str, int] = {}
    for c in exposed_cities:
        t = c["nearest_event"]
        by_type[t] = by_type.get(t, 0) + c["population"]

    # Group by country
    by_country: dict[str, int] = {}
    for c in exposed_cities:
        country = c["country"]
        by_country[country] = by_country.get(country, 0) + c["population"]

    return {
        "exposed_cities": exposed_cities,
        "exposed_city_count": len(exposed_cities) if results else None,
        "total_exposed_population": total_exposed_pop if results else None,
        "total_exposed_population_formatted": _format_pop(total_exposed_pop) if results else "未知",
        "status": "unavailable" if not results else "ok" if all(value == "ok" for value in coverage.values()) else "partial",
        "coverage": {"available": len(results), "expected": len(coros), "sources": coverage},
        "source_times": source_times,
        "note": "可用事件样本附近的静态城市名录人口，不是实际受灾人口；卫星热异常不等同已核实山火，缺源和未覆盖城市未计入。",
        **({"error": "事件来源未取得，人口暴露待核验"} if not results else {}),
        "by_event_type": {k: _format_pop(v) for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)},
        "by_country": {k: _format_pop(v) for k, v in sorted(by_country.items(), key=lambda x: x[1], reverse=True)[:10]},
        "events_analyzed": len(events) if results else None,
        "radius_km": radius_km,
        "event_types": sorted(types),
        "source": "population-exposure-analysis",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _format_pop(pop: int) -> str:
    if pop >= 1_000_000:
        return f"{pop / 1_000_000:.1f}M"
    elif pop >= 1_000:
        return f"{pop / 1_000:.0f}K"
    return str(pop)
