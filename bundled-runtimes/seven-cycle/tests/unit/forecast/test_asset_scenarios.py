import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from seven_cycle_platform.attribution.stage2 import (
    CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    ChannelToAssetResult,
)
from seven_cycle_platform.forecast import (
    ASSET_FORECAST_COMPONENT_COLUMNS,
    ASSET_FORECAST_DRAW_COLUMNS,
    ASSET_FORECAST_MONTHLY_COLUMNS,
    ASSET_FORECAST_SUMMARY_COLUMNS,
    BENCHMARK_FORECAST_INPUT_COLUMNS,
    CONTROL_FORECAST_INPUT_COLUMNS,
    EVENT_FORECAST_INPUT_COLUMNS,
    INTERACTION_FORECAST_INPUT_COLUMNS,
    POSITIONING_FORECAST_INPUT_COLUMNS,
    RESIDUAL_FORECAST_INPUT_COLUMNS,
    SCENARIO_CHANNEL_PATH_COLUMNS,
    STANDARD_SCENARIO_IDS,
    VALUATION_FORECAST_INPUT_COLUMNS,
    AssetForecastConfig,
    AssetForecastInput,
    AssetForecastResult,
    ScenarioCatalog,
    ScenarioDefinition,
    ScenarioShock,
    forecast_asset_distributions,
    load_scenario_catalog,
)
from seven_cycle_platform.forecast.channels import (
    CHANNEL_HISTORY_COLUMNS,
    CURRENT_CHANNEL_STATE_COLUMNS,
    CURRENT_EXOGENOUS_PATH_COLUMNS,
    CYCLE_PREDICTOR_ARCHIVE_COLUMNS,
    EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
    ChannelForecastConfig,
    ChannelForecastInput,
    ChannelForecastResult,
    forecast_transmission_channels,
)
from seven_cycle_platform.forecast.cycles import (
    CALIBRATION_HISTORY_COLUMNS,
    CYCLE_STATE_COLUMNS,
    LEADING_SIGNAL_COLUMNS,
    CycleForecastConfig,
    CycleForecastInput,
    forecast_cycle_phases,
)
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.registry.loader import load_registry_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AS_OF = date(2024, 6, 30)
FORECAST_DATES = pd.date_range("2024-07-31", periods=12, freq="ME")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
ASSET_ALPHA = "asset_alpha"
ASSET_SAFE = "asset_safe"


def _registry():
    return load_registry_bundle(PROJECT_ROOT / "config" / "seven_cycle")


def _cycle_states() -> pd.DataFrame:
    rows = []
    for position, cycle in enumerate(_registry().cycles, start=1):
        center_period = (
            float(cycle.initial_center)
            if cycle.initial_center is not None
            else (float(cycle.search_min) + float(cycle.search_max)) / 2.0
        )
        period_months = (
            center_period * 12.0 if cycle.frequency == "A" else center_period
        )
        rows.append(
            {
                "as_of": AS_OF,
                "state_date": AS_OF,
                "visible_date": AS_OF,
                "data_vintage": AS_OF,
                "cycle_id": cycle.cycle_id,
                "status": "available",
                "unavailable_reason": None,
                "level": 0.45 - 0.03 * position,
                "quadrature": 0.10 + 0.02 * position,
                "covariance_00": 0.02,
                "covariance_01": 0.002,
                "covariance_11": 0.018,
                "phase_velocity": 2.0 * np.pi / period_months,
                "acceleration": 0.0,
                "phase_duration_months": 3.0,
                "confidence": 0.85,
                "center_period": center_period,
                "state_model_version": "cycle-state-v1",
                "state_config_hash": HASH_A,
            }
        )
    return pd.DataFrame(rows, columns=CYCLE_STATE_COLUMNS)


def _cycle_forecast(*, draw_count: int = 16):
    registry = _registry()
    forecast_input = CycleForecastInput(
        as_of=AS_OF,
        cycle_specs=registry.cycles,
        indicator_specs=registry.indicators,
        states=_cycle_states(),
        leading_signals=pd.DataFrame(columns=LEADING_SIGNAL_COLUMNS),
        calibration_history=pd.DataFrame(columns=CALIBRATION_HISTORY_COLUMNS),
    )
    return forecast_cycle_phases(
        forecast_input,
        config=CycleForecastConfig(draw_count=draw_count, seed=13),
    )


def _forecast_date(origin: object, horizon: int) -> pd.Timestamp:
    return pd.Timestamp(origin).normalize() + pd.offsets.MonthEnd(horizon)


def _origin_state(origin_number: int, channel_number: int) -> float:
    return float(
        0.25 * np.sin(0.27 * origin_number + 0.11 * channel_number)
        + 0.03 * channel_number
    )


def _cycle_value(
    origin_number: int,
    horizon: int,
    cycle_number: int,
) -> tuple[float, float]:
    angle = 0.19 * (origin_number + horizon) + 0.23 * cycle_number
    return float(np.sin(angle)), float(0.19 * np.cos(angle))


