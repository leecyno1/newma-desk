from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import (
    normalize_health,
    normalize_snapshot,
)


def test_snapshot_keeps_titled_evidence_and_strips_external_markup() -> None:
    payload = {
        "meta": {
            "timestamp": "2026-08-24T00:00:00Z",
            "sourcesQueried": 3,
            "sourcesOk": 2,
            "sourcesFailed": 1,
        },
        "health": [
            {"n": "GDELT", "err": False, "stale": False},
            {"n": "GSCPI", "err": False, "stale": True},
            {"n": "Telegram", "err": True, "stale": False},
        ],
        "newsFeed": [
            {
                "headline": "<b>Shipping risk rises</b>",
                "source": "GDELT",
                "type": "gdelt",
                "timestamp": "2026-08-24T00:10:00Z",
                "region": "Global",
                "url": "https://example.com/story",
            },
            {"headline": "", "source": "Category only"},
            {
                "headline": "Unsafe link",
                "source": "Telegram",
                "url": "javascript:alert(1)",
            },
        ],
        "fred": [
            {
                "id": "CPIAUCSL",
                "label": "US CPI",
                "value": 315.2,
                "date": "2026-07-01",
                "momChangePct": 0.2,
            }
        ],
        "gscpi": {
            "value": 1.25,
            "date": "2026-08-01",
            "interpretation": "Above normal pressure",
        },
        "defense": [
            {
                "recipient": "Example Corp",
                "amount": 1200000,
                "desc": "<i>Radar systems</i>",
            }
        ],
    }

    result = normalize_snapshot(
        payload,
        now=datetime(2026, 8, 24, 0, 30, tzinfo=UTC),
    )

    assert result["contract"] == "newma-desk.crucix-intelligence.v1"
    assert result["freshness"]["status"] == "fresh"
    assert result["sourceHealth"] == {
        "queried": 3,
        "ok": 1,
        "failed": 1,
        "partial": 0, "stale": 1, "unknown": 0,
        "items": [
            {"source": "GDELT", "status": "ok"},
            {"source": "GSCPI", "status": "stale"},
            {"source": "Telegram", "status": "error"},
        ],
    }
    assert [item["title"] for item in result["news"]] == [
        "Shipping risk rises",
        "Unsafe link",
    ]
    assert result["news"][0]["url"] == "https://example.com/story"
    assert "url" not in result["news"][1]
    assert result["macro"]["gscpi"]["value"] == 1.25
    assert result["global"]["defenseContracts"][0]["description"] == "Radar systems"
    assert "ideas" not in result


def test_gdelt_indexing_and_legacy_sweep_dates_are_not_publication_dates() -> None:
    result = normalize_snapshot({"newsFeed": [
        {"headline": "Indexed article", "source": "GDELT", "type": "gdelt", "timestamp": "2026-09-10T08:00:00Z", "timestampBasis": "indexed"},
        {"headline": "Legacy article", "source": "GDELT", "type": "gdelt", "timestamp": "2026-09-10T09:00:00Z"},
        {"headline": "RSS article", "source": "RSS", "type": "rss", "timestamp": "2026-09-10T07:00:00Z"},
    ]})
    indexed, legacy, rss = result["news"]
    assert indexed["publishedAt"] is None
    assert indexed["indexedAt"] == "2026-09-10T08:00:00Z"
    assert legacy["publishedAt"] is None
    assert "indexedAt" not in legacy
    assert rss["publishedAt"] == "2026-09-10T07:00:00Z"


@pytest.mark.parametrize("offset", ["00:30:00.001", "01:30:00"])
def test_future_sweep_is_unknown_not_fresh(offset) -> None:
    timestamp = f"2026-08-24T{offset}Z"
    now = datetime(2026, 8, 24, 0, 30, tzinfo=UTC)
    snapshot = normalize_snapshot({"meta": {"timestamp": timestamp}}, now=now)
    health = normalize_health({"status": "ok", "lastSweep": timestamp, "sourcesOk": 1}, now=now)
    assert snapshot["freshness"]["status"] == "unknown"
    assert snapshot["freshness"]["ageSeconds"] is None
    assert health["freshness"]["status"] == "unknown"
    assert health["status"] == "degraded"


def test_health_marks_old_or_partial_sweep_as_degraded() -> None:
    result = normalize_health(
        {
            "status": "ok",
            "lastSweep": "2026-08-23T20:00:00Z",
            "nextSweep": "2026-08-23T21:00:00Z",
            "sourcesOk": 28,
            "sourcesFailed": 1,
            "refreshIntervalMinutes": 60,
            "sweepInProgress": False,
        },
        now=datetime(2026, 8, 24, 0, 30, tzinfo=UTC),
    )

    assert result["status"] == "degraded"
    assert result["freshness"]["status"] == "stale"
    assert result["sourceHealth"] == {"queried": 29, "ok": 28, "failed": 1, "partial": 0, "stale": 0, "unknown": 0}


def test_source_counts_follow_complete_detail_not_inflated_legacy_totals():
    result = normalize_snapshot({
        "meta": {"sourcesQueried": 4, "sourcesOk": 4, "sourcesFailed": 0},
        "health": [{"n": "EIA", "status": "partial", "err": True, "reason": "部分观测缺失"},
                   {"n": "YFinance", "status": "error", "err": True},
                   {"n": "FRED", "err": True}],
    })
    health = result["sourceHealth"]
    assert {key: health[key] for key in ("queried", "ok", "failed", "partial", "stale", "unknown")} == {
        "queried": 4, "ok": 0, "failed": 2, "partial": 1, "stale": 0, "unknown": 1,
    }
    assert health["items"][0] == {"source": "EIA", "status": "partial", "reason": "部分观测缺失"}


