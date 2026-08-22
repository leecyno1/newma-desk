import httpx
import pytest

from vibe_visualization_api.capital_flow.service import CapitalFlowService


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
