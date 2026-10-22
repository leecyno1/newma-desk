from datetime import datetime, timedelta

import requests

from instock.core.market_data_provider import (
    HistoricalWindowUnavailable,
    MarketDataError,
    MarketScanUnavailable,
    NewmaDeskMarketDataProvider,
    VibeDeskMarketDataProvider,
    _normalize_kline,
    get_market_data_provider,
)
import pytest


@pytest.mark.parametrize("method", ["get_security_announcements", "get_security_reports", "get_security_news"])
@pytest.mark.parametrize("rows", [[None], [{"title": "valid record"}, "invalid record"]])
def test_event_list_rejects_malformed_rows_instead_of_silently_dropping_them(monkeypatch, method, rows):
    from types import SimpleNamespace
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k:
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": rows}))
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8991/api")
    with pytest.raises(MarketDataError, match="格式无效"):
        getattr(provider, method)("300502")


@pytest.mark.parametrize("method", ["get_security_announcements", "get_security_reports", "get_security_news"])
def test_event_list_preserves_explicit_empty_response(monkeypatch, method):
    from types import SimpleNamespace
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k:
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": []}))
    assert getattr(NewmaDeskMarketDataProvider("http://127.0.0.1:8991/api"), method)("300502") == []


@pytest.mark.parametrize("base", ["http://127.0.0.1:8991", "http://127.0.0.1:8991/api", "http://127.0.0.1:8991/api/"])
def test_standalone_research_root_and_api_prefix_use_one_api_segment(monkeypatch, base):
    from types import SimpleNamespace
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if url.endswith('/health'):
            payload = {'ok': True, 'service': 'vibe-research-api'}
        elif url.endswith('/statement-announcements'):
            payload = {'data': {'symbol': '300502', 'source': 'cninfo', 'items': []}}
        else:
            payload = {'data': {'items': [{'date': '2026-10-19', 'open': 10, 'high': 12, 'low': 9, 'close': 11, 'volume': 100}]}}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr('instock.core.market_data_provider.requests.get', get)
    provider = NewmaDeskMarketDataProvider(base)
    assert provider.health()['status'] == 'ready'
    assert len(provider.get_kline('300502', limit=1)) == 1
    assert provider.get_statement_announcements('300502')['source'] == 'cninfo'
    assert calls == [
        'http://127.0.0.1:8991/api/health',
        'http://127.0.0.1:8991/api/market-terminal/ohlcv',
        'http://127.0.0.1:8991/api/equity-research/statement-announcements',
    ]


def test_native_calendar_uses_source_boundaries_not_observed_quotes(monkeypatch):
    import sys
    from types import SimpleNamespace
    import pandas as pd
    from instock.core.market_data_provider import InStockMarketDataProvider
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    monkeypatch.setitem(sys.modules, "instock.core.crawling.trade_date_hist", SimpleNamespace(
        tool_trade_date_hist_sina=lambda: pd.DataFrame({"trade_date": dates})))
    provider = InStockMarketDataProvider()
    assert provider.get_trading_calendar("2026-01-03", "2026-01-05")["sessions"] == ["2026-01-05"]
    with pytest.raises(MarketDataError, match="未覆盖"):
        provider.get_trading_calendar("2026-01-03", "2026-01-07")
    monkeypatch.setitem(sys.modules, "instock.core.crawling.trade_date_hist", None)
    with pytest.raises(MarketDataError, match="解码依赖未安装"):
        provider.get_trading_calendar("2026-01-03", "2026-01-05")


def test_independent_calendar_uses_desk_and_preserves_exact_range(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"schemaVersion": "newma-desk.trading-calendar.v1", "status": "ready", "sessions": []}
    def fake_get(url, **kwargs):
        calls.append((url, kwargs)); return Response()
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    assert provider.get_trading_calendar("2025-01-01", "2026-10-19")["sessions"] == []
    assert calls[0][0] == "http://127.0.0.1:8911/api/capital-flow/trading-calendar"
    assert calls[0][1]["params"] == {"start": "2025-01-01", "end": "2026-10-19"}


def test_separate_market_services_do_not_reuse_research_origin_or_credentials(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"schemaVersion": "newma-desk.trading-calendar.v1", "status": "ready", "sessions": []}
    monkeypatch.setattr("instock.core.market_data_provider.requests.get",
                        lambda url, **kwargs: calls.append((url, kwargs)) or Response())
    provider = NewmaDeskMarketDataProvider("https://research.example/api", token="research-test",
        market_services_url="http://127.0.0.1:8994", market_services_token="calendar-test")
    provider.get_trading_calendar("2026-01-01", "2026-01-05")
    url, options = calls[0]
    assert url == "http://127.0.0.1:8994/api/capital-flow/trading-calendar"
    assert options["headers"]["Authorization"] == "Bearer calendar-test"
    assert options["proxies"] == {"http": None, "https": None}
    provider = NewmaDeskMarketDataProvider("https://research.example/api", token="research-test",
        market_services_url="https://calendar.example")
    provider.get_trading_calendar("2026-01-01", "2026-01-05")
    assert "Authorization" not in calls[-1][1]["headers"]


