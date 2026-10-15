import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover_history import TurnoverHistoryService, history_analysis


DAYS = [(date(2026, 9, 1) + timedelta(days=i)).isoformat() for i in range(21)]


def observations():
    rows = [{"date": day, "status": "ready", "amounts": {f"{i:06}.SZ": 100000 for i in range(1, 26)}} for day in DAYS]
    rows[-1]["amounts"] = {code: amount * 2 for code, amount in rows[-1]["amounts"].items()}
    rows[-1]["amounts"]["600000.SH"] = 1e9  # newly observed stock must not inflate fixed-universe volume
    return rows


def test_common_universe_prior_only_baseline_and_concentration():
    result = history_analysis(observations(), DAYS, 20, True)
    assert result["current"]
    assert result["commonCount"] == 25 and result["excludedLatest"] == 1
    assert result["summary"]["meanTurnoverYi"] == 25
    assert result["summary"]["relativeVolume"] == 2
    assert result["summary"]["percentilePct"] == 100
    assert result["summary"]["top20SharePct"] == 80
    assert result["summary"]["concentrationChangePp"] == 0


@pytest.mark.parametrize("case", ["missing", "failed", "calendar", "short"])
def test_incomplete_window_never_uses_available_only_average(case):
    rows = observations()
    if case == "missing": rows.pop(4)
    if case == "failed": rows[4]["status"] = "unavailable"
    result = history_analysis(rows, DAYS[:-1] if case == "short" else DAYS, 20, case != "calendar")
    assert not result["current"]
    assert result["summary"]["relativeVolume"] is None
    assert all(row["turnoverYi"] is None for row in result["points"])


def test_zero_baseline_no_ratio_and_thin_common_sample_no_confirmation():
    rows = observations()
    for row in rows:
        row["amounts"] = {code: 0 for code in row["amounts"]}
    result = history_analysis(rows, DAYS, 20, True)
    assert result["summary"]["meanTurnoverYi"] == 0
    assert result["summary"]["relativeVolume"] is None
    assert result["summary"]["concentrationChangePp"] is None
    rows[0]["amounts"] = {"000001.SZ": 0}
    assert not history_analysis(rows, DAYS, 20, True)["current"]


@pytest.mark.asyncio
async def test_bounded_batches_reuse_history_and_failed_refresh_does_not_confirm(tmp_path):
    calls, fail = [], False
    def handler(request):
        p = json.loads(request.content)
        fields = p["fields"].split(",")
        if p["api_name"] == "trade_cal":
            rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DAYS]
        else:
            calls.append(p["params"]["trade_date"])
            if fail: return httpx.Response(503)
            rows = [{"ts_code": f"{i:06}.SZ", "trade_date": p["params"]["trade_date"], "amount": 100000} for i in range(1, 26)]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(f) for f in fields] for row in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TurnoverHistoryService("test", CapitalHistoryStore(tmp_path / "test.sqlite"), client=client, today=date(2026, 9, 22))
        first = await service.history()
        assert first["completed"] == 8 and first["remaining"] == 13 and first["canContinue"]
        second = await service.history()
        assert second["completed"] == 16 and second["canContinue"]
        third = await service.history()
        assert third["current"] and not third["canContinue"]
        assert len(calls) == 21
        assert (await service.history())["current"]
        assert len(calls) == 21
        fail = True
        failed = await service.history(refresh=True)
        assert failed["failedDates"] == [DAYS[-1]]
        assert not failed["current"] and not failed["canContinue"]
        assert failed["summary"]["relativeVolume"] is None
