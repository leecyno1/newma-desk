from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.indicator_cycle_contribution import (
    _evaluate_cross_filter_gain,
    build_cross_filter_indicator_cycle_contribution,
    build_indicator_cycle_contribution,
)


def test_contribution_reconstruction_conserves_indicator_value() -> None:
    index = pd.date_range("1960-01-31", periods=780, freq="ME")
    time = np.arange(len(index), dtype=float)
    components = {
        "C2": pd.Series(np.sin(2.0 * np.pi * time / 200.0), index=index),
        "C3": pd.Series(np.sin(2.0 * np.pi * time / 100.0), index=index),
        "C4": pd.Series(np.sin(2.0 * np.pi * time / 42.0), index=index),
        "C5": pd.Series(np.sin(2.0 * np.pi * time / 20.0), index=index),
        "C6": pd.Series(np.sin(2.0 * np.pi * time / 12.0), index=index),
        "C7": pd.Series(np.sin(2.0 * np.pi * time / 6.0), index=index),
    }
    target = (
        0.2
        + 0.6 * components["C2"]
        + 0.4 * components["C3"]
        + 0.3 * components["C4"]
        + 0.2 * components["C5"]
        + 0.1 * components["C6"]
        + 0.05 * components["C7"]
        + pd.Series(np.cos(time / 17.0) * 0.08, index=index)
    )

    result = build_indicator_cycle_contribution(target, components)

    assert result["status"] == "retrospective_diagnostic"
    assert result["eligibleCycles"] == ["C2", "C3", "C4", "C5", "C6", "C7"]
    assert abs(result["current"]["conservationError"]) < 1e-10
    assert sum(
        row["absoluteShare"] for row in result["current"]["components"].values()
    ) == pytest.approx(1.0)
    variance_total = sum(
        row["varianceShare120"]
        for row in result["current"]["components"].values()
    ) + result["diagnostics"]["residualVarianceShare120"]
    assert variance_total == pytest.approx(1.0)


def test_contribution_excludes_cycles_without_three_complete_repeats() -> None:
    index = pd.date_range("2000-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    components = {
        cycle_id: pd.Series(np.sin(2.0 * np.pi * time / period), index=index)
        for cycle_id, period in {
            "C2": 200.0,
            "C3": 100.0,
            "C4": 42.0,
            "C5": 20.0,
            "C6": 12.0,
            "C7": 6.0,
        }.items()
    }
    target = components["C4"] + components["C5"] + components["C6"]

    result = build_indicator_cycle_contribution(target, components)

    assert "C2" not in result["eligibleCycles"]
    assert "C3" not in result["eligibleCycles"]
    assert {"C4", "C5", "C6", "C7"} <= set(result["eligibleCycles"])


def test_annual_long_history_supports_c1_to_c3() -> None:
    index = pd.Index(range(1800, 2025), name="year")
    time = np.arange(len(index), dtype=float)
    periods = {"C1": 50.0, "C2": 200.0 / 12.0, "C3": 100.0 / 12.0}
    components = {
        cycle_id: pd.Series(np.sin(2.0 * np.pi * time / period), index=index)
        for cycle_id, period in periods.items()
    }
    target = 0.5 * components["C1"] + 0.3 * components["C2"] + 0.2 * components["C3"]

    result = build_indicator_cycle_contribution(
        target,
        components,
        periods=periods,
        minimum_observations=40,
    )

    assert result["status"] == "retrospective_diagnostic"
    assert result["eligibleCycles"] == ["C1", "C2", "C3"]
    assert result["current"]["date"] == "2024"


def test_cross_filter_contribution_marks_consistent_paths_stable() -> None:
    index = pd.date_range("1960-01-31", periods=780, freq="ME")
    time = np.arange(len(index), dtype=float)
    components = {
        cycle_id: pd.Series(np.sin(2.0 * np.pi * time / period), index=index)
        for cycle_id, period in {
            "C2": 200.0,
            "C3": 100.0,
            "C4": 42.0,
            "C5": 20.0,
            "C6": 12.0,
            "C7": 6.0,
        }.items()
    }
    target = sum(
        weight * components[cycle_id]
        for cycle_id, weight in {
            "C2": 0.6,
            "C3": 0.5,
            "C4": 0.4,
            "C5": 0.3,
            "C6": 0.2,
            "C7": 0.1,
        }.items()
    )

    result = build_cross_filter_indicator_cycle_contribution(
        target,
        components,
        {cycle_id: series * 1.02 for cycle_id, series in components.items()},
    )

    assert result["status"] == "retrospective_diagnostic"
    assert result["filterRobustness"]["stableCycles"] == 6
    assert result["filterRobustness"]["directionAgreementCycles"] == 6
    assert result["quality"] == "stable"
    assert all(
        component["filterRobustness"]["status"] == "stable"
        for component in result["current"]["components"].values()
    )


def test_cross_track_gain_calibration_adopts_common_training_bias() -> None:
    primary = np.linspace(-1.0, 1.0, 30)
    candidates = [
        {
            "training": (primary, primary * 0.5),
            "validation": (primary, primary * 0.5),
            "audit": (primary, primary * 0.5),
        }
        for _ in range(5)
    ]

    calibration = _evaluate_cross_filter_gain(candidates)

    assert calibration["status"] == "adopted"
    assert calibration["gain"] == pytest.approx(2.0)
    assert calibration["validationRelativeImprovement"] == pytest.approx(1.0)
    assert calibration["auditRelativeImprovement"] == pytest.approx(1.0)


def test_cross_track_gain_calibration_rejects_audit_reversal() -> None:
    primary = np.linspace(-1.0, 1.0, 30)
    candidates = [
        {
            "training": (primary, primary * 0.5),
            "validation": (primary, primary * 0.5),
            "audit": (primary, primary * 2.0),
        }
        for _ in range(5)
    ]

    calibration = _evaluate_cross_filter_gain(candidates)

    assert calibration["status"] == "rejected"
    assert calibration["validationRelativeImprovement"] > 0.0
    assert calibration["auditRelativeImprovement"] < 0.0
