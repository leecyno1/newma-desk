"""Coverage, real source field names and cycle-local reuse."""

import asyncio
import os
import subprocess
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from world_intel_mcp.analysis.inputs import AnalysisInputs
from world_intel_mcp.analysis.posture import build_strategic_posture, fetch_strategic_posture
from world_intel_mcp.analysis.alerts import build_alert_digest, fetch_alert_digest
from world_intel_mcp.sources import climate, health, infrastructure, intelligence, military, shipping


def test_analysis_databases_follow_explicit_cache_directory(tmp_path):
    env = {**os.environ, "WORLD_INTEL_CACHE_DB": str(tmp_path / "cache.db")}
    result = subprocess.run([sys.executable, "-c",
        "from world_intel_mcp.analysis.temporal import _DB_PATH as t; "
        "from world_intel_mcp.analysis.spikes import _DB_PATH as s; "
        "print(t); print(s)"], env=env, text=True, capture_output=True, check=True)
    assert result.stdout.splitlines() == [str(tmp_path / "temporal.db"), str(tmp_path / "keyword_spikes.db")]


def test_no_inputs_are_unknown_not_low_risk():
    posture = build_strategic_posture({})
    assert posture["composite_score"] is None
    assert posture["risk_level"] == "UNKNOWN"
    assert posture["coverage"]["available"] == 0
    assert all(item["score"] is None for item in posture["domain_scores"].values())
    alerts = build_alert_digest({})
    assert alerts["alert_count"] is None
    assert alerts["domains_checked"] == []


def test_actual_cyber_climate_outage_fields_are_used():
    inputs = {
        "cyber_threats": {"count": 33, "feeds_successful": 2, "feeds_attempted": 4},
        "climate_anomalies": {"status": "partial", "zones": {
            "arctic": {"temp_anomaly_c": 4.0, "is_significant": True},
            "sahel": {"temp_anomaly_c": 0.0, "is_significant": False},
        }},
        "internet_outages": {"status": "ok", "ongoing_count": 6},
        "cable_health": {"status": "ok", "corridors": {"a": {"status_score": 0}}},
    }
    posture = build_strategic_posture(inputs)
    assert posture["domain_scores"]["cyber"]["score"] == 66
    assert posture["domain_scores"]["climate"]["score"] == 18
    assert posture["domain_scores"]["infrastructure"]["score"] is None
    assert posture["composite_score"] is None
    assert posture["coverage"]["available"] == 2
    alerts = build_alert_digest(inputs)
    assert alerts["alert_count"] == 1
    assert alerts["alerts"][0]["value"] == 6
    assert alerts["coverage"]["available"] == 1


@pytest.mark.parametrize("invalid", [{"error": "failed"}, {"_stale": True}, {"status": "unavailable"}, {"current_kp": None}, {"current_kp": False}])
def test_failed_or_stale_input_never_generates_alert(invalid):
    data = {"current_kp": 8, **invalid}
    assert build_strategic_posture({"space_weather": data})["domain_scores"]["space"]["score"] is None
    assert build_alert_digest({"space_weather": data})["alert_count"] is None


def test_valid_zero_is_a_partial_empty_sample_not_global_safety():
    inputs = {"space_weather": {"status": "ok", "current_kp": 0}}
    assert build_strategic_posture(inputs)["domain_scores"]["space"]["score"] == 0
    alerts = build_alert_digest(inputs)
    assert alerts["alert_count"] == 0
    assert alerts["status"] == "partial"
    assert alerts["coverage"]["available"] == 1
    assert alerts["coverage"]["expected"] == 7


async def test_three_consumers_share_one_cycle_fetch():
    inputs = AnalysisInputs(None)
    calls = {}

    async def source(name):
        calls[name] = calls.get(name, 0) + 1
        await asyncio.sleep(0)
        return {"current_kp": 6, "status": "ok"} if name == "space_weather" else {"error": "not configured"}

    inputs.factories = {name: lambda name=name: source(name) for name in inputs.factories}
    try:
        raw, posture, alerts = await asyncio.gather(
            inputs.get("space_weather"), fetch_strategic_posture(None, inputs=inputs),
            fetch_alert_digest(None, inputs=inputs),
        )
        assert raw["current_kp"] == 6
        assert posture["domain_scores"]["space"]["score"] == 66
        assert alerts["alert_count"] == 1
        assert set(calls.values()) == {1}
        assert len(calls) == 11
    finally:
        await inputs.close()
    assert all(task.done() for task in inputs.tasks.values())