def test_direct_research_without_calendar_configuration_fails_before_network(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("未配置基础服务时不应猜测 Research 上的交易日历路由")
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", unexpected)
    provider = NewmaDeskMarketDataProvider("https://research.example/api")
    with pytest.raises(MarketDataError, match="INSTOCK_MARKET_SERVICES_URL"):
        provider.get_trading_calendar("2026-01-01", "2026-01-05")


def test_factory_reads_separate_market_service_configuration(monkeypatch):
    monkeypatch.setenv("INSTOCK_MARKET_DATA_PROVIDER", "http")
    monkeypatch.setenv("INSTOCK_DATA_URL", "https://research.example/api")
    monkeypatch.setenv("INSTOCK_DATA_TOKEN", "research-test")
    monkeypatch.setenv("INSTOCK_MARKET_SERVICES_URL", "https://market.example/")
    monkeypatch.setenv("INSTOCK_MARKET_SERVICES_TOKEN", "market-test")
    get_market_data_provider.cache_clear()
    try:
        provider = get_market_data_provider()
        assert provider.market_services_url == "https://market.example"
        assert provider.market_services_token == "market-test"
        assert provider.token == "research-test"
    finally:
        get_market_data_provider.cache_clear()


def test_integrated_gateway_preserves_legacy_service_credentials(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"data": {}}
    monkeypatch.setattr("instock.core.market_data_provider.requests.get",
                        lambda url, **kwargs: calls.append((url, kwargs)) or Response())
    provider = NewmaDeskMarketDataProvider("https://desk.example/api/research", token="desk-test")
    for route in ("trading-calendar", "execution-prices", "market-structure", "market-evidence"):
        provider._invoke_research_http("/api/capital-flow/" + route, {}, desk_native=True)
        assert calls[-1][0] == "https://desk.example/api/capital-flow/" + route
        assert calls[-1][1]["headers"]["Authorization"] == "Bearer desk-test"
    provider = NewmaDeskMarketDataProvider("https://desk.example/api/research", token="desk-test",
                                         market_services_url="https://desk.example")
    provider._invoke_research_http("/api/capital-flow/trading-calendar", {}, desk_native=True)
    assert "Authorization" not in calls[-1][1]["headers"]


def test_execution_prices_require_same_symbol_dates_and_unadjusted_basis(monkeypatch):
    payload = {"schemaVersion": "newma-desk.execution-prices.v1", "symbol": "510300", "start": "2026-01-02", "end": "2026-01-05", "priceBasis": "unadjusted", "rows": []}
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return payload
    def fake_get(url, **kwargs):
        calls.append((url, kwargs)); return Response()
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    assert provider.get_execution_prices("510300", "2026-01-02", "2026-01-05")["rows"] == []
    assert calls[0][0] == "http://127.0.0.1:8911/api/capital-flow/execution-prices"
    assert calls[0][1]["params"] == {"symbol": "510300", "start": "2026-01-02", "end": "2026-01-05"}
    for key, wrong in (("priceBasis", "qfq"), ("symbol", "000001"), ("end", "2026-01-06")):
        original = payload[key]; payload[key] = wrong
        with pytest.raises(MarketDataError, match="不匹配"):
            provider.get_execution_prices("510300", "2026-01-02", "2026-01-05")
        payload[key] = original


def test_market_structure_uses_desk_origin_not_research_proxy(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"schemaVersion": "newma-desk.market-structure.v1"}
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    assert provider.get_market_structure(refresh=True)["schemaVersion"] == "newma-desk.market-structure.v1"
    assert calls[0][0] == "http://127.0.0.1:8911/api/capital-flow/market-structure"
    assert calls[0][1]["params"] == {"refresh": "true"}


def test_market_evidence_keeps_exact_code_date_and_aliases(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"schemaVersion": "newma-desk.market-evidence.v1"}
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    provider.get_market_evidence("512070.SH", "2026-10-15", "非银金融", ("非银金融", "证券", "保险"))
    assert calls[0][0] == "http://127.0.0.1:8911/api/capital-flow/market-evidence"
    assert calls[0][1]["params"] == {"code": "512070.SH", "as_of": "2026-10-15", "industry": "非银金融",
                                      "aliases": ["非银金融", "证券", "保险"], "refresh": "false"}


def _bars(size=30):
    return [
        {
            "datetime": datetime(2026, 1, 1) + timedelta(days=index),
            "open": 10 + index * 0.1,
            "high": 10.5 + index * 0.1,
            "low": 9.5 + index * 0.1,
            "close": 10.2 + index * 0.1,
            "vol": 1000 + index,
            "volume": 1000 + index,
            "amount": 10000 + index,
        }
        for index in range(size)
    ]


def test_standalone_health_uses_existing_research_health_route(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "service": "vibe-research-api"}

    def fake_get(url, headers, timeout, proxies=None, params=None):
        captured.update({
            "url": url,
            "headers": headers,
            "timeout": timeout,
            "proxies": proxies,
        })
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider(
        "http://127.0.0.1:8991/api", token="secret", timeout=20
    )

    result = provider.health()

    assert result == {
        "status": "ready",
        "provider": "newma-desk",
        "reason": None,
        "service": "vibe-research-api",
    }
    assert captured["url"] == "http://127.0.0.1:8991/api/health"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["timeout"] == 2.0
    assert captured["proxies"] == {"http": None, "https": None}


def test_desk_health_uses_registered_capability_not_old_embedded_route(monkeypatch):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k: pytest.fail("不能探测旧内嵌Research路径"))
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "service": "vibe-research-api"})
    monkeypatch.setattr("instock.core.market_data_provider.requests.post", post)
    result = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research").health()
    assert result["status"] == "ready"
    assert calls[0][0] == "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.health"
    assert calls[0][1]["json"] == {}
    assert calls[0][1]["timeout"] == 2


