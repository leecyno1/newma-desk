"""Evidence-gated cycle-pair response surfaces for asset outcomes."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_MINIMUM_SAMPLES = 36
BANDWIDTH_CANDIDATES = (0.18, 0.25, 0.34, 0.46, 0.62)
ESTIMATOR_VERSION = "circular-kernel-purged-loocv-v2"


def _normalized_angle(value: float) -> float:
    normalized = float(value) % 360.0
    return normalized + 360.0 if normalized < 0.0 else normalized


def _circular_distance(left: np.ndarray | float, right: float) -> np.ndarray:
    direct = np.abs(np.mod(left, 360.0) - _normalized_angle(right))
    return np.minimum(direct, 360.0 - direct) / 180.0


def _weighted_prediction(
    observations: pd.DataFrame,
    *,
    x: float,
    y: float,
    bandwidth: float,
    excluded_indices: np.ndarray | None = None,
) -> dict[str, float] | None:
    x_values = observations["x"].to_numpy(dtype=float)
    y_values = observations["y"].to_numpy(dtype=float)
    z_values = observations["z"].to_numpy(dtype=float)
    squared_distance = np.square(_circular_distance(x_values, x)) + np.square(
        _circular_distance(y_values, y)
    )
    weights = np.exp(-0.5 * squared_distance / float(bandwidth**2))
    if excluded_indices is not None:
        weights[excluded_indices] = 0.0
    total_weight = float(weights.sum())
    if total_weight <= 1e-10:
        return None
    prediction = float(np.dot(weights, z_values) / total_weight)
    residual_scale = float(
        math.sqrt(np.dot(weights, np.square(z_values - prediction)) / total_weight)
    )
    return {
        "prediction": prediction,
        "density": total_weight,
        "residual_scale": residual_scale,
    }


def _month_number(value: object) -> int:
    timestamp = pd.Timestamp(value)
    return int(timestamp.year * 12 + timestamp.month)


def _oos_evidence(
    observations: pd.DataFrame,
    bandwidth: float,
    *,
    horizon_months: int,
) -> dict[str, float] | None:
    z_values = observations["z"].to_numpy(dtype=float)
    baseline_mse = float(np.mean(np.square(z_values - float(z_values.mean()))))
    if baseline_mse <= 1e-12:
        return None
    squared_errors: list[float] = []
    month_numbers = observations["date"].map(_month_number).to_numpy(dtype=int)
    for index, row in enumerate(observations.itertuples(index=False)):
        excluded_indices = np.flatnonzero(
            np.abs(month_numbers - month_numbers[index]) < horizon_months
        )
        prediction = _weighted_prediction(
            observations,
            x=float(row.x),
            y=float(row.y),
            bandwidth=bandwidth,
            excluded_indices=excluded_indices,
        )
        if prediction is None:
            return None
        squared_errors.append(float((float(row.z) - prediction["prediction"]) ** 2))
    mse = float(np.mean(squared_errors))
    return {"mse": mse, "score": float(1.0 - (mse / baseline_mse))}


def _select_bandwidth(
    observations: pd.DataFrame,
    *,
    horizon_months: int,
) -> dict[str, float] | None:
    candidates: list[dict[str, float]] = []
    for bandwidth in BANDWIDTH_CANDIDATES:
        evidence = _oos_evidence(
            observations,
            bandwidth,
            horizon_months=horizon_months,
        )
        if evidence is not None:
            candidates.append({"bandwidth": bandwidth, **evidence})
    return min(candidates, key=lambda candidate: candidate["mse"]) if candidates else None


def _observations(
    cycles: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    cycle_x: str,
    cycle_y: str,
) -> pd.DataFrame:
    required_cycle_columns = {"date", "cycle_id", "angle"}
    required_return_columns = {"period_end", "observed_return"}
    if not required_cycle_columns.issubset(cycles.columns):
        raise ValueError("cycles is missing required response-surface columns")
    if not required_return_columns.issubset(returns.columns):
        raise ValueError("returns is missing required response-surface columns")
    selected_cycles = cycles.loc[
        cycles["cycle_id"].isin([cycle_x, cycle_y]),
        [column for column in ["date", "cycle_id", "angle", "vintage"] if column in cycles.columns],
    ].copy()
    selected_cycles["angle"] = pd.to_numeric(selected_cycles["angle"], errors="coerce")
    selected_cycles = selected_cycles.dropna(subset=["date", "cycle_id", "angle"])
    selected_cycles = selected_cycles.drop_duplicates(["date", "cycle_id"], keep="first")
    angles = selected_cycles.pivot(index="date", columns="cycle_id", values="angle")
    if cycle_x not in angles.columns or cycle_y not in angles.columns:
        return pd.DataFrame(columns=["date", "x", "y", "z", "vintage"])
    normalized_returns = returns.copy()
    if "return_basis" in normalized_returns.columns:
        normalized_returns = normalized_returns.loc[
            ~normalized_returns["return_basis"].isin(["excess", "excess_return"])
        ]
    normalized_returns["observed_return"] = pd.to_numeric(
        normalized_returns["observed_return"], errors="coerce"
    )
    normalized_returns = normalized_returns.dropna(subset=["period_end", "observed_return"])
    normalized_returns = normalized_returns.drop_duplicates("period_end", keep="first")
    joined = angles[[cycle_x, cycle_y]].join(
        normalized_returns.set_index("period_end")[["observed_return"]], how="inner"
    )
    vintage_by_date = (
        selected_cycles.drop_duplicates("date", keep="first").set_index("date")["vintage"]
        if "vintage" in selected_cycles.columns
        else pd.Series(dtype=object)
    )
    observations = pd.DataFrame(
        {
            "date": list(joined.index),
            "x": joined[cycle_x].map(_normalized_angle).to_numpy(dtype=float),
            "y": joined[cycle_y].map(_normalized_angle).to_numpy(dtype=float),
            "z": joined["observed_return"].to_numpy(dtype=float),
            "vintage": [str(vintage_by_date.get(date, "unknown")) for date in joined.index],
        }
    )
    return observations.sort_values("date", kind="mergesort").reset_index(drop=True)


def build_cycle_asset_surface(
    *,
    cycles: pd.DataFrame,
    returns: pd.DataFrame,
    asset_id: str,
    asset_label: str,
    cycle_x: str,
    cycle_y: str,
    horizon_months: int = 1,
    grid_size: int = 25,
    minimum_samples: int = DEFAULT_MINIMUM_SAMPLES,
) -> dict[str, Any]:
    """Build one deterministic, evidence-gated response surface."""

    if cycle_x == cycle_y:
        raise ValueError("cycle_x and cycle_y must differ")
    if cycle_x not in {f"C{index}" for index in range(1, 8)} or cycle_y not in {
        f"C{index}" for index in range(1, 8)
    }:
        raise ValueError("cycle ids must be C1 through C7")
    if not isinstance(minimum_samples, int) or minimum_samples < 12:
        raise ValueError("minimum_samples must be an integer >= 12")
    if not isinstance(horizon_months, int) or horizon_months < 1:
        raise ValueError("horizon_months must be a positive integer")
    observations = _observations(cycles, returns, cycle_x=cycle_x, cycle_y=cycle_y)

    def result(
        *,
        status: str,
        reason: str,
        grid: list[dict[str, float]] | None = None,
        bandwidth: float | None = None,
        oos_score: float | None = None,
    ) -> dict[str, Any]:
        return {
            "asset_id": str(asset_id),
            "asset_label": str(asset_label),
            "cycle_x": cycle_x,
            "cycle_y": cycle_y,
            "metric": "observed_return",
            "estimator_version": ESTIMATOR_VERSION,
            "status": status,
            "observations": [
                {
                    "date": pd.Timestamp(row.date).date().isoformat(),
                    "x": float(row.x),
                    "y": float(row.y),
                    "z": float(row.z),
                    "vintage": str(row.vintage),
                }
                for row in observations.itertuples(index=False)
            ],
            "grid": grid or [],
            "evidence": {
                "sample_count": int(len(observations)),
                "bandwidth": bandwidth,
                "oos_score": oos_score,
                "identifiable": status == "available",
                "reason": reason,
            },
        }

    if len(observations) < minimum_samples:
        return result(
            status="not_identifiable",
            reason=f"有效历史样本不足：至少 {minimum_samples} 期，当前 {len(observations)} 期",
        )
    selected = _select_bandwidth(
        observations,
        horizon_months=horizon_months,
    )
    if selected is None:
        reason = (
            "净化交叠样本后缺少可检验的横截面变化"
            if horizon_months > 1
            else "历史收益缺少可检验的横截面变化"
        )
        return result(status="not_identifiable", reason=reason)
    if selected["score"] <= 0.0:
        reason = (
            "净化交叠样本后，留一法外样本表现未优于历史均值，不发布拟合曲面"
            if horizon_months > 1
            else "留一法外样本表现未优于历史均值，不发布拟合曲面"
        )
        return result(
            status="not_identifiable",
            reason=reason,
            bandwidth=float(selected["bandwidth"]),
            oos_score=float(selected["score"]),
        )
    normalized_grid_size = max(9, min(41, int(round(grid_size))))
    grid: list[dict[str, float]] = []
    for x in np.linspace(0.0, 360.0, normalized_grid_size):
        for y in np.linspace(0.0, 360.0, normalized_grid_size):
            prediction = _weighted_prediction(
                observations,
                x=float(x),
                y=float(y),
                bandwidth=float(selected["bandwidth"]),
            )
            if prediction is None:
                continue
            interval = 1.2816 * prediction["residual_scale"]
            grid.append(
                {
                    "x": float(x),
                    "y": float(y),
                    "z": prediction["prediction"],
                    "lower80": prediction["prediction"] - interval,
                    "upper80": prediction["prediction"] + interval,
                    "density": prediction["density"],
                }
            )
    return result(
        status="available",
        reason="样本量与留一法外样本检验通过",
        grid=grid,
        bandwidth=float(selected["bandwidth"]),
        oos_score=float(selected["score"]),
    )


__all__ = [
    "BANDWIDTH_CANDIDATES",
    "DEFAULT_MINIMUM_SAMPLES",
    "ESTIMATOR_VERSION",
    "build_cycle_asset_surface",
]
