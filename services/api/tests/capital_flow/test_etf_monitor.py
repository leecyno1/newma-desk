from copy import deepcopy
from datetime import date, timedelta

from vibe_visualization_api.capital_flow.etf_monitor import build_etf_monitor, CSI300_POOL


DATES = [(date(2026, 8, 1) + timedelta(days=i)).isoformat() for i in range(65)
         if (date(2026, 8, 1) + timedelta(days=i)).weekday() < 5][-25:]


def fund(code="510300.SH", sign=1):
    return {"code": code, "name": code, "source": "测试来源", "fetchStatus": "ready", "usingSaved": False,
            "asOf": DATES[-1], "summary": {"strength": {"1": {"current": True}}},
            "points": [{"date": day, "shareChangePct": sign * (2 if i == 24 else .01 + i % 4 * .02),
                        "flowYi": sign * (5 if i == 24 else .1), "suspectedSplit": False} for i, day in enumerate(DATES)]}


def test_large_flow_anomaly_and_same_index_alignment():
    result = build_etf_monitor([fund(code) for code in CSI300_POOL], DATES, True)
    assert all(row["flagged"] and row["sameDirection5d"] == 5 for row in result["rows"])
    assert result["cohort"]["flowYi"] == 20
    assert result["cohort"]["sameDirectionPct"] == 100
    assert result["cohort"]["abnormalCount"] == 4
    assert result["rows"][0]["baselineSamples"] == 20
    # Current observation is not part of its own baseline.
    changed = fund()
    changed["points"][-1]["shareChangePct"] = 4
    assert build_etf_monitor([changed], DATES, True)["rows"][0]["medianPct"] == result["rows"][0]["medianPct"]


def test_redemption_and_small_amount_do_not_become_identity_claims():
    etf = fund(sign=-1)
    row = build_etf_monitor([etf], DATES, True)["rows"][0]
    assert row["flagged"] and row["label"] == "大额净赎回异常" and row["robustZ"] < -3
    etf["points"][-1]["flowYi"] = -.5
    assert not build_etf_monitor([etf], DATES, True)["rows"][0]["flagged"]


def test_missing_baseline_and_zero_mad_are_not_neutral_scores():
    missing = fund()
    del missing["points"][-3]
    row = build_etf_monitor([missing], DATES, True)["rows"][0]
    assert row["robustZ"] is None and not row["flagged"]
    assert row["sameDirection5d"] is None
    assert row["baselineSamples"] == 19
    flat = fund()
    for point in flat["points"][:-1]:
        point["shareChangePct"] = 0
    row = build_etf_monitor([flat], DATES, True)["rows"][0]
    assert row["robustZ"] is None and "MAD" in row["reason"]


def test_incomplete_or_stale_cohort_cannot_be_reported_as_all_inflow():
    pool = [fund(code) for code in CSI300_POOL]
    result = build_etf_monitor(pool[:3], DATES, True)
    assert result["cohort"]["available"] == 3
    assert result["cohort"]["sameDirectionPct"] is None and result["cohort"]["flowYi"] is None
    pool[0]["usingSaved"] = True
    result = build_etf_monitor(pool, DATES, True)
    assert not result["rows"][0]["flagged"] and result["rows"][0]["flowYi"] is None
    assert not result["cohort"]["current"]
    assert not any(row["current"] for row in build_etf_monitor(pool, DATES, False)["rows"])


def test_split_and_true_zero_are_distinct():
    pool = [fund(code) for code in CSI300_POOL]
    pool[0]["points"][-1].update(shareChangePct=0, flowYi=0)
    result = build_etf_monitor(pool, DATES, True)
    assert result["cohort"]["inflowCount"] == 3 and result["cohort"]["sameDirectionPct"] == 75
    assert result["rows"][0]["sameDirection5d"] == 0
    split = deepcopy(pool[0])
    split["points"][-1]["suspectedSplit"] = True
    assert not build_etf_monitor([split], DATES, True)["rows"][0]["current"]