def _channel_forecast(*, draw_count: int = 16) -> ChannelForecastResult:
    registry = _registry()
    origins = pd.date_range("2020-01-31", periods=30, freq="ME")
    channel_rows = []
    cycle_rows = []
    for origin_number, origin in enumerate(origins):
        for horizon in range(1, 13):
            target_date = _forecast_date(origin, horizon)
            target_visible_date = target_date + pd.Timedelta(days=5)
            revision_window_end = target_date + pd.Timedelta(days=20)
            for channel_number, channel in enumerate(registry.channels):
                origin_state = _origin_state(origin_number, channel_number)
                cycle_level, cycle_slope = _cycle_value(origin_number, horizon, 3)
                target_state = float(
                    0.35 * origin_state
                    + 0.95 * cycle_level
                    - 0.35 * cycle_slope
                    + 0.02 * channel_number
                    + 0.005 * np.sin(origin_number + channel_number)
                )
                channel_rows.append(
                    {
                        "forecast_origin": origin,
                        "origin_state_date": origin,
                        "origin_visible_date": origin,
                        "target_date": target_date,
                        "target_visible_date": target_visible_date,
                        "target_revision_window_end": revision_window_end,
                        "channel_id": channel.channel_id,
                        "horizon_months": horizon,
                        "origin_state": origin_state,
                        "origin_innovation": origin_state
                        - _origin_state(max(origin_number - 1, 0), channel_number),
                        "origin_uncertainty": 0.10,
                        "origin_status": "available",
                        "origin_status_reason": None,
                        "target_state": target_state,
                        "target_innovation": target_state - origin_state,
                        "target_uncertainty": 0.08,
                        "target_status": "available",
                        "target_status_reason": None,
                        "data_vintage": min(revision_window_end, pd.Timestamp(AS_OF)),
                    }
                )
            for cycle_number, cycle in enumerate(registry.cycles, start=1):
                if horizon > max(cycle.horizons):
                    continue
                level, slope = _cycle_value(origin_number, horizon, cycle_number)
                for draw_id, shift in enumerate((-0.01, 0.0, 0.01)):
                    cycle_rows.append(
                        {
                            "forecast_origin": origin,
                            "date": target_date,
                            "visible_date": origin,
                            "generated_date": origin,
                            "cycle_id": cycle.cycle_id,
                            "draw_id": draw_id,
                            "horizon_months": horizon,
                            "level": level + shift,
                            "slope": slope + shift / 5.0,
                            "predictor_kind": "forecast",
                            "forecast_model_version": "cycle-archive-v1",
                            "forecast_config_hash": HASH_B,
                            "registry_hash": HASH_C,
                            "data_vintage": origin,
                        }
                    )
    current_rows = []
    for channel_number, channel in enumerate(registry.channels):
        state = _origin_state(len(origins), channel_number)
        current_rows.append(
            {
                "as_of": AS_OF,
                "state_date": AS_OF,
                "visible_date": AS_OF,
                "revision_window_end": AS_OF,
                "channel_id": channel.channel_id,
                "state": state,
                "innovation": state - _origin_state(len(origins) - 1, channel_number),
                "uncertainty": 0.12,
                "status": "available",
                "status_reason": None,
                "data_vintage": AS_OF,
            }
        )
    forecast_input = ChannelForecastInput(
        as_of=AS_OF,
        channel_specs=registry.channels,
        cycle_forecast=_cycle_forecast(draw_count=draw_count),
        channel_history=pd.DataFrame(channel_rows, columns=CHANNEL_HISTORY_COLUMNS),
        cycle_predictor_archive=pd.DataFrame(
            cycle_rows,
            columns=CYCLE_PREDICTOR_ARCHIVE_COLUMNS,
        ),
        exogenous_forecast_archive=pd.DataFrame(
            columns=EXOGENOUS_FORECAST_ARCHIVE_COLUMNS
        ),
        current_channel_states=pd.DataFrame(
            current_rows,
            columns=CURRENT_CHANNEL_STATE_COLUMNS,
        ),
        current_exogenous_paths=pd.DataFrame(columns=CURRENT_EXOGENOUS_PATH_COLUMNS),
        exogenous_feature_ids=(),
    )
    return forecast_transmission_channels(
        forecast_input,
        config=ChannelForecastConfig(
            horizons=tuple(range(1, 13)),
            alpha_grid=(0.1,),
            min_training_count=6,
            alpha_validation_window=3,
            embargo_days=0,
            covariance_min_samples=3,
            covariance_shrinkage=0.2,
            seed=31,
        ),
    )


