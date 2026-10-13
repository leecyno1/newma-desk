from datetime import UTC, datetime, timedelta

import httpx
import pytest

from vibe_visualization_api.global_topics.service import TOPICS, forecast, topic_snapshot
from vibe_visualization_api.global_topics.sources import TopicSources, parse_fred, year_over_year


@pytest.mark.parametrize("topic_id", TOPICS)
def test_missing_sources_never_seed_fake_metrics_or_events(topic_id):
    evidence = {"metrics": [], "events": [], "observations": [], "dataMode": "unavailable", "dataAsOf": None}
    result = topic_snapshot(topic_id, evidence)
    assert result["dataMode"] == "unavailable"
    assert result["dataAsOf"] is None
    assert result["generatedAt"] == result["updatedAt"]
    assert result["observations"] == [] and result["events"] == [] and result["metrics"] == []
    assert all(factor["value"] == 50 for factor in result["factors"])
    assert result["factorSource"] == "user-assumptions"
    assert "不代表真实发生概率" in result["forecast"]["disclaimer"]


def test_forecast_remains_a_parameter_driven_scenario_model():
    low = forecast("fed-rates", {"inflation": 0, "employment": 0, "financialStress": 100})
    high = forecast("fed-rates", {"inflation": 100, "employment": 100, "financialStress": 0})
    assert low["probabilities"] != high["probabilities"]
    assert sum(item["probability"] for item in high["probabilities"]) == 100


CLOCK = datetime(2026, 9, 11, 12, tzinfo=UTC)


def response_for(request):
    if request.url.host == "api.tushare.pro":
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["date", "y2", "y10"], "items": [["20260909", 4.1, 4.5]]}})
    if request.url.host == "www.federalreserve.gov":
        return httpx.Response(200, text='''<rss><channel><item><title>Policy statement</title><link>https://www.federalreserve.gov/newsevents/pressreleases/policy.htm</link><pubDate>Thu, 10 Sep 2026 18:00:00 GMT</pubDate></item><item><title>Future</title><link>https://www.federalreserve.gov/future.htm</link><pubDate>Fri, 09 Oct 2026 18:00:00 GMT</pubDate></item></channel></rss>''')
    if request.url.host == "www.federalregister.gov":
        assert request.url.params["conditions[term]"] == "China"
        return httpx.Response(200, json={"count": 2, "results": [{"document_number": "2026-1", "title": "China export control", "publication_date": "2026-09-09", "html_url": "https://www.federalregister.gov/documents/2026/09/09/2026-1", "type": "Proposed Rule"}, {"document_number": "2026-2", "title": "Russian airline denial order", "publication_date": "2026-09-08", "html_url": "https://www.federalregister.gov/documents/2026/09/08/2026-2", "type": "Notice"}]})
    identifier = request.url.params["id"]
    rows = "2026-09-09,3.5\n2026-09-10,.\n2026-10-01,999"
    if identifier == "CPILFESL":
        rows = "2025-07-01,300\n2026-07-01,309\n2026-08-01,310"
    elif identifier == "T10Y2Y":
        rows = "2026-09-09,0.40"
    return httpx.Response(200, text=f"observation_date,{identifier}\n{rows}\n")


async def crucix():
    return {"asOf": "2026-09-10T08:00:00Z", "freshness": {"status": "fresh"}, "news": [], "macro": {
        "energy": {"observations": [{"id": identifier, "value": value, "kind": "spot", "unit": "美元/桶", "period": "2026-09-09", "source": {"label": "EIA via FRED", "seriesId": identifier, "url": "https://fred.stlouisfed.org/series/" + identifier}} for identifier, value in [("wti", 70), ("brent", 75)]]},
        "gscpi": {"value": 1.06, "period": "2026-08", "freshness": {"status": "fresh"}},
    }}


def test_cpi_uses_same_month_last_year_and_rejects_missing_nonfinite_future_values():
    rows = parse_fred("observation_date,CPI\n2025-07-01,300\n2026-07-01,309\n2026-08-01,310\n2026-09-01,NaN\n2026-10-01,1000", "CPI", CLOCK.date())
    assert year_over_year(rows) == [{"date": "2026-07-01", "value": 3.0}]


