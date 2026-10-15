import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow.supply import CapitalSupplyService, capacity_analysis, supply_events
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


def test_repurchase_stage_units_no_cumulative_total():
    rows = [{"ts_code": "600519.SH", "ann_date": "20261013", "end_date": "20261012",
             "proc": "实施", "amount": 2e8, "vol": 20000},
            {"ts_code": "600519.SH", "ann_date": "20261001", "proc": "股东大会通过", "amount": 3e8},
            {"ts_code": "600519.SH", "ann_date": "20260901", "proc": "未知阶段", "amount": None}]
    events, removed = supply_events("repurchase", [*rows, rows[0]], "600519.SH", "2026-10-14")
    assert removed == 1 and len(events) == 3
    assert events[0]["stage"] == "实施进展"
    assert events[0]["amountYi"] == 2 and events[0]["sharesWan"] == 2
    assert events[1]["stage"] == "计划" and events[1]["sharesWan"] is None
    assert events[2]["stage"] == "阶段待核验" and events[2]["amountYi"] is None


def test_holder_intervals_unknown_stage_and_no_cash_estimation():
    row = {"ts_code": "300308.SZ", "ann_date": "20261013", "holder_name": "甲", "in_de": "DE",
           "change_vol": 5500000, "change_ratio": .4975, "avg_price": 521.73,
           "begin_date": "20251120", "close_date": "20261012"}
    events, _ = supply_events("stk_holdertrade", [row, {**row, "holder_name": "乙", "close_date": None}], "300308.SZ", "2026-10-14")
    known = next(item for item in events if item["holder"] == "甲")
    unknown = next(item for item in events if item["holder"] == "乙")
    assert known["sharesWan"] == 550 and known["amountYi"] is None
    assert known["stage"] == "区间披露·待核验" and known["eventDate"] == "2026-10-12"
    assert unknown["stage"] == "阶段待核验"


def test_future_unlock_revisions_and_unknown_announcement():
    row = {"ts_code": "300308.SZ", "ann_date": "20261001", "float_date": "20261201",
           "holder_name": "甲", "share_type": "股权激励", "float_share": 10000, "float_ratio": .1}
    events, removed = supply_events("share_float", [row, {**row, "ann_date": "20261013", "float_share": 9000},
        {**row, "ann_date": "20261015"}, {**row, "holder_name": "乙", "ann_date": None},
        {**row, "ts_code": "600519.SH"}], "300308.SZ", "2026-10-14")
    assert len(events) == 3 and removed == 0
    assert sum(item["superseded"] for item in events) == 1
    assert all(item["stage"] == "待解禁" for item in events)
    assert all(item["amountYi"] is None for item in events)


@pytest.mark.asyncio
async def test_preserve_same_day_events_future_dates_cache_failures_and_successful_empty(tmp_path):
    calls = []
    mode = "ready"
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if mode == "fail":
            return httpx.Response(503)
        api = payload["api_name"]
        if api == "share_float":
            assert payload["params"]["end_date"] == "20270112"
            rows = [{"ts_code": "300308.SZ", "ann_date": "20261001", "float_date": "20261201", "holder_name": holder,
                     "float_share": 10000, "share_type": "股权激励"} for holder in ["甲", "乙"]]
        elif api == "stk_holdertrade":
            assert payload["params"]["end_date"] == "20261014"
            rows = [{"ts_code": "300308.SZ", "ann_date": "20261013", "holder_name": holder, "in_de": "DE"} for holder in ["甲", "乙"]]
        else:
            rows = []
        fields = payload["fields"].split(",")
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields,
            "items": [] if mode == "empty" else [[row.get(field) for field in fields] for row in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = CapitalSupplyService("test", CapitalHistoryStore(tmp_path / "capital.sqlite"), client=client, today=date(2026, 10, 14))
        first = await service.research("300308")
        assert first["aggregateSafe"] is False and first["symbol"] == "300308.SZ"
        assert [feed["count"] for feed in first["feeds"]] == [0, 2, 2]
        cached = await service.research("300308")
        assert len(calls) == 5 and cached["feeds"][2]["count"] == 2
        mode = "fail"
        saved = await service.research("300308", refresh=True)
        assert saved["feeds"][2]["usingSaved"] is True
        assert saved["feeds"][2]["status"] == "upstream-error"
        mode = "empty"
        empty = await service.research("300308", refresh=True)
        assert all(feed["count"] == 0 and feed["status"] == "empty" and not feed["usingSaved"] for feed in empty["feeds"])
        second = await service.research("920093")
        assert second["symbol"] == "920093.BJ" and not any(feed["items"] for feed in second["feeds"])


def test_capacity_units_and_missing_or_failed_window():
    dates = [f"2026-09-{index:02d}" for index in range(1, 21)]
    rows = [{"date": day, "vol": 10000, "amount": 30000} for day in dates]
    result = capacity_analysis(rows, dates, True)
    assert result["averageVolumeWan"] == 100 and result["averageTurnoverYi"] == .3
    assert result["participationPct"] == 5
    assert capacity_analysis(rows[:-1], dates, True)["averageVolumeWan"] is None
    assert capacity_analysis(rows, dates, False)["averageTurnoverYi"] is None
