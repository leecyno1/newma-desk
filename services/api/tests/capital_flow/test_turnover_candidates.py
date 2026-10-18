from datetime import date, timedelta

import pytest

from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover_candidates import RULE, TurnoverCandidatesService, scan, forward_path, cohort_summary, compare_cohorts, record_timing, track_cohorts
from vibe_visualization_api.capital_flow.turnover_history import DATASET
from vibe_visualization_api.capital_flow.turnover_candidates import DATASET as COHORTS
from vibe_visualization_api.capital_flow.turnover import TurnoverResearchService


def sample():
    sessions = [(date(2026, 9, 1) + timedelta(days=n)).isoformat() for n in range(26)]
    rows = [{"date": day, "status": "ready", "amounts": {f"{n:06}.SZ": 100000 for n in range(25)},
             "returns": {f"{n:06}.SZ": 1 for n in range(25)}} for day in sessions]
    return rows, sessions


def test_signal_uses_only_prior_twenty_days_and_not_future_membership():
    rows, sessions = sample()
    rows[20]["amounts"]["000000.SZ"] = 300000
    rows[21]["amounts"].pop("000000.SZ")
    rows[25]["amounts"]["000001.SZ"] = 99999999
    result = scan(rows, sessions, sessions[20], True)
    assert result["current"] and result["baselineEnd"] == sessions[19]
    assert [r["code"] for r in result["candidates"]] == ["000000.SZ"]
    assert result["candidates"][0]["amountYi"] == 3
    assert result["candidates"][0]["ownRatio"] == 3


def test_market_wide_expansion_is_not_a_stock_specific_anomaly():
    rows, sessions = sample()
    rows[20]["amounts"] = {code: 200000 for code in rows[20]["amounts"]}
    rows[20]["amounts"]["000000.SZ"] = 600000
    result = scan(rows, sessions, sessions[20], True)
    assert result["marketMedianRatio"] == 2 and len(result["candidates"]) == 1
    assert result["candidates"][0]["marketAdjustedRatio"] == 3


def test_missing_dates_and_nonpositive_amounts_are_not_filled():
    rows, sessions = sample()
    rows[0]["amounts"].pop("000000.SZ")
    rows[1]["amounts"]["000001.SZ"] = 0
    result = scan(rows, sessions, sessions[20], True)
    assert result["eligibleCount"] == 23 and result["excludedCount"] == 2
    rows[2]["status"] = "unavailable"
    assert not scan(rows, sessions, sessions[20], True)["current"]
    assert not scan(rows, sessions, sessions[20], False)["current"]


def test_forward_paths_exclude_signal_day_and_preserve_missing_or_pending():
    rows, sessions = sample()
    rows[20]["returns"]["000000.SZ"] = 99
    rows[21]["returns"]["000000.SZ"] = -10
    rows[22]["returns"]["000000.SZ"] = 10
    indexed = {row["date"]: row for row in rows}
    assert forward_path("000000.SZ", sessions[20], sessions, indexed, 1)["changePct"] == pytest.approx(-10)
    assert forward_path("000000.SZ", sessions[20], sessions, indexed, 3)["changePct"] == pytest.approx(-0.01)
    rows[23]["returns"].pop("000000.SZ")
    assert forward_path("000000.SZ", sessions[20], sessions, indexed, 3)["status"] == "missing"
    assert forward_path("000000.SZ", sessions[24], sessions, indexed, 3)["status"] == "pending"


