from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import (
    normalize_health,
    normalize_snapshot,
)


@pytest.mark.parametrize("status,actual,declared", [("ok", 19499, 19499), ("ok", 0, 0), ("partial", 1, 2), ("error", None, None)])
def test_ofac_observation_preserves_date_counts_and_collection_without_screening(status, actual, declared):
    result = normalize_snapshot({"meta": {"timestamp": "2026-11-05T09:00:00Z"}, "ofac": {
        "status": status, "reason": "source receipt", "collectedAt": "2026-11-04T09:00:00Z",
        "sdnList": {"publishDate": "2026-11-04", "entryCount": actual, "recordCount": declared,
                    "countBasis": "sdn-entries", "dataAvailable": status != "error", "complete": status == "ok"},
        "sampleEntries": [{"name": "Not a new designation"}],
    }}, now=datetime(2026, 11, 5, 9, tzinfo=UTC))["global"]["ofac"]
    assert result["status"] == status
    assert result["entryCount"] == actual and result["recordCount"] == declared
    assert result["publishedDate"] == ("2026-11-04" if status != "error" else None)
    assert result["checkedAt"] == "2026-11-04T09:00:00Z"
    assert result["collectedAt"] == ("2026-11-04T09:00:00Z" if status != "error" else None)
    assert result["collectionFreshness"]["status"] == ("stale" if status != "error" else "unknown")
    assert result["complete"] is (status == "ok")
    assert result["countBasis"] == "sdn-entries"
    assert "非合规筛查" in result["note"] and "不是新增" in result["note"]
    assert "sampleEntries" not in result and "publishedAt" not in result


def test_ofac_missing_and_legacy_data_do_not_invent_a_verified_list():
    assert normalize_snapshot({"meta": {}})["global"]["ofac"] is None
    result = normalize_snapshot({"ofac": {"status": "unknown", "sdnList": {
        "entryCount": 1, "dataAvailable": True}}})["global"]["ofac"]
    assert result["status"] == "unknown"
    assert result["entryCount"] is None and result["recordCount"] is None
    assert result["publishedDate"] is None and result["complete"] is False
    assert result["collectedAt"] is None


@pytest.mark.parametrize("source", [{}, {"totalEvents": 0, "totalFatalities": 0}, {"status": "no_credentials"}])
def test_acled_missing_or_legacy_data_is_not_zero_conflict(source):
    result = normalize_snapshot({"acled": source})["global"]["acled"]
    assert result["totalEvents"] is None
    assert result["totalFatalities"] is None
    assert result["deadliestEvents"] == []


def test_acled_preserves_sample_scope_nested_counts_and_zero_coordinates():
    result = normalize_snapshot({"acled": {
        "status": "partial", "basis": "bounded-event-sample", "totalEvents": 2, "totalFatalities": None,
        "period": {"start": "2026-10-21", "end": "2026-10-27"}, "collectedAt": "2026-10-27T09:00:00Z",
        "coverage": {"accepted": 2, "unknownFatalities": 1, "truncated": True},
        "byRegion": {"Example": {"count": 2, "fatalities": None, "unknownFatalities": 1}},
        "deadliestEvents": [{"id": "sample", "date": "2026-10-26", "lat": 0, "lon": 0, "fatalities": 1}],
    }})["global"]["acled"]
    assert result["totalEvents"] == 2 and result["totalFatalities"] is None
    assert result["period"] == {"start": "2026-10-21", "end": "2026-10-27"}
    assert result["coverage"]["truncated"] is True
    assert result["byRegion"]["Example"] == {"count": 2, "fatalities": None, "unknownFatalities": 1}
    assert result["deadliestEvents"][0]["latitude"] == result["deadliestEvents"][0]["longitude"] == 0
    assert result["deadliestEvents"][0]["date"] == "2026-10-26T00:00:00Z"
    zero = normalize_snapshot({"acled": {"status": "ok", "basis": "bounded-event-sample", "totalEvents": 0, "totalFatalities": 0}})["global"]["acled"]
    assert zero["totalEvents"] == zero["totalFatalities"] == 0


