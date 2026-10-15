import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow.sectors import SectorResearchService, catalog_rows, classify_boards, sector_point, sector_summary
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = ["2026-10-09", "2026-10-12", "2026-10-13"]


def board(code="BK1340.DC", category="行业", **extra):
    return {"date": DATES[-1], "ts_code": code, "content_type": category, "name": "印制电路板",
            "net_amount": 2e8, "pct_change": 2, "net_amount_rate": 3,
            "buy_elg_amount": .5e8, "buy_lg_amount": 1.5e8, **extra}


def test_classification_deduplication_and_units():
    rows, duplicates = catalog_rows([board(), board(), board("BK1136.DC", "概念")], "industry")
    assert len(rows) == 1
    assert duplicates == 1
    assert rows[0]["net"] == 2
    assert rows[0]["aggregateSafe"] is False
    conflicting, _ = catalog_rows([board(), board(net_amount=1e8)], "industry")
    assert conflicting[0]["duplicateConflict"] is True
    assert conflicting[0]["net"] is None
    assert sector_point(board())["superNetYi"] == .5


def test_hierarchy_joins_date_and_code_not_names_and_rejects_conflicts():
    boards, _ = catalog_rows([board("BK1.DC"), board("BK2.DC"), board("BK3.DC"), board("BK4.DC")], "industry")
    rows = [{"date": DATES[-1], "ts_code": code, "idx_type": "行业板块", "level": level}
            for code, level in [("BK1.DC", "东财一级行业"), ("BK2.DC", "东财二级行业"),
                                ("BK3.DC", "东财一级行业"), ("BK3.DC", "东财三级行业")]]
    feed = {"status": "ready", "rows": [{"date": DATES[-1], "boards": rows}]}
    mapped, coverage = classify_boards(boards, feed, DATES[-1], DATES[-1], True)
    assert {row["code"]: row["level"] for row in mapped} == {"BK1.DC": "L1", "BK2.DC": "L2", "BK3.DC": "unknown", "BK4.DC": "unknown"}
    assert coverage["counts"] == {"L1": 1, "L2": 1, "L3": 0, "unknown": 2}
    assert coverage["conflicts"] == 1
    assert coverage["constituentsVerified"] is False
    assert all(not row["aggregateSafe"] for row in mapped)


@pytest.mark.parametrize("state", ["date", "failure", "calendar"])
def test_stale_hierarchy_never_confirms_current_level(state):
    boards, _ = catalog_rows([board()], "industry")
    feed = {"status": "ready", "rows": [{"date": DATES[-1], "boards": [
        {"date": DATES[-1], "ts_code": "BK1340.DC", "idx_type": "行业板块", "level": "东财一级行业"}]}]}
    if state == "failure":
        feed.update(status="upstream-error", usingSaved=True)
    mapped, coverage = classify_boards(boards, feed, DATES[-1], DATES[-2] if state == "date" else DATES[-1], state != "calendar")
    assert not coverage["current"]
    assert mapped[0]["level"] == "unknown"
    assert mapped[0]["reportedLevel"] == "东财一级行业"


def test_strict_windows_streak_and_compound_price():
    points = [{"date": day, "net": 1, "pct": 10} for day in DATES]
    summary = sector_summary(points, DATES)
    assert summary["net1dYi"] == 1
    assert summary["net5dYi"] is None
    assert summary["streak"] == {"direction": "in", "days": 3}
    summary = sector_summary([points[0], points[-1]], DATES)
    assert summary["streak"] == {"direction": "in", "days": 1}
    assert sector_summary(points[:-1], DATES)["streak"] == {"direction": "unknown", "days": 0}
    sessions = [f"2026-09-{i:02}" for i in range(1, 22)]
    summary = sector_summary([{"date": day, "net": 1, "pct": 10} for day in sessions], sessions)
    assert summary["net5dYi"] == 5
    assert summary["price5dPct"] == pytest.approx(61.051)
    assert summary["baseline"]["samples"] == 20