@pytest.mark.parametrize("gateway", [False, True])
def test_newma_desk_health_returns_unavailable_without_raising(monkeypatch, gateway):
    def fake_get(url, headers, timeout, proxies=None, params=None):
        raise requests.ConnectionError("desk stopped")

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    monkeypatch.setattr("instock.core.market_data_provider.requests.post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("desk stopped")))
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research" if gateway else "http://127.0.0.1:8991/api")

    result = provider.health()

    assert result["status"] == "unavailable"
    assert result["reason"] == "desk_health_unreachable"
    assert result["provider"] == "newma-desk"


@pytest.mark.parametrize("gateway", [False, True])
def test_health_distinguishes_missing_desk_capability_from_connection_failure(monkeypatch, gateway):
    calls = []
    def unavailable(url, **kwargs):
        calls.append(url)
        response = requests.Response()
        response.status_code = 404
        response.url = url
        response._content = b'{"detail":"data service capability not found"}'
        return response
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", unavailable)
    monkeypatch.setattr("instock.core.market_data_provider.requests.post", unavailable)
    base = "http://127.0.0.1:8911/api/research" if gateway else "http://127.0.0.1:8991/api"
    result = NewmaDeskMarketDataProvider(base).health()
    assert result["status"] == "unavailable"
    assert result["reason"] == ("desk_health_capability_unavailable" if gateway else "desk_health_unreachable")
    assert len(calls) == 1
    if gateway:
        assert "market.health" in result["detail"]
        assert "配套" in result["detail"]
        assert "http://" not in result["detail"]


def test_newma_desk_json_capability_retries_one_transient_gateway_failure(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(
                    f"HTTP {self.status_code}", response=self
                )

        def json(self):
            return {"data": {"identity": {"symbol": "300502"}}}

    def fake_post(url, json, headers, timeout, proxies=None):
        calls.append(url)
        return Response(503 if len(calls) == 1 else 200)

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    result = provider.get_equity_snapshot("300502")

    assert result["identity"]["symbol"] == "300502"
    assert len(calls) == 2


def test_newma_desk_equity_snapshot_does_not_bypass_failed_gateway(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []

    def unavailable(*args, **kwargs):
        raise MarketDataError("gateway unavailable")

    def direct(path, parameters):
        calls.append((path, parameters))
        return {"identity": {"symbol": "300502", "name": "新易盛"}}

    monkeypatch.setattr(provider, "_invoke_json_capability", unavailable)
    monkeypatch.setattr(provider, "_invoke_research_http", direct)

    with pytest.raises(MarketDataError, match="gateway unavailable"):
        provider.get_equity_snapshot("300502")
    assert calls == []


def test_newma_desk_equity_comparison_uses_longer_batch_timeout(monkeypatch):
    provider = NewmaDeskMarketDataProvider(
        "http://127.0.0.1:8911/api/research", timeout=20
    )
    calls = []

    def invoke(capability, path, parameters, *, timeout=None):
        calls.append((capability, path, parameters, timeout))
        return {"rows": [], "errors": []}

    monkeypatch.setattr(provider, "_invoke_json_capability", invoke)

    result = provider.get_equity_comparison(["300502", "300308"])

    assert result == {"rows": [], "errors": []}
    assert calls == [(
        "research.equity-comparison",
        "/equity-research/comparison",
        {"symbols": "300502,300308"},
        60.0,
    )]


def test_newma_desk_equity_comparison_cache_reuses_and_copy_isolates_packet(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []

    def direct(capability, path, parameters, *, timeout=None):
        calls.append((path, parameters, timeout))
        return {
            "rows": [{"identity": {"symbol": "300502", "name": "新易盛"}}],
            "errors": [],
        }

    monkeypatch.setattr(provider, "_invoke_json_capability", direct)
    first = provider.get_equity_comparison(["300502"])
    first["rows"][0]["identity"]["name"] = "被修改"
    second = provider.get_equity_comparison(["300502"])

    assert len(calls) == 1
    assert second["rows"][0]["identity"]["name"] == "新易盛"


def test_newma_desk_equity_comparison_refresh_bypasses_cache(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []

    def direct(capability, path, parameters, *, timeout=None):
        calls.append(1)
        return {"rows": [], "errors": []}

    monkeypatch.setattr(provider, "_invoke_json_capability", direct)
    provider.get_equity_comparison(["300502"])
    provider.get_equity_comparison(["300502"], refresh=True)

    assert len(calls) == 2


@pytest.mark.parametrize("status,code", [(401, "UPSTREAM_AUTH_REQUIRED"), (403, "UPSTREAM_FORBIDDEN"), (502, "UPSTREAM_TIMEOUT")])
def test_financial_gateway_errors_are_safe_and_not_retried(monkeypatch, status, code):
    calls = []
    class Response:
        status_code = status
        def raise_for_status(self):
            raise requests.HTTPError("private-url?token=secret", response=self)
        def json(self):
            return {"error": {"code": code, "message": "private-url?token=secret"}}
    monkeypatch.setattr("instock.core.market_data_provider.requests.post", lambda *a, **k: calls.append(k) or Response())
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    with pytest.raises(MarketDataError) as caught:
        provider.get_equity_snapshot("300502")
    assert caught.value.code == code
    assert "private-url" not in str(caught.value)
    assert "secret" not in str(caught.value)
    assert len(calls) == 1


def test_standalone_comparison_uses_configured_auth_and_batch_budget(monkeypatch):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda url, **k:
        calls.append((url, k)) or SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": {"rows": []}}))
    provider = NewmaDeskMarketDataProvider("https://research.example/api", token="synthetic-key")
    provider.get_equity_comparison(["300502", "300308"])
    assert calls[0][0] == "https://research.example/api/equity-research/comparison"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer synthetic-key"
    assert calls[0][1]["timeout"] == 60


def test_normalize_kline_keeps_actual_week_end_date():
    frame = _normalize_kline(_bars(), period="weekly", limit=10, source="fixture")

    assert not frame.empty
    assert frame.attrs["data_source"] == "fixture"
    assert set(["date", "open", "high", "low", "close", "volume", "amount"]).issubset(frame.columns)
    assert all(date.weekday() <= 4 for date in frame["date"])


def test_normalize_kline_accepts_millisecond_timestamp():
    rows = _bars(3)
    for index, row in enumerate(rows):
        row.pop("datetime")
        row["timestamp"] = int((datetime(2026, 1, 1) + timedelta(days=index)).timestamp() * 1000)

    frame = _normalize_kline(rows, period="daily", limit=3, source="fixture")

    assert frame["date"].iloc[0].year == 2026
    assert frame["date"].iloc[-1].day == 3


def test_newma_desk_adapter_uses_unified_kline_api(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "symbol": "300502",
                    "market": "CN",
                    "timeframe": "1w",
                    "adjust": "qfq",
                    "source": "tencent",
                    "asOf": "2026-08-04T08:05:59+00:00",
                    "hasMore": False,
                    "items": _bars(25),
                }
            }

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
            "proxies": proxies,
        })
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8000", token="secret")
    frame = provider.get_kline("300502.SZ", period="weekly", limit=120)

    assert captured["url"] == "http://127.0.0.1:8000/api/market-terminal/ohlcv"
    assert captured["params"] == {
        "symbol": "300502", "market": "CN", "timeframe": "1w", "limit": 120, "adjust": "qfq"
    }
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["proxies"] == {"http": None, "https": None}
    assert frame.attrs["data_source"] == "newma-desk"
    assert frame.attrs["adjust"] == "qfq"
    assert frame.attrs["upstream_source"] == "tencent"
    assert frame.attrs["upstream_as_of"] == "2026-08-04T08:05:59+00:00"
    assert frame.attrs["upstream_market"] == "CN"
    assert frame.attrs["upstream_timeframe"] == "1w"
    assert frame.attrs["upstream_has_more"] is False
    assert len(frame) == 25


@pytest.mark.parametrize("method,symbol", [("get_kline", "300502"), ("get_signal_kline", "881001")])
@pytest.mark.parametrize("metadata,expected", [
    ({}, "unknown"), ({"adjust": None}, "unknown"), ({"adjust": ""}, "unknown"),
    ({"adjust": "unexpected"}, "unknown"), ({"adjust": "qfq"}, "qfq"),
    ({"adjust": "hfq"}, "hfq"), ({"adjust": "none"}, "none"),
])
def test_kline_reports_returned_adjustment_not_requested_adjustment(monkeypatch, method, symbol, metadata, expected):
    from types import SimpleNamespace
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": {"items": _bars(40), **metadata}})
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k: response)
    monkeypatch.setattr("instock.core.market_data_provider.requests.post", lambda *a, **k: response)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    frame = getattr(provider, method)(symbol, limit=40)
    assert len(frame) == 40
    assert frame.attrs["adjust"] == expected


@pytest.mark.parametrize("method", ["get_kline", "get_signal_kline"])
def test_bare_kline_rows_keep_unknown_adjustment(monkeypatch, method):
    from types import SimpleNamespace
    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k:
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": _bars(40)}))
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8991/api")
    assert getattr(provider, method)("300502", limit=40).attrs["adjust"] == "unknown"


def test_newma_desk_adapter_preserves_sw_index_code_and_uses_no_adjust(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "symbol": "801730.SI",
                    "market": "CN",
                    "timeframe": "1d",
                    "adjust": "none",
                    "source": "tushare",
                    "items": _bars(30),
                }
            }

    def fake_post(url, json, headers, timeout, proxies=None):
        captured.update({"url": url, "params": json, "proxies": proxies})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    frame = provider.get_signal_kline("801730.SI", period="daily", limit=30)

    assert captured["url"] == (
        "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.ohlcv"
    )
    assert captured["params"]["symbol"] == "801730.SI"
    assert captured["params"]["adjust"] == "none"
    assert captured["proxies"] == {"http": None, "https": None}
    assert frame.attrs["adjust"] == "none"
    assert frame.attrs["upstream_source"] == "tushare"


