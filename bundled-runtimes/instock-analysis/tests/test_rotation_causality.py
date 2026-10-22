import numpy as np
import pandas as pd
import pytest
import json

from instock.core.rotation.rotation_experiment import RotationExperiment, ROTATION_WEIGHT_PROFILES, _metrics
from test_rotation_experiment import ExperimentProvider, UNIVERSE


def inputs():
    provider = ExperimentProvider(size=160)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    frames = {code: frame.copy() for code, frame in provider.frames.items() if code != "510300"}
    return experiment, {"benchmark_frame": provider.frames["510300"].copy(),
                        "trade_frames": frames, "signal_frames": frames,
                        "window": 60, "rebalance_days": 10, "cost_bps": 25}


def window(experiment, kwargs):
    return experiment._window_trade_sets(**kwargs, weight_profiles=ROTATION_WEIGHT_PROFILES)


@pytest.mark.parametrize("date_position", [126, 136])
@pytest.mark.parametrize("selected_missing", [True, False])
@pytest.mark.parametrize("remove_row", [False, True])
def test_future_price_missing_does_not_rewrite_signal_or_skip_period(date_position, selected_missing, remove_row):
    experiment, kwargs = inputs()
    before = window(experiment, kwargs)
    winner = before["balanced"][0]["symbol"]
    code = winner if selected_missing else next(code for code in kwargs["trade_frames"] if code != winner)
    if remove_row:
        kwargs["trade_frames"][code] = kwargs["trade_frames"][code].drop(index=date_position).reset_index(drop=True)
    else:
        kwargs["trade_frames"][code].loc[date_position, "open"] = np.nan
    after = window(experiment, kwargs)
    for profile in before:
        for field in ("signal_date", "symbol", "score", "current_leader_symbol", "current_leader_score"):
            assert after[profile][0][field] == before[profile][0][field]
        assert len(after[profile]) == len(before[profile])
    assert after["balanced"][0]["equal_weight_return"] is None
    if selected_missing:
        assert after["balanced"][0]["net_return"] is None
        assert _metrics(after["balanced"], 10)["total_return_pct"] is None
        assert RotationExperiment._equity_curve(after["balanced"])[-1]["strategy"] is None
    else:
        assert after["balanced"][0]["net_return"] == before["balanced"][0]["net_return"]
        assert _metrics(after["balanced"], 10)["equal_weight_return_pct"] is None


def test_confirmation_policies_do_not_rerank_using_future_execution_availability():
    experiment, kwargs = inputs()
    kwargs["weights"] = ROTATION_WEIGHT_PROFILES["balanced"]
    before = experiment._confirmation_trade_sets(**kwargs)
    chosen = before["raw"][0]["symbol"]
    kwargs["trade_frames"][chosen].loc[136, "open"] = np.nan
    after = experiment._confirmation_trade_sets(**kwargs)
    for policy in before:
        assert after[policy][0]["symbol"] == before[policy][0]["symbol"]
        assert after[policy][0]["score"] == before[policy][0]["score"]
        assert len(after[policy]) == len(before[policy])
    assert after["raw"][0]["net_return"] is None


def test_unresolved_votes_are_kept_but_not_counted_as_verified_hit_rates():
    experiment, kwargs = inputs()
    trade_sets = window(experiment, kwargs)
    first = trade_sets["balanced"][0]
    kwargs["trade_frames"][first["symbol"]].loc[136, "open"] = np.nan
    changed = window(experiment, kwargs)
    for vote_source in ("buffered_selection", "current_leader"):
        before = RotationExperiment._parameter_ensemble_trades(trade_sets, cost_bps=25, vote_source=vote_source)
        after = RotationExperiment._parameter_ensemble_trades(changed, cost_bps=25, vote_source=vote_source)
        assert [(row["symbol"], row["vote_count"]) for row in after] == [(row["symbol"], row["vote_count"]) for row in before]
    summary = RotationExperiment._ensemble_signal_summary(changed["balanced"], high_confidence_only=False)
    assert summary["gross_beat_benchmark_rate_pct"] is None
    assert summary["unresolved_samples"] > 0