@pytest.mark.asyncio
async def test_catalog_preserves_all_boards_and_code_histories(tmp_path):
    calls = []
    failing = False

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if failing:
            return httpx.Response(503)
        if payload["api_name"] == "trade_cal":
            fields, items = ["cal_date", "is_open"], [[day.replace("-", ""), 1] for day in DATES]
        else:
            params = payload["params"]
            fields = payload["fields"].split(",")
            if params.get("ts_code"):
                rows = [{**board(params["ts_code"]), "trade_date": day.replace("-", "")} for day in DATES]
            else:
                assert params["trade_date"] == "20261013"
                rows = [{**board(code), "trade_date": "20261013"} for code in ("BK1340.DC", "BK1329.DC")]
            items = [[row.get(field) for field in fields] for row in rows]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": items}})

    store = CapitalHistoryStore(tmp_path / "capital.sqlite")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SectorResearchService("test", store, client=client, today=date(2026, 10, 14))
        first = await service.research()
        assert len(first["boards"]) == 2
        assert first["coverage"]["hierarchyVerified"] is False
        assert first["selected"]["summary"]["net1dYi"] == 2
        count = len(calls)
        cached = await service.research()
        assert cached["boards"] == first["boards"]
        assert len(calls) == count
        second = await service.research(code="BK1329.DC")
        assert second["selected"]["code"] == "BK1329.DC"
        assert len(calls) == count + 1
        not_found = await service.research(code="BK9999.DC")
        assert not_found["selected"] is None
        assert not_found["coverage"]["selectedNotFound"] is True
        failing = True
        saved = await service.research(refresh=True)
        assert saved["coverage"]["status"] == "upstream-error"
        assert saved["coverage"]["usingSaved"] is True
        assert saved["selected"]["status"] == "partial"
        assert len(saved["boards"]) == 2


@pytest.mark.asyncio
async def test_permission_denied_does_not_become_empty_or_zero(tmp_path):
    def handler(request):
        if json.loads(request.content)["api_name"] == "trade_cal":
            return httpx.Response(200, json={"code": 0, "data": {"fields": ["cal_date", "is_open"], "items": [["20261013", 1]]}})
        return httpx.Response(200, json={"code": 40203, "msg": "没有接口权限"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SectorResearchService("test", CapitalHistoryStore(tmp_path / "capital.sqlite"), client=client,
                                             today=date(2026, 10, 14)).research()
    assert result["boards"] == []
    assert result["selected"] is None
    assert result["coverage"]["status"] == "permission-denied"


@pytest.mark.asyncio
async def test_level_filter_uses_shared_catalog_and_does_not_fetch_history_for_excluded_code(tmp_path, monkeypatch):
    calls = []
    async def dataset(self, client, api, symbol, *args, **kwargs):
        calls.append((api, symbol))
        if api == "trade_cal":
            rows = [{"date": day, "is_open": 1} for day in DATES]
        elif api == "dc_index":
            rows = [{"date": DATES[-1], "boards": [
                {"date": DATES[-1], "ts_code": code, "idx_type": "行业板块", "level": level}
                for code, level in [("BK0001.DC", "东财一级行业"), ("BK0002.DC", "东财二级行业")]]}]
        else:
            rows = [{"date": DATES[-1], "boards": [board("BK0001.DC"), board("BK0002.DC")]}]
        return {"rows": rows, "status": "ready", "usingSaved": False, "reason": ""}
    monkeypatch.setattr(SectorResearchService, "_dataset", dataset)
    service = SectorResearchService("test", CapitalHistoryStore(tmp_path / "capital.sqlite"))
    result = await service.research(level="L1", code="BK0002.DC")
    assert [row["code"] for row in result["boards"]] == ["BK0001.DC"]
    assert result["coverage"]["selectedNotFound"]
    assert result["selected"] is None
    assert result["classification"]["counts"]["L2"] == 1
    assert not any(symbol == "BK0002.DC" for _, symbol in calls)