@pytest.mark.asyncio
async def test_fed_uses_tushare_and_real_dated_fred_observations():
    async with httpx.AsyncClient(transport=httpx.MockTransport(response_for)) as client:
        service = TopicSources(tushare_token="test-token", crucix_snapshot=crucix, client=client, clock=lambda: CLOCK)
        result = await service.snapshot("fed-rates")
    assert result["dataMode"] == "source-backed"
    assert result["metrics"][0]["label"] == "有效联邦基金利率"
    assert result["metrics"][1]["value"] == "3.00"
    assert result["metrics"][1]["date"] == "2026-07-01"
    assert result["metrics"][2]["value"] == "40.00"
    assert result["metrics"][2]["unit"] == "bp"
    assert result["metrics"][2]["source"] == "Tushare Pro · us_tycr"
    assert len(result["events"]) == 1
    assert result["events"][0]["evidenceType"] == "official-release"
    assert result["events"][0]["publishedAt"] == "2026-09-10T18:00:00+00:00"
    assert result["events"][0]["collectedAt"] == CLOCK.isoformat()
    assert result["eventCoverage"] == {"count": 1, "readySourceCount": 1, "staleSourceCount": 0}
    assert "test-token" not in str(result)


@pytest.mark.asyncio
async def test_tushare_permission_failure_uses_same_unit_fallback_with_reason():
    def handler(request):
        return httpx.Response(200, json={"code": -1}) if request.url.host == "api.tushare.pro" else response_for(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TopicSources(tushare_token="test", crucix_snapshot=crucix, client=client, clock=lambda: CLOCK).snapshot("fed-rates")
    assert result["metrics"][2]["value"] == "40.00"
    assert result["metrics"][2]["source"] == "FRED · T10Y2Y"
    assert "权限不足" in result["metrics"][2]["change"]


@pytest.mark.asyncio
async def test_failed_refresh_keeps_original_observation_and_collection_dates():
    now, failing = CLOCK, False
    def handler(request):
        return httpx.Response(503) if failing else response_for(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TopicSources(tushare_token="test", crucix_snapshot=crucix, client=client, clock=lambda: now)
        first = await service.snapshot("fed-rates")
        now, failing = CLOCK + timedelta(minutes=6), True
        result = await service.snapshot("fed-rates")
    assert result["freshness"] == "stale"
    assert result["metrics"][0]["date"] == first["metrics"][0]["date"]
    assert result["metrics"][0]["collectedAt"] == CLOCK.isoformat()
    assert all(row["status"] == "stale" for row in result["sourceStatus"])


@pytest.mark.asyncio
async def test_hormuz_keeps_prices_but_does_not_invent_route_risk_or_history():
    async with httpx.AsyncClient(transport=httpx.MockTransport(response_for)) as client:
        result = await TopicSources(crucix_snapshot=crucix, client=client, clock=lambda: CLOCK).snapshot("hormuz")
    assert [row["value"] for row in result["metrics"]] == ["70.00", "75.00", "—", "—"]
    assert len(result["observations"]) == 2
    assert result["events"] == []
    assert result["eventCoverage"]["count"] == 0  # Price observations are not event evidence.
    assert result["dataMode"] == "source-backed"
    assert result["metrics"][0]["collectedAt"] == "2026-09-10T08:00:00Z"


@pytest.mark.asyncio
async def test_trade_keeps_official_document_scope_separate_from_global_pressure():
    async with httpx.AsyncClient(transport=httpx.MockTransport(response_for)) as client:
        result = await TopicSources(crucix_snapshot=crucix, client=client, clock=lambda: CLOCK).snapshot("us-china-trade")
    assert result["metrics"][0]["value"] == "2"
    assert result["metrics"][0]["dateBasis"] == "query-time"
    assert result["metrics"][1]["value"] == "1.06"
    assert result["metrics"][1]["unit"] == "标准差"
    assert result["events"][0]["documentType"] == "Proposed Rule"
    assert result["events"][0]["evidenceKey"] == result["events"][0]["sourceUrl"]
    assert result["events"][0]["sourceStatus"] == "ready"
    assert result["events"][0]["date"] == "2026-09-09"
    assert len(result["events"]) == 1
    assert result["metrics"][2]["value"] == "—"


@pytest.mark.asyncio
async def test_first_source_outage_returns_missing_values_not_demo_data():
    async def unavailable():
        raise RuntimeError("offline")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        service = TopicSources(crucix_snapshot=unavailable, client=client, clock=lambda: CLOCK)
        for topic_id in TOPICS:
            result = await service.snapshot(topic_id)
            assert result["dataMode"] == "unavailable"
            assert result["observations"] == [] and result["events"] == []
            assert all(row["value"] == "—" for row in result["metrics"])


def test_topic_route_uses_source_service_and_rejects_unknown_topic(client):
    class Source:
        async def snapshot(self, topic_id):
            return {"dataMode": "unavailable", "metrics": [], "events": [], "observations": [], "series": [], "sourceStatus": []}
    client.app.state.global_topic_sources = Source()
    result = client.get("/api/global-topics/fed-rates")
    assert result.status_code == 200
    assert result.json()["factorSource"] == "user-assumptions"
    assert result.json()["metrics"] == []
    assert client.get("/api/global-topics/not-a-topic").status_code == 404


def navigation_snapshot():
    def warning(identifier, text, **extra):
        return {"id": identifier, "navarea": "P", "broadcast_area": "P", "broadcast_label": "HYDROPAC",
                "issue_date": "2024-05-08T16:53:00Z", "issue_date_raw": "081653Z MAY 2024",
                "status": "active", "text": text, "coordinates": [], **extra}
    return {"collected_at": "2026-09-11T11:50:00Z", "cache_expires_at": "2026-09-11T12:50:00Z", "freshness": "fresh", "warnings": [
        warning("2024-1", "STRAIT OF HORMUZ. NAVIGATION WARNING."),
        warning("2024-2", "SURVEY AREA", coordinates=[{"lat": 20, "lon": 60}, {"lat": 26.5, "lon": 56.3}]),
        warning("2024-3", "QATAR. SURVEY WORKS.", origin_navarea="IX"),
        warning("2024-4", "UNRELATED WARNING"),
        warning("2024-5", "HORMUZ. CANCELLED", status="cancelled"),
    ]}


@pytest.mark.asyncio
async def test_maritime_separates_relevance_publication_and_snapshot_validity():
    async def read():
        return navigation_snapshot()
    service = TopicSources(crucix_snapshot=crucix, maritime_snapshot=read, clock=lambda: CLOCK)
    result = await service.snapshot("hormuz")
    evidence = result["maritime"]
    assert evidence["counts"] == {"hormuz-mentioned": 1, "nearby-coordinate": 1, "regional": 1}
    assert evidence["scannedCount"] == 5 and evidence["matchedCount"] == 3
    assert evidence["warnings"][0]["publishedAt"] == "2024-05-08T16:53:00+00:00"
    assert evidence["collectedAt"] == "2026-09-11T11:50:00Z"
    assert evidence["status"] == "ready"
    assert all(row["currentValidity"] == "unverified" for row in evidence["warnings"])
    assert result["metrics"][2]["value"] == "—"  # Warnings do not prove route closure.


@pytest.mark.asyncio
async def test_maritime_checks_upstream_expiry_even_inside_topic_cache_then_retains_failed_refresh():
    now, fails = CLOCK + timedelta(minutes=49), False
    async def read():
        if fails:
            raise RuntimeError("offline")
        return navigation_snapshot()
    service = TopicSources(crucix_snapshot=crucix, maritime_snapshot=read, clock=lambda: now)
    assert (await service.snapshot("hormuz"))["maritime"]["status"] == "ready"
    now = CLOCK + timedelta(minutes=51)
    expired = (await service.snapshot("hormuz"))["maritime"]
    assert expired["status"] == "stale"
    now, fails = CLOCK + timedelta(minutes=55), True
    result = await service.snapshot("hormuz")
    assert result["freshness"] == "stale"
    assert result["maritime"]["warnings"] == expired["warnings"]
    assert result["maritime"]["collectedAt"] == "2026-09-11T11:50:00Z"
    assert result["sourceStatus"][-1]["status"] == "stale"


@pytest.mark.asyncio
async def test_maritime_empty_success_and_source_failure_are_distinct():
    async def empty():
        return {**navigation_snapshot(), "warnings": []}
    async def unavailable():
        return {"warnings": [], "error": "offline"}
    for reader, count, status in [(empty, 0, "ready"), (unavailable, None, "unavailable")]:
        result = await TopicSources(crucix_snapshot=crucix, maritime_snapshot=reader, clock=lambda: CLOCK).snapshot("hormuz")
        assert result["maritime"]["scannedCount"] == result["maritime"]["matchedCount"] == count
        assert result["maritime"]["status"] == status
        assert result["maritime"]["warnings"] == []
        assert "不代表海峡安全" in result["maritime"]["limitations"]


@pytest.mark.asyncio
async def test_maritime_scan_without_current_metric_or_event_is_not_source_backed():
    async def no_energy():
        return {"asOf": CLOCK.isoformat(), "freshness": {"status": "fresh"},
                "macro": {"energy": {"observations": []}}, "news": []}

    async def read():
        return navigation_snapshot()

    result = await TopicSources(crucix_snapshot=no_energy, maritime_snapshot=read, clock=lambda: CLOCK).snapshot("hormuz")
    assert result["maritime"]["scannedCount"] == 5
    assert result["dataMode"] == "unavailable"
    assert result["eventCoverage"]["count"] == 0
