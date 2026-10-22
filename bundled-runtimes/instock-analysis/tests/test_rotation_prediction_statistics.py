"""Undefined correlations and tied memberships are not observed failures."""

import pytest

from instock.core.rotation.rotation_experiment import RotationExperiment as Experiment


def effect(scores, returns, benchmark=0):
    return Experiment._ranking_effect(scores, returns, benchmark)


def test_constant_scores_are_complete_labels_but_undefined_predictions():
    row = effect([50] * 6, [.1, -.2, .3, .4, -.5, .6])
    assert row["available"] is True
    assert row["rank_ic"] is None
    assert row["top3_minus_bottom3"] is None
    assert row["top3_beat_benchmark"] is None
    assert row["leader_beat_benchmark"] is None
    summary = Experiment._effect_summary([row], horizon=10)
    assert summary["samples"] == 1
    assert summary["missing_samples"] == 0
    assert summary["rank_ic_samples"] == summary["top3_hit_samples"] == 0
    assert summary["top3_beat_benchmark_rate_pct"] is None
    assert summary["top3_beat_benchmark_wilson_95_pct"] is None


def test_constant_returns_leave_measurable_zero_spread_and_hit_rate():
    row = effect([6, 5, 4, 3, 2, 1], [.1] * 6)
    assert row["rank_ic"] is None
    assert row["top3_minus_bottom3"] == 0
    assert row["top3_beat_benchmark"] is True
    assert row["top3_beat_median"] is False
    assert effect([6, 5, 4, 3, 2, 1], [.1] * 6, benchmark=.1)["top3_beat_benchmark"] is False


def test_genuine_zero_ic_is_preserved_but_overlapping_groups_are_not_spread():
    row = effect([1, 2, 3, 4], [2, 4, 1, 3])
    assert row["rank_ic"] == pytest.approx(0)
    assert row["top3_minus_bottom3"] is None
    assert row["top3_beat_benchmark"] is True
    assert row["metric_issues"] == ["fewer_than_six_assets"]


@pytest.mark.parametrize("scores", [[6, 5, 4, 4, 2, 1], [6, 6, 4, 3, 2, 1], [6, 5, 5, 3, 2, 1]])
def test_ties_are_invariant_to_input_permutation(scores):
    returns = [.1, -.2, .3, -.4, .5, -.6]
    reference = effect(scores, returns)
    for indices in ([5, 4, 3, 2, 1, 0], [1, 3, 5, 0, 2, 4]):
        assert effect([scores[i] for i in indices], [returns[i] for i in indices]) == reference
    if scores[2] == scores[3]:
        assert reference["top3_beat_benchmark"] is None
    else:
        assert reference["top3_beat_benchmark"] is not None
    assert (reference["leader_beat_benchmark"] is None) == (scores[0] == scores[1])


def test_metric_specific_denominators_and_missing_labels_are_separate():
    rows = [effect([1] * 6, list(range(6))),
            effect(list(range(6)), [.1] * 6),
            effect(list(range(6)), list(range(6))),
            effect(list(range(6)), [None, 1, 2, 3, 4, 5])]
    summary = Experiment._effect_summary(rows, horizon=5)
    assert (summary["expected_samples"], summary["samples"], summary["missing_samples"]) == (4, 3, 1)
    assert summary["rank_ic_samples"] == 1
    assert summary["rank_ic_mean"] == 1
    assert summary["spread_samples"] == summary["top3_hit_samples"] == 2
    assert summary["top3_beat_benchmark_rate_pct"] == 100
    assert summary["effective_non_overlapping_samples"] == 2
    assert summary["metric_issue_counts"]["constant_scores"] == 1
    horizon = Experiment._summarize_prediction_records([{**row, "horizon": 5} for row in rows])["horizons"][0]
    assert horizon["rank_ic_samples"] == 1
    assert horizon["leader_beat_benchmark_samples"] == 2
    assert horizon["top3_beat_benchmark_rate_pct"] == 100


def test_ablation_compares_paired_sections_not_two_different_averages():
    rows = [
        {"available": True, "rank_ic": .5, "top3_beat_benchmark": True,
         "ablation_effects": {"momentum": {"available": True, "rank_ic": .3, "top3_beat_benchmark": False}}},
        {"available": True, "rank_ic": -.9, "top3_beat_benchmark": False,
         "ablation_effects": {"momentum": {"available": True, "rank_ic": None, "top3_beat_benchmark": None}}},
    ]
    assert Experiment._paired_ablation_delta(rows, "momentum", "rank_ic") == {"samples": 1, "delta": .2}
    assert Experiment._paired_ablation_delta(rows, "momentum", "top3_beat_benchmark", scale=100) == {"samples": 1, "delta": 100}


def test_constant_factor_is_not_classified_as_weak_or_stable():
    constant = effect([1] * 6, list(range(6)))
    row = {**effect(list(range(6)), list(range(6))), "horizon": 10,
           "factor_effects": {"momentum": constant}, "ablation_effects": {"momentum": constant}}
    result = Experiment._factor_effectiveness([row], [row], {"active_factors": ["momentum"]}, horizon=10)
    factor = next(item for item in result["factors"] if item["factor"] == "momentum")
    assert factor["state"] == "undefined_ic"
    assert factor["leave_one_out"]["rank_ic_contribution_oos"] is None
    assert factor["leave_one_out"]["paired_samples"]["rank_ic_oos"] == 0


def test_all_tied_composites_do_not_choose_best_horizon_or_confidence_threshold(monkeypatch):
    import json
    import pandas as pd
    from test_rotation_experiment import ExperimentProvider, UNIVERSE
    from instock.core.rotation.rotation_engine import RotationEngine, ROTATION_WEIGHT_PROFILES

    original = RotationEngine._score_factor_frame

    def tied_scores(self, *args, **kwargs):
        return [{**row, "total_score": 50.0} for row in original(self, *args, **kwargs)]

    monkeypatch.setattr(RotationEngine, "_score_factor_frame", tied_scores)
    provider = ExperimentProvider(size=360)
    experiment = Experiment(provider, universe=UNIVERSE)
    benchmark, trades, signals, _, _ = experiment._load_frames("510300", None)
    result = experiment._prediction_diagnostics(benchmark_frame=benchmark, trade_frames=trades,
        signal_frames=signals, weights=ROTATION_WEIGHT_PROFILES["balanced"], window=60,
        split_date=pd.Timestamp(benchmark.iloc[234]["date"]))
    assert result["label_coverage"]["missing_periods"] == 0
    assert result["verdict"]["state"] == "undefined_ic"
    assert result["best_observed_horizon_sessions"] == 0
    assert result["confidence_diagnostics"]["threshold"] is None
    for row in result["all"]["horizons"]:
        assert row["samples"] > 0
        assert row["rank_ic_samples"] == row["top3_hit_samples"] == 0
    json.dumps(result, allow_nan=False)
