"""Space weather and solar activity source for world-intel-mcp.

Provides real-time solar activity monitoring via NOAA's Space Weather
Prediction Center (SWPC). No API key required.

Data includes:
- Solar flare activity (X-ray flux class)
- Geomagnetic storm indices (Kp, Dst)
- Solar wind speed and density
- Coronal mass ejection (CME) alerts
"""

import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.space_weather")

# ---------------------------------------------------------------------------
# NOAA SWPC endpoints (all free, no API key)
# ---------------------------------------------------------------------------

_SWPC_BASE = "https://services.swpc.noaa.gov"

# 3-day solar/geomagnetic forecast
_FORECAST_URL = f"{_SWPC_BASE}/products/noaa-planetary-k-index-forecast.json"

# Current planetary K-index (geomagnetic disturbance, 0-9)
_KP_URL = f"{_SWPC_BASE}/products/noaa-planetary-k-index.json"

# Recent solar flares (R1-R5 scale)
_FLARE_URL = f"{_SWPC_BASE}/json/goes/primary/xrays-6-hour.json"

# Solar wind real-time plasma data
_PLASMA_URL = f"{_SWPC_BASE}/products/solar-wind/plasma-7-day.json"

# Alerts and warnings
_ALERTS_URL = f"{_SWPC_BASE}/products/alerts.json"

_CACHE_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_kp(kp: float) -> str:
    """Classify Kp index into storm level."""
    if kp >= 9:
        return "G5 Extreme"
    elif kp >= 8:
        return "G4 Severe"
    elif kp >= 7:
        return "G3 Strong"
    elif kp >= 6:
        return "G2 Moderate"
    elif kp >= 5:
        return "G1 Minor"
    elif kp >= 4:
        return "Active"
    else:
        return "Quiet"


def _classify_xray(flux: float) -> str:
    """Classify X-ray flux into flare class (A, B, C, M, X)."""
    if flux >= 1e-4:
        return f"X{flux / 1e-4:.1f}"
    elif flux >= 1e-5:
        return f"M{flux / 1e-5:.1f}"
    elif flux >= 1e-6:
        return f"C{flux / 1e-6:.1f}"
    elif flux >= 1e-7:
        return f"B{flux / 1e-7:.1f}"
    else:
        return "A"


def _parse_kp_row(row) -> tuple[str | None, float] | None:
    """Parse NOAA Kp rows from either current dict or legacy list payloads."""
    try:
        if isinstance(row, dict):
            raw_kp = row.get("Kp", row.get("kp"))
            if raw_kp is None:
                return None
            return row.get("time_tag") or row.get("time"), float(raw_kp)
        if isinstance(row, list) and len(row) >= 2:
            return row[0], float(row[1])
    except (ValueError, TypeError):
        return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_space_weather(fetcher: Fetcher) -> dict:
    """Fetch current space weather conditions from NOAA SWPC.

    Returns a composite view of solar and geomagnetic activity including
    current Kp index, latest X-ray flux class, solar wind speed, and
    any active alerts/warnings.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with current conditions, alerts, forecast, and metadata.
    """
    import asyncio

    # Fetch all sources in parallel
    kp_data, flare_data, alerts_data = await asyncio.gather(
        fetcher.get_json(
            _KP_URL,
            source="swpc",
            cache_key="space:kp",
            cache_ttl=_CACHE_TTL,
        ),
        fetcher.get_json(
            _FLARE_URL,
            source="swpc",
            cache_key="space:xray",
            cache_ttl=_CACHE_TTL,
        ),
        fetcher.get_json(
            _ALERTS_URL,
            source="swpc",
            cache_key="space:alerts",
            cache_ttl=_CACHE_TTL,
        ),
    )

    result: dict = {
        "current_kp": None,
        "kp_level": "Unknown",
        "latest_flare_class": None,
        "solar_wind_speed_km_s": None,
        "alerts": [],
        "kp_recent": [],
        "source": "noaa-swpc",
        "timestamp": _utc_now_iso(),
    }

    # --- Kp index ---
    if kp_data and isinstance(kp_data, list) and len(kp_data) > 1:
        # NOAA has served both legacy list rows [time_tag, Kp, ...] and
        # current dict rows {"time_tag": "...", "Kp": ...}; tolerate both.
        latest = next(
            (
                parsed
                for parsed in (_parse_kp_row(row) for row in reversed(kp_data))
                if parsed is not None
            ),
            None,
        )
        if latest is not None:
            _, kp_val = latest
            result["current_kp"] = kp_val
            result["kp_level"] = _classify_kp(kp_val)

        recent = []
        for row in kp_data[-8:]:
            parsed = _parse_kp_row(row)
            if parsed is None:
                continue
            row_time, kp_val = parsed
            recent.append({
                "time": row_time,
                "kp": kp_val,
            })
        result["kp_recent"] = recent

    # --- X-ray flux (flare activity) ---
    if flare_data and isinstance(flare_data, list):
        try:
            # Last entry has the most recent flux reading
            latest_flare = flare_data[-1]
            if isinstance(latest_flare, dict):
                flux = latest_flare.get("flux")
                if flux is not None:
                    result["latest_flare_class"] = _classify_xray(float(flux))
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Failed to parse X-ray flux: %s", exc)

    # --- Alerts ---
    if alerts_data and isinstance(alerts_data, list):
        alerts = []
        for alert in alerts_data[:10]:
            if isinstance(alert, dict):
                alerts.append({
                    "issue_datetime": alert.get("issue_datetime"),
                    "message": (alert.get("message") or "")[:200],
                    "product_id": alert.get("product_id"),
                })
        result["alerts"] = alerts

    return result
