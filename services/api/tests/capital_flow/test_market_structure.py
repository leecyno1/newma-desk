import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.market_structure import INDEXES, MarketStructureService, build_structure, index_analysis
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover import turnover_snapshot


DAYS = [(date(2026, 9, 1) + timedelta(days=i)).isoformat() for i in range(21)]


def test_distribution_counts_only_valid_traded_sample_and_preserves_boundaries():
    values = [-5, -3, -1, 0, 1, 3, 5, None, 0]
    rows = [{"ts_code": f"{i + 1:06}.SZ", "trade_date": "20260921", "amount": 0 if i == 8 else 100,
             "close": 10, "pct_chg": pct} for i, pct in enumerate(values)]
    result = turnover_snapshot(rows, [], DAYS[-1])
    breadth = result["breadth"]
    assert [row["count"] for row in breadth["buckets"]] == [1] * 7
    assert breadth["up"] == breadth["down"] == 3
    assert breadth["flat"] == 1
    assert breadth["inactiveCount"] == breadth["missingPctCount"] == 1
    assert breadth["validCount"] == 7
    assert breadth["upRatioPct"] == pytest.approx(3 / 7 * 100)
    assert breadth["medianPct"] == 0


def index(code, name, *, status="ready", missing=False):
    rows = [{"ts_code": code, "date": day, "close": 100 + i} for i, day in enumerate(DAYS)]
    if missing:
        rows.pop(18)
    return index_analysis(code, name, {"rows": rows, "status": status, "reason": "", "usingSaved": status != "ready"}, DAYS, True)


def test_price_windows_use_base_close_and_revoke_failed_or_incomplete_comparisons():
    full = index(*INDEXES[0])
    assert full["windows"]["5"]["returnPct"] == pytest.approx((120 / 115 - 1) * 100)
    assert full["windows"]["20"]["returnPct"] == pytest.approx(20)
    gap = index(*INDEXES[0], missing=True)
    assert not gap["windows"]["5"]["current"]
    assert gap["windows"]["5"]["returnPct"] is None
    assert gap["windows"]["1"]["current"]
    saved = index(*INDEXES[0], status="upstream-error")
    assert saved["windows"]["5"]["returnPct"] is not None
    assert not saved["windows"]["5"]["current"]


def test_divergence_requires_same_date_and_complete_breadth_no_style_fallback():
    turnover = {"current": True, "asOf": DAYS[-1], "calendarStatus": "ready",
                "breadth": {"validCount": 100, "missingPctCount": 0, "upRatioPct": 40}}
    indices = [index(code, name) for code, name in INDEXES]
    result = build_structure(turnover, indices, DAYS)
    assert result["current"]
    assert result["relationship"]["text"] == "沪深300上涨，但样本上涨不足一半"
    assert result["styles"][0]["windows"]["5"]["spreadPp"] == 0
    indices[-1] = index(*INDEXES[-1], status="upstream-error")
    result = build_structure(turnover, indices, DAYS)
    assert not result["current"]
    assert result["styles"][1]["windows"]["5"]["spreadPp"] is None
    turnover["asOf"] = DAYS[-2]
    assert not build_structure(turnover, indices, DAYS)["relationship"]["current"]
    turnover["asOf"] = DAYS[-1]
    turnover["breadth"]["missingPctCount"] = 1
    assert not build_structure(turnover, indices, DAYS)["breadth"]["current"]


@pytest.mark.asyncio
async def test_service_reuses_turnover_and_index_cache_and_failed_refresh_retains_reference(tmp_path):
    calls, fail = [], False
    def handler(request):
        body = json.loads(request.content); api = body["api_name"]; calls.append(api)
        if fail and api == "index_daily":
            return httpx.Response(503)
        fields = body["fields"].split(",")
        if api == "trade_cal":
            rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DAYS]
        elif api == "daily":
            rows = [{"ts_code": "000001.SZ", "trade_date": "20260921", "close": 10, "pct_chg": 1, "amount": 100}]
        elif api == "stock_basic":
            rows = [{"ts_code": "000001.SZ", "name": "测试", "industry": "银行"}]
        else:
            rows = [{"ts_code": body["params"]["ts_code"], "trade_date": day.replace("-", ""), "close": 100 + i, "pct_chg": 1} for i, day in enumerate(DAYS)]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[r.get(f) for f in fields] for r in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = MarketStructureService("test", CapitalHistoryStore(tmp_path / "test.sqlite"), client=client, today=date(2026, 9, 22))
        first = await service.research()
        assert first["current"]
        assert first["turnover"]["summary"]["sampleTurnoverYi"] == .001
        before = len(calls)
        assert (await service.research())["current"]
        assert len(calls) == before
        fail = True
        saved = await service.research(refresh=True)
        assert not saved["current"]
        assert saved["breadth"]["current"]
        assert not saved["relationship"]["current"]
        assert saved["indices"][0]["windows"]["5"]["returnPct"] is not None
