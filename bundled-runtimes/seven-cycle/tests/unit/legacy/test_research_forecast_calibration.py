from __future__ import annotations

import numpy as np
import pandas as pd

from seven_cycle_platform.legacy.research_forecast_calibration import (
    FORECAST_CALIBRATION_FOLD_COLUMNS,
    FORECAST_CALIBRATION_SUMMARY_COLUMNS,
    ForecastCalibrationConfig,
    calibrate_retrospective_analog_forecast,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.date_range("2016-01-31", periods=96, freq="ME")
    cycle_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    for month_number, month in enumerate(months):
        latent = 2.0 * np.pi * month_number / 24.0
        for position in range(1, 8):
            cycle_rows.append(
                {
                    "date": month,
                    "cycle_id": f"C{position}",
                    "angle": float(np.degrees(latent * position) % 360.0),
                }
            )
        alpha = float(0.02 * np.sin(latent) + 0.003)
        beta = float(-0.01 * np.sin(latent) + 0.001)
        for asset_id, asset_return, benchmark_return in (
            ("asset_alpha", alpha, beta),
            ("asset_beta", beta, alpha),
        ):
            return_rows.append(
                {
                    "date": month,
                    "asset_id": asset_id,
                    "return": asset_return,
                    "benchmark_return": benchmark_return,
                }
            )
    return pd.DataFrame(cycle_rows), pd.DataFrame(return_rows)


def test_walk_forward_calibration_uses_only_fully_realized_prior_paths() -> None:
    cycles, returns = _inputs()
    result = calibrate_retrospective_analog_forecast(
        cycles,
        returns,
        ForecastCalibrationConfig(
            neighbor_count=8,
            min_training_paths=16,
            min_validation_folds=8,
        ),
    )

    assert tuple(result.folds.columns) == FORECAST_CALIBRATION_FOLD_COLUMNS
    assert tuple(result.summary.columns) == FORECAST_CALIBRATION_SUMMARY_COLUMNS
    assert not result.folds.empty
    assert (result.folds["training_end"] < result.folds["validation_origin"]).all()
    assert result.folds["neighbor_count"].eq(8).all()
    assert set(result.summary["horizon_months"]) == {3, 6, 12}
    assert set(result.summary["target_id"]) == {"asset_alpha", "asset_beta"}
    assert result.summary["validation_count"].ge(8).all()
    assert result.summary["status"].eq("retrospective_only").all()
    assert np.isfinite(
        result.summary[["model_mae", "baseline_mae", "mae_improvement"]].to_numpy(
            dtype="float64"
        )
    ).all()
