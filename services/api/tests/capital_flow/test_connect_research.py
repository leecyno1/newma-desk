import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.connect_research import ConnectResearchService, connect_point, connect_window
from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


def snapshot(day="2026-10-14", flag=1):
    return {"date": day, **{f"{exchange}-{side}": {"tradingDay": flag, "summary": {
        "Total Turnover": "300", "Buy Turnover": "200", "Sell Turnover": "100", "ETF Turnover": "10"}}
        for exchange in ("sse", "szse") for side in ("northbound", "southbound")}}


def test_units_net_direction_and_northbound_never_infers_buy_sell():
    north = connect_point(snapshot(), "2026-10-14", "northbound")
    south = connect_point(snapshot(), "2026-10-14", "southbound")
    assert north["turnoverYi"] == 6
    assert north["netBuyYi"] is None and north["buyYi"] is None
    assert south["buyYi"] == 4 and south["sellYi"] == 2 and south["netBuyYi"] == 2
    assert south["etfTurnoverYi"] == .2


def test_closed_is_distinct_from_missing_zero_and_amount_conflict():
    assert connect_point(snapshot(flag=0), "2026-10-14", "southbound")["status"] == "closed"
    data = snapshot(); data["szse-southbound"]["summary"].pop("Buy Turnover")
    assert connect_point(data, "2026-10-14", "southbound")["status"] == "unavailable"
    data = snapshot(); data["szse-southbound"]["summary"]["Total Turnover"] = "400"
    assert connect_point(data, "2026-10-14", "southbound")["status"] == "unavailable"
    data = snapshot()
    for key in ("sse-southbound", "szse-southbound"):
        data[key]["summary"].update({"Buy Turnover": "150", "Sell Turnover": "150"})
    assert connect_point(data, "2026-10-14", "southbound")["netBuyYi"] == 0


def test_window_excludes_official_closed_only_and_censors_streak():
    days = [(date(2026, 9, 1) + timedelta(days=n)).isoformat() for n in range(24)]
    rows = [{"date": day, "southbound": connect_point(snapshot(day), day, "southbound")} for day in days]
    rows[-3]["southbound"] = connect_point(snapshot(days[-3], 0), days[-3], "southbound")
    result = connect_window(rows, days, "southbound", 5)
    assert result["current"] and result["summary"]["netBuyYi"] == 10
    assert result["summary"]["streakDays"] == 5 and result["summary"]["streakCensored"]
    assert result["summary"]["latestVsPrior20"] == 1
    rows[-4]["southbound"]["status"] = "unavailable"
    failed = connect_window(rows, days, "southbound", 5)
    assert not failed["current"]
    assert failed["summary"]["netBuyYi"] is None
    assert failed["summary"]["latestVsPrior20"] is None
    assert failed["missingDates"] == [days[-4]]


def test_momentum_uses_weighted_intensity_and_non_overlapping_periods():
    days = [(date(2026, 9, 1) + timedelta(days=n)).isoformat() for n in range(10)]
    rows = [{"date": day, "southbound": {"date": day, "status": "ready", "turnoverYi": 100 if i < 5 else 200,
             "netBuyYi": 10, "buyYi": 55 if i < 5 else 105, "sellYi": 45 if i < 5 else 95}}
            for i, day in enumerate(days)]
    result = connect_window(rows, days, "southbound", 5)
    momentum = result["momentum"]
    assert momentum["current"] and momentum["netChangeYi"] == 0
    assert momentum["previous"]["end"] < momentum["recent"]["start"]
    assert momentum["recent"]["netIntensityPct"] == 5
    assert momentum["intensityChangePp"] == -5
    assert momentum["turnoverRatio"] == 2
    rows[-1]["southbound"].update(turnoverYi=600, buyYi=305, sellYi=295)
    weighted = connect_window(rows, days, "southbound", 5)["momentum"]
    assert weighted["recent"]["netIntensityPct"] == pytest.approx(50 / 1400 * 100)
    # A prior-period gap does not invalidate the latest five days, but must revoke comparison.
    rows[0]["southbound"]["status"] = "unavailable"
    result = connect_window(rows, days, "southbound", 5)
    assert result["current"] and not result["momentum"]["current"]
    assert result["momentum"]["netChangeYi"] is None
    assert result["momentum"]["intensityChangePp"] is None
    assert result["momentum"]["missingDates"] == [days[0]]


@pytest.mark.parametrize("direction", ["southbound", "northbound"])
def test_momentum_zero_baseline_and_insufficient_history(direction):
    days = [(date(2026, 9, 1) + timedelta(days=n)).isoformat() for n in range(10)]
    rows = [{"date": day, direction: {"date": day, "status": "ready", "turnoverYi": 0,
             "netBuyYi": 0 if direction == "southbound" else None}} for day in days]
    result = connect_window(rows, days, direction, 5)["momentum"]
    assert result["current"]
    assert result["turnoverRatio"] is None and result["intensityChangePp"] is None
    assert result["recent"]["netIntensityPct"] is None
    assert result["netChangeYi"] == (0 if direction == "southbound" else None)
    result = connect_window(rows[-5:], days[-5:], direction, 5)["momentum"]
    assert not result["current"] and result["previous"]["available"] == 0


@pytest.mark.asyncio
async def test_exact_official_date_never_falls_back_or_accepts_misdated_payload():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, text='var data = '+json.dumps([{"market": "SSE Southbound", "date": "2026-10-13", "tradingDay": 1, "content": []}]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await CapitalFlowService("")._fetch_hkex_connect(client, "2026-10-14", exact=True) == {}
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_bounded_fetch_cache_and_failed_refresh_revoke_confirmation(tmp_path, monkeypatch):
    calls, fail = [], False
    async def official(self, client, day, *, exact):
        assert exact
        calls.append(day)
        return {} if fail else snapshot(day)
    monkeypatch.setattr(CapitalFlowService, "_fetch_hkex_connect", official)
    async with httpx.AsyncClient() as client:
        service = ConnectResearchService(CapitalHistoryStore(tmp_path / "test.sqlite"), client=client, today=date(2026, 10, 15))
        first = await service.research()
        assert len(calls) == 6 and first["canContinue"]
        for _ in range(5):
            result = await service.research()
            if not result["canContinue"]: break
        assert result["remaining"] == 0 and result["windows"]["20"]["southbound"]["current"]
        count = len(calls)
        assert not (await service.research())["canContinue"]
        assert len(calls) == count
        fail = True
        failed = await service.research(refresh=True)
        assert failed["failedDates"] == ["2026-10-14"]
        assert not failed["windows"]["5"]["southbound"]["current"]
        assert failed["windows"]["5"]["southbound"]["points"][-1]["usingSaved"]
