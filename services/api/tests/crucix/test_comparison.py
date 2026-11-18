from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import normalize_snapshot

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def payload():
    return {"meta": {"timestamp": "2026-11-14T11:00:00Z"},
            "fred": [{"id": "VIXCLS", "value": 25, "date": "2026-11-13"}],
            "deltaState": {"status": "current", "timestamp": "2026-11-14T11:00:00Z"},
            "delta": {"timestamp": "2026-11-14T11:00:00Z", "previous": "2026-11-13T11:00:00Z",
                      "summary": {"totalChanges": 1, "direction": "mixed"},
                      "signals": {"new": [], "escalated": [{"key": "vix", "label": "VIX", "from": 20, "to": 25,
                          "change": 5, "pctChange": 25, "fromDate": "2026-11-12", "toDate": "2026-11-13",
                          "seriesId": "VIXCLS", "unit": "index points", "changeUnit": "index points"}],
                                  "deescalated": [], "unchanged": []}, "comparisonGaps": []}}


def comparison(raw):
    return normalize_snapshot(raw, now=NOW)["comparison"]


def test_current_comparison_keeps_dated_numbers_separate_from_risk_rating():
    result = comparison(payload())
    assert result["status"] == "current" and result["changeCount"] == 1
    assert result["timestamp"] == "2026-11-14T11:00:00Z"
    assert result["entries"][0] == {"key": "vix", "label": "VIX", "from": 20, "to": 25, "change": 5,
        "pctChange": 25, "fromDate": "2026-11-12", "toDate": "2026-11-13", "seriesId": "VIXCLS",
        "unit": "index points", "changeUnit": "index points", "direction": "up", "currentEligible": True,
        "basis": "dated-source-comparison", "source": "FRED"}
    assert result["reportedDirection"] == "mixed" and "非风险评级" in result["note"]


@pytest.mark.parametrize("state,delta", [("baseline", None), ("unavailable", None), (None, None)])
def test_no_comparison_is_not_unchanged_or_zero(state, delta):
    raw = payload()
    raw["deltaState"]["status"], raw["delta"] = state, delta
    result = comparison(raw)
    assert result["status"] == (state or "unavailable")
    assert result["changeCount"] is None and result["entries"] == []


@pytest.mark.parametrize("change", [
    {"fromDate": "2026-11-13"}, {"fromDate": None}, {"toDate": "2026-11-12"},
    {"to": 26}, {"unit": "%"}, {"change": -5}, {"pctChange": 500},
])
def test_revision_legacy_mismatch_or_bad_arithmetic_is_a_gap(change):
    raw = payload()
    raw["delta"]["signals"]["escalated"][0].update(change)
    result = comparison(raw)
    assert result["entries"] == [] and result["gaps"][0]["key"] == "vix"


def test_unverified_count_zero_and_notices_do_not_become_risk_deescalation():
    raw = payload()
    raw["delta"]["signals"]["deescalated"] = [{"key": "conflict_events", "from": 20, "to": 0, "change": -20}]
    raw["delta"]["signals"]["new"] = [{"key": "source_degradation", "reason": "source heuristic"}]
    raw["delta"]["summary"]["totalChanges"] = 3
    result = comparison(raw)
    assert result["changeCount"] == 1
    assert {row["key"] for row in result["gaps"]} == {"conflict_events", "source-notices"}


def test_restored_comparison_keeps_old_timestamp_and_is_not_current_eligible():
    raw = payload()
    for row in [raw["meta"], raw["deltaState"], raw["delta"]]: row["timestamp"] = "2026-11-01T12:00:00Z"
    raw["delta"]["previous"] = "2026-10-31T12:00:00Z"
    raw["deltaState"]["status"] = "restored"
    raw["fred"][0]["date"] = "2026-10-30"
    raw["delta"]["signals"]["escalated"][0].update(fromDate="2026-10-29", toDate="2026-10-30")
    result = comparison(raw)
    assert result["status"] == "restored" and result["freshness"]["status"] == "stale"
    assert result["entries"][0]["currentEligible"] is False


@pytest.mark.parametrize("patch", [{"timestamp": "2026-11-13T11:00:00Z"}, {"previous": "2026-11-14T12:00:00Z"}])
def test_different_batch_or_nonforward_comparison_is_unavailable(patch):
    raw = payload()
    raw["delta"].update(patch)
    result = comparison(raw)
    assert result["status"] == "unavailable" and result["changeCount"] is None


