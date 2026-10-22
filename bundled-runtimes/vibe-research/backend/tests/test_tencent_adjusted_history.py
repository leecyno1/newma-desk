"""Tencent must supply the requested adjustment, not a same-day raw quote."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import market_terminal as terminal


def response_for(monkeypatch, block):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0, "data": {"bj920096": block}}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(terminal.requests, "get", get)
    return calls


def row(day, close="11"):
    return [day, "10", close, "12", "9", "100"]


def test_uses_current_tencent_history_endpoint(monkeypatch):
    calls = response_for(monkeypatch, {"qfqday": [row("2026-10-20")]})
    bars = terminal._tencent_ohlcv("920096", "1d", 800, "qfq")
    assert len(bars) == 1
    assert calls[0][0] == "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    assert calls[0][1]["params"] == {"param": "bj920096,day,,,800,qfq"}


@pytest.mark.parametrize("adjust,period,key", [
    ("qfq", "1d", "qfqday"), ("hfq", "1d", "hfqday"),
    ("qfq", "1w", "qfqweek"), ("hfq", "1M", "hfqmonth"),
])
def test_raw_series_cannot_impersonate_adjusted_history(monkeypatch, adjust, period, key):
    raw_key = {"1d": "day", "1w": "week", "1M": "month"}[period]
    response_for(monkeypatch, {key: [], raw_key: [row("2026-10-21")]})
    assert terminal._tencent_ohlcv("920096", period, 800, adjust) == []


def test_explicit_unadjusted_request_uses_raw_series(monkeypatch):
    response_for(monkeypatch, {"day": [row("2026-10-20")]})
    bars = terminal._tencent_ohlcv("920096", "1d", 800, "none")
    assert len(bars) == 1 and bars[0]["close"] == 11


def test_missing_adjusted_series_falls_back_with_truthful_provenance(monkeypatch):
    response_for(monkeypatch, {"day": [row("2026-10-21")]})
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: [])
    raw_bars = terminal._parse_tencent_rows([row("2026-10-20")])
    monkeypatch.setattr(terminal, "_sina_cn_ohlcv", lambda *a: raw_bars)
    result = terminal.get_ohlcv("920096", market="CN")
    assert result["items"] == raw_bars
    assert result["source"] == "sina-unadjusted" and result["adjust"] == "none"


def test_cutoff_keeps_adjusted_history_instead_of_latest_raw_quote(monkeypatch):
    response_for(monkeypatch, {
        "qfqday": [row("2026-10-19", "10.5"), row("2026-10-20"), row("2026-10-21")],
        "day": [row("2026-10-21", "100")],
    })
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: pytest.fail("valid adjusted history must stop fallback"))
    result = terminal.get_ohlcv("920096", market="CN", limit=800, as_of="2026-10-20")
    assert result["source"] == "tencent" and result["adjust"] == "qfq"
    assert [bar["close"] for bar in result["items"]] == [10.5, 11]
    assert datetime.fromtimestamp(result["items"][-1]["timestamp"] / 1000, ZoneInfo("Asia/Shanghai")).date().isoformat() == "2026-10-20"
