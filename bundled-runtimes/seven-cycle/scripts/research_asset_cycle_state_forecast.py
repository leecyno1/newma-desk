"""Build governed asset risk-return forecasts from C4/C5/C7 states.

The research compares historical state analogs, a fixed-prior robust analog,
strongly regularized Ridge challengers, and a fixed-rule consensus challenger.
Each asset and horizon is recursively validated against expanding historical
cutoffs. Forecasts remain research-only and do not produce portfolio weights.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import math
import os

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
C4_PATH = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
C5_PATH = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"
C7_PATH = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "asset_cycle_state_forecast.json"
SYNCHRONOUS_REFERENCE_PATH = (
    PROJECT_ROOT / "output" / "asset_cycle_state_forecast_synchronous_reference.json"
)

HORIZONS = (1, 3, 6)
NEIGHBOR_COUNT = 24
MIN_VALIDATION_TRAIN = 72
MIN_VALIDATION_OBSERVATIONS = 60
ANALOG_PRIOR_OBSERVATIONS = MIN_VALIDATION_TRAIN
STRONG_ANALOG_PRIOR_OBSERVATIONS = MIN_VALIDATION_TRAIN * 2
STRONG_SHRINK_MIN_OOS_R2 = 0.005
STRONG_SHRINK_MIN_RELATIVE_MAE_IMPROVEMENT = 0.001
STRONG_SHRINK_MIN_BRIER_IMPROVEMENT = 0.001
RECENT_VALIDATION_OBSERVATIONS = 48
MIN_RECENT_VALIDATION_OBSERVATIONS = 36
MIN_RECENT_PASSED_GATES = 4
MIN_NON_OVERLAP_OBSERVATIONS = 18
MIN_NON_OVERLAP_PASSED_GATES = 4
MIN_NESTED_NON_OVERLAP_OBSERVATIONS = 12
RIDGE_ALPHA = 10.0
LOGISTIC_C = 0.05
DEFAULT_FORECAST_WORKERS = min(4, os.cpu_count() or 1)
RECENCY_HALF_LIFE_MONTHS = 60.0
RECENCY_ROBUSTNESS_HALF_LIVES = (36.0, 60.0, 96.0)
UNCERTAINTY_BOOTSTRAP_SAMPLES = 300
ASYNCHRONOUS_CLOCK = "asynchronous_release_clock"
SYNCHRONOUS_CLOCK = "synchronous_restated_clock"
MODEL_VERSION = "asset_cycle_state_v8_cycle_shapley"
NESTED_ENSEMBLE_PRIMARY_SIZE = 4
NESTED_ENSEMBLE_ROBUSTNESS_SIZES = (3, 4, 5)
FIXED_MODEL_POLICY_BY_HORIZON = {6: "state_analog_shrunk"}
FEATURE_CLOCK_LAGS = {
    ASYNCHRONOUS_CLOCK: {"C4": 1, "C5": 1, "C7": 0},
    SYNCHRONOUS_CLOCK: {"C4": 0, "C5": 0, "C7": 0},
}
CYCLE_FEATURE_COLUMNS = {
    "C4": ("c4_level", "c4_slope3"),
    "C5": ("c5_state", "c5_slope3"),
    "C7": ("c7_state", "c7_slope3"),
}
ATTRIBUTION_METRICS = (
    "probabilityUp",
    "medianReturn",
    "conditionalVol",
    "valueAtRisk95",
)
ATTRIBUTION_STABILITY_POINTS = 24
ATTRIBUTION_SIGN_EPSILON = 0.0005
MAJOR_CATEGORY_BY_CATEGORY = {
    "A股宽基指数": "股票",
    "风格/规模指数": "股票",
    "申万一级行业": "股票",
    "海外指数/ETF": "股票",
    "美股行业ETF": "股票",
    "FF 17行业组合(US)": "股票",
    "各类债券指数": "债券",
    "商品": "商品",
    "外汇": "外汇",
}
SOURCE_REPORTING_LAG_LIMITS = {
    "FF 17行业组合(US)": 2,
}


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _timeline(path: Path, mapping: dict[str, str]) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["timeline"])
    frame.index = pd.PeriodIndex(frame["date"], freq="M").to_timestamp("M")
    return (
        frame[list(mapping)]
        .apply(pd.to_numeric, errors="coerce")
        .rename(columns=mapping)
    )


def _shift_to_available_month(
    frame: pd.DataFrame,
    lag_months: int,
) -> pd.DataFrame:
    shifted = frame.copy(deep=True)
    if lag_months:
        shifted.index = shifted.index + pd.offsets.MonthEnd(lag_months)
    return shifted


def build_feature_frame(
    clock: str = ASYNCHRONOUS_CLOCK,
) -> pd.DataFrame:
    if clock not in FEATURE_CLOCK_LAGS:
        raise ValueError(f"Unsupported feature clock: {clock}")
    lags = FEATURE_CLOCK_LAGS[clock]
    c4 = _timeline(C4_PATH, {"rt_level": "c4_level"})
    c4["c4_slope3"] = c4["c4_level"].diff(3) / 3.0
    c5 = _timeline(C5_PATH, {"state": "c5_state", "slope3": "c5_slope3"})
    c7 = _timeline(C7_PATH, {"state": "c7_state", "slope3": "c7_slope3"})
    c4 = _shift_to_available_month(c4, lags["C4"])
    c5 = _shift_to_available_month(c5, lags["C5"])
    c7 = _shift_to_available_month(c7, lags["C7"])
    return c4.join(c5, how="inner").join(c7, how="inner").dropna().sort_index()


def build_asset_feature_frame(
    state_features: pd.DataFrame,
    returns: pd.Series,
    *,
    category_returns: pd.Series | None = None,
) -> pd.DataFrame:
    frame = state_features.copy(deep=True)
    asset_returns = pd.to_numeric(returns, errors="coerce").reindex(frame.index)
    frame["asset_return_1m"] = asset_returns
    frame["asset_momentum_3m"] = (
        (1.0 + asset_returns)
        .rolling(3, min_periods=3)
        .apply(np.prod, raw=True)
        - 1.0
    )
    frame["asset_momentum_6m"] = (
        (1.0 + asset_returns)
        .rolling(6, min_periods=6)
        .apply(np.prod, raw=True)
        - 1.0
    )
    frame["asset_volatility_6m"] = asset_returns.rolling(
        6,
        min_periods=4,
    ).std(ddof=1)
    frame["asset_volatility_12m"] = asset_returns.rolling(
        12,
        min_periods=8,
    ).std(ddof=1)
    frame["month_sin"] = np.sin(2.0 * np.pi * frame.index.month / 12.0)
    frame["month_cos"] = np.cos(2.0 * np.pi * frame.index.month / 12.0)
    if category_returns is not None:
        category = pd.to_numeric(category_returns, errors="coerce").reindex(frame.index)
        category_momentum_3m = (
            (1.0 + category)
            .rolling(3, min_periods=3)
            .apply(np.prod, raw=True)
            - 1.0
        )
        category_momentum_6m = (
            (1.0 + category)
            .rolling(6, min_periods=6)
            .apply(np.prod, raw=True)
            - 1.0
        )
        frame["category_return_1m"] = category
        frame["category_momentum_3m"] = category_momentum_3m
        frame["category_momentum_6m"] = category_momentum_6m
        frame["category_volatility_6m"] = category.rolling(
            6,
            min_periods=4,
        ).std(ddof=1)
        frame["category_volatility_12m"] = category.rolling(
            12,
            min_periods=8,
        ).std(ddof=1)
        frame["asset_relative_return_1m"] = asset_returns - category
        frame["asset_relative_momentum_3m"] = (
            frame["asset_momentum_3m"] - category_momentum_3m
        )
        frame["asset_relative_momentum_6m"] = (
            frame["asset_momentum_6m"] - category_momentum_6m
        )
    return frame


def _future_return(series: pd.Series, horizon: int) -> pd.Series:
    return (1.0 + series).rolling(horizon, min_periods=horizon).apply(
        np.prod, raw=True
    ).shift(-horizon) - 1.0


def _month_lag(current_date: pd.Timestamp, asset_end: pd.Timestamp | None) -> int | None:
    if asset_end is None or pd.isna(asset_end):
        return None
    return int(
        (current_date.year - asset_end.year) * 12
        + current_date.month
        - asset_end.month
    )


def _freshness_status(
    current_date: pd.Timestamp,
    asset_end: pd.Timestamp | None,
    *,
    category: str | None = None,
) -> tuple[str, int | None]:
    lag_months = _month_lag(current_date, asset_end)
    if lag_months is not None and lag_months <= 0:
        return "current", lag_months
    allowed_lag = SOURCE_REPORTING_LAG_LIMITS.get(category or "", 0)
    if lag_months is not None and 0 < lag_months <= allowed_lag:
        return "source_lag", lag_months
    return "stale", lag_months


def _analog_values(
    training_features: pd.DataFrame,
    training_target: pd.Series,
    current_features: pd.Series,
) -> pd.Series:
    center = training_features.median()
    scale = (training_features - center).abs().median() * 1.4826
    fallback = training_features.std(ddof=0)
    scale = scale.where(scale > 1e-8, fallback).replace(0, 1.0).fillna(1.0)
    distance = np.sqrt(
        (((training_features - current_features) / scale) ** 2).mean(axis=1)
    )
    neighbors = distance.nsmallest(min(NEIGHBOR_COUNT, len(distance))).index
    return training_target.loc[neighbors].dropna()


def _forecast_distribution(values: pd.Series) -> dict[str, object]:
    value_at_risk = float(values.quantile(0.05))
    tail = values.loc[values <= value_at_risk]
    return {
        "analogs": int(len(values)),
        "probabilityUp": _json_value((values > 0).mean()),
        "downsideProbability": _json_value((values <= 0).mean()),
        "medianReturn": _json_value(values.median()),
        "low20": _json_value(values.quantile(0.20)),
        "high80": _json_value(values.quantile(0.80)),
        "conditionalVol": _json_value(values.std(ddof=1)),
        "valueAtRisk95": _json_value(value_at_risk),
        "expectedShortfall95": _json_value(tail.mean()),
    }


def _recency_weights(
    index: pd.DatetimeIndex,
    current_date: pd.Timestamp,
    half_life_months: float,
) -> np.ndarray:
    ages = np.asarray(
        [
            (current_date.year - date.year) * 12
            + current_date.month
            - date.month
            for date in index
        ],
        dtype="float64",
    )
    return np.power(0.5, ages / half_life_months)


def _weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    order = np.argsort(values)
    ordered_values = values[order]
    ordered_weights = weights[order]
    cutoff = quantile * float(ordered_weights.sum())
    position = int(
        np.searchsorted(np.cumsum(ordered_weights), cutoff, side="left")
    )
    return float(ordered_values[min(position, len(ordered_values) - 1)])


def _recency_analog_estimate(
    analogs: pd.Series,
    current_date: pd.Timestamp,
    half_life_months: float,
) -> dict[str, object]:
    values = analogs.to_numpy(dtype="float64")
    weights = _recency_weights(
        pd.DatetimeIndex(analogs.index),
        current_date,
        half_life_months,
    )
    probability_up = float(np.average((values > 0).astype(float), weights=weights))
    value_at_risk = _weighted_quantile(values, weights, 0.05)
    tail = values <= value_at_risk
    weighted_mean = float(np.average(values, weights=weights))
    weighted_variance = float(
        np.average((values - weighted_mean) ** 2, weights=weights)
    )
    return {
        "probabilityUp": probability_up,
        "medianReturn": _weighted_quantile(values, weights, 0.50),
        "low20": _weighted_quantile(values, weights, 0.20),
        "high80": _weighted_quantile(values, weights, 0.80),
        "conditionalVol": math.sqrt(weighted_variance),
        "valueAtRisk95": value_at_risk,
        "expectedShortfall95": float(
            np.average(values[tail], weights=weights[tail])
        ),
    }


def _shrunk_analog_estimate(
    analogs: pd.Series,
    training_target: pd.Series,
    *,
    prior_observations: int = ANALOG_PRIOR_OBSERVATIONS,
) -> dict[str, float]:
    local_observations = float(len(analogs))
    local_weight = local_observations / (
        local_observations + prior_observations
    )
    baseline_return = float(training_target.median())
    baseline_probability = float((training_target > 0).mean())
    local_return = float(analogs.median())
    local_probability = float((analogs > 0).mean())
    return {
        "localWeight": local_weight,
        "return": local_weight * local_return
        + (1.0 - local_weight) * baseline_return,
        "probabilityUp": local_weight * local_probability
        + (1.0 - local_weight) * baseline_probability,
    }


def _validation_metrics(
    *,
    model: str,
    actual: list[float],
    predicted: list[float],
    probabilities: list[float],
    baseline: list[float],
    baseline_probabilities: list[float],
    minimum_observations: int = MIN_VALIDATION_OBSERVATIONS,
) -> dict[str, object]:
    if len(actual) < minimum_observations:
        return {
            "model": model,
            "observations": int(len(actual)),
            "passedGateCount": 0,
            "qualified": False,
            "reason": "insufficient_recursive_observations",
            "reasonCodes": ["insufficient_recursive_observations"],
        }
    actual_array = np.asarray(actual)
    predicted_array = np.asarray(predicted)
    probability_array = np.asarray(probabilities)
    baseline_array = np.asarray(baseline)
    baseline_probability_array = np.asarray(baseline_probabilities)
    actual_up = actual_array > 0
    accuracy = float(np.mean((predicted_array >= 0) == actual_up))
    base_accuracy = float(np.mean((baseline_array >= 0) == actual_up))
    brier = float(np.mean((probability_array - actual_up) ** 2))
    base_brier = float(np.mean((baseline_probability_array - actual_up) ** 2))
    mae = float(np.mean(np.abs(predicted_array - actual_array)))
    base_mae = float(np.mean(np.abs(baseline_array - actual_array)))
    denominator = float(np.sum((actual_array - baseline_array) ** 2))
    oos_r2 = (
        1.0 - float(np.sum((actual_array - predicted_array) ** 2)) / denominator
        if denominator > 0
        else None
    )
    gates = {
        "direction_above_55": accuracy >= 0.55,
        "direction_beats_baseline": accuracy >= base_accuracy,
        "brier_beats_baseline": brier < base_brier,
        "mae_beats_baseline": mae < base_mae,
        "positive_oos_r2": float(oos_r2 or 0.0) > 0,
    }
    reason_codes = [name for name, passed in gates.items() if not passed]
    residuals = actual_array - predicted_array
    residual_value_at_risk = float(np.quantile(residuals, 0.05))
    residual_tail = residuals[residuals <= residual_value_at_risk]
    qualified = all(gates.values())
    return {
        "model": model,
        "observations": int(len(actual_array)),
        "directionAccuracy": _json_value(accuracy),
        "baseAccuracy": _json_value(base_accuracy),
        "brier": _json_value(brier),
        "baseBrier": _json_value(base_brier),
        "mae": _json_value(mae),
        "baseMae": _json_value(base_mae),
        "oosR2": _json_value(oos_r2),
        "passedGateCount": sum(gates.values()),
        "qualified": qualified,
        "reason": "passed" if qualified else "did_not_beat_all_baselines",
        "reasonCodes": reason_codes,
        "residualDistribution": {
            "median": _json_value(np.median(residuals)),
            "low20": _json_value(np.quantile(residuals, 0.20)),
            "high80": _json_value(np.quantile(residuals, 0.80)),
            "volatility": _json_value(np.std(residuals, ddof=1)),
            "valueAtRisk95": _json_value(residual_value_at_risk),
            "expectedShortfall95": _json_value(np.mean(residual_tail)),
        },
    }


def _validation_uncertainty(
    trace: list[dict[str, object]],
    horizon: int,
) -> dict[str, object] | None:
    if len(trace) < MIN_RECENT_VALIDATION_OBSERVATIONS:
        return None
    actual = np.asarray(
        [float(point["actualReturn"]) for point in trace],
        dtype="float64",
    )
    predicted = np.asarray(
        [float(point["predictedReturn"]) for point in trace],
        dtype="float64",
    )
    baseline = np.asarray(
        [float(point["baselineReturn"]) for point in trace],
        dtype="float64",
    )
    actual_up = actual > 0
    predicted_up = predicted >= 0
    observations = len(actual)
    z_score = 1.6448536269514722
    direction_accuracy = float(np.mean(predicted_up == actual_up))
    denominator = 1.0 + z_score**2 / observations
    center = (
        direction_accuracy + z_score**2 / (2.0 * observations)
    ) / denominator
    half_width = (
        z_score
        * math.sqrt(
            direction_accuracy * (1.0 - direction_accuracy) / observations
            + z_score**2 / (4.0 * observations**2)
        )
        / denominator
    )
    block_months = max(1, horizon)
    block_count = math.ceil(observations / block_months)
    rng = np.random.default_rng(20260811 + horizon * 1000 + observations)
    bootstrap_r2: list[float] = []
    for _ in range(UNCERTAINTY_BOOTSTRAP_SAMPLES):
        starts = rng.integers(0, observations, size=block_count)
        indices = np.concatenate(
            [
                (start + np.arange(block_months)) % observations
                for start in starts
            ]
        )[:observations]
        sampled_actual = actual[indices]
        sampled_predicted = predicted[indices]
        sampled_baseline = baseline[indices]
        sampled_denominator = float(
            np.sum((sampled_actual - sampled_baseline) ** 2)
        )
        if sampled_denominator <= 0:
            continue
        bootstrap_r2.append(
            1.0
            - float(
                np.sum((sampled_actual - sampled_predicted) ** 2)
            )
            / sampled_denominator
        )
    if not bootstrap_r2:
        return None
    r2_low, r2_high = np.quantile(bootstrap_r2, [0.05, 0.95])
    evidence_strength = (
        "strong"
        if center - half_width >= 0.5 and r2_low > 0
        else "moderate"
        if direction_accuracy >= 0.55
        and float(np.median(bootstrap_r2)) > 0
        else "weak"
    )
    return {
        "confidenceLevel": 0.90,
        "observations": observations,
        "blockMonths": block_months,
        "bootstrapSamples": UNCERTAINTY_BOOTSTRAP_SAMPLES,
        "directionAccuracy": {
            "low": _json_value(max(0.0, center - half_width)),
            "high": _json_value(min(1.0, center + half_width)),
        },
        "oosR2": {
            "low": _json_value(float(r2_low)),
            "high": _json_value(float(r2_high)),
        },
        "evidenceStrength": evidence_strength,
    }


def _attach_validation_uncertainty(
    validation: dict[str, object],
    horizon: int,
) -> None:
    trace = list(validation.get("_fullTrace", []))
    validation["uncertainty"] = _validation_uncertainty(trace, horizon)
    validation["recentUncertainty"] = _validation_uncertainty(
        trace[-RECENT_VALIDATION_OBSERVATIONS:],
        horizon,
    )


def _validation_with_recent(
    *,
    model: str,
    horizon: int,
    dates: list[str],
    actual: list[float],
    predicted: list[float],
    probabilities: list[float],
    baseline: list[float],
    baseline_probabilities: list[float],
    minimum_non_overlap_observations: int = MIN_NON_OVERLAP_OBSERVATIONS,
) -> dict[str, object]:
    validation = _validation_metrics(
        model=model,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )
    recent_slice = slice(-RECENT_VALIDATION_OBSERVATIONS, None)
    recent_validation = _validation_metrics(
        model=model,
        actual=actual[recent_slice],
        predicted=predicted[recent_slice],
        probabilities=probabilities[recent_slice],
        baseline=baseline[recent_slice],
        baseline_probabilities=baseline_probabilities[recent_slice],
        minimum_observations=MIN_RECENT_VALIDATION_OBSERVATIONS,
    )
    validation["recentValidation"] = recent_validation
    validation["recentStable"] = bool(
        recent_validation.get("observations", 0)
        >= MIN_RECENT_VALIDATION_OBSERVATIONS
        and recent_validation.get("passedGateCount", 0)
        >= MIN_RECENT_PASSED_GATES
    )
    minimum_path_observations = max(
        minimum_non_overlap_observations,
        MIN_VALIDATION_OBSERVATIONS // horizon,
    )
    path_results = []
    for offset in range(horizon):
        positions = [
            position
            for position, date in enumerate(dates)
            if pd.Period(date, freq="M").ordinal % horizon == offset
        ]
        path_validation = _validation_metrics(
            model=model,
            actual=[actual[position] for position in positions],
            predicted=[predicted[position] for position in positions],
            probabilities=[probabilities[position] for position in positions],
            baseline=[baseline[position] for position in positions],
            baseline_probabilities=[
                baseline_probabilities[position] for position in positions
            ],
            minimum_observations=minimum_path_observations,
        )
        path_oos_r2 = path_validation.get("oosR2")
        path_results.append(
            {
                "offset": offset,
                "observations": path_validation["observations"],
                "directionAccuracy": path_validation.get("directionAccuracy"),
                "baseAccuracy": path_validation.get("baseAccuracy"),
                "brier": path_validation.get("brier"),
                "baseBrier": path_validation.get("baseBrier"),
                "mae": path_validation.get("mae"),
                "baseMae": path_validation.get("baseMae"),
                "oosR2": path_oos_r2,
                "passedGateCount": path_validation["passedGateCount"],
                "stable": bool(
                    path_validation["passedGateCount"]
                    >= MIN_NON_OVERLAP_PASSED_GATES
                    and path_oos_r2 is not None
                    and float(path_oos_r2) > 0
                ),
            }
        )
    eligible_paths = [
        path
        for path in path_results
        if path["observations"] >= minimum_path_observations
    ]
    stable_paths = [path for path in eligible_paths if path["stable"]]
    path_oos_values = [
        float(path["oosR2"])
        for path in eligible_paths
        if path["oosR2"] is not None
    ]
    median_path_oos_r2 = (
        float(np.median(path_oos_values)) if path_oos_values else None
    )
    non_overlap_stable = bool(
        horizon == 1
        or (
            len(eligible_paths) == horizon
            and len(stable_paths) >= math.ceil(horizon / 2)
            and median_path_oos_r2 is not None
            and median_path_oos_r2 > 0
        )
    )
    validation["nonOverlapStable"] = non_overlap_stable
    validation["nonOverlappingValidation"] = {
        "spacingMonths": horizon,
        "minimumObservationsPerPath": minimum_path_observations,
        "eligiblePaths": len(eligible_paths),
        "stablePaths": len(stable_paths),
        "requiredStablePaths": math.ceil(horizon / 2),
        "medianOosR2": _json_value(median_path_oos_r2),
        "stable": non_overlap_stable,
        "paths": path_results,
    }
    full_trace = [
        {
            "date": date,
            "actualReturn": _json_value(actual_value),
            "predictedReturn": _json_value(predicted_value),
            "baselineReturn": _json_value(baseline_value),
            "probabilityUp": _json_value(probability),
            "baselineProbabilityUp": _json_value(baseline_probability),
        }
        for date, actual_value, predicted_value, baseline_value, probability, baseline_probability in zip(
            dates,
            actual,
            predicted,
            baseline,
            probabilities,
            baseline_probabilities,
            strict=True,
        )
    ]
    validation["_fullTrace"] = full_trace
    validation["recentTrace"] = [
        {
            "date": point["date"],
            "actualReturn": point["actualReturn"],
            "predictedReturn": point["predictedReturn"],
            "baselineReturn": point["baselineReturn"],
            "probabilityUp": point["probabilityUp"],
        }
        for point in full_trace[recent_slice]
    ]
    return validation


def _analog_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    frame = features.join(target.rename("target")).dropna()
    predicted: list[float] = []
    probabilities: list[float] = []
    actual: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    dates: list[str] = []
    for current_date, row in frame.iterrows():
        training = frame.loc[
            frame.index <= current_date - pd.DateOffset(months=horizon)
        ]
        if len(training) < MIN_VALIDATION_TRAIN:
            continue
        analogs = _analog_values(
            training[features.columns],
            training["target"],
            row[features.columns],
        )
        if len(analogs) < 12:
            continue
        dates.append(current_date.strftime("%Y-%m"))
        predicted.append(float(analogs.median()))
        probabilities.append(float((analogs > 0).mean()))
        actual.append(float(row["target"]))
        baseline.append(float(training["target"].median()))
        baseline_probabilities.append(float((training["target"] > 0).mean()))

    return _validation_with_recent(
        model="state_analog",
        horizon=horizon,
        dates=dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )


def _shrunk_analog_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
    *,
    model: str = "state_analog_shrunk",
    prior_observations: int = ANALOG_PRIOR_OBSERVATIONS,
) -> dict[str, object]:
    frame = features.join(target.rename("target")).dropna()
    predicted: list[float] = []
    probabilities: list[float] = []
    actual: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    dates: list[str] = []
    for current_date, row in frame.iterrows():
        training = frame.loc[
            frame.index <= current_date - pd.DateOffset(months=horizon)
        ]
        if len(training) < MIN_VALIDATION_TRAIN:
            continue
        analogs = _analog_values(
            training[features.columns],
            training["target"],
            row[features.columns],
        )
        if len(analogs) < 12:
            continue
        estimate = _shrunk_analog_estimate(
            analogs,
            training["target"],
            prior_observations=prior_observations,
        )
        dates.append(current_date.strftime("%Y-%m"))
        predicted.append(estimate["return"])
        probabilities.append(estimate["probabilityUp"])
        actual.append(float(row["target"]))
        baseline.append(float(training["target"].median()))
        baseline_probabilities.append(float((training["target"] > 0).mean()))

    return _validation_with_recent(
        model=model,
        horizon=horizon,
        dates=dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )


def _strong_shrink_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    validation = _shrunk_analog_validation(
        features,
        target,
        horizon,
        model="state_analog_strong_shrink",
        prior_observations=STRONG_ANALOG_PRIOR_OBSERVATIONS,
    )
    base_mae = float(validation.get("baseMae") or 0.0)
    mae = float(validation.get("mae") or math.inf)
    relative_mae_improvement = (
        (base_mae - mae) / base_mae if base_mae > 0 else -math.inf
    )
    brier_improvement = float(validation.get("baseBrier") or 0.0) - float(
        validation.get("brier") or math.inf
    )
    materiality = {
        "oosR2": float(validation.get("oosR2") or -math.inf)
        >= STRONG_SHRINK_MIN_OOS_R2,
        "relativeMaeImprovement": relative_mae_improvement
        >= STRONG_SHRINK_MIN_RELATIVE_MAE_IMPROVEMENT,
        "brierImprovement": brier_improvement
        >= STRONG_SHRINK_MIN_BRIER_IMPROVEMENT,
    }
    validation["robustnessStable"] = all(materiality.values())
    validation["robustnessReasonCode"] = "strong_shrink_materiality"
    validation["challengerMateriality"] = {
        "passed": all(materiality.values()),
        "gates": materiality,
        "relativeMaeImprovement": _json_value(relative_mae_improvement),
        "brierImprovement": _json_value(brier_improvement),
        "minimumOosR2": STRONG_SHRINK_MIN_OOS_R2,
        "minimumRelativeMaeImprovement": (
            STRONG_SHRINK_MIN_RELATIVE_MAE_IMPROVEMENT
        ),
        "minimumBrierImprovement": STRONG_SHRINK_MIN_BRIER_IMPROVEMENT,
    }
    return validation


def _shrunk_analog_forecast(
    analogs: pd.Series,
    training_target: pd.Series,
    *,
    model: str = "state_analog_shrunk",
    prior_observations: int = ANALOG_PRIOR_OBSERVATIONS,
) -> dict[str, object]:
    estimate = _shrunk_analog_estimate(
        analogs,
        training_target,
        prior_observations=prior_observations,
    )
    return {
        **_forecast_distribution(analogs),
        "model": model,
        "localWeight": _json_value(estimate["localWeight"]),
        "probabilityUp": _json_value(estimate["probabilityUp"]),
        "downsideProbability": _json_value(1.0 - estimate["probabilityUp"]),
        "medianReturn": _json_value(estimate["return"]),
    }


def _recency_analog_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
    *,
    half_life_months: float,
) -> dict[str, object]:
    frame = features.join(target.rename("target")).dropna()
    predicted: list[float] = []
    probabilities: list[float] = []
    actual: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    dates: list[str] = []
    for current_date, row in frame.iterrows():
        training = frame.loc[
            frame.index <= current_date - pd.DateOffset(months=horizon)
        ]
        if len(training) < MIN_VALIDATION_TRAIN:
            continue
        analogs = _analog_values(
            training[features.columns],
            training["target"],
            row[features.columns],
        )
        if len(analogs) < 12:
            continue
        estimate = _recency_analog_estimate(
            analogs,
            current_date,
            half_life_months,
        )
        dates.append(current_date.strftime("%Y-%m"))
        predicted.append(float(estimate["medianReturn"]))
        probabilities.append(float(estimate["probabilityUp"]))
        actual.append(float(row["target"]))
        baseline.append(float(training["target"].median()))
        baseline_probabilities.append(float((training["target"] > 0).mean()))
    return _validation_with_recent(
        model="state_analog_recency",
        horizon=horizon,
        dates=dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )


def _robust_recency_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    sensitivity = {
        half_life: _recency_analog_validation(
            features,
            target,
            horizon,
            half_life_months=half_life,
        )
        for half_life in RECENCY_ROBUSTNESS_HALF_LIVES
    }
    validation = sensitivity[RECENCY_HALF_LIFE_MONTHS]
    validation["robustnessStable"] = all(
        result.get("qualified") and result.get("recentStable")
        for result in sensitivity.values()
    )
    validation["robustness"] = {
        "halfLivesMonths": list(RECENCY_ROBUSTNESS_HALF_LIVES),
        "results": {
            str(int(half_life)): {
                "qualified": result.get("qualified"),
                "recentStable": result.get("recentStable"),
                "passedGateCount": result.get("passedGateCount"),
                "oosR2": result.get("oosR2"),
            }
            for half_life, result in sensitivity.items()
        },
    }
    return validation


def _recency_analog_forecast(
    analogs: pd.Series,
    current_date: pd.Timestamp,
) -> dict[str, object]:
    estimate = _recency_analog_estimate(
        analogs,
        current_date,
        RECENCY_HALF_LIFE_MONTHS,
    )
    probability_up = float(estimate["probabilityUp"])
    return {
        "analogs": int(len(analogs)),
        "model": "state_analog_recency",
        "halfLifeMonths": RECENCY_HALF_LIFE_MONTHS,
        "probabilityUp": _json_value(probability_up),
        "downsideProbability": _json_value(1.0 - probability_up),
        "medianReturn": _json_value(estimate["medianReturn"]),
        "low20": _json_value(estimate["low20"]),
        "high80": _json_value(estimate["high80"]),
        "conditionalVol": _json_value(estimate["conditionalVol"]),
        "valueAtRisk95": _json_value(estimate["valueAtRisk95"]),
        "expectedShortfall95": _json_value(estimate["expectedShortfall95"]),
    }


def _ridge_regressor() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=RIDGE_ALPHA),
    )


def _direction_classifier() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(
            C=LOGISTIC_C,
            max_iter=500,
            class_weight="balanced",
        ),
    )


def _ridge_point_probability(
    training: pd.DataFrame,
    feature_columns: list[str],
    current_features: pd.Series,
) -> tuple[float, float] | None:
    direction = (training["target"] > 0).astype(int)
    if direction.nunique() < 2:
        return None
    regressor = _ridge_regressor()
    classifier = _direction_classifier()
    regressor.fit(training[feature_columns], training["target"])
    classifier.fit(training[feature_columns], direction)
    current_frame = current_features[feature_columns].to_frame().T
    return (
        float(regressor.predict(current_frame)[0]),
        float(classifier.predict_proba(current_frame)[0, 1]),
    )


def _ridge_validation(
    features: pd.DataFrame,
    target: pd.Series,
    horizon: int,
    *,
    model: str = "state_ridge",
) -> dict[str, object]:
    frame = features.join(target.rename("target")).dropna(subset=["target"])
    predicted: list[float] = []
    probabilities: list[float] = []
    actual: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    dates: list[str] = []
    for current_date, row in frame.iterrows():
        training = frame.loc[
            frame.index <= current_date - pd.DateOffset(months=horizon)
        ]
        if len(training) < MIN_VALIDATION_TRAIN:
            continue
        direction = (training["target"] > 0).astype(int)
        if direction.nunique() < 2:
            continue
        regressor = _ridge_regressor()
        classifier = _direction_classifier()
        regressor.fit(training[features.columns], training["target"])
        classifier.fit(training[features.columns], direction)
        current_features = row[features.columns].to_frame().T
        dates.append(current_date.strftime("%Y-%m"))
        predicted.append(float(regressor.predict(current_features)[0]))
        probabilities.append(
            float(classifier.predict_proba(current_features)[0, 1])
        )
        actual.append(float(row["target"]))
        baseline.append(float(training["target"].median()))
        baseline_probabilities.append(float(direction.mean()))
    return _validation_with_recent(
        model=model,
        horizon=horizon,
        dates=dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )


def _ridge_forecast(
    training: pd.DataFrame,
    feature_columns: list[str],
    current_features: pd.Series,
    validation: dict[str, object],
    *,
    model: str = "state_ridge",
) -> dict[str, object] | None:
    residual_distribution = validation.get("residualDistribution")
    estimate = _ridge_point_probability(
        training,
        feature_columns,
        current_features,
    )
    if estimate is None or not isinstance(residual_distribution, dict):
        return None
    point, probability_up = estimate
    return {
        "analogs": int(len(training)),
        "model": model,
        "probabilityUp": _json_value(probability_up),
        "downsideProbability": _json_value(1.0 - probability_up),
        "medianReturn": _json_value(point + float(residual_distribution["median"])),
        "low20": _json_value(point + float(residual_distribution["low20"])),
        "high80": _json_value(point + float(residual_distribution["high80"])),
        "conditionalVol": _json_value(residual_distribution["volatility"]),
        "valueAtRisk95": _json_value(
            point + float(residual_distribution["valueAtRisk95"])
        ),
        "expectedShortfall95": _json_value(
            point + float(residual_distribution["expectedShortfall95"])
        ),
    }


def _consensus_components(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    current_date: pd.Timestamp,
    horizon: int,
    current_state_features: pd.Series | None = None,
    current_asset_features: pd.Series | None = None,
    current_category_features: pd.Series | None = None,
) -> tuple[list[float], list[float], int] | None:
    training_target = target.loc[
        target.index <= current_date - pd.DateOffset(months=horizon)
    ].dropna()
    if len(training_target) < MIN_VALIDATION_TRAIN:
        return None
    state_training = state_features.reindex(training_target.index).join(
        training_target.rename("target")
    )
    analogs = _analog_values(
        state_training[state_features.columns],
        state_training["target"],
        current_state_features
        if current_state_features is not None
        else state_features.loc[current_date],
    )
    if len(analogs) < 12:
        return None
    analog_estimate = _shrunk_analog_estimate(
        analogs,
        state_training["target"],
    )
    points = [float(analog_estimate["return"])]
    probabilities = [float(analog_estimate["probabilityUp"])]
    for model_features, current_features in (
        (asset_features, current_asset_features),
        (category_features, current_category_features),
    ):
        if model_features is None:
            continue
        ridge_training = model_features.reindex(training_target.index).join(
            training_target.rename("target")
        )
        estimate = _ridge_point_probability(
            ridge_training,
            list(model_features.columns),
            current_features
            if current_features is not None
            else model_features.loc[current_date],
        )
        if estimate is None:
            continue
        point, probability = estimate
        points.append(point)
        probabilities.append(probability)
    if len(points) < 2:
        return None
    return points, probabilities, len(analogs)


def _consensus_validation(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    predicted: list[float] = []
    probabilities: list[float] = []
    actual: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    dates: list[str] = []
    for current_date, actual_value in target.dropna().items():
        if current_date not in state_features.index:
            continue
        components = _consensus_components(
            state_features=state_features,
            asset_features=asset_features,
            category_features=category_features,
            target=target,
            current_date=current_date,
            horizon=horizon,
        )
        if components is None:
            continue
        points, component_probabilities, _ = components
        training_target = target.loc[
            target.index <= current_date - pd.DateOffset(months=horizon)
        ].dropna()
        dates.append(current_date.strftime("%Y-%m"))
        predicted.append(float(np.mean(points)))
        probabilities.append(float(np.mean(component_probabilities)))
        actual.append(float(actual_value))
        baseline.append(float(training_target.median()))
        baseline_probabilities.append(float((training_target > 0).mean()))
    return _validation_with_recent(
        model="state_model_consensus",
        horizon=horizon,
        dates=dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
    )


def _consensus_forecast(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    current_date: pd.Timestamp,
    horizon: int,
    validation: dict[str, object],
    current_state_features: pd.Series | None = None,
    current_asset_features: pd.Series | None = None,
    current_category_features: pd.Series | None = None,
) -> dict[str, object] | None:
    residual_distribution = validation.get("residualDistribution")
    components = _consensus_components(
        state_features=state_features,
        asset_features=asset_features,
        category_features=category_features,
        target=target,
        current_date=current_date,
        horizon=horizon,
        current_state_features=current_state_features,
        current_asset_features=current_asset_features,
        current_category_features=current_category_features,
    )
    if components is None or not isinstance(residual_distribution, dict):
        return None
    points, probabilities, analog_count = components
    point = float(np.mean(points))
    probability_up = float(np.mean(probabilities))
    return {
        "analogs": analog_count,
        "model": "state_model_consensus",
        "componentCount": len(points),
        "probabilityUp": _json_value(probability_up),
        "downsideProbability": _json_value(1.0 - probability_up),
        "medianReturn": _json_value(point + float(residual_distribution["median"])),
        "low20": _json_value(point + float(residual_distribution["low20"])),
        "high80": _json_value(point + float(residual_distribution["high80"])),
        "conditionalVol": _json_value(residual_distribution["volatility"]),
        "valueAtRisk95": _json_value(
            point + float(residual_distribution["valueAtRisk95"])
        ),
        "expectedShortfall95": _json_value(
            point + float(residual_distribution["expectedShortfall95"])
        ),
    }


def _model_rank(validation: dict[str, object]) -> tuple[object, ...]:
    recent_validation = validation.get("recentValidation")
    recent_passed = (
        int(recent_validation.get("passedGateCount", 0))
        if isinstance(recent_validation, dict)
        else 0
    )
    governed_qualified = bool(validation.get("qualified")) and bool(
        validation.get("robustnessStable", True)
    ) and bool(validation.get("nonOverlapStable", True))
    return (
        governed_qualified,
        bool(validation.get("recentStable")),
        int(validation.get("passedGateCount", 0)),
        recent_passed,
        float(validation.get("oosR2") or -1e9),
        float(validation.get("baseBrier") or 0.0)
        - float(validation.get("brier") or 1e9),
        float(validation.get("baseMae") or 0.0)
        - float(validation.get("mae") or 1e9),
    )


def _validation_from_trace(
    *,
    model: str,
    trace: list[dict[str, object]],
) -> dict[str, object]:
    return _validation_metrics(
        model=model,
        actual=[float(point["actualReturn"]) for point in trace],
        predicted=[float(point["predictedReturn"]) for point in trace],
        probabilities=[float(point["probabilityUp"]) for point in trace],
        baseline=[float(point["baselineReturn"]) for point in trace],
        baseline_probabilities=[
            float(point["baselineProbabilityUp"]) for point in trace
        ],
    )


def _nested_champion_validation(
    validations: dict[str, dict[str, object]],
    horizon: int,
) -> dict[str, object]:
    return _nested_walk_forward_validation(
        validations,
        horizon,
        top_model_count=1,
    )


def _nested_walk_forward_validation(
    validations: dict[str, dict[str, object]],
    horizon: int,
    *,
    top_model_count: int,
) -> dict[str, object]:
    traces = {
        model: list(validation.get("_fullTrace", []))
        for model, validation in validations.items()
    }
    trace_maps = {
        model: {str(point["date"]): point for point in trace}
        for model, trace in traces.items()
    }
    dated_traces = {
        model: [
            (pd.Period(str(point["date"]), freq="M"), point)
            for point in trace
        ]
        for model, trace in traces.items()
    }
    dates = sorted(
        {
            str(point["date"])
            for trace in traces.values()
            for point in trace
        }
    )
    selected_dates: list[str] = []
    selected_model_sets: list[tuple[str, ...]] = []
    actual: list[float] = []
    predicted: list[float] = []
    probabilities: list[float] = []
    baseline: list[float] = []
    baseline_probabilities: list[float] = []
    for date in dates:
        cutoff = pd.Period(date, freq="M") - horizon
        candidate_validations: dict[str, dict[str, object]] = {}
        for model, dated_trace in dated_traces.items():
            if date not in trace_maps[model]:
                continue
            history = [
                point
                for period, point in dated_trace
                if period <= cutoff
            ]
            if len(history) < MIN_VALIDATION_OBSERVATIONS:
                continue
            candidate_validations[model] = _validation_from_trace(
                model=model,
                trace=history,
            )
        if not candidate_validations:
            continue
        ordered_models = sorted(
            candidate_validations,
            key=lambda model: _model_rank(candidate_validations[model]),
            reverse=True,
        )
        selected_models = tuple(ordered_models[:top_model_count])
        points = [trace_maps[model][date] for model in selected_models]
        selected_dates.append(date)
        selected_model_sets.append(selected_models)
        actual.append(float(points[0]["actualReturn"]))
        predicted.append(
            float(np.mean([float(point["predictedReturn"]) for point in points]))
        )
        probabilities.append(
            float(np.mean([float(point["probabilityUp"]) for point in points]))
        )
        baseline.append(
            float(np.mean([float(point["baselineReturn"]) for point in points]))
        )
        baseline_probabilities.append(
            float(
                np.mean(
                    [float(point["baselineProbabilityUp"]) for point in points]
                )
            )
        )
    validation = _validation_with_recent(
        model=(
            "nested_walk_forward"
            if top_model_count == 1
            else "nested_model_average"
        ),
        horizon=horizon,
        dates=selected_dates,
        actual=actual,
        predicted=predicted,
        probabilities=probabilities,
        baseline=baseline,
        baseline_probabilities=baseline_probabilities,
        minimum_non_overlap_observations=(
            MIN_NESTED_NON_OVERLAP_OBSERVATIONS
        ),
    )
    model_counts: dict[str, int] = {}
    for selected_models in selected_model_sets:
        for selected_model in selected_models:
            model_counts[selected_model] = model_counts.get(selected_model, 0) + 1
    validation["modelCounts"] = model_counts
    validation["switches"] = sum(
        current != previous
        for previous, current in zip(
            selected_model_sets,
            selected_model_sets[1:],
        )
    )
    selection_history = [
        {
            "date": date,
            "model": (
                selected_models[0]
                if top_model_count == 1
                else "nested_model_average"
            ),
            "models": list(selected_models),
        }
        for date, selected_models in zip(selected_dates, selected_model_sets)
    ]
    validation["topModelCount"] = top_model_count
    validation["_selectionHistory"] = selection_history
    validation["recentSelections"] = selection_history[-48:]
    return validation


def _robust_nested_model_average_validation(
    validations: dict[str, dict[str, object]],
    horizon: int,
) -> dict[str, object]:
    sensitivity = {
        model_count: _nested_walk_forward_validation(
            validations,
            horizon,
            top_model_count=model_count,
        )
        for model_count in NESTED_ENSEMBLE_ROBUSTNESS_SIZES
    }
    primary = sensitivity[NESTED_ENSEMBLE_PRIMARY_SIZE]
    stable = all(
        result.get("qualified")
        and result.get("nonOverlapStable")
        and result.get("recentStable")
        for result in sensitivity.values()
    )
    primary["robustnessStable"] = stable
    primary["robustnessReasonCode"] = "nested_ensemble_size_instability"
    primary["ensembleSizeRobustness"] = {
        "primarySize": NESTED_ENSEMBLE_PRIMARY_SIZE,
        "sizes": {
            str(model_count): {
                "qualified": result.get("qualified"),
                "recentStable": result.get("recentStable"),
                "nonOverlapStable": result.get("nonOverlapStable"),
                "passedGateCount": result.get("passedGateCount"),
                "oosR2": result.get("oosR2"),
            }
            for model_count, result in sensitivity.items()
        },
    }
    return primary


def _nested_model_average_forecast(
    validations: dict[str, dict[str, object]],
    forecasts: dict[str, object | None],
) -> dict[str, object] | None:
    available_models = [
        model
        for model, forecast in forecasts.items()
        if forecast is not None
    ]
    if len(available_models) < NESTED_ENSEMBLE_PRIMARY_SIZE:
        return None

    def aggregate(model_count: int) -> dict[str, object]:
        selected_models = sorted(
            available_models,
            key=lambda model: _model_rank(validations[model]),
            reverse=True,
        )[:model_count]
        selected_forecasts = [
            forecasts[model]
            for model in selected_models
            if isinstance(forecasts[model], dict)
        ]
        numeric_fields = (
            "probabilityUp",
            "medianReturn",
            "low20",
            "high80",
            "conditionalVol",
            "valueAtRisk95",
            "expectedShortfall95",
        )
        aggregated = {
            field: float(
                np.mean([float(forecast[field]) for forecast in selected_forecasts])
            )
            for field in numeric_fields
        }
        return {
            "componentModels": selected_models,
            **aggregated,
        }

    sensitivity = {
        model_count: aggregate(model_count)
        for model_count in NESTED_ENSEMBLE_ROBUSTNESS_SIZES
    }
    primary = sensitivity[NESTED_ENSEMBLE_PRIMARY_SIZE]
    return {
        "analogs": min(
            int(forecast.get("analogs", 0))
            for forecast in forecasts.values()
            if isinstance(forecast, dict)
        ),
        "model": "nested_model_average",
        "componentCount": NESTED_ENSEMBLE_PRIMARY_SIZE,
        "componentModels": primary["componentModels"],
        "probabilityUp": _json_value(primary["probabilityUp"]),
        "downsideProbability": _json_value(1.0 - primary["probabilityUp"]),
        "medianReturn": _json_value(primary["medianReturn"]),
        "low20": _json_value(primary["low20"]),
        "high80": _json_value(primary["high80"]),
        "conditionalVol": _json_value(primary["conditionalVol"]),
        "valueAtRisk95": _json_value(primary["valueAtRisk95"]),
        "expectedShortfall95": _json_value(primary["expectedShortfall95"]),
        "ensembleSizeSensitivity": {
            str(model_count): {
                key: _json_value(value)
                if key != "componentModels"
                else value
                for key, value in result.items()
            }
            for model_count, result in sensitivity.items()
        },
    }


def _counterfactual_selected_forecast(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    current_date: pd.Timestamp,
    horizon: int,
    validations: dict[str, dict[str, object]],
    forecasts: dict[str, object | None],
    champion: str,
    active_cycles: frozenset[str],
    neutral_values: pd.Series,
) -> dict[str, object] | None:
    if champion == "nested_model_average":
        nested_forecast = forecasts.get(champion)
        required_models = set(
            nested_forecast.get("componentModels", [])
            if isinstance(nested_forecast, dict)
            else []
        )
        if not required_models:
            required_models = set(
                sorted(
                    (
                        model
                        for model, model_forecast in forecasts.items()
                        if model_forecast is not None
                        and model != "nested_model_average"
                    ),
                    key=lambda model: _model_rank(validations[model]),
                    reverse=True,
                )[:NESTED_ENSEMBLE_PRIMARY_SIZE]
            )
    else:
        required_models = {champion}
    state_current = state_features.loc[current_date].copy()
    asset_current = asset_features.loc[current_date].copy()
    category_current = (
        category_features.loc[current_date].copy()
        if category_features is not None
        else None
    )
    for cycle_id, columns in CYCLE_FEATURE_COLUMNS.items():
        if cycle_id in active_cycles:
            continue
        for column in columns:
            value = float(neutral_values[column])
            state_current[column] = value
            asset_current[column] = value
            if category_current is not None:
                category_current[column] = value

    candidate_forecasts: dict[str, object | None] = {
        model: None for model in required_models
    }
    cutoff = current_date - pd.DateOffset(months=horizon)
    analog_known = state_features.join(target.rename("target")).dropna()
    analog_training = analog_known.loc[analog_known.index <= cutoff]
    analog_models = {
        "state_analog",
        "state_analog_shrunk",
        "state_analog_strong_shrink",
        "state_analog_recency",
    }
    if (
        len(analog_training) >= MIN_VALIDATION_TRAIN
        and any(model in required_models for model in analog_models)
    ):
        analogs = _analog_values(
            analog_training[state_features.columns],
            analog_training["target"],
            state_current,
        )
        if len(analogs) >= 12:
            if "state_analog" in required_models:
                candidate_forecasts["state_analog"] = {
                    **_forecast_distribution(analogs),
                    "model": "state_analog",
                }
            if "state_analog_shrunk" in required_models:
                candidate_forecasts["state_analog_shrunk"] = (
                    _shrunk_analog_forecast(
                        analogs,
                        analog_training["target"],
                    )
                )
            if "state_analog_strong_shrink" in required_models:
                candidate_forecasts["state_analog_strong_shrink"] = (
                    _shrunk_analog_forecast(
                        analogs,
                        analog_training["target"],
                        model="state_analog_strong_shrink",
                        prior_observations=STRONG_ANALOG_PRIOR_OBSERVATIONS,
                    )
                )
            if "state_analog_recency" in required_models:
                candidate_forecasts["state_analog_recency"] = (
                    _recency_analog_forecast(analogs, current_date)
                )

    ridge_feature_sets = {
        "state_ridge": (asset_features, asset_current),
        "category_context_ridge": (category_features, category_current),
    }
    for model, (model_features, current_features) in ridge_feature_sets.items():
        if (
            model not in required_models
            or model_features is None
            or current_features is None
        ):
            continue
        ridge_known = model_features.join(target.rename("target")).dropna(
            subset=["target"]
        )
        ridge_training = ridge_known.loc[ridge_known.index <= cutoff]
        if len(ridge_training) >= MIN_VALIDATION_TRAIN:
            candidate_forecasts[model] = _ridge_forecast(
                ridge_training,
                list(model_features.columns),
                current_features,
                validations[model],
                model=model,
            )

    if "state_model_consensus" in required_models:
        candidate_forecasts["state_model_consensus"] = _consensus_forecast(
            state_features=state_features,
            asset_features=asset_features,
            category_features=category_features,
            target=target,
            current_date=current_date,
            horizon=horizon,
            validation=validations["state_model_consensus"],
            current_state_features=state_current,
            current_asset_features=asset_current,
            current_category_features=category_current,
        )

    if champion == "nested_model_average":
        return _nested_model_average_forecast(
            validations,
            candidate_forecasts,
        )
    selected = candidate_forecasts.get(champion)
    return selected if isinstance(selected, dict) else None


def _cycle_state_shapley_attribution(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    current_date: pd.Timestamp,
    horizon: int,
    validations: dict[str, dict[str, object]],
    forecasts: dict[str, object | None],
    champion: str,
    published_forecast: dict[str, object] | None,
) -> dict[str, object] | None:
    cutoff = current_date - pd.DateOffset(months=horizon)
    training_state = state_features.loc[state_features.index <= cutoff]
    if len(training_state) < MIN_VALIDATION_TRAIN:
        return None
    feature_columns = [
        column
        for columns in CYCLE_FEATURE_COLUMNS.values()
        for column in columns
    ]
    neutral_values = training_state[feature_columns].median()
    cycles = tuple(CYCLE_FEATURE_COLUMNS)
    subset_values: dict[frozenset[str], dict[str, float]] = {}
    for mask in range(1 << len(cycles)):
        active = frozenset(
            cycle_id
            for position, cycle_id in enumerate(cycles)
            if mask & (1 << position)
        )
        forecast = _counterfactual_selected_forecast(
            state_features=state_features,
            asset_features=asset_features,
            category_features=category_features,
            target=target,
            current_date=current_date,
            horizon=horizon,
            validations=validations,
            forecasts=forecasts,
            champion=champion,
            active_cycles=active,
            neutral_values=neutral_values,
        )
        if forecast is None:
            return None
        subset_values[active] = {
            metric: float(forecast[metric])
            for metric in ATTRIBUTION_METRICS
        }

    contributions = {
        cycle_id: {metric: 0.0 for metric in ATTRIBUTION_METRICS}
        for cycle_id in cycles
    }
    cycle_count = len(cycles)
    for cycle_id in cycles:
        remaining = [item for item in cycles if item != cycle_id]
        for mask in range(1 << len(remaining)):
            subset = frozenset(
                item
                for position, item in enumerate(remaining)
                if mask & (1 << position)
            )
            weight = (
                math.factorial(len(subset))
                * math.factorial(cycle_count - len(subset) - 1)
                / math.factorial(cycle_count)
            )
            with_cycle = subset | {cycle_id}
            for metric in ATTRIBUTION_METRICS:
                contributions[cycle_id][metric] += weight * (
                    subset_values[with_cycle][metric]
                    - subset_values[subset][metric]
                )

    baseline = subset_values[frozenset()]
    full = subset_values[frozenset(cycles)]
    conservation_error = max(
        abs(
            baseline[metric]
            + sum(contributions[cycle_id][metric] for cycle_id in cycles)
            - full[metric]
        )
        for metric in ATTRIBUTION_METRICS
    )
    published_match_error = (
        max(
            abs(full[metric] - float(published_forecast[metric]))
            for metric in ATTRIBUTION_METRICS
        )
        if published_forecast is not None
        else None
    )
    return {
        "method": "shapley_current_state_neutralization",
        "model": champion,
        "horizonMonths": horizon,
        "cycles": list(cycles),
        "baseline": {
            metric: _json_value(value) for metric, value in baseline.items()
        },
        "full": {
            metric: _json_value(value) for metric, value in full.items()
        },
        "contributions": {
            cycle_id: {
                metric: _json_value(value)
                for metric, value in metrics.items()
            }
            for cycle_id, metrics in contributions.items()
        },
        "ranking": sorted(
            cycles,
            key=lambda cycle_id: abs(
                contributions[cycle_id]["medianReturn"]
            ),
            reverse=True,
        ),
        "neutralValues": {
            cycle_id: {
                column: _json_value(neutral_values[column])
                for column in columns
            }
            for cycle_id, columns in CYCLE_FEATURE_COLUMNS.items()
        },
        "conservationError": _json_value(conservation_error),
        "publishedMatchError": _json_value(published_match_error),
        "notCausal": True,
        "definition": "保持资产自身动量和波动不变，将未激活周期的当前状态替换为预测截点前历史中位数；遍历全部8种组合并用Shapley值分摊交互项。",
    }


def _contribution_sign(value: float) -> int:
    if value > ATTRIBUTION_SIGN_EPSILON:
        return 1
    if value < -ATTRIBUTION_SIGN_EPSILON:
        return -1
    return 0


def _cycle_attribution_stability(
    *,
    state_features: pd.DataFrame,
    asset_features: pd.DataFrame,
    category_features: pd.DataFrame | None,
    target: pd.Series,
    horizon: int,
    current_date: pd.Timestamp,
    validations: dict[str, dict[str, object]],
    forecasts: dict[str, object | None],
    champion: str,
    current_attribution: dict[str, object],
) -> dict[str, object] | None:
    candidate_dates = [
        date
        for date in state_features.index
        if date < current_date
        and (current_date.to_period("M").ordinal - date.to_period("M").ordinal)
        % horizon
        == 0
    ][-ATTRIBUTION_STABILITY_POINTS:]
    history: list[dict[str, object]] = []
    for date in candidate_dates:
        attribution = _cycle_state_shapley_attribution(
            state_features=state_features,
            asset_features=asset_features,
            category_features=category_features,
            target=target,
            current_date=date,
            horizon=horizon,
            validations=validations,
            forecasts=forecasts,
            champion=champion,
            published_forecast=None,
        )
        if attribution is None:
            continue
        contributions = attribution["contributions"]
        dominant_cycle = max(
            CYCLE_FEATURE_COLUMNS,
            key=lambda cycle_id: abs(
                float(contributions[cycle_id]["medianReturn"])
            ),
        )
        history.append(
            {
                "date": date.strftime("%Y-%m"),
                "dominantCycle": dominant_cycle,
                "contributions": {
                    cycle_id: {
                        metric: contributions[cycle_id][metric]
                        for metric in ATTRIBUTION_METRICS
                    }
                    for cycle_id in CYCLE_FEATURE_COLUMNS
                },
            }
        )
    if len(history) < max(12, ATTRIBUTION_STABILITY_POINTS // 2):
        return None

    current_contributions = current_attribution["contributions"]
    current_dominant = str(current_attribution["ranking"][0])
    cycle_summary: dict[str, object] = {}
    for cycle_id in CYCLE_FEATURE_COLUMNS:
        values = np.asarray(
            [
                float(point["contributions"][cycle_id]["medianReturn"])
                for point in history
            ],
            dtype="float64",
        )
        current_value = float(
            current_contributions[cycle_id]["medianReturn"]
        )
        current_sign = _contribution_sign(current_value)
        historical_signs = np.asarray(
            [_contribution_sign(value) for value in values],
            dtype="int64",
        )
        eligible_signs = historical_signs[historical_signs != 0]
        same_sign_share = (
            float(np.mean(eligible_signs == current_sign))
            if current_sign != 0 and len(eligible_signs)
            else None
        )
        cycle_summary[cycle_id] = {
            "currentReturnContribution": _json_value(current_value),
            "medianReturnContribution": _json_value(float(np.median(values))),
            "positiveShare": _json_value(float(np.mean(values > 0))),
            "sameSignShare": _json_value(same_sign_share),
            "dominantShare": _json_value(
                float(
                    np.mean(
                        [
                            point["dominantCycle"] == cycle_id
                            for point in history
                        ]
                    )
                )
            ),
        }
    dominant_persistence = float(
        np.mean(
            [point["dominantCycle"] == current_dominant for point in history]
        )
    )
    dominant_sign_consistency = cycle_summary[current_dominant][
        "sameSignShare"
    ]
    dominant_sign_value = (
        float(dominant_sign_consistency)
        if dominant_sign_consistency is not None
        else 0.0
    )
    absolute_current_contribution = sum(
        abs(float(current_contributions[cycle_id]["medianReturn"]))
        for cycle_id in CYCLE_FEATURE_COLUMNS
    )
    normalized_contribution = absolute_current_contribution / math.sqrt(horizon)
    materiality = (
        "high"
        if normalized_contribution >= 0.015
        else "medium"
        if normalized_contribution >= 0.005
        else "low"
    )
    dominance_status = (
        "persistent"
        if dominant_persistence >= 0.50
        else "mixed"
        if dominant_persistence >= 0.33
        else "rotating"
    )
    direction_status = (
        "consistent"
        if dominant_sign_value >= 0.65
        else "mixed"
        if dominant_sign_value >= 0.50
        else "reversing"
    )
    status = (
        "low_impact"
        if materiality == "low"
        else "stable"
        if dominance_status == "persistent"
        and direction_status == "consistent"
        else "mixed"
        if dominance_status != "rotating" or direction_status != "reversing"
        else "unstable"
    )
    return {
        "status": status,
        "observations": len(history),
        "spacingMonths": horizon,
        "start": history[0]["date"],
        "end": history[-1]["date"],
        "currentDominantCycle": current_dominant,
        "dominantPersistence": _json_value(dominant_persistence),
        "dominantSignConsistency": _json_value(dominant_sign_consistency),
        "dominanceStatus": dominance_status,
        "directionStatus": direction_status,
        "materiality": materiality,
        "absoluteCurrentReturnContribution": _json_value(
            absolute_current_contribution
        ),
        "normalizedReturnContribution": _json_value(normalized_contribution),
        "cycles": cycle_summary,
        "history": history,
        "frozenCurrentSpecification": True,
        "noFutureTargetLeakage": True,
        "notForecastAccuracy": True,
        "definition": "固定当前已通过的模型规格，在历史非重叠截点仅使用当时及以前的训练目标，重复计算三周期Shapley贡献；用于检查贡献方向和主导关系是否持续。",
    }


def attach_cycle_attribution_stability(
    assets: list[dict[str, object]],
    *,
    features: pd.DataFrame,
    returns: pd.DataFrame,
) -> dict[str, object]:
    category_returns = {
        category: returns[category].mean(axis=1, skipna=True)
        for category in returns.columns.get_level_values(0).unique()
    }
    attached = 0
    status_counts = {
        "stable": 0,
        "mixed": 0,
        "unstable": 0,
        "low_impact": 0,
    }
    for asset in assets:
        category = str(asset["category"])
        name = str(asset["name"])
        series = pd.to_numeric(returns[(category, name)], errors="coerce")
        asset_features = build_asset_feature_frame(features, series)
        category_features = (
            build_asset_feature_frame(
                features,
                series,
                category_returns=category_returns[category],
            )
            if returns[category].shape[1] >= 2
            else None
        )
        for horizon_key, result in asset["horizons"].items():
            result["cycleAttributionStability"] = None
            current_attribution = result.get("cycleAttribution")
            if not result["publicationQualified"] or not isinstance(
                current_attribution,
                dict,
            ):
                continue
            horizon = int(horizon_key)
            model_results = result["models"]
            validations = {
                model: model_result["validation"]
                for model, model_result in model_results.items()
            }
            forecasts = {
                model: model_result["forecast"]
                for model, model_result in model_results.items()
            }
            stability = _cycle_attribution_stability(
                state_features=features,
                asset_features=asset_features,
                category_features=category_features,
                target=_future_return(series, horizon),
                horizon=horizon,
                current_date=features.index[-1],
                validations=validations,
                forecasts=forecasts,
                champion=str(result["championModel"]),
                current_attribution=current_attribution,
            )
            result["cycleAttributionStability"] = stability
            if stability is not None:
                attached += 1
                status_counts[str(stability["status"])] += 1
    return {
        "version": "v1_frozen_spec_non_overlapping",
        "assets": attached,
        "points": ATTRIBUTION_STABILITY_POINTS,
        "statusCounts": status_counts,
    }


def _champion_model(validations: dict[str, dict[str, object]]) -> str:
    return max(validations, key=lambda model: _model_rank(validations[model]))


def _public_validation(
    validation: dict[str, object],
    *,
    include_recent_trace: bool,
) -> dict[str, object]:
    return {
        key: value
        for key, value in validation.items()
        if not key.startswith("_")
        and (include_recent_trace or key != "recentTrace")
    }


def _build_asset_result(
    *,
    category: str,
    name: str,
    series: pd.Series,
    features: pd.DataFrame,
    category_returns: pd.Series,
    category_size: int,
    current_date: pd.Timestamp,
    ensemble_horizons: tuple[int, ...] = (3,),
) -> dict[str, object]:
    asset_end = series.last_valid_index()
    freshness_status, lag_months = _freshness_status(
        current_date,
        asset_end,
        category=category,
    )
    current_data_available = freshness_status == "current"
    asset_features = build_asset_feature_frame(features, series)
    category_asset_features = build_asset_feature_frame(
        features,
        series,
        category_returns=category_returns,
    )
    horizons: dict[str, object] = {}
    for horizon in HORIZONS:
        target = _future_return(series, horizon)
        base_validations = {
            "state_analog": _analog_validation(features, target, horizon),
            "state_analog_shrunk": _shrunk_analog_validation(
                features,
                target,
                horizon,
            ),
            "state_analog_strong_shrink": _strong_shrink_validation(
                features,
                target,
                horizon,
            ),
            "state_analog_recency": _robust_recency_validation(
                features,
                target,
                horizon,
            ),
            "state_ridge": _ridge_validation(asset_features, target, horizon),
            "state_model_consensus": _consensus_validation(
                state_features=features,
                asset_features=asset_features,
                category_features=(
                    category_asset_features if category_size >= 2 else None
                ),
                target=target,
                horizon=horizon,
            ),
        }
        if category_size >= 2:
            base_validations["category_context_ridge"] = _ridge_validation(
                category_asset_features,
                target,
                horizon,
                model="category_context_ridge",
            )
        selection_policy = "nested_champion"
        selection_validation = _nested_champion_validation(
            base_validations,
            horizon,
        )
        analog_known = features.join(target.rename("target")).dropna()
        analog_training = analog_known.loc[
            analog_known.index <= current_date - pd.DateOffset(months=horizon)
        ]
        forecasts: dict[str, object | None] = {
            model: None for model in base_validations
        }
        if len(analog_training) >= MIN_VALIDATION_TRAIN:
            analogs = _analog_values(
                analog_training[features.columns],
                analog_training["target"],
                features.loc[current_date],
            )
            if len(analogs) >= 12:
                forecasts["state_analog"] = {
                    **_forecast_distribution(analogs),
                    "model": "state_analog",
                }
                forecasts["state_analog_shrunk"] = _shrunk_analog_forecast(
                    analogs,
                    analog_training["target"],
                )
                forecasts["state_analog_strong_shrink"] = (
                    _shrunk_analog_forecast(
                        analogs,
                        analog_training["target"],
                        model="state_analog_strong_shrink",
                        prior_observations=STRONG_ANALOG_PRIOR_OBSERVATIONS,
                    )
                )
                forecasts["state_analog_recency"] = _recency_analog_forecast(
                    analogs,
                    current_date,
                )
        ridge_feature_sets = {"state_ridge": asset_features}
        if "category_context_ridge" in base_validations:
            ridge_feature_sets["category_context_ridge"] = category_asset_features
        for model, model_features in ridge_feature_sets.items():
            ridge_known = model_features.join(target.rename("target")).dropna(
                subset=["target"]
            )
            ridge_training = ridge_known.loc[
                ridge_known.index <= current_date - pd.DateOffset(months=horizon)
            ]
            if len(ridge_training) >= MIN_VALIDATION_TRAIN:
                forecasts[model] = _ridge_forecast(
                    ridge_training,
                    list(model_features.columns),
                    model_features.loc[current_date],
                    base_validations[model],
                    model=model,
                )
        forecasts["state_model_consensus"] = _consensus_forecast(
            state_features=features,
            asset_features=asset_features,
            category_features=(
                category_asset_features if category_size >= 2 else None
            ),
            target=target,
            current_date=current_date,
            horizon=horizon,
            validation=base_validations["state_model_consensus"],
        )
        validations = base_validations
        if horizon in ensemble_horizons:
            ensemble_validation = _robust_nested_model_average_validation(
                base_validations,
                horizon,
            )
            ensemble_forecast = _nested_model_average_forecast(
                base_validations,
                forecasts,
            )
            validations = {
                **base_validations,
                "nested_model_average": ensemble_validation,
            }
            forecasts["nested_model_average"] = ensemble_forecast
            champion = "nested_model_average"
            selection_validation = ensemble_validation
            selection_policy = "nested_model_average"
        elif horizon in FIXED_MODEL_POLICY_BY_HORIZON:
            champion = FIXED_MODEL_POLICY_BY_HORIZON[horizon]
            selection_validation = base_validations[champion]
            selection_policy = "fixed_model"
        else:
            available_validations = {
                model: base_validations[model]
                for model, model_forecast in forecasts.items()
                if model_forecast is not None
            }
            champion = _champion_model(
                available_validations or base_validations
            )
        validation = validations[champion]
        _attach_validation_uncertainty(validation, horizon)
        if selection_validation is not validation:
            _attach_validation_uncertainty(selection_validation, horizon)
        forecast = forecasts[champion]
        publication_reason_codes = list(validation["reasonCodes"])
        if forecast is None:
            publication_reason_codes.append("current_forecast_unavailable")
        if freshness_status == "source_lag":
            publication_reason_codes.append("source_reporting_lag")
        elif freshness_status == "stale":
            publication_reason_codes.append("stale_asset_data")
        if not validation.get("robustnessStable", True):
            publication_reason_codes.append(
                str(
                    validation.get(
                        "robustnessReasonCode",
                        "recency_half_life_instability",
                    )
                )
            )
        if not validation.get("nonOverlapStable", True):
            publication_reason_codes.append("non_overlapping_instability")
        current_model_full_qualified = bool(
            validation["qualified"]
            and validation.get("robustnessStable", True)
            and validation.get("nonOverlapStable", True)
            and forecast is not None
            and current_data_available
        )
        selection_full_qualified = bool(
            selection_validation.get("observations", 0)
            >= MIN_VALIDATION_OBSERVATIONS
            and selection_validation.get("qualified")
            and selection_validation.get("nonOverlapStable", True)
        )
        if selection_policy != "fixed_model":
            if selection_validation.get("observations", 0) < MIN_VALIDATION_OBSERVATIONS:
                publication_reason_codes.append("nested_selection_insufficient")
            elif not selection_full_qualified:
                publication_reason_codes.append("nested_selection_instability")
            elif not selection_validation.get("recentStable"):
                publication_reason_codes.append("nested_selection_recent_instability")
        if current_model_full_qualified and not validation.get("recentStable"):
            publication_reason_codes.append("recent_window_instability")
        full_sample_qualified = bool(
            current_model_full_qualified and selection_full_qualified
        )
        publication_qualified = bool(
            full_sample_qualified
            and validation.get("recentStable")
            and selection_validation.get("recentStable")
        )
        cycle_attribution = (
            _cycle_state_shapley_attribution(
                state_features=features,
                asset_features=asset_features,
                category_features=(
                    category_asset_features if category_size >= 2 else None
                ),
                target=target,
                current_date=current_date,
                horizon=horizon,
                validations=validations,
                forecasts=forecasts,
                champion=champion,
                published_forecast=forecast,
            )
            if publication_qualified and isinstance(forecast, dict)
            else None
        )
        horizons[str(horizon)] = {
            "championModel": champion,
            "selectionPolicy": selection_policy,
            "models": {
                model: {
                    "validation": _public_validation(
                        validations[model],
                        include_recent_trace=False,
                    ),
                    "forecast": forecasts[model],
                }
                for model in validations
            },
            "validation": _public_validation(
                validation,
                include_recent_trace=True,
            ),
            "selectionValidation": _public_validation(
                selection_validation,
                include_recent_trace=True,
            ),
            "forecast": forecast,
            "fullSampleQualified": full_sample_qualified,
            "publicationQualified": publication_qualified,
            "cycleAttribution": cycle_attribution,
            "publicationReasonCodes": publication_reason_codes,
            "status": "limited" if publication_qualified else "blocked",
        }
    qualified_horizons = [
        horizon
        for horizon, result in horizons.items()
        if result["publicationQualified"]
    ]
    return {
        "assetId": f"{category}::{name}",
        "majorCategory": MAJOR_CATEGORY_BY_CATEGORY[category],
        "category": category,
        "name": name,
        "dataEnd": asset_end.strftime("%Y-%m")
        if asset_end is not None and not pd.isna(asset_end)
        else None,
        "observations": int(series.notna().sum()),
        "currentDataAvailable": current_data_available,
        "freshnessStatus": freshness_status,
        "lagMonths": lag_months,
        "qualifiedHorizons": qualified_horizons,
        "status": "limited" if qualified_horizons else "blocked",
        "horizons": horizons,
    }


def _summarize_assets(assets: list[dict[str, object]]) -> dict[str, object]:
    summary = {
        str(horizon): {
            "validatedAssets": 0,
            "nestedValidatedAssets": 0,
            "nestedQualifiedAssets": 0,
            "nestedRecentStableAssets": 0,
            "fullSampleQualifiedAssets": 0,
            "qualifiedAssets": 0,
            "researchForecastAssets": 0,
            "championModels": {
                "state_analog": 0,
                "state_analog_shrunk": 0,
                "state_analog_strong_shrink": 0,
                "state_analog_recency": 0,
                "state_ridge": 0,
                "category_context_ridge": 0,
                "state_model_consensus": 0,
                "nested_model_average": 0,
            },
            "blockedReasonCounts": {},
        }
        for horizon in HORIZONS
    }
    for asset in assets:
        for horizon, result in asset["horizons"].items():
            validation = result["validation"]
            selection_validation = result["selectionValidation"]
            if validation["observations"] >= MIN_VALIDATION_OBSERVATIONS:
                summary[horizon]["validatedAssets"] += 1
            if selection_validation["observations"] >= MIN_VALIDATION_OBSERVATIONS:
                summary[horizon]["nestedValidatedAssets"] += 1
            if (
                selection_validation.get("qualified")
                and selection_validation.get("nonOverlapStable", True)
            ):
                summary[horizon]["nestedQualifiedAssets"] += 1
            if selection_validation.get("recentStable"):
                summary[horizon]["nestedRecentStableAssets"] += 1
            if result["forecast"] is not None:
                summary[horizon]["researchForecastAssets"] += 1
            if result["fullSampleQualified"]:
                summary[horizon]["fullSampleQualifiedAssets"] += 1
            if result["publicationQualified"]:
                summary[horizon]["qualifiedAssets"] += 1
            champion = result["championModel"]
            summary[horizon]["championModels"][champion] += 1
            reason_counts = summary[horizon]["blockedReasonCounts"]
            for reason_code in result["publicationReasonCodes"]:
                reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
    return summary


def _run_asset_job(job: dict[str, object]) -> dict[str, object]:
    return _build_asset_result(**job)


def _build_assets(
    *,
    features: pd.DataFrame,
    returns: pd.DataFrame,
    workers: int,
    ensemble_horizons: tuple[int, ...] = (3,),
) -> list[dict[str, object]]:
    current_date = features.index[-1]
    category_returns = {
        category: returns[category].mean(axis=1, skipna=True)
        for category in returns.columns.get_level_values(0).unique()
    }
    category_sizes = {
        category: int(returns[category].shape[1])
        for category in returns.columns.get_level_values(0).unique()
    }
    worker_count = max(1, workers)
    jobs = [
        {
            "category": category,
            "name": name,
            "series": pd.to_numeric(returns[(category, name)], errors="coerce"),
            "features": features,
            "category_returns": category_returns[category],
            "category_size": category_sizes[category],
            "current_date": current_date,
            "ensemble_horizons": ensemble_horizons,
        }
        for category, name in returns.columns
    ]
    if worker_count == 1:
        assets = [_build_asset_result(**job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            assets = list(executor.map(_run_asset_job, jobs, chunksize=1))
    return assets


def _state_clock(clock: str, decision_date: pd.Timestamp) -> dict[str, object]:
    source_paths = {"C4": C4_PATH, "C5": C5_PATH, "C7": C7_PATH}
    cycles = []
    for cycle_id, path in source_paths.items():
        timeline = json.loads(path.read_text(encoding="utf-8"))["timeline"]
        source_end = pd.Period(str(timeline[-1]["date"]), freq="M")
        lag_months = FEATURE_CLOCK_LAGS[clock][cycle_id]
        used_period = pd.Period(decision_date, freq="M") - lag_months
        cycles.append(
            {
                "cycleId": cycle_id,
                "observationUsed": str(used_period),
                "sourceDataThrough": str(source_end),
                "availabilityLagMonths": lag_months,
                "availableForDecisionMonth": decision_date.strftime("%Y-%m"),
                "identity": "latest_restated_not_true_vintage",
            }
        )
    return {
        "mode": clock,
        "decisionAsOf": decision_date.strftime("%Y-%m"),
        "cycles": cycles,
    }


def _stable_model_validation(result: dict[str, object]) -> bool:
    validation = result["validation"]
    return bool(
        validation.get("qualified")
        and validation.get("robustnessStable", True)
        and validation.get("nonOverlapStable", True)
        and validation.get("recentStable")
    )


def _apply_synchronous_policy_gate(
    asynchronous_assets: list[dict[str, object]],
    synchronous_assets: list[dict[str, object]],
) -> None:
    synchronous_by_id = {
        str(asset["assetId"]): asset for asset in synchronous_assets
    }
    for asset in asynchronous_assets:
        synchronous_asset = synchronous_by_id.get(str(asset["assetId"]))
        for horizon, model in FIXED_MODEL_POLICY_BY_HORIZON.items():
            result = asset["horizons"][str(horizon)]
            synchronous_result = (
                synchronous_asset["horizons"][str(horizon)]
                if synchronous_asset is not None
                else None
            )
            stable = bool(
                synchronous_result is not None
                and synchronous_result["championModel"] == model
                and _stable_model_validation(synchronous_result)
            )
            result["synchronousReferenceStable"] = stable
            if result["publicationQualified"] and not stable:
                result["publicationQualified"] = False
                result["status"] = "blocked"
                result["cycleAttribution"] = None
                result["publicationReasonCodes"].append(
                    "synchronous_reference_instability"
                )
        asset["qualifiedHorizons"] = [
            horizon
            for horizon, result in asset["horizons"].items()
            if result["publicationQualified"]
        ]
        asset["status"] = "limited" if asset["qualifiedHorizons"] else "blocked"


def _paired_trace_metrics(
    asynchronous: dict[str, object],
    synchronous: dict[str, object],
) -> dict[str, object] | None:
    asynchronous_trace = {
        str(point["date"]): point
        for point in asynchronous["selectionValidation"]["recentTrace"]
    }
    synchronous_trace = {
        str(point["date"]): point
        for point in synchronous["selectionValidation"]["recentTrace"]
    }
    dates = sorted(set(asynchronous_trace) & set(synchronous_trace))
    if len(dates) < MIN_RECENT_VALIDATION_OBSERVATIONS:
        return None

    def metrics(trace: dict[str, dict[str, object]]) -> dict[str, float | None]:
        actual = np.asarray(
            [float(trace[date]["actualReturn"]) for date in dates],
            dtype="float64",
        )
        predicted = np.asarray(
            [float(trace[date]["predictedReturn"]) for date in dates],
            dtype="float64",
        )
        probability = np.asarray(
            [float(trace[date]["probabilityUp"]) for date in dates],
            dtype="float64",
        )
        baseline = np.asarray(
            [float(trace[date]["baselineReturn"]) for date in dates],
            dtype="float64",
        )
        actual_up = actual > 0
        denominator = float(np.sum((actual - baseline) ** 2))
        return {
            "directionAccuracy": float(np.mean((predicted >= 0) == actual_up)),
            "brier": float(np.mean((probability - actual_up) ** 2)),
            "mae": float(np.mean(np.abs(predicted - actual))),
            "oosR2": (
                1.0 - float(np.sum((actual - predicted) ** 2)) / denominator
                if denominator > 0
                else None
            ),
        }

    asynchronous_actual = np.asarray(
        [float(asynchronous_trace[date]["actualReturn"]) for date in dates]
    )
    synchronous_actual = np.asarray(
        [float(synchronous_trace[date]["actualReturn"]) for date in dates]
    )
    if not np.allclose(asynchronous_actual, synchronous_actual, equal_nan=True):
        raise ValueError("Clock comparison must use identical realized returns")
    return {
        "observations": len(dates),
        "start": dates[0],
        "end": dates[-1],
        "asynchronous": metrics(asynchronous_trace),
        "synchronous": metrics(synchronous_trace),
    }


def _clock_comparison(
    asynchronous_assets: list[dict[str, object]],
    synchronous_assets: list[dict[str, object]],
) -> dict[str, object]:
    synchronous_by_id = {
        str(asset["assetId"]): asset for asset in synchronous_assets
    }
    horizons: dict[str, object] = {}
    for horizon in map(str, HORIZONS):
        rows = []
        for asynchronous_asset in asynchronous_assets:
            synchronous_asset = synchronous_by_id.get(
                str(asynchronous_asset["assetId"])
            )
            if synchronous_asset is None:
                continue
            paired = _paired_trace_metrics(
                asynchronous_asset["horizons"][horizon],
                synchronous_asset["horizons"][horizon],
            )
            if paired is not None:
                rows.append(paired)

        def median(clock: str, metric: str) -> object:
            values = [
                float(row[clock][metric])
                for row in rows
                if row[clock][metric] is not None
            ]
            return _json_value(np.median(values)) if values else None

        def better_count(metric: str, *, higher_is_better: bool) -> int:
            count = 0
            for row in rows:
                asynchronous_value = row["asynchronous"][metric]
                synchronous_value = row["synchronous"][metric]
                if asynchronous_value is None or synchronous_value is None:
                    continue
                if (
                    float(asynchronous_value) > float(synchronous_value)
                    if higher_is_better
                    else float(asynchronous_value) < float(synchronous_value)
                ):
                    count += 1
            return count

        horizons[horizon] = {
            "assetsCompared": len(rows),
            "commonObservationsMedian": _json_value(
                np.median([row["observations"] for row in rows])
            )
            if rows
            else None,
            "commonWindowStart": min((row["start"] for row in rows), default=None),
            "commonWindowEnd": max((row["end"] for row in rows), default=None),
            "asynchronous": {
                "directionAccuracyMedian": median(
                    "asynchronous", "directionAccuracy"
                ),
                "brierMedian": median("asynchronous", "brier"),
                "maeMedian": median("asynchronous", "mae"),
                "oosR2Median": median("asynchronous", "oosR2"),
                "publicationQualifiedAssets": sum(
                    bool(asset["horizons"][horizon]["publicationQualified"])
                    for asset in asynchronous_assets
                ),
            },
            "synchronous": {
                "directionAccuracyMedian": median(
                    "synchronous", "directionAccuracy"
                ),
                "brierMedian": median("synchronous", "brier"),
                "maeMedian": median("synchronous", "mae"),
                "oosR2Median": median("synchronous", "oosR2"),
                "publicationQualifiedAssets": sum(
                    bool(asset["horizons"][horizon]["publicationQualified"])
                    for asset in synchronous_assets
                ),
            },
            "asynchronousBetterAssets": {
                "directionAccuracy": better_count(
                    "directionAccuracy", higher_is_better=True
                ),
                "brier": better_count("brier", higher_is_better=False),
                "mae": better_count("mae", higher_is_better=False),
                "oosR2": better_count("oosR2", higher_is_better=True),
            },
        }
    return {
        "status": "paired_recent_nested_oos",
        "publicationClock": ASYNCHRONOUS_CLOCK,
        "referenceClock": SYNCHRONOUS_CLOCK,
        "minimumCommonObservations": MIN_RECENT_VALIDATION_OBSERVATIONS,
        "horizons": horizons,
        "rule": "同步口径仅作修订后参照；异步口径必须独立通过方向、Brier、MAE、R²及稳定性门槛，不因同步结果更好而恢复当月尚未发布的信息。",
    }


def _synchronous_reference_assets(
    *,
    features: pd.DataFrame,
    returns: pd.DataFrame,
    workers: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    expected_as_of = features.index[-1].strftime("%Y-%m")
    expected_asset_end = returns.index.max().strftime("%Y-%m")
    asset_data_modified_ns = RETURNS_PATH.stat().st_mtime_ns
    refresh = os.environ.get("CIRCLE_REFRESH_SYNC_REFERENCE") == "1"
    if SYNCHRONOUS_REFERENCE_PATH.exists() and not refresh:
        payload = json.loads(
            SYNCHRONOUS_REFERENCE_PATH.read_text(encoding="utf-8")
        )
        meta = payload.get("meta", {})
        assets = payload.get("assets", [])
        if (
            meta.get("asOf") == expected_as_of
            and meta.get("assetDataThrough") == expected_asset_end
            and meta.get("assetDataModifiedNs") == asset_data_modified_ns
            and meta.get("modelVersion") == MODEL_VERSION
            and len(assets) == len(returns.columns)
        ):
            return assets, {
                "status": "cached",
                "generated": meta.get("generated"),
                "asOf": expected_as_of,
                "assetDataThrough": expected_asset_end,
                "assetDataModifiedNs": asset_data_modified_ns,
                "path": str(SYNCHRONOUS_REFERENCE_PATH.relative_to(PROJECT_ROOT)),
            }

    assets = _build_assets(
        features=features,
        returns=returns,
        workers=workers,
    )
    generated = pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
    SYNCHRONOUS_REFERENCE_PATH.write_text(
        json.dumps(
            {
                "meta": {
                    "generated": generated,
                    "asOf": expected_as_of,
                    "assetDataThrough": expected_asset_end,
                    "assetDataModifiedNs": asset_data_modified_ns,
                    "modelVersion": MODEL_VERSION,
                    "forecastClock": SYNCHRONOUS_CLOCK,
                },
                "assets": assets,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return assets, {
        "status": "refreshed",
        "generated": generated,
        "asOf": expected_as_of,
        "assetDataThrough": expected_asset_end,
        "assetDataModifiedNs": asset_data_modified_ns,
        "path": str(SYNCHRONOUS_REFERENCE_PATH.relative_to(PROJECT_ROOT)),
    }


def build_payload(*, workers: int = 1) -> dict[str, object]:
    asynchronous_features = build_feature_frame(ASYNCHRONOUS_CLOCK)
    synchronous_features = build_feature_frame(SYNCHRONOUS_CLOCK)
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    asynchronous_assets = _build_assets(
        features=asynchronous_features,
        returns=returns,
        workers=workers,
    )
    synchronous_assets, synchronous_reference = _synchronous_reference_assets(
        features=synchronous_features,
        returns=returns,
        workers=workers,
    )
    _apply_synchronous_policy_gate(asynchronous_assets, synchronous_assets)
    attribution_stability = attach_cycle_attribution_stability(
        asynchronous_assets,
        features=asynchronous_features,
        returns=returns,
    )
    current_date = asynchronous_features.index[-1]
    horizon_summary = _summarize_assets(asynchronous_assets)

    refreshed_assets = sum(
        asset["currentDataAvailable"] for asset in asynchronous_assets
    )
    source_lag_assets = sum(
        asset["freshnessStatus"] == "source_lag"
        for asset in asynchronous_assets
    )
    stale_assets = sum(
        asset["freshnessStatus"] == "stale" for asset in asynchronous_assets
    )
    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "asOf": current_date.strftime("%Y-%m"),
            "assetDataThrough": returns.index.max().strftime("%Y-%m"),
            "definition": "按月末可得信息构造联合状态：C4库存与C5流动性使用上月已发布状态，C7风险偏好及资产价格使用当月状态。1个月保留历史截点逐期选模；3个月固定采用历史截点排名前4模型平均，并要求前3/4/5模型三种规模全部通过；6个月固定使用72期历史先验收缩的状态近邻，并要求同步参照时钟重复通过。通过发布门槛后，再将C4/C5/C7当前状态逐组中性化并用三因子Shapley值拆解收益、上涨概率、波动和5%情景贡献。",
            "riskDefinition": "valueAtRisk95为条件收益分布5%分位数，expectedShortfall95为该分位数以下的平均条件收益；负值表示损失。",
            "stateIdentity": "latest_restated_with_release_clock_not_true_vintage",
            "modelVersion": MODEL_VERSION,
            "modelPolicies": {
                "1": "nested_champion",
                "3": "nested_model_average",
                "6": "fixed_state_analog_shrunk",
            },
            "forecastClock": ASYNCHRONOUS_CLOCK,
            "stateClock": _state_clock(ASYNCHRONOUS_CLOCK, current_date),
            "synchronousReferenceClock": _state_clock(
                SYNCHRONOUS_CLOCK,
                synchronous_features.index[-1],
            ),
            "synchronousReference": synchronous_reference,
            "attributionStability": attribution_stability,
            "notPortfolioBacktest": True,
        },
        "summary": {
            "assets": len(asynchronous_assets),
            "refreshedAssets": int(refreshed_assets),
            "sourceLagAssets": int(source_lag_assets),
            "staleAssets": int(stale_assets),
            "horizons": horizon_summary,
        },
        "clockComparison": _clock_comparison(
            asynchronous_assets,
            synchronous_assets,
        ),
        "assets": asynchronous_assets,
        "governance": {
            "publicationStatus": "limited",
            "sourceReportingLagLimits": SOURCE_REPORTING_LAG_LIMITS,
            "allowed": ["逐资产上涨概率", "条件收益区间", "条件波动", "样本外门槛", "模型或组合身份", "双时钟稳健性", "通过资产的周期状态Shapley贡献"],
            "notAllowed": [
                "组合权重",
                "因果归因",
                "交易指令",
                "未通过资产的确定性预测",
            ],
        },
        "caveat": "周期状态仍是修订后序列，不是真实历史vintage；但异步发布时钟禁止在历史截点使用当月尚未发布的C4/C5。同步时钟只作为固定6个月模型的稳健性复核，不参与当前点预测。周期贡献只描述当前预测对C4/C5/C7状态的模型敏感度，交互项由Shapley规则公平分摊，不是经济因果归因或资产配置权重。",
    }


def main() -> None:
    configured_workers = os.environ.get("CIRCLE_FORECAST_WORKERS")
    workers = (
        DEFAULT_FORECAST_WORKERS
        if configured_workers is None
        else max(1, int(configured_workers))
    )
    payload = build_payload(workers=workers)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH),
                "asOf": payload["meta"]["asOf"],
                "summary": payload["summary"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
