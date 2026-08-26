"""统一 A/H/US 市场扫描接口契约。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app as app_module
import market_terminal


class _Response:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"data": {"diff": self._rows}}


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