def test_newma_desk_signal_request_never_uses_legacy_kline_fallback(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        raise requests.ConnectionError("fixture failure")

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    with pytest.raises(MarketDataError, match="指数信号请求失败"):
        provider.get_signal_kline("801730.SI", limit=30)

    assert calls == [
        "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.ohlcv"
    ]


def test_newma_desk_adapter_uses_standard_data_service_gateway(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"items": _bars(40), "adjust": "qfq", "source": "tushare"}}

    def fake_post(url, json, headers, timeout, proxies=None):
        captured.update({"url": url, "json": json, "proxies": proxies})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    frame = provider.get_kline("510300.SH", limit=40)

    assert captured["url"].endswith("/invoke/market.ohlcv")
    assert captured["json"] == {
        "symbol": "510300",
        "market": "CN",
        "timeframe": "1d",
        "limit": 40,
        "adjust": "qfq",
    }
    assert captured["proxies"] == {"http": None, "https": None}
    assert frame.attrs["upstream_source"] == "tushare"


def test_newma_desk_adapter_normalizes_stock_scan(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "items": [{
                        "symbol": "300502", "name": "新易盛", "market": "CN",
                        "exchange": "SZ", "price": 415.3, "changePct": 3.93,
                        "amount": 19_977_399_893.31, "turnoverPct": 3.86,
                        "volumeRatio": 0.72, "marketCap": 579_034_800_865,
                        "floatMarketCap": 520_887_183_517, "pe": 52.07,
                        "pb": 29.83, "industry": "通信设备",
                        "industryL1": "通信", "industryL2": "通信设备",
                        "industryClassification": {"taxonomy": "sw2021",
                            "source": "tushare.index_member_all", "l1Code": "801770.SI",
                            "l2Code": "801102.SI", "pointInTime": False},
                    }],
                    "market": "CN", "sort": "amount", "order": "desc",
                    "source": "tushare", "asOf": "2026-08-11T09:34:14+00:00",
                    "coverage": {"requested": 30, "returned": 1},
                }
            }

    def fake_post(url, json, headers, timeout, proxies=None):
        captured.update({"url": url, "json": json, "proxies": proxies})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    result = provider.get_stock_scan(limit=30)

    assert captured["url"].endswith("/invoke/market.scan")
    assert captured["json"] == {"market": "CN", "sort": "amount", "order": "desc", "limit": 30}
    assert captured["proxies"] == {"http": None, "https": None}
    assert result["source"] == "tushare"
    assert result["as_of"] == "2026-08-11T09:34:14+00:00"
    assert result["coverage"]["sort_basis"] == "amount"
    assert result["items"][0]["change_pct"] == 3.93
    assert result["items"][0]["turnover_pct"] == 3.86
    assert result["items"][0]["volume_ratio"] == 0.72
    assert result["items"][0]["float_market_cap"] == 520_887_183_517
    assert result["items"][0]["industry_l1"] == "通信"
    assert result["items"][0]["industry_l2"] == "通信设备"
    assert result["items"][0]["industry_classification"]["source"] == "tushare.index_member_all"


