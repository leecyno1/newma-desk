from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.attribution.stage2 import (
    CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    ChannelToAssetResult,
)
from seven_cycle_platform.forecast.assets import (
    BENCHMARK_FORECAST_INPUT_COLUMNS,
    CONTROL_FORECAST_INPUT_COLUMNS,
    EVENT_FORECAST_INPUT_COLUMNS,
    INTERACTION_FORECAST_INPUT_COLUMNS,
    POSITIONING_FORECAST_INPUT_COLUMNS,
    RESIDUAL_FORECAST_INPUT_COLUMNS,
    VALUATION_FORECAST_INPUT_COLUMNS,
    AssetForecastConfig,
    AssetForecastInput,
    forecast_asset_distributions,
)
from seven_cycle_platform.forecast.channels import (
    CHANNEL_HISTORY_COLUMNS,
    CURRENT_CHANNEL_STATE_COLUMNS,
    CURRENT_EXOGENOUS_PATH_COLUMNS,
    CYCLE_PREDICTOR_ARCHIVE_COLUMNS,
    EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
    ChannelForecastConfig,
    ChannelForecastInput,
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
from seven_cycle_platform.forecast.evaluation import (
    OOS_FOLD_ARTIFACT_COLUMNS,
    MappingReference,
    PromotionConfig,
    PromotionEvidenceContext,
    evaluate_challenger_promotion,
)
from seven_cycle_platform.forecast.protocol import (
    FeatureAudit,
    ModelCard,
)
from seven_cycle_platform.forecast.scenarios import (
    STANDARD_SCENARIO_IDS,
    load_scenario_catalog,
)
from seven_cycle_platform.forecast.evaluation import (
    MAPPING_MANIFEST_METADATA_KEY,
    MAPPING_REFERENCE_FILENAME,
    MAPPING_REFERENCE_SCHEMA_VERSION,
)
from seven_cycle_platform.forecast.protocol import GOVERNED_MAPPING_REQUIRED
from seven_cycle_platform.mapping.distribution import (
    CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    CurrentDistributionConfig,
    CurrentDistributionResult,
    direction_probabilities,
)
from seven_cycle_platform.mapping.features import (
    CurrentFeatureSnapshot,
    FeatureInput,
    FeatureKind,
    FeaturePayload,
    FeatureProvenance,
    FreshnessPolicy,
    StructuralDriftFlag,
)
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.mapping.transferability import (
    TransferabilityConfig,
    score_transferability,
)
from seven_cycle_platform.mapping.weights import (
    WEIGHT_POLICY_COLUMNS,
    suggest_weight_ranges,
)
from seven_cycle_platform.products.asset_mapping_current import (
    M3_INFLUENCE_COLUMNS,
    build_asset_mapping_current,
)
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_FILENAME,
    ASSET_MAPPING_FUTURE_SCHEMA,
    build_asset_mapping_future,
    mapping_manifest_metadata,
)
from seven_cycle_platform.products.cycle_forecast import (
    CYCLE_FORECAST_FILENAME,
    CYCLE_FORECAST_SCHEMA,
    build_cycle_forecast,
)
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import RunManifest
from seven_cycle_platform.storage.run_context import canonical_json_bytes
from seven_cycle_platform.types import VintageKind
from seven_cycle_platform.verification import forecast as verification_api


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2024, 6, 30)
FUTURE_DATES = pd.date_range("2024-07-31", periods=12, freq="ME")
ASSET_ID = "asset_alpha"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
M3_RUN_ID = "2024-06-28-aaaaaaaaaaaa-bbbbbbbbbbbb"
COMPONENT_IDENTITY_COLUMNS = (
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
)


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _component_contract_hash(
    row: pd.Series,
    baseline_entries: list[dict[str, object]],
    scenario_entries: list[dict[str, object]],
) -> str:
    payload = {
        "schema_version": 1,
        "asset_id": row["asset_id"],
        "scenario_id": row["scenario_id"],
        "horizon_months": int(row["horizon_months"]),
        "baseline_component_keys": sorted(
            [entry["component_type"], entry["component_id"]]
            for entry in baseline_entries
        ),
        "scenario_component_keys": sorted(
            [entry["component_type"], entry["component_id"]]
            for entry in scenario_entries
        ),
        "source_identity": {
            column: row[column] for column in COMPONENT_IDENTITY_COLUMNS
        },
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


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


def _cycle_forecast():
    registry = _registry()
    return forecast_cycle_phases(
        CycleForecastInput(
            as_of=AS_OF,
            cycle_specs=registry.cycles,
            indicator_specs=registry.indicators,
            states=_cycle_states(),
            leading_signals=pd.DataFrame(columns=LEADING_SIGNAL_COLUMNS),
            calibration_history=pd.DataFrame(columns=CALIBRATION_HISTORY_COLUMNS),
        ),
        config=CycleForecastConfig(draw_count=8, seed=13),
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


def _channel_forecast(cycle_forecast):
    registry = _registry()
    origins = pd.date_range("2020-01-31", periods=18, freq="ME")
    channel_rows = []
    cycle_rows = []
    for origin_number, origin in enumerate(origins):
        for horizon in range(1, 13):
            target_date = _forecast_date(origin, horizon)
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
                        "target_visible_date": target_date + pd.Timedelta(days=5),
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
        cycle_forecast=cycle_forecast,
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


def _stage2_rows(
    labels: list[tuple[str, str, float, float]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    posterior_date = pd.Timestamp(AS_OF)
    predicted = float(sum(mean * value for _, _, mean, value in labels))
    residual = 0.0005
    common = {
        "training_start": pd.Timestamp("2020-01-31"),
        "training_end": posterior_date - pd.offsets.MonthEnd(1),
        "training_count": 42,
        "effective_training_count": 36.0,
        "parent_node_id": "industry_asset_alpha",
        "own_weight": 0.8,
        "parent_weight": 0.2,
        "confidence": 0.9,
        "proxy_discount": 1.0,
        "condition_number": 12.0,
        "status": "estimated",
        "window": "expanding",
        "rolling_window": None,
        "forgetting_factor": 1.0,
        "estimation_method": "hierarchical_tvp_ridge",
    }
    components = [
        {
            "date": posterior_date,
            "asset_id": ASSET_ID,
            "component_type": component_type,
            "component_id": component_id,
            "component_value": value,
            "coefficient_mean": mean,
            "contribution": mean * value,
            "observed_return": predicted + residual,
            "predicted_return": predicted,
            "asset_residual": residual,
            "parent_coefficient_mean": np.nan,
            **common,
        }
        for component_type, component_id, mean, value in labels
    ]
    components.append(
        {
            "date": posterior_date,
            "asset_id": ASSET_ID,
            "component_type": "residual",
            "component_id": "asset_residual",
            "component_value": residual,
            "coefficient_mean": 1.0,
            "contribution": residual,
            "observed_return": predicted + residual,
            "predicted_return": predicted,
            "asset_residual": residual,
            "parent_coefficient_mean": np.nan,
            **common,
        }
    )
    posteriors = [
        {
            "date": posterior_date,
            "node_level": "asset",
            "node_id": ASSET_ID,
            "parent_node_id": "industry_asset_alpha",
            "component_type": component_type,
            "component_id": component_id,
            "coefficient_mean": mean,
            "parent_coefficient_mean": np.nan,
            "prior_precision": 1.0,
            "own_weight": 0.8,
            "parent_weight": 0.2,
            "confidence": 0.9,
            "proxy_discount": 1.0,
            "training_start": pd.Timestamp("2020-01-31"),
            "training_end": posterior_date - pd.offsets.MonthEnd(1),
            "training_count": 42,
            "effective_training_count": 36.0,
            "condition_number": 12.0,
            "status": "estimated",
            "window": "expanding",
            "rolling_window": None,
            "forgetting_factor": 1.0,
            "estimation_method": "hierarchical_tvp_ridge",
        }
        for component_type, component_id, mean, _ in labels
    ]
    covariance = []
    for row_position, (type_i, id_i, _, _) in enumerate(labels):
        for column_position, (type_j, id_j, _, _) in enumerate(labels):
            covariance.append(
                {
                    "date": posterior_date,
                    "node_level": "asset",
                    "node_id": ASSET_ID,
                    "parent_node_id": "industry_asset_alpha",
                    "component_i_type": type_i,
                    "component_i_id": id_i,
                    "component_j_type": type_j,
                    "component_j_id": id_j,
                    "coefficient_covariance": (
                        0.0004 if row_position == column_position else 0.0
                    ),
                    "training_start": pd.Timestamp("2020-01-31"),
                    "training_end": posterior_date - pd.offsets.MonthEnd(1),
                    "training_count": 42,
                    "effective_training_count": 36.0,
                    "prior_precision": 1.0,
                    "own_weight": 0.8,
                    "parent_weight": 0.2,
                    "confidence": 0.9,
                    "proxy_discount": 1.0,
                    "condition_number": 12.0,
                    "status": "estimated",
                    "window": "expanding",
                    "rolling_window": None,
                    "forgetting_factor": 1.0,
                    "estimation_method": "hierarchical_tvp_ridge",
                }
            )
    return components, posteriors, covariance


def _stage2() -> ChannelToAssetResult:
    labels = [
        ("intercept", "intercept", 0.001, 1.0),
        ("benchmark", "benchmark_return", 0.20, 0.002),
        ("channel", "growth_demand", 0.50, 0.10),
        ("channel", "inflation_prices", -0.30, -0.04),
        ("channel", "real_rate_discount", -0.25, 0.02),
        ("channel", "liquidity_credit", 0.20, 0.03),
        ("channel", "supply_inventory_geopolitics", -0.15, 0.01),
        ("control", "valuation_z", -0.12, -0.30),
        ("control", "positioning_score", 0.06, 0.40),
        ("control", "liquidity_control", 0.08, 0.20),
        ("interaction", "growth_x_valuation", 0.03, -0.03),
        ("event", "event_shock", 0.04, 0.10),
    ]
    components, posteriors, covariance = _stage2_rows(labels)
    return ChannelToAssetResult(
        components=pd.DataFrame(
            components,
            columns=CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
        ),
        posteriors=pd.DataFrame(
            posteriors,
            columns=CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
        ),
        covariance=pd.DataFrame(
            covariance,
            columns=CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
        ),
    )


def _feature_rows(
    component_ids: tuple[str, ...],
    *,
    draw_count: int,
    value_column: str,
    unit: str,
) -> list[dict[str, object]]:
    rows = []
    for component_position, component_id in enumerate(component_ids):
        for draw_id in range(draw_count):
            for month_number, forecast_date in enumerate(FUTURE_DATES, start=1):
                rows.append(
                    {
                        "forecast_origin": AS_OF,
                        "date": forecast_date,
                        "visible_date": AS_OF,
                        "generated_date": AS_OF,
                        "data_vintage": AS_OF,
                        "asset_id": ASSET_ID,
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
    benchmark_rows = []
    residual_rows = []
    for draw_id in range(draw_count):
        for month_number, forecast_date in enumerate(FUTURE_DATES, start=1):
            provenance = {
                "forecast_origin": AS_OF,
                "date": forecast_date,
                "visible_date": AS_OF,
                "generated_date": AS_OF,
                "data_vintage": AS_OF,
                "asset_id": ASSET_ID,
                "draw_id": draw_id,
                "unit": "decimal_return",
                "path_kind": "forecast",
            }
            benchmark_rows.append(
                {
                    **provenance,
                    "benchmark_return": 0.001 + 0.0001 * month_number,
                    "model_version": "benchmark-v1",
                }
            )
            residual_rows.append(
                {
                    **provenance,
                    "residual_return": 0.0002 * ((draw_id + month_number) % 5 - 2),
                    "model_version": "residual-v1",
                }
            )
    return {
        "valuation_forecasts": pd.DataFrame(
            _feature_rows(
                ("valuation_z",),
                draw_count=draw_count,
                value_column="valuation_value",
                unit="z_score",
            ),
            columns=VALUATION_FORECAST_INPUT_COLUMNS,
        ),
        "positioning_forecasts": pd.DataFrame(
            _feature_rows(
                ("positioning_score",),
                draw_count=draw_count,
                value_column="positioning_value",
                unit="score",
            ),
            columns=POSITIONING_FORECAST_INPUT_COLUMNS,
        ),
        "control_forecasts": pd.DataFrame(
            _feature_rows(
                ("liquidity_control",),
                draw_count=draw_count,
                value_column="control_value",
                unit="score",
            ),
            columns=CONTROL_FORECAST_INPUT_COLUMNS,
        ),
        "interaction_forecasts": pd.DataFrame(
            _feature_rows(
                ("growth_x_valuation",),
                draw_count=draw_count,
                value_column="interaction_value",
                unit="interaction_score",
            ),
            columns=INTERACTION_FORECAST_INPUT_COLUMNS,
        ),
        "event_forecasts": pd.DataFrame(
            _feature_rows(
                ("event_shock",),
                draw_count=draw_count,
                value_column="event_value",
                unit="scenario_score",
            ),
            columns=EVENT_FORECAST_INPUT_COLUMNS,
        ),
        "benchmark_forecasts": pd.DataFrame(
            benchmark_rows,
            columns=BENCHMARK_FORECAST_INPUT_COLUMNS,
        ),
        "residual_forecasts": pd.DataFrame(
            residual_rows,
            columns=RESIDUAL_FORECAST_INPUT_COLUMNS,
        ),
    }


def _asset_forecasts(channel_forecast) -> tuple:
    catalog = load_scenario_catalog(
        PROJECT_ROOT / "config" / "seven_cycle" / "scenarios.yaml"
    )
    frames = _forecast_frames(
        channel_forecast.forecast_input.cycle_forecast.config.draw_count
    )
    stage2 = _stage2()
    return tuple(
        forecast_asset_distributions(
            AssetForecastInput(
                as_of=AS_OF,
                view_mode="forecast",
                scenario_catalog=catalog,
                scenario_id=scenario_id,
                channel_forecast=channel_forecast,
                stage2=stage2,
                **frames,
            ),
            config=AssetForecastConfig(seed=1729, min_effective_samples=6),
        )
        for scenario_id in STANDARD_SCENARIO_IDS
    )


def _unavailable_scenario_forecast(source_result, *, scenario_id: str):
    source_input = source_result.forecast_input
    empty_frames = {
        name: getattr(source_input, name).iloc[0:0].copy(deep=True)
        for name in (
            "valuation_forecasts",
            "positioning_forecasts",
            "control_forecasts",
            "interaction_forecasts",
            "event_forecasts",
            "benchmark_forecasts",
            "residual_forecasts",
        )
    }
    return forecast_asset_distributions(
        AssetForecastInput(
            as_of=source_input.as_of,
            view_mode="forecast",
            scenario_catalog=source_input.scenario_catalog,
            scenario_id=scenario_id,
            channel_forecast=source_input.channel_forecast,
            stage2=source_input.stage2,
            **empty_frames,
        ),
        config=source_result.config,
    )


def _current_context() -> RunContext:
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF - timedelta(days=1),
        model_version="m4-current-mapping-v1",
        config={"mapping": "current", "as_of": AS_OF.isoformat()},
        input_checksums={"fixture.json": _checksum(b"current-mapping")},
        quality_summary={"passed": 1},
        created_at=datetime(2024, 7, 1, tzinfo=timezone.utc),
    )


def _feature(kind: FeatureKind, feature_id: str, entity_id: str | None = None):
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values={"value": 0.25},
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=AS_OF - timedelta(days=5),
        release_date=AS_OF - timedelta(days=4),
        vintage_date=AS_OF - timedelta(days=3),
        source="integration-point-in-time-archive",
        unit="score",
        retrieval_time=datetime.combine(
            AS_OF - timedelta(days=2),
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=VintageKind.REALTIME,
        methodology="point_in_time_integration_fixture",
    )
    return FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=30,
            max_visible_age_days=30,
        ),
        structural_drift=StructuralDriftFlag(
            detected=False,
            score=0.10,
            threshold=0.50,
            method="rolling_population_stability_index",
            baseline_id="mapping-baseline-v1",
            evaluated_at=AS_OF - timedelta(days=2),
            reason="within threshold",
        ),
    )


def _snapshot() -> CurrentFeatureSnapshot:
    return CurrentFeatureSnapshot(
        as_of=AS_OF,
        cycle_states=tuple(
            _feature(FeatureKind.CYCLE, f"C{position}") for position in range(1, 8)
        ),
        channel_states=(_feature(FeatureKind.CHANNEL, "growth_demand"),),
        valuation_controls=(_feature(FeatureKind.VALUATION, "forward_pe", ASSET_ID),),
        earnings_controls=(
            _feature(FeatureKind.EARNINGS, "earnings_revision", ASSET_ID),
        ),
        positioning_controls=(
            _feature(FeatureKind.POSITIONING, "fund_positioning", ASSET_ID),
        ),
        liquidity_controls=(
            _feature(FeatureKind.LIQUIDITY, "market_liquidity", ASSET_ID),
        ),
        event_scenarios=(_feature(FeatureKind.EVENT, "policy_surprise", ASSET_ID),),
        historical_posterior=(
            _feature(FeatureKind.HISTORICAL_POSTERIOR, "asset_posterior", ASSET_ID),
        ),
        run_context=_current_context(),
    )


def _current_distribution(
    snapshot: CurrentFeatureSnapshot,
) -> CurrentDistributionResult:
    monthly_rates = (0.025, 0.010, -0.015, 0.005, 0.020)
    config = CurrentDistributionConfig(
        draw_count=len(monthly_rates),
        seed=0,
        residual_block_length=1,
        min_effective_samples=1,
    )
    monthly_rows = []
    draw_rows = []
    summary_rows = []
    for draw_id, monthly_return in enumerate(monthly_rates):
        for month_number, forecast_date in enumerate(FUTURE_DATES, start=1):
            monthly_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "draw_id": draw_id,
                    "month_number": month_number,
                    "date": forecast_date,
                    "forecast_origin": AS_OF,
                    "asset_monthly_return": monthly_return,
                    "benchmark_monthly_return": 0.0,
                    "relative_monthly_return": monthly_return,
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                }
            )
    for horizon in (3, 6, 12):
        returns = []
        drawdowns = []
        for draw_id, monthly_return in enumerate(monthly_rates):
            horizon_return = (1.0 + monthly_return) ** horizon - 1.0
            drawdown = float(compute_max_drawdown(np.repeat(monthly_return, horizon)))
            returns.append(horizon_return)
            drawdowns.append(drawdown)
            draw_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "draw_id": draw_id,
                    "horizon_months": horizon,
                    "absolute_return": horizon_return,
                    "benchmark_return": 0.0,
                    "excess_return": horizon_return,
                    "absolute_max_drawdown": drawdown,
                    "excess_max_drawdown": drawdown,
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                }
            )
        return_values = np.asarray(returns)
        drawdown_values = np.asarray(drawdowns)
        q10, q25, q50, q75, q90 = np.quantile(
            return_values,
            [0.10, 0.25, 0.50, 0.75, 0.90],
        )
        risk = summarize_risk(return_values, drawdown_values)
        for basis in ("absolute", "excess"):
            probabilities = direction_probabilities(
                return_values,
                neutral_band=config.neutral_bands[(basis, horizon)],
            )
            summary_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "horizon_months": horizon,
                    "return_basis": basis,
                    "raw_up_probability": probabilities["up"],
                    "raw_neutral_probability": probabilities["neutral"],
                    "raw_down_probability": probabilities["down"],
                    "up_probability": probabilities["up"],
                    "neutral_probability": probabilities["neutral"],
                    "down_probability": probabilities["down"],
                    "q10": float(q10),
                    "q25": float(q25),
                    "q50": float(q50),
                    "q75": float(q75),
                    "q90": float(q90),
                    "expected_return": float(np.mean(return_values)),
                    "volatility": risk.volatility,
                    "var95": risk.var95,
                    "cvar95": risk.cvar95,
                    "drawdown_q50": risk.drawdown_q50,
                    "drawdown_q80": risk.drawdown_q80,
                    "drawdown_q95": risk.drawdown_q95,
                    "effective_samples": 36,
                    "stage1_training_count": 36,
                    "stage2_effective_training_count": 36,
                    "residual_history_count": 36,
                    "status": "available",
                    "calibration_version": "identity-v1",
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                    "snapshot_data_vintage": snapshot.provenance.data_vintage,
                    "snapshot_model_version": snapshot.provenance.model_version,
                    "snapshot_config_hash": snapshot.provenance.config_hash,
                    "stage1_posterior_date": AS_OF - timedelta(days=2),
                    "stage2_posterior_date": AS_OF - timedelta(days=2),
                    "forecast_origin": AS_OF,
                }
            )
    return CurrentDistributionResult(
        summary=pd.DataFrame(
            summary_rows,
            columns=CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
        ),
        monthly_draws=pd.DataFrame(
            monthly_rows,
            columns=CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
        ),
        draws=pd.DataFrame(draw_rows, columns=CURRENT_DISTRIBUTION_DRAW_COLUMNS),
        config=config,
    )


