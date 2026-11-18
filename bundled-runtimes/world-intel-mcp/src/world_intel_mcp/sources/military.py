"""Military aviation tracking source for world-intel-mcp.

Provides real-time military aircraft tracking via OpenSky Network and
aircraft detail lookups via hexdb.io (free, no API key).
"""

import asyncio
import base64
import logging
import math
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher
from ..source_time import source_cache_timing

logger = logging.getLogger("world-intel-mcp.sources.military")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
_ADSBLOL_MIL_URL = "https://api.adsb.lol/v2/mil"
_HEXDB_BASE_URL = "https://hexdb.io/api/v1/aircraft"

# Callsign prefixes commonly used by military flights.
MILITARY_CALLSIGN_PREFIXES = [
    "RCH", "DUKE", "REACH", "EVAC", "JAKE", "TOPCAT", "BOXER",
    "IRON", "CASA", "NATO", "LAGR", "TEAL", "SAM", "EXEC",
    "SPAR", "VALOR", "BLADE",
]

# Theater bounding boxes for global military posture assessment.
THEATERS = {
    "european": {"bbox": "35,-25,72,45", "desc": "NATO/Russia theater"},
    "indo_pacific": {"bbox": "-10,95,55,155", "desc": "China/Taiwan/SCS"},
    "middle_east": {"bbox": "10,25,45,65", "desc": "Persian Gulf/Red Sea"},
    "arctic": {"bbox": "65,-180,90,180", "desc": "Arctic region"},
    "korean_peninsula": {"bbox": "33,124,43,132", "desc": "Korean DMZ"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_military_callsign(callsign: str | None) -> bool:
    """Check whether a callsign matches known military callsign patterns."""
    if not callsign:
        return False
    cs = callsign.strip().upper()
    for prefix in MILITARY_CALLSIGN_PREFIXES:
        if cs.startswith(prefix):
            return True
    return False


def _build_opensky_auth_headers() -> dict[str, str] | None:
    """Build HTTP Basic auth header from OpenSky env vars, or None if unset."""
    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    if client_id and client_secret:
        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}
    return None


def _extract_aircraft(state: list) -> dict:
    """Extract a structured aircraft dict from an OpenSky state vector."""
    return {
        "icao24": state[0],
        "callsign": state[1].strip() if state[1] else None,
        "origin_country": state[2],
        "country_basis": "registration country; not operator nationality",
        "classification_basis": "callsign-heuristic",
        "timestamp": datetime.fromtimestamp(state[3], timezone.utc).isoformat() if _number(state[3]) else None,
        "latitude": state[6],
        "longitude": state[5],
        "altitude_m": state[7],
        "velocity_ms": state[9],
        "heading": state[10],
        "on_ground": state[8],
        "squawk": state[14],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def _fetch_adsblol_military(fetcher: Fetcher) -> list[dict] | None:
    """Fetch military aircraft from adsb.lol free API (pre-filtered)."""
    data = await fetcher.get_json(
        url=_ADSBLOL_MIL_URL,
        source="adsblol",
        cache_key="military:adsblol:mil",
        cache_ttl=300,
    )
    if not isinstance(data, dict) or not isinstance(data.get("ac"), list):
        return None

    aircraft: list[dict] = []
    for ac in data.get("ac") or []:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue
        icao24 = ac.get("hex", "")
        aircraft.append({
            "icao24": icao24,
            "callsign": (ac.get("flight") or "").strip() or None,
            "origin_country": "",
            "classification_basis": "provider-military-tag",
            "country_basis": "unknown; registration prefix is not operator nationality",
            "latitude": lat,
            "longitude": lon,
            "altitude_m": ac["alt_baro"] * 0.3048 if _number(ac.get("alt_baro")) else None,
            "velocity_ms": ac["gs"] * 0.514444 if _number(ac.get("gs")) else None,
            "position_age_seconds": ac.get("seen_pos"),
            "heading": ac.get("track"),
            "on_ground": ac.get("alt_baro") == "ground",
            "squawk": ac.get("squawk"),
            "aircraft_type": ac.get("t"),
            "registration": ac.get("r"),
        })
    return aircraft


async def _fetch_opensky_military(
    fetcher: Fetcher, bbox: str | None = None,
) -> list[dict] | None:
    """Fetch military aircraft from OpenSky (requires filtering)."""
    params: dict[str, str] = {}
    if bbox is not None:
        parts = bbox.split(",")
        if len(parts) == 4:
            params["lamin"] = parts[0]
            params["lomin"] = parts[1]
            params["lamax"] = parts[2]
            params["lomax"] = parts[3]

    headers = _build_opensky_auth_headers()
    cache_label = bbox or "global"

    data = await fetcher.get_json(
        url=_OPENSKY_STATES_URL,
        source="opensky",
        cache_key=f"military:flights:{cache_label}",
        cache_ttl=300,
        headers=headers,
        params=params if params else None,
    )

    if not isinstance(data, dict) or not isinstance(data.get("states"), list):
        return None

    states = data.get("states") or []
    aircraft: list[dict] = []
    for state in states:
        if not state or len(state) < 17:
            continue
        icao24 = state[0] or ""
        callsign = state[1] or ""
        # Broad registration prefixes also contain civilian aircraft.
        if _is_military_callsign(callsign):
            aircraft.append(_extract_aircraft(state))
    return aircraft


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _located(aircraft):
    """Keep unique, valid coordinate observations; never fabricate positions."""
    result, seen = [], set()
    for ac in aircraft:
        identity = str(ac.get("icao24") or "").strip().lower()
        lat, lon = ac.get("latitude"), ac.get("longitude")
        if not identity or identity in seen or not _number(lat) or not _number(lon):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        age = ac.get("position_age_seconds")
        if _number(age) and age > 300:
            continue
        seen.add(identity)
        result.append(ac)
    return result


def _within(aircraft, bbox):
    south, west, north, east = map(float, bbox.split(","))
    return [ac for ac in aircraft if south <= ac["latitude"] <= north and
            (west <= ac["longitude"] <= east if west <= east else ac["longitude"] >= west or ac["longitude"] <= east)]


async def fetch_military_flights(fetcher: Fetcher, bbox: str | None = None) -> dict:
    """Public ADS-B observations, not a complete inventory of deployments."""
    aircraft = await _fetch_adsblol_military(fetcher)
    source, key, method = "adsb.lol", "military:adsblol:mil", "provider-military-tag"
    if aircraft is None:
        aircraft = await _fetch_opensky_military(fetcher, bbox)
        source, key, method = "opensky", f"military:flights:{bbox or 'global'}", "callsign-heuristic"
    if aircraft is None:
        return {"aircraft": [], "count": None, "status": "unavailable",
                "error": "Military flight sources unavailable", "source": "none", "timestamp": _utc_now_iso()}
    located = _located(aircraft)
    if bbox:
        located = _within(located, bbox)
    timing = source_cache_timing(fetcher.cache, key)
    for ac in located:
        if "timestamp" not in ac:
            ac["timestamp"] = timing["collected_at"]
    return {
        "aircraft": located, "count": len(located), "source": source,
        "status": "ok" if timing["freshness"] == "fresh" else "stale" if timing["freshness"] == "stale" else "partial",
        "military_filter": method, "observation_basis": "public-adsb-coordinate-sample",
        "observation_id": f"{source}:{method}:{timing['collected_at']}" if timing["collected_at"] else None,
        **timing, "timestamp": timing["collected_at"],
        "note": "Publicly received positions only. Provider tags/callsigns do not verify mission, operator nationality, deployment strength or combat readiness.",
    }


def build_theater_posture(flights: dict) -> dict:
    from ..analysis.surge import SENSITIVE_REGIONS

    if flights.get("error") or flights.get("_stale") or flights.get("status") in {"unavailable", "stale"} or flights.get("freshness") == "stale":
        return {"status": "unavailable", "error": "Fresh aviation observations unavailable",
                "theaters": {}, "region_observations": {}, "total_military_aircraft": None}
    if not isinstance(flights.get("aircraft"), list):
        return {"status": "unavailable", "error": "Aviation observation list missing", "theaters": {}}
    aircraft = _located(flights["aircraft"])
    theaters, union = {}, set()
    for name, info in THEATERS.items():
        members = _within(aircraft, info["bbox"])
        union.update(ac["icao24"] for ac in members)
        theaters[name] = {
            "status": "ok", "count": len(members), "bbox": info["bbox"], "description": info["desc"],
            "countries": sorted({ac["origin_country"] for ac in members if ac.get("origin_country")}),
            "country_basis": "registration hints only; not used to allocate aircraft counts",
            "sample_callsigns": [ac["callsign"] for ac in members if ac.get("callsign")][:5],
        }
    return {
        "status": flights.get("status", "partial"), "theaters": theaters,
        "region_observations": {name: {"count": len(_within(aircraft, info["bbox"])), "bbox": info["bbox"]}
                                for name, info in SENSITIVE_REGIONS.items()},
        "total_military_aircraft": len(union), "observed_aircraft_total": len(aircraft),
        "source": flights.get("source"), "observation_id": flights.get("observation_id"),
        "freshness": flights.get("freshness", "unknown"), "timestamp": flights.get("timestamp"),
        "observation_basis": "public-adsb-coordinate-sample",
        "note": "Theater counts may overlap; total is deduplicated. Zero means no received positions in this sample, not absence of forces.",
    }


async def fetch_theater_posture(fetcher: Fetcher, *, flights: dict | None = None) -> dict:
    # One global source response, then local geometry; no five-way network fan-out.
    return build_theater_posture(flights if flights is not None else await fetch_military_flights(fetcher))


async def fetch_aircraft_details_batch(fetcher: Fetcher, icao24_list: list[str]) -> dict:
    """Look up multiple aircraft by ICAO24 hex codes in parallel.

    Args:
        fetcher: Shared HTTP fetcher.
        icao24_list: List of ICAO24 hex addresses (max 20).

    Returns:
        Dict with aircraft[] details, count, source, timestamp.
    """
    icao24_list = icao24_list[:20]  # cap at 20

    async def _lookup(icao: str) -> dict | None:
        result = await fetch_aircraft_details(fetcher, icao)
        ac = result.get("aircraft", {})
        if not ac:
            return None
        ac["icao24"] = icao
        return ac

    tasks = [_lookup(icao) for icao in icao24_list]
    results = await asyncio.gather(*tasks)

    aircraft = [a for a in results if a is not None]
    return {
        "aircraft": aircraft,
        "count": len(aircraft),
        "requested": len(icao24_list),
        "source": "hexdb",
        "timestamp": _utc_now_iso(),
    }


async def fetch_aircraft_details(fetcher: Fetcher, icao24: str) -> dict:
    """Look up detailed aircraft information from hexdb.io (free, no API key).

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        icao24: The ICAO 24-bit hex address of the aircraft.

    Returns:
        Dict with aircraft detail payload, source, and timestamp.
    """
    url = f"{_HEXDB_BASE_URL}/{icao24}"

    data = await fetcher.get_json(
        url=url,
        source="hexdb",
        cache_key=f"military:aircraft:{icao24}",
        cache_ttl=3600,
    )

    if data is None:
        logger.warning("hexdb.io returned no data for icao24=%s", icao24)
        return {
            "aircraft": {},
            "source": "hexdb",
            "timestamp": _utc_now_iso(),
        }

    return {
        "aircraft": data,
        "source": "hexdb",
        "timestamp": _utc_now_iso(),
    }
