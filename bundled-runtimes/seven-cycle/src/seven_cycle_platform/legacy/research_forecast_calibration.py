"""Leakage-controlled walk-forward calibration for retrospective analog forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

import numpy as np
import pandas as pd

from seven_cycle_platform.legacy.research_current_mapping_release import (
    EXPECTED_CYCLE_IDS,
    _circular_distance,
    _cycle_matrix,
    _return_panel,
)


FORECAST_CALIBRATION_FOLD_COLUMNS = (
    "target_type",
    "target_id",
    "horizon_months",
    "validation_origin",
    "training_end",
    "training_path_count",
    "neighbor_count",
    "model_prediction",
    "baseline_prediction",
    "actual_return",
    "model_absolute_error",
    "baseline_absolute_error",
    "model_direction_correct",
    "baseline_direction_correct",
)
FORECAST_CALIBRATION_SUMMARY_COLUMNS = (
    "target_type",
    "target_id",
    "horizon_months",
    "validation_count",
    "model_mae",
    "baseline_mae",
    "mae_improvement",
    "model_direction_accuracy",
    "baseline_direction_accuracy",
    "direction_accuracy_increment",
    "research_gate_passed",
    "status",
    "method",
)
METHOD_ID = "expanding_purged_cycle_analog_walk_forward_v1"


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


@dataclass(frozen=True, slots=True)
class ForecastCalibrationConfig:
    """Walk-forward neighbor, support, and horizon policy."""

    neighbor_count: int = 12
    min_training_paths: int = 24
    min_validation_folds: int = 8
    horizons: tuple[int, ...] = (3, 6, 12)

    def __post_init__(self) -> None:
        neighbors = _positive_integer(self.neighbor_count, name="neighbor_count")
        training = _positive_integer(
            self.min_training_paths,
            name="min_training_paths",
        )
        validations = _positive_integer(
            self.min_validation_folds,
            name="min_validation_folds",
        )
        horizons = tuple(
            _positive_integer(value, name="horizon") for value in self.horizons
        )
        if horizons != (3, 6, 12):
            raise ValueError("horizons must remain exactly 3, 6, and 12")
        if neighbors > training:
            raise ValueError("neighbor_count cannot exceed min_training_paths")
        object.__setattr__(self, "neighbor_count", neighbors)
        object.__setattr__(self, "min_training_paths", training)
        object.__setattr__(self, "min_validation_folds", validations)
        object.__setattr__(self, "horizons", horizons)


@dataclass(frozen=True, slots=True)
class ForecastCalibrationResult:
    """Detached fold-level evidence and aggregated research gates."""

    folds: pd.DataFrame
    summary: pd.DataFrame
    config: ForecastCalibrationConfig

    def __post_init__(self) -> None:
        if tuple(self.folds.columns) != FORECAST_CALIBRATION_FOLD_COLUMNS:
            raise ValueError("folds do not match the calibration contract")
        if tuple(self.summary.columns) != FORECAST_CALIBRATION_SUMMARY_COLUMNS:
            raise ValueError("summary does not match the calibration contract")
        object.__setattr__(self, "folds", self.folds.copy(deep=True))
        object.__setattr__(self, "summary", self.summary.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in {"folds", "summary"} and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def _compound(panel: pd.DataFrame, origin: pd.Timestamp, horizon: int) -> pd.Series:
    dates = pd.date_range(origin + pd.offsets.MonthEnd(1), periods=horizon, freq="ME")
    return (1.0 + panel.loc[dates]).prod(axis=0) - 1.0


def calibrate_retrospective_analog_forecast(
    cycle_phase: pd.DataFrame,
    asset_returns: pd.DataFrame,
    config: ForecastCalibrationConfig | None = None,
) -> ForecastCalibrationResult:
    """Evaluate analog forecasts against an expanding unconditional baseline."""

    normalized_config = config or ForecastCalibrationConfig()
    if not isinstance(normalized_config, ForecastCalibrationConfig):
        raise TypeError("config must be a ForecastCalibrationConfig or None")
    cycles = _cycle_matrix(cycle_phase)
    if tuple(cycles.columns) != EXPECTED_CYCLE_IDS:
        raise ValueError("cycle matrix must retain ordered C1-C7")
    asset_panel, _ = _return_panel(asset_returns)
    fold_rows: list[dict[str, object]] = []
    for horizon in normalized_config.horizons:
        realized_origins = [
            pd.Timestamp(origin)
            for origin in cycles.index
            if pd.date_range(
                pd.Timestamp(origin) + pd.offsets.MonthEnd(1),
                periods=horizon,
                freq="ME",
            )
            .isin(asset_panel.index)
            .all()
        ]
        for validation_origin in realized_origins:
            training_origins = [
                origin
                for origin in realized_origins
                if origin < validation_origin
                and origin + pd.offsets.MonthEnd(horizon) < validation_origin
            ]
            if len(training_origins) < normalized_config.min_training_paths:
                continue
            distances = _circular_distance(
                cycles.loc[training_origins].to_numpy(dtype="float64"),
                cycles.loc[validation_origin].to_numpy(dtype="float64"),
                period=360.0,
            )
            ranked = np.argsort(distances, kind="stable")
            neighbors = [
                training_origins[position]
                for position in ranked[: normalized_config.neighbor_count]
            ]
            all_training = pd.DataFrame(
                [_compound(asset_panel, origin, horizon) for origin in training_origins]
            )
            neighbor_training = pd.DataFrame(
                [_compound(asset_panel, origin, horizon) for origin in neighbors]
            )
            actual = _compound(asset_panel, validation_origin, horizon)
            model = neighbor_training.median(axis=0)
            baseline = all_training.median(axis=0)
            for asset_id in asset_panel.columns:
                actual_value = float(actual[asset_id])
                model_value = float(model[asset_id])
                baseline_value = float(baseline[asset_id])
                fold_rows.append(
                    {
                        "target_type": "asset_return",
                        "target_id": asset_id,
                        "horizon_months": horizon,
                        "validation_origin": validation_origin.date(),
                        "training_end": max(
                            origin + pd.offsets.MonthEnd(horizon)
                            for origin in training_origins
                        ).date(),
                        "training_path_count": len(training_origins),
                        "neighbor_count": len(neighbors),
                        "model_prediction": model_value,
                        "baseline_prediction": baseline_value,
                        "actual_return": actual_value,
                        "model_absolute_error": abs(model_value - actual_value),
                        "baseline_absolute_error": abs(baseline_value - actual_value),
                        "model_direction_correct": (model_value >= 0.0)
                        == (actual_value >= 0.0),
                        "baseline_direction_correct": (baseline_value >= 0.0)
                        == (actual_value >= 0.0),
                    }
                )
    folds = pd.DataFrame(fold_rows, columns=FORECAST_CALIBRATION_FOLD_COLUMNS)
    summary_rows: list[dict[str, object]] = []
    for (target_id, horizon), group in folds.groupby(
        ["target_id", "horizon_months"],
        sort=True,
    ):
        model_mae = float(group["model_absolute_error"].mean())
        baseline_mae = float(group["baseline_absolute_error"].mean())
        improvement = (
            0.0 if baseline_mae == 0.0 else (baseline_mae - model_mae) / baseline_mae
        )
        model_direction = float(group["model_direction_correct"].mean())
        baseline_direction = float(group["baseline_direction_correct"].mean())
        direction_increment = model_direction - baseline_direction
        sufficient = len(group) >= normalized_config.min_validation_folds
        summary_rows.append(
            {
                "target_type": "asset_return",
                "target_id": target_id,
                "horizon_months": int(horizon),
                "validation_count": len(group),
                "model_mae": model_mae,
                "baseline_mae": baseline_mae,
                "mae_improvement": improvement,
                "model_direction_accuracy": model_direction,
                "baseline_direction_accuracy": baseline_direction,
                "direction_accuracy_increment": direction_increment,
                "research_gate_passed": bool(
                    sufficient and improvement > 0.0 and direction_increment >= 0.0
                ),
                "status": "retrospective_only" if sufficient else "unavailable",
                "method": METHOD_ID,
            }
        )
    summary = pd.DataFrame(
        summary_rows,
        columns=FORECAST_CALIBRATION_SUMMARY_COLUMNS,
    )
    return ForecastCalibrationResult(
        folds=folds,
        summary=summary,
        config=normalized_config,
    )


__all__ = [
    "FORECAST_CALIBRATION_FOLD_COLUMNS",
    "FORECAST_CALIBRATION_SUMMARY_COLUMNS",
    "ForecastCalibrationConfig",
    "ForecastCalibrationResult",
    "calibrate_retrospective_analog_forecast",
]