def _stage2_asset_rows(
    *,
    asset_id: str,
    posterior_date: pd.Timestamp,
    labels: list[tuple[str, str, float, float]],
    status: str = "estimated",
    effective_training_count: float = 36.0,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    usable = status in {"estimated", "parent_informed", "parent_only"}
    predicted = (
        float(sum(mean * value for _, _, mean, value in labels))
        if usable
        else float("nan")
    )
    residual = 0.0005 if usable else float("nan")
    common = {
        "training_start": pd.Timestamp("2020-01-31"),
        "training_end": posterior_date - pd.offsets.MonthEnd(1),
        "training_count": 42,
        "effective_training_count": effective_training_count,
        "parent_node_id": f"industry_{asset_id}",
        "own_weight": 0.8,
        "parent_weight": 0.2,
        "confidence": 0.9,
        "proxy_discount": 1.0,
        "condition_number": 12.0,
        "status": status,
        "window": "expanding",
        "rolling_window": None,
        "forgetting_factor": 1.0,
        "estimation_method": "hierarchical_tvp_ridge",
    }
    component_rows = []
    for component_type, component_id, mean, value in labels:
        component_rows.append(
            {
                "date": posterior_date,
                "asset_id": asset_id,
                "component_type": component_type,
                "component_id": component_id,
                "component_value": value if usable else np.nan,
                "coefficient_mean": mean if usable else np.nan,
                "contribution": mean * value if usable else np.nan,
                "observed_return": predicted + residual if usable else np.nan,
                "predicted_return": predicted,
                "asset_residual": residual,
                "parent_coefficient_mean": np.nan,
                **common,
            }
        )
    component_rows.append(
        {
            "date": posterior_date,
            "asset_id": asset_id,
            "component_type": "residual",
            "component_id": "asset_residual",
            "component_value": residual,
            "coefficient_mean": 1.0 if usable else np.nan,
            "contribution": residual,
            "observed_return": predicted + residual if usable else np.nan,
            "predicted_return": predicted,
            "asset_residual": residual,
            "parent_coefficient_mean": np.nan,
            **common,
        }
    )
    posterior_rows = []
    for component_type, component_id, mean, _ in labels:
        posterior_rows.append(
            {
                "date": posterior_date,
                "node_level": "asset",
                "node_id": asset_id,
                "parent_node_id": f"industry_{asset_id}",
                "component_type": component_type,
                "component_id": component_id,
                "coefficient_mean": mean if usable else np.nan,
                "parent_coefficient_mean": np.nan,
                "prior_precision": 1.0,
                "own_weight": 0.8,
                "parent_weight": 0.2,
                "confidence": 0.9,
                "proxy_discount": 1.0,
                "training_start": pd.Timestamp("2020-01-31"),
                "training_end": posterior_date - pd.offsets.MonthEnd(1),
                "training_count": 42,
                "effective_training_count": effective_training_count,
                "condition_number": 12.0,
                "status": status,
                "window": "expanding",
                "rolling_window": None,
                "forgetting_factor": 1.0,
                "estimation_method": "hierarchical_tvp_ridge",
            }
        )
    covariance_rows = []
    for row_position, (type_i, id_i, _, _) in enumerate(labels):
        for column_position, (type_j, id_j, _, _) in enumerate(labels):
            covariance_rows.append(
                {
                    "date": posterior_date,
                    "node_level": "asset",
                    "node_id": asset_id,
                    "parent_node_id": f"industry_{asset_id}",
                    "component_i_type": type_i,
                    "component_i_id": id_i,
                    "component_j_type": type_j,
                    "component_j_id": id_j,
                    "coefficient_covariance": (
                        0.0004 if usable and row_position == column_position else 0.0
                    )
                    if usable
                    else np.nan,
                    "training_start": pd.Timestamp("2020-01-31"),
                    "training_end": posterior_date - pd.offsets.MonthEnd(1),
                    "training_count": 42,
                    "effective_training_count": effective_training_count,
                    "prior_precision": 1.0,
                    "own_weight": 0.8,
                    "parent_weight": 0.2,
                    "confidence": 0.9,
                    "proxy_discount": 1.0,
                    "condition_number": 12.0,
                    "status": status,
                    "window": "expanding",
                    "rolling_window": None,
                    "forgetting_factor": 1.0,
                    "estimation_method": "hierarchical_tvp_ridge",
                }
            )
    return component_rows, posterior_rows, covariance_rows


def _stage2(
    *,
    include_low_support: bool = False,
    include_history: bool = True,
) -> ChannelToAssetResult:
    alpha_latest = [
        ("intercept", "intercept", 0.001, 1.0),
        ("benchmark", "benchmark_return", 0.20, 0.002),
        ("channel", "growth_demand", 0.65, 0.10),
        ("channel", "inflation_prices", -0.35, -0.04),
        ("control", "valuation_z", -0.12, -0.30),
        ("control", "positioning_score", 0.06, 0.40),
        ("control", "liquidity_control", 0.08, 0.20),
        ("interaction", "growth_x_valuation", 0.03, -0.03),
        ("event", "event_shock", 0.04, 0.10),
    ]
    safe_labels = [
        ("intercept", "intercept", 0.0005, 1.0),
        ("benchmark", "benchmark_return", 0.10, 0.001),
        ("channel", "fx_external_demand", -0.25, 0.05),
    ]
    component_rows: list[dict[str, object]] = []
    posterior_rows: list[dict[str, object]] = []
    covariance_rows: list[dict[str, object]] = []
    specifications = [
        (ASSET_ALPHA, pd.Timestamp(AS_OF), alpha_latest, "estimated", 36.0),
        (ASSET_SAFE, pd.Timestamp(AS_OF), safe_labels, "estimated", 34.0),
    ]
    if include_history:
        alpha_prior = [
            (*label[:2], 0.05 if label[0] == "channel" else label[2], label[3])
            for label in alpha_latest
        ]
        specifications.insert(
            0,
            (
                ASSET_ALPHA,
                pd.Timestamp("2024-05-31"),
                alpha_prior,
                "estimated",
                35.0,
            ),
        )
    if include_low_support:
        specifications.append(
            (
                "asset_low_support",
                pd.Timestamp(AS_OF),
                [
                    ("intercept", "intercept", 0.0, 1.0),
                    ("channel", "growth_demand", 0.0, 0.0),
                ],
                "insufficient_history",
                4.0,
            )
        )
    for asset_id, posterior_date, labels, status, effective_count in specifications:
        components, posteriors, covariance = _stage2_asset_rows(
            asset_id=asset_id,
            posterior_date=posterior_date,
            labels=labels,
            status=status,
            effective_training_count=effective_count,
        )
        component_rows.extend(components)
        posterior_rows.extend(posteriors)
        covariance_rows.extend(covariance)
    return ChannelToAssetResult(
        components=pd.DataFrame(
            component_rows,
            columns=CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
        ),
        posteriors=pd.DataFrame(
            posterior_rows,
            columns=CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
        ),
        covariance=pd.DataFrame(
            covariance_rows,
            columns=CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
        ),
    )


def _feature_rows(
    *,
    assets: tuple[str, ...],
    component_ids: tuple[str, ...],
    draw_count: int,
    value_column: str,
    unit: str,
) -> list[dict[str, object]]:
    rows = []
    for asset_id in assets:
        for component_position, component_id in enumerate(component_ids):
            for draw_id in range(draw_count):
                for month_number, forecast_date in enumerate(FORECAST_DATES, start=1):
                    rows.append(
                        {
                            "forecast_origin": AS_OF,
                            "date": forecast_date,
                            "visible_date": AS_OF,
                            "generated_date": AS_OF,
                            "data_vintage": AS_OF,
                            "asset_id": asset_id,
                            "component_id": component_id,
                            "draw_id": draw_id,
                            value_column: 0.01
                            * (component_position + 1)
                            * (1.0 + month_number / 20.0)
                            + 0.0001 * draw_id,
                            "unit": unit,
                            "path_kind": "forecast",
                            "model_version": f"{value_column}-v1",
                        }
                    )
    return rows


def _forecast_frames(draw_count: int) -> dict[str, pd.DataFrame]:
    valuation = pd.DataFrame(
        _feature_rows(
            assets=(ASSET_ALPHA,),
            component_ids=("valuation_z",),
            draw_count=draw_count,
            value_column="valuation_value",
            unit="z_score",
        ),
        columns=VALUATION_FORECAST_INPUT_COLUMNS,
    )
    positioning = pd.DataFrame(
        _feature_rows(
            assets=(ASSET_ALPHA,),
            component_ids=("positioning_score",),
            draw_count=draw_count,
            value_column="positioning_value",
            unit="score",
        ),
        columns=POSITIONING_FORECAST_INPUT_COLUMNS,
    )
    controls = pd.DataFrame(
        _feature_rows(
            assets=(ASSET_ALPHA,),
            component_ids=("liquidity_control",),
            draw_count=draw_count,
            value_column="control_value",
            unit="score",
        ),
        columns=CONTROL_FORECAST_INPUT_COLUMNS,
    )
    interactions = pd.DataFrame(
        _feature_rows(
            assets=(ASSET_ALPHA,),
            component_ids=("growth_x_valuation",),
            draw_count=draw_count,
            value_column="interaction_value",
            unit="interaction_score",
        ),
        columns=INTERACTION_FORECAST_INPUT_COLUMNS,
    )
    events = pd.DataFrame(
        _feature_rows(
            assets=(ASSET_ALPHA,),
            component_ids=("event_shock",),
            draw_count=draw_count,
            value_column="event_value",
            unit="scenario_score",
        ),
        columns=EVENT_FORECAST_INPUT_COLUMNS,
    )
    benchmark_rows = []
    residual_rows = []
    for asset_position, asset_id in enumerate((ASSET_ALPHA, ASSET_SAFE), start=1):
        for draw_id in range(draw_count):
            for month_number, forecast_date in enumerate(FORECAST_DATES, start=1):
                provenance = {
                    "forecast_origin": AS_OF,
                    "date": forecast_date,
                    "visible_date": AS_OF,
                    "generated_date": AS_OF,
                    "data_vintage": AS_OF,
                    "asset_id": asset_id,
                    "draw_id": draw_id,
                    "unit": "decimal_return",
                    "path_kind": "forecast",
                }
                benchmark_rows.append(
                    {
                        **provenance,
                        "benchmark_return": 0.001 * asset_position
                        + 0.0001 * month_number
                        + 0.00001 * draw_id,
                        "model_version": "benchmark-v1",
                    }
                )
                residual_rows.append(
                    {
                        **provenance,
                        "residual_return": 0.0002
                        * ((draw_id + month_number + asset_position) % 5 - 2),
                        "model_version": "residual-v1",
                    }
                )
    return {
        "valuation_forecasts": valuation,
        "positioning_forecasts": positioning,
        "control_forecasts": controls,
        "interaction_forecasts": interactions,
        "event_forecasts": events,
        "benchmark_forecasts": pd.DataFrame(
            benchmark_rows,
            columns=BENCHMARK_FORECAST_INPUT_COLUMNS,
        ),
        "residual_forecasts": pd.DataFrame(
            residual_rows,
            columns=RESIDUAL_FORECAST_INPUT_COLUMNS,
        ),
    }


@pytest.fixture(scope="module")
def channel_forecast() -> ChannelForecastResult:
    return _channel_forecast()


@pytest.fixture(scope="module")
def scenario_catalog() -> ScenarioCatalog:
    return load_scenario_catalog(
        PROJECT_ROOT / "config" / "seven_cycle" / "scenarios.yaml"
    )


def _asset_input(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
    *,
    scenario_id: str = "baseline",
    stage2: ChannelToAssetResult | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
    view_mode: str = "forecast",
) -> AssetForecastInput:
    normalized_frames = frames or _forecast_frames(
        channel_forecast.forecast_input.cycle_forecast.config.draw_count
    )
    return AssetForecastInput(
        as_of=AS_OF,
        view_mode=view_mode,
        scenario_catalog=scenario_catalog,
        scenario_id=scenario_id,
        channel_forecast=channel_forecast,
        stage2=stage2 or _stage2(),
        **normalized_frames,
    )


def _estimate(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
    *,
    scenario_id: str = "baseline",
    stage2: ChannelToAssetResult | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
    config: AssetForecastConfig | None = None,
) -> AssetForecastResult:
    return forecast_asset_distributions(
        _asset_input(
            channel_forecast,
            scenario_catalog,
            scenario_id=scenario_id,
            stage2=stage2,
            frames=frames,
        ),
        config=config or AssetForecastConfig(seed=1729, min_effective_samples=12),
    )


def test_scenario_yaml_defines_all_six_explicit_versioned_contracts(
    scenario_catalog: ScenarioCatalog,
) -> None:
    assert tuple(scenario_catalog.scenario_ids) == (
        "baseline",
        "easing",
        "tightening",
        "growth",
        "inflation",
        "geopolitical_supply",
    )
    raw = yaml.safe_load(
        (PROJECT_ROOT / "config" / "seven_cycle" / "scenarios.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert raw["catalog_version"]
    for scenario in raw["scenarios"]:
        assert scenario["version"]
        for shock in scenario["shocks"]:
            assert shock["channel_id"]
            assert shock.get("effective_date") or shock.get("effective_date_rule")
            assert shock.get("duration_months") or shock.get("end_date")
            assert isinstance(shock["value"], (int, float))
            assert shock["unit"] == "channel_innovation"
            assert shock["direction"] in {"increase", "decrease", "flat"}
            assert shock["path"] in {"step", "linear", "pulse"}
            assert shock["version"]


def test_runtime_catalog_requires_exact_standard_scenarios(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    scenarios = scenario_catalog.scenarios
    malformed = [
        ScenarioCatalog(
            catalog_version="missing-v1",
            scenarios=scenarios[:-1],
        ),
        ScenarioCatalog(
            catalog_version="extra-v1",
            scenarios=(
                *scenarios,
                ScenarioDefinition(
                    scenario_id="extra",
                    name="Extra",
                    version="extra-v1",
                    shocks=(),
                ),
            ),
        ),
        ScenarioCatalog(
            catalog_version="reordered-v1",
            scenarios=(scenarios[1], scenarios[0], *scenarios[2:]),
        ),
    ]
    duplicate = ScenarioCatalog(
        catalog_version="duplicate-v1",
        scenarios=scenarios,
    )
    object.__setattr__(
        duplicate,
        "scenarios",
        (*scenarios[:-1], scenarios[0]),
    )
    malformed.append(duplicate)

    for catalog in malformed:
        with pytest.raises(
            ValueError,
            match="scenario_catalog|standard|baseline|exact",
        ):
            _asset_input(channel_forecast, catalog)

    assert scenario_catalog.scenario_ids == STANDARD_SCENARIO_IDS


def test_baseline_retains_zero_shocks_and_monthly_conservation(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    result = _estimate(channel_forecast, scenario_catalog)

    assert tuple(result.channel_paths.columns) == SCENARIO_CHANNEL_PATH_COLUMNS
    assert tuple(result.components.columns) == ASSET_FORECAST_COMPONENT_COLUMNS
    assert tuple(result.monthly_draws.columns) == ASSET_FORECAST_MONTHLY_COLUMNS
    assert tuple(result.draws.columns) == ASSET_FORECAST_DRAW_COLUMNS
    assert tuple(result.summary.columns) == ASSET_FORECAST_SUMMARY_COLUMNS
    assert result.channel_paths["scenario_shock"].eq(0.0).all()
    assert result.channel_paths["baseline_channel_state"].equals(
        result.channel_paths["adjusted_channel_state"]
    )
    assert result.channel_paths["baseline_channel_innovation"].equals(
        result.channel_paths["adjusted_channel_innovation"]
    )
    assert result.components["scenario_contribution"].eq(0.0).all()
    assert result.components["cycle_contribution"].eq(0.0).all()
    channel_components = result.components.loc[
        result.components["component_type"].eq("channel")
    ]
    channel_audit = channel_components.merge(
        result.channel_paths,
        left_on=["component_id", "draw_id", "month_number"],
        right_on=["channel_id", "draw_id", "month_number"],
        validate="many_to_one",
    )
    assert np.allclose(
        channel_audit["baseline_predictor_value"],
        channel_audit["baseline_channel_innovation"],
    )
    assert np.allclose(
        channel_audit["baseline_contribution"],
        channel_audit["coefficient_draw"]
        * channel_audit["baseline_channel_innovation"],
    )
    decomposition = [
        "intercept_contribution",
        "benchmark_contribution",
        "channel_contribution",
        "valuation_contribution",
        "positioning_contribution",
        "control_contribution",
        "interaction_contribution",
        "event_contribution",
        "scenario_contribution",
        "residual_contribution",
    ]
    assert np.allclose(
        result.monthly_draws[decomposition].sum(axis=1),
        result.monthly_draws["asset_monthly_return"],
        atol=1e-12,
        rtol=1e-12,
    )


def test_single_channel_scenario_changes_only_target_surface_and_is_not_double_counted(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    baseline = _estimate(channel_forecast, scenario_catalog)
    growth = _estimate(channel_forecast, scenario_catalog, scenario_id="growth")
    merged = baseline.channel_paths.merge(
        growth.channel_paths,
        on=["channel_id", "draw_id", "month_number", "date", "forecast_origin"],
        suffixes=("_baseline", "_growth"),
    )
    unaffected = ~(
        merged["channel_id"].eq("growth_demand")
        & merged["scenario_shock_growth"].ne(0.0)
    )
    assert merged.loc[unaffected, "baseline_channel_state_baseline"].equals(
        merged.loc[unaffected, "adjusted_channel_state_growth"]
    )
    targeted = merged["scenario_shock_growth"].ne(0.0)
    assert targeted.any()
    assert np.allclose(
        merged.loc[targeted, "adjusted_channel_state_growth"],
        merged.loc[targeted, "baseline_channel_state_growth"]
        + merged.loc[targeted, "scenario_shock_growth"],
    )
    assert np.allclose(
        merged.loc[targeted, "adjusted_channel_innovation_growth"],
        merged.loc[targeted, "baseline_channel_innovation_growth"]
        + merged.loc[targeted, "scenario_shock_growth"],
    )
    assert np.allclose(
        merged.loc[targeted, "adjusted_channel_state_growth"],
        merged.loc[targeted, "origin_channel_state_growth"]
        + merged.loc[targeted, "adjusted_channel_innovation_growth"],
    )
    assert set(merged.loc[targeted, "shock_unit_growth"]) == {"channel_innovation"}
    channel_components = growth.components.loc[
        growth.components["component_type"].eq("channel")
    ]
    assert np.allclose(
        channel_components["contribution"],
        channel_components["baseline_contribution"]
        + channel_components["scenario_contribution"],
    )
    assert channel_components["cycle_contribution"].eq(0.0).all()
    growth_rows = channel_components["component_id"].eq("growth_demand")
    assert channel_components.loc[growth_rows, "scenario_contribution"].ne(0.0).any()
    assert channel_components.loc[~growth_rows, "scenario_contribution"].eq(0.0).all()
    assert np.allclose(
        channel_components["scenario_contribution"],
        channel_components["coefficient_draw"]
        * channel_components["scenario_predictor_value"],
    )


def test_actual_forecast_mixing_and_future_pit_inputs_are_rejected(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    with pytest.raises(ValueError, match="view_mode.*forecast|actual"):
        _asset_input(
            channel_forecast,
            scenario_catalog,
            view_mode="actual",
        )

    mixed = _forecast_frames(16)
    mixed["valuation_forecasts"].loc[0, "path_kind"] = "actual"
    with pytest.raises(ValueError, match="actual|path_kind|forecast"):
        _asset_input(channel_forecast, scenario_catalog, frames=mixed)

    future_visible = _forecast_frames(16)
    future_visible["event_forecasts"].loc[0, "visible_date"] = FORECAST_DATES[0]
    with pytest.raises(ValueError, match="visible_date|as_of|future"):
        _asset_input(channel_forecast, scenario_catalog, frames=future_visible)

    future_vintage = _forecast_frames(16)
    future_vintage["benchmark_forecasts"].loc[0, "data_vintage"] = FORECAST_DATES[0]
    with pytest.raises(ValueError, match="data_vintage|as_of|future"):
        _asset_input(channel_forecast, scenario_catalog, frames=future_vintage)


def test_future_stage2_posterior_and_forged_governed_results_are_rejected(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    future_stage2 = _stage2(include_history=False)
    for field in ("components", "posteriors", "covariance"):
        frame = getattr(future_stage2, field)
        frame["date"] = pd.Timestamp("2024-07-31")
        frame["training_end"] = pd.Timestamp("2024-06-30")
        object.__setattr__(future_stage2, field, frame)
    with pytest.raises(ValueError, match="posterior|future|as_of"):
        _asset_input(channel_forecast, scenario_catalog, stage2=future_stage2)

    original_draws = channel_forecast.draws
    forged_draws = original_draws.copy(deep=True)
    forged_draws.loc[0, "forecast_state"] += 1.0
    object.__setattr__(channel_forecast, "draws", forged_draws)
    try:
        with pytest.raises(
            ValueError,
            match="channel|retained|deterministic|inconsistent",
        ):
            _asset_input(channel_forecast, scenario_catalog)
    finally:
        object.__setattr__(channel_forecast, "draws", original_draws)


def test_latest_dynamic_stage2_exposure_is_used_and_sampled_once_per_draw(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    constant_frames = _forecast_frames(16)
    for name, value_column in (
        ("valuation_forecasts", "valuation_value"),
        ("positioning_forecasts", "positioning_value"),
        ("control_forecasts", "control_value"),
        ("interaction_forecasts", "interaction_value"),
        ("event_forecasts", "event_value"),
        ("benchmark_forecasts", "benchmark_return"),
        ("residual_forecasts", "residual_return"),
    ):
        constant_frames[name][value_column] = 0.0
    result = _estimate(
        channel_forecast,
        scenario_catalog,
        frames=constant_frames,
        config=AssetForecastConfig(seed=7, min_effective_samples=12),
    )
    alpha_channels = result.components.loc[
        result.components["asset_id"].eq(ASSET_ALPHA)
        & result.components["component_type"].eq("channel")
    ]
    assert set(
        zip(
            alpha_channels["component_id"],
            alpha_channels["coefficient_mean"],
            strict=True,
        )
    ) == {("growth_demand", 0.65), ("inflation_prices", -0.35)}
    assert set(alpha_channels["stage2_posterior_date"]) == {AS_OF}
    assert (
        alpha_channels.groupby(["draw_id", "component_id"])["coefficient_draw"]
        .nunique()
        .eq(1)
        .all()
    )
    coefficient_matrix = alpha_channels.pivot_table(
        index="draw_id",
        columns="component_id",
        values="coefficient_draw",
        aggfunc="first",
    )
    assert set(coefficient_matrix) == {"growth_demand", "inflation_prices"}
    assert (
        coefficient_matrix["growth_demand"]
        .ne(coefficient_matrix["inflation_prices"])
        .all()
    )


def test_joint_draw_ids_and_shared_prefix_horizons_are_preserved(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    result = _estimate(channel_forecast, scenario_catalog)
    expected_draw_ids = set(range(16))
    for asset_id in (ASSET_ALPHA, ASSET_SAFE):
        assert (
            set(
                result.monthly_draws.loc[
                    result.monthly_draws["asset_id"].eq(asset_id), "draw_id"
                ]
            )
            == expected_draw_ids
        )
    first = result.monthly_draws.loc[
        result.monthly_draws["asset_id"].eq(ASSET_ALPHA)
        & result.monthly_draws["draw_id"].eq(0)
    ].sort_values("month_number")
    horizons = result.draws.loc[
        result.draws["asset_id"].eq(ASSET_ALPHA) & result.draws["draw_id"].eq(0)
    ].set_index("horizon_months")
    for horizon in (3, 6, 12):
        prefix = first.iloc[:horizon]
        absolute = float(np.expm1(np.log1p(prefix["asset_monthly_return"]).sum()))
        benchmark = float(np.expm1(np.log1p(prefix["benchmark_monthly_return"]).sum()))
        excess = (1.0 + absolute) / (1.0 + benchmark) - 1.0
        assert horizons.loc[horizon, "absolute_return"] == pytest.approx(absolute)
        assert horizons.loc[horizon, "benchmark_return"] == pytest.approx(benchmark)
        assert horizons.loc[horizon, "excess_return"] == pytest.approx(excess)
        assert horizons.loc[horizon, "absolute_max_drawdown"] == pytest.approx(
            compute_max_drawdown(prefix["asset_monthly_return"].to_numpy())
        )


def test_summary_intervals_and_risk_metrics_recompute_from_horizon_draws(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    result = _estimate(channel_forecast, scenario_catalog)
    row = result.summary.loc[
        result.summary["asset_id"].eq(ASSET_ALPHA)
        & result.summary["horizon_months"].eq(12)
        & result.summary["return_basis"].eq("absolute")
    ].iloc[0]
    draws = result.draws.loc[
        result.draws["asset_id"].eq(ASSET_ALPHA) & result.draws["horizon_months"].eq(12)
    ]
    returns = draws["absolute_return"].to_numpy()
    drawdowns = draws["absolute_max_drawdown"].to_numpy()
    q10, q25, q50, q75, q90 = np.quantile(
        returns,
        [0.10, 0.25, 0.50, 0.75, 0.90],
    )
    risk = summarize_risk(returns, drawdowns)
    assert row["q10"] == pytest.approx(q10)
    assert row["q25"] == pytest.approx(q25)
    assert row["q50"] == pytest.approx(q50)
    assert row["median"] == pytest.approx(q50)
    assert row["q75"] == pytest.approx(q75)
    assert row["q90"] == pytest.approx(q90)
    assert row["interval50_lower"] == pytest.approx(q25)
    assert row["interval50_upper"] == pytest.approx(q75)
    assert row["interval80_lower"] == pytest.approx(q10)
    assert row["interval80_upper"] == pytest.approx(q90)
    assert row["expected_return"] == pytest.approx(np.mean(returns))
    assert row["volatility"] == pytest.approx(risk.volatility)
    assert row["var95"] == pytest.approx(risk.var95)
    assert row["cvar95"] == pytest.approx(risk.cvar95)
    assert row["drawdown_q95"] == pytest.approx(risk.drawdown_q95)


def test_horizon_draw_provenance_aligns_with_summary_and_rejects_tampering(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    result = _estimate(channel_forecast, scenario_catalog)
    provenance_columns = (
        "scenario_id",
        "scenario_version",
        "catalog_version",
        "scenario_config_hash",
        "asset_forecast_model_version",
        "asset_forecast_config_hash",
        "channel_forecast_model_version",
        "channel_forecast_config_hash",
        "channel_registry_hash",
        "cycle_forecast_model_version",
        "cycle_forecast_config_hash",
        "cycle_registry_hash",
        "stage2_posterior_date",
        "stage2_estimation_method",
        "forecast_origin",
        "data_vintage",
        "feature_visible_date",
        "feature_generated_date",
        "feature_vintage_date",
        "model_provenance",
        "data_provenance",
    )
    assert set(provenance_columns).issubset(ASSET_FORECAST_DRAW_COLUMNS)
    summary = result.summary.loc[
        result.summary["return_basis"].eq("absolute")
    ].set_index(["asset_id", "horizon_months"])
    for row in result.draws.itertuples(index=False):
        summary_row = summary.loc[(row.asset_id, row.horizon_months)]
        for column in provenance_columns:
            assert getattr(row, column) == summary_row[column]

    tampered_draws = result.draws
    tampered_draws.loc[0, "channel_registry_hash"] = "f" * 64
    with pytest.raises(ValueError, match="draws|retained|replay|inconsistent"):
        AssetForecastResult(
            summary=result.summary,
            monthly_draws=result.monthly_draws,
            draws=tampered_draws,
            components=result.components,
            channel_paths=result.channel_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )


def test_unavailable_and_partial_assets_keep_audit_rows_without_numeric_pollution(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    result = _estimate(
        channel_forecast,
        scenario_catalog,
        stage2=_stage2(include_low_support=True),
    )
    low = result.summary.loc[result.summary["asset_id"].eq("asset_low_support")]
    assert len(low) == 6
    assert set(low["status"]) == {"unavailable"}
    assert (
        low[
            [
                "q10",
                "q25",
                "q50",
                "q75",
                "q90",
                "expected_return",
                "volatility",
                "var95",
                "cvar95",
            ]
        ]
        .isna()
        .all()
        .all()
    )
    assert result.monthly_draws["asset_id"].isin({ASSET_ALPHA, ASSET_SAFE}).all()
    assert set(
        result.summary.loc[
            result.summary["asset_id"].isin({ASSET_ALPHA, ASSET_SAFE}), "status"
        ]
    ) == {"available"}

    missing_safe = _forecast_frames(16)
    for frame_name in ("benchmark_forecasts", "residual_forecasts"):
        missing_safe[frame_name] = missing_safe[frame_name].loc[
            ~missing_safe[frame_name]["asset_id"].eq(ASSET_SAFE)
        ]
    partial = _estimate(channel_forecast, scenario_catalog, frames=missing_safe)
    safe_summary = partial.summary.loc[partial.summary["asset_id"].eq(ASSET_SAFE)]
    assert set(safe_summary["status"]) == {"unavailable"}
    assert safe_summary["feature_visible_date"].isna().all()
    assert safe_summary["feature_generated_date"].isna().all()
    assert safe_summary["feature_vintage_date"].isna().all()
    assert safe_summary["data_vintage"].notna().all()
    assert set(
        partial.summary.loc[partial.summary["asset_id"].eq(ASSET_ALPHA), "status"]
    ) == {"available"}


def test_empty_explicit_surfaces_degrade_to_unavailable_without_fabricated_draws(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    empty_frames = {
        name: frame.iloc[0:0].copy(deep=True)
        for name, frame in _forecast_frames(16).items()
    }
    result = _estimate(
        channel_forecast,
        scenario_catalog,
        frames=empty_frames,
    )

    assert result.components.empty
    assert result.monthly_draws.empty
    assert result.draws.empty
    assert len(result.summary) == 12
    assert set(result.summary["status"]) == {"unavailable"}
    assert result.summary["unavailable_reason"].str.contains("missing_").all()
    metric_columns = (
        "q10",
        "q25",
        "q50",
        "q75",
        "q90",
        "expected_return",
        "volatility",
        "var95",
        "cvar95",
        "drawdown_q50",
        "drawdown_q80",
        "drawdown_q95",
    )
    assert result.summary.loc[:, metric_columns].isna().all().all()
    for column in (
        "feature_visible_date",
        "feature_generated_date",
        "feature_vintage_date",
    ):
        assert result.summary[column].isna().all()
    assert result.summary["data_vintage"].notna().all()


def test_asset_level_provenance_uses_only_surfaces_consumed_by_that_asset(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    frames = _forecast_frames(16)
    safe_visible = pd.Timestamp("2024-05-10")
    safe_generated = pd.Timestamp("2024-05-20")
    safe_vintage = pd.Timestamp("2024-05-15")
    for frame_name, version in (
        ("benchmark_forecasts", "safe-benchmark-v2"),
        ("residual_forecasts", "safe-residual-v2"),
    ):
        safe_rows = frames[frame_name]["asset_id"].eq(ASSET_SAFE)
        frames[frame_name].loc[safe_rows, "visible_date"] = safe_visible
        frames[frame_name].loc[safe_rows, "generated_date"] = safe_generated
        frames[frame_name].loc[safe_rows, "data_vintage"] = safe_vintage
        frames[frame_name].loc[safe_rows, "model_version"] = version
    result = _estimate(channel_forecast, scenario_catalog, frames=frames)

    safe_summary = result.summary.loc[result.summary["asset_id"].eq(ASSET_SAFE)]
    alpha_summary = result.summary.loc[result.summary["asset_id"].eq(ASSET_ALPHA)]
    assert set(safe_summary["feature_visible_date"]) == {safe_visible.date()}
    assert set(safe_summary["feature_generated_date"]) == {safe_generated.date()}
    assert set(safe_summary["feature_vintage_date"]) == {safe_vintage.date()}
    assert set(alpha_summary["feature_visible_date"]) == {AS_OF}
    safe_model = json.loads(safe_summary["model_provenance"].iloc[0])
    assert safe_model["feature_model_versions"] == [
        "safe-benchmark-v2",
        "safe-residual-v2",
    ]
    assert "valuation_value-v1" not in safe_summary["model_provenance"].iloc[0]
    assert safe_summary["data_provenance"].nunique() == 1
    assert alpha_summary["data_provenance"].nunique() == 1
    assert (
        safe_summary["data_provenance"].iloc[0]
        != alpha_summary["data_provenance"].iloc[0]
    )

    shared_columns = (
        "model_provenance",
        "data_provenance",
        "data_vintage",
        "feature_visible_date",
        "feature_generated_date",
        "feature_vintage_date",
    )
    safe_reference = safe_summary.iloc[0]
    for frame in (result.draws, result.monthly_draws):
        safe_frame = frame.loc[frame["asset_id"].eq(ASSET_SAFE)]
        for column in shared_columns:
            assert set(safe_frame[column]) == {safe_reference[column]}


def test_seed_shuffle_and_cross_scenario_replay_are_deterministic(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    config = AssetForecastConfig(seed=91, min_effective_samples=12)
    frames = _forecast_frames(16)
    baseline = _estimate(
        channel_forecast,
        scenario_catalog,
        frames=frames,
        config=config,
    )
    shuffled = {
        name: frame.sample(frac=1.0, random_state=position).reset_index(drop=True)
        for position, (name, frame) in enumerate(frames.items(), start=1)
    }
    replay = _estimate(
        channel_forecast,
        scenario_catalog,
        frames=shuffled,
        config=config,
    )
    pd.testing.assert_frame_equal(baseline.channel_paths, replay.channel_paths)
    pd.testing.assert_frame_equal(baseline.components, replay.components)
    pd.testing.assert_frame_equal(baseline.monthly_draws, replay.monthly_draws)
    pd.testing.assert_frame_equal(baseline.draws, replay.draws)
    pd.testing.assert_frame_equal(baseline.summary, replay.summary)

    growth = _estimate(
        channel_forecast,
        scenario_catalog,
        scenario_id="growth",
        frames=frames,
        config=config,
    )
    baseline_coefficients = baseline.components[
        ["asset_id", "draw_id", "component_type", "component_id", "coefficient_draw"]
    ]
    growth_coefficients = growth.components[
        ["asset_id", "draw_id", "component_type", "component_id", "coefficient_draw"]
    ]
    pd.testing.assert_frame_equal(baseline_coefficients, growth_coefficients)


def test_standard_nonbaseline_scenarios_require_a_nonzero_explicit_shock(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    empty_growth = ScenarioCatalog(
        catalog_version="empty-growth-v1",
        scenarios=tuple(
            replace(scenario, shocks=())
            if scenario.scenario_id == "growth"
            else scenario
            for scenario in scenario_catalog.scenarios
        ),
    )
    with pytest.raises(ValueError, match="growth|nonzero|non-baseline"):
        _asset_input(channel_forecast, empty_growth)

    zero_growth_shock = ScenarioShock(
        shock_id="zero-growth",
        channel_id="growth_demand",
        effective_date_rule="forecast_month:1",
        duration_months=1,
        value=0.0,
        unit="channel_innovation",
        direction="flat",
        path="step",
        version="zero-growth-v1",
    )
    zero_growth = ScenarioCatalog(
        catalog_version="zero-growth-v1",
        scenarios=tuple(
            replace(scenario, shocks=(zero_growth_shock,))
            if scenario.scenario_id == "growth"
            else scenario
            for scenario in scenario_catalog.scenarios
        ),
    )
    with pytest.raises(ValueError, match="growth|nonzero|non-baseline"):
        _asset_input(channel_forecast, zero_growth)

    forged_baseline = replace(scenario_catalog.get("baseline"))
    object.__setattr__(
        forged_baseline,
        "shocks",
        (replace(scenario_catalog.get("growth").shocks[0]),),
    )
    nonzero_baseline = ScenarioCatalog(
        catalog_version="nonzero-baseline-v1",
        scenarios=tuple(
            forged_baseline if scenario.scenario_id == "baseline" else scenario
            for scenario in scenario_catalog.scenarios
        ),
    )
    with pytest.raises(ValueError, match="baseline|zero"):
        _asset_input(channel_forecast, nonzero_baseline)


def test_scenario_duplicate_channel_unit_and_horizon_validation(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    duplicate_shocks = (
        ScenarioShock(
            shock_id="one",
            channel_id="growth_demand",
            effective_date_rule="forecast_month:1",
            duration_months=2,
            value=0.2,
            unit="channel_innovation",
            direction="increase",
            path="step",
            version="shock-v1",
        ),
        ScenarioShock(
            shock_id="two",
            channel_id="growth_demand",
            effective_date_rule="forecast_month:1",
            duration_months=2,
            value=0.1,
            unit="channel_innovation",
            direction="increase",
            path="step",
            version="shock-v2",
        ),
    )
    duplicate = ScenarioCatalog(
        catalog_version="test-v1",
        scenarios=tuple(
            replace(scenario, shocks=duplicate_shocks)
            if scenario.scenario_id == "growth"
            else scenario
            for scenario in scenario_catalog.scenarios
        ),
    )
    with pytest.raises(ValueError, match="duplicate|overlap"):
        _asset_input(channel_forecast, duplicate, scenario_id="growth")

    for update, pattern in (
        ({"channel_id": "unknown_channel"}, "channel"),
        ({"unit": "percentage_points"}, "unit"),
        ({"effective_date_rule": "forecast_month:13"}, "horizon|date|month"),
    ):
        shock = replace(scenario_catalog.get("growth").shocks[0], **update)
        scenarios = tuple(
            replace(scenario, shocks=(shock,))
            if scenario.scenario_id == "growth"
            else scenario
            for scenario in scenario_catalog.scenarios
        )
        invalid = ScenarioCatalog(
            catalog_version="invalid-v1",
            scenarios=scenarios,
        )
        with pytest.raises(ValueError, match=pattern):
            _asset_input(channel_forecast, invalid, scenario_id="growth")


def test_invalid_monthly_return_and_constructor_tampering_are_rejected(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    invalid = _forecast_frames(16)
    invalid["residual_forecasts"].loc[
        invalid["residual_forecasts"]["asset_id"].eq(ASSET_ALPHA),
        "residual_return",
    ] = -2.0
    with pytest.raises(ValueError, match="greater than -1|-100%"):
        _estimate(channel_forecast, scenario_catalog, frames=invalid)

    result = _estimate(channel_forecast, scenario_catalog)
    tampered_summary = result.summary
    tampered_summary.loc[0, "q50"] += 1.0
    with pytest.raises(ValueError, match="summary|retained|replay|inconsistent"):
        AssetForecastResult(
            summary=tampered_summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            components=result.components,
            channel_paths=result.channel_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )
    tampered_components = result.components
    tampered_components.loc[0, "scenario_contribution"] += 1.0
    with pytest.raises(ValueError, match="component|retained|replay|inconsistent"):
        AssetForecastResult(
            summary=result.summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            components=tampered_components,
            channel_paths=result.channel_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )


def test_inputs_outputs_and_config_are_defensive_and_frozen(
    channel_forecast: ChannelForecastResult,
    scenario_catalog: ScenarioCatalog,
) -> None:
    frames = _forecast_frames(16)
    forecast_input = _asset_input(
        channel_forecast,
        scenario_catalog,
        frames=frames,
    )
    frames["valuation_forecasts"].loc[0, "valuation_value"] = 999.0
    assert forecast_input.valuation_forecasts.loc[0, "valuation_value"] != 999.0
    returned = forecast_input.valuation_forecasts
    returned.loc[0, "valuation_value"] = 999.0
    assert forecast_input.valuation_forecasts.loc[0, "valuation_value"] != 999.0

    result = forecast_asset_distributions(
        forecast_input,
        config=AssetForecastConfig(seed=3, min_effective_samples=12),
    )
    summary = result.summary
    summary.loc[0, "q50"] = 999.0
    assert result.summary.loc[0, "q50"] != 999.0
    with pytest.raises(FrozenInstanceError):
        result.config.seed = 4


def test_task26_component_dict_literals_do_not_repeat_keys() -> None:
    source = (
        PROJECT_ROOT / "src" / "seven_cycle_platform" / "forecast" / "assets.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
        assert len(keys) == len(set(keys))