async def test_cancelled_consumer_does_not_cancel_shared_source_and_close_reaps():
    inputs = AnalysisInputs(None)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def waiting():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    inputs.factories["space_weather"] = waiting
    consumer = asyncio.create_task(inputs.get("space_weather"))
    await started.wait()
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)
    assert not inputs.tasks["space_weather"].done()
    await inputs.close()
    assert stopped.is_set()


async def test_shipping_missing_and_zero_quotes(fetcher, monkeypatch):
    quote = AsyncMock(return_value=None)
    monkeypatch.setattr(shipping, "_fetch_yahoo_quote", quote)
    failed = await shipping.fetch_shipping_index(fetcher)
    assert failed["stress_score"] is None
    assert failed["assessment"] == "unknown"
    quote.return_value = {"change_pct": 0, "price": 1}
    valid = await shipping.fetch_shipping_index(fetcher)
    assert valid["stress_score"] == 0
    assert valid["status"] == "ok"


async def test_infrastructure_failure_is_not_clear(fetcher, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setattr(fetcher, "get_json", AsyncMock(return_value=None))
    outage = await infrastructure.fetch_internet_outages(fetcher)
    cable = await infrastructure.fetch_cable_health(fetcher)
    assert outage["ongoing_count"] is None
    assert all(c["status_score"] is None for c in cable["corridors"].values())
    assert build_alert_digest({"internet_outages": outage, "cable_health": cable})["alert_count"] is None


async def test_missing_theaters_do_not_pollute_surge_baseline(fetcher, monkeypatch):
    monkeypatch.setattr(military, "fetch_military_flights", AsyncMock(return_value={"source": "none", "error": "failed"}))
    recorder = Mock()
    monkeypatch.setattr(intelligence._temporal, "record_and_check", recorder)
    posture = await military.fetch_theater_posture(fetcher)
    surge = await intelligence.fetch_military_surge(fetcher, posture=posture)
    assert posture["total_military_aircraft"] is None
    assert surge["surge_count"] is None
    recorder.assert_not_called()


async def test_hotspots_without_conflict_data_are_unknown(fetcher, monkeypatch):
    monkeypatch.setattr(intelligence, "acled_query", AsyncMock(return_value=None))
    theater = AsyncMock()
    monkeypatch.setattr(military, "fetch_theater_posture", theater)
    result = await intelligence.fetch_hotspot_escalation(fetcher)
    assert result["status"] == "unavailable"
    assert result["count"] is None
    theater.assert_not_awaited()


async def test_empty_climate_response_cannot_create_zero_anomaly(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "get_json", AsyncMock(return_value={"daily": {}}))
    result = await climate.fetch_climate_anomalies(fetcher, zones=["arctic"])
    assert result["status"] == "unavailable"
    assert result["zones"] == {}


async def test_historical_health_reports_remain_visible_but_do_not_score(fetcher, monkeypatch):
    xml = '<rss version="2.0"><channel><title>Test</title><item><title>Ebola report</title><pubDate>Wed, 01 Jan 2020 00:00:00 GMT</pubDate></item></channel></rss>'
    monkeypatch.setattr(health, "_HEALTH_FEEDS", [("Test", "https://example.test/feed")])
    fetcher.cache.set("health:rss:test", xml, 300)
    monkeypatch.setattr(fetcher, "get_xml", AsyncMock(return_value=xml))
    result = await health.fetch_disease_outbreaks(fetcher)
    assert len(result["items"]) == 1
    assert result["current_count"] == 0
    assert result["high_concern_count"] == 0
    assert build_strategic_posture({"disease_outbreaks": result})["domain_scores"]["health"]["score"] == 0
