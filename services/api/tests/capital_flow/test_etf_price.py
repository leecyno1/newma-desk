from datetime import date
import json

import httpx
import pytest

from vibe_visualization_api.capital_flow.etf_price import ETFPriceService, price_windows
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = ["2026-10-13", "2026-10-14", "2026-10-15"]


@pytest.mark.parametrize("close,factor,raw,adjusted", [(110, 1, 10, 10), (90, 1, -10, -10), (50, 2, -50, 0), (90, 100 / 90, -10, 0)])
def test_price_adjustment_and_action_gate(close, factor, raw, adjusted):
    prices = [{"date": day, "close": 100 if i < 2 else close, "vol": 100} for i, day in enumerate(DATES)]
    factors = [{"date": day, "adj_factor": 1 if i < 2 else factor} for i, day in enumerate(DATES)]
    windows = price_windows(prices, factors, DATES)
    window = windows["1"]
    assert window["rawReturnPct"] == raw
    assert window["adjustedReturnPct"] == pytest.approx(adjusted)
    assert window["baseDate"] == DATES[-2]
    assert window["current"] == (factor == 1)
    assert window["factorChangeDates"] == ([] if factor == 1 else [DATES[-1]])
    assert not windows["5"]["current"] and windows["5"]["adjustedReturnPct"] is None


@pytest.mark.parametrize("missing", ["price", "factor", "halted", "invalid"])
def test_missing_price_factor_or_trading_never_filled(missing):
    prices = [{"date": day, "close": 100, "vol": 100} for day in DATES]
    factors = [{"date": day, "adj_factor": 1} for day in DATES]
    if missing == "price": prices.pop()
    if missing == "factor": factors.pop()
    if missing == "halted": prices[-1]["vol"] = 0
    if missing == "invalid": factors[-1]["adj_factor"] = 0
    window = price_windows(prices, factors, DATES)["1"]
    assert not window["current"] and window["adjustedReturnPct"] is None
    assert window["missingDates"] == [DATES[-1]]


def test_factor_change_inside_window_not_just_endpoints():
    dates = [f"2026-09-{day:02}" for day in range(1, 22)]
    prices = [{"date": day, "close": 100, "vol": 100} for day in dates]
    factors = [{"date": day, "adj_factor": 2 if i == 10 else 1} for i, day in enumerate(dates)]
    window = price_windows(prices, factors, dates)["20"]
    assert window["rawReturnPct"] == window["adjustedReturnPct"] == 0
    assert not window["current"]
    assert window["factorChangeDates"] == dates[10:12]


@pytest.mark.asyncio
async def test_price_service_cache_and_failed_adjustment_downgrade(tmp_path):
    fail = False
    calls = []
    def handle(request):
        payload = json.loads(request.content); api = payload["api_name"]; calls.append(api)
        assert payload["params"]["end_date"] == "20261015"
        if api == "fund_adj" and fail: return httpx.Response(503)
        values = {"trade_cal": [[day.replace("-", ""), 1] for day in DATES],
            "fund_daily": [["588000.SH", day.replace("-", ""), 100 + i, 100] for i, day in enumerate(DATES)],
            "fund_adj": [["588000.SH", day.replace("-", ""), 1] for day in DATES]}
        return httpx.Response(200, json={"code": 0, "data": {"fields": payload["fields"].split(","), "items": values[api]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        service = ETFPriceService("test", CapitalHistoryStore(tmp_path / "price.sqlite"), client=client, today=date(2026, 10, 16))
        result = await service.price("588000.SH")
        assert result["windows"]["1"]["current"] and len(calls) == 3
        await service.price("588000.SH")
        assert len(calls) == 3
        fail = True
        result = await service.price("588000.SH", refresh=True)
        assert result["feeds"]["adjustment"]["usingSaved"]
        assert not result["windows"]["1"]["current"]
        assert result["windows"]["1"]["adjustedReturnPct"] is not None
        assert "更新未确认" in result["windows"]["1"]["reason"]
