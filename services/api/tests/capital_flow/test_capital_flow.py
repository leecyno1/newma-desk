import httpx
import pytest

from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.capital_flow.turnover import TurnoverResearchService
from vibe_visualization_api.capital_flow.routes import get_capital_flow, search_capital_flow_security
from vibe_visualization_api.config import Settings


@pytest.mark.asyncio
async def test_capital_flow_routes_use_resolved_server_token(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "old-test-token")
    tokens = []

    async def dashboard(service, code, *, include_legacy_turnover):
        assert include_legacy_turnover is False
        tokens.append(service._tushare_token)
        return {"code": code, "summary": {}, "dimensions": [{"id": "market"}], "riskAppetite": {"drivers": []}, "upstream": {}}

    async def turnover(service, *, refresh):
        tokens.append(service.token)
        assert refresh is False
        return {"leaders": [], "summary": {"top20TurnoverYi": None}, "current": False, "asOf": None, "reason": "未取得"}

    async def search(service, query, limit):
        tokens.append(service._tushare_token)
        return {"items": []}

    monkeypatch.setattr(CapitalFlowService, "dashboard", dashboard)
    monkeypatch.setattr(CapitalFlowService, "search_securities", search)
    monkeypatch.setattr(TurnoverResearchService, "research", turnover)
    settings = Settings(tushare_token="configured-test-token", _env_file=None)

    assert (await get_capital_flow("300308", settings))["code"] == "300308"
    assert await search_capital_flow_security("中际旭创", 8, settings) == {"items": []}
    assert tokens == ["configured-test-token"] * 3


@pytest.mark.asyncio
async def test_capital_flow_aggregates_market_and_security_data(monkeypatch):
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requested_paths.append(path)
        if path.endswith("/api/market/overview"):
            return httpx.Response(200, json={"data": {"sentiment": {"active": "45%", "date": "2026-08-14"}, "sectors": [{"name": "通信", "net": 10, "inflow": 30, "outflow": 20}, {"name": "医药", "net": -3, "inflow": 7, "outflow": 10}]}})
        if path.endswith("/api/market/turnover-top"):
            return httpx.Response(200, json={"data": {"stocks": [{"code": "300308", "amount": 2_000_000_000}]}})
        if path.endswith("/api/macro-monitor"):
            return httpx.Response(200, json={"data": {"indicators": [{"id": "m2"}], "regime": {"liquidity": {"signal": "positive", "summary": "偏宽松"}}}})
        if path.endswith("/api/fund-flow"):
            return httpx.Response(200, json={"data": [
                {"date": "2026-08-14", "main_net": 10},
                {"date": "2026-08-13", "close": 0, "main_net": 0, "net_amount": 0},
            ]})
        return httpx.Response(200, json={"data": [{"date": "2026-08-14", "rzye": 20}]})

    async def fake_hkex(*_args):
        return {
            "date": "2026-08-14",
            "source": "HKEX 官方每日统计",
            "sse-northbound": {"summary": {"Total Turnover": "2200", "Buy Turnover": "1200", "Sell Turnover": "1000"}},
            "szse-northbound": {"summary": {"Total Turnover": "1900", "Buy Turnover": "900", "Sell Turnover": "1000"}},
            "sse-southbound": {"summary": {"Buy Turnover": "500", "Sell Turnover": "800"}},
            "szse-southbound": {"summary": {"Buy Turnover": "400", "Sell Turnover": "300"}},
        }

    async def fake_north_history(*_args):
        return {
            "points": [{
                "date": "2026-08-14",
                "sseTurnoverYi": 22.0,
                "szseTurnoverYi": 19.0,
                "northTurnoverYi": 41.0,
            }],
            "metric": "turnover",
        }

    monkeypatch.setattr(CapitalFlowService, "_fetch_hkex_connect", fake_hkex)
    monkeypatch.setattr(CapitalFlowService, "_fetch_northbound_history", fake_north_history)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://research") as client:
        payload = await CapitalFlowService("http://research", client=client).dashboard("300308")
    assert payload["summary"]["sectorNetYi"] == 7
    assert payload["summary"]["top20TurnoverYi"] == 20
    assert payload["sectors"][0]["name"] == "通信"
    assert payload["security"]["fundFlow"] == [{"date": "2026-08-14", "main_net": 10}]
    assert "/api/market/emotion" not in requested_paths
    drivers = {item["id"]: item for item in payload["riskAppetite"]["drivers"]}
    assert drivers["sector-flow"]["signal"] == "supportive"
    assert drivers["northbound-turnover"]["value"] == "41.00 人民币亿元"
    assert drivers["southbound-flow"]["value"] == "-2.00 港元亿元"
    assert payload["crossBorder"]["northbound"]["sse"]["currency"] == "CNY"
    assert payload["crossBorder"]["northbound"]["sse"]["unit"] == "人民币亿元"
    assert payload["crossBorder"]["southbound"]["sse"]["currency"] == "HKD"
    assert payload["crossBorder"]["southbound"]["sse"]["unit"] == "港元亿元"
    assert payload["crossBorder"]["northbound"]["history"]["status"] == "ready"
    assert payload["crossBorder"]["northbound"]["history"]["validation"]["status"] == "verified"
    assert drivers["macro-liquidity"]["value"] == "偏宽松"
    assert drivers["etf-flow"]["signal"] == "unavailable"
    assert payload["riskAppetite"]["available"] == 5


