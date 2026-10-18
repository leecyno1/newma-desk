import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.sentiment import breadth_history
from vibe_visualization_api.capital_flow.turnover_history import DATASET, TurnoverHistoryService
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DAYS = [(date(2026, 9, 1) + timedelta(days=i)).isoformat() for i in range(20)]


def observations():
    return [{"date": day, "status": "ready", "breadthStatus": "ready",
             "returns": {f"{i:06}.SZ": (1 if i < (15 if index >= 15 else 10) else -1) for i in range(20)}}
            for index, day in enumerate(DAYS)]


def test_common_sample_and_nonoverlapping_five_day_comparison():
    rows = observations()
    rows[-1]["returns"]["600000.SH"] = 30  # new security must not inflate the last day
    result = breadth_history(rows, DAYS, 20, True)
    assert result["current"] and result["commonCount"] == 20
    assert result["points"][-1]["excludedCount"] == 1
    assert result["summary"] == {"latestUpRatioPct": 75, "latestChangePp": 0,
                                 "mean5Pct": 75, "previous5Pct": 50, "change5Pp": 25, "aboveHalfDays": 5}


@pytest.mark.parametrize("case", ["missing", "failed", "calendar", "short", "legacy", "thin"])
def test_gaps_and_unverified_calendar_never_make_a_trend(case):
    rows = observations()
    if case == "missing": rows.pop(4)
    if case == "failed": rows[4]["status"] = "unavailable"
    if case == "legacy": rows[4].pop("breadthStatus")
    if case == "thin": rows[4]["returns"] = {"000001.SZ": 1}
    result = breadth_history(rows, DAYS[:-1] if case == "short" else DAYS, 20, case != "calendar")
    assert not result["current"]
    assert result["summary"]["mean5Pct"] is None
    assert all(row["upRatioPct"] is None for row in result["points"])


def test_flat_and_zero_participation_are_valid():
    rows = observations()
    for row in rows:
        row["returns"] = {code: 0 for code in row["returns"]}
    result = breadth_history(rows, DAYS, 20, True)
    assert result["current"] and result["summary"]["latestUpRatioPct"] == 0
    assert result["summary"]["change5Pp"] == 0


@pytest.mark.asyncio
async def test_upgrade_existing_amount_only_history_in_bounded_batches(tmp_path):
    store = CapitalHistoryStore(tmp_path / "history.sqlite")
    store.save(DATASET, "CN", [{"date": day, "status": "ready", "amounts": {"000001.SZ": 10}}
                              for day in DAYS], start=DAYS[0], end=DAYS[-1], status="ready", reason="", received_at="2026-09-21T00:00:00+00:00")
    calls, fail = [], False
    def handler(request):
        p = json.loads(request.content)
        fields = p["fields"].split(",")
        if p["api_name"] == "trade_cal":
            rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DAYS]
        else:
            calls.append(p["params"]["trade_date"])
            if fail: return httpx.Response(503)
            rows = [{"ts_code": f"{i:06}.SZ", "trade_date": p["params"]["trade_date"],
                     "amount": 100, "close": 10, "pct_chg": 1 if i < 10 else 0} for i in range(20)]
            rows.extend([{"ts_code": "600001.SH", "trade_date": p["params"]["trade_date"], "amount": 0, "close": 10, "pct_chg": 0},
                         {"ts_code": "600002.SH", "trade_date": p["params"]["trade_date"], "amount": 100, "close": 10, "pct_chg": None}])
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(f) for f in fields] for row in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TurnoverHistoryService("test", store, client=client, today=date(2026, 9, 21))
        assert (await service.history(include_breadth=True))["completed"] == 8
        assert (await service.history(include_breadth=True))["completed"] == 16
        result = await service.history(include_breadth=True)
        assert result["current"] and result["commonCount"] == 20
        assert len(calls) == 20 and result["summary"]["latestUpRatioPct"] == 50
        assert (await service.history(include_breadth=True))["current"]
        assert len(calls) == 20
        fail = True
        result = await service.history(include_breadth=True, refresh=True)
        assert result["missingDates"] == [DAYS[-1]]
        assert result["failedDates"] == [DAYS[-1]]
        assert not result["current"] and not result["canContinue"]
        assert result["summary"]["latestUpRatioPct"] is None
