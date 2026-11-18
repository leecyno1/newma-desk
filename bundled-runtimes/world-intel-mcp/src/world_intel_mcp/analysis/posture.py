"""Strategic posture assessment — composite risk from all intelligence domains.

Aggregates scores from 9 domains into an overall global risk assessment.
Each domain is scored 0-100 with a weight, producing a weighted composite.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .inputs import AnalysisInputs, input_status, number

logger = logging.getLogger("world-intel-mcp.analysis.posture")


# Domain weights (sum to 1.0)
DOMAIN_WEIGHTS: dict[str, float] = {
    "military": 0.18,
    "political": 0.16,
    "conflict": 0.16,
    "infrastructure": 0.10,
    "economic": 0.10,
    "cyber": 0.08,
    "health": 0.07,
    "climate": 0.08,
    "space": 0.07,
}


def _risk_level(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    elif score >= 55:
        return "HIGH"
    elif score >= 35:
        return "ELEVATED"
    elif score >= 20:
        return "GUARDED"
    return "LOW"


def _score_military(surge_data: dict, posture_data: dict) -> tuple[float, list[str]]:
    """Score military domain 0-100 from surge + theater posture."""
    signals: list[str] = []
    score = 0.0

    surge_count = surge_data.get("surge_count", 0)
    if surge_count > 0:
        score += min(50.0, surge_count * 20.0)
        surges = surge_data.get("surges", [])
        for s in surges[:3]:
            signals.append(f"Surge: {s.get('region', 'unknown')} ({s.get('aircraft_count', '?')} aircraft)")

    theaters = posture_data.get("theaters", {})
    # theaters is a dict keyed by theater name, values are dicts with "count"
    if isinstance(theaters, dict):
        active_theaters = [(name, t) for name, t in theaters.items() if isinstance(t, dict) and number(t.get("count")) and t["count"] > 10]
    else:
        active_theaters = []
    score += min(50.0, len(active_theaters) * 12.0)
    for name, t in active_theaters[:3]:
        signals.append(f"{name}: {t.get('count', 0)} aircraft")

    return min(100.0, score), signals


def _score_political(instability_data: dict) -> tuple[float, list[str]]:
    """Score political domain 0-100 from instability index."""
    signals: list[str] = []
    countries = instability_data.get("countries", [])
    if not countries:
        return 0.0, signals

    # Average of top-5 CII scores
    top5 = sorted(countries, key=lambda c: c.get("instability_index", 0), reverse=True)[:5]
    avg = sum(c.get("instability_index", 0) for c in top5) / len(top5)
    for c in top5[:3]:
        signals.append(f"{c.get('country_name', c.get('country_code', '?'))}: CII {c.get('instability_index', 0)}")

    return min(100.0, avg), signals


def _score_conflict(hotspot_data: dict) -> tuple[float, list[str]]:
    """Score conflict domain 0-100 from hotspot escalation."""
    signals: list[str] = []
    hotspots = hotspot_data.get("hotspots", [])
    if not hotspots:
        return 0.0, signals

    top5 = sorted(hotspots, key=lambda h: h.get("score", 0), reverse=True)[:5]
    avg = sum(h.get("score", 0) for h in top5) / len(top5)
    for h in top5[:3]:
        signals.append(f"{h.get('name', '?')}: {h.get('score', 0)}/100")

    return min(100.0, avg), signals


def _score_infrastructure(cable_data: dict, outage_data: dict) -> tuple[float, list[str]]:
    """Score infrastructure 0-100 from cable health + outages."""
    signals: list[str] = []
    score = 0.0

    # Cable health is unassessed; the input gate prevents a complete score.
    # Navigation warning counts must not be converted into damage risk points.

    outage_count = outage_data.get("ongoing_count", 0)
    score += min(50.0, outage_count * 5.0)
    if outage_count > 0:
        signals.append(f"{outage_count} internet outages")

    return min(100.0, score), signals


def _score_economic(shipping_data: dict) -> tuple[float, list[str]]:
    """Score economic 0-100 from shipping stress."""
    signals: list[str] = []
    stress = shipping_data.get("stress_score", 0)
    assessment = shipping_data.get("assessment", "unknown")
    if stress > 0:
        signals.append(f"Shipping stress: {stress} ({assessment})")
    return min(100.0, stress), signals


def _score_cyber(cyber_data: dict) -> tuple[float, list[str]]:
    """Score cyber 0-100 from threat intelligence."""
    signals: list[str] = []
    threat_count = cyber_data.get("count", 0)
    score = min(100.0, threat_count * 2.0)
    if threat_count > 0:
        signals.append(f"{threat_count} threat records in monitored feeds")
    by_source = cyber_data.get("by_type", {})
    for src, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:2]:
        signals.append(f"{src}: {count}")
    return score, signals


def _score_health(health_data: dict) -> tuple[float, list[str]]:
    """Score health 0-100 from disease outbreaks."""
    signals: list[str] = []
    count = health_data.get("current_count", health_data.get("count", 0))
    high_concern = health_data.get("high_concern_count", 0)
    score = min(100.0, high_concern * 25.0 + count * 3.0)
    if high_concern > 0:
        signals.append(f"{high_concern} recent reports mentioning high-concern pathogens (not confirmed outbreaks)")
    if count > 0:
        signals.append(f"{count} health feed reports (not confirmed active outbreaks)")
    return score, signals


def _score_climate(climate_data: dict) -> tuple[float, list[str]]:
    """Score climate 0-100 from anomalies."""
    signals: list[str] = []
    anomalies = [{"zone": name, **value} for name, value in climate_data.get("zones", {}).items() if value.get("is_significant")]
    extreme = [a for a in anomalies if abs(a.get("temp_anomaly_c", 0)) > 3.0]
    score = min(100.0, len(extreme) * 15.0 + len(anomalies) * 3.0)
    for a in extreme[:2]:
        signals.append(f"{a.get('zone', '?')}: {a.get('temp_anomaly_c', 0):+.1f}°C")
    return score, signals


def _score_space(sw_data: dict) -> tuple[float, list[str]]:
    """Score space weather 0-100 from Kp index."""
    signals: list[str] = []
    kp = sw_data.get("current_kp")
    if kp is None:
        return 0.0, signals
    # Kp 0-9 mapped to 0-100
    score = min(100.0, kp * 11.0)
    signals.append(f"Kp={kp} ({sw_data.get('kp_level', 'Unknown')})")
    return score, signals


DOMAIN_INPUTS = {
    "military": ("military_surge", "theater_posture"),
    "political": ("instability",),
    "conflict": ("hotspot_escalation",),
    "infrastructure": ("cable_health", "internet_outages"),
    "economic": ("shipping_index",),
    "cyber": ("cyber_threats",),
    "health": ("disease_outbreaks",),
    "climate": ("climate_anomalies",),
    "space": ("space_weather",),
}


def build_strategic_posture(inputs: dict) -> dict:
    """Keep observed domain scores; never zero-fill the composite."""
    scorers = {
        "military": _score_military, "political": _score_political,
        "conflict": _score_conflict, "infrastructure": _score_infrastructure,
        "economic": _score_economic, "cyber": _score_cyber,
        "health": _score_health, "climate": _score_climate, "space": _score_space,
    }
    domain_scores = {}
    for domain, names in DOMAIN_INPUTS.items():
        states = {name: input_status(name, inputs.get(name, {})) for name in names}
        missing = [name for name, state in states.items() if state == "unavailable"]
        status = "unavailable" if missing else "ok" if all(s == "ok" for s in states.values()) else "partial"
        score, signals = (None, []) if missing else scorers[domain](*(inputs[name] for name in names))
        domain_scores[domain] = {
            "score": round(score, 1) if score is not None else None,
            "level": _risk_level(score) if score is not None else "UNKNOWN",
            "signals": signals, "status": status, "inputs": states,
            "missing": missing,
        }

    available = [name for name, value in domain_scores.items() if value["score"] is not None]
    complete = [name for name, value in domain_scores.items() if value["status"] == "ok"]
    composite = sum(domain_scores[name]["score"] * weight for name, weight in DOMAIN_WEIGHTS.items()) if len(complete) == len(DOMAIN_WEIGHTS) else None
    signals = [
        {"domain": name, "signal": signal, "domain_score": value["score"], "status": value["status"]}
        for name, value in domain_scores.items() for signal in value["signals"]
    ]
    signals.sort(key=lambda item: item["domain_score"], reverse=True)
    return {
        "composite_score": round(composite, 1) if composite is not None else None,
        "risk_level": _risk_level(composite) if composite is not None else "UNKNOWN",
        "status": "ok" if composite is not None else "partial" if available else "unavailable",
        "domain_scores": domain_scores, "weights": DOMAIN_WEIGHTS,
        "top_threats": signals[:10], "domains_assessed": len(available),
        "coverage": {
            "available": len(available), "complete": len(complete), "expected": len(DOMAIN_WEIGHTS),
            "missing": [name for name in DOMAIN_WEIGHTS if name not in available],
            "partial": [name for name in available if name not in complete],
        },
        "note": "Heuristic monitored-sample scores, not calibrated probabilities. Missing or partial inputs prevent a complete composite; legacy political/conflict models include static baselines and proxies.",
        "source": "strategic-posture-assessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_strategic_posture(fetcher, *, inputs=None) -> dict:
    owned = inputs is None
    inputs = inputs or AnalysisInputs(fetcher)
    try:
        names = tuple(dict.fromkeys(name for names in DOMAIN_INPUTS.values() for name in names))
        return build_strategic_posture(await inputs.collect(names))
    finally:
        if owned:
            await inputs.close()