def test_newma_desk_adapter_enriches_identity_only_scan_with_batch_quotes(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, json, headers, timeout, proxies=None):
        calls.append((url, json))
        if url.endswith("/invoke/market.scan"):
            if json["sort"] == "amount":
                return Response({"data": {
                    "items": [{
                        "symbol": "300502", "name": "新易盛", "market": "CN",
                        "price": None, "amount": None, "pe": 50,
                        "industry": "通信设备",
                    }],
                    "source": "eastmoney-delay", "asOf": "2026-08-12T00:00:00+00:00",
                    "coverage": {"requested": 30, "returned": 1},
                }})
            return Response({"data": {
                "items": [{
                    "symbol": "300502", "name": "新易盛", "market": "CN",
                    "price": None, "amount": None, "pe": 50,
                    "industry": "通信设备",
                }],
                "source": "eastmoney-delay", "asOf": "2026-08-12T00:00:00+00:00",
                "coverage": {"requested": 30, "returned": 1},
            }})
        if url.endswith("/invoke/market.quotes"):
            return Response({"data": {
                "items": [{
                    "symbol": "300502", "name": "新易盛", "market": "CN",
                    "exchange": "SZ", "price": 415.3, "changePct": 3.93,
                    "amount": 19_977_399_893.31, "turnoverPct": 3.86,
                    "volumeRatio": 0.72, "marketCap": 579_034_800_865,
                    "floatMarketCap": 520_887_183_517, "pe": 52.07,
                    "pb": 29.83, "source": "tencent",
                }],
                "asOf": "2026-08-12T01:04:54+00:00",
            }})
        raise AssertionError(url)

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    result = provider.get_stock_scan(limit=30)

    assert calls == [
        (
            "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.scan",
            {"market": "CN", "sort": "amount", "order": "desc", "limit": 30},
        ),
        (
            "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.scan",
            {"market": "CN", "sort": "marketCap", "order": "desc", "limit": 200},
        ),
        (
            "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.quotes",
            {"symbols": "CN:300502"},
        ),
    ]
    assert result["source"] == "eastmoney-delay+tencent"
    assert result["as_of"] == "2026-08-12T01:04:54+00:00"
    assert result["coverage"]["quote_enriched"] is True
    assert result["coverage"]["sort_basis"] == "amount"
    assert result["items"][0]["price"] == 415.3
    assert result["items"][0]["amount"] == 19_977_399_893.31
    assert result["items"][0]["industry"] == "通信设备"


def test_newma_desk_adapter_keeps_scan_market_caps_when_live_quote_swaps_them(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, json, **kwargs):
        if url.endswith("/invoke/market.scan"):
            return Response({"data": {
                "items": [{
                    "symbol": "300502", "name": "新易盛", "price": None,
                    "marketCap": 597_020_712_089,
                    "floatMarketCap": 537_066_920_256,
                }],
                "source": "eastmoney-delay",
            }})
        if url.endswith("/invoke/market.quotes"):
            return Response({"data": {"items": [{
                "symbol": "300502", "name": "新易盛", "price": 428.2,
                "amount": 18_751_550_000, "marketCap": 537_067_000_000,
                "floatMarketCap": 597_021_000_000, "source": "tencent",
            }]}})
        raise AssertionError(url)

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    result = NewmaDeskMarketDataProvider(
        "http://127.0.0.1:8911/api/research"
    ).get_stock_scan(limit=30)

    row = result["items"][0]
    assert row["price"] == 428.2
    assert row["amount"] == 18_751_550_000
    assert row["market_cap"] == 597_020_712_089
    assert row["float_market_cap"] == 537_066_920_256


def test_newma_desk_adapter_keeps_market_cap_proxy_when_live_amount_is_zero(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, json, **kwargs):
        if url.endswith("/invoke/market.scan"):
            if json["sort"] == "amount":
                return Response({"data": {
                    "items": [{"symbol": "600001", "name": "大市值", "price": None}],
                    "source": "eastmoney-delay",
                }})
            return Response({"data": {
                "items": [
                    {"symbol": "600001", "name": "大市值", "marketCap": 200, "industry": "银行"},
                    {"symbol": "600002", "name": "小市值", "marketCap": 100, "industry": "电子"},
                ],
                "source": "eastmoney-delay", "coverage": {"requested": 200, "returned": 2},
            }})
        if url.endswith("/invoke/market.quotes"):
            return Response({"data": {"items": [
                {"symbol": "600001", "name": "大市值", "price": 10, "amount": 0, "source": "tencent"},
                {"symbol": "600002", "name": "小市值", "price": 20, "amount": 0, "source": "tencent"},
            ]}})
        raise AssertionError(url)

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    result = NewmaDeskMarketDataProvider(
        "http://127.0.0.1:8911/api/research"
    ).get_stock_scan(sort="amount", limit=30)

    assert [row["symbol"] for row in result["items"]] == ["600001", "600002"]
    assert result["coverage"]["sort_basis"] == "marketCap_proxy"
    assert result["coverage"]["scope"] == "market_cap_pool_local_sort"


def test_newma_desk_adapter_normalizes_full_market_turnover_top(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {
                "stocks": [{
                    "code": "300502", "name": "新易盛", "price": 428.2,
                    "pct": 4.2, "amount": 18_751_550_000,
                    "mcap": 597_020_712_089, "float_cap": 537_066_920_256,
                    "industry": "通信设备",
                }],
                "updated": "2026-08-13T09:31:00+08:00",
            }}

    monkeypatch.setattr(
        "instock.core.market_data_provider.requests.post",
        lambda *args, **kwargs: Response(),
    )
    result = NewmaDeskMarketDataProvider(
        "http://127.0.0.1:8911/api/research"
    ).get_market_turnover_top()

    assert result["items"][0]["symbol"] == "300502"
    assert result["items"][0]["amount"] == 18_751_550_000
    for field in ("pe", "pb", "turnover_pct", "volume_ratio"):
        assert result["items"][0][field] is None
    assert result["coverage"] == {
        "requested": 20,
        "returned": 1,
        "quote_enriched": False,
        "sort_basis": "amount",
        "scope": "full_market_top20",
    }


