"""Aviation and waterway observations. These inputs cannot establish fleet readiness."""

from datetime import datetime, timezone

from ..analysis.inputs import AnalysisInputs


def build_fleet_report(inputs: dict, naval_base_count: int) -> dict:
    posture = inputs.get("theater_posture", {})
    vessel = inputs.get("vessel_snapshot", {})
    surge = inputs.get("military_surge", {})
    available = [name for name, data in inputs.items() if data and not data.get("error")
                 and data.get("status") not in {"unavailable", "stale"}]
    theaters = posture.get("theaters", {}) if "theater_posture" in available else {}
    waterways = vessel.get("waterways", []) if "vessel_snapshot" in available else []
    return {
        "status": "partial" if available else "unavailable",
        "readiness_score": None, "readiness_level": "NOT_ASSESSED",
        "observation_basis": "public-aviation-and-navigation-warning-samples",
        "coverage": {"available": len(available), "expected": 3,
                     "missing": [name for name in inputs if name not in available]},
        "input_status": {name: data.get("status", "unknown") for name, data in inputs.items()},
        "theater_summary": [{"name": name, "aircraft_count": row.get("count"),
                            "bbox": row.get("bbox")} for name, row in theaters.items()],
        "theater_count": len(theaters) if theaters else None,
        "total_tracked_aircraft": posture.get("total_military_aircraft") if theaters else None,
        "waterway_summary": [{"name": row["name"], "status": row["status"], "warning_count": row["warning_count"],
                             "location_basis": row["location_basis"]} for row in waterways],
        "waterway_count": len(waterways) if "vessel_snapshot" in available else None,
        "unlocated_warning_count": vessel.get("unlocated_warning_count"),
        "active_surges": surge.get("surges", []) if "military_surge" in available else [],
        "surge_count": surge.get("surge_count") if "military_surge" in available else None,
        "baseline_coverage": surge.get("coverage", {}),
        "naval_base_count": naval_base_count,
        "naval_base_basis": "static-reference",
        "note": "Aircraft broadcasts, nearby navigation warnings and reference base locations do not establish naval fleet size or combat readiness. Unknown components stay unknown; anomalies require a learned observation baseline.",
        "source": "fleet-activity-report",
        "source_times": {name: data.get("timestamp") for name, data in inputs.items()},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_fleet_report(fetcher, *, inputs=None) -> dict:
    from . import geospatial
    owned = inputs is None
    inputs = inputs or AnalysisInputs(fetcher)
    try:
        data = await inputs.collect(("theater_posture", "vessel_snapshot", "military_surge"))
        bases = await geospatial.fetch_military_bases(base_type="naval_base")
        return build_fleet_report(data, bases["count"])
    finally:
        if owned:
            await inputs.close()