def test_cohort_distribution_counts_missing_and_pending_without_filling():
    candidates = [{"forward": [
        {"days": 1, "status": "ready" if value is not None else "missing", "changePct": value, "end": "2026-10-12"},
        {"days": 3, "status": "missing", "changePct": None, "end": "2026-10-14"},
        {"days": 5, "status": "pending", "changePct": None, "end": None},
    ]} for value in (-20, -5, 0, 5, 20, None)]
    result = cohort_summary(candidates)
    first, missing, pending = result["windows"]
    assert result["total"] == 6
    assert (first["valid"], first["missing"], first["pending"]) == (5, 1, 0)
    assert (first["up"], first["flat"], first["down"]) == (2, 1, 2)
    assert first["positivePct"] == 40  # denominator is 5, never 6
    assert first["coveragePct"] == pytest.approx(100 * 5 / 6)
    assert first["medianPct"] == first["meanPct"] == 0
    assert (first["p25Pct"], first["p75Pct"]) == (-5, 5)
    assert (first["minPct"], first["maxPct"]) == (-20, 20)
    assert first["status"] == "partial"
    assert missing["status"] == "missing" and missing["missing"] == 6
    assert pending["status"] == "pending" and pending["pending"] == 6
    for row in (missing, pending):
        assert row["positivePct"] is None and row["medianPct"] is None and row["meanPct"] is None


def test_cohort_includes_beyond_page_one_and_handles_empty_and_single_sample():
    candidates = [{"forward": [{"days": days, "status": "ready", "changePct": -1 if i < 50 else 2,
                               "end": "2026-10-16"} for days in (1, 3, 5)]} for i in range(61)]
    result = cohort_summary(candidates)["windows"][0]
    assert result["valid"] == 61 and result["up"] == 11 and result["down"] == 50
    assert result["positivePct"] == pytest.approx(100 * 11 / 61)
    assert result["status"] == "ready"
    one = cohort_summary(candidates[-1:])["windows"][0]
    assert one["p25Pct"] == one["p75Pct"] == one["meanPct"] == 2
    empty = cohort_summary([])["windows"][0]
    assert empty["status"] == "empty" and empty["positivePct"] is None and empty["coveragePct"] is None


def test_non_candidates_use_signal_day_universe_and_identical_forward_windows():
    rows, sessions = sample()
    rows[0]["amounts"].pop("000001.SZ")  # Not eligible at signal date.
    rows[20]["amounts"]["000000.SZ"] = 300000
    rows[21]["returns"]["000000.SZ"] = -10
    rows[21]["amounts"]["999999.SZ"] = 900000  # Future entrant must not enter the control group.
    rows[21]["returns"]["999999.SZ"] = 99
    rows[22]["returns"].pop("000024.SZ")  # Missing later data does not change membership.
    group = scan(rows, sessions, sessions[20], True)
    indexed = {row["date"]: row for row in rows}
    candidates = [{**row, "forward": [forward_path(row["code"], sessions[20], sessions, indexed, days) for days in (1, 3, 5)]} for row in group["candidates"]]
    result = compare_cohorts(group, cohort_summary(candidates), sessions[20], sessions, indexed)
    assert result["eligibleCount"] == 24 and result["control"]["total"] == 23
    one, three, five = result["control"]["windows"]
    assert one["valid"] == 23 and one["positivePct"] == 100 and one["meanPct"] == pytest.approx(1)
    assert result["windows"][0]["positiveGapPp"] == -100
    assert result["windows"][0]["medianGapPp"] == pytest.approx(-11)
    assert result["windows"][0]["meanGapPp"] == pytest.approx(-11)
    assert three["valid"] == five["valid"] == 22 and three["missing"] == five["missing"] == 1
    assert result["windows"][1]["medianGapPp"] is None
    assert result["windows"][1]["reason"] == "两组样本未齐，不计算差值"


def test_legacy_cohort_without_frozen_universe_is_not_reconstructed():
    rows, sessions = sample()
    group = scan(rows, sessions, sessions[20], True)
    group.pop("eligibleCodes")
    result = compare_cohorts(group, cohort_summary([]), sessions[20], sessions, {row["date"]: row for row in rows})
    assert result["status"] == "unavailable" and result["control"] is None and not result["windows"]
    assert "旧快照" in result["reason"]


