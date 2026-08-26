"""Stable, governed current asset mapping product."""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import date, datetime, timezone
import hashlib
import json
from numbers import Integral, Real
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.mapping.distribution import (
    HORIZONS,
    CurrentDistributionConfig,
    CurrentDistributionResult,
)
from seven_cycle_platform.mapping.features import (
    CurrentFeature,
    CurrentFeatureSnapshot,
    FeatureInput,
    FreshnessPolicy,
)
from seven_cycle_platform.mapping.transferability import (
    TRANSFERABILITY_DIMENSIONS,
    TransferabilityConfig,
    TransferabilityResult,
)
from seven_cycle_platform.mapping.weights import (
    WeightRangeConfig,
    WeightRangeResult,
)
from seven_cycle_platform.storage import RUN_ID_PATTERN, RunContext
from seven_cycle_platform.types import EvidenceLevel, MappingStatus


ASSET_MAPPING_CURRENT_FILENAME = "asset_mapping_current.parquet"

M3_INFLUENCE_COLUMNS = (
    "asset_id",
    "horizon_months",
    "component_type",
    "component_id",
    "influence_score",
    "status",
    "evidence_level",
    "reason_code",
    "source_stage",
    "source_run_id",
    "source_date",
    "source_model_version",
    "source_config_hash",
)