def test_partial_collection_keeps_valid_energy_observation_fresh():
    result = normalize_snapshot({
        "health": [{"n": "EIA", "status": "partial", "err": True}],
        "energy": {"observations": [{"id": "wti", "value": 70, "period": "2026-09-08", "frequency": "daily",
                                      "source": {"id": "EIA"}}]},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    assert result["macro"]["energy"]["observations"][0]["freshness"]["status"] == "fresh"


def test_partial_only_health_does_not_report_ok_when_nothing_failed():
    result = normalize_health({
        "status": "ok", "lastSweep": "2026-09-10T00:00:00Z", "sourcesQueried": 2,
        "sourcesOk": 1, "sourcesFailed": 0, "sourcesPartial": 1,
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    assert result["status"] == "degraded"
    assert result["sourceHealth"]["partial"] == 1


@pytest.mark.parametrize(("period", "expected"), [("2026-08", "fresh"), ("2025-08", "stale"), ("2026-13", "unknown"), ("2026-10", "unknown")])
def test_supply_chain_preserves_month_and_ages_data_separately_from_collection(period, expected):
    result = normalize_snapshot({
        "meta": {"timestamp": "2026-09-10T00:00:00Z"},
        "gscpi": {"date": period, "value": 1.06},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    item = result["macro"]["gscpi"]
    assert result["freshness"]["status"] == "fresh"
    assert item["freshness"]["status"] == expected
    assert item["period"] == (None if period == "2026-13" else period)
    assert item["date"] == item["period"]
    assert item["dateBasis"] == "period"
    assert item["unit"] == "标准差"


def test_energy_preserves_source_units_and_stale_observation_despite_new_sweep():
    result = normalize_snapshot({
        "meta": {"timestamp": "2026-09-10T00:00:00Z"},
        "energy": {"observations": [{
            "id": "wti", "label": "WTI期货", "value": 72, "kind": "futures", "frequency": "quote",
            "observedAt": "2026-08-01T18:00:00Z", "unit": "美元/桶",
            "source": {"id": "YFinance", "label": "Yahoo Finance", "seriesId": "CL=F", "url": "https://finance.yahoo.com/quote/CL%3DF/"},
        }, {
            "id": "crudeStocks", "label": "美国商业原油库存", "value": 420000, "kind": "inventory", "frequency": "weekly",
            "period": "2026-09-04", "unit": "千桶", "source": {"id": "EIA", "seriesId": "WCESTUS1"},
        }]},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    quote, _, _, stocks = result["macro"]["energy"]["observations"]
    assert quote["source"]["seriesId"] == "CL=F"
    assert quote["kind"] == "futures"
    assert quote["freshness"]["status"] == "stale"
    assert quote["period"] is None
    assert stocks["unit"] == "千桶"
    assert stocks["period"] == "2026-09-04"
    assert stocks["freshness"]["status"] == "fresh"


def test_legacy_energy_does_not_invent_eia_provenance_or_observation_date():
    result = normalize_snapshot({"meta": {"timestamp": "2026-09-10T00:00:00Z"}, "energy": {"wti": 72}},
                                now=datetime(2026, 9, 10, tzinfo=UTC))
    quote = result["macro"]["energy"]["observations"][0]
    assert quote["value"] == 72
    assert quote["kind"] == "unknown"
    assert quote["unit"] is None and quote["source"] is None
    assert quote["period"] is None and quote["observedAt"] is None
    assert quote["freshness"]["status"] == "unknown"


@pytest.mark.parametrize(("period", "collector_failed", "freshness"), [
    ("2026-09-01", False, "stale"), ("2026-09-08", False, "fresh"), ("2026-09-08", True, "stale"),
])
def test_public_energy_preserves_source_chain_and_uses_its_own_collector_health(period, collector_failed, freshness):
    source = {"id": "FRED-public", "label": "FRED · EIA", "seriesId": "DCOILWTICO",
              "url": "https://fred.stlouisfed.org/series/DCOILWTICO", "collectorId": "EIA",
              "originalSource": "美国能源信息署 EIA", "originalSeriesId": "RWTC",
              "originalUrl": "https://www.eia.gov/", "fallbackReason": "EIA API 不可用，改用公开数据。"}
    result = normalize_snapshot({
        "meta": {"timestamp": "2026-09-10T00:00:00Z"},
        "health": [{"n": "FRED", "err": True}, {"n": "EIA", "err": collector_failed}],
        "energy": {"observations": [{"id": "wti", "value": 91.48, "kind": "spot", "frequency": "daily",
                                      "period": period, "unit": "美元/桶", "source": source}]},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    item = result["macro"]["energy"]["observations"][0]
    assert item["source"] == source
    assert item["value"] == 91.48
    assert item["freshness"]["status"] == freshness
    assert item["observedAt"] is None


def test_source_failure_marks_retained_monthly_value_stale():
    result = normalize_snapshot({
        "meta": {"timestamp": "2026-09-10T00:00:00Z"},
        "health": [{"n": "GSCPI", "err": True}], "gscpi": {"value": 1.06, "date": "2026-08"},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))
    assert result["macro"]["gscpi"]["freshness"]["status"] == "stale"
