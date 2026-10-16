from copy import deepcopy

import pytest

from instock.core.workbench.market_continuity import build_continuity


def snapshot():
    history = []
    for day in range(1, 21):
        codes = ["1", "2", "3", "4", "5", "6"] if day <= 15 else ["1", "2", "3", "4", "6", "5"]
        history.append({"date": f"2026-09-{day:02}", "rankings": [
            {"code": code, "name": code, "industry": code, "rank": rank,
             "signal_mode": "etf_fallback", "data_lag_sessions": 0, "signal_lag_sessions": 0}
            for rank, code in enumerate(codes, 1)]})
    return {"as_of": "2026-09-20", "requested_as_of": "2026-09-20", "universe_size": 6,
            "rotation_history": history, "etfs": [{"code": "1", "momentum_20d": -2, "relative_20d": 3}]}


def test_replay_membership_and_observations_not_current_score_or_absolute_strength():
    result = build_continuity(snapshot())
    assert result["current"]
    assert result["summary"] == {"retained": 4, "entered": 1, "leaderPeriods": 20, "leaderChanges": 0}
    assert result["comparisonDate"] == "2026-09-15"
    rows = {row["code"]: row for row in result["rows"]}
    assert rows["6"]["phase"] == "新进前五"
    assert rows["6"]["top5Periods"] == 5
    assert rows["6"]["rankChange"] == 1
    assert rows["5"]["phase"] == "退出前五"
    assert rows["5"]["rankChange"] == -1
    assert rows["1"]["price20dPct"] == -2  # first place can lose money


@pytest.mark.parametrize("case", ["short", "date", "pool", "gap", "stale", "metadata", "mode"])
def test_incomparable_evidence_never_gets_a_continuity_label(case):
    data = deepcopy(snapshot())
    if case == "short":
        data["rotation_history"] = data["rotation_history"][-5:]
    elif case == "date":
        data["requested_as_of"] = "2026-09-21"
    elif case == "pool":
        data["universe_size"] = 7
    elif case == "gap":
        data["rotation_history"][0]["rankings"].pop()
    elif case == "stale":
        data["rotation_history"][0]["rankings"][0]["signal_lag_sessions"] = 1
    elif case == "metadata":
        del data["rotation_history"][0]["rankings"][0]["data_lag_sessions"]
    else:
        data["rotation_history"][0]["rankings"][0]["signal_mode"] = "industry_index"
    result = build_continuity(data)
    assert not result["current"] and result["reasons"]
    assert result["summary"]["entered"] is None
    assert all(row["rankChange"] is None and row["phase"] == "待核验" for row in result["rows"])


def test_empty_is_unknown_not_zero():
    result = build_continuity({})
    assert not result["current"]
    assert result["summary"]["leaderChanges"] is None
    assert result["rows"] == []
