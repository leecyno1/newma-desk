"""Scheduled signal gaps must not vanish from performance or holding state."""

import json

import pytest
import pandas as pd

from instock.core.market_data_provider import MarketDataError
from instock.core.rotation.rotation_experiment import RotationExperiment, ROTATION_WEIGHT_PROFILES, _metrics
from instock.core.rotation.rotation_risk import daily_rotation_risk
from test_rotation_causality import inputs, window
from test_rotation_experiment import ExperimentProvider, UNIVERSE


@pytest.mark.parametrize("signal_position", [125, 135, 145])
def test_leading_middle_trailing_signal_gaps_keep_full_calendar(signal_position):
    experiment, kwargs = inputs()
    before = window(experiment, kwargs)
    # Signal data alone disappears; execution bars remain complete. A missing
    # decision must not be misclassified as missing future execution prices.
    kwargs["signal_frames"] = {
        code: frame.drop(index=range(signal_position - 5, signal_position + 1)).reset_index(drop=True)
        for code, frame in kwargs["signal_frames"].items()
    }
    changed = window(experiment, kwargs)
    policies = experiment._confirmation_trade_sets(**kwargs, weights=ROTATION_WEIGHT_PROFILES["balanced"])
    expected = [(row["entry_date"], row["exit_date"]) for row in before["balanced"]]
    for rows in [*changed.values(), *policies.values()]:
        assert [(row["entry_date"], row["exit_date"]) for row in rows] == expected
        gap = rows[(signal_position - 125) // 10]
        assert gap["decision_issue"] == "insufficient_signal_coverage"
        assert gap["symbol"] is None  # Never CASH, nor the prior held ETF.
        assert gap["benchmark_return"] is not None
        assert gap["gross_return"] is None
        assert _metrics(rows, 10)["total_return_pct"] is None
        assert experiment._stress_metrics(rows, rebalance_days=10, cost_bps=50)["total_return_pct"] is None
        curve = experiment._equity_curve(rows)
        assert curve[-1]["strategy"] is None
        assert curve[-1]["benchmark"] is not None
    risk = daily_rotation_risk(changed["balanced"], trade_frames=kwargs["trade_frames"],
                               sessions=kwargs["benchmark_frame"]["date"],
                               benchmark_frame=kwargs["benchmark_frame"], expected_periods=expected)
    assert risk["strategy"]["max_drawdown_pct"] is None
    assert risk["strategy"]["ending_nav"] is None
    assert risk["benchmark"]["state"] == "complete"
    for source in ("buffered_selection", "current_leader"):
        votes = experiment._parameter_ensemble_trades(changed, cost_bps=25, vote_source=source)
        assert [(row["entry_date"], row["exit_date"]) for row in votes] == expected
        assert _metrics(votes, 10)["total_return_pct"] is None
        summary = experiment._ensemble_signal_summary(votes, high_confidence_only=True)
        assert summary["gross_beat_benchmark_rate_pct"] is None
        assert summary["unclassified_periods"] >= 1
        json.dumps(votes, allow_nan=False)


def test_buffer_recovery_requires_unambiguous_holding_and_then_unambiguous_cost():
    rankings = [{"code": "A", "rank": 1, "total_score": 90},
                {"code": "B", "rank": 2, "total_score": 89}]
    chosen, possible, _ = RotationExperiment._decision_from_possible_holdings(rankings, {None, "A", "B"})
    assert chosen is None
    assert possible == {"A", "B"}
    # A decisive lead resolves the new holding, but not whether this period
    # incurred switching costs. The next period has an exact holding state.
    rankings[1]["total_score"] = 10
    chosen, possible, switched = RotationExperiment._decision_from_possible_holdings(rankings, possible)
    assert chosen["code"] == "A"
    assert possible == {"A"}
    assert switched is None
    chosen, possible, switched = RotationExperiment._decision_from_possible_holdings(rankings, possible)
    assert switched is False
    # Confirmed-only can deterministically choose CASH; it is not a gap.
    chosen, possible, switched = RotationExperiment._decision_from_possible_holdings(rankings, {"A"}, "confirmed_only")
    assert chosen is None and possible == {None} and switched is True


def test_incomplete_model_vote_preserves_calendar_and_does_not_renormalize_votes():
    experiment, kwargs = inputs()
    sets = window(experiment, kwargs)
    sets["balanced"].pop(1)
    for source in ("buffered_selection", "current_leader"):
        votes = experiment._parameter_ensemble_trades(sets, cost_bps=25, vote_source=source)
        assert len(votes) == 3
        assert votes[1]["vote_count"] is None
        assert votes[1]["decision_issue"] == "incomplete_parameter_votes"
        assert votes[2]["symbol"] is not None
        assert votes[2]["transaction_cost"] is None
        assert votes[2]["net_return"] is None
        assert experiment._stress_metrics(votes, rebalance_days=10, cost_bps=50)["total_return_pct"] is None


def test_oos_decision_gap_keeps_selection_and_expected_period_counts():
    provider = ExperimentProvider(size=360)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    before = experiment.run()
    for code, frame in list(provider.frames.items()):
        if code != "510300":
            provider.frames[code] = frame.drop(index=range(240, 246)).reset_index(drop=True)
    result = experiment.run()
    assert result["selected_variant"]["id"] == before["selected_variant"]["id"]
    assert result["selected_variant"]["train"] == before["selected_variant"]["train"]
    audit = result["execution_audit"]
    assert audit["planned_oos_periods"] == before["execution_audit"]["planned_oos_periods"]
    assert audit["missing_signal_periods"] == 1
    assert audit["uncertain_holding_periods"] >= 1
    assert audit["planned_oos_periods"] == result["daily_risk"]["strategy"]["coverage"]["expected_periods"]
    assert result["summary"]["oos_return_pct"] is None
    assert result["equity_curve"][-1]["strategy"] is None
    assert all(row["total_return_pct"] is None for row in result["stress_tests"])
    for policy in result["confirmation_comparison"]["policies"]:
        assert policy["out_of_sample"]["execution_state"] == "incomplete"
    assert result["parameter_ensemble"]["out_of_sample"]["strategy"]["execution_state"] == "incomplete"
    json.dumps(result, allow_nan=False)


def test_training_decision_gap_cannot_be_hidden_by_dropping_periods():
    provider = ExperimentProvider(size=360)
    for code, frame in list(provider.frames.items()):
        if code != "510300":
            provider.frames[code] = frame.drop(index=range(120, 126)).reset_index(drop=True)
    with pytest.raises(MarketDataError, match="训练段缺少"):
        RotationExperiment(provider, universe=UNIVERSE).run()


@pytest.mark.parametrize("missing_position", [0, 245, 246, 250, 256, 359])
def test_independent_axis_survives_whole_benchmark_row_loss(missing_position):
    provider = ExperimentProvider(size=360)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    benchmark, trades, signals, _, _ = experiment._load_frames("510300", None)
    aligned, before = experiment._calendar_frame(benchmark, trades, None)
    changed, audit = experiment._calendar_frame(benchmark.drop(index=missing_position), trades, None)
    assert changed["date"].equals(aligned["date"])
    assert audit["session_count"] == 360
    assert audit["session_start"] == before["session_start"]
    assert audit["session_end"] == before["session_end"]
    assert audit["missing_benchmark_dates"] == [provider.sessions[missing_position].strftime("%Y-%m-%d")]
    assert pd.isna(changed.iloc[missing_position]["open"])


@pytest.mark.parametrize("missing_position", [245, 246, 250, 256])
def test_benchmark_loss_preserves_scheduled_decisions_and_predictions(missing_position):
    provider = ExperimentProvider(size=360)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    benchmark, trades, signals, _, _ = experiment._load_frames("510300", None)
    baseline, _ = experiment._calendar_frame(benchmark, trades, None)
    changed, _ = experiment._calendar_frame(benchmark.drop(index=missing_position), trades, None)
    kwargs = dict(trade_frames=trades, signal_frames=signals, window=60, rebalance_days=10, cost_bps=25)
    before = experiment._window_trade_sets(benchmark_frame=baseline, **kwargs, weight_profiles=ROTATION_WEIGHT_PROFILES)
    after = experiment._window_trade_sets(benchmark_frame=changed, **kwargs, weight_profiles=ROTATION_WEIGHT_PROFILES)
    policies = experiment._confirmation_trade_sets(benchmark_frame=changed, **kwargs, weights=ROTATION_WEIGHT_PROFILES["balanced"])
    expected = [(r["signal_date"], r["entry_date"], r["exit_date"]) for r in before["balanced"]]
    for rows in [*after.values(), *policies.values()]:
        assert [(r["signal_date"], r["entry_date"], r["exit_date"]) for r in rows] == expected
        decision = next(row for row in rows if row["signal_date"] == provider.sessions[245].strftime("%Y-%m-%d"))
        if missing_position == 245:
            assert decision["decision_issue"] == "missing_benchmark_signal"
            assert decision["symbol"] is None
        elif missing_position in (246, 256):
            assert decision["benchmark_return"] is None
            assert decision["symbol"] is not None or decision.get("selection_policy") == "confirmed_only"
    diagnostics = experiment._prediction_diagnostics(benchmark_frame=changed, trade_frames=trades,
        signal_frames=signals, window=60, weights=ROTATION_WEIGHT_PROFILES["balanced"], split_date=provider.sessions[234])
    assert diagnostics["label_coverage"]["expected_periods"] == len(range(125, 360 - 21, 5)) * 3
    assert diagnostics["label_coverage"]["missing_periods"] > 0


def test_calendar_failure_is_not_replaced_by_price_dates():
    provider = ExperimentProvider(size=360)
    provider.get_trading_calendar = lambda start, end: {"status": "unavailable"}
    with pytest.raises(MarketDataError, match="独立交易日历"):
        RotationExperiment(provider, universe=UNIVERSE).run()


def test_provider_backfilled_older_quote_does_not_shift_800_session_window():
    provider = ExperimentProvider(size=820)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    benchmark, trades, _, _, _ = experiment._load_frames("510300", None)
    before, _ = experiment._calendar_frame(benchmark, trades, None)
    provider.frames["510300"] = provider.frames["510300"].drop(index=600).reset_index(drop=True)
    benchmark, trades, _, _, _ = experiment._load_frames("510300", None)
    after, audit = experiment._calendar_frame(benchmark, trades, None)
    assert before["date"].equals(after["date"])
    assert audit["session_count"] == 800
    assert audit["missing_benchmark_dates"] == [provider.sessions[600].strftime("%Y-%m-%d")]


def test_missing_signal_confidence_is_not_zero_in_training_threshold():
    effect = RotationExperiment._ranking_effect([1, 2, 3, 4], [.01, .02, .03, .04], 0)
    valid = {**effect, "horizon": 10, "confidence": {"score": 80},
             "entry_date": "2023-01-02", "exit_date": "2023-01-16"}
    missing = {**valid, **RotationExperiment._ranking_effect([], [], None), "confidence": {}}
    result = RotationExperiment._confidence_diagnostics([valid, *[missing] * 9], [valid], horizon=10)
    assert result["threshold"] == 80
    assert result["train"]["all"]["expected_samples"] == 10
    assert result["train"]["high_confidence"]["samples"] == 1


def test_oos_benchmark_gap_does_not_move_training_split_or_shorten_daily_path():
    provider = ExperimentProvider(size=360)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    before = experiment.run()
    provider.frames["510300"] = provider.frames["510300"].drop(index=250).reset_index(drop=True)
    after = experiment.run()
    assert after["rules"]["split"] == before["rules"]["split"]
    assert after["selected_variant"]["id"] == before["selected_variant"]["id"]
    assert after["selected_variant"]["train"] == before["selected_variant"]["train"]
    assert after["execution_audit"]["planned_oos_periods"] == before["execution_audit"]["planned_oos_periods"]
    assert after["daily_risk"]["benchmark"]["coverage"]["expected_closes"] == before["daily_risk"]["benchmark"]["coverage"]["expected_closes"]
    assert after["daily_risk"]["benchmark"]["coverage"]["observed_closes"] == before["daily_risk"]["benchmark"]["coverage"]["observed_closes"] - 1
    assert after["daily_risk"]["benchmark"]["max_drawdown_pct"] is None
    assert after["summary"]["oos_return_pct"] is None
    json.dumps(after, allow_nan=False)
