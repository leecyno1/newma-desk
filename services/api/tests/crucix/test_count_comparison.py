from copy import deepcopy
from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import normalize_snapshot

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
START, END = "2026-11-14T10:51:00Z", "2026-11-14T11:01:00Z"


def payload():
    window = {"start": "2026-10-15T00:00:00Z", "end": "2026-11-14T00:00:00Z", "days": 30}
    return {"meta": {"timestamp": "2026-11-14T11:00:00Z"},
        "whoMeta": {"status": "ok", "count": 0, "collectedAt": END, "window": window}, "who": [{"title": "display is not count"}],
        "deltaState": {"status": "current", "timestamp": "2026-11-14T11:00:00Z"},
        "delta": {"timestamp": "2026-11-14T11:00:00Z", "previous": "2026-11-14T10:50:00Z",
            "summary": {"totalChanges": 1, "direction": "risk-on"}, "comparisonGaps": [],
            "signals": {"new": [], "unchanged": [], "escalated": [], "deescalated": [{
                "key": "who_alerts", "from": 3, "to": 0, "change": -3, "pctChange": -100,
                "fromDate": START, "toDate": END, "unit": "records", "changeUnit": "records",
                "countBasis": "collection-sample-v1", "countScope": {"source": "WHO-DON", "window": window, "limit": 100}}]}}}


def comparison(raw, now=NOW):
    return normalize_snapshot(raw, now=now)["comparison"]


def test_count_zero_uses_metadata_and_collection_time_not_display_or_sweep_clock():
    result = comparison(payload())
    row = result["entries"][0]
    assert (row["from"], row["to"], row["change"]) == (3, 0, -3)
    assert row["kind"] == "collection-sample" and row["timeBasis"] == "collected"
    assert row["basis"] == "collection-sample-v1" and row["countScope"]["limit"] == 100
    assert row["fromDate"] == START and row["toDate"] == END and row["currentEligible"] is True
    assert "风险下降" in row["note"] and result["reportedDirection"] is None


@pytest.mark.parametrize("patch", [
    {"countBasis": None}, {"countScope": {"source": "WHO-DON", "limit": 10}},
    {"to": 1}, {"from": -1}, {"from": True}, {"from": 2.5}, {"change": -2},
    {"pctChange": 0}, {"unit": "detections"}, {"fromDate": END},
    {"toDate": "2026-11-14T11:02:00Z"}, {"fromDate": "2026-11-14T06:51:00Z"},
    {"fromDate": "2026-11-14T10:51:00"},
])
def test_count_mismatches_are_gaps_not_zero_or_risk_on(patch):
    raw = payload()
    raw["delta"]["signals"]["deescalated"][0].update(patch)
    result = comparison(raw)
    assert result["entries"] == [] and result["gaps"][0]["key"] == "who_alerts"
    assert result["reportedDirection"] is None


@pytest.mark.parametrize("status", ["partial", "error", "unknown"])
def test_partial_current_source_does_not_confirm_old_count(status):
    raw = payload()
    raw["whoMeta"]["status"] = status
    assert comparison(raw)["entries"] == []


def test_old_restored_sample_keeps_original_time_but_is_not_current():
    raw = payload()
    raw["deltaState"]["status"] = "restored"
    result = comparison(raw, datetime(2026, 11, 20, tzinfo=UTC))
    assert result["entries"][0]["toDate"] == END
    assert result["entries"][0]["currentEligible"] is False


def test_source_collected_before_primary_batch_summary_is_not_discarded():
    raw = payload()
    raw["whoMeta"]["collectedAt"] = "2026-11-14T10:59:00Z"
    raw["delta"]["signals"]["deescalated"][0].update(
        fromDate="2026-11-14T10:49:00Z", toDate="2026-11-14T10:59:00Z")
    row = comparison(raw)["entries"][0]
    assert row["currentEligible"] is True and row["toDate"] == "2026-11-14T10:59:00Z"


