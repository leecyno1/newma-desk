"""Alert digest and weekly trends analysis for world-intel-mcp.

Provides cross-domain alert aggregation (intel_alert_digest) and
temporal trend analysis (intel_weekly_trends). Both use lazy imports
to avoid circular dependencies with source modules.
"""

import asyncio
import logging
import math
import sqlite3
from datetime import datetime, timezone

from .inputs import AnalysisInputs, input_status

logger = logging.getLogger("world-intel-mcp.analysis.alerts")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _safe_fetch(coro, label: str) -> dict:
    """Run a coroutine safely, returning empty dict on failure."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("Alert digest: %s failed: %s", label, exc)
        return {}


# ---------------------------------------------------------------------------
# Alert Digest
# ---------------------------------------------------------------------------

_ALERT_THRESHOLDS: dict[str, dict] = {
    "space_weather": {
        "field": "current_kp",
        "threshold": 5.0,
        "priority": "high",
        "domain": "space",
        "message_template": "Geomagnetic storm: Kp={value} ({level})",
    },
    "instability": {
        "field": "countries",
        "threshold": 70,
        "priority": "critical",
        "domain": "political",
        "message_template": "{count} countries above instability threshold",
    },
    "military_surge": {
        "field": "surge_count",
        "threshold": 1,
        "priority": "high",
        "domain": "military",
        "message_template": "{count} regional aircraft sample anomalies; not verified deployments",
    },
    "hotspot_escalation": {
        "field": "hotspots",
        "threshold": 60,
        "priority": "critical",
        "domain": "security",
        "message_template": "{count} hotspots above escalation threshold",
    },
    "internet_outages": {
        "field": "outage_count",
        "threshold": 5,
        "priority": "medium",
        "domain": "infrastructure",
        "message_template": "{count} internet outages active",
    },
    "shipping_stress": {
        "field": "stress_score",
        "threshold": 30.0,
        "priority": "medium",
        "domain": "economic",
        "message_template": "Shipping stress index at {value}",
    },
}


ALERT_INPUTS = (
    "space_weather", "instability", "military_surge", "cable_health",
    "hotspot_escalation", "internet_outages", "shipping_index",
)


async def fetch_alert_digest(fetcher, *, inputs=None) -> dict:
    owned = inputs is None
    inputs = inputs or AnalysisInputs(fetcher)
    try:
        return build_alert_digest(await inputs.collect(ALERT_INPUTS))
    finally:
        if owned:
            await inputs.close()


def build_alert_digest(inputs: dict) -> dict:
    states = {name: input_status(name, inputs.get(name, {})) for name in ALERT_INPUTS}
    usable = {name: inputs[name] if states[name] != "unavailable" else {} for name in ALERT_INPUTS}
    sw_data, instability_data, surge_data, _cable_data, hotspot_data, outage_data, shipping_data = (usable[name] for name in ALERT_INPUTS)
    alerts: list[dict] = []

    # Space weather: Kp >= 5
    kp = sw_data.get("current_kp")
    if kp is not None and kp >= _ALERT_THRESHOLDS["space_weather"]["threshold"]:
        alerts.append({
            "domain": "space",
            "priority": "high",
            "message": f"Geomagnetic storm: Kp={kp} ({sw_data.get('kp_level', 'Unknown')})",
            "value": kp,
        })

    # Instability: countries above threshold
    countries = instability_data.get("countries", [])
    high_instability = [c for c in countries if c.get("instability_index", 0) >= 70]
    if high_instability:
        alerts.append({
            "domain": "political",
            "priority": "critical",
            "message": f"{len(high_instability)} countries above instability threshold (>=70)",
            "countries": [c.get("country_name", c.get("country_code")) for c in high_instability[:5]],
            "value": len(high_instability),
        })

    # Military surge
    surge_count = surge_data.get("surge_count", 0)
    if surge_count >= 1:
        alerts.append({
            "domain": "military",
            "priority": "high",
            "message": f"{surge_count} regional aircraft sample anomalies; not verified deployments",
            "surges": surge_data.get("surges", [])[:3],
            "value": surge_count,
        })

    # Cable observations remain in coverage as unassessed, never damage alerts.

    # Hotspot escalation: hotspots with score >= 60
    hotspots = hotspot_data.get("hotspots", [])
    hot = [h for h in hotspots if h.get("score", 0) >= 60]
    if hot:
        alerts.append({
            "domain": "security",
            "priority": "critical",
            "message": f"{len(hot)} hotspots above escalation threshold",
            "hotspots": [h.get("name") for h in hot[:5]],
            "value": len(hot),
        })

    # Internet outages
    outage_count = outage_data.get("ongoing_count", 0)
    if outage_count >= 5:
        alerts.append({
            "domain": "infrastructure",
            "priority": "medium",
            "message": f"{outage_count} internet outages active",
            "value": outage_count,
        })

    # Shipping stress
    stress = shipping_data.get("stress_score", 0)
    if stress >= 30:
        alerts.append({
            "domain": "economic",
            "priority": "medium" if stress < 60 else "high",
            "message": f"Shipping stress index at {stress} ({shipping_data.get('assessment', 'unknown')})",
            "value": stress,
        })

    # Sort: critical > high > medium
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: priority_order.get(a.get("priority", "low"), 4))

    # Group by priority
    by_priority: dict[str, int] = {}
    for a in alerts:
        p = a.get("priority", "unknown")
        by_priority[p] = by_priority.get(p, 0) + 1

    checked = [name for name, state in states.items() if state != "unavailable"]
    complete = [name for name, state in states.items() if state == "ok"]
    return {
        "status": "ok" if len(complete) == len(ALERT_INPUTS) else "partial" if checked else "unavailable",
        "coverage": {
            "available": len(checked), "complete": len(complete), "expected": len(ALERT_INPUTS),
            "missing": [name for name in ALERT_INPUTS if name not in checked],
            "partial": [name for name in checked if name not in complete],
        },
        "input_status": states,
        "note": "Alerts describe only the monitored sample. Missing checks are not evidence of safety; political/conflict inputs include static baselines and proxies.",
        "alerts": alerts,
        "alert_count": len(alerts) if checked else None,
        "by_priority": by_priority,
        "domains_checked": checked,
        "source": "alert-digest",
        "timestamp": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Weekly Trends
# ---------------------------------------------------------------------------

async def fetch_weekly_trends(fetcher) -> dict:
    """Analyze weekly trends from temporal baselines.

    Reads the TemporalBaseline SQLite database to compute volatility
    (coefficient of variation) for each tracked metric, and calls
    temporal_anomalies to get current deviations.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with trends, trend_count, analysis_period, source.
    """
    from ..analysis.temporal import TemporalBaseline, _DB_PATH
    from ..sources import intelligence

    now = datetime.now(timezone.utc)

    # Get current anomalies
    anomaly_data = await _safe_fetch(
        intelligence.fetch_temporal_anomalies(fetcher), "temporal_anomalies"
    )

    # Read baselines from SQLite
    trends: list[dict] = []

    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT key, count, mean, m2, updated_at FROM baselines WHERE count >= 5"
        ).fetchall()
        conn.close()

        for key, n, mean, m2, updated_at in rows:
            parts = key.split(":")
            if len(parts) < 2:
                continue

            event_type = parts[0]
            region = parts[1]
            weekday = parts[2] if len(parts) > 2 else ""
            month = parts[3] if len(parts) > 3 else ""

            # Compute coefficient of variation (volatility)
            variance = m2 / (n - 1) if n > 1 else 0.0
            std = math.sqrt(variance) if variance > 0 else 0.0
            cv = (std / mean * 100) if mean > 0 else 0.0

            trends.append({
                "metric": event_type,
                "region": region,
                "weekday": weekday,
                "month": month,
                "observations": n,
                "mean": round(mean, 2),
                "std_dev": round(std, 2),
                "volatility_cv": round(cv, 1),
                "last_updated": updated_at,
            })

    except (sqlite3.Error, OSError) as exc:
        logger.warning("Failed to read temporal baselines: %s", exc)

    # Sort by volatility descending
    trends.sort(key=lambda t: t.get("volatility_cv", 0), reverse=True)

    # Attach current anomalies
    current_anomalies = anomaly_data.get("anomalies", [])

    return {
        "trends": trends[:50],
        "trend_count": len(trends),
        "current_anomalies": current_anomalies,
        "current_anomaly_count": len(current_anomalies),
        "analysis_period": "weekly (by weekday+month seasonality)",
        "source": "temporal-weekly-trends",
        "timestamp": _utc_now_iso(),
    }
