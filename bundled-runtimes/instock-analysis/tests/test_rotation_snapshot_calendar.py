"""Live rankings, history, and factor evidence share one explicit date axis."""

import json

import pandas as pd
import pytest

from instock.core.market_data_provider import MarketDataError
from instock.core.rotation.calendar import align_benchmark_calendar
from instock.core.rotation.rotation_engine import RotationEngine
from instock.core.rotation.rotation_shadow_state import RotationShadowState
from test_rotation_engine import FixtureProvider, UNIVERSE


@pytest.mark.parametrize("position", [100, 144])
def test_missing_current_benchmark_window_does_not_return_old_or_compressed_ranking(position):
    provider = FixtureProvider()
    provider.frames["510300"] = provider.frames["510300"].drop(index=position)
    with pytest.raises(MarketDataError, match="不能确认当前排名.*未回退到旧日期"):
        RotationEngine(provider, universe=UNIVERSE).analyze()


def test_calendar_failure_does_not_fall_back_to_quote_dates():
    provider = FixtureProvider()
    provider.get_trading_calendar = lambda start, end: {"status": "unavailable"}
    with pytest.raises(MarketDataError, match="独立交易日历"):
        RotationEngine(provider, universe=UNIVERSE).analyze()


def test_old_benchmark_gap_preserves_history_days_and_blocks_incomplete_votes(tmp_path):
    provider = FixtureProvider()
    provider.frames["510300"] = provider.frames["510300"].drop(index=80)
    result = RotationEngine(provider, universe=UNIVERSE).analyze()
    history = result["rotation_history"]
    assert [point["date"] for point in history] == provider.sessions[-20:].strftime("%Y-%m-%d").tolist()
    assert [point["state"] for point in history] == ["unavailable"] * 16 + ["available"] * 4
    assert result["summary"]["history_missing_days"] == 16
    assert result["summary"]["rotation_changes_20d"] is None
    assert result["summary"]["leader_streak_days"] == 4
    leader = result["etfs"][0]
    assert leader["persistence_score"] is None
    assert leader["rank_change_5d"] is None
    assert leader["rotation_signal"] != "确认领先"
    consensus = result["parameter_consensus"]
    assert consensus["state"] == "incomplete_models"
    assert consensus["model_count"] == 6
    assert consensus["majority_threshold"] == 5
    assert any("仅6/9组可核验" in text for text in leader["insight"]["evidence"])
    assert consensus["shadow_state"]["models"] == []
    assert not RotationShadowState(str(tmp_path / "shadow.db")).record("510300", consensus["shadow_state"])
    json.dumps(result, allow_nan=False)


def test_daily_gaps_do_not_shorten_shadow_elapsed_sessions():
    provider = FixtureProvider()
    frame = provider.frames["510300"].drop(index=[138, 140])
    aligned, _ = align_benchmark_calendar(provider, frame, {"100001": provider.frames["100001"]}, None,
                                          limit=165, minimum_sessions=61)
    last_rebalance = provider.sessions[134].strftime("%Y-%m-%d")
    shadow = {"strategy_id": RotationEngine.shadow_strategy_id, "as_of": last_rebalance,
              "last_rebalance_date": last_rebalance, "models": [{"id": "fixture"}]}
    schedule = RotationEngine._shadow_schedule(aligned, shadow, enabled=True)
    assert schedule["lifecycle_state"] == "rebalanced"
    assert RotationEngine._session_lag(aligned["date"], provider.sessions[141]) == 3


def test_missing_asset_day_is_not_compressed_into_momentum_window():
    provider = FixtureProvider()
    provider.frames["100001"] = provider.frames["100001"].drop(index=100)
    result = RotationEngine(provider, universe=UNIVERSE).analyze()
    assert "100001" not in {row["code"] for row in result["etfs"]}
    assert any("未压缩缺日" in row["error"] for row in result["failures"])


def test_missing_slow_factor_is_null_and_not_scored_as_neutral():
    provider = FixtureProvider()
    engine = RotationEngine(provider, universe=UNIVERSE)
    baseline = engine.analyze()
    assert all(row["factor_scores"]["valuation"] is None for row in baseline["etfs"])
    day = provider.sessions[-1].strftime("%Y-%m-%d")
    slow = {"as_of": day, "source": "test", "items": {
        item.code: {"valuation_score": 0} for item in UNIVERSE[1:]
    }}
    result = engine.analyze(slow_factors=slow)
    assert "valuation" in result["factor_model"]["active_factors"]
    missing = next(row for row in result["etfs"] if row["code"] == "100001")
    before = next(row for row in baseline["etfs"] if row["code"] == "100001")
    assert missing["factor_scores"]["valuation"] is None
    assert missing["factor_effective_weights"]["valuation"] == 0
    # Reweight only its actual factors; 50 is never inserted as valuation evidence.
    expected = sum(missing["factor_scores"][key] * weight for key, weight in missing["factor_effective_weights"].items() if weight)
    assert missing["total_score"] == pytest.approx(expected, abs=.02)
    observed_zero = next(row for row in result["etfs"] if row["code"] == "100002")
    assert observed_zero["factor_scores"]["valuation"] == 0
    assert observed_zero["factor_effective_weights"]["valuation"] > 0
    assert before["factor_scores"]["valuation"] is None
    json.dumps(result, allow_nan=False)


def test_five_day_rank_change_uses_calendar_endpoints_not_six_observations():
    result = RotationEngine(FixtureProvider(), universe=UNIVERSE).analyze()
    rows = result["etfs"]
    history = result["rotation_history"][-7:]
    code = rows[0]["code"]
    history[1]["rankings"] = [r for r in history[1]["rankings"] if r["code"] != code]
    RotationEngine._attach_rotation_confirmation(rows, history)
    assert rows[0]["history_sample_days"] == 6
    assert rows[0]["rank_change_5d"] is None
    assert rows[0]["persistence_score"] is None