def test_bls_month_and_change_basis_survive_adapter_without_invented_daily_timestamp():
    result = normalize_snapshot({"bls": [{
        "id": "LNS14000000", "label": "Unemployment", "value": 4.2, "date": "2026-09",
        "momChange": 0.2, "momChangePct": 5, "momPreviousPeriod": "2026-08",
        "yoyChangePct": 10, "yoyPreviousPeriod": "2025-09", "unit": "percent",
        "changeUnit": "percentage-points", "seasonalAdjustment": "seasonally-adjusted",
    }]}, now=datetime(2026, 10, 27, tzinfo=UTC))["macro"]["bls"][0]
    assert result["date"] == result["period"] == "2026-09"
    assert result["frequency"] == "monthly"
    assert result["momChange"] == 0.2
    assert result["changeUnit"] == "percentage-points"
    assert result["momPreviousPeriod"] == "2026-08"
    assert result["yoyPreviousPeriod"] == "2025-09"
    assert result["seasonalAdjustment"] == "seasonally-adjusted"
    assert result["freshness"]["status"] == "fresh"


@pytest.mark.parametrize("status,count", [("ok", 0), ("partial", 61), ("error", None)])
def test_weather_retains_coverage_and_unlocated_alerts_without_new_sweep_timestamps(status, count):
    result = normalize_snapshot({"meta": {"timestamp": "2026-10-27T09:00:00Z"}, "noaa": {
        "status": status, "totalAlerts": count, "collectedAt": "2026-10-26T01:00:00Z",
        "coverage": {"complete": status == "ok"}, "httpStatus": 400 if status == "error" else None,
        "alerts": [{"id": "alert-1", "event": "Flood Warning", "lat": None, "lon": None,
                    "sent": "2026-10-26T00:00:00Z", "expires": "2026-10-26T12:00:00Z",
                    "url": "https://api.weather.gov/alerts/1", "areas": "Example county"}],
    }}, now=datetime(2026, 10, 27, 9, tzinfo=UTC))["global"]
    assert result["weatherCoverage"]["totalAlerts"] == count
    assert result["weatherCoverage"]["freshness"]["status"] == "stale"
    warning = result["weatherAlerts"][0]
    assert warning["id"] == "alert-1" and warning["latitude"] is None
    assert warning["sent"] == "2026-10-26T00:00:00Z"
    assert warning["expires"] == "2026-10-26T12:00:00Z"


def test_legacy_weather_zero_without_source_status_is_not_certified_empty():
    coverage = normalize_snapshot({"noaa": {"totalAlerts": 0, "alerts": []}})["global"]["weatherCoverage"]
    assert coverage["status"] == "unknown"
    assert coverage["totalAlerts"] is None


def test_treasury_keeps_daily_debt_monthly_cost_basis_and_original_freshness():
    result = normalize_snapshot({"meta": {"timestamp": "2026-10-27T09:00:00Z"}, "treasury": {
        "collectedAt": "2026-10-27T08:00:00Z", "status": "ok",
        "debt": [{"date": "2026-01-02", "totalDebt": "40000000000000.12", "publicDebt": None}],
        "interestRates": [{"date": "2026-09-30", "rate": 3.5, "security": "Treasury Notes", "securityType": "Marketable",
                           "basis": "outstanding-debt-average-interest-rate"}],
    }}, now=datetime(2026, 10, 27, tzinfo=UTC))["macro"]["treasury"]
    assert result["totalDebt"] == "40000000000000.12"
    assert result["freshness"]["status"] == "stale"
    assert result["debt"][0]["publicDebt"] is None
    rate = result["interestRates"][0]
    assert rate["date"] == "2026-09"
    assert rate["rate"] == 3.5 and rate["unit"] == "percent"
    assert rate["freshness"]["status"] == "fresh"
    assert rate["basis"] == "outstanding-debt-average-interest-rate"


def test_treasury_legacy_zero_and_missing_rates_are_unknown_not_market_yields():
    result = normalize_snapshot({"treasury": {"totalDebt": "0", "interestRates": [{"date": "2026-09-30", "rate": None}]}})["macro"]["treasury"]
    assert result["totalDebt"] is None
    assert result["freshness"]["status"] == "unknown"
    assert result["interestRates"][0]["basis"] == "unknown"