def _current_mapping():
    snapshot = _snapshot()
    distribution = _current_distribution(snapshot)
    evidence = pd.DataFrame(
        [
            {
                "asset_id": ASSET_ID,
                "horizon_months": horizon,
                "sign_stability": 0.95,
                "magnitude_stability": 0.95,
                "historical_neighbor_similarity": 0.95,
                "constituent_business_model_stability": 0.95,
                "valuation_positioning_similarity": 0.95,
                "structural_stability": 0.95,
                "cycle_confidence": 0.95,
                "channel_confidence": 0.95,
                "proxy_discount": 0.0,
                "model_oos_loss": 0.70,
                "baseline_oos_loss": 1.00,
                "oos_validation_count": 24,
                "evidence_date": AS_OF - timedelta(days=1),
                "validation_end": date(2024, 5, 31),
            }
            for horizon in (3, 6, 12)
        ]
    )
    transferability = score_transferability(
        distribution,
        evidence,
        TransferabilityConfig(),
    )
    policy = pd.DataFrame(
        [
            {
                "asset_id": ASSET_ID,
                "horizon_months": horizon,
                "neutral_min_weight": 0.40,
                "neutral_max_weight": 0.50,
                "max_active_tilt": 0.20,
                "active_risk_budget_cap": 0.20,
                "model_disagreement": 0.0,
                "leveraged": False,
                "liquidity_constrained": False,
                "currency_exposed": False,
                "policy_date": AS_OF,
                "policy_version": "weight-policy-v1",
            }
            for horizon in (3, 6, 12)
        ],
        columns=WEIGHT_POLICY_COLUMNS,
    )
    ranges = suggest_weight_ranges(distribution, transferability, policy)
    influence_rows = []
    for horizon in (3, 6, 12):
        for component_id in tuple(f"C{position}" for position in range(1, 8)):
            influence_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "horizon_months": horizon,
                    "component_type": "cycle",
                    "component_id": component_id,
                    "influence_score": 0.10,
                    "status": "available",
                    "evidence_level": "high",
                    "reason_code": "score_available",
                    "source_stage": "m3_asset_attribution",
                    "source_run_id": M3_RUN_ID,
                    "source_date": AS_OF - timedelta(days=2),
                    "source_model_version": "m3-attribution-v1",
                    "source_config_hash": HASH_D,
                }
            )
        influence_rows.append(
            {
                "asset_id": ASSET_ID,
                "horizon_months": horizon,
                "component_type": "channel",
                "component_id": "growth_demand",
                "influence_score": -0.20,
                "status": "available",
                "evidence_level": "high",
                "reason_code": "score_available",
                "source_stage": "m3_asset_attribution",
                "source_run_id": M3_RUN_ID,
                "source_date": AS_OF - timedelta(days=2),
                "source_model_version": "m3-attribution-v1",
                "source_config_hash": HASH_D,
            }
        )
    return build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        ranges,
        pd.DataFrame(influence_rows, columns=M3_INFLUENCE_COLUMNS),
    )


