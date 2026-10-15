import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover import TurnoverResearchService, turnover_snapshot, with_turnover


DAY = "2026-10-14"


def quote(code="000001.SZ", amount=100000, **extra):
    return {"ts_code": code, "trade_date": "20261014", "amount": amount, "close": 11, "pct_chg": None, **extra}


def test_units_sample_concentration_names_and_exchange_missing():
    data = turnover_snapshot([quote(), quote("600000.SH", 200000), quote()], [{"ts_code": "000001.SZ", "name": "平安银行"}], DAY)
    assert data["summary"] == {"sampleTurnoverYi": 3, "top20TurnoverYi": 3, "top20SharePct": 100}
    assert data["coverage"]["duplicates"] == 1
    assert data["coverage"]["universeVerified"] is False
    assert data["leaders"][0]["code"] == "600000"
    assert data["leaders"][1]["amount"] == 1e8
    assert data["leaders"][1]["name"] == "平安银行"
    assert data["leaders"][1]["pct"] is None
    assert data["exchanges"][2]["turnoverYi"] is None


@pytest.mark.parametrize("bad", [quote("600000.SH", None), quote("600000.SH", -1), quote("600000.SH", trade_date="20261013"), quote("900001.SH"), quote(amount=5)])
def test_missing_wrong_day_and_conflicts_cannot_confirm_aggregate(bad):
    data = turnover_snapshot([quote(), bad], [], DAY)
    assert not data["coverage"]["valid"]
    assert data["summary"]["sampleTurnoverYi"] is None
    assert data["summary"]["top20SharePct"] is None


def test_real_zero_not_missing_and_top20_denominator_uses_entire_sample():
    zero = turnover_snapshot([quote(amount=0)], [], DAY)
    assert zero["coverage"]["valid"]
    assert zero["summary"]["sampleTurnoverYi"] == 0
    assert zero["summary"]["top20SharePct"] is None
    data = turnover_snapshot([quote(f"{i:06}.SZ") for i in range(1, 22)], [], DAY)
    assert len(data["leaders"]) == 20
    assert data["summary"]["top20SharePct"] == pytest.approx(20 / 21 * 100)


@pytest.mark.asyncio
async def test_pagination_cache_and_failed_second_page_preserve_dated_snapshot(tmp_path):
    calls, fail = [], False
    def handler(request):
        p = json.loads(request.content); calls.append(p)
        fields = p["fields"].split(",")
        offset = p["params"].get("offset", 0)
        if p["api_name"] == "trade_cal":
            rows = [{"cal_date": "20261014", "is_open": 1}]
        elif p["api_name"] == "stock_basic":
            rows = [{"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行"}]
        else:
            assert p["params"]["trade_date"] == "20261014"
            if fail and offset:
                return httpx.Response(503)
            rows = [quote(), quote("600000.SH", 200000)] if offset == 0 else [quote("920001.BJ", 50000)]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[r.get(f) for f in fields] for r in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TurnoverResearchService("test", CapitalHistoryStore(tmp_path / "test.sqlite"), client=client, today=date(2026, 10, 15))
        service.page_size = 2
        first = await service.research()
        assert first["current"] and first["asOf"] == DAY
        assert first["summary"]["sampleTurnoverYi"] == 3.5
        count = len(calls)
        assert (await service.research())["cached"]
        assert len(calls) == count
        fail = True
        saved = await service.research(refresh=True)
        assert saved["status"] == "upstream-error"
        assert saved["usingSaved"] and not saved["current"]
        assert saved["summary"]["sampleTurnoverYi"] == 3.5
        assert len(saved["leaders"]) == 3
        dashboard = {"summary": {}, "dimensions": [{"id": "market"}], "riskAppetite": {"drivers": []}, "upstream": {}}
        mapped = with_turnover(dashboard, saved)
        assert mapped["summary"]["top20TurnoverYi"] is None
        assert mapped["dimensions"][0]["asOf"] == DAY
        assert mapped["dimensions"][0]["status"] == "degraded"


@pytest.mark.asyncio
async def test_pagination_limit_and_repeated_pages_are_not_complete(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["ts_code"], "items": [["000001.SZ"], ["600000.SH"]]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = TurnoverResearchService("test", CapitalHistoryStore(tmp_path / "test.sqlite"), client=client)
        service.page_size = 2
        with pytest.raises(ValueError, match="分页重复"):
            await service._pages(client, "daily", {}, "ts_code")
        service.max_pages = 1
        with pytest.raises(ValueError, match="分页上限"):
            await service._pages(client, "daily", {}, "ts_code")
