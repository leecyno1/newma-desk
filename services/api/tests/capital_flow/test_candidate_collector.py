from datetime import date, datetime, timedelta

import pytest

from vibe_visualization_api.capital_flow.candidate_collector import CandidateCollector, collection_status, RUNS, ZONE
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover_candidates import DATASET, RULE
from vibe_visualization_api.capital_flow.turnover_history import TurnoverHistoryService, DATASET as HISTORY
from vibe_visualization_api.scheduler.store import SchedulerStore


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", [9, 15, 21, 23])
async def test_outside_close_window_never_fetches_or_backfills(tmp_path, hour):
    store = CapitalHistoryStore(tmp_path / "app.db")
    result = await CandidateCollector("test", store).collect(datetime(2026, 10, 19, hour, tzinfo=ZONE))
    assert result["status"] == "outside-window"
    assert store.read(DATASET, RULE["id"], "1990-01-01", "9999-12-31")[0] == []


@pytest.mark.asyncio
async def test_official_closure_and_unknown_calendar_are_distinct(tmp_path, monkeypatch):
    store = CapitalHistoryStore(tmp_path / "app.db")
    calendar = [{"cal_date": "20261017", "is_open": 0}]
    async def pages(self, client, api, params, fields):
        assert api == "trade_cal" and params["start_date"] == params["end_date"] == "20261017"
        return calendar
    monkeypatch.setattr(TurnoverHistoryService, "_pages", pages)
    collector = CandidateCollector("test", store)
    instant = datetime(2026, 10, 17, 16, tzinfo=ZONE)
    assert (await collector.collect(instant))["status"] == "closed"
    calendar.clear()
    with pytest.raises(ValueError, match="交易日历未确认"):
        await collector.collect(instant)
    assert store.read(RUNS, RULE["id"], "2026-10-17", "2026-10-17")[0][0]["status"] == "failed"
    assert store.read(DATASET, RULE["id"], "1990-01-01", "9999-12-31")[0] == []


@pytest.mark.asyncio
async def test_today_window_waits_for_data_then_freezes_once_without_historical_writes(tmp_path, monkeypatch):
    store = CapitalHistoryStore(tmp_path / "app.db")
    sessions = [(date(2026, 10, 16) - timedelta(days=i)).isoformat() for i in reversed(range(26))]
    rows = [{"date": day, "status": "ready", "amounts": {f"{i:06}.SZ": 100000 for i in range(25)}} for day in sessions]
    rows[-1]["amounts"]["000000.SZ"] = 300000
    complete = False
    calls = 0
    async def pages(self, client, api, params, fields):
        return [{"cal_date": "20261016", "is_open": 1}]
    async def history(self, days, refresh=False):
        nonlocal calls
        calls += 1
        assert self.end == "2026-10-16" and refresh  # normal service ends at yesterday
        store.save(HISTORY, "CN", rows if complete else rows[1:], start=sessions[0], end=sessions[-1],
                   status="ready", reason="", received_at="2026-10-16T08:00:00Z")
        return {"points": [{"date": day} for day in sessions], "calendarStatus": "ready", "reason": ""}
    monkeypatch.setattr(TurnoverHistoryService, "_pages", pages)
    monkeypatch.setattr(TurnoverHistoryService, "history", history)
    # Remove a date in the 20-day signal baseline, not an earlier unused day.
    rows[5]["status"] = "unavailable"
    instant = datetime(2026, 10, 16, 16, tzinfo=ZONE)
    collector = CandidateCollector("test", store)
    assert (await collector.collect(instant))["status"] == "waiting-data"
    assert store.read(DATASET, RULE["id"], sessions[0], sessions[-1])[0] == []
    complete = True
    rows[5]["status"] = "ready"
    result = await collector.collect(instant + timedelta(minutes=30))
    assert result["status"] == "recorded"
    saved = store.read(DATASET, RULE["id"], sessions[0], sessions[-1])[0]
    assert len(saved) == 1 and saved[0]["date"] == sessions[-1]
    assert saved[0]["captureSource"] == "scheduled-close" and len(saved[0]["eligibleCodes"]) == 25
    assert saved[0]["capturedAt"] == (instant + timedelta(minutes=30)).isoformat()
    assert len(saved[0]["candidates"]) == 1
    rows[-1]["amounts"]["000001.SZ"] = 900000
    await collector.collect(instant + timedelta(hours=1))
    assert calls == 2
    assert store.read(DATASET, RULE["id"], sessions[0], sessions[-1])[0] == saved


def test_collection_gaps_only_use_known_closed_days_and_do_not_claim_full_audit(tmp_path):
    store = CapitalHistoryStore(tmp_path / "app.db")
    calendar = [{"date": day, "is_open": status} for day, status in [("2026-10-15", 1), ("2026-10-16", 1), ("2026-10-17", 0)]]
    store.save("trade_cal", "SSE", calendar, start="2026-10-15", end="2026-10-17", status="ready", reason="", received_at="2026-10-16T08:00:00Z")
    jobs = SchedulerStore(store.path)
    now = datetime(2026, 10, 16, 16, tzinfo=ZONE)
    status = collection_status(store, jobs, enabled=True, token_ready=True, now=now)
    assert status["job"] is None and status["lastCheck"] is None
    assert status["missingDates"] == ["2026-10-15"]
    evening = collection_status(store, jobs, enabled=True, token_ready=True, now=now + timedelta(hours=5))
    assert evening["missingDates"] == ["2026-10-15", "2026-10-16"]
    store.save_once(DATASET, RULE["id"], {"date": "2026-10-16", "capturedAt": now.isoformat(), "candidates": []})
    assert collection_status(store, jobs, enabled=False, token_ready=False, now=now + timedelta(days=1))["missingDates"] == ["2026-10-15"]
