from copy import deepcopy
from datetime import date, timedelta
import math
import statistics

import pytest

from vibe_visualization_api.capital_flow.appetite import BROAD_POOL, benchmark_analysis, breadth_analysis, build_window


def sample():
    sessions = [(date(2026, 7, 1) + timedelta(days=i)).isoformat() for i in range(60)]
    feed = {"status": "ready", "usingSaved": False, "rows": [
        {"date": day, "ts_code": "000300.SH", "close": 100 - i / 2, "pct_chg": -1 if i % 2 else .5}
        for i, day in enumerate(sessions)]}
    funding = {"expectedDate": sessions[-1], "calendar": {"status": "ready", "dates": sessions},
        "etfs": [{"code": code, "fetchStatus": "ready", "usingSaved": False, "asOf": sessions[-1],
            "summary": {"flow5dYi": 2, "flow20dYi": -3}} for code in BROAD_POOL],
        "leverage": {"fetchStatus": "ready", "asOf": sessions[-1], "summary": {"net5dYi": 20, "net20dYi": -20}}}
    liquidity = {"daily": {"series": [
        {"id": "dr007", "change5Bp": -5, "change20Bp": 4, "current": True, "asOf": sessions[-1]},
        {"id": "spreadBp", "change5Bp": 2, "change20Bp": 1, "current": True, "asOf": sessions[-1]}]},
        "credit": {"social": {"flow3mYoYDiffYi": -100, "current": True, "month": "2026-07"}}}
    return sessions, feed, funding, liquidity


def test_benchmark_compounds_returns_and_computes_sample_vol_and_drawdown():
    sessions, feed, *_ = sample()
    result = benchmark_analysis(feed, sessions, True)
    assert result["current"]
    assert result["return5dPct"] == pytest.approx((.99 ** 3 * 1.005 ** 2 - 1) * 100, abs=1e-4)
    assert result["volatility20dPct"] == pytest.approx(statistics.stdev([-.01, .005] * 10) * math.sqrt(252) * 100, abs=1e-4)
    assert result["maxDrawdown60dPct"] == -29.5


def test_missing_session_never_compresses_window_or_fills_zero():
    sessions, feed, *_ = sample()
    feed["rows"].pop(-3)
    result = benchmark_analysis(feed, sessions, True)
    assert result["return5dPct"] is None
    assert result["return20dPct"] is None
    assert result["volatility20dPct"] is None
    assert result["maxDrawdown60dPct"] is None
    assert len(result["points"]) == 60
    assert result["points"][-3]["close"] is None


def test_window_relationships_and_mixed_frequencies_remain_separate():
    sessions, feed, funding, liquidity = sample()
    market = benchmark_analysis(feed, sessions, True)
    short, long = [build_window(n, funding, liquidity, market) for n in (5, 20)]
    assert short["divergences"] == 2
    assert long["divergences"] == 0
    assert short["verifiedRelationships"] == long["verifiedRelationships"] == 2
    assert short["conditions"]["status"] == "divergent"
    assert long["conditions"]["status"] == "aligned"
    assert short["evidence"][-1] == long["evidence"][-1]  # monthly context is not a daily sum
    assert short["evidence"][3]["scope"] == "5观测日"
    assert short["evidence"][1]["value"] == 6


@pytest.mark.parametrize("failure", ["etf-missing", "etf-saved", "etf-date", "margin-missing", "margin-saved", "calendar", "price-saved"])
def test_incomplete_or_failed_sources_cannot_confirm_relationships(failure):
    sessions, feed, funding, liquidity = sample()
    if failure == "etf-missing":
        funding["etfs"].pop()
    elif failure == "etf-saved":
        funding["etfs"][0].update(fetchStatus="upstream-error", usingSaved=True)
    elif failure == "etf-date":
        funding["etfs"][0]["asOf"] = sessions[-2]
    elif failure == "margin-missing":
        funding["leverage"]["summary"]["net5dYi"] = None
    elif failure == "margin-saved":
        funding["leverage"].update(fetchStatus="permission-denied", usingSaved=True)
    elif failure == "calendar":
        funding["calendar"]["status"] = "upstream-error"
    else:
        feed.update(status="upstream-error", usingSaved=True)
    result = build_window(5, funding, liquidity, benchmark_analysis(feed, sessions, True))
    assert result["verifiedRelationships"] == (0 if failure in {"calendar", "price-saved"} else 1)
    if failure == "etf-missing":
        assert result["evidence"][1]["value"] is None
    if failure == "etf-date":
        assert result["evidence"][1]["asOf"] is None


def test_daily_breadth_has_explicit_missing_and_overlap_boundary():
    sectors = {"asOf": "2026-10-14", "expectedDate": "2026-10-14", "calendar": {"status": "ready"},
        "coverage": {"status": "ready"}, "boards": [
            {"code": str(i), "name": f"行业{i}", "net": net, "pct": pct}
            for i, (net, pct) in enumerate([(1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (None, 1)])]}
    result = breadth_analysis(sectors)
    assert result["current"] and result["comparable"] == 5
    assert all(row["count"] == 1 for row in result["buckets"])
    saved = deepcopy(sectors)
    saved["coverage"]["usingSaved"] = True
    assert not breadth_analysis(saved)["current"]