def test_newma_desk_liquidity_scan_combines_turnover_top_with_market_cap_fill(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    monkeypatch.setattr(provider, "get_market_turnover_top", lambda **kwargs: {
        "items": [{"symbol": "300502", "name": "新易盛"}],
        "source": "turnover",
        "as_of": "2026-08-13",
        "coverage": {},
    })
    monkeypatch.setattr(provider, "get_stock_scan", lambda **kwargs: {
        "items": [
            {"symbol": "300502", "name": "新易盛"},
            {"symbol": "000001", "name": "平安银行"},
        ],
        "source": "market-cap",
        "as_of": "2026-08-13",
        "coverage": {"quote_enriched": True},
    })

    result = provider.get_liquidity_scan(limit=20)

    assert [row["symbol"] for row in result["items"]] == ["300502", "000001"]
    assert result["coverage"]["sort_basis"] == "amount_top20_then_marketCap"
    assert result["coverage"]["scope"] == "full_market_top20_plus_market_cap_pool"
    assert result["coverage"]["full_market_turnover_count"] == 1


def test_newma_desk_liquidity_scan_falls_back_when_turnover_capability_is_unavailable(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    def unavailable(**kwargs):
        raise MarketDataError("turnover unavailable")

    monkeypatch.setattr(provider, "get_market_turnover_top", unavailable)
    monkeypatch.setattr(provider, "get_stock_scan", lambda **kwargs: {
        "items": [{"symbol": "000001", "name": "平安银行"}],
        "source": "market-cap",
        "as_of": "2026-08-13",
        "coverage": {"quote_enriched": False},
    })

    result = provider.get_liquidity_scan(limit=30)

    assert result["items"][0]["symbol"] == "000001"
    assert result["coverage"]["sort_basis"] == "marketCap"
    assert result["coverage"]["scope"] == "market_cap_pool_only"


def test_newma_desk_equity_snapshot_cache_reuses_and_copy_isolates_packet(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []

    def invoke(*args, **kwargs):
        calls.append(1)
        return {"identity": {"symbol": "300502", "name": "新易盛"}}

    monkeypatch.setattr(provider, "_invoke_json_capability", invoke)
    first = provider.get_equity_snapshot("300502")
    first["identity"]["name"] = "被修改"
    second = provider.get_equity_snapshot("300502")

    assert len(calls) == 1
    assert second["identity"]["name"] == "新易盛"


def test_newma_desk_adapter_reads_existing_research_event_interfaces(monkeypatch):
    calls = []
    payloads = {
        "/api/fund-flow": [],
        "/api/dragon-tiger": {"records": [{"date": "2026-07-28"}]},
        "/api/margin": [{"date": "2026-08-10", "rzye": 100}],
        "/api/block-trade": [{"date": "2026-07-31", "amount": 1000}],
        "/api/holders": [{"date": "2026-03-31", "holder_num": 10}],
        "/api/dividend": [{"date": "2026-06-11", "bonus_rmb": 10}],
        "/api/lockup": {"history": [{"date": "2025-06-13"}], "upcoming": []},
    }

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": self.payload}

    def fake_get(url, params, headers, timeout, proxies=None):
        path = next(path for path in payloads if url.endswith(path))
        calls.append((url, params, proxies))
        return Response(payloads[path])

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    result = provider.get_security_event_flow("300502.SZ")

    assert len(calls) == 7
    assert calls[0][0] == "http://127.0.0.1:8911/api/research/api/fund-flow"
    assert all(call[1] == {"code": "300502"} for call in calls)
    assert all(call[2] == {"http": None, "https": None} for call in calls)
    assert result["source"] == "newma-desk-research-http"
    assert result["sources"]["fund_flow"]["state"] == "empty"
    assert result["sources"]["dragon_tiger"]["records"] == 1
    assert result["sources"]["lockup"]["units"]["able_shares"] == "万股"


def test_event_source_failure_keeps_http_status_without_exposing_internal_url(monkeypatch):
    provider = NewmaDeskMarketDataProvider('http://127.0.0.1:18913/api')
    def invoke(path, params):
        if path == '/api/dragon-tiger':
            response = requests.Response()
            response.status_code = 502
            response.url = 'http://internal.test/private?token=test-only'
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise MarketDataError(str(exc)) from exc
        return []
    monkeypatch.setattr(provider, '_invoke_research_http', invoke)
    result = provider.get_security_event_flow('300502')
    failure = result['failures'][0]
    assert failure['source'] == 'dragon_tiger'
    assert '502' in failure['message']
    assert '不等于' in failure['message']
    assert 'internal.test' not in failure['message']
    assert 'token=' not in failure['message']
    assert result['sources']['dragon_tiger']['state'] == 'failed'


def test_newma_desk_adapter_retries_transient_gateway_error(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(
                    f"HTTP {self.status_code}",
                    response=self,
                )

        def json(self):
            return {"data": {"items": _bars(25), "source": "tencent"}}

    def fake_get(url, params, headers, timeout, proxies=None):
        calls.append(url)
        if not url.endswith("/api/market-terminal/ohlcv"):
            raise AssertionError("瞬时网关错误不应直接降级到旧接口")
        return Response(502 if len(calls) < 3 else 200)

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8000")

    frame = provider.get_kline("300502", period="daily", limit=25)

    assert len(calls) == 3
    assert len(frame) == 25


def test_newma_desk_adapter_filters_latest_window_for_historical_as_of(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"items": _bars(40), "hasMore": False}}

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({"url": url, "params": params})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8000")
    frame = provider.get_kline("300502", period="daily", limit=10, as_of="2026-01-20")

    assert captured["params"]["limit"] == 800
    assert captured["params"]["asOf"] == "2026-01-20"
    assert len(frame) == 10
    assert frame["date"].iloc[-1].strftime("%Y-%m-%d") == "2026-01-20"
    assert frame.attrs["as_of_mode"] == "client_filter"
    assert frame.attrs["upstream_limit"] == 800
    assert "upstream_no_historical_anchor" in frame.attrs["replay_limitations"]


def test_newma_desk_adapter_rejects_as_of_before_latest_window(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"items": _bars(40)}}

    monkeypatch.setattr(
        "instock.core.market_data_provider.requests.get",
        lambda *args, **kwargs: Response(),
    )
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8000")

    with pytest.raises(HistoricalWindowUnavailable, match="无法回放"):
        provider.get_kline("300502", period="daily", limit=10, as_of="2025-01-01")


def test_newma_desk_adapter_uses_existing_industry_api(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"top": [{"rank": 1, "name": "银行"}], "bottom": [], "total": 100}}

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
            "proxies": proxies,
        })
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = VibeDeskMarketDataProvider("http://127.0.0.1:8900", token="secret")
    result = provider.get_industry_ranking(top=50)

    assert captured["url"] == "http://127.0.0.1:8900/api/industry"
    assert captured["params"] == {"top": 50}
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["proxies"] == {"http": None, "https": None}
    assert result["total"] == 100
    assert result["top"][0]["name"] == "银行"