@pytest.mark.parametrize("period,value,status", [("2025-09", 100, "stale"), ("2026-09", None, "unknown"), ("2026-13", 100, "unknown")])
def test_bls_old_missing_or_invalid_month_is_not_refreshed_by_sweep(period, value, status):
    result = normalize_snapshot({"meta": {"timestamp": "2026-10-27T00:00:00Z"}, "bls": [{
        "id": "CUUR0000SA0", "date": period, "value": value, "momChangePct": None,
    }]}, now=datetime(2026, 10, 27, tzinfo=UTC))["macro"]["bls"][0]
    assert result["freshness"]["status"] == status
    assert result["momChangePct"] is None
    assert result["seasonalAdjustment"] == "unknown"



@pytest.mark.parametrize("status,count", [("ok", 0), ("partial", 2), ("error", None)])
def test_rss_coverage_preserves_source_outcomes_and_unknown_counts(status, count):
    result = normalize_snapshot({
        "newsMeta": {"coverage": {"requested": 2}, "displayedCount": count,
                     "items": [{"source": "Synthetic", "status": status, "count": count,
                                "reason": "source outcome", "asOf": "2026-10-01T00:00:00Z"}]},
    }, now=datetime(2026, 10, 27, tzinfo=UTC))
    rss = result["newsCoverage"]
    assert rss["items"][0]["count"] == count
    assert rss["coverage"]["unknown"] == 1
    assert rss["coverage"]["requested"] == 2
    assert rss["items"][0]["freshness"]["status"] == "stale"
    assert rss["status"] != "ok"


def test_rss_unscanned_is_not_successful_empty_and_legacy_stays_absent():
    assert normalize_snapshot({"meta": {}})["newsCoverage"] is None
    rss = normalize_snapshot({"newsMeta": {"status": "unknown", "coverage": {"requested": 0}, "items": []}})["newsCoverage"]
    assert rss["status"] == "unknown"
    assert rss["displayedCount"] is None
    assert rss["asOf"] is None

@pytest.mark.parametrize("attempt", ["ok", "error"])
def test_rss_cache_retains_data_clock_and_failure_separately(attempt):
    collected = "2026-10-26T12:00:00Z"
    result = normalize_snapshot({
        "meta": {"timestamp": "2026-10-27T00:00:00Z"},
        "newsMeta": {"mode": "cache", "coverage": {"requested": 1}, "cache": {"status": "ok"},
                     "items": [{"source": "Synthetic", "status": attempt, "count": 1 if attempt == "ok" else None,
                                "asOf": "2026-10-26T23:59:00Z", "cached": True,
                                "dataAsOf": collected, "availableCount": 1}]},
        "newsFeed": [{"headline": "Retained report", "source": "Synthetic", "type": "rss",
                      "timestamp": None, "collectedAt": collected, "cached": True, "sourceStatus": attempt}],
    }, now=datetime(2026, 10, 27, tzinfo=UTC))
    assert result["newsCoverage"]["status"] == "partial"
    assert result["newsCoverage"]["cachedSources"] == 1
    row = result["newsCoverage"]["items"][0]
    assert row["status"] == attempt
    assert row["dataFreshness"]["status"] == "stale"
    assert row["availableCount"] == 1
    news = result["news"][0]
    assert news["publishedAt"] is None
    assert news["collectedAt"] == row["dataAsOf"]
    assert news["collectionFreshness"]["status"] == "stale"
    assert news["sourceStatus"] == attempt


def test_rss_cache_write_failure_does_not_claim_full_success():
    result = normalize_snapshot({"newsMeta": {"coverage": {"requested": 1},
        "cache": {"status": "error", "reason": "cache unavailable"},
        "items": [{"source": "Synthetic", "status": "ok", "count": 0}]} })
    assert result["newsCoverage"]["status"] == "partial"
    assert result["newsCoverage"]["cache"]["status"] == "error"