def test_prediction_missing_20_day_label_keeps_five_day_ranking_and_confidence(monkeypatch):
    experiment, kwargs = inputs()
    kwargs.pop("rebalance_days")
    kwargs.pop("cost_bps")
    kwargs.update(weights=ROTATION_WEIGHT_PROFILES["balanced"], split_date=pd.Timestamp("2023-07-01"))
    captured = []
    original = RotationExperiment._summarize_prediction_records

    def capture(cls, rows):
        captured.extend(rows)
        return original(rows)

    monkeypatch.setattr(RotationExperiment, "_summarize_prediction_records", classmethod(capture))
    experiment._prediction_diagnostics(**kwargs)
    first_date = min(row["signal_date"] for row in captured)
    before = {row["horizon"]: row for row in captured if row["signal_date"] == first_date}
    captured.clear()
    kwargs["trade_frames"]["100001"].loc[146, "open"] = np.nan
    result = experiment._prediction_diagnostics(**kwargs)
    after = {row["horizon"]: row for row in captured if row["signal_date"] == first_date}
    assert after[5] == before[5]
    assert after[10] == before[10]
    assert after[20]["confidence"] == before[20]["confidence"]
    assert after[20]["available"] is False
    assert after[20]["rank_ic"] is None
    assert result["label_coverage"]["missing_periods"] > 0


def test_missing_benchmark_open_does_not_delete_original_decisions():
    experiment, kwargs = inputs()
    before = window(experiment, kwargs)
    kwargs["benchmark_frame"].loc[136, "open"] = np.nan
    after = window(experiment, kwargs)
    assert after["balanced"][0]["symbol"] == before["balanced"][0]["symbol"]
    assert after["balanced"][0]["benchmark_return"] is None
    assert len(after["balanced"]) == len(before["balanced"])


def test_missing_top_three_label_never_promotes_fourth_place():
    result = RotationExperiment._ranking_effect([100, 90, 80, 70, 60], [None, .1, .2, .3, .4], 0)
    assert result["available"] is False
    assert result["top3_beat_benchmark"] is None


def test_all_missing_prediction_labels_return_null_statistics_without_crashing():
    experiment, kwargs = inputs()
    kwargs.pop("rebalance_days")
    kwargs.pop("cost_bps")
    for frame in kwargs["trade_frames"].values():
        frame.loc[126:, "open"] = np.nan
    result = experiment._prediction_diagnostics(**kwargs, weights=ROTATION_WEIGHT_PROFILES["balanced"],
                                                 split_date=pd.Timestamp("2023-07-01"))
    for row in result["all"]["horizons"]:
        assert row["samples"] == 0
        assert row["rank_ic_mean"] is None
        assert row["top3_beat_benchmark_rate_pct"] is None
        assert row["top3_beat_benchmark_wilson_95_pct"] is None
    assert result["best_observed_horizon_sessions"] == 0
    json.dumps(result, allow_nan=False)


def test_oos_missing_execution_does_not_reselect_training_variant_or_compound_gaps():
    provider = ExperimentProvider(size=360)
    experiment = RotationExperiment(provider, universe=UNIVERSE)
    before = experiment.run()
    # First OOS entry is position 236; a missing exit at 246 cannot be used
    # as an eligibility check when choosing parameters from the training set.
    for code, frame in provider.frames.items():
        if code != "510300":
            frame.loc[246, "open"] = np.nan
    after = experiment.run()
    assert after["selected_variant"]["id"] == before["selected_variant"]["id"]
    assert after["selected_variant"]["train"] == before["selected_variant"]["train"]
    assert after["summary"]["oos_return_pct"] is None
    assert after["summary"]["positive_variant_share_pct"] is None
    assert after["equity_curve"][-1]["strategy"] is None
    assert after["daily_risk"]["strategy"]["max_drawdown_pct"] is None
    assert after["execution_audit"]["unresolved_decisions"]
    assert after["confirmation_comparison"]["selected_policy"]["id"] == before["confirmation_comparison"]["selected_policy"]["id"]
    assert all(row["total_return_pct"] is None for row in after["stress_tests"])
    assert after["verdict"]["state"] == "insufficient_evidence"
    json.dumps(after, allow_nan=False)
