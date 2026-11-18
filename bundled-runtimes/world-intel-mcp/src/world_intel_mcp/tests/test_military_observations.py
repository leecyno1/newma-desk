"""Observed coordinates, learned baselines and fleet evidence boundaries."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from world_intel_mcp.analysis.inputs import AnalysisInputs
from world_intel_mcp.analysis.temporal import TemporalBaseline
from world_intel_mcp.sources import fleet, intelligence, maritime, military


def flight(identity, lat, lon):
    return {"icao24": identity, "latitude": lat, "longitude": lon, "callsign": "TEST"}


def snapshot(aircraft):
    return {"aircraft": aircraft, "count": len(aircraft), "freshness": "fresh", "status": "ok",
            "source": "test", "timestamp": "2026-10-27T00:00:00Z", "observation_id": "test:1"}


async def test_one_global_request_and_no_overlap_double_count(fetcher, monkeypatch):
    source = AsyncMock(return_value=snapshot([flight("a", 68, 25), flight("a", 68, 25), flight("b", 0, 0)]))
    monkeypatch.setattr(military, "fetch_military_flights", source)
    result = await military.fetch_theater_posture(fetcher)
    source.assert_awaited_once_with(fetcher)
    assert result["theaters"]["european"]["count"] == 1
    assert result["theaters"]["arctic"]["count"] == 1
    assert result["total_military_aircraft"] == 1
    assert result["observed_aircraft_total"] == 2


def test_regions_use_actual_coordinates_not_theater_country_shares():
    result = military.build_theater_posture(snapshot([flight("a", 35, 50)]))
    assert result["theaters"]["middle_east"]["count"] == 1
    assert result["region_observations"]["persian_gulf"]["count"] == 0
    assert result["region_observations"]["red_sea"]["count"] == 0


@pytest.mark.parametrize("flights", [{"error": "offline"}, {"status": "stale"}, {"_stale": True}])
def test_stale_or_failed_positions_never_count_as_zero(flights):
    result = military.build_theater_posture({**snapshot([]), **flights})
    assert result["status"] == "unavailable"
    assert result["total_military_aircraft"] is None


async def test_valid_empty_primary_does_not_trigger_fallback(fetcher, monkeypatch):
    monkeypatch.setattr(military, "_fetch_adsblol_military", AsyncMock(return_value=[]))
    fallback = AsyncMock()
    monkeypatch.setattr(military, "_fetch_opensky_military", fallback)
    fetcher.cache.set("military:adsblol:mil", {"ac": []}, 300)
    result = await military.fetch_military_flights(fetcher)
    assert result["count"] == 0
    assert result["status"] == "ok"
    fallback.assert_not_awaited()


async def test_adsb_units_and_unknown_country_are_honest(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "get_json", AsyncMock(return_value={"ac": [
        {"hex": "AE1234", "lat": 0, "lon": 0, "alt_baro": 10000, "gs": 100},
        {"hex": "AE2345", "lat": 1, "lon": 1, "alt_baro": "ground"},
    ]}))
    result = await military._fetch_adsblol_military(fetcher)
    assert result[0]["altitude_m"] == 3048
    assert result[0]["velocity_ms"] == pytest.approx(51.4444)
    assert result[0]["origin_country"] == ""
    assert result[0]["classification_basis"] == "provider-military-tag"
    assert result[1]["altitude_m"] is None


async def test_opensky_uses_callsigns_not_civilian_registration_prefix(fetcher, monkeypatch):
    rows = [["ae1234", "CIV123", "United States", 1793091600, 1793091601, 50, 35, 1000, False, 50, 90, 0, None, 1100, "1000", False, 0],
            ["ae5678", "RCH123", "United States", 1793091600, 1793091601, 50, 35, 1000, False, 50, 90, 0, None, 1100, "1000", False, 0]]
    monkeypatch.setattr(fetcher, "get_json", AsyncMock(return_value={"states": rows}))
    result = await military._fetch_opensky_military(fetcher)
    assert len(result) == 1
    assert result[0]["icao24"] == "ae5678"
    assert result[0]["classification_basis"] == "callsign-heuristic"
    assert result[0]["timestamp"] == "2026-10-27T09:00:00+00:00"


def test_maritime_report_renders_warning_samples_not_inferred_vessels():
    from world_intel_mcp.reports import _render_maritime
    html = _render_maritime({"waterways": [{"name": "Test", "status": "no-matched-warning", "warning_count": 0}]})
    assert "<th>Count</th>" in html and "<td>0</td>" in html
    assert "not vessel tracking" in html
    assert "unavailable" in _render_maritime({"error": "offline"})


def test_invalid_and_expired_positions_are_excluded_but_zero_is_valid():
    result = military.build_theater_posture(snapshot([
        flight("zero", 0, 0), flight("bad", 91, 0), flight("nan", float("nan"), 20),
        {**flight("old", 35, 40), "position_age_seconds": 600},
    ]))
    assert result["observed_aircraft_total"] == 1


async def test_cold_start_does_not_claim_no_surge_and_replay_does_not_train(fetcher, monkeypatch, tmp_path):
    baseline = TemporalBaseline(str(tmp_path / "baseline.sqlite"))
    monkeypatch.setattr(intelligence, "_temporal", baseline)
    posture = military.build_theater_posture(snapshot([flight("a", 25, 50)]))
    first = await intelligence.fetch_military_surge(fetcher, posture=posture)
    repeat = await intelligence.fetch_military_surge(fetcher, posture=posture)
    assert first["surge_count"] is None
    assert first == repeat
    assert baseline.summary("located_aircraft_v1:test", "persian_gulf")["samples"] == 1


async def test_surge_checks_prior_observations_before_recording_current(fetcher, monkeypatch, tmp_path):
    baseline = TemporalBaseline(str(tmp_path / "baseline.sqlite"))
    monkeypatch.setattr(intelligence, "_temporal", baseline)
    for count in [1, 2] * 5:
        baseline.record("located_aircraft_v1:test", "persian_gulf", count)
    posture = military.build_theater_posture(snapshot([flight(str(i), 25, 50) for i in range(20)]))
    result = await intelligence.fetch_military_surge(fetcher, posture=posture)
    assert result["surge_count"] == 1
    assert result["surges"][0]["aircraft_count"] == 20
    assert result["surges"][0]["sample_count"] == 10
    assert result["region_observations"]["persian_gulf"]["baseline"]["mean"] == 1.5


async def test_warning_is_matched_by_coordinates_not_repeated_globally(fetcher):
    place = intelligence.STRATEGIC_WATERWAYS[0]
    result = await intelligence.fetch_vessel_snapshot(fetcher, nav_data={
        "freshness": "fresh", "warnings": [
            {"id": "near", "text": "NAVAL EXERCISE", "coordinates": [{"lat": place["lat"], "lon": place["lon"]}]},
            {"id": "unknown", "text": "NAVAL EXERCISE", "coordinates": []},
        ],
    })
    assert result["waterways"][0]["warning_count"] == 1
    assert any(item["warning_count"] == 0 for item in result["waterways"])
    assert result["unlocated_warning_count"] == 1
    assert all(item["status"] not in {"clear", "critical"} for item in result["waterways"])


async def test_failed_navigation_does_not_claim_clear_waterways(fetcher):
    result = await intelligence.fetch_vessel_snapshot(fetcher, nav_data={"error": "offline"})
    assert result["count"] is None
    assert result["status"] == "unavailable"


def test_fleet_retains_partial_observations_without_readiness_score():
    posture = military.build_theater_posture(snapshot([flight("a", 68, 25)]))
    result = fleet.build_fleet_report({"theater_posture": posture,
        "vessel_snapshot": {"status": "unavailable", "error": "offline"},
        "military_surge": {"status": "partial", "surge_count": None}}, 10)
    assert result["total_tracked_aircraft"] == 1
    assert result["waterway_count"] is None
    assert result["readiness_score"] is None
    assert result["readiness_level"] == "NOT_ASSESSED"
    assert result["surge_count"] is None


async def test_dashboard_and_fleet_share_aviation_and_navigation(fetcher, monkeypatch, tmp_path):
    monkeypatch.setattr(intelligence, "_temporal", TemporalBaseline(str(tmp_path / "baseline.sqlite")))
    flights = AsyncMock(return_value=snapshot([]))
    warnings = AsyncMock(return_value={"freshness": "fresh", "warnings": [], "status": "ok"})
    monkeypatch.setattr(military, "fetch_military_flights", flights)
    monkeypatch.setattr(maritime, "fetch_nav_warnings", warnings)
    inputs = AnalysisInputs(fetcher)
    try:
        _, _, result = await asyncio.gather(inputs.get("military_flights"), inputs.get("nav_warnings"),
                                           fleet.fetch_fleet_report(fetcher, inputs=inputs))
        flights.assert_awaited_once()
        warnings.assert_awaited_once()
        assert result["readiness_score"] is None
        assert result["total_tracked_aircraft"] == 0
    finally:
        await inputs.close()