def test_real_zero_basis_and_decrease_keep_absolute_change_not_invented_percent():
    raw = payload()
    raw["fred"][0].update(id="T10Y2Y", value=-.2)
    entry = raw["delta"]["signals"]["escalated"].pop()
    entry.update(key="10y2y", seriesId="T10Y2Y", **{"from": 0, "to": -.2, "change": -.2,
                 "pctChange": None, "unit": "percentage points", "changeUnit": "percentage points"})
    raw["delta"]["signals"]["deescalated"] = [entry]
    row = comparison(raw)["entries"][0]
    assert row["from"] == 0 and row["pctChange"] is None and row["direction"] == "down"


@pytest.mark.parametrize("signals", [None, {}, {"new": [], "escalated": [], "deescalated": []},
    {"new": [], "escalated": {}, "deescalated": [], "unchanged": []}])
def test_incomplete_signal_groups_cannot_report_zero_changes(signals):
    raw = payload()
    raw["delta"]["signals"] = signals
    result = comparison(raw)
    assert result["status"] == "unavailable" and result["changeCount"] is None
    assert result["reportedChangeCount"] is None


@pytest.mark.parametrize("total", [None, 0, 2, True])
def test_unverified_summary_keeps_valid_values_but_not_a_false_source_total(total):
    raw = payload()
    raw["delta"]["summary"]["totalChanges"] = total
    result = comparison(raw)
    assert result["changeCount"] == 1 and result["reportedChangeCount"] is None
    assert result["reportedDirection"] is None
    assert any(gap["key"] == "source-summary" for gap in result["gaps"])


def test_completed_empty_signal_groups_are_not_missing_records():
    raw = payload()
    raw["delta"]["signals"]["escalated"] = []
    raw["delta"]["summary"]["totalChanges"] = 0
    result = comparison(raw)
    assert result["status"] == "current" and result["changeCount"] == 0
    assert result["reportedChangeCount"] == 0


def test_monthly_unemployment_preserves_observation_period_and_adjustment():
    raw = payload()
    raw["bls"] = [{"id": "LNS14000000", "value": 4.4, "date": "2026-10", "frequency": "monthly",
                   "unit": "percent", "seasonalAdjustment": "seasonally-adjusted"}]
    raw["delta"]["signals"]["escalated"] = [{"key": "unemployment", "from": 4, "to": 4.4,
        "change": .4, "pctChange": 10, "fromDate": "2026-09", "toDate": "2026-10",
        "seriesId": "LNS14000000", "unit": "percent", "changeUnit": "percentage-points"}]
    row = comparison(raw)["entries"][0]
    assert row["source"] == "BLS" and row["currentEligible"] is True
    raw["bls"][0]["seasonalAdjustment"] = "not-seasonally-adjusted"
    assert comparison(raw)["entries"] == []


@pytest.mark.parametrize("key,unit", [("wti", "美元/桶"), ("gold", "USD/troy-ounce")])
def test_commodity_comparison_requires_matching_source_and_quote_basis(key, unit):
    raw = payload()
    metal = key == "gold"
    basis = {"id": key, "kind": "futures", "frequency": "quote", "unit": unit,
             "sourceId": "Yahoo Finance", "seriesId": "GC=F" if metal else "CL=F"}
    raw["metals" if metal else "energy"] = {"observations": [{**{k: v for k, v in basis.items() if k not in {"sourceId", "seriesId"}},
        "value": 105, "observedAt": "2026-11-14T10:00:00Z", "source": {"id": basis["sourceId"], "seriesId": basis["seriesId"]}}]}
    entry = {"key": key, "from": 100, "to": 105, "change": 5, "pctChange": 5,
             "fromDate": "2026-11-13T10:00:00Z", "toDate": "2026-11-14T10:00:00Z",
             "unit": unit, "changeUnit": unit, "metalBasis" if metal else "energyBasis": basis}
    raw["delta"]["signals"]["escalated"] = [entry]
    assert comparison(raw)["entries"][0]["currentEligible"] is True
    entry["metalBasis" if metal else "energyBasis"] = {**basis, "seriesId": "other-contract"}
    assert comparison(raw)["entries"] == []