def test_record_timing_respects_exchange_timezone_weekend_and_opening_boundary():
    assert record_timing("2026-10-10T01:00:00Z", "2026-10-09", "2026-10-12") == "before-open"
    assert record_timing("2026-10-12T01:30:00Z", "2026-10-09", "2026-10-12") == "late"
    assert record_timing("2026-10-10T01:00:00Z", "2026-10-09", None) == "pending-calendar"
    assert record_timing("2026-10-09T06:59:00Z", "2026-10-09", "2026-10-12") == "unknown"
    assert record_timing("2026-10-09T16:00:00", "2026-10-09", "2026-10-12") == "unknown"


def test_tracking_separates_timely_late_and_reconstructed_dates_without_pooling():
    rows, sessions = sample()
    rows[20]["amounts"]["000000.SZ"] = 300000
    rows[21]["amounts"]["000001.SZ"] = 300000
    recorded = {
        sessions[20]: {**scan(rows, sessions, sessions[20], True), "capturedAt": f"{sessions[20]}T16:00:00+08:00"},
        sessions[21]: {**scan(rows, sessions, sessions[21], True), "capturedAt": f"{sessions[22]}T09:30:00+08:00"},
    }
    tracked = track_cohorts(rows, sessions, recorded, True)
    assert tracked["recordedDays"] == 2 and tracked["retrospectiveDays"] == 4
    assert tracked["forwardCompleteDays"] == {"1": 1, "3": 1, "5": 1}
    assert tracked["rows"][-1]["timing"] == "before-open"
    assert tracked["rows"][-2]["timing"] == "late"
    assert tracked["rows"][0]["timing"] == "retrospective"
    rows[22]["returns"].pop("000024.SZ")
    missing = track_cohorts(rows, sessions, recorded, True)
    assert missing["forwardCompleteDays"] == {"1": 1, "3": 0, "5": 0}
    assert missing["rows"][-1]["windows"][1]["medianGapPp"] is None
    assert track_cohorts(rows, sessions, recorded, False)["forwardCompleteDays"] == {"1": 0, "3": 0, "5": 0}
    assert len(recorded) == 2  # Tracking does not create historical snapshots.


@pytest.mark.asyncio
async def test_first_observation_is_frozen_but_history_is_labeled_retrospective(tmp_path, monkeypatch):
    rows, sessions = sample()
    store = CapitalHistoryStore(tmp_path / "history.db")
    store.save(DATASET, "CN", rows, start=sessions[0], end=sessions[-1], status="ready", reason="", received_at="2026-10-17T00:00:00+00:00")
    async def history(self, days, refresh=False):
        return {"points": [{"date": day} for day in sessions], "calendarStatus": "ready", "generatedAt": "2026-10-17T00:00:00+00:00", "completed": 26, "canContinue": False, "reason": ""}
    monkeypatch.setattr(TurnoverCandidatesService, "history", history)
    service = TurnoverCandidatesService("test", store, today=date(2026, 10, 17))
    first = await service.candidates()
    assert first["mode"] == "recorded" and first["candidateCount"] == 0
    assert first["cohort"]["total"] == 0
    assert first["cohort"]["windows"][0]["status"] == "empty"
    assert first["comparison"]["control"]["total"] == 25
    assert all(row["meanGapPp"] is None for row in first["comparison"]["windows"])
    rows[-1]["amounts"]["000000.SZ"] = 300000
    store.save(DATASET, "CN", rows[-1:], start=sessions[-1], end=sessions[-1], status="ready", reason="", received_at="2026-10-17T01:00:00+00:00")
    assert (await service.candidates(refresh=True))["candidateCount"] == 0  # Even a zero-candidate snapshot is frozen.
    historical = await service.candidates(signal_date=sessions[20])
    assert historical["mode"] == "retrospective" and historical["capturedAt"] is None
    assert historical["tracking"]["recordedDays"] == 1
    assert historical["tracking"]["retrospectiveDays"] == 5
    assert historical["tracking"]["forwardCompleteDays"] == {"1": 0, "3": 0, "5": 0}
    recorded, _ = store.read(COHORTS, RULE["id"], sessions[0], sessions[-1])
    assert len(recorded) == 1 and recorded[0]["date"] == sessions[-1]
    with pytest.raises(ValueError):
        await service.candidates(signal_date=sessions[0])


