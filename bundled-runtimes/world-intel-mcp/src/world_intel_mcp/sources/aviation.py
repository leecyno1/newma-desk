"""FAA airport advisories and OpenSky traffic observations."""

import base64
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from ..fetcher import Fetcher
from ..source_time import source_cache_timing

# Linked as "XML" by the FAA National Airspace System site's footer.
_FAA_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"
_FAA_CACHE_KEY = "aviation:faa:nas-status:v1"
_FAA_LISTS = {
    "Ground_Stop_List": ("Program", "Ground Stop Programs"),
    "Ground_Delay_List": ("Ground_Delay", "Ground Delay Programs"),
    "Arrival_Departure_Delay_List": ("Delay", "General Arrival/Departure Delay Info"),
    "Airport_Closure_List": ("Airport", "Airport Closures"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_faa_status(xml_text: str) -> tuple[list[dict], str | None, int]:
    root = ElementTree.fromstring(xml_text)
    if root.tag != "AIRPORT_STATUS_INFORMATION":
        raise ValueError("Unexpected FAA document")
    raw_time = root.findtext("Update_Time", "").strip()
    try:
        updated = parsedate_to_datetime(raw_time)
        updated_at = updated.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if updated.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        updated_at = None
    airports: dict[str, dict] = {}
    invalid = 0
    for group in root.findall("Delay_type"):
        for listing in group:
            if listing.tag == "Name":
                continue
            spec = _FAA_LISTS.get(listing.tag)
            if spec is None:
                invalid += 1
                continue
            record_tag, label = spec
            for record in listing:
                code = record.findtext("ARPT", "").strip().upper()
                if record.tag != record_tag or not code:
                    invalid += 1
                    continue
                direction = record.find("Arrival_Departure")
                status = {
                    "type": label,
                    "reason": record.findtext("Reason", "").strip(),
                    "avg_delay": record.findtext("Avg", "").strip(),
                    "max_delay": record.findtext("Max", "").strip(),
                    "min_delay": "",
                    "direction": "",
                    "trend": "",
                    "end_time": record.findtext("End_Time", "").strip(),
                    "closure_begin": record.findtext("Start", "").strip(),
                    "closure_end": record.findtext("Reopen", "").strip(),
                }
                if direction is not None:
                    status.update({
                        "direction": direction.get("Type", ""),
                        "min_delay": direction.findtext("Min", "").strip(),
                        "max_delay": direction.findtext("Max", "").strip(),
                        "trend": direction.findtext("Trend", "").strip(),
                    })
                airport = airports.setdefault(code, {"code": code, "name": code, "status": []})
                if status not in airport["status"]:
                    airport["status"].append(status)
    return list(airports.values()), updated_at, invalid


async def fetch_airport_delays(fetcher: Fetcher) -> dict:
    """Read one official FAA advisory feed; absence is not proof of no delays.

    The compatibility field 'delayed' contains airports with listed advisories,
    including limited closures. The feed does not enumerate checked airports or
    all delayed flights, so total_checked is unknown.
    """
    xml_text = await fetcher.get_xml(
        _FAA_STATUS_URL, source="faa", cache_key=_FAA_CACHE_KEY, cache_ttl=300,
    )
    timing = source_cache_timing(fetcher.cache, _FAA_CACHE_KEY)
    base = {
        "source": "faa",
        "source_url": _FAA_STATUS_URL,
        "observation_basis": "faa-nas-airport-advisories",
        "count_basis": "airports-with-listed-advisories",
        "total_checked": None,
        "note": "FAA公布的机场运行通告，不是全部航班延误；未列出不等于运行正常。关闭类通告可能仅限制部分航班，须核对原文。来源更新时间超过30分钟按历史参考展示（本地保守阈值，非FAA保证）。",
    }
    try:
        if xml_text is None:
            raise ValueError("FAA unavailable")
        airports, updated_at, invalid = _parse_faa_status(xml_text)
    except (ElementTree.ParseError, ValueError, TypeError):
        return {**base, **timing, "status": "unavailable", "freshness": "unknown",
                "error": "FAA机场运行通告未能取得或格式异常；不能据此判断没有延误",
                "delayed": [], "delayed_count": None, "reported_airport_count": None,
                "advisory_count": None, "updated_at": None, "timestamp": None,
                "errors": 1, "coverage": {"available": 0, "expected": 1}}

    age = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_at.replace("Z", "+00:00"))).total_seconds() if updated_at else None
    freshness = "unknown" if age is None or age < 0 else "stale" if age > 1800 or timing["freshness"] == "stale" else timing["freshness"]
    status = "stale" if freshness == "stale" else "partial" if invalid or freshness != "fresh" else "ok"
    count = len(airports) if airports or invalid == 0 else None
    return {
        **base, **timing, "freshness": freshness, "status": status,
        "delayed": airports, "delayed_count": count, "reported_airport_count": count,
        "advisory_count": sum(len(airport["status"]) for airport in airports) if count is not None else None,
        "updated_at": updated_at, "timestamp": updated_at,
        "invalid_records": invalid, "errors": 0,
        "coverage": {"available": 1, "expected": 1},
    }


