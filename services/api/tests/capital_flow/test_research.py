import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow import research as module
from vibe_visualization_api.capital_flow.research import (
    CapitalResearchService, baseline, etf_analysis, margin_analysis, window_sum,
)
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = ["2026-10-09", "2026-10-12", "2026-10-13"]


def test_etf_units_and_price_not_flow():
    result = etf_analysis("510300.SH", "ETF", "宽基", [
        {"date": DATES[0], "sharesWan": 10000, "nav": 4},
        {"date": DATES[1], "sharesWan": 10000, "nav": 4.2},
        {"date": DATES[2], "sharesWan": 11000, "nav": 4.3},
    ], DATES)
    assert result["points"][1]["flowYi"] == 0
    assert result["points"][1]["navChangePct"] == pytest.approx(5)
    assert result["summary"]["flow1dYi"] == .43
    assert result["summary"]["flow5dYi"] is None


def test_etf_missing_session_and_split_are_not_flows():
    result = etf_analysis("ETF", "ETF", "宽基", [
        {"date": DATES[0], "sharesWan": 100, "nav": 4},
        {"date": DATES[2], "sharesWan": 110, "nav": 4},
    ], DATES)
    assert result["latest"]["flowYi"] is None
    assert result["status"] == "partial"
    result = etf_analysis("ETF", "ETF", "宽基", [
        {"date": DATES[1], "sharesWan": 100, "nav": 4},
        {"date": DATES[2], "sharesWan": 200, "nav": 2},
    ], DATES)
    assert result["latest"]["suspectedSplit"] is True
    assert result["latest"]["flowYi"] is None
    assert "公告核验" in result["note"]
    assert result["summary"]["strength"]["1"]["strengthPct"] is None
    assert result["summary"]["strength"]["1"]["splitDates"] == [DATES[-1]]