def _publish_promotion_mapping(tmp_path: Path) -> tuple[Path, RunManifest]:
    mapping_product = "asset_mapping_future"
    mapping_id = "promotion-evidence"
    artifact_filename = "mapping.json"
    artifact_bytes = b'{"assets":["asset_alpha"]}\n'
    metadata = {
        "schema_version": MAPPING_REFERENCE_SCHEMA_VERSION,
        "mapping_product": mapping_product,
        "mapping_id": mapping_id,
        "artifact_filename": artifact_filename,
    }
    context = RunContext.create(
        as_of=date(2020, 3, 31),
        data_vintage=date(2020, 3, 31),
        model_version="mapping-evidence-v1",
        config={"mapping_id": mapping_id},
        input_checksums={"inputs/channels.parquet": HASH_A},
        quality_summary={MAPPING_MANIFEST_METADATA_KEY: metadata},
        created_at=datetime(2020, 4, 1, tzinfo=timezone.utc),
    )
    catalog = {
        **metadata,
        "version": context.model_version,
        "run_id": context.run_id,
        "config_hash": context.config_hash,
        "artifact_hash": hashlib.sha256(artifact_bytes).hexdigest(),
        "as_of": context.as_of.isoformat(),
    }
    product_root = tmp_path / "promotion-evidence" / mapping_product

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / artifact_filename).write_bytes(artifact_bytes)
        (staging_dir / MAPPING_REFERENCE_FILENAME).write_bytes(
            canonical_json_bytes(catalog) + b"\n"
        )

    manifest = publish_run(product_root, context, write_staging=write_staging)
    return product_root / "runs" / manifest.run_id, manifest