def test_monitoring_reference_locations_and_unknown_safety_survive_api():
    result = normalize_snapshot({
        "air": [{"key": "b", "region": "second region", "geoBasis": "query-bounds-center",
                 "lat": 0, "lon": 0, "total": 0, "status": "ok", "observedAt": "2026-10-27T00:00:00Z"},
                {"key": "legacy", "region": "legacy", "lat": 20, "lon": 30, "total": None}],
        "nuke": [{"key": "sample", "site": "sample area", "geoBasis": "query-radius-center",
                  "lat": 1, "lon": 2, "cpm": 0, "deviceId": 7, "anom": False, "n": 1,
                  "sampleReadings": 1, "radiusKm": 50, "status": "ok",
                  "measurements": [{"value": 0, "unit": "cpm", "deviceId": 7, "observedAt": "2026-10-27T00:00:00Z"}]},
                 {"key": "bad", "site": "legacy", "lat": 91, "lon": 0, "anom": True, "cpm": 300}],
    }, now=datetime(2026, 10, 27, tzinfo=UTC))["global"]
    air = result["airRegions"]
    assert air[0]["id"] == "b" and air[0]["latitude"] == 0 and air[0]["totalAircraft"] == 0
    assert air[1]["latitude"] is None and air[1]["totalAircraft"] is None
    radiation = result["radiationAreas"]
    assert radiation[0]["assessment"] == "unassessed"
    assert radiation[0]["avgCPM"] == 0
    assert radiation[0]["measurements"][0]["unit"] == "cpm"
    assert radiation[1]["latitude"] is None and radiation[1]["avgCPM"] is None
    assert all(row["assessment"] == "unassessed" for row in radiation)

@pytest.mark.parametrize("count", [None, 0, 3])
def test_news_collection_preserves_missing_zero_and_partial_coverage(count):
    result = normalize_snapshot({
        "health": [{"n": "GDELT", "status": "partial", "reason": "部分查询失败"}],
        "gdelt": {"totalArticles": count, "coverage": {"requested": 2, "succeeded": 1, "failed": 1},
                  "gaps": {"articles": "文章查询失败"} if count is None else {"geo": "地理查询失败"},
                  "geoPoints": [{"lat": 0, "lon": 0, "count": 0}, {"lat": 1, "lon": 2, "count": None}]},
    })
    gdelt = result["global"]["gdelt"]
    assert gdelt["totalArticles"] == count
    assert gdelt["coverage"] == {"requested": 2, "succeeded": 1, "failed": 1}
    assert gdelt["gaps"]
    assert [point["count"] for point in gdelt["geoPoints"]] == [0, None]
    assert result["sourceHealth"]["partial"] == 1


def test_absent_gdelt_is_not_a_successful_zero_article_scan():
    result = normalize_snapshot({"meta": {"sourcesQueried": 0}})
    assert result["global"]["gdelt"]["totalArticles"] is None


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
    assert item["unit"] is None  # Legacy snapshots did not retain source units.


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


def test_economic_history_keeps_real_periods_and_zero_without_manufacturing_dates():
    history = [{"period": "2026-09-09", "value": 71}, {"period": "2026-09-08", "value": 0},
               {"period": "2026-09-08", "value": 99}, {"period": "2026-09-10", "value": 999},
               {"period": "not-a-date", "value": 70}, {"period": "2026-09-07", "value": None}, 72]
    result = normalize_snapshot({
        "energy": {"wtiRecent": [72, 70], "observations": [{"id": "wti", "value": 71,
            "period": "2026-09-09", "frequency": "daily", "history": history}]},
        "gscpi": {"date": "2026-08", "value": 1.2, "history": [
            {"date": "2026-08", "value": 1.2}, {"date": "2026-07", "value": 0},
            {"date": "2026-10", "value": 99}, {"date": "2026-13", "value": 99}]},
    }, now=datetime(2026, 9, 10, tzinfo=UTC))["macro"]
    assert result["energy"]["observations"][0]["history"] == [
        {"period": "2026-09-08", "value": 0}, {"period": "2026-09-09", "value": 71}]
    assert result["gscpi"]["history"] == [{"period": "2026-07", "value": 0}, {"period": "2026-08", "value": 1.2}]
    assert result["energy"]["observations"][1]["history"] == []