def test_etf_strength_uses_fixed_opening_assets_and_is_scale_invariant():
    sessions = ["2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]
    rows = [{"date": day, "sharesWan": 10000 + i * 1000, "nav": 1 + i / 10} for i, day in enumerate(sessions)]
    result = etf_analysis("ETF", "ETF", "宽基", rows, sessions)["summary"]["strength"]
    window = result["5"]
    assert window["baseDate"] == sessions[0] and window["start"] == sessions[1]
    assert window["baseAssetsYi"] == 1
    assert window["flowYi"] == pytest.approx(.65)
    assert window["strengthPct"] == 65
    assert window["available"] == window["expected"] == 5 and window["current"]
    large = etf_analysis("ETF", "ETF", "宽基", [{**row, "sharesWan": row["sharesWan"] * 100} for row in rows], sessions)
    assert large["summary"]["strength"]["5"]["strengthPct"] == window["strengthPct"]
    assert large["summary"]["strength"]["5"]["flowYi"] == 65
    assert result["20"]["strengthPct"] is None and not result["20"]["current"]
    unchanged = etf_analysis("ETF", "ETF", "宽基", [{**row, "sharesWan": 10000} for row in rows], sessions)
    assert unchanged["summary"]["strength"]["5"]["strengthPct"] == 0
    assert unchanged["summary"]["strength"]["5"]["current"]


@pytest.mark.parametrize("field,value", [("nav", None), ("nav", 0), ("sharesWan", 0), ("sharesWan", -1)])
def test_etf_strength_invalid_opening_assets_are_not_zero(field, value):
    rows = [{"date": DATES[1], "sharesWan": 10000, "nav": 1, field: value},
            {"date": DATES[2], "sharesWan": 11000, "nav": 1}]
    window = etf_analysis("ETF", "ETF", "宽基", rows, DATES)["summary"]["strength"]["1"]
    assert window["strengthPct"] is None and window["baseAssetsYi"] is None
    assert not window["current"] and "期初" in window["reason"]


def test_etf_strength_missing_middle_day_and_small_amount_precision():
    sessions = [f"2026-10-{day:02}" for day in range(9, 15)]
    rows = [{"date": day, "sharesWan": 100 + i, "nav": .001} for i, day in enumerate(sessions)]
    result = etf_analysis("ETF", "ETF", "宽基", rows, sessions)
    assert result["summary"]["flow5dYi"] == 0  # Legacy display rounds to 4 decimals.
    assert result["summary"]["strength"]["5"]["strengthPct"] == 5  # Not computed from rounded display.
    missing = etf_analysis("ETF", "ETF", "宽基", rows[:2] + rows[3:], sessions)["summary"]["strength"]["5"]
    assert missing["strengthPct"] is None and not missing["current"]
    assert missing["missingDates"] == sessions[2:4]


def test_market_margin_requires_three_exchanges():
    rows = [{"date": DATES[-1], "exchange_id": exchange, "rzye": 10e8,
             "rzmre": 3e8, "rzche": 2e8} for exchange in module.EXCHANGES]
    result = margin_analysis(rows, DATES)
    assert result["latest"]["balanceYi"] == 30
    assert result["summary"]["net1dYi"] == 3
    incomplete = margin_analysis(rows[:2], DATES)
    assert incomplete["latest"]["balanceYi"] is None
    assert incomplete["summary"]["net1dYi"] is None
    assert len(incomplete["latest"]["byExchange"]) == 2


def test_history_windows_and_baseline_report_coverage():
    sessions = [f"2026-09-{i:02}" for i in range(1, 23)]
    points = [{"date": day, "flow": index} for index, day in enumerate(sessions)]
    assert window_sum(points, sessions, "flow", 5) == 95
    assert window_sum(points[:-2] + points[-1:], sessions, "flow", 5) is None
    assert baseline(points, sessions, "flow") == {"samples": 21, "expected": 21, "percentile": 100, "mean": 10}
    assert baseline(points[:4] + points[-1:], sessions, "flow")["percentile"] is None


def api_result(fields, items):
    return httpx.Response(200, json={"code": 0, "data": {"fields": fields.split(","), "items": items}})


@pytest.mark.asyncio
async def test_permission_fallback_join_cache_and_failed_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ETF_SAMPLE", (("510300.SH", "沪深300ETF", "宽基"),))
    calls = []
    failing = False

    def handler(request):
        payload = json.loads(request.content)
        api = payload["api_name"]
        calls.append(api)
        assert payload["params"]["end_date"] == "20261013"
        if api == "etf_share_size":
            return httpx.Response(200, json={"code": 40203, "msg": "没有接口访问权限"})
        if failing:
            return httpx.Response(503)
        if api == "trade_cal":
            return api_result("cal_date,is_open", [[day.replace("-", ""), 1] for day in DATES])
        if api == "margin":
            return api_result("trade_date,exchange_id,rzye,rzmre,rzche", [
                [day.replace("-", ""), exchange, 10e8, 3e8, 2e8]
                for day in DATES for exchange in module.EXCHANGES])
        if api == "fund_share":
            return api_result("ts_code,trade_date,fd_share", [["510300.SH", "20261012", 10000], ["510300.SH", "20261013", 11000]])
        if api == "fund_nav":
            # Same NAV date revisions must retain the more recently announced value.
            return api_result("ts_code,ann_date,nav_date,unit_nav", [
                ["510300.SH", "20261013", "20261013", 4.3],
                ["510300.SH", "20261012", "20261013", 4],
                ["510300.SH", "20261012", "20261012", 4.2]])
        raise AssertionError(api)

    store = CapitalHistoryStore(tmp_path / "capital.sqlite")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = CapitalResearchService("test-token", store, client=client, today=date(2026, 10, 14))
        first = await service.research()
        assert first["expectedDate"] == DATES[-1]
        assert first["coverage"]["primaryStatus"] == "permission-denied"
        assert first["etfs"][0]["source"] == "Tushare fund_share + fund_nav"
        assert first["etfs"][0]["latest"]["nav"] == 4.3
        assert first["etfs"][0]["summary"]["flow1dYi"] == .43
        assert first["leverage"]["latest"]["balanceYi"] == 30
        count = len(calls)
        again = await CapitalResearchService("test-token", store, client=client, today=date(2026, 10, 14)).research()
        assert len(calls) == count
        assert again["leverage"]["latest"] == first["leverage"]["latest"]
        failing = True
        saved = await service.research(refresh=True)
        assert saved["etfs"][0]["usingSaved"] is True
        assert saved["etfs"][0]["status"] == "partial"
        assert saved["leverage"]["usingSaved"] is True
        assert saved["leverage"]["latest"]["balanceYi"] == 30
        assert saved["calendar"]["status"] == "upstream-error"
        assert first["etfs"][0]["summary"]["strength"]["1"]["current"]
        window = saved["etfs"][0]["summary"]["strength"]["1"]
        assert window["strengthPct"] is not None and not window["current"]
        assert "更新未确认" in window["reason"]


@pytest.mark.asyncio
async def test_missing_nav_not_borrowed_from_other_date(tmp_path):
    def handler(request):
        payload = json.loads(request.content)
        if payload["api_name"] == "fund_share":
            return api_result("trade_date,fd_share", [["20261012", 100], ["20261013", 110]])
        if payload["api_name"] == "fund_nav":
            return api_result("nav_date,ann_date,unit_nav", [["20261012", "20261012", 4]])
        return api_result("cal_date,is_open", [["20261012", 1], ["20261013", 1]])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CapitalResearchService("test", CapitalHistoryStore(tmp_path / "capital.sqlite"), client=client,
                                              today=date(2026, 10, 14)).research()
    assert all(row["summary"]["flow1dYi"] is None for row in result["etfs"])


@pytest.mark.asyncio
async def test_no_token_does_not_call_network(tmp_path):
    def handler(request):
        raise AssertionError("No outbound request without a token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CapitalResearchService("", CapitalHistoryStore(tmp_path / "capital.sqlite"), client=client).research()
    assert result["coverage"]["etfAvailable"] == 0
    assert result["expectedDate"] is None
    assert result["leverage"]["status"] == "unavailable"
