"""Deterministic response-surface queries over one verified immutable catalog."""

from __future__ import annotations

from typing import Any
import json

import pandas as pd

from seven_cycle_platform.api.dependencies import RequestContext
from seven_cycle_platform.api.repository import QueryResult
from seven_cycle_platform.surfaces import (
    build_cycle_asset_surface,
    select_preferred_cycle_vintage,
)


ASSET_LABELS = {
    "gold": "黄金",
    "cn_equity_hs300": "沪深300",
    "cn_equity_csi500": "中证500",
    "cn_bond_total": "中证全债",
    "cn_bond_government_index": "中国国债",
    "crude_oil": "原油",
    "copper": "铜",
    "usd_cny": "美元兑人民币",
}


def _frame(
    context: RequestContext, sql: str, parameters: list[object]
) -> pd.DataFrame:
    return context.connection.execute(sql, parameters).fetch_arrow_table().to_pandas()


def _shortest_angle_delta(start: float, end: float) -> float:
    return ((end - start + 540.0) % 360.0) - 180.0


def _finite(value: object) -> bool:
    try:
        return value is not None and pd.notna(value) and float(value) == float(value)
    except (TypeError, ValueError):
        return False


def _prediction_at(surface: dict[str, Any], x: float, y: float) -> float | None:
    grid = surface.get("grid", [])
    if not grid:
        return None
    best: tuple[float, float] | None = None
    for point in grid:
        x_distance = min(abs(float(point["x"]) - x), 360.0 - abs(float(point["x"]) - x))
        y_distance = min(abs(float(point["y"]) - y), 360.0 - abs(float(point["y"]) - y))
        distance = x_distance**2 + y_distance**2
        if best is None or distance < best[0]:
            best = (distance, float(point["z"]))
    return best[1] if best is not None else None


def _state_path(
    context: RequestContext,
    *,
    surface: dict[str, Any],
    asset_id: str,
    cycle_x: str,
    cycle_y: str,
    horizon: int,
    scenario: str,
) -> tuple[dict[str, float] | None, list[dict[str, float | str]]]:
    current_cycles = _frame(
        context,
        """
        SELECT cycle_id, angle
        FROM cycle_current
        WHERE cycle_id IN (?, ?)
        ORDER BY cycle_id
        """,
        [cycle_x, cycle_y],
    )
    current_angles = {
        str(row.cycle_id): float(row.angle)
        for row in current_cycles.itertuples(index=False)
        if _finite(row.angle)
    }
    if cycle_x not in current_angles or cycle_y not in current_angles:
        return None, []
    current_mapping = _frame(
        context,
        """
        SELECT absolute_expected_return
        FROM asset_mapping_current
        WHERE asset_id = ? AND horizon_months = ?
        ORDER BY asset_id
        LIMIT 1
        """,
        [asset_id, horizon],
    )
    current_return = (
        float(current_mapping.iloc[0]["absolute_expected_return"])
        if not current_mapping.empty
        and _finite(current_mapping.iloc[0]["absolute_expected_return"])
        else _prediction_at(surface, current_angles[cycle_x], current_angles[cycle_y])
    )
    if current_return is None:
        return None, []
    current_point = {
        "x": current_angles[cycle_x],
        "y": current_angles[cycle_y],
        "z": current_return,
    }
    forecasts = _frame(
        context,
        """
        SELECT cycle_id, angle_q50
        FROM cycle_forecast
        WHERE cycle_id IN (?, ?) AND horizon_months = ? AND status = 'available'
        ORDER BY cycle_id
        """,
        [cycle_x, cycle_y, horizon],
    )
    forecast_angles = {
        str(row.cycle_id): float(row.angle_q50)
        for row in forecasts.itertuples(index=False)
        if _finite(row.angle_q50)
    }
    future_mapping = _frame(
        context,
        """
        SELECT absolute_expected_return
        FROM asset_mapping_future
        WHERE asset_id = ? AND horizon_months = ? AND scenario_id = ?
          AND status = 'available'
        ORDER BY asset_id
        LIMIT 1
        """,
        [asset_id, horizon, scenario],
    )
    if (
        cycle_x not in forecast_angles
        or cycle_y not in forecast_angles
        or future_mapping.empty
        or not _finite(future_mapping.iloc[0]["absolute_expected_return"])
    ):
        return current_point, []
    future_return = float(future_mapping.iloc[0]["absolute_expected_return"])
    delta_x = _shortest_angle_delta(current_point["x"], forecast_angles[cycle_x])
    delta_y = _shortest_angle_delta(current_point["y"], forecast_angles[cycle_y])
    path: list[dict[str, float | str]] = []
    for index in range(5):
        progress = index / 4.0
        path.append(
            {
                "label": "当前" if index == 0 else "未来预测" if index == 4 else f"路径 {index}",
                "x": (current_point["x"] + delta_x * progress + 360.0) % 360.0,
                "y": (current_point["y"] + delta_y * progress + 360.0) % 360.0,
                "z": current_point["z"] + (future_return - current_point["z"]) * progress,
            }
        )
    return current_point, path


