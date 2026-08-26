#!/usr/bin/env python3
"""Rebuild the governed C4 forecast from the pseudo-realtime state history."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
BRIDGE_INPUT = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "c4_forecast_reproducible_latest.json"
HORIZONS = (3, 6, 12)
FORECAST_MONTHS = 24
RIDGE_ALPHA = 1.0
RANDOM_SEED = 42


def _phase(level: float, slope: float) -> str:
    if level >= 0:
        return "expansion" if slope >= 0 else "downturn"
    return "recovery" if slope >= 0 else "contraction"


def _features(series: pd.Series, origin: int) -> np.ndarray:
    values = [float(series.iloc[origin - lag]) for lag in range(7)]
    values.extend(
        [
            float(series.iloc[origin] - series.iloc[origin - 3]),
            float(series.iloc[origin] - series.iloc[origin - 6]),
            float(series.iloc[origin - 5 : origin + 1].mean()),
            float(series.iloc[origin - 5 : origin + 1].std(ddof=0)),
        ]
    )
    return np.asarray(values, dtype=float)


def _ridge_predict(series: pd.Series, origin: int, horizon: int) -> float:
    train_origins = list(range(6, origin - horizon + 1))
    if len(train_origins) < 48:
        return float(series.iloc[origin])
    features = np.vstack([_features(series, index) for index in train_origins])
    target = np.asarray(
        [series.iloc[index + horizon] for index in train_origins],
        dtype=float,
    )
    model = Ridge(alpha=RIDGE_ALPHA)
    model.fit(features, target)
    return float(model.predict(_features(series, origin).reshape(1, -1))[0])


def _harmonic_predict(series: pd.Series, origin: int, horizon: int) -> float:
    omega = 2.0 * math.pi / 42.0
    damping = 0.985
    previous = float(series.iloc[origin - 1])
    current = float(series.iloc[origin])
    for _ in range(horizon):
        next_value = (
            2.0 * damping * math.cos(omega) * current
            - damping**2 * previous
        )
        previous, current = current, next_value
    return current


def _analog_predict(series: pd.Series, origin: int, horizon: int) -> float:
    query = _features(series, origin)[:7]
    candidates: list[tuple[float, float]] = []
    for candidate in range(6, origin - horizon + 1):
        candidate_features = _features(series, candidate)[:7]
        distance = float(np.linalg.norm(query - candidate_features))
        candidates.append((distance, float(series.iloc[candidate + horizon])))
    if not candidates:
        return float(series.iloc[origin])
    nearest = sorted(candidates, key=lambda item: item[0])[:8]
    distances = np.asarray([item[0] for item in nearest], dtype=float)
    values = np.asarray([item[1] for item in nearest], dtype=float)
    weights = 1.0 / np.maximum(distances, 1e-6)
    return float(np.average(values, weights=weights))


def _persistence_predict(series: pd.Series, origin: int, horizon: int) -> float:
    del horizon
    return float(series.iloc[origin])


MODELS: dict[str, Callable[[pd.Series, int, int], float]] = {
    "persistence": _persistence_predict,
    "harmonic": _harmonic_predict,
    "ridge": _ridge_predict,
    "analog": _analog_predict,
}


def _evaluate(series: pd.Series) -> tuple[list[dict[str, Any]], dict[int, list[float]]]:
    origins = list(range(84, len(series) - max(HORIZONS), 3))
    metrics: list[dict[str, Any]] = []
    ridge_residuals: dict[int, list[float]] = {}
    for model_name, predict in MODELS.items():
        for horizon in HORIZONS:
            errors: list[float] = []
            sign_hits: list[bool] = []
            phase_hits: list[bool] = []
            residuals: list[float] = []
            for origin in origins:
                predicted = predict(series, origin, horizon)
                actual = float(series.iloc[origin + horizon])
                current = float(series.iloc[origin])
                errors.append(abs(predicted - actual))
                residuals.append(actual - predicted)
                sign_hits.append((predicted >= 0) == (actual >= 0))
                phase_hits.append(
                    _phase(predicted, predicted - current)
                    == _phase(actual, actual - current)
                )
            metrics.append(
                {
                    "model": model_name,
                    "horizon_months": horizon,
                    "n_origins": len(origins),
                    "mae": float(np.mean(errors)),
                    "sign_accuracy": float(np.mean(sign_hits)),
                    "phase_accuracy": float(np.mean(phase_hits)),
                }
            )
            if model_name == "ridge":
                ridge_residuals[horizon] = residuals
    return metrics, ridge_residuals


def _model_summary(metrics: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    frame = pd.DataFrame(metrics)
    persistence = frame[frame["model"] == "persistence"].set_index("horizon_months")
    rows: list[dict[str, Any]] = []
    qualified_models: list[str] = []
    for model_name in MODELS:
        model_rows = frame[frame["model"] == model_name].copy()
        qualified_horizons = 0
        if model_name != "persistence":
            for row in model_rows.itertuples(index=False):
                baseline = persistence.loc[row.horizon_months]
                if row.mae < baseline["mae"] and row.phase_accuracy > baseline["phase_accuracy"]:
                    qualified_horizons += 1
        governance_eligible = model_name not in {"persistence", "harmonic"}
        publish_eligible = qualified_horizons >= 2 and governance_eligible
        if publish_eligible:
            qualified_models.append(model_name)
        rows.append(
            {
                "model": model_name,
                "qualified_horizons": qualified_horizons,
                "governance_eligible": governance_eligible,
                "publish_eligible": publish_eligible,
                "mean_mae": float(model_rows["mae"].mean()),
                "mean_phase_accuracy": float(model_rows["phase_accuracy"].mean()),
            }
        )
    return rows, qualified_models


def _forecast_paths(
    series: pd.Series,
    ridge_residuals: dict[int, list[float]],
    months: int = FORECAST_MONTHS,
) -> list[dict[str, Any]]:
    origin = len(series) - 1
    medians = np.asarray(
        [_ridge_predict(series, origin, horizon) for horizon in range(1, months + 1)],
        dtype=float,
    )
    residual_pool = np.asarray(
        [value for values in ridge_residuals.values() for value in values],
        dtype=float,
    )
    residual_pool = residual_pool - residual_pool.mean()
    rng = np.random.default_rng(RANDOM_SEED)
    paths = np.zeros((500, months), dtype=float)
    for path_index in range(paths.shape[0]):
        error = 0.0
        for horizon in range(1, months + 1):
            innovation = float(rng.choice(residual_pool))
            scale = math.sqrt(min(horizon, 12) / 6.0)
            error = 0.62 * error + innovation * scale
            paths[path_index, horizon - 1] = medians[horizon - 1] + error
    forecast_dates = pd.period_range(
        series.index[-1].to_period("M") + 1,
        periods=months,
        freq="M",
    )
    rows: list[dict[str, Any]] = []
    previous = np.full(paths.shape[0], float(series.iloc[-1]), dtype=float)
    for index, forecast_date in enumerate(forecast_dates):
        levels = paths[:, index]
        slopes = levels - previous
        phases = np.asarray(
            [_phase(float(level), float(slope)) for level, slope in zip(levels, slopes)],
            dtype=object,
        )
        rows.append(
            {
                "date": str(forecast_date),
                "median": float(np.median(levels)),
                "low": float(np.quantile(levels, 0.1)),
                "high": float(np.quantile(levels, 0.9)),
                "p_recovery": float(np.mean(phases == "recovery")),
                "p_expansion": float(np.mean(phases == "expansion")),
                "p_downturn": float(np.mean(phases == "downturn")),
                "p_contraction": float(np.mean(phases == "contraction")),
            }
        )
        previous = levels
    return rows


def _phase_windows(forecast: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phase_keys = {
        "recovery": "p_recovery",
        "expansion": "p_expansion",
        "downturn": "p_downturn",
        "contraction": "p_contraction",
    }
    labels: list[tuple[str, float]] = []
    for row in forecast:
        phase, probability = max(
            ((phase, float(row[key])) for phase, key in phase_keys.items()),
            key=lambda item: item[1],
        )
        labels.append((phase if probability >= 0.5 else "uncertain", probability))
    windows: list[dict[str, Any]] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index < len(labels) and labels[index][0] == labels[start][0]:
            continue
        probabilities = [probability for _, probability in labels[start:index]]
        windows.append(
            {
                "start": forecast[start]["date"],
                "end": forecast[index - 1]["date"],
                "phase": labels[start][0],
                "min_probability": min(probabilities),
                "max_probability": max(probabilities),
            }
        )
        start = index
    return windows


def build_forecast(input_path: Path, output_path: Path) -> dict[str, Any]:
    realtime = json.loads(input_path.read_text(encoding="utf-8"))
    timeline = realtime["timeline"]
    series = pd.Series(
        [row["rt_level"] for row in timeline],
        index=pd.PeriodIndex([row["date"] for row in timeline], freq="M").to_timestamp("M"),
        dtype=float,
    )
    metrics, ridge_residuals = _evaluate(series)
    model_summary, qualified_models = _model_summary(metrics)
    forecast = _forecast_paths(series, ridge_residuals)
    latest_timeline = timeline[-1]
    history = [
        {
            "date": row["date"],
            "rt_level": row["rt_level"],
            "rt_low": row["rt_low"],
            "rt_high": row["rt_high"],
            "confirmed_phase": row["confirmed_phase"],
            "confidence": row["confidence"],
        }
        for row in timeline[-120:]
    ]
    payload = {
        "meta": {
            "generated": date.today().isoformat(),
            "target": "future causal C4 state",
            "backtest": "expanding quarterly origins; 3/6/12 month horizons",
            "timesfm_status": "not installed; not used",
            "forecast_horizon_months": FORECAST_MONTHS,
            "data_as_of": timeline[-1]["date"],
            "uncertainty": "500-path correlated residual bootstrap",
            "publish_rule": "must beat persistence on MAE and phase accuracy in at least two horizons",
            "generator": "scripts/research_c4_forecast.py",
        },
        "metrics": metrics,
        "model_summary": model_summary,
        "qualified_models": qualified_models,
        "weights": {model: 1.0 / len(qualified_models) for model in qualified_models},
        "history": history,
        "latest": {
            "date": latest_timeline["date"],
            "value": latest_timeline["rt_level"],
            "phase": latest_timeline["confirmed_phase"] or latest_timeline["rt_phase"],
            "confidence": latest_timeline["confidence"],
        },
        "forecast": forecast,
        "phase_windows": _phase_windows(forecast),
        "eligibility": {
            "C1": "scenario_only_long_sample",
            "C2": "blocked_period_unidentified",
            "C3": "blocked_period_unidentified",
            "C4": "forecast_candidate" if qualified_models else "blocked_model_validation",
            "C5": "blocked_period_unidentified",
            "C6": "calendar_projection_only",
            "C7": "blocked_period_unidentified",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=BRIDGE_INPUT if BRIDGE_INPUT.exists() else DEFAULT_INPUT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_forecast(args.input, args.output)
    print(
        json.dumps(
            {
                "data_as_of": payload["meta"]["data_as_of"],
                "output": str(args.output),
                "qualified_models": payload["qualified_models"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
