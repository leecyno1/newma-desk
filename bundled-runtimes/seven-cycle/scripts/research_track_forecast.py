#!/usr/bin/env python3
"""Build validated track-level conditional forecasts for the market surface."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


VALIDATION_HORIZONS = (3, 6, 12)
FORECAST_MONTHS = 24
RIDGE_ALPHA = 4.0
MIN_TRAIN_ORIGINS = 60
MIN_TEST_ORIGINS = 12
MAX_INPUT_LAG_MONTHS = 6


@dataclass(frozen=True, slots=True)
class _RidgeModel:
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    target_mean: float
    coefficients: np.ndarray

    def predict(self, features: np.ndarray) -> np.ndarray:
        standardized = (features - self.feature_mean) / self.feature_scale
        return self.target_mean + standardized @ self.coefficients


def _json_number(value: float | int | None) -> float | int | None:
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def _monthly_series(series: pd.Series) -> pd.Series:
    clean = series.astype(float).copy()
    if not isinstance(clean.index, pd.PeriodIndex):
        clean.index = pd.to_datetime(clean.index).to_period("M")
    clean = clean.groupby(clean.index).last().sort_index()
    if clean.empty:
        return clean
    return clean.reindex(pd.period_range(clean.index.min(), clean.index.max(), freq="M"))


def _feature_vector(
    series: pd.Series,
    c4_history: pd.Series,
    origin: int,
    horizon: int,
    *,
    future_c4: dict[pd.Period, float] | None = None,
) -> np.ndarray | None:
    lag_positions = [origin - lag for lag in (0, 1, 2, 3, 6, 12)]
    if min(lag_positions) < 0:
        return None
    lag_values = series.iloc[lag_positions]
    recent = series.iloc[origin - 5 : origin + 1]
    if lag_values.isna().any() or recent.isna().any():
        return None
    origin_period = series.index[origin]
    target_period = origin_period + horizon
    c4_origin = c4_history.get(origin_period)
    c4_target = c4_history.get(target_period)
    if c4_origin is None and future_c4 is not None:
        c4_origin = future_c4.get(origin_period)
    if c4_target is None and future_c4 is not None:
        c4_target = future_c4.get(target_period)
    if c4_origin is None or c4_target is None:
        return None
    if not np.isfinite(c4_origin) or not np.isfinite(c4_target):
        return None
    target_month = target_period.month
    values = [float(value) for value in lag_values]
    values.extend(
        [
            float(series.iloc[origin] - series.iloc[origin - 1]),
            float(series.iloc[origin] - series.iloc[origin - 3]),
            float(series.iloc[origin - 2 : origin + 1].mean()),
            float(recent.mean()),
            float(recent.std(ddof=0)),
            float(c4_origin),
            float(c4_target),
            math.sin(2.0 * math.pi * target_month / 12.0),
            math.cos(2.0 * math.pi * target_month / 12.0),
            horizon / 12.0,
        ]
    )
    return np.asarray(values, dtype=float)


def _fit_model(
    features: np.ndarray,
    target: np.ndarray,
) -> _RidgeModel:
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0, ddof=0)
    feature_scale = np.where(feature_scale < 1e-8, 1.0, feature_scale)
    standardized = (features - feature_mean) / feature_scale
    target_mean = float(target.mean())
    centered_target = target - target_mean
    penalty = RIDGE_ALPHA * np.eye(standardized.shape[1], dtype=float)
    coefficients = np.linalg.solve(
        standardized.T @ standardized + penalty,
        standardized.T @ centered_target,
    )
    return _RidgeModel(
        feature_mean=feature_mean,
        feature_scale=feature_scale,
        target_mean=target_mean,
        coefficients=coefficients,
    )


def _local_projection(series: pd.Series, origin: int, horizon: int) -> float:
    slope = (
        0.55 * float(series.iloc[origin] - series.iloc[origin - 1])
        + 0.30 * float((series.iloc[origin] - series.iloc[origin - 3]) / 3.0)
        + 0.15 * float((series.iloc[origin] - series.iloc[origin - 6]) / 6.0)
    )
    slope = float(np.clip(slope, -1.5, 1.5))
    damped_steps = sum(0.68**step for step in range(1, horizon + 1))
    return float(series.iloc[origin] + slope * damped_steps)


def _continuity_adjust(
    series: pd.Series,
    origins: np.ndarray,
    horizons: np.ndarray,
    predicted: np.ndarray,
) -> np.ndarray:
    adjusted = predicted.astype(float).copy()
    for index, (origin, horizon) in enumerate(zip(origins, horizons)):
        weight = 0.55 * math.exp(-(int(horizon) - 1) / 1.6)
        if weight < 0.01:
            continue
        local = _local_projection(series, int(origin), int(horizon))
        adjusted[index] = weight * local + (1.0 - weight) * adjusted[index]
    return adjusted


def _samples(
    series: pd.Series,
    c4_history: pd.Series,
    horizons: range | tuple[int, ...],
    *,
    origin_start: int,
    origin_end: int,
    stride: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    feature_rows: list[np.ndarray] = []
    targets: list[float] = []
    origins: list[int] = []
    sample_horizons: list[int] = []
    for origin in range(origin_start, origin_end, stride):
        for horizon in horizons:
            if origin + horizon >= len(series):
                continue
            target = series.iloc[origin + horizon]
            feature = _feature_vector(series, c4_history, origin, horizon)
            if feature is None or not np.isfinite(target):
                continue
            feature_rows.append(feature)
            targets.append(float(target))
            origins.append(origin)
            sample_horizons.append(horizon)
    if not feature_rows:
        return (
            np.empty((0, 16), dtype=float),
            np.asarray([], dtype=float),
            np.asarray([], dtype=int),
            np.asarray([], dtype=int),
        )
    return (
        np.vstack(feature_rows),
        np.asarray(targets, dtype=float),
        np.asarray(origins, dtype=int),
        np.asarray(sample_horizons, dtype=int),
    )


def _validate_model(
    series: pd.Series,
    c4_history: pd.Series,
    months: int,
) -> tuple[
    list[dict[str, Any]],
    dict[int, np.ndarray],
    np.ndarray,
    np.ndarray,
]:
    all_features, all_target, all_origins, all_horizons = _samples(
        series,
        c4_history,
        range(1, months + 1),
        origin_start=12,
        origin_end=len(series) - 1,
    )
    unique_origins = np.unique(all_origins)
    split_index = max(MIN_TRAIN_ORIGINS, int(len(unique_origins) * 0.7))
    train_origin_values = unique_origins[:split_index]
    test_origin_values = unique_origins[split_index::3]
    train_mask = np.isin(all_origins, train_origin_values)
    test_mask = np.isin(all_origins, test_origin_values)
    train_features = all_features[train_mask]
    train_target = all_target[train_mask]
    train_origins = all_origins[train_mask]
    train_horizons = all_horizons[train_mask]
    test_features = all_features[test_mask]
    test_target = all_target[test_mask]
    test_origins = all_origins[test_mask]
    test_horizons = all_horizons[test_mask]
    distinct_train_origins = len(train_origin_values)
    if (
        distinct_train_origins < MIN_TRAIN_ORIGINS
        or len(test_target) < MIN_TEST_ORIGINS
    ):
        return [], {}, all_features, all_target
    model = _fit_model(train_features, train_target)
    predicted = _continuity_adjust(
        series,
        test_origins,
        test_horizons,
        model.predict(test_features),
    )
    residuals = test_target - predicted
    metrics: list[dict[str, Any]] = []
    residuals_by_horizon: dict[int, np.ndarray] = {}
    for horizon in range(1, months + 1):
        mask = test_horizons == horizon
        if not mask.any():
            continue
        horizon_residuals = residuals[mask]
        residuals_by_horizon[horizon] = horizon_residuals
        if horizon not in VALIDATION_HORIZONS or mask.sum() < MIN_TEST_ORIGINS:
            continue
        horizon_origins = test_origins[mask]
        actual = test_target[mask]
        horizon_predicted = predicted[mask]
        current = np.asarray(
            [series.iloc[origin] for origin in horizon_origins],
            dtype=float,
        )
        train_mask = train_horizons == horizon
        train_current = np.asarray(
            [series.iloc[origin] for origin in train_origins[train_mask]],
            dtype=float,
        )
        train_change = train_target[train_mask] - train_current
        baseline_up = bool(np.mean(train_change >= 0) >= 0.5)
        model_mae = float(np.mean(np.abs(actual - horizon_predicted)))
        baseline_mae = float(np.mean(np.abs(actual - current)))
        model_direction = float(
            np.mean((horizon_predicted - current >= 0) == (actual - current >= 0))
        )
        baseline_direction = float(np.mean(baseline_up == (actual - current >= 0)))
        metrics.append(
            {
                "horizonMonths": horizon,
                "testOrigins": int(mask.sum()),
                "mae": model_mae,
                "baselineMae": baseline_mae,
                "directionAccuracy": model_direction,
                "baselineDirectionAccuracy": baseline_direction,
                "qualified": model_mae < baseline_mae
                and model_direction > baseline_direction,
            }
        )
    return metrics, residuals_by_horizon, all_features, all_target


def _forecast_path(
    series: pd.Series,
    c4_history: pd.Series,
    future_c4: dict[pd.Period, float],
    residuals_by_horizon: dict[int, np.ndarray],
    training_features: np.ndarray,
    training_target: np.ndarray,
    months: int,
) -> tuple[list[str], list[float], list[float], list[float]]:
    if len(training_target) == 0:
        return [], [], [], []
    model = _fit_model(training_features, training_target)
    current_origin = len(series) - 1
    dates: list[str] = []
    medians: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    for horizon in range(1, months + 1):
        current_features = _feature_vector(
            series,
            c4_history,
            current_origin,
            horizon,
            future_c4=future_c4,
        )
        if current_features is None:
            break
        predicted = float(model.predict(current_features.reshape(1, -1))[0])
        predicted = float(
            _continuity_adjust(
                series,
                np.asarray([current_origin], dtype=int),
                np.asarray([horizon], dtype=int),
                np.asarray([predicted], dtype=float),
            )[0]
        )
        residuals = residuals_by_horizon.get(horizon, np.asarray([], dtype=float))
        if residuals.size >= MIN_TEST_ORIGINS:
            low_error = float(np.quantile(residuals, 0.1))
            high_error = float(np.quantile(residuals, 0.9))
        else:
            scale = float(series.diff().dropna().std(ddof=0)) * math.sqrt(
                max(1.0, horizon / 3.0)
            )
            low_error, high_error = -1.28 * scale, 1.28 * scale
        dates.append(str(series.index[-1] + horizon))
        medians.append(float(np.clip(predicted, -4.0, 4.0)))
        lows.append(float(np.clip(predicted + min(low_error, high_error), -4.5, 4.5)))
        highs.append(float(np.clip(predicted + max(low_error, high_error), -4.5, 4.5)))
    return dates, medians, lows, highs


def _turning_point(
    bridge_value: float,
    dates: list[str],
    medians: list[float],
    current_slope: float,
) -> str | None:
    if len(medians) < 3:
        return None
    values = np.asarray([bridge_value, *medians], dtype=float)
    slopes = np.diff(values)
    initial = current_slope if abs(current_slope) >= 0.05 else float(np.mean(slopes[:2]))
    if abs(initial) < 0.05:
        return None
    initial_sign = 1.0 if initial > 0 else -1.0
    for index in range(len(slopes)):
        local_slope = float(np.mean(slopes[max(0, index - 1) : index + 1]))
        if abs(local_slope) >= 0.05 and np.sign(local_slope) != initial_sign:
            return dates[index]
    return None


def build_track_forecast(
    *,
    track_id: str,
    series: pd.Series,
    c4_history: pd.Series,
    c4_forecast: list[dict[str, Any]],
    forecast_as_of: str,
    months: int = FORECAST_MONTHS,
) -> dict[str, Any]:
    del track_id
    series = _monthly_series(series)
    c4_history = _monthly_series(c4_history)
    future_c4 = {
        pd.Period(row["date"], freq="M"): float(row["median"])
        for row in c4_forecast
        if row.get("median") is not None
    }
    last_position = series.last_valid_index()
    if last_position is None:
        return {
            "status": "unavailable",
            "method": "track-level direct multi-horizon Ridge",
            "caveat": "轨道缺少可用历史，无法生成条件预测。",
            "vintageDate": forecast_as_of,
            "dates": [],
            "median": [],
            "low": [],
            "high": [],
        }
    series = series.loc[:last_position]
    forecast_period = pd.Period(forecast_as_of, freq="M")
    input_lag_months = max(0, forecast_period.ordinal - series.index[-1].ordinal)
    stale_input = input_lag_months > MAX_INPUT_LAG_MONTHS
    metrics, residuals_by_horizon, training_features, training_target = (
        _validate_model(series, c4_history, months)
    )
    qualified_horizons = sum(bool(metric["qualified"]) for metric in metrics)
    publishable = len(metrics) == len(VALIDATION_HORIZONS) and qualified_horizons >= 2
    dates: list[str] = []
    medians: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    if publishable and not stale_input:
        dates, medians, lows, highs = _forecast_path(
            series,
            c4_history,
            future_c4,
            residuals_by_horizon,
            training_features,
            training_target,
            months,
        )
    bridge_value = float(series.iloc[-1])
    slope3 = (
        float((series.iloc[-1] - series.iloc[-4]) / 3.0)
        if len(series) >= 4 and series.iloc[-4:].notna().all()
        else 0.0
    )
    direction3 = None
    if len(medians) >= 3:
        change3 = medians[2] - bridge_value
        direction3 = "上行" if change3 > 0.1 else "下行" if change3 < -0.1 else "震荡"
    status_reason = (
        f"轨道历史末点 {series.index[-1]} 距预测 vintage {forecast_as_of} 已滞后 {input_lag_months} 个月，"
        f"超过 {MAX_INPUT_LAG_MONTHS} 个月输入门槛。"
        if stale_input
        else None
    )
    return {
        "status": "limited" if publishable and dates and not stale_input else "blocked",
        "statusReason": status_reason,
        "inputAsOf": str(series.index[-1]),
        "inputLagMonths": input_lag_months,
        "method": "连续性约束的轨道级多期限 Ridge（自身滞后/趋势 + C4条件路径 + 月份季节项）",
        "caveat": (
            f"预测 vintage {forecast_as_of}；后段留出样本按3/6/12个月与原地不动基准比较。"
            "这是轨道级条件预测，不是确定性外推。"
        ),
        "vintageDate": forecast_as_of,
        "dates": dates,
        "median": medians,
        "low": lows,
        "high": highs,
        "bridge": {"date": str(series.index[-1]), "value": bridge_value},
        "validation": {
            "qualifiedHorizons": qualified_horizons,
            "requiredHorizons": 2,
            "metrics": metrics,
        },
        "judgment": {
            "currentSlope3": _json_number(slope3),
            "direction3": direction3,
            "turningPoint": _turning_point(bridge_value, dates, medians, slope3),
        },
    }
