import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.security import SecurityResearchService, observations, security_analysis
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = [(date(2026, 7, 1) + timedelta(days=i)).isoformat() for i in range(90)]


def history():
    flows = [{"date": day, "net_amount": 10000, "buy_lg_amount": 6000, "buy_elg_amount": 4000} for day in DATES]
    daily = [{"date": day, "amount": 200000, "close": 100 - index * .1} for index, day in enumerate(DATES)]
    factors = [{"date": day, "adj_factor": 1} for day in DATES]
    margins = [{"date": day, "rzye": (10 + index) * 1e8, "rzmre": 2e8, "rzche": 1e8} for index, day in enumerate(DATES)]
    return flows, daily, factors, margins


def test_order_units_weighted_share_and_margin_reconciliation():
    result = security_analysis(*history(), DATES)
    assert result["order"]["net1dYi"] == 1
    assert result["order"]["net5dYi"] == 5
    assert result["order"]["net20dYi"] == 20
    assert result["order"]["share5dPct"] == 50
    assert result["order"]["streak"] == {"direction": "in", "days": 90}
    assert result["leverage"]["net5dYi"] == 5
    assert result["leverage"]["balanceChange5dYi"] == 5
    assert result["leverage"]["reconciliationChecked"] == 20
    assert result["leverage"]["reconciliationConflicts"] == 0
    assert result["order"]["baseline"]["samples"] == 60


def test_ex_rights_adjusted_price_not_false_divergence():
    flows, daily, factors, margins = history()
    for index in range(69, 90):
        daily[index]["close"] = 100 if index < 88 else 50
        factors[index]["adj_factor"] = 1 if index < 88 else 2
    result = security_analysis(flows, daily, factors, margins, DATES)
    assert result["price"]["change5dPct"] == 0
    assert result["price"]["change20dPct"] == 0
    assert result["price"]["factorChanges20d"] == 1
    assert result["points"][-2]["adjustedPct"] == 0


def test_missing_session_breaks_windows_price_and_streak():
    rows = history()
    for row in rows:
        row.pop(-2)
    result = security_analysis(*rows, DATES)
    assert result["order"]["net1dYi"] == 1
    assert result["order"]["net5dYi"] is None
    assert result["order"]["streak"]["days"] == 1
    assert result["price"]["change5dPct"] is None
    assert result["leverage"]["balanceChange5dYi"] is None
    assert result["points"][-1]["marginResidualYuan"] is None


def test_both_window_endpoints_are_required_for_price():
    rows = history()
    rows[2].pop(-6)
    result = security_analysis(*rows, DATES)
    assert result["price"]["change5dPct"] is None
    assert result["order"]["net5dYi"] == 5


def test_fallback_uses_large_order_difference_not_total_moneyflow():
    flows = [{"date": DATES[-1], "buy_lg_amount": 10000, "sell_lg_amount": 5000,
              "buy_elg_amount": 3000, "sell_elg_amount": 1000, "net_mf_amount": 90000000}]
    result = security_analysis(flows, [], [], [], DATES, source="moneyflow")
    assert result["order"]["net1dYi"] == .7
    assert result["order"]["share1dPct"] is None
    assert result["leverage"]["net1dYi"] is None


def test_observations_need_sources_and_margin_conflicts_remain_visible():
    rows = history()
    rows[3][-1]["rzye"] += 100
    result = security_analysis(*rows, DATES)
    feeds = {key: {"status": "ready", "usingSaved": False} for key in ("orders", "daily", "factors", "margin")}
    reviews = observations(result, feeds, True)
    assert reviews[0]["title"] == "下跌伴随大额订单净买入"
    assert reviews[1]["title"] == "下跌期间融资余额增加"
    assert reviews[2]["id"] == "margin-conflict"
    feeds["orders"]["usingSaved"] = True
    assert observations(result, feeds, True)[0]["title"] == "资金价格对照待核验"
    assert observations(result, feeds, False)[0]["title"] == "资金价格对照待核验"


@pytest.mark.asyncio
async def test_service_fallback_failure_cache_and_shared_required_fields(tmp_path):
    calls, failing = [], False
    rows_by_api = dict(zip(("moneyflow_dc", "daily", "adj_factor", "margin_detail"), history()))
    def handler(request):
        payload = json.loads(request.content)
        api = payload["api_name"]
        calls.append(api)
        if failing:
            return httpx.Response(503)
        if api == "moneyflow_dc":
            return httpx.Response(200, json={"code": 40203, "msg": "没有接口访问权限"})
        if api == "trade_cal":
            source = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DATES]
        elif api == "moneyflow":
            source = [{"ts_code": "600519.SH", "trade_date": day.replace("-", ""), "buy_lg_amount": 10000,
                       "sell_lg_amount": 5000, "buy_elg_amount": 3000, "sell_elg_amount": 1000} for day in DATES]
        else:
            source = [{**row, "ts_code": "600519.SH", "trade_date": row["date"].replace("-", "")} for row in rows_by_api[api]]
        fields = payload["fields"].split(",")
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in source]}})

    store = CapitalHistoryStore(tmp_path / "history.sqlite")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SecurityResearchService("test", store, client=client, today=date(2026, 9, 30))
        # Capacity's reduced-field cache must not be used as the price dataset.
        await service._dataset(client, "daily", "600519.SH", {"ts_code": "600519.SH"}, "ts_code,trade_date,vol,amount")
        first = await service.research("600519")
        assert calls.count("daily") == 2
        assert first["source"] == "Tushare moneyflow"
        assert first["fallbackReason"] == "moneyflow_dc 接口权限不足"
        assert first["order"]["net5dYi"] == 3.5
        assert first["price"]["change5dPct"] is not None
        await service._dataset(client, "daily", "600519.SH", {"ts_code": "600519.SH"}, "ts_code,trade_date,vol,amount", refresh=True)
        price_rows, _ = store.read("daily:security", "600519.SH", service.start, service.end)
        assert price_rows[-1]["close"] is not None
        count = len(calls)
        await service.research("600519")
        assert len(calls) == count
        failing = True
        saved = await service.research("600519", refresh=True)
        assert saved["feeds"]["orders"]["usingSaved"] is True
        assert saved["order"]["net5dYi"] == 3.5
        assert saved["observations"][0]["title"] == "资金价格对照待核验"


@pytest.mark.asyncio
async def test_no_token_leaves_metrics_missing(tmp_path):
    def handler(request):
        raise AssertionError("No network without a token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SecurityResearchService("", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client).research("920093")
    assert result["symbol"] == "920093.BJ"
    assert result["expectedDate"] is None
    assert result["order"]["net1dYi"] is None
    assert result["leverage"]["reconciliationChecked"] == 0
    assert result["observations"][0]["title"] == "资金价格对照待核验"