# ---------------------------------------------------------------------------
# Domestic / commercial air traffic (OpenSky Network)
# ---------------------------------------------------------------------------

_OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

_AIR_REGIONS = {
    "north_america": (15, -170, 72, -50),
    "europe": (35, -25, 72, 45),
    "east_asia": (15, 95, 55, 155),
    "middle_east": (12, 25, 42, 65),
    "south_asia": (5, 60, 40, 100),
    "africa": (-35, -20, 37, 55),
    "south_america": (-56, -82, 15, -34),
    "oceania": (-50, 110, 0, 180),
}

_COMMERCIAL_PREFIXES = [
    "UAL", "AAL", "DAL", "SWA", "JBU", "ASA", "NKS", "FFT", "SKW",
    "BAW", "EZY", "RYR", "DLH", "AFR", "KLM", "SAS", "AUA", "TAP",
    "QFA", "ANZ", "JST", "VOZ", "CPA", "SIA", "THA", "ANA", "JAL",
    "CES", "CSN", "CCA", "HDA", "AIC", "UAE", "ETH", "SAA", "RAM",
    "TAM", "GLO", "AZU", "AVA", "LAN", "THY", "TRK", "SHT",
]


def _opensky_auth_headers() -> dict[str, str] | None:
    username = os.environ.get("OPENSKY_USERNAME")
    password = os.environ.get("OPENSKY_PASSWORD")
    if username and password:
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}
    return None


def _classify_region(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "unknown"
    for name, (lat_min, lon_min, lat_max, lon_max) in _AIR_REGIONS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return "other"


def _is_commercial(callsign: str | None) -> bool:
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in _COMMERCIAL_PREFIXES)


async def fetch_domestic_flights(fetcher: Fetcher) -> dict:
    """Fetch global air traffic counts from OpenSky Network.

    Queries all airborne aircraft once, then buckets by region and type.
    """
    data = await fetcher.get_json(
        _OPENSKY_STATES_URL,
        source="opensky-domestic",
        cache_key="aviation:opensky:all",
        cache_ttl=120,
        headers=_opensky_auth_headers(),
    )

    if data is None or not isinstance(data, dict):
        return {
            "total_aircraft": 0,
            "by_region": {},
            "busiest_origins": [],
            "error": "OpenSky API unavailable",
            "source": "opensky-domestic",
            "timestamp": _utc_now_iso(),
        }

    states = data.get("states") or []

    by_region: dict[str, dict] = {r: {"count": 0, "commercial": 0, "general": 0} for r in _AIR_REGIONS}
    by_region["other"] = {"count": 0, "commercial": 0, "general": 0}
    by_region["unknown"] = {"count": 0, "commercial": 0, "general": 0}
    country_counts: dict[str, int] = {}
    total = 0

    # Sample every Nth aircraft for map markers (keep payload <200KB)
    sample_step = 10
    sampled: list[dict] = []

    for idx, s in enumerate(states):
        if not isinstance(s, list) or len(s) < 15:
            continue
        if s[8]:  # on_ground
            continue

        total += 1
        lat, lon = s[6], s[5]
        callsign = (s[1] or "").strip()
        origin = s[2] or "Unknown"

        region = _classify_region(lat, lon)
        is_comm = _is_commercial(callsign)
        by_region[region]["count"] += 1
        if is_comm:
            by_region[region]["commercial"] += 1
        else:
            by_region[region]["general"] += 1

        country_counts[origin] = country_counts.get(origin, 0) + 1

        # Sample for map display
        if idx % sample_step == 0 and lat is not None and lon is not None:
            sampled.append({
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "callsign": callsign or None,
                "origin": origin,
                "alt": round(s[7]) if s[7] else None,
                "commercial": is_comm,
            })

    # Remove empty regions
    by_region = {k: v for k, v in by_region.items() if v["count"] > 0}

    busiest = sorted(country_counts.items(), key=lambda x: -x[1])[:15]

    return {
        "total_aircraft": total,
        "by_region": by_region,
        "busiest_origins": [{"country": c, "count": n} for c, n in busiest],
        "positions": sampled,
        "source": "opensky-domestic",
        "timestamp": _utc_now_iso(),
    }