def _model_card(role: str, *, version: str) -> ModelCard:
    return ModelCard(
        model_id=f"cycle-{role}",
        version=version,
        role=role,
        scope="cycle",
        algorithm="state_space" if role == "champion" else "sequence_challenger",
        code_hash=HASH_A if role == "champion" else HASH_B,
        config_hash=HASH_B if role == "champion" else HASH_A,
        seed_policy="fixed",
        seed=7,
        training_objective="minimize governed out-of-sample forecast loss",
        output_contract="cycle_forecast_v1",
        downstream_mapping_requirement=GOVERNED_MAPPING_REQUIRED,
        direct_asset_weights_allowed=False,
        direct_asset_prediction_bypass_allowed=False,
        historical_contribution_weights_allowed=False,
        feature_ids=("f_growth", "f_credit"),
        data_vintage=date(2020, 3, 31),
        training_cutoff=date(2020, 3, 31),
    )


def _feature_audit(card: ModelCard) -> FeatureAudit:
    return FeatureAudit(
        model_id=card.model_id,
        version=card.version,
        role=card.role,
        scope=card.scope,
        as_of=card.data_vintage,
        feature_ids=card.feature_ids,
        max_visible_date=date(2020, 3, 30),
        max_generated_date=date(2020, 3, 30),
        max_vintage_date=date(2020, 3, 30),
        train_start=date(2018, 1, 1),
        train_end=card.training_cutoff,
        data_vintage=card.data_vintage,
        leakage_checks=(
            "visible_date_lte_as_of",
            "generated_date_lte_as_of",
            "vintage_date_lte_as_of",
        ),
        forbidden_features=(),
        status="passed",
        reasons=(),
        code_hash=card.code_hash,
        config_hash=card.config_hash,
    )


