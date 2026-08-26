from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backtest.rebalance_notes import compute_rebalance_notes, write_rebalance_notes


def test_rebalance_notes_capture_entries_exits_and_turnover(tmp_path) -> None:
    frame = pd.DataFrame(
        [[0.5, 0.5], [0.75, 0.25], [0.0, 1.0]],
        columns=["A", "B"],
        index=pd.date_range("2025-01-01", periods=3),
    )
    notes = compute_rebalance_notes(frame)

    assert notes["summary"] == {
        "rebalance_count": 2,
        "turnover_total": pytest.approx(1.0),
        "turnover_mean": pytest.approx(0.5),
        "turnover_max": pytest.approx(0.75),
        "largest_rebalance_date": "2025-01-03",
    }
    assert notes["rebalances"][1]["exits"] == [{"code": "A", "weight": 0.75}]

    path = tmp_path / "rebalance_notes.json"
    payload = write_rebalance_notes(path, notes)
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_rebalance_notes_are_stable_for_noops_and_nan_cells() -> None:
    frame = pd.DataFrame(
        [[0.5, np.nan], [0.5 + 1e-9, 0.0], [0.5, 0.5]],
        columns=["A", "B"],
        index=pd.date_range("2025-01-01", periods=3),
    )
    notes = compute_rebalance_notes(frame)

    assert notes["summary"]["rebalance_count"] == 1
    assert notes["rebalances"][0]["entries"] == [{"code": "B", "weight": 0.5}]


def test_rebalance_notes_reject_non_finite_targets() -> None:
    frame = pd.DataFrame([[0.5], [np.inf]], columns=["A"])
    with pytest.raises(ValueError, match="non-finite"):
        compute_rebalance_notes(frame)