def test_rss_read_cache_keeps_historical_evidence_but_failed_attempt_is_not_a_receipt():
    raw = payload()
    raw["deltaState"]["status"] = "restored"
    raw["news"] = []
    raw["newsMeta"] = {"status": "partial", "mode": "cache", "asOf": END, "cachedSources": 1, "limit": 50,
        "items": [{"url": "https://example.org/feed", "status": "ok", "dataStatus": "ok", "cached": True,
                   "asOf": END, "dataAsOf": END}]}
    entry = raw["delta"]["signals"]["deescalated"][0]
    entry.update(key="news_count", countScope={"source": "RSS", "feeds": ["https://example.org/feed"],
        "limit": 50, "selection": "regional-reserve-30d-v1"})
    result = comparison(raw)
    assert result["entries"][0]["currentEligible"] is False
    raw["deltaState"]["status"] = "current"
    assert comparison(raw)["entries"] == []
    raw["deltaState"]["status"] = "restored"
    raw["newsMeta"]["items"][0]["status"] = "error"
    assert comparison(raw)["entries"] == []


def test_rss_selection_revision_must_match_count_scope_before_passing_to_page():
    raw = payload()
    raw["news"] = []
    raw["newsMeta"] = {"status": "ok", "asOf": END, "cachedSources": 0, "limit": 50,
        "selection": "regional-reserve-30d-url-v2",
        "items": [{"url": "https://example.org/feed", "status": "ok", "cached": False, "asOf": END}]}
    row = raw["delta"]["signals"]["deescalated"][0]
    row.update(key="news_count", countScope={"source": "RSS", "feeds": ["https://example.org/feed"],
        "limit": 50, "selection": "regional-reserve-30d-v1"})
    assert comparison(raw)["entries"] == []
    row["countScope"]["selection"] = raw["newsMeta"]["selection"]
    result = comparison(raw)
    assert result["entries"][0]["countScope"]["selection"] == raw["newsMeta"]["selection"]


def test_count_rounding_is_one_decimal_and_zero_base_is_unknown_percent():
    raw = payload()
    entry = raw["delta"]["signals"]["deescalated"][0]
    raw["whoMeta"]["count"] = 2
    entry.update(to=2, change=-1, pctChange=-33.3)
    assert comparison(raw)["entries"][0]["pctChange"] == -33.3
    entry.update({"from": 0, "change": 2, "pctChange": None})
    assert comparison(raw)["entries"][0]["pctChange"] is None


@pytest.mark.parametrize("key,source,unit", [
    ("urgent_posts", "Telegram-web-preview", "records"), ("thermal_total", "FIRMS", "detections"),
    ("air_total", "OpenSky", "regional-aircraft-samples"), ("conflict_events", "ACLED", "records"),
    ("conflict_fatalities", "ACLED", "reported-fatalities"), ("sources_ok", "collection-health", "source-checks"),
])
def test_other_sample_categories_match_the_actual_endpoint_and_scope(key, source, unit):
    raw = payload()
    scope = {"source": source}
    if key == "urgent_posts":
        scope.update(channels=["public-channel"], limit=15, selection="significance-order-exclude-cyrillic-v1")
        raw["tg"] = {"status": "ok", "urgent": [], "collectedAt": END, "scope": scope}
    elif key == "thermal_total":
        scope.update(days=2, regions=[{"region": "A", "bounds": [30, 10, 40, 20]}])
        raw.update(thermal=[{"det": 0}], thermalMeta={"status": "ok", "collectedAt": END, "scope": scope})
    elif key == "air_total":
        scope.update(regions=[{"region": "A", "bounds": [30, 10, 40, 20]}])
        raw.update(air=[{"total": 0, "status": "ok", "observedAt": END}],
                   airMeta={"fallback": False, "timestamp": END, "scope": scope})
    elif key.startswith("conflict_"):
        scope.update(period={"start": "2026-11-01", "end": "2026-11-13"}, limit=200)
        raw["acled"] = {"status": "ok", "basis": "bounded-event-sample", "period": scope["period"],
            "sampleLimit": 200, "coverage": {"truncated": False}, "collectedAt": END, "totalEvents": 0, "totalFatalities": 0}
    else:
        scope = {"sources": ["FIRMS"]}
        raw["health"] = [{"n": "FIRMS", "status": "error"}]
        raw["meta"].update(sourcesQueried=1, sourcesOk=0)
    entry = raw["delta"]["signals"]["deescalated"][0]
    entry.update(key=key, countScope=deepcopy(scope), unit=unit, changeUnit=unit,
                 toDate=raw["meta"]["timestamp"] if key == "sources_ok" else END)
    row = comparison(raw)["entries"][0]
    assert row["to"] == 0 and row["countScope"] == scope
    entry["countScope"] = {"source": "different-scope"}
    assert comparison(raw)["entries"] == []
