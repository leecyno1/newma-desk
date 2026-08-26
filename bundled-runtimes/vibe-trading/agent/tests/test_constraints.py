from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.constraints import apply_constraints_frame, load_constraints


def test_constraints_preserve_signs_and_process_dates_independently() -> None:
    frame = pd.DataFrame(
        [[0.7, -0.2, 0.1], [-0.1, 0.8, 0.1]],
        columns=["A", "B", "C"],
        index=pd.date_range("2025-01-01", periods=2),
    )
    constraints = load_constraints({"constraints": [{"type": "max_weight", "cap": 0.5}]})

    result = apply_constraints_frame(frame, constraints)

    np.testing.assert_array_equal(np.sign(result), np.sign(frame))
    assert result.abs().max().max() <= 0.5 + 1e-9
    assert result.abs().sum(axis=1).tolist() == pytest.approx([1.0, 1.0])


def test_constraint_composition_is_idempotent_when_feasible() -> None:
    frame = pd.DataFrame([[0.65, 0.25, 0.1]], columns=["A", "B", "C"])
    constraints = load_constraints(
        {
            "constraints": [
                {"type": "max_weight", "cap": 0.5},
                {"type": "min_weight", "floor": 0.1},
                {
                    "type": "group_exposure",
                    "groups": {"A": "growth", "B": "growth", "C": "defensive"},
                    "caps": {"growth": 0.8},
                },
            ]
        }
    )

    once = apply_constraints_frame(frame, constraints)
    twice = apply_constraints_frame(once, constraints)

    pd.testing.assert_frame_equal(once, twice)


def test_infeasible_max_weight_fails_closed() -> None:
    frame = pd.DataFrame([[0.6, 0.4]], columns=["A", "B"])
    constraints = load_constraints({"constraints": [{"type": "max_weight", "cap": 0.4}]})
    with pytest.raises(ValueError, match="infeasible"):
        apply_constraints_frame(frame, constraints)


def test_later_floor_cannot_silently_break_earlier_group_cap() -> None:
    frame = pd.DataFrame([[0.7, 0.2, 0.1]], columns=["A", "B", "C"])
    constraints = load_constraints(
        {
            "constraints": [
                {
                    "type": "group_exposure",
                    "groups": {"A": "tech", "B": "tech", "C": "other"},
                    "caps": {"tech": 0.5},
                },
                {"type": "min_weight", "floor": 0.25},
            ]
        }
    )
    with pytest.raises(ValueError, match="constraint composition is infeasible"):
        apply_constraints_frame(frame, constraints)


def test_constraint_config_validation() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        load_constraints({"constraints": {"type": "max_weight", "cap": 0.5}})
    with pytest.raises(ValueError, match="unknown constraint"):
        load_constraints({"constraints": [{"type": "mystery"}]})