def _probabilities(realized_phase: str, true_probability: float) -> dict[str, float]:
    phases = ("expansion", "downturn", "contraction", "recovery")
    other = (1.0 - true_probability) / 3.0
    return {
        f"{phase}_probability": true_probability if phase == realized_phase else other
        for phase in phases
    }


def _promotion_artifacts(
    card: ModelCard,
    *,
    challenger: bool,
    evidence_context: PromotionEvidenceContext,
) -> pd.DataFrame:
    phases = ("expansion", "downturn", "contraction", "recovery")
    reference = evidence_context.mapping_reference
    records = []
    for fold_index, validation_origin in enumerate(
        pd.date_range("2020-06-30", periods=3, freq="6ME"),
        start=1,
    ):
        embargo_cutoff = validation_origin - pd.Timedelta(days=5)
        train_end = embargo_cutoff - pd.Timedelta(days=1)
        for sample_index in range(4):
            realized_phase = phases[sample_index]
            target_date = validation_origin + pd.offsets.MonthEnd(3)
            downstream_actual = sample_index / 10.0
            downstream_error = 0.5 if challenger else 1.0
            covered = sample_index < (3 if challenger else 1)
            records.append(
                {
                    "outer_fold_id": f"fold-{fold_index}",
                    "sample_id": f"fold-{fold_index}-sample-{sample_index}",
                    "train_start": pd.Timestamp("2018-01-01"),
                    "train_end": train_end,
                    "inner_tuning_start": train_end - pd.Timedelta(days=90),
                    "inner_tuning_end": train_end - pd.Timedelta(days=1),
                    "validation_origin": validation_origin,
                    "embargo_cutoff": embargo_cutoff,
                    "evaluation_cutoff": pd.Timestamp(
                        evidence_context.evaluation_cutoff
                    ),
                    "target_date": target_date,
                    "target_visible_date": target_date + pd.Timedelta(days=5),
                    "target_revision_window_end": target_date + pd.Timedelta(days=10),
                    "model_id": card.model_id,
                    "model_role": card.role,
                    "model_version": card.version,
                    "seed": card.seed,
                    "prediction_scope": card.scope,
                    "prediction_id": "C3",
                    "horizon_months": 3,
                    **_probabilities(
                        realized_phase,
                        0.70 if challenger else 0.45,
                    ),
                    "realized_phase": realized_phase,
                    "interval_lower": -1.0 if covered else 1.0,
                    "interval_upper": 1.0 if covered else 2.0,
                    "interval_nominal_coverage": 0.75,
                    "realized_target": 0.0,
                    "downstream_asset_id": ASSET_ID,
                    "downstream_asset_prediction": downstream_actual + downstream_error,
                    "downstream_asset_actual": downstream_actual,
                    "downstream_asset_loss": downstream_error**2,
                    "downstream_loss": "squared_error",
                    "mapping_product": reference.mapping_product,
                    "mapping_id": reference.mapping_id,
                    "mapping_version": reference.version,
                    "mapping_run_id": reference.run_id,
                    "mapping_config_hash": reference.config_hash,
                    "mapping_artifact_hash": reference.artifact_hash,
                    "mapping_manifest_hash": reference.manifest_hash,
                    "mapping_reference_hash": reference.reference_hash,
                    "mapping_reference_filename": reference.reference_filename,
                    "mapping_artifact_filename": reference.artifact_filename,
                    "mapping_as_of": reference.as_of,
                    "data_vintage": validation_origin - pd.Timedelta(days=1),
                    "feature_max_visible_date": validation_origin
                    - pd.Timedelta(days=1),
                    "feature_max_generated_date": validation_origin
                    - pd.Timedelta(days=1),
                    "feature_max_vintage_date": validation_origin
                    - pd.Timedelta(days=1),
                    "status": "complete",
                    "reason": None,
                }
            )
    return pd.DataFrame(records, columns=OOS_FOLD_ARTIFACT_COLUMNS)


def _rejected_promotion(tmp_path: Path, *, champion_version: str):
    run_dir, manifest = _publish_promotion_mapping(tmp_path)
    evidence = PromotionEvidenceContext(
        evaluation_cutoff=date(2022, 12, 31),
        mapping_reference=MappingReference.from_published_run(
            run_dir,
            expected_manifest=manifest,
        ),
    )
    champion = _model_card("champion", version=champion_version)
    challenger = _model_card("challenger", version="cycle-challenger-v1")
    return evaluate_challenger_promotion(
        _promotion_artifacts(champion, challenger=False, evidence_context=evidence),
        _promotion_artifacts(challenger, challenger=True, evidence_context=evidence),
        champion_model_card=champion,
        challenger_model_card=challenger,
        champion_feature_audit=_feature_audit(champion),
        challenger_feature_audit=_feature_audit(challenger),
        evidence_context=evidence,
        config=replace(
            PromotionConfig(
                minimum_folds=3,
                minimum_samples=12,
                embargo_days=5,
                coverage_tolerance=0.05,
            ),
            minimum_folds=4,
        ),
    )


