from datetime import date

import pytest

import market_scan_daily as daily
import market_terminal as terminal


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "test-only")
    tables = {
        "daily": [
            {"ts_code": "688071.SH", "trade_date": day, "open": price, "high": price + 1,
             "low": price - 1, "close": price, "vol": 0, "amount": 0}
            for day, price in [("20261020", 10), ("20261019", 18)]
        ],
        "adj_factor": [{"ts_code": "688071.SH", "trade_date": day, "adj_factor": factor}
                       for day, factor in [("20261020", 2), ("20261019", 1)]],
    }
    calls = []

    def request(token, api, params, fields, **kwargs):
        calls.append((api, params, kwargs))
        return tables[api]

    monkeypatch.setattr(daily, "_request", request)
    return tables, calls


def load():
    return daily.load_adjusted_daily_history("688071.SH", limit=40, adjust="qfq", end=date(2026, 10, 20))


def test_same_day_factors_adjust_prices_not_volume_or_turnover(history):
    result = load()
    old, latest = result["items"]
    assert [old["close"], latest["close"]] == [9, 10]
    assert old["high"] == 9.5 and old["low"] == 8.5
    assert latest["volume"] == latest["turnover"] == 0
    assert result["adjustmentAnchor"] == "2026-10-20"
    assert history[1][0][1] == {"ts_code": "688071.SH", "end_date": "20261020", "limit": 40}
    assert history[1][1][1]["start_date"] == "20261019"
    assert all(call[2]["timeout"] == 4 for call in history[1])


def test_hfq_uses_factor_without_rebasing_to_window_start(history):
    result = daily.load_adjusted_daily_history("688071.SH", limit=40, adjust="hfq", end=date(2026, 10, 20))
    assert [row["close"] for row in result["items"]] == [18, 20]


@pytest.mark.parametrize("broken", ["missing", "zero", "nan", "wrong_security", "duplicate", "future"])
def test_incomplete_or_mismatched_factors_do_not_create_adjusted_prices(history, broken):
    rows = history[0]["adj_factor"]
    if broken == "missing": rows.pop()
    elif broken == "zero": rows[0]["adj_factor"] = 0
    elif broken == "nan": rows[0]["adj_factor"] = float("nan")
    elif broken == "wrong_security": rows[0]["ts_code"] = "600519.SH"
    elif broken == "duplicate": rows.append(dict(rows[0]))
    elif broken == "future": rows[0]["trade_date"] = "20261021"
    with pytest.raises(daily.DailyScanUnavailable):
        load()


def test_amount_converts_thousand_yuan_and_volume_stays_in_hands(history):
    history[0]["daily"][0].update(vol=123, amount=456)
    row = load()["items"][-1]
    assert row["volume"] == 123 and row["turnover"] == 456_000


def test_missing_token_does_not_make_external_request(monkeypatch, history):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(daily.DailyScanUnavailable):
        load()
    assert history[1] == []


@pytest.mark.parametrize("code", ["000300.SH", "510300.SH", "688071.SZ"])
def test_index_fund_or_wrong_exchange_cannot_query_stock_history(code, history):
    with pytest.raises(daily.DailyScanUnavailable):
        daily.load_adjusted_daily_history(code, limit=40, adjust="qfq")
    assert history[1] == []


def test_missing_price_does_not_get_filled_with_zero(history):
    history[0]["daily"][0]["close"] = None
    with pytest.raises(daily.DailyScanUnavailable):
        load()


def test_fallback_only_applies_to_explicit_daily_stock_source(monkeypatch):
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "tushare-daily")
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: [])
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: [])
    calls = []
    bars = terminal._parse_tencent_rows([["2026-10-20", "10", "10", "11", "9", "100"]])
    def load_history(code, **kwargs):
        calls.append((code, kwargs))
        return {"items": bars, "adjustmentAnchor": "2026-10-20"}
    monkeypatch.setattr(terminal, "load_adjusted_daily_history", load_history)
    monkeypatch.setattr(terminal, "_sina_cn_ohlcv", lambda *a: bars)
    result = terminal.get_ohlcv("688071", market="CN", as_of="2026-10-20")
    assert result["source"] == "tushare-daily" and result["adjust"] == "qfq"
    assert result["adjustmentAnchor"] == "2026-10-20"
    assert calls[0][0] == "688071.SH" and calls[0][1]["end"] == date(2026, 10, 20)
    calls.clear()
    terminal.get_ohlcv("510300", market="CN", asset_type="etf")
    terminal.get_ohlcv("688071", market="CN", timeframe="1w")
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "eastmoney")
    terminal.get_ohlcv("688071", market="CN")
    assert calls == []


def test_factor_failure_keeps_truthful_unadjusted_fallback(monkeypatch):
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "tushare-daily")
    monkeypatch.setattr(terminal, "_tencent_ohlcv", lambda *a: [])
    monkeypatch.setattr(terminal, "_eastmoney_ohlcv", lambda *a: [])
    def unavailable(*args, **kwargs):
        raise daily.DailyScanUnavailable("复权因子缺失")
    monkeypatch.setattr(terminal, "load_adjusted_daily_history", unavailable)
    bars = terminal._parse_tencent_rows([["2026-10-20", "10", "10", "11", "9", "100"]])
    monkeypatch.setattr(terminal, "_sina_cn_ohlcv", lambda *a: bars)
    result = terminal.get_ohlcv("688071", market="CN")
    assert result["source"] == "sina-unadjusted" and result["adjust"] == "none"
