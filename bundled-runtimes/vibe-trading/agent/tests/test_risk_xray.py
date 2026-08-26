from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backtest.risk_xray import (
    average_invested_weights,
    compute_risk_xray,
    write_risk_xray,
)


def _closes(values: dict[str, object]) -> pd.DataFrame:
    length = max(len(value) for value in values.values())
    return pd.DataFrame(values, index=pd.date_range("2025-01-01", periods=length))


def test_risk_xray_is_strict_json_and_computes_concentration() -> None:
    closes = _closes(
        {
            "A": np.arange(100.0, 160.0),
            "B": np.arange(50.0, 110.0),
            "C": np.arange(200.0, 260.0),
        }
    )
    report = compute_risk_xray(closes, {"A": 0.5, "B": 0.25, "C": 0.25})

    assert report["concentration"]["hhi"] == pytest.approx(0.375)
    assert report["concentration"]["effective_n"] == pytest.approx(1 / 0.375)
    json.dumps(report, allow_nan=False)


def test_risk_xray_filters_thin_symbols_and_rejects_zero_surviving_weight() -> None:
    closes = _closes(
        {
            "A": np.arange(100.0, 140.0),
            "THIN": [1.0] + [np.nan] * 39,
        }
    )
    with pytest.raises(ValueError, match="zero total weight"):
        compute_risk_xray(closes, {"A": 0.0, "THIN": 1.0}, min_history=10)


def test_risk_xray_rejects_long_short_average_basket() -> None:
    frame = pd.DataFrame({"A": [0.5, 0.5], "B": [-0.2, -0.2]})
    with pytest.raises(ValueError, match="net short.*B"):
        average_invested_weights(frame)


def test_risk_xray_constant_prices_never_emit_nan(tmp_path) -> None:
    closes = _closes({"A": [10.0] * 40, "B": [20.0] * 40})
    report = compute_risk_xray(closes, {"A": 0.5, "B": 0.5})
    path = tmp_path / "risk_xray.json"

    payload = write_risk_xray(path, report)

    assert json.loads(path.read_text(encoding="utf-8")) == payload
    json.dumps(payload, allow_nan=False)