def test_newma_desk_adapter_uses_existing_market_overview(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "sentiment": {
                        "up": 3405, "down": 1664, "flat": 128,
                        "breadth": "偏强", "speculation": "亢奋",
                    },
                    "sectors": [],
                    "updated": "2026-08-04 17:07",
                }
            }

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
            "proxies": proxies,
        })
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8900", token="secret")
    result = provider.get_market_overview()

    assert captured["url"] == "http://127.0.0.1:8900/api/market/overview"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["params"] == {}
    assert captured["proxies"] == {"http": None, "https": None}
    assert result["sentiment"]["breadth"] == "偏强"
    assert result["sentiment"]["up"] == 3405
    assert result["updated"] == "2026-08-04 17:07"


def test_newma_desk_adapter_normalizes_market_emotion(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {
                "date": "2026-08-17", "zt_count": 63, "dt_count": 10,
                "zb_count": 19, "max_boards": 5, "lianban_count": 11,
                "seal_rate": 0.768, "break_rate": 0.232,
                "promotion_rate": 0.186, "yzt_count": 59,
                "ladder": [{"boards": 2, "count": 5}],
                "lianban_stocks": [{"code": "300862", "boards": 5}],
            }}

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({"url": url, "params": params})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8900")
    result = provider.get_market_emotion()

    assert captured == {
        "url": "http://127.0.0.1:8900/api/market/emotion", "params": {}
    }
    assert result["state"] == "available"
    assert result["limit_up_count"] == 63
    assert result["break_rate"] == 0.232
    assert result["leaders"][0]["code"] == "300862"


def test_newma_desk_adapter_normalizes_dragon_tiger_institution_evidence(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {
                "records": [{"date": "2026-08-15", "reason": "日涨幅偏离", "net_buy": 10}],
                "institution": {"buy_amt": 1000, "sell_amt": 300, "net_amt": 700},
            }}

    captured = {}

    def fake_get(url, params, headers, timeout, proxies=None):
        captured.update({"url": url, "params": params})
        return Response()

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", fake_get)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8900")
    result = provider.get_dragon_tiger_evidence("300862")

    assert captured["url"] == "http://127.0.0.1:8900/api/dragon-tiger"
    assert captured["params"] == {"code": "300862"}
    assert result["institution"]["net_amt"] == 700
    assert result["records"][0]["reason"] == "日涨幅偏离"