def _published_surface_available(context: RequestContext) -> bool:
    row = context.connection.execute(
        "SELECT available FROM _catalog_views WHERE view_name = 'cycle_asset_surface'"
    ).fetchone()
    return bool(row and row[0])


def _query_published_surface(
    context: RequestContext,
    *,
    asset_id: str,
    cycle_x: str,
    cycle_y: str,
    horizon: int,
    scenario: str,
    window_months: int,
    grid_size: int,
) -> QueryResult:
    def query(selected_scenario: str) -> pd.DataFrame:
        return _frame(
            context,
            """
        SELECT *
        FROM cycle_asset_surface
        WHERE asset_id = ? AND cycle_x = ? AND cycle_y = ?
          AND horizon_months = ? AND scenario_id = ?
          AND window_months = ? AND grid_size = ?
        ORDER BY asset_id, cycle_x, cycle_y
        """,
            [
                asset_id,
                cycle_x,
                cycle_y,
                horizon,
                selected_scenario,
                window_months,
                grid_size,
            ],
        )

    frame = query(scenario)
    scenario_fallback = frame.empty and scenario != "baseline"
    if scenario_fallback:
        frame = query("baseline")
    if frame.empty:
        return QueryResult(
            rows=[],
            total=0,
            available=True,
            view="cycle_asset_surface",
            primary_usage_statuses=(),
        )
    row = frame.iloc[0].to_dict()
    current_json = row.pop("current_point_json")
    result = {
        "asset_id": row["asset_id"],
        "asset_label": row["asset_label"],
        "cycle_x": row["cycle_x"],
        "cycle_y": row["cycle_y"],
        "metric": row["metric"],
        "estimator_version": row["estimator_version"],
        "horizon_months": int(row["horizon_months"]),
        "scenario_id": row["scenario_id"],
        "requested_scenario_id": scenario,
        "scenario_fallback": scenario_fallback,
        "window_months": int(row["window_months"]),
        "grid_size": int(row["grid_size"]),
        "status": row["status"],
        "observations": json.loads(row["observations_json"]),
        "grid": json.loads(row["grid_json"]),
        "current_point": None if current_json is None or pd.isna(current_json) else json.loads(current_json),
        "future_path": [] if scenario_fallback else json.loads(row["future_path_json"]),
        "evidence": {
            "sample_count": int(row["sample_count"]),
            "bandwidth": None if pd.isna(row["bandwidth"]) else float(row["bandwidth"]),
            "oos_score": None if pd.isna(row["oos_score"]) else float(row["oos_score"]),
            "identifiable": bool(row["identifiable"]),
            "reason": row["reason"],
        },
        "source_kind": "published_product",
    }
    return QueryResult(
        rows=[result],
        total=1,
        available=True,
        view="cycle_asset_surface",
        primary_usage_statuses=(str(result["status"]),),
    )


def query_cycle_asset_surface(
    context: RequestContext,
    *,
    asset_id: str,
    cycle_x: str,
    cycle_y: str,
    horizon: int,
    scenario: str,
    window_months: int,
    grid_size: int,
) -> QueryResult:
    if _published_surface_available(context):
        return _query_published_surface(
            context,
            asset_id=asset_id,
            cycle_x=cycle_x,
            cycle_y=cycle_y,
            horizon=horizon,
            scenario=scenario,
            window_months=window_months,
            grid_size=grid_size,
        )
    cycles = _frame(
        context,
        """
        SELECT date, cycle_id, angle, vintage
        FROM cycle_history
        WHERE cycle_id IN (?, ?)
        ORDER BY date, cycle_id
        """,
        [cycle_x, cycle_y],
    )
    cycles = select_preferred_cycle_vintage(cycles)
    if not cycles.empty:
        latest_dates = sorted(cycles["date"].dropna().unique())[-window_months:]
        cycles = cycles.loc[cycles["date"].isin(latest_dates)].reset_index(drop=True)
    returns = _frame(
        context,
        """
        SELECT period_end, observed_return, return_basis, component_type, component_id
        FROM attribution
        WHERE asset_id = ? AND horizon_months = ?
        ORDER BY period_end, component_type, component_id
        """,
        [asset_id, horizon],
    )
    surface = build_cycle_asset_surface(
        cycles=cycles,
        returns=returns,
        asset_id=asset_id,
        asset_label=ASSET_LABELS.get(asset_id, asset_id),
        cycle_x=cycle_x,
        cycle_y=cycle_y,
        horizon_months=horizon,
        grid_size=grid_size,
    )
    current_point, future_path = _state_path(
        context,
        surface=surface,
        asset_id=asset_id,
        cycle_x=cycle_x,
        cycle_y=cycle_y,
        horizon=horizon,
        scenario=scenario,
    )
    surface["horizon_months"] = horizon
    surface["scenario_id"] = scenario
    surface["window_months"] = window_months
    surface["current_point"] = current_point
    surface["future_path"] = future_path
    surface["source_kind"] = "derived_fallback"
    return QueryResult(
        rows=[surface],
        total=1,
        available=True,
        view="cycle_asset_surface",
        primary_usage_statuses=(str(surface["status"]),),
    )


__all__ = ["query_cycle_asset_surface"]
