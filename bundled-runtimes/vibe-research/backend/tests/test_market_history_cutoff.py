from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi.testclient import TestClient

import app as app_module
import market_terminal as terminal


def bar(day):
    return {"timestamp": int(datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000),
            "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "turnover": 1100}


def test_cutoff_skips_future_only_primary_and_keeps_fallback_provenance(monkeypatch):
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: [bar("2026-10-21")])
    def unavailable(*args):
        raise requests.HTTPError("source unavailable")
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", unavailable)
    monkeypatch.setattr(terminal, "_sina_cn_ohlcv", lambda *a: [bar("2026-10-19"), bar("2026-10-20"), bar("2026-10-21")])
    monkeypatch.setattr(terminal, "_mootdx_ohlcv", lambda *a: pytest.fail("available fallback must stop the chain"))
    result = terminal.get_ohlcv("920096", market="CN", as_of="2026-10-20")
    assert result["items"] == [bar("2026-10-19"), bar("2026-10-20")]
    assert result["source"] == "sina-unadjusted"
    assert result["adjust"] == "none"
    assert result["requestedAsOf"] == "2026-10-20"


def test_short_primary_history_before_cutoff_is_not_a_transport_failure(monkeypatch):
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: [bar("2026-10-20"), bar("2026-10-21")])
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: pytest.fail("do not refetch valid short history"))
    result = terminal.get_ohlcv("301660", market="CN", as_of="2026-10-20")
    assert result["items"] == [bar("2026-10-20")]
    assert result["source"] == "tencent" and result["adjust"] == "qfq"


def test_latest_mode_preserves_primary_without_cutoff(monkeypatch):
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: [bar("2026-10-21")])
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: pytest.fail("latest mode is unchanged"))
    assert terminal.get_ohlcv("920096", market="CN")["items"] == [bar("2026-10-21")]


def test_no_source_can_substitute_future_bars_for_cutoff(monkeypatch):
    for name in ["_tencent_ohlcv", "_eastmoney_ohlcv", "_sina_cn_ohlcv", "_mootdx_ohlcv"]:
        monkeypatch.setattr(terminal, name, lambda *a: [bar("2026-10-21")])
    with pytest.raises(RuntimeError, match="2026-10-20"):
        terminal.get_ohlcv("920096", market="CN", as_of="2026-10-20")


def test_cutoff_preserves_has_more_from_upstream_window(monkeypatch):
    rows = [bar("2026-10-20")] * 39 + [bar("2026-10-21")]
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: rows)
    result = terminal.get_ohlcv("600519", market="CN", limit=40, as_of="2026-10-20")
    assert len(result["items"]) == 39 and result["hasMore"] is True


def test_route_forwards_cutoff_and_rejects_invalid_calendar_date(monkeypatch):
    calls = []
    monkeypatch.setattr(terminal, "get_ohlcv", lambda symbol, **kwargs: calls.append(kwargs) or {"items": []})
    client = TestClient(app_module.app)
    assert client.get("/api/market-terminal/ohlcv?symbol=920096&asOf=2026-10-20").status_code == 200
    assert calls[0]["as_of"] == "2026-10-20"
    assert client.get("/api/market-terminal/ohlcv?symbol=920096&asOf=2026-02-30").status_code == 422
    assert len(calls) == 1


@pytest.mark.parametrize("market,timeframe", [("HK", "1d"), ("CN", "1w")])
def test_cutoff_does_not_claim_unsupported_market_or_period(market, timeframe):
    with pytest.raises(ValueError, match="A股日线"):
        terminal.get_ohlcv("600519", market=market, timeframe=timeframe, as_of="2026-10-20")