ASSET_MAPPING_CURRENT_SCHEMA = pa.schema(
    [
        pa.field("asset_id", pa.string()),
        pa.field("horizon_months", pa.int32()),
        pa.field("absolute_up_probability", pa.float64()),
        pa.field("absolute_neutral_probability", pa.float64()),
        pa.field("absolute_down_probability", pa.float64()),
        pa.field("absolute_q10", pa.float64()),
        pa.field("absolute_q25", pa.float64()),
        pa.field("absolute_q50", pa.float64()),
        pa.field("absolute_q75", pa.float64()),
        pa.field("absolute_q90", pa.float64()),
        pa.field("absolute_expected_return", pa.float64()),
        pa.field("absolute_volatility", pa.float64()),
        pa.field("absolute_var95", pa.float64()),
        pa.field("absolute_cvar95", pa.float64()),
        pa.field("absolute_drawdown_q50", pa.float64()),
        pa.field("absolute_drawdown_q80", pa.float64()),
        pa.field("absolute_drawdown_q95", pa.float64()),
        pa.field("absolute_distribution_status", pa.string()),
        pa.field("absolute_effective_samples", pa.int32()),
        pa.field("absolute_calibration_version", pa.string()),
        pa.field("excess_up_probability", pa.float64()),
        pa.field("excess_neutral_probability", pa.float64()),
        pa.field("excess_down_probability", pa.float64()),
        pa.field("excess_q10", pa.float64()),
        pa.field("excess_q25", pa.float64()),
        pa.field("excess_q50", pa.float64()),
        pa.field("excess_q75", pa.float64()),
        pa.field("excess_q90", pa.float64()),
        pa.field("excess_expected_return", pa.float64()),
        pa.field("excess_volatility", pa.float64()),
        pa.field("excess_var95", pa.float64()),
        pa.field("excess_cvar95", pa.float64()),
        pa.field("excess_drawdown_q50", pa.float64()),
        pa.field("excess_drawdown_q80", pa.float64()),
        pa.field("excess_drawdown_q95", pa.float64()),
        pa.field("excess_distribution_status", pa.string()),
        pa.field("excess_effective_samples", pa.int32()),
        pa.field("excess_calibration_version", pa.string()),
        pa.field("cycle_influence_json", pa.string()),
        pa.field("channel_influence_json", pa.string()),
        pa.field("influence_status", pa.string()),
        pa.field("influence_evidence_level", pa.string()),
        pa.field("influence_reason_codes", pa.string()),
        pa.field("influence_source_stage", pa.string()),
        pa.field("influence_run_id", pa.string()),
        pa.field("influence_source_date", pa.date32()),
        pa.field("influence_model_version", pa.string()),
        pa.field("influence_config_hash", pa.string()),
        pa.field("published_min_weight", pa.float64()),
        pa.field("published_max_weight", pa.float64()),
        pa.field("neutral_min_weight", pa.float64()),
        pa.field("neutral_max_weight", pa.float64()),
        pa.field("source_range_status", pa.string()),
        pa.field("range_status", pa.string()),
        pa.field("range_scope", pa.string()),
        pa.field("range_reason_codes", pa.string()),
        pa.field("range_caveat_codes", pa.string()),
        pa.field("policy_date", pa.date32()),
        pa.field("policy_version", pa.string()),
        pa.field("policy_hash", pa.string()),
        pa.field("transferability_score", pa.float64()),
        pa.field("transferability_status", pa.string()),
        pa.field("sign_score", pa.float64()),
        pa.field("magnitude_score", pa.float64()),
        pa.field("neighbor_score", pa.float64()),
        pa.field("constituent_score", pa.float64()),
        pa.field("valuation_positioning_score", pa.float64()),
        pa.field("structural_score", pa.float64()),
        pa.field("cycle_confidence_score", pa.float64()),
        pa.field("channel_confidence_score", pa.float64()),
        pa.field("proxy_quality_score", pa.float64()),
        pa.field("oos_increment_score", pa.float64()),
        pa.field("baseline_gate_passed", pa.bool_()),
        pa.field("formal_hard_gates_passed", pa.bool_()),
        pa.field("transferability_reason_codes", pa.string()),
        pa.field("transferability_evidence_date", pa.date32()),
        pa.field("transferability_validation_end", pa.date32()),
        pa.field("mapping_status", pa.string()),
        pa.field("evidence_level", pa.string()),
        pa.field("freshness_status", pa.string()),
        pa.field("stale_feature_count", pa.int32()),
        pa.field("freshness_reason_codes", pa.string()),
        pa.field("stale_feature_json", pa.string()),
        pa.field("publication_status", pa.string()),
        pa.field("publication_reason_codes", pa.string()),
        pa.field("caveat_codes", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("snapshot_config_hash", pa.string()),
        pa.field("distribution_config_hash", pa.string()),
        pa.field("transferability_config_hash", pa.string()),
        pa.field("weight_config_hash", pa.string()),
        pa.field("stage1_posterior_date", pa.date32()),
        pa.field("stage2_posterior_date", pa.date32()),
        pa.field("forecast_origin", pa.date32()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)
ASSET_MAPPING_CURRENT_COLUMNS = tuple(ASSET_MAPPING_CURRENT_SCHEMA.names)

_VALIDATED_PRODUCT_TOKEN = object()
_RESULT_FIELDS = frozenset({"mapping"})
_RETURN_BASES = ("absolute", "excess")
_DISTRIBUTION_STATUSES = frozenset({"available", "unavailable"})
_RANGE_STATUSES = frozenset({"available", "unavailable"})
_INFLUENCE_STATUSES = frozenset({"available", "unavailable"})
_INFLUENCE_AGGREGATE_STATUSES = frozenset({"available", "partial", "unavailable"})
_PUBLICATION_STATUSES = frozenset({"live", "partial"})
_FRESHNESS_STATUSES = frozenset({"fresh", "stale"})
_MAPPING_STATUSES = frozenset(member.value for member in MappingStatus)
_EVIDENCE_LEVELS = frozenset(member.value for member in EvidenceLevel)
_EXPECTED_CYCLES = tuple(f"C{position}" for position in range(1, 8))
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_SECRET_PATTERN = re.compile(
    r"(?i)(tushare[_-]?token|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret[_-]?key|bearer\s+|\bsk-[a-z0-9])"
)
_METRIC_SUFFIXES = (
    "up_probability",
    "neutral_probability",
    "down_probability",
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
_FLOAT_COLUMNS = tuple(
    field.name
    for field in ASSET_MAPPING_CURRENT_SCHEMA
    if pa.types.is_floating(field.type)
)
_DATE_COLUMNS = tuple(
    field.name for field in ASSET_MAPPING_CURRENT_SCHEMA if pa.types.is_date(field.type)
)
_STRING_COLUMNS = tuple(
    field.name
    for field in ASSET_MAPPING_CURRENT_SCHEMA
    if pa.types.is_string(field.type)
)
_JSON_COLUMNS = (
    "cycle_influence_json",
    "channel_influence_json",
    "influence_reason_codes",
    "range_reason_codes",
    "range_caveat_codes",
    "transferability_reason_codes",
    "freshness_reason_codes",
    "stale_feature_json",
    "publication_reason_codes",
    "caveat_codes",
)
_PROVENANCE_COLUMNS = (
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "snapshot_config_hash",
    "distribution_config_hash",
    "transferability_config_hash",
    "weight_config_hash",
    "influence_source_stage",
    "influence_run_id",
    "influence_source_date",
    "influence_model_version",
    "influence_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
    "created_at",
)


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


def _enum_value(value: object) -> str:
    member_value = getattr(value, "value", value)
    return str(member_value)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _identifier(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must contain non-empty strings")
    normalized = value.strip()
    _reject_secret_like(normalized, name=name)
    return normalized


def _valid_hash(value: object, *, name: str) -> str:
    normalized = _identifier(value, name=name)
    if _HASH_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return normalized


def _date_value(
    value: object,
    *,
    name: str,
    allow_missing: bool = False,
) -> date | None:
    if _is_missing(value):
        if allow_missing:
            return None
        raise ValueError(f"{name} cannot be missing")
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must contain date-like values")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must contain valid dates") from error
    if timestamp.tzinfo is not None:
        raise ValueError(f"{name} dates must be timezone-naive")
    return timestamp.normalize().date()


def _created_at(value: object) -> datetime:
    if not isinstance(value, (datetime, pd.Timestamp, str, np.datetime64)):
        raise TypeError("created_at must contain timezone-aware timestamps")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("created_at must contain valid timestamps") from error
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    return timestamp.tz_convert(timezone.utc).to_pydatetime()


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _optional_real(value: object, *, name: str) -> float:
    if _is_missing(value):
        return np.nan
    return _finite_real(value, name=name)


def _unit_interval(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return numeric


def _optional_unit(value: object, *, name: str) -> float:
    if _is_missing(value):
        return np.nan
    return _unit_interval(value, name=name)


def _nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return numeric


def _strict_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a boolean")
    return bool(value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _parse_canonical_json(value: object, *, name: str) -> object:
    text = _identifier(value, name=name)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must contain valid JSON") from error
    try:
        canonical = _canonical_json(parsed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain canonical finite JSON") from error
    if text != canonical:
        raise ValueError(f"{name} must use canonical JSON serialization")
    return parsed


def _reason_values(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        try:
            parsed = json.loads(values)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            values = parsed
        else:
            values = (values,)
    try:
        normalized = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError("reason codes must be iterable") from error
    return tuple(
        sorted(
            {
                _identifier(_enum_value(value), name="reason code")
                for value in normalized
            }
        )
    )


def _reject_secret_like(value: object, *, name: str) -> None:
    if isinstance(value, str):
        if _SECRET_PATTERN.search(value):
            raise ValueError(f"secret-like values are forbidden in {name}")
        return
    if isinstance(value, pd.DataFrame):
        for column in value.columns:
            for item in value[column].tolist():
                _reject_secret_like(item, name=f"{name}.{column}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_secret_like(key, name=name)
            _reject_secret_like(item, name=name)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            _reject_secret_like(item, name=name)


def _serialized_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _distribution_config_hash(config: CurrentDistributionConfig) -> str:
    neutral_bands = [
        {
            "return_basis": return_basis,
            "horizon_months": horizon_months,
            "neutral_band": float(config.neutral_bands[(return_basis, horizon_months)]),
        }
        for return_basis in _RETURN_BASES
        for horizon_months in HORIZONS
    ]
    return _serialized_hash(
        {
            "draw_count": config.draw_count,
            "seed": config.seed,
            "residual_block_length": config.residual_block_length,
            "min_effective_samples": config.min_effective_samples,
            "neutral_bands": neutral_bands,
        }
    )


def _reconstruct_context(context: object) -> RunContext:
    if not isinstance(context, RunContext):
        raise TypeError("snapshot run_context must be a RunContext")
    try:
        return RunContext.model_validate(context.model_dump(mode="python"))
    except (TypeError, ValueError) as error:
        raise ValueError("snapshot RunContext provenance is inconsistent") from error


def _as_feature_input(feature: object) -> FeatureInput:
    if not isinstance(feature, CurrentFeature):
        raise TypeError("snapshot groups must contain CurrentFeature values")
    return FeatureInput(
        payload=feature.payload,
        provenance=feature.provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=feature.freshness.max_observation_age_days,
            max_visible_age_days=feature.freshness.max_visible_age_days,
        ),
        structural_drift=feature.structural_drift,
    )


def _reconstruct_snapshot(snapshot: object) -> CurrentFeatureSnapshot:
    if not isinstance(snapshot, CurrentFeatureSnapshot):
        raise TypeError("snapshot must be a CurrentFeatureSnapshot")
    context = _reconstruct_context(snapshot.run_context)
    try:
        rebuilt = CurrentFeatureSnapshot(
            as_of=snapshot.as_of,
            cycle_states=tuple(
                _as_feature_input(value) for value in snapshot.cycle_states
            ),
            channel_states=tuple(
                _as_feature_input(value) for value in snapshot.channel_states
            ),
            valuation_controls=tuple(
                _as_feature_input(value) for value in snapshot.valuation_controls
            ),
            earnings_controls=tuple(
                _as_feature_input(value) for value in snapshot.earnings_controls
            ),
            positioning_controls=tuple(
                _as_feature_input(value) for value in snapshot.positioning_controls
            ),
            liquidity_controls=tuple(
                _as_feature_input(value) for value in snapshot.liquidity_controls
            ),
            event_scenarios=tuple(
                _as_feature_input(value) for value in snapshot.event_scenarios
            ),
            historical_posterior=tuple(
                _as_feature_input(value) for value in snapshot.historical_posterior
            ),
            run_context=context,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("snapshot retained feature inputs are inconsistent") from error
    secret_surface: list[object] = [
        context.model_version,
        dict(context.quality_summary),
        dict(context.input_checksums),
    ]
    for feature in rebuilt.features:
        secret_surface.extend(
            [
                feature.feature_id,
                feature.entity_id,
                feature.payload.values,
                feature.provenance.source,
                feature.provenance.unit,
                feature.provenance.quality_status,
                feature.provenance.methodology,
                feature.provenance.vintage_caveat,
                feature.structural_drift.method,
                feature.structural_drift.baseline_id,
                feature.structural_drift.reason,
            ]
        )
    _reject_secret_like(secret_surface, name="snapshot")
    return rebuilt


def _reconstruct_distribution(distribution: object) -> CurrentDistributionResult:
    if not isinstance(distribution, CurrentDistributionResult):
        raise TypeError("distribution must be a CurrentDistributionResult")
    source_config = distribution.config
    if not isinstance(source_config, CurrentDistributionConfig):
        raise TypeError("distribution config must be CurrentDistributionConfig")
    config = CurrentDistributionConfig(
        draw_count=source_config.draw_count,
        seed=source_config.seed,
        residual_block_length=source_config.residual_block_length,
        min_effective_samples=source_config.min_effective_samples,
        neutral_bands=dict(source_config.neutral_bands),
    )
    try:
        rebuilt = CurrentDistributionResult(
            summary=distribution.summary,
            monthly_draws=distribution.monthly_draws,
            draws=distribution.draws,
            config=config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "distribution retained inputs or summary are inconsistent"
        ) from error
    _reject_secret_like(
        [rebuilt.summary, rebuilt.monthly_draws, rebuilt.draws],
        name="distribution",
    )
    return rebuilt


def _reconstruct_transferability(
    transferability: object,
) -> TransferabilityResult:
    if not isinstance(transferability, TransferabilityResult):
        raise TypeError("transferability must be a TransferabilityResult")
    source_config = transferability.config
    if not isinstance(source_config, TransferabilityConfig):
        raise TypeError("transferability config must be TransferabilityConfig")
    config = TransferabilityConfig(
        **{
            item.name: getattr(source_config, item.name)
            for item in dataclass_fields(TransferabilityConfig)
        }
    )
    nested_distribution = _reconstruct_distribution(transferability.distribution)
    try:
        rebuilt = TransferabilityResult(
            summary=transferability.summary,
            evidence=transferability.evidence,
            distribution=nested_distribution,
            config=config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "transferability retained inputs or summary are inconsistent"
        ) from error
    _reject_secret_like([rebuilt.summary, rebuilt.evidence], name="transferability")
    return rebuilt


def _reconstruct_weight_ranges(weight_ranges: object) -> WeightRangeResult:
    if not isinstance(weight_ranges, WeightRangeResult):
        raise TypeError("weight_ranges must be a WeightRangeResult")
    source_config = weight_ranges.config
    if not isinstance(source_config, WeightRangeConfig):
        raise TypeError("weight-range config must be WeightRangeConfig")
    config = WeightRangeConfig(
        **{
            item.name: getattr(source_config, item.name)
            for item in dataclass_fields(WeightRangeConfig)
        }
    )
    nested_distribution = _reconstruct_distribution(weight_ranges.distribution)
    nested_transferability = _reconstruct_transferability(weight_ranges.transferability)
    try:
        rebuilt = WeightRangeResult(
            summary=weight_ranges.summary,
            policy=weight_ranges.policy,
            distribution=nested_distribution,
            transferability=nested_transferability,
            config=config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "weight-range retained inputs or summary are inconsistent"
        ) from error
    _reject_secret_like([rebuilt.summary, rebuilt.policy], name="weight ranges")
    return rebuilt


def _assert_frame_equal(left: pd.DataFrame, right: pd.DataFrame, *, name: str) -> None:
    try:
        pd.testing.assert_frame_equal(
            left,
            right,
            check_dtype=True,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(f"{name} inputs do not align exactly") from error


def _assert_distribution_equal(
    left: CurrentDistributionResult,
    right: CurrentDistributionResult,
    *,
    name: str,
) -> None:
    _assert_frame_equal(left.summary, right.summary, name=f"{name} summary")
    _assert_frame_equal(
        left.monthly_draws,
        right.monthly_draws,
        name=f"{name} monthly draws",
    )
    _assert_frame_equal(left.draws, right.draws, name=f"{name} draws")
    if _distribution_config_hash(left.config) != _distribution_config_hash(
        right.config
    ):
        raise ValueError(f"{name} distribution configs do not align exactly")


def _assert_transferability_equal(
    left: TransferabilityResult,
    right: TransferabilityResult,
    *,
    name: str,
) -> None:
    _assert_frame_equal(left.summary, right.summary, name=f"{name} summary")
    _assert_frame_equal(left.evidence, right.evidence, name=f"{name} evidence")
    if left.config.config_hash != right.config.config_hash:
        raise ValueError(f"{name} configs do not align exactly")
    _assert_distribution_equal(
        left.distribution,
        right.distribution,
        name=f"{name} nested distribution",
    )


def _dimensions(values: pd.DataFrame) -> set[tuple[str, int]]:
    return {
        (str(asset_id), int(horizon_months))
        for asset_id, horizon_months in values[
            ["asset_id", "horizon_months"]
        ].itertuples(index=False, name=None)
    }


def _validate_alignment(
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
) -> None:
    _assert_distribution_equal(
        distribution,
        transferability.distribution,
        name="distribution and transferability",
    )
    _assert_distribution_equal(
        distribution,
        weight_ranges.distribution,
        name="distribution and weight ranges",
    )
    _assert_transferability_equal(
        transferability,
        weight_ranges.transferability,
        name="transferability and weight ranges",
    )

    distribution_summary = distribution.summary
    distribution_dimensions = _dimensions(distribution_summary)
    if _dimensions(transferability.summary) != distribution_dimensions:
        raise ValueError("transferability dimensions do not align with distribution")
    if _dimensions(weight_ranges.summary) != distribution_dimensions:
        raise ValueError("weight-range dimensions do not align with distribution")
    assets = set(distribution_summary["asset_id"])
    snapshot_assets = {
        feature.entity_id
        for feature in snapshot.features
        if feature.entity_id is not None
    }
    if snapshot_assets != assets:
        raise ValueError(
            "snapshot asset coverage must align exactly with mapping inputs"
        )

    expected = {
        "run_id": snapshot.provenance.run_id,
        "snapshot_as_of": snapshot.as_of,
        "snapshot_data_vintage": snapshot.provenance.data_vintage,
        "snapshot_model_version": snapshot.provenance.model_version,
        "snapshot_config_hash": snapshot.provenance.config_hash,
        "forecast_origin": snapshot.as_of,
    }
    for field_name, expected_value in expected.items():
        if not distribution_summary[field_name].eq(expected_value).all():
            raise ValueError(
                f"distribution {field_name} must align exactly with snapshot"
            )
    if distribution_summary["stage1_posterior_date"].gt(snapshot.as_of).any():
        raise ValueError("stage1 posterior provenance cannot follow as_of")
    if distribution_summary["stage2_posterior_date"].gt(snapshot.as_of).any():
        raise ValueError("stage2 posterior provenance cannot follow as_of")


def _validated_inputs(
    snapshot: object,
    distribution: object,
    transferability: object,
    weight_ranges: object,
) -> tuple[
    CurrentFeatureSnapshot,
    CurrentDistributionResult,
    TransferabilityResult,
    WeightRangeResult,
]:
    validated_snapshot = _reconstruct_snapshot(snapshot)
    validated_distribution = _reconstruct_distribution(distribution)
    validated_transferability = _reconstruct_transferability(transferability)
    validated_weight_ranges = _reconstruct_weight_ranges(weight_ranges)
    _validate_alignment(
        validated_snapshot,
        validated_distribution,
        validated_transferability,
        validated_weight_ranges,
    )
    return (
        validated_snapshot,
        validated_distribution,
        validated_transferability,
        validated_weight_ranges,
    )


def _normalize_influence(
    influence: object,
    *,
    dimensions: set[tuple[str, int]],
    as_of: date,
    expected_channels: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(influence, pd.DataFrame):
        raise TypeError("influence must be a pandas DataFrame")
    if influence.columns.has_duplicates:
        raise ValueError("influence columns must be unique")
    if tuple(influence.columns) != M3_INFLUENCE_COLUMNS:
        raise ValueError("influence columns do not match the strict public contract")
    if influence.empty:
        raise ValueError("M3 influence evidence cannot be empty")
    frame = influence.copy(deep=True)
    _reject_secret_like(frame, name="influence")
    frame["asset_id"] = [
        _identifier(value, name="influence asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _nonnegative_integer(value, name="influence horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError("influence horizons must use 3, 6, and 12 months")
    if frame.duplicated(
        ["asset_id", "horizon_months", "component_type", "component_id"]
    ).any():
        raise ValueError("influence component dimensions must be unique")
    if _dimensions(frame) != dimensions:
        raise ValueError("M3 influence coverage must match mapping inputs exactly")

    frame["component_type"] = [
        _identifier(value, name="influence component_type")
        for value in frame["component_type"].tolist()
    ]
    if not set(frame["component_type"]).issubset({"cycle", "channel"}):
        raise ValueError("influence component_type must be cycle or channel")
    frame["component_id"] = [
        _identifier(value, name="influence component_id")
        for value in frame["component_id"].tolist()
    ]
    frame["status"] = [
        _identifier(_enum_value(value), name="influence status")
        for value in frame["status"].tolist()
    ]
    if not set(frame["status"]).issubset(_INFLUENCE_STATUSES):
        raise ValueError("influence status must be available or unavailable")
    frame["evidence_level"] = [
        _identifier(_enum_value(value), name="influence evidence_level")
        for value in frame["evidence_level"].tolist()
    ]
    if not set(frame["evidence_level"]).issubset(_EVIDENCE_LEVELS):
        raise ValueError("influence evidence_level is invalid")
    frame["reason_code"] = [
        _identifier(_enum_value(value), name="influence reason_code")
        for value in frame["reason_code"].tolist()
    ]
    scores: list[float] = []
    for status_value, score_value, reason_code in zip(
        frame["status"].tolist(),
        frame["influence_score"].tolist(),
        frame["reason_code"].tolist(),
        strict=True,
    ):
        if status_value == "available":
            score = _finite_real(score_value, name="available influence_score")
            if not -1.0 <= score <= 1.0:
                raise ValueError("available influence_score must be in [-1, 1]")
            scores.append(score)
        else:
            if not _is_missing(score_value):
                raise ValueError("unavailable influence scores must be missing")
            if not reason_code or reason_code == "score_available":
                raise ValueError(
                    "unavailable influence scores require an explicit reason"
                )
            scores.append(np.nan)
    frame["influence_score"] = scores

    frame["source_stage"] = [
        _identifier(value, name="influence source_stage")
        for value in frame["source_stage"].tolist()
    ]
    if set(frame["source_stage"]) != {"m3_asset_attribution"}:
        raise ValueError(
            "influence source_stage must explicitly identify M3 asset attribution"
        )
    frame["source_run_id"] = [
        _identifier(value, name="influence source_run_id")
        for value in frame["source_run_id"].tolist()
    ]
    if any(
        RUN_ID_PATTERN.fullmatch(value) is None
        for value in frame["source_run_id"].tolist()
    ):
        raise ValueError("influence source_run_id is invalid")
    frame["source_date"] = [
        _date_value(value, name="influence source_date")
        for value in frame["source_date"].tolist()
    ]
    if any(value > as_of for value in frame["source_date"].tolist()):
        raise ValueError("influence source_date cannot be future-dated after as_of")
    for source_run_id, source_date in zip(
        frame["source_run_id"].tolist(),
        frame["source_date"].tolist(),
        strict=True,
    ):
        if date.fromisoformat(source_run_id[:10]) != source_date:
            raise ValueError(
                "influence source_run_id date must match source_date provenance"
            )
    frame["source_model_version"] = [
        _identifier(value, name="influence source_model_version")
        for value in frame["source_model_version"].tolist()
    ]
    frame["source_config_hash"] = [
        _valid_hash(value, name="influence source_config_hash")
        for value in frame["source_config_hash"].tolist()
    ]
    source_columns = (
        "source_stage",
        "source_run_id",
        "source_date",
        "source_model_version",
        "source_config_hash",
    )
    if any(frame[column].nunique(dropna=False) != 1 for column in source_columns):
        raise ValueError("M3 influence source provenance must be constant")

    for _, group in frame.groupby(["asset_id", "horizon_months"], sort=False):
        cycles = group.loc[group["component_type"].eq("cycle"), "component_id"]
        channels = group.loc[group["component_type"].eq("channel"), "component_id"]
        if len(cycles) != 7 or set(cycles) != set(_EXPECTED_CYCLES):
            raise ValueError(
                "M3 influence must contain exactly C1-C7 for every asset/horizon"
            )
        if len(channels) != len(expected_channels) or set(channels) != set(
            expected_channels
        ):
            raise ValueError(
                "M3 influence channel coverage must exactly match the complete "
                "snapshot channel universe for every asset/horizon"
            )

    frame["_component_order"] = frame["component_type"].map({"cycle": 0, "channel": 1})
    frame["_cycle_order"] = (
        frame["component_id"]
        .map({cycle_id: position for position, cycle_id in enumerate(_EXPECTED_CYCLES)})
        .fillna(100)
    )
    return (
        frame.sort_values(
            [
                "asset_id",
                "horizon_months",
                "_component_order",
                "_cycle_order",
                "component_id",
            ],
            kind="stable",
        )
        .drop(columns=["_component_order", "_cycle_order"])
        .reset_index(drop=True)
    )


def _json_influence_records(values: pd.DataFrame) -> str:
    records: list[dict[str, object]] = []
    for row in values.itertuples(index=False):
        records.append(
            {
                "asset_id": row.asset_id,
                "horizon_months": int(row.horizon_months),
                "component_type": row.component_type,
                "component_id": row.component_id,
                "influence_score": (
                    None
                    if _is_missing(row.influence_score)
                    else float(row.influence_score)
                ),
                "status": row.status,
                "evidence_level": row.evidence_level,
                "reason_code": row.reason_code,
                "source_stage": row.source_stage,
                "source_run_id": row.source_run_id,
                "source_date": row.source_date.isoformat(),
                "source_model_version": row.source_model_version,
                "source_config_hash": row.source_config_hash,
            }
        )
    return _canonical_json(records)


def _influence_summary(values: pd.DataFrame) -> dict[str, object]:
    statuses = values["status"].tolist()
    if all(status == "available" for status in statuses):
        aggregate_status = "available"
    elif all(status == "unavailable" for status in statuses):
        aggregate_status = "unavailable"
    else:
        aggregate_status = "partial"
    level_rank = {"low": 0, "medium": 1, "high": 2}
    minimum_level = min(
        (str(level) for level in values["evidence_level"].tolist()),
        key=level_rank.__getitem__,
    )
    if aggregate_status != "available":
        minimum_level = "low"
    return {
        "cycle_influence_json": _json_influence_records(
            values.loc[values["component_type"].eq("cycle")]
        ),
        "channel_influence_json": _json_influence_records(
            values.loc[values["component_type"].eq("channel")]
        ),
        "influence_status": aggregate_status,
        "influence_evidence_level": minimum_level,
        "influence_reason_codes": _canonical_json(
            list(_reason_values(values["reason_code"].tolist()))
        ),
        "influence_source_stage": values["source_stage"].iloc[0],
        "influence_run_id": values["source_run_id"].iloc[0],
        "influence_source_date": values["source_date"].iloc[0],
        "influence_model_version": values["source_model_version"].iloc[0],
        "influence_config_hash": values["source_config_hash"].iloc[0],
    }


def _feature_sort_key(feature: CurrentFeature) -> tuple[str, str, str]:
    return (
        feature.kind.value,
        feature.entity_id or "",
        feature.feature_id,
    )


def _freshness_summary(
    snapshot: CurrentFeatureSnapshot,
    *,
    asset_id: str,
) -> dict[str, object]:
    relevant = tuple(
        sorted(
            (
                feature
                for feature in snapshot.features
                if feature.entity_id is None or feature.entity_id == asset_id
            ),
            key=_feature_sort_key,
        )
    )
    stale = tuple(feature for feature in relevant if not feature.freshness.is_fresh)
    stale_records = [
        {
            "entity_id": feature.entity_id,
            "feature_id": feature.feature_id,
            "kind": feature.kind.value,
            "reasons": list(feature.freshness.reasons),
        }
        for feature in stale
    ]
    reason_codes = sorted(
        {
            f"{feature.kind.value}:{feature.feature_id}:{reason}"
            for feature in stale
            for reason in feature.freshness.reasons
        }
    )
    return {
        "freshness_status": "fresh" if not stale else "stale",
        "stale_feature_count": len(stale),
        "freshness_reason_codes": _canonical_json(reason_codes),
        "stale_feature_json": _canonical_json(stale_records),
        "contains_pseudo_vintage": any(
            feature.is_pseudo_vintage for feature in relevant
        ),
    }


def _unavailable_feature_caveats(
    snapshot: CurrentFeatureSnapshot,
    *,
    asset_id: str,
) -> set[str]:
    groups = (
        (snapshot.valuation_controls, "valuation_control_unavailable"),
        (snapshot.earnings_controls, "earnings_control_unavailable"),
        (snapshot.positioning_controls, "positioning_control_unavailable"),
        (snapshot.liquidity_controls, "liquidity_control_unavailable"),
        (snapshot.event_scenarios, "event_scenario_unavailable"),
    )
    caveats: set[str] = set()
    for features, caveat in groups:
        relevant = tuple(
            feature
            for feature in features
            if feature.entity_id is None or feature.entity_id == asset_id
        )
        if relevant and all(
            feature.payload.values.get("status") == "unavailable"
            for feature in relevant
        ):
            caveats.add(caveat)
    return caveats


def _basis_values(row: pd.Series, *, basis: str) -> dict[str, object]:
    return {
        f"{basis}_up_probability": row["up_probability"],
        f"{basis}_neutral_probability": row["neutral_probability"],
        f"{basis}_down_probability": row["down_probability"],
        f"{basis}_q10": row["q10"],
        f"{basis}_q25": row["q25"],
        f"{basis}_q50": row["q50"],
        f"{basis}_q75": row["q75"],
        f"{basis}_q90": row["q90"],
        f"{basis}_expected_return": row["expected_return"],
        f"{basis}_volatility": row["volatility"],
        f"{basis}_var95": row["var95"],
        f"{basis}_cvar95": row["cvar95"],
        f"{basis}_drawdown_q50": row["drawdown_q50"],
        f"{basis}_drawdown_q80": row["drawdown_q80"],
        f"{basis}_drawdown_q95": row["drawdown_q95"],
        f"{basis}_distribution_status": _enum_value(row["status"]),
        f"{basis}_effective_samples": int(row["effective_samples"]),
        f"{basis}_calibration_version": row["calibration_version"],
    }


def _evidence_level(
    *,
    publish_range: bool,
    transferability_status: str,
    influence_status: str,
    influence_evidence_level: str,
) -> str:
    if (
        publish_range
        and transferability_status == MappingStatus.FORMAL.value
        and influence_status == "available"
        and influence_evidence_level == EvidenceLevel.HIGH.value
    ):
        return EvidenceLevel.HIGH.value
    if (
        publish_range
        and transferability_status
        in {MappingStatus.FORMAL.value, MappingStatus.CONDITIONAL.value}
        and influence_status != "unavailable"
    ):
        return EvidenceLevel.MEDIUM.value
    return EvidenceLevel.LOW.value


def _build_mapping_frame(
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
    influence: pd.DataFrame,
) -> pd.DataFrame:
    distribution_summary = distribution.summary.set_index(
        ["asset_id", "horizon_months", "return_basis"]
    )
    transferability_summary = transferability.summary.set_index(
        ["asset_id", "horizon_months"]
    )
    weight_summary = weight_ranges.summary.set_index(["asset_id", "horizon_months"])
    distribution_dimensions = sorted(
        _dimensions(distribution.summary),
        key=lambda item: (item[0], item[1]),
    )
    distribution_hash = _distribution_config_hash(distribution.config)
    records: list[dict[str, object]] = []

    for asset_id, horizon_months in distribution_dimensions:
        absolute = distribution_summary.loc[(asset_id, horizon_months, "absolute")]
        excess = distribution_summary.loc[(asset_id, horizon_months, "excess")]
        transfer = transferability_summary.loc[(asset_id, horizon_months)]
        weight = weight_summary.loc[(asset_id, horizon_months)]
        influence_rows = influence.loc[
            influence["asset_id"].eq(asset_id)
            & influence["horizon_months"].eq(horizon_months)
        ]
        influence_values = _influence_summary(influence_rows)
        freshness = _freshness_summary(snapshot, asset_id=asset_id)
        transferability_status = _enum_value(transfer["status"])
        source_range_status = _enum_value(weight["range_status"])
        distributions_available = (
            _enum_value(absolute["status"]) == "available"
            and _enum_value(excess["status"]) == "available"
        )
        source_range_available = (
            source_range_status == "available"
            and not _is_missing(weight["min_weight"])
            and not _is_missing(weight["max_weight"])
        )
        transferability_eligible = transferability_status in {
            MappingStatus.FORMAL.value,
            MappingStatus.CONDITIONAL.value,
        }
        publish_range = bool(
            distributions_available
            and source_range_available
            and transferability_eligible
            and freshness["freshness_status"] == "fresh"
        )

        range_reasons = set(_reason_values(weight["reason_codes"]))
        if publish_range:
            range_reasons.add("range_available")
        else:
            range_reasons.discard("range_available")
            if freshness["freshness_status"] == "stale":
                range_reasons.add("stale_current_features")
            if not distributions_available:
                range_reasons.add("distribution_unavailable")
            if not transferability_eligible:
                range_reasons.add("transferability_not_publishable")
            if not source_range_available:
                range_reasons.add("source_weight_range_unavailable")

        mapping_status = (
            MappingStatus.UNAVAILABLE.value
            if freshness["freshness_status"] == "stale" or not distributions_available
            else transferability_status
        )
        publication_status = (
            "live"
            if publish_range and influence_values["influence_status"] == "available"
            else "partial"
        )
        publication_reasons: set[str] = set()
        if publication_status == "live":
            publication_reasons.add("mapping_live")
        else:
            publication_reasons.add("partial_publication")
            if not publish_range:
                publication_reasons.add("weight_range_not_published")
            if freshness["freshness_status"] == "stale":
                publication_reasons.add("stale_current_features")
            if influence_values["influence_status"] != "available":
                publication_reasons.add("influence_incomplete")
            if not distributions_available:
                publication_reasons.add("distribution_unavailable")
            if not transferability_eligible:
                publication_reasons.add("transferability_not_publishable")

        caveats = set(_reason_values(weight["caveat_codes"]))
        caveats.update(_unavailable_feature_caveats(snapshot, asset_id=asset_id))
        if transferability_status == MappingStatus.CONDITIONAL.value:
            caveats.add("conditional_transferability")
        if freshness["freshness_status"] == "stale":
            caveats.add("stale_current_features")
        if bool(freshness["contains_pseudo_vintage"]):
            caveats.add("pseudo_vintage_evidence")
        if influence_values["influence_status"] != "available":
            caveats.add("influence_incomplete")
        if publication_status == "partial":
            caveats.add("partial_publication")

        evidence_level = _evidence_level(
            publish_range=publish_range,
            transferability_status=transferability_status,
            influence_status=str(influence_values["influence_status"]),
            influence_evidence_level=str(influence_values["influence_evidence_level"]),
        )
        record = {
            "asset_id": asset_id,
            "horizon_months": horizon_months,
            **_basis_values(absolute, basis="absolute"),
            **_basis_values(excess, basis="excess"),
            **influence_values,
            "published_min_weight": (
                float(weight["min_weight"]) if publish_range else np.nan
            ),
            "published_max_weight": (
                float(weight["max_weight"]) if publish_range else np.nan
            ),
            "neutral_min_weight": float(weight["neutral_min_weight"]),
            "neutral_max_weight": float(weight["neutral_max_weight"]),
            "source_range_status": source_range_status,
            "range_status": "available" if publish_range else "unavailable",
            "range_scope": weight["scope"],
            "range_reason_codes": _canonical_json(sorted(range_reasons)),
            "range_caveat_codes": _canonical_json(
                list(_reason_values(weight["caveat_codes"]))
            ),
            "policy_date": weight["policy_date"],
            "policy_version": weight["policy_version"],
            "policy_hash": weight["policy_hash"],
            "transferability_score": transfer["overall_score"],
            "transferability_status": transferability_status,
            **{
                f"{dimension}_score": transfer[f"{dimension}_score"]
                for dimension in TRANSFERABILITY_DIMENSIONS
            },
            "baseline_gate_passed": bool(transfer["baseline_gate_passed"]),
            "formal_hard_gates_passed": bool(transfer["formal_hard_gates_passed"]),
            "transferability_reason_codes": _canonical_json(
                list(_reason_values(transfer["reason_codes"]))
            ),
            "transferability_evidence_date": transfer["evidence_date"],
            "transferability_validation_end": transfer["validation_end"],
            "mapping_status": mapping_status,
            "evidence_level": evidence_level,
            "freshness_status": freshness["freshness_status"],
            "stale_feature_count": freshness["stale_feature_count"],
            "freshness_reason_codes": freshness["freshness_reason_codes"],
            "stale_feature_json": freshness["stale_feature_json"],
            "publication_status": publication_status,
            "publication_reason_codes": _canonical_json(sorted(publication_reasons)),
            "caveat_codes": _canonical_json(sorted(caveats)),
            "run_id": snapshot.provenance.run_id,
            "as_of": snapshot.as_of,
            "data_vintage": snapshot.provenance.data_vintage,
            "model_version": snapshot.provenance.model_version,
            "snapshot_config_hash": snapshot.provenance.config_hash,
            "distribution_config_hash": distribution_hash,
            "transferability_config_hash": transferability.config.config_hash,
            "weight_config_hash": weight_ranges.config.config_hash,
            "stage1_posterior_date": absolute["stage1_posterior_date"],
            "stage2_posterior_date": absolute["stage2_posterior_date"],
            "forecast_origin": absolute["forecast_origin"],
            "created_at": snapshot.provenance.created_at,
        }
        records.append(record)
    return pd.DataFrame(records, columns=ASSET_MAPPING_CURRENT_COLUMNS)


def _validate_basis(row: pd.Series, *, basis: str) -> None:
    status = row[f"{basis}_distribution_status"]
    metric_columns = [f"{basis}_{suffix}" for suffix in _METRIC_SUFFIXES]
    if status == "unavailable":
        if not all(_is_missing(row[column]) for column in metric_columns):
            raise ValueError(
                f"unavailable {basis} distribution metrics must be missing"
            )
        return
    probabilities = np.asarray(
        [
            row[f"{basis}_up_probability"],
            row[f"{basis}_neutral_probability"],
            row[f"{basis}_down_probability"],
        ],
        dtype="float64",
    )
    if (
        not np.isfinite(probabilities).all()
        or bool(((probabilities < 0.0) | (probabilities > 1.0)).any())
        or not np.isclose(probabilities.sum(), 1.0, atol=1e-10, rtol=1e-10)
    ):
        raise ValueError(f"{basis} calibrated probabilities are invalid")
    quantiles = [row[f"{basis}_q{quantile}"] for quantile in (10, 25, 50, 75, 90)]
    if not all(np.isfinite(quantiles)) or quantiles != sorted(quantiles):
        raise ValueError(f"{basis} quantiles must be finite and ordered")
    _finite_real(row[f"{basis}_expected_return"], name=f"{basis} expected return")
    volatility = _finite_real(row[f"{basis}_volatility"], name=f"{basis} volatility")
    var95 = _finite_real(row[f"{basis}_var95"], name=f"{basis} var95")
    cvar95 = _finite_real(row[f"{basis}_cvar95"], name=f"{basis} cvar95")
    if volatility < 0.0 or var95 < 0.0 or cvar95 < var95:
        raise ValueError(f"{basis} risk metrics are invalid")
    drawdowns = [
        _unit_interval(row[f"{basis}_drawdown_q{quantile}"], name="drawdown")
        for quantile in (50, 80, 95)
    ]
    if drawdowns != sorted(drawdowns):
        raise ValueError(f"{basis} drawdown quantiles must be ordered")


def _validate_influence_entries(row: pd.Series, *, column: str, kind: str) -> None:
    parsed = _parse_canonical_json(row[column], name=column)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"{column} must contain a non-empty JSON array")
    expected_keys = set(M3_INFLUENCE_COLUMNS)
    component_ids: list[str] = []
    statuses: list[str] = []
    levels: list[str] = []
    reasons: list[str] = []
    for entry in parsed:
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise ValueError(f"{column} entries do not match the influence contract")
        if entry["asset_id"] != row["asset_id"]:
            raise ValueError("influence JSON asset provenance is inconsistent")
        if int(entry["horizon_months"]) != row["horizon_months"]:
            raise ValueError("influence JSON horizon provenance is inconsistent")
        if entry["component_type"] != kind:
            raise ValueError("influence JSON component_type is inconsistent")
        component_ids.append(
            _identifier(entry["component_id"], name="influence component_id")
        )
        status = _identifier(entry["status"], name="influence status")
        level = _identifier(entry["evidence_level"], name="influence evidence")
        reason = _identifier(entry["reason_code"], name="influence reason")
        if status not in _INFLUENCE_STATUSES or level not in _EVIDENCE_LEVELS:
            raise ValueError("influence JSON status or evidence is invalid")
        score = entry["influence_score"]
        if status == "available":
            numeric = _finite_real(score, name="influence score")
            if not -1.0 <= numeric <= 1.0:
                raise ValueError("available influence score must be in [-1, 1]")
        elif score is not None:
            raise ValueError("unavailable influence JSON scores must be null")
        if entry["source_stage"] != "m3_asset_attribution":
            raise ValueError("influence JSON must identify M3 attribution")
        if entry["source_run_id"] != row["influence_run_id"]:
            raise ValueError("influence JSON run provenance is inconsistent")
        if entry["source_date"] != row["influence_source_date"].isoformat():
            raise ValueError("influence JSON date provenance is inconsistent")
        if entry["source_model_version"] != row["influence_model_version"]:
            raise ValueError("influence JSON model provenance is inconsistent")
        if entry["source_config_hash"] != row["influence_config_hash"]:
            raise ValueError("influence JSON config provenance is inconsistent")
        statuses.append(status)
        levels.append(level)
        reasons.append(reason)
    if kind == "cycle" and component_ids != list(_EXPECTED_CYCLES):
        raise ValueError("cycle influence JSON must contain ordered C1-C7")
    if kind == "channel" and component_ids != sorted(component_ids):
        raise ValueError("channel influence JSON must be deterministically ordered")


def _normalize_product_frame(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("asset mapping product must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError("asset mapping product columns must be unique")
    if tuple(values.columns) != ASSET_MAPPING_CURRENT_COLUMNS:
        raise ValueError("asset mapping product columns do not match the stable schema")
    if values.empty:
        raise ValueError("asset mapping product cannot be empty")
    frame = values.copy(deep=True)
    _reject_secret_like(frame, name="asset mapping product")
    frame["asset_id"] = [
        _identifier(value, name="asset_id") for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _nonnegative_integer(value, name="horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("asset/horizon dimensions must be unique")
    for _, asset_rows in frame.groupby("asset_id", sort=False):
        if set(asset_rows["horizon_months"]) != set(HORIZONS) or len(asset_rows) != 3:
            raise ValueError("every asset must retain exact 3/6/12 horizon coverage")

    for column in _STRING_COLUMNS:
        if column in _JSON_COLUMNS:
            continue
        frame[column] = [
            _identifier(_enum_value(value), name=column)
            for value in frame[column].tolist()
        ]
    for column in _FLOAT_COLUMNS:
        frame[column] = [
            _optional_real(value, name=column) for value in frame[column].tolist()
        ]
    for column in (
        "absolute_effective_samples",
        "excess_effective_samples",
        "stale_feature_count",
    ):
        frame[column] = [
            _nonnegative_integer(value, name=column) for value in frame[column].tolist()
        ]
    for column in ("baseline_gate_passed", "formal_hard_gates_passed"):
        frame[column] = [
            _strict_bool(value, name=column) for value in frame[column].tolist()
        ]
    for column in _DATE_COLUMNS:
        frame[column] = [
            _date_value(
                value,
                name=column,
                allow_missing=column
                in {
                    "transferability_evidence_date",
                    "transferability_validation_end",
                },
            )
            for value in frame[column].tolist()
        ]
    frame["created_at"] = [_created_at(value) for value in frame["created_at"]]

    if not set(frame["absolute_distribution_status"]).issubset(
        _DISTRIBUTION_STATUSES
    ) or not set(frame["excess_distribution_status"]).issubset(_DISTRIBUTION_STATUSES):
        raise ValueError("distribution status is invalid")
    if not set(frame["source_range_status"]).issubset(_RANGE_STATUSES):
        raise ValueError("source range status is invalid")
    if not set(frame["range_status"]).issubset(_RANGE_STATUSES):
        raise ValueError("range status is invalid")
    if not set(frame["transferability_status"]).issubset(_MAPPING_STATUSES):
        raise ValueError("transferability status is invalid")
    if not set(frame["mapping_status"]).issubset(_MAPPING_STATUSES):
        raise ValueError("mapping status is invalid")
    if not set(frame["evidence_level"]).issubset(_EVIDENCE_LEVELS):
        raise ValueError("evidence level is invalid")
    if not set(frame["influence_evidence_level"]).issubset(_EVIDENCE_LEVELS):
        raise ValueError("influence evidence level is invalid")
    if not set(frame["influence_status"]).issubset(_INFLUENCE_AGGREGATE_STATUSES):
        raise ValueError("influence aggregate status is invalid")
    if not set(frame["freshness_status"]).issubset(_FRESHNESS_STATUSES):
        raise ValueError("freshness status is invalid")
    if not set(frame["publication_status"]).issubset(_PUBLICATION_STATUSES):
        raise ValueError("publication status is invalid")

    for column in _JSON_COLUMNS:
        frame[column] = [
            _canonical_json(_parse_canonical_json(value, name=column))
            for value in frame[column].tolist()
        ]

    for row_index, row in frame.iterrows():
        for basis in _RETURN_BASES:
            _validate_basis(row, basis=basis)
        _validate_influence_entries(row, column="cycle_influence_json", kind="cycle")
        _validate_influence_entries(
            row,
            column="channel_influence_json",
            kind="channel",
        )
        cycle_entries = json.loads(row["cycle_influence_json"])
        channel_entries = json.loads(row["channel_influence_json"])
        influence_entries = cycle_entries + channel_entries
        statuses = [entry["status"] for entry in influence_entries]
        expected_influence_status = (
            "available"
            if all(status == "available" for status in statuses)
            else "unavailable"
            if all(status == "unavailable" for status in statuses)
            else "partial"
        )
        if row["influence_status"] != expected_influence_status:
            raise ValueError("influence aggregate status is inconsistent")
        expected_influence_reasons = sorted(
            {entry["reason_code"] for entry in influence_entries}
        )
        if json.loads(row["influence_reason_codes"]) != expected_influence_reasons:
            raise ValueError("influence reason codes are inconsistent")

        neutral_min = _unit_interval(
            row["neutral_min_weight"], name="neutral_min_weight"
        )
        neutral_max = _unit_interval(
            row["neutral_max_weight"], name="neutral_max_weight"
        )
        if neutral_min >= neutral_max:
            raise ValueError("neutral weight range must be strictly ordered")
        if row["range_status"] == "available":
            minimum = _unit_interval(
                row["published_min_weight"], name="published_min_weight"
            )
            maximum = _unit_interval(
                row["published_max_weight"], name="published_max_weight"
            )
            if minimum >= maximum:
                raise ValueError("published weight range must be strictly ordered")
            if row["source_range_status"] != "available":
                raise ValueError("published range requires an available source range")
            if row["freshness_status"] != "fresh":
                raise ValueError("published range requires fresh snapshot evidence")
            if row["transferability_status"] not in {
                MappingStatus.FORMAL.value,
                MappingStatus.CONDITIONAL.value,
            }:
                raise ValueError(
                    "published range requires formal or conditional transferability"
                )
            if (
                row["absolute_distribution_status"] != "available"
                or row["excess_distribution_status"] != "available"
            ):
                raise ValueError("published range requires available distributions")
        elif not _is_missing(row["published_min_weight"]) or not _is_missing(
            row["published_max_weight"]
        ):
            raise ValueError("unavailable range must not publish numeric weights")

        stale_records = json.loads(row["stale_feature_json"])
        if not isinstance(stale_records, list):
            raise ValueError("stale_feature_json must contain an array")
        if row["stale_feature_count"] != len(stale_records):
            raise ValueError("stale feature count is inconsistent")
        expected_freshness = "fresh" if not stale_records else "stale"
        if row["freshness_status"] != expected_freshness:
            raise ValueError("freshness status is inconsistent")
        distributions_available = (
            row["absolute_distribution_status"] == "available"
            and row["excess_distribution_status"] == "available"
        )
        expected_mapping_status = (
            MappingStatus.UNAVAILABLE.value
            if expected_freshness == "stale" or not distributions_available
            else row["transferability_status"]
        )
        if row["mapping_status"] != expected_mapping_status:
            raise ValueError(
                "mapping status must mirror freshness, distribution availability, "
                "and transferability status"
            )

        expected_publication = (
            "live"
            if row["range_status"] == "available"
            and row["influence_status"] == "available"
            else "partial"
        )
        if row["publication_status"] != expected_publication:
            raise ValueError("publication status is inconsistent")
        expected_evidence = _evidence_level(
            publish_range=row["range_status"] == "available",
            transferability_status=row["transferability_status"],
            influence_status=row["influence_status"],
            influence_evidence_level=row["influence_evidence_level"],
        )
        if row["evidence_level"] != expected_evidence:
            raise ValueError("mapping evidence level is inconsistent")
        if row["policy_date"] > row["as_of"]:
            raise ValueError("policy_date cannot follow as_of")
        if row["influence_source_date"] > row["as_of"]:
            raise ValueError("influence source_date cannot follow as_of")
        if row["data_vintage"] > row["as_of"]:
            raise ValueError("data_vintage cannot follow as_of")
        if (
            row["stage1_posterior_date"] > row["as_of"]
            or row["stage2_posterior_date"] > row["as_of"]
        ):
            raise ValueError("posterior provenance cannot follow as_of")
        if row["forecast_origin"] != row["as_of"]:
            raise ValueError("forecast_origin must equal as_of")
        for column in (
            "snapshot_config_hash",
            "distribution_config_hash",
            "transferability_config_hash",
            "weight_config_hash",
            "policy_hash",
            "influence_config_hash",
        ):
            _valid_hash(row[column], name=column)
        if RUN_ID_PATTERN.fullmatch(row["run_id"]) is None:
            raise ValueError("run_id provenance is invalid")
        if RUN_ID_PATTERN.fullmatch(row["influence_run_id"]) is None:
            raise ValueError("influence run_id provenance is invalid")
        frame.loc[row_index, "mapping_status"] = row["mapping_status"]

    if any(frame[column].nunique(dropna=False) != 1 for column in _PROVENANCE_COLUMNS):
        raise ValueError("product source and run provenance must be constant")
    return frame.sort_values(
        ["asset_id", "horizon_months"],
        kind="stable",
    ).reset_index(drop=True)


@dataclass(frozen=True)
class AssetMappingCurrentProduct:
    """Detached one-row-per-asset/horizon current mapping frame."""

    mapping: pd.DataFrame
    _context: RunContext | None = field(default=None, repr=False, compare=False)
    _validation_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _VALIDATED_PRODUCT_TOKEN:
            raise TypeError(
                "AssetMappingCurrentProduct must be created by "
                "build_asset_mapping_current"
            )
        if not isinstance(self._context, RunContext):
            raise TypeError("validated product context must be a RunContext")
        normalized = _normalize_product_frame(object.__getattribute__(self, "mapping"))
        if not normalized["run_id"].eq(self._context.run_id).all():
            raise ValueError("product run_id does not match builder context")
        if not normalized["as_of"].eq(self._context.as_of).all():
            raise ValueError("product as_of does not match builder context")
        object.__setattr__(self, "mapping", _copy_frame(normalized))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    def __iter__(self) -> Iterator[pd.DataFrame]:
        yield self.mapping


def build_asset_mapping_current(
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
    influence: pd.DataFrame,
) -> AssetMappingCurrentProduct:
    """Build the stable current mapping from reconstructed governed inputs."""

    (
        validated_snapshot,
        validated_distribution,
        validated_transferability,
        validated_weight_ranges,
    ) = _validated_inputs(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
    )
    dimensions = _dimensions(validated_distribution.summary)
    validated_influence = _normalize_influence(
        influence,
        dimensions=dimensions,
        as_of=validated_snapshot.as_of,
        expected_channels=tuple(
            feature.feature_id for feature in validated_snapshot.channel_states
        ),
    )
    mapping = _build_mapping_frame(
        validated_snapshot,
        validated_distribution,
        validated_transferability,
        validated_weight_ranges,
        validated_influence,
    )
    product = AssetMappingCurrentProduct(
        mapping=mapping,
        _context=validated_snapshot.run_context,
        _validation_token=_VALIDATED_PRODUCT_TOKEN,
    )
    validate_asset_mapping_current(product)
    return product


def _product_frame(product: object) -> tuple[pd.DataFrame, RunContext | None]:
    if isinstance(product, AssetMappingCurrentProduct):
        return product.mapping, object.__getattribute__(product, "_context")
    if isinstance(product, pd.DataFrame):
        return product.copy(deep=True), None
    raise TypeError("product must be AssetMappingCurrentProduct or pandas DataFrame")


def validate_asset_mapping_current(
    product: object,
    *,
    snapshot: CurrentFeatureSnapshot | None = None,
    distribution: CurrentDistributionResult | None = None,
    transferability: TransferabilityResult | None = None,
    weight_ranges: WeightRangeResult | None = None,
    influence: pd.DataFrame | None = None,
) -> None:
    """Validate schema, semantics, provenance, and optional governed sources."""

    frame, product_context = _product_frame(product)
    normalized = _normalize_product_frame(frame)
    supplied_sources = (
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    if any(value is not None for value in supplied_sources) and not all(
        value is not None for value in supplied_sources
    ):
        raise ValueError("all governed source inputs must be supplied together")
    if all(value is not None for value in supplied_sources):
        (
            validated_snapshot,
            validated_distribution,
            validated_transferability,
            validated_weight_ranges,
        ) = _validated_inputs(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
        )
        validated_influence = _normalize_influence(
            influence,
            dimensions=_dimensions(validated_distribution.summary),
            as_of=validated_snapshot.as_of,
            expected_channels=tuple(
                feature.feature_id for feature in validated_snapshot.channel_states
            ),
        )
        expected = _normalize_product_frame(
            _build_mapping_frame(
                validated_snapshot,
                validated_distribution,
                validated_transferability,
                validated_weight_ranges,
                validated_influence,
            )
        )
        try:
            pd.testing.assert_frame_equal(
                normalized,
                expected,
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as error:
            raise ValueError(
                "asset mapping product is inconsistent with governed inputs"
            ) from error
        if (
            product_context is not None
            and product_context != validated_snapshot.run_context
        ):
            raise ValueError("product context does not match governed snapshot context")


def _arrow_table(values: pd.DataFrame) -> pa.Table:
    arrays = [
        pa.array(values[field.name].tolist(), type=field.type, from_pandas=True)
        for field in ASSET_MAPPING_CURRENT_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=ASSET_MAPPING_CURRENT_SCHEMA)


def _directory_identity_from_stat(value: os.stat_result) -> tuple[int, int]:
    return (value.st_dev, value.st_ino)


def _directory_identity_from_fd(descriptor: int, *, label: str) -> tuple[int, int]:
    descriptor_stat = os.fstat(descriptor)
    if not stat.S_ISDIR(descriptor_stat.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return _directory_identity_from_stat(descriptor_stat)


def _open_real_directory_path(
    directory: Path,
    *,
    label: str,
) -> tuple[Path, int, tuple[int, int]]:
    absolute = Path(os.path.abspath(os.fspath(directory)))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            try:
                child_stat = os.stat(
                    component,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ValueError(f"{label} must be a real directory") from error
            if stat.S_ISLNK(child_stat.st_mode):
                raise ValueError(f"{label} cannot contain symlink components")
            if not stat.S_ISDIR(child_stat.st_mode):
                raise ValueError(f"{label} must contain only real directories")
            try:
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                raise ValueError(
                    f"{label} must contain only real non-symlink directories"
                ) from error
            try:
                child_identity = _directory_identity_from_fd(
                    child_descriptor,
                    label=label,
                )
                if child_identity != _directory_identity_from_stat(child_stat):
                    raise ValueError(f"{label} changed while it was being opened")
            except BaseException:
                os.close(child_descriptor)
                raise
            os.close(descriptor)
            descriptor = child_descriptor
        identity = _directory_identity_from_fd(descriptor, label=label)
        return absolute, descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _assert_directory_path_identity(
    directory: Path,
    *,
    expected_identity: tuple[int, int],
) -> None:
    _, descriptor, identity = _open_real_directory_path(
        directory,
        label="run_dir",
    )
    try:
        if identity != expected_identity:
            raise ValueError("run_dir was replaced during publication")
    finally:
        os.close(descriptor)


def _open_run_directory(
    run_dir: Path,
    context: RunContext,
) -> tuple[Path, int, tuple[int, int]]:
    directory, descriptor, identity = _open_real_directory_path(
        run_dir,
        label="run_dir",
    )
    if directory.name != context.run_id:
        os.close(descriptor)
        raise ValueError("run_dir name must match product run_id")
    return directory, descriptor, identity


def _require_target_absent_at(directory_descriptor: int, name: str) -> None:
    try:
        target_stat = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if stat.S_ISLNK(target_stat.st_mode):
        raise ValueError("asset mapping target cannot be a symlink")
    if not stat.S_ISREG(target_stat.st_mode):
        raise ValueError("asset mapping target must be absent or a regular file")
    raise FileExistsError(f"refuse accidental overwrite of {name}")


def _temporary_file_at(directory_descriptor: int) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(128):
        name = f".{ASSET_MAPPING_CURRENT_FILENAME}.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(
                name,
                flags,
                0o600,
                dir_fd=directory_descriptor,
            )
        except FileExistsError:
            continue
        return name, descriptor
    raise FileExistsError("unable to allocate a unique temporary product")


def _read_schema_at(
    directory_descriptor: int,
    name: str,
    *,
    expected_identity: tuple[int, int],
) -> pa.Schema:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise ValueError("product entry is missing, invalid, or a symlink") from error
    descriptor_open = True
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ValueError("product entry must be a regular file")
        if _directory_identity_from_stat(opened_stat) != expected_identity:
            raise ValueError("product entry identity changed")
        with os.fdopen(descriptor, "rb") as source:
            descriptor_open = False
            return pq.read_schema(source)
    finally:
        if descriptor_open:
            os.close(descriptor)


def _write_temporary_table_at(
    directory_descriptor: int,
    values: pd.DataFrame,
) -> tuple[str, tuple[int, int]]:
    temporary_name, file_descriptor = _temporary_file_at(directory_descriptor)
    descriptor_open = True
    try:
        with os.fdopen(file_descriptor, "wb") as product_file:
            descriptor_open = False
            pq.write_table(
                _arrow_table(values),
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
            product_file.flush()
            os.fsync(product_file.fileno())
        temporary_stat = os.stat(
            temporary_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(temporary_stat.st_mode):
            raise ValueError("temporary product must be a regular file")
        identity = _directory_identity_from_stat(temporary_stat)
        if (
            _read_schema_at(
                directory_descriptor,
                temporary_name,
                expected_identity=identity,
            )
            != ASSET_MAPPING_CURRENT_SCHEMA
        ):
            raise ValueError("persisted asset mapping schema mismatch")
        return temporary_name, identity
    except BaseException:
        if descriptor_open:
            os.close(file_descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_descriptor)
        except FileNotFoundError:
            pass
        raise


def _unlink_if_identity_at(
    directory_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    try:
        entry_stat = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if _directory_identity_from_stat(entry_stat) == expected_identity:
        os.unlink(name, dir_fd=directory_descriptor)


def _validate_published_table_at(
    directory_descriptor: int,
    target_name: str,
    expected_identity: tuple[int, int],
) -> None:
    if (
        _read_schema_at(
            directory_descriptor,
            target_name,
            expected_identity=expected_identity,
        )
        != ASSET_MAPPING_CURRENT_SCHEMA
    ):
        raise ValueError("published asset mapping schema mismatch")


def _validate_final_publication_at(
    directory_descriptor: int,
    directory: Path,
    directory_identity: tuple[int, int],
    target_name: str,
    target_identity: tuple[int, int],
) -> None:
    _assert_directory_path_identity(
        directory,
        expected_identity=directory_identity,
    )
    _validate_published_table_at(
        directory_descriptor,
        target_name,
        target_identity,
    )


def _publish_temporary_table_at(
    directory_descriptor: int,
    directory: Path,
    directory_identity: tuple[int, int],
    temporary_name: str,
    temporary_identity: tuple[int, int],
    target_name: str,
) -> None:
    linked = False
    try:
        _assert_directory_path_identity(
            directory,
            expected_identity=directory_identity,
        )
        os.link(
            temporary_name,
            target_name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        linked = True
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite or concurrent publish of {target_name}"
        ) from error
    try:
        _validate_published_table_at(
            directory_descriptor,
            target_name,
            temporary_identity,
        )
        _assert_directory_path_identity(
            directory,
            expected_identity=directory_identity,
        )
        os.unlink(temporary_name, dir_fd=directory_descriptor)
        os.fsync(directory_descriptor)
        _validate_final_publication_at(
            directory_descriptor,
            directory,
            directory_identity,
            target_name,
            temporary_identity,
        )
    except BaseException:
        if linked:
            _unlink_if_identity_at(
                directory_descriptor,
                target_name,
                temporary_identity,
            )
            os.fsync(directory_descriptor)
        raise


def write_asset_mapping_current(
    run_dir: Path,
    product: object,
) -> Path:
    """Atomically and exclusively write a builder-validated mapping product."""

    if not isinstance(product, AssetMappingCurrentProduct):
        raise TypeError(
            "write_asset_mapping_current requires a product returned by "
            "build_asset_mapping_current"
        )
    context = object.__getattribute__(product, "_context")
    if not isinstance(context, RunContext):
        raise TypeError("product context is invalid")
    validate_asset_mapping_current(product)
    directory, directory_descriptor, directory_identity = _open_run_directory(
        Path(run_dir),
        context,
    )
    target_name = ASSET_MAPPING_CURRENT_FILENAME
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    try:
        _require_target_absent_at(directory_descriptor, target_name)
        temporary_name, temporary_identity = _write_temporary_table_at(
            directory_descriptor,
            product.mapping,
        )
        _publish_temporary_table_at(
            directory_descriptor,
            directory,
            directory_identity,
            temporary_name,
            temporary_identity,
            target_name,
        )
        published_identity = temporary_identity
        temporary_name = None
        _validate_final_publication_at(
            directory_descriptor,
            directory,
            directory_identity,
            target_name,
            published_identity,
        )
    except BaseException:
        if published_identity is not None:
            _unlink_if_identity_at(
                directory_descriptor,
                target_name,
                published_identity,
            )
            os.fsync(directory_descriptor)
        if temporary_name is not None and temporary_identity is not None:
            _unlink_if_identity_at(
                directory_descriptor,
                temporary_name,
                temporary_identity,
            )
        raise
    finally:
        os.close(directory_descriptor)
    return directory / target_name


def build_and_write_asset_mapping_current(
    run_dir: Path,
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
    influence: pd.DataFrame,
) -> Path:
    """Build, validate, and exclusively write the current mapping product."""

    product = build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    return write_asset_mapping_current(run_dir, product)


__all__ = [
    "ASSET_MAPPING_CURRENT_COLUMNS",
    "ASSET_MAPPING_CURRENT_FILENAME",
    "ASSET_MAPPING_CURRENT_SCHEMA",
    "M3_INFLUENCE_COLUMNS",
    "AssetMappingCurrentProduct",
    "build_and_write_asset_mapping_current",
    "build_asset_mapping_current",
    "validate_asset_mapping_current",
    "write_asset_mapping_current",
]
