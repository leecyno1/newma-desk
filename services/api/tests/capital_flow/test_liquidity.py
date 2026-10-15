import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.liquidity import LiquidityResearchService, credit_analysis, month_shift, rate_analysis, transmission
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


def feed(rows, **changes):
    return {"rows": rows, "status": "ready", "reason": "", "usingSaved": False, **changes}


def rate_feeds():
    days = [(date(2026, 9, 15) + timedelta(days=i)).isoformat() for i in range(30)]
    return {
        "dr007": feed([{"date": day, "ts_code": "DR007.IB", "weight": 1 + i / 100, "weight_r": 99} for i, day in enumerate(days)]),
        "r007": feed([{"date": day, "ts_code": "R007.IB", "weight": 1.2 + i / 100} for i, day in enumerate(days)]),
        "shibor": feed([{"date": day, "1w": 1.3, "3m": 1.5} for day in days]),
    }


def monthly_feeds():
    months = [month_shift("2025-07", i) for i in range(15)]
    return (feed([{"date": month + "-01", "m1_yoy": 3, "m2_yoy": 7} for month in months]),
            feed([{"date": month + "-01", "inc_month": 100 + i, "stk_endval": 400 + i} for i, month in enumerate(months)]))


def test_rate_units_same_date_spread_and_observation_changes():
    data = rate_analysis(rate_feeds(), date(2026, 10, 15))
    rates = {row["id"]: row for row in data["series"]}
    assert rates["dr007"]["value"] == 1.29  # weight, not weight_r or close
    assert rates["dr007"]["change5Bp"] == 5
    assert rates["dr007"]["change20Bp"] == 20
    assert rates["spreadBp"]["value"] == 20
    assert rates["spreadBp"]["change5Bp"] == 0
    assert rates["dr007"]["baselineSamples"] == 29
    assert rates["dr007"]["percentile"] == 100


def test_missing_same_date_does_not_forward_fill_or_join_across_gap():
    feeds = rate_feeds()
    feeds["r007"]["rows"].pop(-1)
    feeds["dr007"]["rows"].pop(-3)
    data = rate_analysis(feeds, date(2026, 10, 15))
    rates = {row["id"]: row for row in data["series"]}
    assert data["points"][-1]["spreadBp"] is None
    assert rates["spreadBp"]["asOf"] == "2026-10-13"
    assert not rates["spreadBp"]["current"]
    assert rates["dr007"]["change5Bp"] is None
    assert rates["r007"]["current"] is False


def test_failed_or_stale_sources_cannot_drive_current_direction():
    feeds = rate_feeds()
    feeds["dr007"].update(status="upstream-error", usingSaved=True)
    rates = rate_analysis(feeds, date(2026, 10, 15))
    credit = credit_analysis(*monthly_feeds(), date(2026, 10, 15))
    directions = {row["id"]: row["signal"] for row in transmission(rates, credit)}
    assert directions["funding"] == directions["spread"] == "unknown"
    assert all(not row["current"] for row in rate_analysis(rate_feeds(), date(2026, 11, 15))["series"])


def test_credit_units_seasonal_matching_and_no_cumulative_sum():
    result = credit_analysis(*monthly_feeds(), date(2026, 10, 15))
    latest = result["social"]
    assert latest["socialFlowYi"] == 114
    assert latest["socialPriorYearYi"] == 102
    assert latest["socialYoYDiffYi"] == 12
    assert latest["flow3mYi"] == 113 + 112 + 114
    assert latest["flow3mPriorYearYi"] == 100 + 101 + 102
    assert latest["flow3mYoYDiffYi"] == 36
    assert latest["socialStockWanYi"] == 414
    assert latest["socialStockYoy"] == pytest.approx((414 / 402 - 1) * 100, abs=1e-4)


def test_missing_month_is_visible_and_stops_three_month_comparison():
    money, social = monthly_feeds()
    money["rows"] = [row for row in money["rows"] if row["date"] != "2026-08-01"]
    social["rows"] = [row for row in social["rows"] if row["date"] != "2026-08-01"]
    result = credit_analysis(money, social, date(2026, 10, 15))
    missing = next(row for row in result["points"] if row["month"] == "2026-08")
    assert missing["socialFlowYi"] is None
    assert result["social"]["flow3mYi"] is None
    assert result["social"]["flow3mYoYDiffYi"] is None
    assert result["money"]["gapChangePp"] is None


def test_money_definition_break_and_conflicting_credit_evidence():
    result = credit_analysis(feed([
        {"date": "2024-12-01", "m1_yoy": -1, "m2_yoy": 7},
        {"date": "2025-01-01", "m1_yoy": 3, "m2_yoy": 7},
    ]), feed([]), date(2026, 10, 15))
    assert result["points"][0]["m1Yoy"] is None
    assert result["money"]["m1ChangePp"] is None
    assert not result["money"]["current"]
    result = credit_analysis(*monthly_feeds(), date(2026, 10, 15))
    result["social"].update(stockYoyChangePp=-.2, flow3mYoYDiffYi=30)
    signals = transmission(rate_analysis(rate_feeds(), date(2026, 10, 15)), result)
    assert signals[-1]["signal"] == "mixed"
    assert "背离" in signals[-1]["implication"]


@pytest.mark.asyncio
async def test_service_monthly_window_cache_and_failed_refresh_preserve_history(tmp_path):
    calls = []
    failing = False
    def handler(request):
        q = json.loads(request.content)
        calls.append(q)
        if failing:
            return httpx.Response(200, json={"code": 40203, "msg": "权限不足"})
        api = q["api_name"]
        if api in {"cn_m", "sf_month"}:
            assert q["params"]["start_m"] == "202407"
            assert q["params"]["end_m"] == "202609"
            fields = ["month", "m1_yoy", "m2_yoy"] if api == "cn_m" else ["month", "inc_month", "stk_endval"]
            rows = [["202609", 3, 7], ["202610", 999, 999]] if api == "cn_m" else [["202609", 35000, 468]]
        elif api == "repo_daily":
            fields, rows = ["ts_code", "trade_date", "weight"], [[q["params"]["ts_code"], "20261014", 1.4]]
        else:
            fields, rows = ["date", "1w", "3m"], [["20261014", 1.3, 1.4]]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": rows}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = LiquidityResearchService("test-token", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client, today=date(2026, 10, 15))
        result = await service.research()
        assert result["credit"]["money"]["month"] == "2026-09"
        assert result["credit"]["social"]["socialStockWanYi"] == 468
        assert result["operations"]["netYi"] is None
        assert len(calls) == 5
        await service.research()
        assert len(calls) == 5
        failing = True
        result = await service.research(refresh=True)
        assert all(feed["usingSaved"] and feed["status"] == "permission-denied" for feed in result["feeds"])
        assert result["credit"]["social"]["socialFlowYi"] == 35000
        assert not result["credit"]["social"]["current"]
        assert all(row["signal"] == "unknown" for row in result["transmission"])


@pytest.mark.asyncio
async def test_route_uses_resolved_settings_token(tmp_path, monkeypatch):
    from vibe_visualization_api.capital_flow.routes import get_liquidity_research
    from vibe_visualization_api.config import Settings
    async def research(service, *, refresh):
        assert service.token == "settings-only-test-token"
        return {"refresh": refresh}
    monkeypatch.setattr(LiquidityResearchService, "research", research)
    settings = Settings(tushare_token="settings-only-test-token", database_path=tmp_path / "test.sqlite", _env_file=None)
    assert await get_liquidity_research(True, settings) == {"refresh": True}
