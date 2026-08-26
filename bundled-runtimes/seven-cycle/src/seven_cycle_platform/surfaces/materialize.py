"""Scheduled materialization of governed cycle-asset response surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import pandas as pd

from seven_cycle_platform.products.cycle_asset_surface import (
    CycleAssetSurfaceProduct,
    build_cycle_asset_surface_product,
    write_cycle_asset_surface_product,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.surfaces.response import build_cycle_asset_surface


_CYCLE_IDS = frozenset(f"C{index}" for index in range(1, 8))


@dataclass(frozen=True, slots=True)
class SurfaceRequest:
    asset_id: str
    asset_label: str
    cycle_x: str
    cycle_y: str
    horizon_months: int
    scenario_id: str = "baseline"
    window_months: int = 60
    grid_size: int = 27

    def __post_init__(self) -> None:
        for field_name in ("asset_id", "asset_label", "scenario_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.cycle_x not in _CYCLE_IDS or self.cycle_y not in _CYCLE_IDS:
            raise ValueError("cycle ids must be C1 through C7")
        if self.cycle_x == self.cycle_y:
            raise ValueError("cycle dimensions must differ")
        if not isinstance(self.horizon_months, int) or self.horizon_months < 1:
            raise ValueError("horizon_months must be a positive integer")
        if not isinstance(self.window_months, int) or not 36 <= self.window_months <= 120:
            raise ValueError("window_months must be between 36 and 120")
        if not isinstance(self.grid_size, int) or not 9 <= self.grid_size <= 41:
            raise ValueError("grid_size must be between 9 and 41")


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _finite(value: object) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _shortest_angle_delta(start: float, end: float) -> float:
    return ((end - start + 540.0) % 360.0) - 180.0


def _prediction_at(surface: dict[str, object], x: float, y: float) -> float | None:
    grid = surface.get("grid")
    if not isinstance(grid, list) or not grid:
        return None
    best: tuple[float, float] | None = None
    for item in grid:
        if not isinstance(item, dict):
            continue
        point_x = float(item["x"])
        point_y = float(item["y"])
        x_distance = min(abs(point_x - x), 360.0 - abs(point_x - x))
        y_distance = min(abs(point_y - y), 360.0 - abs(point_y - y))
        distance = x_distance**2 + y_distance**2
        if best is None or distance < best[0]:
            best = (distance, float(item["z"]))
    return best[1] if best is not None else None


def _first_number(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    value = frame.iloc[0][column]
    return float(value) if _finite(value) else None


def _attach_state_path(
    surface: dict[str, object],
    *,
    request: SurfaceRequest,
    current_cycles: pd.DataFrame,
    forecasts: pd.DataFrame,
    current_mapping: pd.DataFrame,
    future_mapping: pd.DataFrame,
) -> None:
    current_subset = current_cycles.loc[
        current_cycles["cycle_id"].isin([request.cycle_x, request.cycle_y])
    ]
    current_angles = {
        str(row.cycle_id): float(row.angle)
        for row in current_subset.itertuples(index=False)
        if _finite(row.angle)
    }
    if request.cycle_x not in current_angles or request.cycle_y not in current_angles:
        surface["current_point"] = None
        surface["future_path"] = []
        return
    selected_current_mapping = current_mapping.loc[
        current_mapping["asset_id"].eq(request.asset_id)
        & current_mapping["horizon_months"].eq(request.horizon_months)
    ]
    current_return = _first_number(selected_current_mapping, "absolute_expected_return")
    if current_return is None:
        current_return = _prediction_at(
            surface,
            current_angles[request.cycle_x],
            current_angles[request.cycle_y],
        )
    if current_return is None:
        surface["current_point"] = None
        surface["future_path"] = []
        return
    current_point = {
        "x": current_angles[request.cycle_x],
        "y": current_angles[request.cycle_y],
        "z": current_return,
    }
    surface["current_point"] = current_point
    selected_forecasts = forecasts.loc[
        forecasts["cycle_id"].isin([request.cycle_x, request.cycle_y])
        & forecasts["horizon_months"].eq(request.horizon_months)
        & forecasts["status"].eq("available")
    ]
    forecast_angles = {
        str(row.cycle_id): float(row.angle_q50)
        for row in selected_forecasts.itertuples(index=False)
        if _finite(row.angle_q50)
    }
    selected_future_mapping = future_mapping.loc[
        future_mapping["asset_id"].eq(request.asset_id)
        & future_mapping["horizon_months"].eq(request.horizon_months)
        & future_mapping["scenario_id"].eq(request.scenario_id)
        & future_mapping["status"].eq("available")
    ]
    future_return = _first_number(selected_future_mapping, "absolute_expected_return")
    if (
        request.cycle_x not in forecast_angles
        or request.cycle_y not in forecast_angles
        or future_return is None
    ):
        surface["future_path"] = []
        return
    delta_x = _shortest_angle_delta(current_point["x"], forecast_angles[request.cycle_x])
    delta_y = _shortest_angle_delta(current_point["y"], forecast_angles[request.cycle_y])
    surface["future_path"] = [
        {
            "label": "当前" if index == 0 else "未来预测" if index == 4 else f"路径 {index}",
            "x": (current_point["x"] + delta_x * (index / 4.0) + 360.0) % 360.0,
            "y": (current_point["y"] + delta_y * (index / 4.0) + 360.0) % 360.0,
            "z": current_point["z"] + (future_return - current_point["z"]) * (index / 4.0),
        }
        for index in range(5)
    ]


def materialize_cycle_asset_surfaces(
    *,
    cycles: pd.DataFrame,
    returns: pd.DataFrame,
    current_cycles: pd.DataFrame,
    forecasts: pd.DataFrame,
    current_mapping: pd.DataFrame,
    future_mapping: pd.DataFrame,
    requests: Iterable[SurfaceRequest],
    context: RunContext,
) -> CycleAssetSurfaceProduct:
    """Build all requested surfaces into one governed product."""

    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    _require_columns(cycles, {"date", "cycle_id", "angle"}, "cycles")
    _require_columns(
        returns,
        {"asset_id", "period_end", "horizon_months", "observed_return"},
        "returns",
    )
    _require_columns(current_cycles, {"cycle_id", "angle"}, "current_cycles")
    _require_columns(
        forecasts,
        {"cycle_id", "horizon_months", "status", "angle_q50"},
        "forecasts",
    )
    _require_columns(
        current_mapping,
        {"asset_id", "horizon_months", "absolute_expected_return"},
        "current_mapping",
    )
    _require_columns(
        future_mapping,
        {"asset_id", "horizon_months", "scenario_id", "status", "absolute_expected_return"},
        "future_mapping",
    )
    results: list[dict[str, object]] = []
    for request in requests:
        if not isinstance(request, SurfaceRequest):
            raise TypeError("requests must contain SurfaceRequest values")
        selected_cycles = cycles.loc[
            cycles["cycle_id"].isin([request.cycle_x, request.cycle_y])
        ].copy()
        latest_dates = sorted(selected_cycles["date"].dropna().unique())[-request.window_months :]
        selected_cycles = selected_cycles.loc[selected_cycles["date"].isin(latest_dates)]
        selected_returns = returns.loc[
            returns["asset_id"].eq(request.asset_id)
            & returns["horizon_months"].eq(request.horizon_months)
        ].copy()
        surface = build_cycle_asset_surface(
            cycles=selected_cycles,
            returns=selected_returns,
            asset_id=request.asset_id,
            asset_label=request.asset_label,
            cycle_x=request.cycle_x,
            cycle_y=request.cycle_y,
            horizon_months=request.horizon_months,
            grid_size=request.grid_size,
        )
        surface["horizon_months"] = request.horizon_months
        surface["scenario_id"] = request.scenario_id
        surface["window_months"] = request.window_months
        surface["grid_size"] = request.grid_size
        _attach_state_path(
            surface,
            request=request,
            current_cycles=current_cycles,
            forecasts=forecasts,
            current_mapping=current_mapping,
            future_mapping=future_mapping,
        )
        results.append(surface)
    return build_cycle_asset_surface_product(results, context=context)


def build_and_write_cycle_asset_surfaces(
    run_dir: Path,
    *,
    cycles: pd.DataFrame,
    returns: pd.DataFrame,
    current_cycles: pd.DataFrame,
    forecasts: pd.DataFrame,
    current_mapping: pd.DataFrame,
    future_mapping: pd.DataFrame,
    requests: Iterable[SurfaceRequest],
    context: RunContext,
) -> Path:
    product = materialize_cycle_asset_surfaces(
        cycles=cycles,
        returns=returns,
        current_cycles=current_cycles,
        forecasts=forecasts,
        current_mapping=current_mapping,
        future_mapping=future_mapping,
        requests=requests,
        context=context,
    )
    return write_cycle_asset_surface_product(run_dir, product, context=context)


__all__ = [
    "SurfaceRequest",
    "build_and_write_cycle_asset_surfaces",
    "materialize_cycle_asset_surfaces",
]