def test_newma_desk_adapter_falls_back_to_overview_sectors_for_industry(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    calls = []

    def fake_post(url, json, **kwargs):
        calls.append((url, json))
        if url.endswith("/invoke/market.overview"):
            return Response({
                "data": {
                    "sentiment": {},
                    "sectors": [
                        {"name": "通信设备", "pct": 3.2, "net": 8.1, "firms": 90},
                        {"name": "银行", "pct": -1.1, "net": -3.0, "firms": 42},
                    ],
                    "updated": "2026-08-10 09:30",
                }
            })
        raise AssertionError(url)

    monkeypatch.setattr("instock.core.market_data_provider.requests.post", fake_post)
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")

    result = provider.get_industry_ranking(top=5)

    assert result["total"] == 2
    assert result["top"][0]["name"] == "通信设备"
    assert result["bottom"][-1]["name"] == "银行"
    assert calls == [(
        "http://127.0.0.1:8911/api/data-services/market-data/invoke/market.overview",
        {},
    )]


def test_industry_ranking_prefers_daily_membership_breadth_and_preserves_scope(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    daily = {"top": [{"name": "银行", "change_pct": 0, "up_count": 2, "down_count": 3}],
             "bottom": [], "total": 1, "as_of": "2026-10-21", "source": "tushare-daily",
             "coverage": {"quoteCount": 5568}, "point_in_time": False}
    monkeypatch.setattr(provider, "get_market_overview", lambda: {"industryBreadth": daily,
        "sectors": [{"name": "错误旧板块", "pct": 1}]})
    result = provider.get_industry_ranking()
    assert result == daily


def test_newma_desk_security_master_status_keeps_summary_only_semantics(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []

    def invoke(capability, path, parameters, **kwargs):
        calls.append((capability, path, parameters))
        return {
            "count": 5558,
            "exchanges": {"SH": 2316, "SZ": 2898, "BJ": 344},
            "updatedAt": "2026-08-17T07:48:17+0800",
            "source": "mootdx+eastmoney-clist",
        }

    monkeypatch.setattr(provider, "_invoke_json_capability", invoke)

    result = provider.get_security_master_status()

    assert result == {
        "state": "available",
        "enumerable": False,
        "count": 5558,
        "exchanges": {"SH": 2316, "SZ": 2898, "BJ": 344},
        "source": "mootdx+eastmoney-clist",
        "updated_at": "2026-08-17T07:48:17+0800",
    }
    assert calls == [("market.security-master", "/api/market-terminal/security-master", {})]


def test_stock_scan_failure_keeps_cause_without_exposing_transport_details(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8992/api")
    error = requests.ConnectionError("private transport detail")
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(provider, "_request_capability", fail)
    with pytest.raises(MarketDataError, match="行情扫描暂不可用") as caught:
        provider.get_stock_scan()
    assert caught.value.__cause__ is error
    assert "private transport detail" not in str(caught.value)


def test_daily_scan_preserves_missing_metrics_and_observation_through_union(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8992/api")
    data = {
        "items": [
            {"symbol": "000001", "name": "缺估值", "price": 10, "amount": 100, "pe": None},
            {"symbol": "600000", "name": "真实零", "price": 10, "amount": 0, "pe": 0},
        ],
        "source": "tushare-daily", "asOf": "2026-10-19T15:00:00+08:00",
        "receivedAt": "2026-10-20T10:00:00+08:00",
        "coverage": {"frequency": "daily", "realtime": False, "listedCount": 3,
                     "quoteCount": 2, "missingQuoteCount": 1, "basicCount": 1,
                     "scope": "daily_a_share_ranked_top", "rankableCount": 1, "missingSortCount": 1},
    }
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return data
    monkeypatch.setattr(provider, "_request_capability", lambda *a, **k: Response())
    monkeypatch.setattr(provider, "_enrich_scan_quotes", lambda *a, **k: pytest.fail("daily scan must not fetch live quotes"))
    monkeypatch.setattr(provider, "get_security_master_status", lambda: {})
    scan = provider.get_stock_scan(sort="pe", order="asc")
    assert [row["symbol"] for row in scan["items"]] == ["600000", "000001"]
    assert scan["items"][0]["pe"] == 0
    assert scan["items"][1]["pe"] is None
    assert scan["items"][1]["market_cap"] is None
    assert scan["items"][1]["scan_as_of"] == data["asOf"]
    assert scan["as_of"] == data["asOf"]
    assert scan["coverage"]["missingSortCount"] == 1
    universe = provider.get_candidate_universe()
    observations = universe["coverage"]["observations"]
    assert len(observations) == 1  # not repeated once per scan axis
    assert observations[0]["missing_quote_count"] == 1
    assert observations[0]["realtime"] is False
    assert universe["coverage"]["scans"][0]["coverage"]["rankableCount"] == 1


@pytest.mark.parametrize("failed", [False, True])
def test_candidate_universe_distinguishes_empty_from_unavailable(monkeypatch, failed):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8992/api")
    def scan(**kwargs):
        if failed:
            raise MarketDataError("transport failure")
        return {"items": []}
    monkeypatch.setattr(provider, "get_stock_scan", scan)
    with pytest.raises(MarketDataError) as caught:
        provider.get_candidate_universe()
    message = str(caught.value)
    assert ("11 项查询失败" in message) is failed
    assert ("没有返回候选" in message) is not failed


def test_candidate_universe_covers_small_cap_and_low_activity_tails():
    class AxisProvider(NewmaDeskMarketDataProvider):
        def __init__(self):
            super().__init__("http://127.0.0.1:8911/api/research")
            self.axes = []

        def get_security_master_status(self):
            return {"state": "unavailable", "enumerable": False, "count": 0}

        def get_stock_scan(self, *, market="CN", sort="amount", order="desc", limit=50):
            self.axes.append((market, sort, order, limit))
            index = len(self.axes)
            return {
                "items": [{
                    "symbol": f"60{index:04d}",
                    "name": f"样本{index}",
                    "market": market,
                    "amount": 1e9,
                    "market_cap": 1e10,
                }],
                "source": "fixture-desk",
                "as_of": "2026-08-15T15:00:00+08:00",
                "coverage": {},
            }

    provider = AxisProvider()
    result = provider.get_candidate_universe(markets=("CN",), per_scan_limit=200)

    assert ("CN", "marketCap", "asc", 200) in provider.axes
    assert ("CN", "turnoverPct", "asc", 200) in provider.axes
    assert ("CN", "volumeRatio", "asc", 200) in provider.axes
    assert len(provider.axes) == 11
    assert result["coverage"]["sort_basis"] == "eleven_scan_axes"
    assert result["coverage"]["full_security_master"] is False
    assert result["items"][0]["scan_membership_scores"]


def test_unavailable_scan_stops_sibling_axes_but_preserves_other_market(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8992/api")
    calls = []
    def scan(**kwargs):
        calls.append(kwargs)
        if kwargs["market"] == "CN":
            raise MarketScanUnavailable("source unavailable")
        return {"items": [{"symbol": "00700", "name": "腾讯控股", "market": "HK"}]}
    monkeypatch.setattr(provider, "get_stock_scan", scan)
    monkeypatch.setattr(provider, "get_security_master_status", lambda: {})
    result = provider.get_candidate_universe(markets=("CN", "HK"))
    assert len(calls) == 12
    assert len([call for call in calls if call["market"] == "CN"]) == 1
    assert result["items"][0]["symbol"] == "00700"
    assert result["coverage"]["scan_failures"][0]["skipped_axes"] == 10
    assert result["coverage"]["scan_count"] == 11


def test_all_unavailable_scans_report_skipped_axes_without_retry_fanout(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8992/api")
    calls = []
    def scan(**kwargs):
        calls.append(kwargs)
        raise MarketScanUnavailable("source unavailable")
    monkeypatch.setattr(provider, "get_stock_scan", scan)
    with pytest.raises(MarketDataError, match="1 项查询失败、10 项未执行"):
        provider.get_candidate_universe()
    assert len(calls) == 1


@pytest.mark.parametrize("provider_name", [None, "http", "newma-desk", "newma", "vibedesk"])
def test_http_provider_requires_explicit_data_endpoint(monkeypatch, provider_name):
    for name in ["INSTOCK_DATA_URL", "NEWMA_DESK_DATA_URL", "NEWMA_DOCK_DATA_URL", "VIBEDESK_DATA_URL",
                 "INSTOCK_MARKET_DATA_PROVIDER"]:
        monkeypatch.delenv(name, raising=False)
    if provider_name is not None:
        monkeypatch.setenv("INSTOCK_MARKET_DATA_PROVIDER", provider_name)
    get_market_data_provider.cache_clear()
    try:
        with pytest.raises(MarketDataError, match="INSTOCK_DATA_URL"):
            get_market_data_provider()
    finally:
        get_market_data_provider.cache_clear()


def test_legacy_provider_name_uses_newma_environment_precedence(monkeypatch):
    get_market_data_provider.cache_clear()
    monkeypatch.setenv("INSTOCK_MARKET_DATA_PROVIDER", "vibedesk")
    monkeypatch.setenv("NEWMA_DESK_DATA_URL", "http://127.0.0.1:8911/api/research")
    monkeypatch.setenv("VIBEDESK_DATA_URL", "http://127.0.0.1:8900")

    provider = get_market_data_provider()

    assert isinstance(provider, NewmaDeskMarketDataProvider)
    assert isinstance(provider, VibeDeskMarketDataProvider)
    assert provider.base_url == "http://127.0.0.1:8911/api/research"
    get_market_data_provider.cache_clear()
