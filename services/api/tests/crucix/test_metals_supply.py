from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import normalize_snapshot


NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def supply(**changes):
    return {"value": 0, "date": "2026-10", "unit": "standard-deviations", "frequency": "monthly",
            "vintage": "46327", "status": "partial", "rejected": 2, "missing": 1,
            "collectedAt": "2026-11-14T10:00:00Z",
            "source": {"id": "GSCPI", "seriesId": "GSCPI", "url": "https://www.newyorkfed.org/research/policy/gscpi"},
            "history": [{"date": "2026-09", "value": 1, "vintage": "46327"},
                        {"date": "2026-10", "value": 0, "vintage": "46327"}], **changes}


def test_supply_preserves_month_vintage_and_receipts_without_inventing_publication():
    row = normalize_snapshot({"gscpi": supply()}, now=NOW)["macro"]["gscpi"]
    assert row["value"] == 0
    assert row["period"] == row["date"] == "2026-10"
    assert row["vintage"] == "46327" and row["vintageBasis"] == "source-column-id"
    assert row["status"] == "partial" and row["rejected"] == 2 and row["missing"] == 1
    assert row["frequency"] == "monthly" and row["unit"] == "standard-deviations"
    assert row["basisVerified"] is True and row["freshness"]["status"] == "fresh"
    assert row["collectedAt"] == "2026-11-14T10:00:00Z"
    assert "publishedAt" not in row
    assert row["history"] == [{"period": "2026-09", "value": 1, "vintage": "46327"},
                              {"period": "2026-10", "value": 0, "vintage": "46327"}]


def test_supply_history_excludes_other_vintages_and_conflicting_months():
    row = normalize_snapshot({"gscpi": supply(history=[
        {"date": "2026-10", "value": 0, "vintage": "46327"},
        {"date": "2026-09", "value": 999, "vintage": "46296"},
        {"date": "2026-08", "value": 1, "vintage": "46327"},
        {"date": "2026-08", "value": 2, "vintage": "46327"},
    ])}, now=NOW)["macro"]["gscpi"]
    assert row["history"] == [{"period": "2026-10", "value": 0, "vintage": "46327"}]


def test_supply_legacy_and_failure_are_not_upgraded_to_verified_current_data():
    legacy = normalize_snapshot({"gscpi": {"value": 0, "date": "2026-10"}}, now=NOW)["macro"]["gscpi"]
    assert legacy["value"] == 0 and legacy["vintage"] is None
    assert legacy["status"] == "unknown" and legacy["basisVerified"] is False
    failed = normalize_snapshot({"gscpi": supply(status="error", value=None)}, now=NOW)["macro"]["gscpi"]
    assert failed["value"] is None and failed["status"] == "error"
    assert failed["freshness"]["status"] == "unknown" and failed["basisVerified"] is False


@pytest.mark.parametrize("observed,unit,expected", [
    ("2026-11-08T20:00:00Z", "USD/troy-ounce", "fresh"),
    ("2026-11-01T20:00:00Z", "USD/troy-ounce", "stale"),
    ("2026-11-15T20:00:00Z", "USD/troy-ounce", "unknown"),
    ("2026-11-13T20:00:00", "USD/troy-ounce", "unknown"),
    ("2026-11-13T20:00:00Z", None, "unknown"),
])
def test_metal_quote_preserves_identity_and_uses_original_seven_day_window(observed, unit, expected):
    result = normalize_snapshot({"metals": {"observations": [{"id": "gold", "value": 0,
        "kind": "futures", "frequency": "quote", "unit": unit, "observedAt": observed,
        "prevClose": 2700, "previousCloseBasis": "daily-bars",
        "source": {"id": "YFinance", "seriesId": "GC=F", "url": "https://finance.yahoo.com/quote/GC%3DF/"}}]}}, now=NOW)
    row, missing = result["macro"]["metals"]["observations"]
    assert row["value"] == 0 and row["kind"] == "futures" and row["source"]["seriesId"] == "GC=F"
    assert row["freshness"]["status"] == expected
    assert row["prevClose"] == 2700 and row["previousCloseBasis"] == "daily-bars"
    assert row["previousCloseDate"] is None and row["history"] == []
    assert missing["value"] is None and missing["freshness"]["status"] == "unknown"


def test_metal_legacy_keeps_value_but_does_not_invent_units_or_source_time():
    row = normalize_snapshot({"metals": {"gold": 2700}}, now=NOW)["macro"]["metals"]["observations"][0]
    assert row["value"] == 2700
    assert row["source"] is None and row["unit"] is None and row["observedAt"] is None
    assert row["kind"] == "unknown" and row["basisVerified"] is False
    assert row["freshness"]["status"] == "unknown"