def _release_context(*, revision: int = 1) -> RunContext:
    mapping_id = "cn-core-assets"
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF,
        model_version=f"m5-forecast-products-v{revision}",
        config={"mapping_id": mapping_id, "revision": revision},
        input_checksums={
            "inputs/task24-26.fixture": _checksum(f"task28-{revision}".encode())
        },
        quality_summary={
            MAPPING_MANIFEST_METADATA_KEY: mapping_manifest_metadata(mapping_id),
            "task28": {"contract": "governed"},
        },
        created_at=datetime(2024, 7, revision, tzinfo=timezone.utc),
    )


@pytest.fixture(scope="module")
def governed_bundle(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("task28-governed")
    cycle_result = _cycle_forecast()
    channel_result = _channel_forecast(cycle_result)
    asset_results = _asset_forecasts(channel_result)
    current_mapping = _current_mapping()
    promotion = _rejected_promotion(
        root,
        champion_version=cycle_result.config.model_version,
    )
    return cycle_result, channel_result, asset_results, current_mapping, promotion


def test_real_m5_build_verify_publish_reload_and_reference(
    tmp_path: Path,
    governed_bundle,
) -> None:
    cycle_result, channel_result, asset_results, current_mapping, promotion = (
        governed_bundle
    )
    context = _release_context()
    build = verification_api.build_forecast_products(
        cycle_result,
        asset_results,
        current_mapping,
        promotion,
        context=context,
    )
    cycle_product = build.cycle_product
    future_product = build.mapping_product
    assert build.verification.passed

    assert promotion.promotion_decision == "rejected"
    assert cycle_product.forecast["forecast_value_source_role"].eq("champion").all()
    assert cycle_product.forecast["challenger_status"].eq("experimental").all()
    assert set(future_product.mapping["scenario_id"]) == set(STANDARD_SCENARIO_IDS)
    assert len(future_product.mapping) == len(STANDARD_SCENARIO_IDS) * 3
    assert future_product.mapping["baseline_gate_passed"].all()
    assert set(future_product.mapping["mapping_status"]).issubset(
        {"formal", "conditional"}
    )
    assert not {
        column
        for column in future_product.mapping.columns
        if "weight" in column or "contribution_share" in column
    }

    baseline_result = asset_results[0]
    source_row = baseline_result.summary.loc[
        baseline_result.summary["asset_id"].eq(ASSET_ID)
        & baseline_result.summary["horizon_months"].eq(3)
        & baseline_result.summary["return_basis"].eq("absolute")
    ].iloc[0]
    product_row = future_product.mapping.loc[
        future_product.mapping["scenario_id"].eq("baseline")
        & future_product.mapping["horizon_months"].eq(3)
    ].iloc[0]
    assert product_row["absolute_median"] == pytest.approx(source_row["median"])
    assert product_row["absolute_interval50_lower"] == pytest.approx(
        source_row["interval50_lower"]
    )
    assert json.loads(product_row["scenario_contribution_json"]) == []
    baseline_entries = json.loads(product_row["baseline_component_contribution_json"])
    channel_entries = json.loads(product_row["channel_contribution_json"])
    assert channel_entries == [
        entry for entry in baseline_entries if entry["component_type"] == "channel"
    ]
    assert sum(
        entry["expected_contribution"] for entry in baseline_entries
    ) == pytest.approx(product_row["absolute_expected_return"])
    assert product_row["contribution_conservation_passed"]
    assert len(product_row["contribution_component_contract_hash"]) == 64

    report = verification_api.verify_forecast_products(
        cycle_product,
        future_product,
        context=context,
    )
    assert report.passed
    assert "channel_simple_baseline_comparison" in set(report.findings["check_id"])
    conservation_detail = report.findings.loc[
        report.findings["check_id"].eq("contribution_conservation"),
        "detail",
    ].iloc[0]
    assert "component contract fingerprint verified" in conservation_detail
    detached = future_product.mapping
    detached.loc[0, "absolute_median"] = 99.0
    assert future_product.mapping.loc[0, "absolute_median"] != 99.0

    product_root = tmp_path / "asset_mapping_future"
    publication = verification_api.publish_forecast_products(
        product_root,
        cycle_product,
        future_product,
        context=context,
        mapping_id="cn-core-assets",
    )
    run_dir = product_root / "runs" / publication.manifest.run_id
    assert pq.read_schema(run_dir / CYCLE_FORECAST_FILENAME) == CYCLE_FORECAST_SCHEMA
    assert (
        pq.read_schema(run_dir / ASSET_MAPPING_FUTURE_FILENAME)
        == ASSET_MAPPING_FUTURE_SCHEMA
    )
    assert (run_dir / MAPPING_REFERENCE_FILENAME).is_file()
    assert publication.mapping_reference == MappingReference.from_published_run(
        run_dir,
        expected_manifest=publication.manifest,
    )
    assert publication.mapping_reference.revalidate() == publication.mapping_reference
    assert verification_api.verify_published_forecast_run(
        run_dir,
        expected_manifest=publication.manifest,
    ).passed
    latest = json.loads((product_root / "latest.json").read_text())
    assert latest == {"run_id": publication.manifest.run_id}
    with pytest.raises(FileExistsError, match="immutable"):
        verification_api.publish_forecast_products(
            product_root,
            cycle_product,
            future_product,
            context=context,
            mapping_id="cn-core-assets",
        )


@pytest.mark.parametrize(
    "tamper_mode",
    (
        "missing_nonchannel",
        "tampered_nonchannel",
        "duplicate_scenario",
    ),
)
def test_verification_independently_rejects_forged_contribution_surfaces(
    governed_bundle,
    monkeypatch: pytest.MonkeyPatch,
    tamper_mode: str,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    context = _release_context(revision=4)
    built = verification_api.build_forecast_products(
        cycle_result,
        asset_results,
        current_mapping,
        promotion,
        context=context,
    )
    raw_mapping = object.__getattribute__(built.mapping_product, "mapping")
    if tamper_mode in {"missing_nonchannel", "tampered_nonchannel"}:
        row_index = raw_mapping.index[
            raw_mapping["scenario_id"].eq("baseline")
            & raw_mapping["horizon_months"].eq(3)
        ][0]
        payload = json.loads(
            raw_mapping.loc[row_index, "baseline_component_contribution_json"]
        )
        residual_index = next(
            index
            for index, entry in enumerate(payload)
            if entry["component_type"] == "residual"
        )
        if tamper_mode == "missing_nonchannel":
            payload.pop(residual_index)
        else:
            payload[residual_index]["expected_contribution"] += 0.01
        raw_mapping.loc[row_index, "baseline_component_contribution_json"] = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    else:
        row_index = raw_mapping.index[
            raw_mapping["scenario_id"].eq("growth")
            & raw_mapping["horizon_months"].eq(3)
        ][0]
        payload = json.loads(raw_mapping.loc[row_index, "scenario_contribution_json"])
        payload.append(payload[0].copy())
        raw_mapping.loc[row_index, "scenario_contribution_json"] = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    raw_mapping.loc[row_index, "contribution_conservation_passed"] = True

    monkeypatch.setattr(
        verification_api,
        "validate_asset_mapping_future",
        lambda *args, **kwargs: None,
    )
    report = verification_api.verify_forecast_products(
        built.cycle_product,
        built.mapping_product,
        context=context,
    )

    conservation = report.findings.loc[
        report.findings["check_id"].eq("contribution_conservation")
    ].iloc[0]
    assert conservation["status"] == "failed"
    assert not report.passed


def test_retained_task26_rejects_component_rename_with_forged_hash(
    governed_bundle,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    context = _release_context(revision=5)
    built = verification_api.build_forecast_products(
        cycle_result,
        asset_results,
        current_mapping,
        promotion,
        context=context,
    )
    raw_mapping = object.__getattribute__(built.mapping_product, "mapping")
    row_index = raw_mapping.index[
        raw_mapping["scenario_id"].eq("baseline") & raw_mapping["horizon_months"].eq(3)
    ][0]
    row = raw_mapping.loc[row_index]
    baseline_entries = json.loads(row["baseline_component_contribution_json"])
    scenario_entries = json.loads(row["scenario_contribution_json"])
    residual = next(
        entry for entry in baseline_entries if entry["component_type"] == "residual"
    )
    residual["component_id"] = "renamed_asset_residual"
    raw_mapping.loc[row_index, "baseline_component_contribution_json"] = json.dumps(
        baseline_entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    raw_mapping.loc[row_index, "contribution_component_contract_hash"] = (
        _component_contract_hash(row, baseline_entries, scenario_entries)
    )

    report = verification_api.verify_forecast_products(
        built.cycle_product,
        built.mapping_product,
        context=context,
    )

    assert (
        report.findings.loc[
            report.findings["check_id"].eq("future_mapping_contract"), "status"
        ].iloc[0]
        == "passed"
    )
    assert (
        report.findings.loc[
            report.findings["check_id"].eq("contribution_conservation"), "status"
        ].iloc[0]
        == "passed"
    )
    retained = report.findings.loc[
        report.findings["check_id"].eq("contribution_component_contract")
    ].iloc[0]
    assert retained["status"] == "failed"
    assert not report.passed


def test_persisted_reload_rejects_component_rename_with_original_hash(
    tmp_path: Path,
    governed_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    context = _release_context(revision=6)
    built = verification_api.build_forecast_products(
        cycle_result,
        asset_results,
        current_mapping,
        promotion,
        context=context,
    )
    product_root = tmp_path / "asset_mapping_future"
    publication = verification_api.publish_forecast_products(
        product_root,
        built.cycle_product,
        built.mapping_product,
        context=context,
        mapping_id="cn-core-assets",
    )
    run_dir = product_root / "runs" / publication.manifest.run_id
    mapping_path = run_dir / ASSET_MAPPING_FUTURE_FILENAME
    frame = pd.read_parquet(mapping_path)
    row_index = frame.index[
        frame["scenario_id"].eq("baseline") & frame["horizon_months"].eq(3)
    ][0]
    payload = json.loads(frame.loc[row_index, "baseline_component_contribution_json"])
    residual = next(entry for entry in payload if entry["component_type"] == "residual")
    residual["component_id"] = "renamed_asset_residual"
    frame.loc[row_index, "baseline_component_contribution_json"] = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    table = pa.Table.from_arrays(
        [
            pa.array(frame[field.name].tolist(), type=field.type, from_pandas=True)
            for field in ASSET_MAPPING_FUTURE_SCHEMA
        ],
        schema=ASSET_MAPPING_FUTURE_SCHEMA,
    )
    pq.write_table(table, mapping_path)

    monkeypatch.setattr(
        verification_api,
        "verify_manifest",
        lambda *args, **kwargs: publication.manifest,
    )
    with pytest.raises(ValueError, match="fingerprint|contract hash"):
        verification_api.verify_published_forecast_run(
            run_dir,
            expected_manifest=publication.manifest,
        )


def test_one_real_unavailable_scenario_does_not_pollute_other_scenarios(
    governed_bundle,
) -> None:
    _, _, asset_results, current_mapping, _ = governed_bundle
    scenario_results = list(asset_results)
    unavailable_scenario = "inflation"
    scenario_index = STANDARD_SCENARIO_IDS.index(unavailable_scenario)
    scenario_results[scenario_index] = _unavailable_scenario_forecast(
        asset_results[scenario_index],
        scenario_id=unavailable_scenario,
    )
    product = build_asset_mapping_future(
        tuple(scenario_results),
        current_mapping,
        context=_release_context(revision=3),
    )

    for horizon in (3, 6, 12):
        rows = product.mapping.loc[product.mapping["horizon_months"].eq(horizon)]
        unavailable = rows.loc[rows["status"].eq("unavailable")]
        available = rows.loc[rows["status"].eq("available")]
        assert set(unavailable["scenario_id"]) == {unavailable_scenario}
        assert set(available["scenario_id"]) == (
            set(STANDARD_SCENARIO_IDS) - {unavailable_scenario}
        )
        assert unavailable["mapping_status"].eq("unavailable").all()
        assert unavailable["baseline_component_contribution_json"].eq("[]").all()
        assert unavailable["channel_contribution_json"].eq("[]").all()
        assert unavailable["scenario_contribution_json"].eq("[]").all()
        assert unavailable["contribution_draw_count"].eq(0).all()
        assert unavailable["contribution_conservation_passed"].eq(False).all()
        assert unavailable["contribution_conservation_max_abs_error"].isna().all()
        assert (
            unavailable["contribution_component_contract_hash"]
            .str.fullmatch(r"[0-9a-f]{64}")
            .all()
        )
        assert available["mapping_status"].isin({"formal", "conditional"}).all()
        for column in (
            "transferability_status",
            "evidence_level",
            "freshness_status",
            "baseline_gate_passed",
            "current_mapping_run_id",
            "current_mapping_model_version",
            "current_mapping_snapshot_config_hash",
            "current_mapping_distribution_config_hash",
            "current_mapping_transferability_config_hash",
        ):
            assert rows[column].nunique(dropna=False) == 1
    unavailable_hashes = product.mapping.loc[
        product.mapping["scenario_id"].eq(unavailable_scenario),
        "contribution_component_contract_hash",
    ]
    assert unavailable_hashes.nunique() == 3
    assert product.mapping["scenario_config_hash"].nunique() == 1


def test_preflight_validation_failure_does_not_create_candidate_run(
    tmp_path: Path,
    governed_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    product_root = tmp_path / "asset_mapping_future"
    first_context = _release_context(revision=1)
    first = verification_api.publish_forecast_products(
        product_root,
        build_cycle_forecast(cycle_result, promotion, context=first_context),
        build_asset_mapping_future(
            asset_results,
            current_mapping,
            context=first_context,
        ),
        context=first_context,
        mapping_id="cn-core-assets",
    )
    latest_before = (product_root / "latest.json").read_bytes()

    second_context = _release_context(revision=2)
    second_cycle = build_cycle_forecast(
        cycle_result,
        promotion,
        context=second_context,
    )
    second_future = build_asset_mapping_future(
        asset_results,
        current_mapping,
        context=second_context,
    )

    def fail_preflight(*_args: object, **_kwargs: object) -> None:
        raise ValueError("simulated preflight validation failure")

    monkeypatch.setattr(
        verification_api,
        "verify_forecast_products",
        fail_preflight,
    )
    with pytest.raises(ValueError, match="simulated preflight validation failure"):
        verification_api.publish_forecast_products(
            product_root,
            second_cycle,
            second_future,
            context=second_context,
            mapping_id="cn-core-assets",
        )
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert json.loads(latest_before) == {"run_id": first.manifest.run_id}
    assert not (product_root / "runs" / second_context.run_id).exists()
    assert not (product_root / "staging" / second_context.run_id).exists()


def test_staging_validation_failure_after_artifacts_preserves_latest(
    tmp_path: Path,
    governed_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    product_root = tmp_path / "asset_mapping_future"
    first_context = _release_context(revision=1)
    first = verification_api.publish_forecast_products(
        product_root,
        build_cycle_forecast(cycle_result, promotion, context=first_context),
        build_asset_mapping_future(
            asset_results,
            current_mapping,
            context=first_context,
        ),
        context=first_context,
        mapping_id="cn-core-assets",
    )
    latest_before = (product_root / "latest.json").read_bytes()
    second_context = _release_context(revision=2)
    second_cycle = build_cycle_forecast(
        cycle_result,
        promotion,
        context=second_context,
    )
    second_future = build_asset_mapping_future(
        asset_results,
        current_mapping,
        context=second_context,
    )

    def fail_staged_run(run_dir: Path, *, manifest: RunManifest):
        assert run_dir.parent.name == "staging"
        assert (run_dir / CYCLE_FORECAST_FILENAME).is_file()
        assert (run_dir / ASSET_MAPPING_FUTURE_FILENAME).is_file()
        assert (run_dir / MAPPING_REFERENCE_FILENAME).is_file()
        assert manifest.run_id == second_context.run_id
        assert (product_root / "latest.json").read_bytes() == latest_before
        raise ValueError("simulated validate_staging failure")

    monkeypatch.setattr(verification_api, "_verify_staged_run", fail_staged_run)
    with pytest.raises(ValueError, match="simulated validate_staging failure"):
        verification_api.publish_forecast_products(
            product_root,
            second_cycle,
            second_future,
            context=second_context,
            mapping_id="cn-core-assets",
        )

    assert (product_root / "latest.json").read_bytes() == latest_before
    assert json.loads(latest_before) == {"run_id": first.manifest.run_id}
    assert not (product_root / "runs" / second_context.run_id).exists()
    assert not (product_root / "staging" / second_context.run_id).exists()
    assert not list((product_root / "runs").glob(f".failed.{second_context.run_id}.*"))


def test_mapping_reference_failure_after_rename_preserves_latest_and_isolates(
    tmp_path: Path,
    governed_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_result, _, asset_results, current_mapping, promotion = governed_bundle
    product_root = tmp_path / "asset_mapping_future"
    first_context = _release_context(revision=1)
    first = verification_api.publish_forecast_products(
        product_root,
        build_cycle_forecast(cycle_result, promotion, context=first_context),
        build_asset_mapping_future(
            asset_results,
            current_mapping,
            context=first_context,
        ),
        context=first_context,
        mapping_id="cn-core-assets",
    )
    latest_before = (product_root / "latest.json").read_bytes()
    second_context = _release_context(revision=2)
    second_cycle = build_cycle_forecast(
        cycle_result,
        promotion,
        context=second_context,
    )
    second_future = build_asset_mapping_future(
        asset_results,
        current_mapping,
        context=second_context,
    )

    def fail_mapping_reference(
        cls,
        run_dir: Path,
        *,
        expected_manifest: RunManifest,
    ):
        assert cls is MappingReference
        assert Path(run_dir).parent.name == "runs"
        assert expected_manifest.run_id == second_context.run_id
        assert (Path(run_dir) / "manifest.json").is_file()
        assert (product_root / "latest.json").read_bytes() == latest_before
        raise ValueError("simulated MappingReference failure after rename")

    monkeypatch.setattr(
        MappingReference,
        "from_published_run",
        classmethod(fail_mapping_reference),
    )
    with pytest.raises(ValueError, match="MappingReference failure after rename"):
        verification_api.publish_forecast_products(
            product_root,
            second_cycle,
            second_future,
            context=second_context,
            mapping_id="cn-core-assets",
        )

    assert (product_root / "latest.json").read_bytes() == latest_before
    assert json.loads(latest_before) == {"run_id": first.manifest.run_id}
    assert not (product_root / "runs" / second_context.run_id).exists()
    isolated = list((product_root / "runs").glob(f".failed.{second_context.run_id}.*"))
    assert len(isolated) == 1
    assert (isolated[0] / MAPPING_REFERENCE_FILENAME).is_file()
