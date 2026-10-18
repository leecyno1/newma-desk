from datetime import date
import json

import httpx
import pytest

from vibe_visualization_api.capital_flow.candidate_performance import performance_windows, CandidatePerformanceService
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = ["2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]


def sample():
    prices = [{"date": day, "open": 101 + i, "high": 112 + i, "low": 99 + i, "close": 100 + i, "vol": 100} for i, day in enumerate(DATES)]
    factors = [{"date": day, "adj_factor": 1} for day in DATES]
    benchmark = [{"date": day, "close": 1000 + i * 5} for i, day in enumerate(DATES)]
    return prices, factors, benchmark


def test_exact_sessions_benchmark_difference_and_t_plus_one():
    result = performance_windows(*sample(), DATES, DATES[0])
    assert result[0]["end"] == "2026-10-12"  # weekend is not a trading session
    assert result[0]["adjustedReturnPct"] == pytest.approx(1)
    assert result[0]["benchmarkReturnPct"] == pytest.approx(.5)
    assert result[0]["excessPp"] == pytest.approx(.5)
    assert result[0]["nextOpenReturnPct"] is None and result[0]["execution"] == "t-plus-one"
    assert result[1]["nextOpenReturnPct"] == pytest.approx((103 / 102 - 1) * 100)
    assert result[2]["end"] == DATES[5]


def test_adjustment_keeps_corporate_action_reference():
    prices, factors, benchmark = sample()
    for p, f in zip(prices[1:], factors[1:]):
        for key in ("open", "high", "low", "close"):
            p[key] /= 2
        f["adj_factor"] = 2
    result = performance_windows(prices, factors, benchmark, DATES, DATES[0])[1]
    assert result["rawReturnPct"] == pytest.approx(-48.5)
    assert result["adjustedReturnPct"] == pytest.approx(3)
    assert result["excessPp"] == pytest.approx(1.5)
    assert result["nextOpenReturnPct"] == pytest.approx((103 / 102 - 1) * 100)
    assert result["status"] == "review" and result["factorChangeDates"] == [DATES[1]]


@pytest.mark.parametrize("missing", ["price", "factor", "halted", "benchmark", "open", "one-price"])
def test_independent_gaps_and_execution_limits(missing):
    prices, factors, benchmark = sample()
    if missing == "price": prices.pop(2)
    if missing == "factor": factors.pop(2)
    if missing == "halted": prices[2]["vol"] = 0
    if missing == "benchmark": benchmark.pop(2)
    if missing == "open": prices[1].pop("open")
    if missing == "one-price": prices[1].update(open=101, high=101, low=101, close=101)
    windows = performance_windows(prices, factors, benchmark, DATES, DATES[0])
    window = windows[1]
    if missing in {"price", "factor", "halted"}:
        assert windows[0]["adjustedReturnPct"] is not None
        assert window["adjustedReturnPct"] is None and window["excessPp"] is None
        assert window["benchmarkReturnPct"] is not None
        assert window["nextOpenReturnPct"] is None
    elif missing == "benchmark":
        assert window["adjustedReturnPct"] is not None
        assert window["benchmarkReturnPct"] is None and window["excessPp"] is None
    else:
        assert window["adjustedReturnPct"] is not None
        assert window["nextOpenReturnPct"] is None and window["execution"] == "blocked"
    assert performance_windows(prices, factors, benchmark, DATES, DATES[-1])[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_service_cache_source_failure_and_invalid_date(tmp_path):
    fail = False
    calls = []
    prices, factors, benchmark = sample()
    def handle(request):
        payload = json.loads(request.content)
        api = payload["api_name"]
        calls.append(api)
        if api == "adj_factor" and fail:
            return httpx.Response(503)
        data = {"trade_cal": [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DATES],
                "daily": prices, "adj_factor": factors, "index_daily": benchmark}[api]
        fields = payload["fields"].split(",")
        rows = [{**row, "trade_date": row.get("date", "").replace("-", ""), "ts_code": payload["params"].get("ts_code")} for row in data]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        service = CandidatePerformanceService("test", CapitalHistoryStore(tmp_path / "data.db"), client=client, today=date(2026, 10, 17))
        result = await service.research("000001.SZ", DATES[0])
        assert result["windows"][1]["adjustedReturnPct"] == pytest.approx(3)
        await service.research("000001.SZ", DATES[0])
        assert len(calls) == 4
        fail = True
        result = await service.research("000001.SZ", DATES[0], refresh=True)
        assert result["feeds"]["adjustment"]["usingSaved"]
        assert result["windows"][1]["adjustedReturnPct"] is None
        assert result["windows"][1]["benchmarkReturnPct"] is not None
        with pytest.raises(ValueError):
            await service.research("000001.SZ", "2026-10-10")


@pytest.mark.asyncio
async def test_benchmark_selection_reuses_prices_and_isolates_index_caches(tmp_path):
    calls = []
    index_mode = "ready"
    prices, factors, benchmark = sample()

    def handle(request):
        payload = json.loads(request.content)
        api, symbol = payload["api_name"], payload["params"].get("ts_code")
        calls.append((api, symbol))
        if api == "index_daily" and index_mode == "failed":
            return httpx.Response(503)
        data = {"trade_cal": [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DATES],
                "daily": prices, "adj_factor": factors, "index_daily": benchmark}[api]
        if api == "index_daily" and symbol == "000852.SH":
            data = [{"date": day, "close": 1000 - i * 10} for i, day in enumerate(DATES)]
        fields = payload["fields"].split(",")
        rows = [{**row, "trade_date": row.get("date", "").replace("-", ""),
                 "ts_code": "000300.SH" if api == "index_daily" and index_mode == "wrong-code" else symbol} for row in data]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in rows]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        service = CandidatePerformanceService("test", CapitalHistoryStore(tmp_path / "data.db"), client=client, today=date(2026, 10, 17))
        with pytest.raises(ValueError, match="不支持该基准"):
            await service.research("000001.SZ", DATES[0], benchmark_code="UNKNOWN")
        assert not calls
        original = await service.research("000001.SZ", DATES[0])
        selected = await service.research("000001.SZ", DATES[0], benchmark_code="000852.SH")
        assert len(calls) == 5 and calls[-1] == ("index_daily", "000852.SH")
        assert selected["benchmark"]["code"] == "000852.SH"
        assert len(selected["benchmarkOptions"]) == 5
        assert selected["windows"][1]["adjustedReturnPct"] == original["windows"][1]["adjustedReturnPct"]
        assert selected["windows"][1]["benchmarkReturnPct"] == pytest.approx(-3)
        assert selected["windows"][1]["excessPp"] == pytest.approx(6)
        restored = await service.research("000001.SZ", DATES[0])
        assert len(calls) == 5 and restored["windows"] == original["windows"]
        index_mode = "wrong-code"
        mismatched = await service.research("000001.SZ", DATES[0], benchmark_code="000852.SH", refresh=True)
        assert mismatched["windows"][1]["benchmarkReturnPct"] is None
        assert mismatched["windows"][1]["excessPp"] is None
        assert mismatched["windows"][1]["adjustedReturnPct"] == pytest.approx(3)
        index_mode = "failed"
        failed = await service.research("000001.SZ", DATES[0], benchmark_code="000852.SH", refresh=True)
        assert failed["feeds"]["benchmark"]["usingSaved"]
        assert failed["windows"][1]["benchmarkReturnPct"] is None
        assert failed["windows"][1]["excessPp"] is None
        assert failed["windows"][1]["adjustedReturnPct"] == pytest.approx(3)
