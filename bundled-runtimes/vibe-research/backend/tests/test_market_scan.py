"""统一 A/H/US 市场扫描接口契约。"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
import requests

import app as app_module
import market_terminal


class _Response:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"rc": 0, "data": {"total": len(self._rows), "diff": self._rows}}

    def raise_for_status(self):
        pass


def test_scan_market_quotes_normalizes_identity_and_metrics(monkeypatch):
    market_terminal._SCAN_CACHE.clear()
    captured = {}

    def fake_get(url, *, params, headers, timeout):
        captured.update({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return _Response({
            "0": {
                "f2": 231.4,
                "f3": 4.25,
                "f4": 9.45,
                "f5": 123_000,
                "f6": 28_400_000,
                "f8": 1.8,
                "f9": 31.2,
                "f10": 1.6,
                "f12": "AAPL",
                "f13": 105,
                "f14": "苹果",
                "f15": 234.0,
                "f16": 226.1,
                "f17": 228.0,
                "f18": 221.95,
                "f20": 3_420_000_000_000,
                "f21": 3_390_000_000_000,
                "f23": 45.1,
                "f100": "消费电子",
            }
        })

    monkeypatch.setattr(market_terminal.astock, "em_get", fake_get)

    result = market_terminal.scan_market_quotes(
        "us", sort="marketCap", order="asc", limit=40
    )

    assert captured["params"]["fid"] == "f20"
    assert captured["params"]["po"] == 0
    assert captured["params"]["pz"] == 40
    assert captured["params"]["fs"] == "m:105,m:106,m:107"
    assert result["coverage"] == {"requested": 40, "returned": 1}
    assert result["source"] == "eastmoney-delay"
    assert result["items"][0] == {
        "symbol": "AAPL",
        "name": "苹果",
        "market": "US",
        "exchange": "NASDAQ",
        "currency": "USD",
        "timezone": "America/New_York",
        "price": 231.4,
        "change": 9.45,
        "changePct": 4.25,
        "prevClose": 221.95,
        "open": 228.0,
        "high": 234.0,
        "low": 226.1,
        "volume": 123_000.0,
        "amount": 28_400_000.0,
        "turnoverPct": 1.8,
        "marketCap": 3_420_000_000_000.0,
        "floatMarketCap": 3_390_000_000_000.0,
        "pe": 31.2,
        "pb": 45.1,
        "volumeRatio": 1.6,
        "industry": "消费电子",
        "source": "eastmoney-delay",
        "sources": ["eastmoney-delay"],
        "asOf": result["items"][0]["asOf"],
    }


def test_scan_route_forwards_sorting_contract(monkeypatch):
    captured = {}

    def fake_scan(market, *, sort, order, limit):
        captured.update({"market": market, "sort": sort, "order": order, "limit": limit})
        return {"items": [], "coverage": {"requested": limit, "returned": 0}}

    monkeypatch.setattr(market_terminal, "scan_market_quotes", fake_scan)
    response = TestClient(app_module.app).get(
        "/api/market-terminal/scan",
        params={"market": "HK", "sort": "turnoverPct", "order": "desc", "limit": 80},
    )

    assert response.status_code == 200
    assert captured == {
        "market": "HK",
        "sort": "turnoverPct",
        "order": "desc",
        "limit": 80,
    }
    assert response.json()["data"]["coverage"]["requested"] == 80


def test_scan_route_rejects_invalid_market():
    response = TestClient(app_module.app).get(
        "/api/market-terminal/scan",
        params={"market": "ALL"},
    )

    assert response.status_code == 422


def test_scan_unavailable_is_not_cached_as_an_empty_success(monkeypatch):
    market_terminal._SCAN_CACHE.clear()
    calls = []

    def unavailable(url, **kwargs):
        calls.append(url)
        raise requests.ConnectionError("private transport detail")

    monkeypatch.setattr(market_terminal.astock, "em_get", unavailable)
    response = TestClient(app_module.app).get("/api/market-terminal/scan")
    assert response.status_code == 502
    assert "行情扫描源暂不可用" in response.json()["detail"]
    assert "private transport detail" not in response.text
    assert len(calls) == 2
    assert not market_terminal._SCAN_CACHE

    monkeypatch.setattr(market_terminal.astock, "em_get", lambda *a, **k: _Response([
        {"f12": "600519", "f14": "贵州茅台", "f2": 1400},
    ]))
    recovered = market_terminal.scan_market_quotes("CN")
    assert recovered["items"][0]["symbol"] == "600519"


@pytest.mark.parametrize("payload", [
    {"rc": 1, "data": {"diff": []}},
    {"rc": 0, "data": None},
    {"rc": 0, "data": {"total": 10, "diff": []}},
    {"rc": 0, "data": {"diff": "invalid"}},
    {"rc": 0, "data": {"diff": [{"f14": "missing identity"}]}},
])
def test_scan_invalid_payload_falls_back_to_next_host(monkeypatch, payload):
    market_terminal._SCAN_CACHE.clear()
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        response = _Response([{"f12": "00700", "f14": "腾讯控股"}])
        if len(calls) == 1:
            response.json = lambda: payload
        return response

    monkeypatch.setattr(market_terminal.astock, "em_get", fetch)
    result = market_terminal.scan_market_quotes("HK")
    assert len(calls) == 2
    assert result["source"] == "eastmoney"
    assert result["items"][0]["symbol"] == "00700"


def test_scan_http_failure_is_not_parsed_as_success(monkeypatch):
    market_terminal._SCAN_CACHE.clear()
    response = _Response([{"f12": "600519"}])

    def fail():
        raise requests.HTTPError("upstream 503")

    response.raise_for_status = fail
    monkeypatch.setattr(market_terminal.astock, "em_get", lambda *a, **k: response)
    result = TestClient(app_module.app).get("/api/market-terminal/scan")
    assert result.status_code == 502
    assert not market_terminal._SCAN_CACHE


def test_scan_explicit_empty_result_stays_distinct_from_failure(monkeypatch):
    market_terminal._SCAN_CACHE.clear()
    monkeypatch.setattr(market_terminal.astock, "em_get", lambda *a, **k: _Response([]))
    response = TestClient(app_module.app).get("/api/market-terminal/scan")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