@pytest.mark.asyncio
async def test_all_candidates_returned_names_are_display_only_and_snapshot_unchanged(tmp_path, monkeypatch):
    rows, sessions = sample()
    for row in rows:
        row["amounts"] = {f"{n:06}.SZ": 100000 for n in range(300)}
    rows[-1]["amounts"].update({f"{n:06}.SZ": 300000 for n in range(121)})
    store = CapitalHistoryStore(tmp_path / "history.db")
    store.save(DATASET, "CN", rows, start=sessions[0], end=sessions[-1], status="ready", reason="", received_at="2026-10-17T00:00:00+00:00")
    async def history(self, days, refresh=False):
        return {"points": [{"date": day} for day in sessions], "calendarStatus": "ready", "generatedAt": "2026-10-17T00:00:00+00:00", "completed": 26, "canContinue": False, "reason": ""}
    names = [{"ts_code": "000000.SZ", "name": "当前名称"}]
    async def catalog(self, client, refresh=False):
        return {"items": names, "receivedAt": "2026-10-17T00:00:00+00:00", "usingSaved": False, "reason": ""}
    monkeypatch.setattr(TurnoverCandidatesService, "history", history)
    monkeypatch.setattr(TurnoverCandidatesService, "stock_names", catalog)
    service = TurnoverCandidatesService("test", store, today=date(2026, 10, 17))
    result = await service.candidates()
    assert len(result["candidates"]) == result["candidateCount"] == 121
    assert result["cohort"]["total"] == 121
    assert result["cohort"]["windows"][0]["pending"] == 121
    assert result["comparison"]["control"]["total"] == 179
    assert result["comparison"]["windows"][0]["reason"] == "观察期未到期"
    assert "eligibleCodes" not in result  # Do not send thousands of codes to Agent.
    assert result["candidates"][0]["name"] == "当前名称"
    assert result["candidates"][-1]["name"] is None
    assert result["nameCatalog"]["matched"] == 1
    frozen, _ = store.read(COHORTS, RULE["id"], sessions[-1], sessions[-1])
    assert "name" not in frozen[0]["candidates"][0]
    assert len(frozen[0]["eligibleCodes"]) == 300
    rows[5]["amounts"]["000299.SZ"] = 0
    store.save(DATASET, "CN", rows[5:6], start=sessions[5], end=sessions[5], status="ready", reason="", received_at="2026-10-17T01:00:00+00:00")
    names[0]["name"] = "改名后"
    after = await service.candidates(refresh=True)
    assert after["candidates"][0]["name"] == "改名后"
    assert after["capturedAt"] == result["capturedAt"]
    assert after["candidateCount"] == 121
    assert after["comparison"]["control"]["total"] == 179  # Frozen membership survives later source revisions.
    # The current signal uses sessions[5:26]; invalidate that baseline, retaining the frozen cohort.
    rows[5]["status"] = "unavailable"
    store.save(DATASET, "CN", rows[5:6], start=sessions[5], end=sessions[5], status="ready", reason="", received_at="2026-10-17T01:00:00+00:00")
    unavailable = await service.candidates()
    assert not unavailable["current"] and unavailable["cohort"] is None
    assert unavailable["comparison"] is None


@pytest.mark.asyncio
async def test_stock_directory_cache_and_failure_do_not_remove_saved_names(tmp_path, monkeypatch):
    service = TurnoverResearchService("test", CapitalHistoryStore(tmp_path / "history.db"))
    calls = 0
    async def pages(client, api, params, fields):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("provider failure")
        return [{"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行"}]
    monkeypatch.setattr(service, "_pages", pages)
    first = await service.stock_names(None)
    cached = await service.stock_names(None)
    assert first["items"] == cached["items"] and calls == 1
    failed = await service.stock_names(None, refresh=True)
    assert failed["usingSaved"] and failed["items"] == first["items"] and failed["reason"]
    empty = TurnoverResearchService("", CapitalHistoryStore(tmp_path / "empty.db"))
    assert (await empty.stock_names(None))["items"] == []
