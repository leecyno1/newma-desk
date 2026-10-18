import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow.limit_boards import LimitBoardsService, pool_snapshot, board_analysis
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


def row(code="000001.SZ", kind="U", boards=1, **extra):
    return {"trade_date": "20261015", "ts_code": code, "name": code, "industry": "测试行业",
            "limit": kind, "limit_times": boards, "open_times": 0, **extra}


def test_unique_pool_denominators_and_actual_previous_intersection():
    current = pool_snapshot([row(boards=3, open_times=4), row("600001.SH", boards=None), row("600002.SH", "Z"), row("600003.SH", "D")], "2026-10-15")
    previous = pool_snapshot([row(trade_date="20261014"), row("600004.SH", trade_date="20261014")], "2026-10-14")
    result = board_analysis(current, previous, True)
    assert result["summary"]["up"] == 2 and result["summary"]["broken"] == 1
    assert result["summary"]["sealRatePct"] == pytest.approx(200 / 3)
    assert result["summary"]["reopenedUp"] == 1  # four events still one security, not four failed boards
    assert result["summary"]["retentionRatePct"] == 50
    assert result["ladder"] == [{"boards": 3, "count": 1}]
    assert result["summary"]["unknownBoards"] == 1


def test_missing_previous_pool_does_not_poison_current_counts():
    result = board_analysis(pool_snapshot([row()], "2026-10-15"), {"status": "unavailable"}, True)
    assert result["summary"]["up"] == 1
    assert result["summary"]["retentionRatePct"] is None
    assert not result["tracking"]["ready"] and result["tracking"]["summary"] is None


def test_previous_cohort_outcomes_unknown_tiers_and_unmatched_continuations():
    previous = pool_snapshot([row(f"{i:06}.SZ", boards=2 if i < 4 else None, trade_date="20261014") for i in range(1, 6)], "2026-10-14")
    current = pool_snapshot([row("000001.SZ", boards=3), row("000002.SZ", kind="Z"),
                             row("000003.SZ", kind="D"), row("000005.SZ", boards=2), row("000006.SZ", boards=4)], "2026-10-15")
    tracking = board_analysis(current, previous, True)["tracking"]
    assert tracking["summary"] == {"total": 5, "U": 2, "Z": 1, "D": 1, "absent": 1, "mismatches": 0}
    assert [tier["boards"] for tier in tracking["tiers"]] == [2, None]
    assert tracking["tiers"][0]["retentionRatePct"] == pytest.approx(100 / 3)
    rows = {r["code"]: r for r in tracking["rows"]}
    assert rows["000004.SZ"]["outcome"] == "absent"
    assert rows["000001.SZ"]["progression"] == "matched"
    assert rows["000005.SZ"]["progression"] == "unknown"
    assert [r["code"] for r in tracking["unmatchedContinuations"]] == ["000006.SZ"]


def test_inconsistent_board_count_does_not_change_source_or_invent_progression():
    current = pool_snapshot([row(boards=4)], "2026-10-15")
    previous = pool_snapshot([row(boards=2, trade_date="20261014")], "2026-10-14")
    result = board_analysis(current, previous, True)
    assert result["tracking"]["summary"]["mismatches"] == 1
    assert result["tracking"]["rows"][0]["currentBoards"] == 4
    assert result["summary"]["retainedUp"] == 1  # Pool intersection remains a fact, not promotion proof.
    unavailable = board_analysis(current, previous, False)["tracking"]
    assert not unavailable["ready"] and unavailable["rows"] == [] and unavailable["summary"] is None


def test_no_previous_up_is_valid_empty_cohort_not_zero_win_rate():
    result = board_analysis(pool_snapshot([row()], "2026-10-15"),
                            pool_snapshot([row(kind="D", trade_date="20261014")], "2026-10-14"), True)
    assert result["tracking"]["ready"] and result["tracking"]["rows"] == []
    assert result["tracking"]["tiers"] == [] and result["summary"]["retentionRatePct"] is None


@pytest.mark.parametrize("bad", [row(kind="Z"), row(trade_date="20261014"), row(kind="X"), row(code="bad")])
def test_wrong_dates_and_conflicting_classification_cannot_count(bad):
    result = board_analysis(pool_snapshot([row(), bad], "2026-10-15"), {}, True)
    assert not result["current"] and not result["items"]
    assert result["summary"]["sealRatePct"] is None


def test_duplicate_deduplication_zero_denominator_and_unknown_board_fields():
    snapshot = pool_snapshot([row(), row()], "2026-10-15")
    assert snapshot["coverage"]["duplicates"] == 1
    assert board_analysis(snapshot, {}, True)["summary"]["up"] == 1
    result = board_analysis(pool_snapshot([row(kind="D")], "2026-10-15"), {}, True)
    assert result["summary"]["up"] == 0 and result["summary"]["sealRatePct"] is None
    for value in [None, "-", 1.5, -1, True]:
        item = pool_snapshot([row(boards=value)], "2026-10-15")["items"][0]
        assert item["boards"] is None


@pytest.mark.asyncio
async def test_pagination_cache_failure_and_empty_do_not_reuse_old_lists(tmp_path):
    fail, empty, quote_fail, calls, quote_calls = False, False, False, [], []
    def handler(request):
        p = json.loads(request.content); fields = p["fields"].split(",")
        if p["api_name"] == "trade_cal":
            rows = [{"cal_date": "20261014", "is_open": 1}, {"cal_date": "20261015", "is_open": 1}]
        elif p["api_name"] in {"daily", "stk_limit"}:
            quote_calls.append(p)
            if quote_fail: return httpx.Response(503)
            rows = [{"ts_code": f"{i:06}.SZ", "trade_date": "20261015", "close": 11, "pct_chg": 10,
                     "amount": 100000, "up_limit": 11, "down_limit": 9} for i in range(3)]
        else:
            calls.append(p)
            if fail: return httpx.Response(503)
            start = p["params"]["offset"]
            rows = [] if empty else [row(f"{i:06}.SZ", trade_date=p["params"]["trade_date"]) for i in range(start, min(start + 2, 3))]
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[r.get(f) for f in fields] for r in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = LimitBoardsService("test", CapitalHistoryStore(tmp_path / "boards.db"), client=client, today=date(2026, 10, 16))
        service.page_size = 2
        result = await service.research()
        assert result["summary"]["up"] == 3 and result["summary"]["retentionRatePct"] == 100
        assert len(calls) == 4
        assert len(quote_calls) == 2
        assert result["tracking"]["quoteVerification"]["summary"]["atLimit"] == 3
        assert (await service.research())["current"] and len(calls) == 4
        assert len(quote_calls) == 2
        quote_fail = True
        failed_quotes = await service.research(refresh=True)
        assert failed_quotes["current"] and failed_quotes["summary"]["up"] == 3
        assert failed_quotes["tracking"]["quoteVerification"]["summary"]["priced"] == 0
        assert all(r["close"] is None for r in failed_quotes["tracking"]["quoteVerification"]["rows"])
        fail = True
        result = await service.research(refresh=True)
        assert not result["current"] and result["summary"]["up"] is None and not result["items"]
        fail, empty = False, True
        result = await service.research(refresh=True)
        assert not result["current"] and result["summary"]["up"] is None
        assert "均为空" in result["reason"]