@pytest.mark.asyncio
async def test_capital_flow_security_search_proxies_cn_master():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/market-terminal/search")
        assert request.url.params["query"] == "中际旭创"
        assert request.url.params["market"] == "CN"
        return httpx.Response(200, json={"data": {"items": [
            {"symbol": "920093", "name": "N信胜", "market": "CN", "exchange": "BJ", "assetType": "stock"},
            {"symbol": "003562", "name": "南方君信混合", "market": "CN", "exchange": "OTC", "assetType": "fund"},
            {"symbol": "03308", "name": "中际旭创", "market": "HK", "exchange": "HKEX", "assetType": "stock"},
            {"symbol": "300308", "name": "中际旭创", "market": "CN", "exchange": "SZ", "assetType": "stock"},
        ]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://research") as client:
        payload = await CapitalFlowService("http://research", client=client).search_securities("中际旭创")
    assert [item["symbol"] for item in payload["items"]] == ["920093", "300308"]


def test_northbound_history_is_hidden_when_hkex_metric_does_not_match():
    history = {
        "points": [{"date": "2026-08-14", "northTurnoverYi": 5.0}],
        "metric": "turnover",
    }
    snapshot = {
        "date": "2026-08-14",
        "sse-northbound": {"summary": {"Total Turnover": "2200"}},
        "szse-northbound": {"summary": {"Total Turnover": "1900"}},
    }

    validated = CapitalFlowService._validate_northbound_history(history, snapshot)

    assert validated["points"] == []
    assert validated["status"] == "metric-mismatch"
    assert validated["reason"] == "字段口径不一致"


@pytest.mark.asyncio
async def test_missing_sources_stay_null_and_security_failure_is_not_no_listing(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/api/market/turnover-top"):
            return httpx.Response(200, json={"data": {"stocks": []}})
        return httpx.Response(503)

    async def unavailable(*_args):
        return {}

    monkeypatch.setattr(CapitalFlowService, "_fetch_hkex_connect", unavailable)
    monkeypatch.setattr(CapitalFlowService, "_fetch_northbound_history", unavailable)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await CapitalFlowService("http://research", client=client).dashboard("300308")
    assert data["summary"]["sectorNetYi"] is None
    assert data["summary"]["top20TurnoverYi"] is None
    assert data["crossBorder"]["northbound"]["date"] is None
    assert data["security"]["coverage"]["dragonTiger"]["status"] == "unavailable"
    assert data["upstream"]["status"] == "degraded"
    assert data["riskAppetite"]["available"] == 0


@pytest.mark.asyncio
async def test_partial_sector_coverage_and_turnover_top20(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/api/market/overview"):
            return httpx.Response(200, json={"data": {"sectors": [{"net": 10}, {"net": None}]}})
        if request.url.path.endswith("/api/market/turnover-top"):
            return httpx.Response(200, json={"data": {"stocks": [{"amount": 100_000_000}] * 25}})
        return httpx.Response(200, json={"data": {}})

    async def unavailable(*_args):
        return {}

    monkeypatch.setattr(CapitalFlowService, "_fetch_hkex_connect", unavailable)
    monkeypatch.setattr(CapitalFlowService, "_fetch_northbound_history", unavailable)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await CapitalFlowService("http://research", client=client).dashboard()
    assert data["summary"]["sectorNetYi"] is None
    assert data["summary"]["sectorInflowYi"] is None
    assert data["summary"]["top20TurnoverYi"] == 20
    assert len(data["turnoverLeaders"]) == 20
    assert data["riskAppetite"]["drivers"][0]["signal"] == "unavailable"


def test_cross_border_partial_channels_are_not_presented_as_total_flow():
    data = CapitalFlowService._risk_appetite([], sector_net=None, north={"sse": {"turnoverYi": 10}}, south={"sse": {"netBuyYi": 3}}, liquidity_regime=None, top_turnover_yi=None, active=None)
    assert data["available"] == 0


def test_overlapping_sector_domains_are_not_a_market_flow_total():
    rows = [{"net": 10, "aggregateSafe": False}, {"net": 8, "aggregateSafe": False}]
    data = CapitalFlowService._risk_appetite(rows, sector_net=None, north={}, south={}, liquidity_regime=None, top_turnover_yi=None, active=None)
    assert data["drivers"][0]["signal"] == "observed"
    assert "重叠" in data["drivers"][0]["detail"]


def test_cross_border_history_checks_components_not_only_total():
    snapshot = {"date": "2026-10-13", "sse-northbound": {"summary": {"Total Turnover": "2200"}}, "szse-northbound": {"summary": {"Total Turnover": "1900"}}}
    history = {"points": [{"date": "2026-10-13", "northTurnoverYi": 41, "sseTurnoverYi": 19, "szseTurnoverYi": 22}]}
    data = CapitalFlowService._validate_northbound_history(history, snapshot)
    assert data["status"] == "metric-mismatch"
    assert data["points"] == []


@pytest.mark.asyncio
async def test_north_history_does_not_continue_old_net_flow_regime():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["trade_date", "hgt", "sgt", "north_money"], "items": [["20240816", 100, 200, 300], ["20261013", None, 200, None]]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        history = await CapitalFlowService("http://research", client=client, tushare_token="test")._fetch_northbound_history(client, "2026-10-13")
    assert len(history["points"]) == 1
    assert history["points"][0]["northTurnoverYi"] is None
    assert history["points"][0]["sseTurnoverYi"] is None
