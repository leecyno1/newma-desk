"""Stable governed ``asset_mapping_future`` product."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
from numbers import Integral, Real
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.forecast.assets import AssetForecastResult
from seven_cycle_platform.forecast.evaluation import (
    MAPPING_MANIFEST_METADATA_KEY,
    MAPPING_REFERENCE_FILENAME,
    MAPPING_REFERENCE_SCHEMA_VERSION,
)
from seven_cycle_platform.forecast.scenarios import STANDARD_SCENARIO_IDS
from seven_cycle_platform.products.asset_mapping_current import (
    AssetMappingCurrentProduct,
    validate_asset_mapping_current,
)
from seven_cycle_platform.security.redaction import redact_secrets
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.storage.manifest import sha256_file
from seven_cycle_platform.storage.run_context import canonical_json_bytes
from seven_cycle_platform.types import MappingStatus


ASSET_MAPPING_FUTURE_FILENAME = "asset_mapping_future.parquet"
ASSET_MAPPING_FUTURE_PRODUCT = "asset_mapping_future"
CONTRIBUTION_AGGREGATION_METHOD = "geometric_shared_prefix_v1"
CONTRIBUTION_CONSERVATION_TOLERANCE = 1e-10
CONTRIBUTION_COMPONENT_CONTRACT_SCHEMA_VERSION = 1
CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS = (
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
ASSET_MAPPING_FUTURE_SCHEMA = pa.schema(
    [
        pa.field("scenario_id", pa.string()),
        pa.field("future_date", pa.date32()),
        pa.field("asset_id", pa.string()),
        pa.field("horizon_months", pa.int32()),
        pa.field("status", pa.string()),
        pa.field("unavailable_reason", pa.string()),
        pa.field("absolute_median", pa.float64()),
        pa.field("absolute_interval50_lower", pa.float64()),
        pa.field("absolute_interval50_upper", pa.float64()),
        pa.field("absolute_interval80_lower", pa.float64()),
        pa.field("absolute_interval80_upper", pa.float64()),
        pa.field("absolute_expected_return", pa.float64()),
        pa.field("absolute_volatility", pa.float64()),
        pa.field("absolute_var95", pa.float64()),
        pa.field("absolute_cvar95", pa.float64()),
        pa.field("absolute_drawdown_q50", pa.float64()),
        pa.field("absolute_drawdown_q80", pa.float64()),
        pa.field("absolute_drawdown_q95", pa.float64()),
        pa.field("excess_median", pa.float64()),
        pa.field("excess_interval50_lower", pa.float64()),
        pa.field("excess_interval50_upper", pa.float64()),
        pa.field("excess_interval80_lower", pa.float64()),
        pa.field("excess_interval80_upper", pa.float64()),
        pa.field("excess_expected_return", pa.float64()),
        pa.field("excess_volatility", pa.float64()),
        pa.field("excess_var95", pa.float64()),
        pa.field("excess_cvar95", pa.float64()),
        pa.field("excess_drawdown_q50", pa.float64()),
        pa.field("excess_drawdown_q80", pa.float64()),
        pa.field("excess_drawdown_q95", pa.float64()),
        pa.field("interval50_nominal_coverage", pa.float64()),
        pa.field("interval80_nominal_coverage", pa.float64()),
        pa.field("effective_samples", pa.int32()),
        pa.field("contribution_draw_count", pa.int32()),
        pa.field("contribution_component_contract_hash", pa.string()),
        pa.field("baseline_component_contribution_json", pa.string()),
        pa.field("channel_contribution_json", pa.string()),
        pa.field("scenario_contribution_json", pa.string()),
        pa.field("contribution_aggregation_method", pa.string()),
        pa.field("contribution_conservation_max_abs_error", pa.float64()),
        pa.field("contribution_conservation_passed", pa.bool_()),
        pa.field("transferability_status", pa.string()),
        pa.field("mapping_status", pa.string()),
        pa.field("mapping_status_reason_codes", pa.string()),
        pa.field("evidence_level", pa.string()),
        pa.field("freshness_status", pa.string()),
        pa.field("freshness_reason_codes", pa.string()),
        pa.field("baseline_gate_passed", pa.bool_()),
        pa.field("oos_increment_score", pa.float64()),
        pa.field("transferability_score", pa.float64()),
        pa.field("transferability_evidence_date", pa.date32()),
        pa.field("transferability_validation_end", pa.date32()),
        pa.field("current_mapping_run_id", pa.string()),
        pa.field("current_mapping_model_version", pa.string()),
        pa.field("current_mapping_snapshot_config_hash", pa.string()),
        pa.field("current_mapping_distribution_config_hash", pa.string()),
        pa.field("current_mapping_transferability_config_hash", pa.string()),
        pa.field("scenario_version", pa.string()),
        pa.field("catalog_version", pa.string()),
        pa.field("scenario_config_hash", pa.string()),
        pa.field("asset_forecast_model_version", pa.string()),
        pa.field("asset_forecast_config_hash", pa.string()),
        pa.field("channel_forecast_model_version", pa.string()),
        pa.field("channel_forecast_config_hash", pa.string()),
        pa.field("channel_registry_hash", pa.string()),
        pa.field("cycle_forecast_model_version", pa.string()),
        pa.field("cycle_forecast_config_hash", pa.string()),
        pa.field("cycle_registry_hash", pa.string()),
        pa.field("stage2_posterior_date", pa.date32()),
        pa.field("stage2_estimation_method", pa.string()),
        pa.field("forecast_origin", pa.date32()),
        pa.field("source_data_vintage", pa.date32()),
        pa.field("feature_visible_date", pa.date32()),
        pa.field("feature_generated_date", pa.date32()),
        pa.field("feature_vintage_date", pa.date32()),
        pa.field("model_provenance", pa.string()),
        pa.field("data_provenance", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)
ASSET_MAPPING_FUTURE_COLUMNS = tuple(ASSET_MAPPING_FUTURE_SCHEMA.names)

_VALIDATED_PRODUCT_TOKEN = object()
_RESULT_FIELDS = frozenset({"mapping"})
_HORIZONS = (3, 6, 12)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAPPING_STATUSES = frozenset(member.value for member in MappingStatus)
_METRIC_SUFFIXES = (
    "median",
    "interval50_lower",
    "interval50_upper",
    "interval80_lower",
    "interval80_upper",
    "expected_return",
    "volatility",
    "var95",
    "cvar95",
    "drawdown_q50",
    "drawdown_q80",
    "drawdown_q95",
)
_METRIC_COLUMNS = tuple(
    f"{basis}_{suffix}"
    for basis in ("absolute", "excess")
    for suffix in _METRIC_SUFFIXES
)
_CONTRIBUTION_FIELDS = frozenset(
    {
        "aggregation_method",
        "component_id",
        "component_type",
        "contribution_kind",
        "draw_count",
        "expected_contribution",
        "interval50_lower",
        "interval50_upper",
        "interval80_lower",
        "interval80_upper",
        "median",
        "scenario_id",
    }
)
_BASELINE_COMPONENT_TYPES = frozenset(
    {
        "intercept",
        "benchmark",
        "channel",
        "valuation",
        "positioning",
        "control",
        "interaction",
        "event",
        "residual",
    }
)
_CURRENT_MAPPING_CARRY_COLUMNS = (
    "transferability_status",
    "evidence_level",
    "freshness_status",
    "freshness_reason_codes",
    "baseline_gate_passed",
    "oos_increment_score",
    "transferability_score",
    "transferability_evidence_date",
    "transferability_validation_end",
    "run_id",
    "model_version",
    "snapshot_config_hash",
    "distribution_config_hash",
    "transferability_config_hash",
)
_SOURCE_PROVENANCE_COLUMNS = (
    "transferability_status",
    "evidence_level",
    "freshness_status",
    "freshness_reason_codes",
    "baseline_gate_passed",
    "oos_increment_score",
    "transferability_score",
    "transferability_evidence_date",
    "transferability_validation_end",
    "current_mapping_run_id",
    "current_mapping_model_version",
    "current_mapping_snapshot_config_hash",
    "current_mapping_distribution_config_hash",
    "current_mapping_transferability_config_hash",
)


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


def _context(value: object) -> RunContext:
    if not isinstance(value, RunContext):
        raise TypeError("context must be a RunContext")
    return value


def _text(value: object, *, name: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if redact_secrets(normalized) != normalized:
        raise ValueError(f"{name} cannot contain secret-like material")
    return normalized


def _date_value(value: object, *, name: str, allow_none: bool = False) -> date | None:
    if value is None or pd.isna(value):
        if allow_none:
            return None
        raise ValueError(f"{name} cannot be missing")
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.normalize().date()


def _integer(
    value: object,
    *,
    name: str,
    minimum: int = 0,
    allow_none: bool = False,
) -> int | None:
    if value is None or pd.isna(value):
        if allow_none:
            return None
        raise ValueError(f"{name} cannot be missing")
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be an integer")
    normalized = int(value)
    if normalized < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return normalized


def _real(
    value: object,
    *,
    name: str,
    allow_none: bool = False,
) -> float | None:
    if value is None or pd.isna(value):
        if allow_none:
            return None
        raise ValueError(f"{name} cannot be missing")
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    normalized = float(value)
    if not np.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    return normalized


def _boolean(value: object, *, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be boolean")
    return bool(value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalize_component_contract_keys(
    values: object,
    *,
    name: str,
    allowed_types: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        raise TypeError(f"{name} must be a sequence of component keys")
    normalized: list[tuple[str, str]] = []
    for index, value in enumerate(values):
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise TypeError(
                f"{name}[{index}] must be a component_type/component_id key"
            )
        component_type = _text(value[0], name=f"{name}[{index}].component_type")
        component_id = _text(value[1], name=f"{name}[{index}].component_id")
        if component_type not in allowed_types:
            raise ValueError(f"{name}[{index}] component_type is invalid")
        normalized.append((component_type, component_id))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must contain unique component keys")
    return tuple(sorted(normalized))


def compute_contribution_component_contract_hash(
    *,
    asset_id: object,
    scenario_id: object,
    horizon_months: object,
    baseline_keys: object,
    scenario_keys: object,
    source_identity: Mapping[str, object],
) -> str:
    """Hash row-bound governed Task 26 component key contracts."""

    if not isinstance(source_identity, Mapping) or set(source_identity) != set(
        CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
    ):
        raise ValueError("source_identity does not match the component contract")
    normalized_baseline = _normalize_component_contract_keys(
        baseline_keys,
        name="baseline_keys",
        allowed_types=_BASELINE_COMPONENT_TYPES,
    )
    normalized_scenario = _normalize_component_contract_keys(
        scenario_keys,
        name="scenario_keys",
        allowed_types=frozenset({"scenario_shock"}),
    )
    payload = {
        "schema_version": CONTRIBUTION_COMPONENT_CONTRACT_SCHEMA_VERSION,
        "asset_id": _text(asset_id, name="asset_id"),
        "scenario_id": _text(scenario_id, name="scenario_id"),
        "horizon_months": _integer(
            horizon_months,
            name="horizon_months",
            minimum=1,
        ),
        "baseline_component_keys": [list(key) for key in normalized_baseline],
        "scenario_component_keys": [list(key) for key in normalized_scenario],
        "source_identity": {
            column: _text(source_identity[column], name=column)
            for column in CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
        },
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _parse_canonical_json(value: object, *, name: str) -> object:
    raw = _text(value, name=name)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must contain valid JSON") from error
    if raw != _canonical_json(parsed):
        raise ValueError(f"{name} must contain canonical JSON")
    return parsed


def mapping_manifest_metadata(mapping_id: str) -> dict[str, object]:
    """Return the exact Task 27 manifest metadata for this product."""

    normalized_id = _text(mapping_id, name="mapping_id")
    return {
        "schema_version": MAPPING_REFERENCE_SCHEMA_VERSION,
        "mapping_product": ASSET_MAPPING_FUTURE_PRODUCT,
        "mapping_id": normalized_id,
        "artifact_filename": ASSET_MAPPING_FUTURE_FILENAME,
    }


def _validate_contribution_json(
    value: object,
    *,
    name: str,
    scenario_id: str,
    kind: str,
    draw_count: int,
) -> tuple[str, list[dict[str, object]]]:
    parsed = _parse_canonical_json(value, name=name)
    if not isinstance(parsed, list):
        raise ValueError(f"{name} must contain a JSON array")
    normalized_entries: list[dict[str, object]] = []
    component_keys: list[tuple[str, str]] = []
    for entry in parsed:
        if not isinstance(entry, dict) or set(entry) != _CONTRIBUTION_FIELDS:
            raise ValueError(f"{name} entries do not match the contribution contract")
        if entry["contribution_kind"] != kind:
            raise ValueError("baseline and scenario contributions must remain separate")
        if entry["scenario_id"] != scenario_id:
            raise ValueError("contribution scenario provenance is inconsistent")
        if entry["aggregation_method"] != CONTRIBUTION_AGGREGATION_METHOD:
            raise ValueError("contribution aggregation method is invalid")
        if _integer(entry["draw_count"], name="contribution draw_count") != draw_count:
            raise ValueError("contribution draw_count is inconsistent")
        component_type = _text(entry["component_type"], name="component_type")
        component_id = _text(entry["component_id"], name="component_id")
        if kind == "baseline_component":
            if component_type not in _BASELINE_COMPONENT_TYPES:
                raise ValueError("baseline contribution component_type is invalid")
        elif component_type != "scenario_shock":
            raise ValueError("scenario contribution must use scenario_shock type")
        component_keys.append((component_type, component_id))
        values = [
            _real(entry[column], name=f"contribution {column}")
            for column in (
                "interval80_lower",
                "interval50_lower",
                "median",
                "interval50_upper",
                "interval80_upper",
            )
        ]
        if values != sorted(values):
            raise ValueError("contribution intervals must be ordered")
        _real(entry["expected_contribution"], name="expected_contribution")
        normalized_entries.append(dict(entry))
    if len(component_keys) != len(set(component_keys)):
        raise ValueError("contribution components must be unique")
    if component_keys != sorted(component_keys):
        raise ValueError("contribution components must be deterministically ordered")
    return _canonical_json(parsed), normalized_entries


def _validate_metric_block(row: pd.Series, *, basis: str) -> None:
    ordered = [
        _real(row[f"{basis}_{column}"], name=f"{basis}_{column}")
        for column in (
            "interval80_lower",
            "interval50_lower",
            "median",
            "interval50_upper",
            "interval80_upper",
        )
    ]
    if ordered != sorted(ordered):
        raise ValueError(f"{basis} intervals must be ordered around the median")
    _real(row[f"{basis}_expected_return"], name=f"{basis}_expected_return")
    volatility = _real(row[f"{basis}_volatility"], name=f"{basis}_volatility")
    var95 = _real(row[f"{basis}_var95"], name=f"{basis}_var95")
    cvar95 = _real(row[f"{basis}_cvar95"], name=f"{basis}_cvar95")
    if volatility < 0.0 or var95 < 0.0 or cvar95 < var95:
        raise ValueError(f"{basis} risk metrics are invalid")
    drawdowns = [
        _real(row[f"{basis}_drawdown_q{quantile}"], name="drawdown")
        for quantile in (50, 80, 95)
    ]
    if drawdowns != sorted(drawdowns) or drawdowns[0] < 0.0:
        raise ValueError(f"{basis} drawdown quantiles are invalid")


def _normalize_frame(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("asset mapping future product must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError("asset mapping future columns must be unique")
    if tuple(values.columns) != ASSET_MAPPING_FUTURE_COLUMNS:
        raise ValueError("asset mapping future columns do not match the stable schema")
    if values.empty:
        raise ValueError("asset mapping future product cannot be empty")
    frame = values.copy(deep=True)
    serialized = frame.to_json(date_format="iso")
    if redact_secrets(serialized) != serialized:
        raise ValueError("asset mapping future cannot contain secret-like material")

    for column in (
        "scenario_id",
        "asset_id",
        "status",
        "transferability_status",
        "mapping_status",
        "evidence_level",
        "freshness_status",
        "current_mapping_run_id",
        "current_mapping_model_version",
        "scenario_version",
        "catalog_version",
        "asset_forecast_model_version",
        "channel_forecast_model_version",
        "cycle_forecast_model_version",
        "stage2_estimation_method",
        "model_provenance",
        "data_provenance",
        "run_id",
        "model_version",
    ):
        frame[column] = [_text(value, name=column) for value in frame[column]]
    frame["unavailable_reason"] = [
        _text(value, name="unavailable_reason", allow_none=True)
        for value in frame["unavailable_reason"]
    ]
    for column in (
        "future_date",
        "transferability_evidence_date",
        "transferability_validation_end",
        "stage2_posterior_date",
        "forecast_origin",
        "source_data_vintage",
        "feature_visible_date",
        "feature_generated_date",
        "feature_vintage_date",
        "as_of",
        "data_vintage",
    ):
        allow_none = column in {
            "transferability_evidence_date",
            "transferability_validation_end",
            "feature_visible_date",
            "feature_generated_date",
            "feature_vintage_date",
        }
        frame[column] = [
            _date_value(value, name=column, allow_none=allow_none)
            for value in frame[column]
        ]
    frame["horizon_months"] = [
        _integer(value, name="horizon_months", minimum=1)
        for value in frame["horizon_months"]
    ]
    if set(frame["scenario_id"]) != set(STANDARD_SCENARIO_IDS):
        raise ValueError("future Mapping must retain all six standard scenarios")
    if not set(frame["horizon_months"]).issubset(_HORIZONS):
        raise ValueError("future Mapping horizons must be approved 3/6/12 months")
    if frame.duplicated(["scenario_id", "future_date", "asset_id"]).any():
        raise ValueError("scenario/future_date/asset dimensions must be unique")
    for asset_id, asset_rows in frame.groupby("asset_id", sort=False):
        expected = {
            (scenario_id, horizon)
            for scenario_id in STANDARD_SCENARIO_IDS
            for horizon in _HORIZONS
        }
        actual = set(
            zip(
                asset_rows["scenario_id"],
                asset_rows["horizon_months"],
                strict=True,
            )
        )
        if actual != expected:
            raise ValueError(
                f"asset {asset_id} must retain exact six-scenario 3/6/12 coverage"
            )

    for row_index, row in frame.iterrows():
        expected_date = (
            pd.Timestamp(row["as_of"]) + pd.offsets.MonthEnd(int(row["horizon_months"]))
        ).date()
        if (
            row["future_date"] != expected_date
            or row["forecast_origin"] != row["as_of"]
        ):
            raise ValueError("future_date and forecast_origin must align with horizon")
        if row["status"] not in {"available", "unavailable"}:
            raise ValueError("forecast status must be available or unavailable")
        if row["transferability_status"] not in _MAPPING_STATUSES:
            raise ValueError("transferability_status is invalid")
        if row["mapping_status"] not in _MAPPING_STATUSES:
            raise ValueError("mapping_status is invalid")
        if row["freshness_status"] not in {"fresh", "stale"}:
            raise ValueError("freshness_status is invalid")
        if row["evidence_level"] not in {"high", "medium", "low"}:
            raise ValueError("evidence_level is invalid")
        effective_samples = _integer(row["effective_samples"], name="effective_samples")
        draw_count = _integer(
            row["contribution_draw_count"], name="contribution_draw_count"
        )
        if row["status"] == "available":
            if row["unavailable_reason"] is not None:
                raise ValueError("available forecast cannot carry unavailable_reason")
            for basis in ("absolute", "excess"):
                _validate_metric_block(row, basis=basis)
            if effective_samples < 1 or draw_count < 1:
                raise ValueError("available forecast requires retained draws")
            if not np.isclose(
                _real(
                    row["interval50_nominal_coverage"],
                    name="interval50_nominal_coverage",
                ),
                0.5,
            ) or not np.isclose(
                _real(
                    row["interval80_nominal_coverage"],
                    name="interval80_nominal_coverage",
                ),
                0.8,
            ):
                raise ValueError("interval coverage metadata must be 50% and 80%")
        else:
            if row["unavailable_reason"] is None:
                raise ValueError("unavailable forecast requires a reason")
            if any(not pd.isna(row[column]) for column in _METRIC_COLUMNS):
                raise ValueError("unavailable rows cannot fabricate forecast numbers")
            if effective_samples != 0 or draw_count != 0:
                raise ValueError("unavailable rows cannot retain fabricated draws")
            if row["mapping_status"] != MappingStatus.UNAVAILABLE.value:
                raise ValueError("unavailable forecast requires unavailable Mapping")

        baseline_json, baseline_entries = _validate_contribution_json(
            row["baseline_component_contribution_json"],
            name="baseline_component_contribution_json",
            scenario_id=row["scenario_id"],
            kind="baseline_component",
            draw_count=draw_count,
        )
        channel_json, channel_entries = _validate_contribution_json(
            row["channel_contribution_json"],
            name="channel_contribution_json",
            scenario_id=row["scenario_id"],
            kind="baseline_component",
            draw_count=draw_count,
        )
        scenario_json, scenario_entries = _validate_contribution_json(
            row["scenario_contribution_json"],
            name="scenario_contribution_json",
            scenario_id=row["scenario_id"],
            kind="scenario_shock",
            draw_count=draw_count,
        )
        frame.loc[row_index, "baseline_component_contribution_json"] = baseline_json
        frame.loc[row_index, "channel_contribution_json"] = channel_json
        frame.loc[row_index, "scenario_contribution_json"] = scenario_json
        expected_channels = [
            entry for entry in baseline_entries if entry["component_type"] == "channel"
        ]
        if channel_entries != expected_channels:
            raise ValueError(
                "channel contributions must equal the baseline channel subset"
            )
        if row["scenario_id"] == "baseline" and scenario_entries:
            raise ValueError("baseline cannot contain scenario contributions")
        if row["contribution_aggregation_method"] != CONTRIBUTION_AGGREGATION_METHOD:
            raise ValueError("contribution aggregation method is invalid")
        conservation_passed = _boolean(
            row["contribution_conservation_passed"],
            name="contribution_conservation_passed",
        )
        if row["status"] == "available":
            if not baseline_entries:
                raise ValueError("available forecast requires baseline components")
            expected_sum = sum(
                float(entry["expected_contribution"])
                for entry in baseline_entries + scenario_entries
            )
            expected_error = abs(
                expected_sum
                - _real(
                    row["absolute_expected_return"],
                    name="absolute_expected_return",
                )
            )
            error = _real(
                row["contribution_conservation_max_abs_error"],
                name="contribution_conservation_max_abs_error",
            )
            if (
                error < 0.0
                or error > CONTRIBUTION_CONSERVATION_TOLERANCE
                or expected_error > CONTRIBUTION_CONSERVATION_TOLERANCE
                or error + CONTRIBUTION_CONSERVATION_TOLERANCE < expected_error
                or not conservation_passed
            ):
                raise ValueError(
                    "public contribution conservation expected values do not reconcile"
                )
        elif (
            baseline_entries
            or channel_entries
            or scenario_entries
            or not pd.isna(row["contribution_conservation_max_abs_error"])
            or conservation_passed
        ):
            raise ValueError(
                "unavailable forecast must expose empty contribution surfaces"
            )

        reasons = _parse_canonical_json(
            row["mapping_status_reason_codes"], name="mapping_status_reason_codes"
        )
        freshness_reasons = _parse_canonical_json(
            row["freshness_reason_codes"], name="freshness_reason_codes"
        )
        if not isinstance(reasons, list) or not all(
            isinstance(reason, str) and reason for reason in reasons
        ):
            raise ValueError("mapping status reason codes are invalid")
        if not isinstance(freshness_reasons, list) or not all(
            isinstance(reason, str) and reason for reason in freshness_reasons
        ):
            raise ValueError("freshness reason codes are invalid")
        frame.loc[row_index, "mapping_status_reason_codes"] = _canonical_json(reasons)
        frame.loc[row_index, "freshness_reason_codes"] = _canonical_json(
            freshness_reasons
        )
        baseline_passed = _boolean(
            row["baseline_gate_passed"], name="baseline_gate_passed"
        )
        if row["freshness_status"] == "stale" and row["mapping_status"] != (
            MappingStatus.UNAVAILABLE.value
        ):
            raise ValueError("stale current Mapping must downgrade to unavailable")
        if not baseline_passed and row["mapping_status"] not in {
            MappingStatus.RETROSPECTIVE_ONLY.value,
            MappingStatus.UNAVAILABLE.value,
        }:
            raise ValueError(
                "baseline failure must downgrade Mapping to retrospective_only"
            )
        if row["transferability_status"] == MappingStatus.RETROSPECTIVE_ONLY.value and (
            row["mapping_status"]
            not in {
                MappingStatus.RETROSPECTIVE_ONLY.value,
                MappingStatus.UNAVAILABLE.value,
            }
        ):
            raise ValueError("non-transferable Mapping must remain retrospective_only")
        if row["transferability_status"] == MappingStatus.UNAVAILABLE.value and (
            row["mapping_status"] != MappingStatus.UNAVAILABLE.value
        ):
            raise ValueError("upstream unavailable Mapping must remain unavailable")
        if row["mapping_status"] in {
            MappingStatus.FORMAL.value,
            MappingStatus.CONDITIONAL.value,
        } and (
            not baseline_passed
            or row["freshness_status"] != "fresh"
            or row["mapping_status"] != row["transferability_status"]
        ):
            raise ValueError("published future Mapping status is not transferable")

        for column in (
            "oos_increment_score",
            "transferability_score",
        ):
            _real(row[column], name=column, allow_none=True)
        for column in (
            "current_mapping_snapshot_config_hash",
            "current_mapping_distribution_config_hash",
            "current_mapping_transferability_config_hash",
            "scenario_config_hash",
            "asset_forecast_config_hash",
            "channel_forecast_config_hash",
            "channel_registry_hash",
            "cycle_forecast_config_hash",
            "cycle_registry_hash",
            "contribution_component_contract_hash",
            "config_hash",
        ):
            value = _text(row[column], name=column)
            if _HASH_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{column} must be a lowercase SHA-256 digest")
        expected_component_contract_hash = compute_contribution_component_contract_hash(
            asset_id=row["asset_id"],
            scenario_id=row["scenario_id"],
            horizon_months=row["horizon_months"],
            baseline_keys=tuple(
                (str(entry["component_type"]), str(entry["component_id"]))
                for entry in baseline_entries
            ),
            scenario_keys=tuple(
                (str(entry["component_type"]), str(entry["component_id"]))
                for entry in scenario_entries
            ),
            source_identity={
                column: row[column]
                for column in CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
            },
        )
        if (
            row["contribution_component_contract_hash"]
            != expected_component_contract_hash
        ):
            raise ValueError(
                "contribution component contract fingerprint does not match JSON keys"
            )
        frame.loc[row_index, "contribution_component_contract_hash"] = (
            expected_component_contract_hash
        )

    for (_, horizon), rows in frame.groupby(["asset_id", "horizon_months"], sort=False):
        for column in _SOURCE_PROVENANCE_COLUMNS:
            if rows[column].nunique(dropna=False) != 1:
                raise ValueError(
                    f"scenario rows cannot mix current Mapping provenance: {column}"
                )
    if frame["scenario_config_hash"].nunique(dropna=False) != 1:
        raise ValueError("standard scenarios must share one governed catalog")
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    return frame.sort_values(
        ["scenario_id", "future_date", "asset_id"], kind="stable"
    ).reset_index(drop=True)


def _validate_provenance(frame: pd.DataFrame, context: RunContext) -> None:
    expected = {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": pd.Timestamp(context.created_at),
    }
    for column, value in expected.items():
        if not frame[column].eq(value).all():
            raise ValueError(f"{column} provenance does not match RunContext")


def _rebuild_asset_result(value: object) -> AssetForecastResult:
    if not isinstance(value, AssetForecastResult):
        raise TypeError("forecasts must contain only AssetForecastResult values")
    return AssetForecastResult(
        summary=value.summary,
        monthly_draws=value.monthly_draws,
        draws=value.draws,
        components=value.components,
        channel_paths=value.channel_paths,
        forecast_input=value.forecast_input,
        config=value.config,
    )


def _current_mapping_frame(value: object) -> pd.DataFrame:
    if isinstance(value, AssetMappingCurrentProduct):
        validate_asset_mapping_current(value)
        return value.mapping
    if isinstance(value, pd.DataFrame):
        validate_asset_mapping_current(value)
        return value.copy(deep=True)
    raise TypeError(
        "current_mapping must be AssetMappingCurrentProduct or its strict DataFrame"
    )


def _mapping_decision(
    current: pd.Series,
    *,
    forecast_available: bool,
) -> tuple[str, str]:
    reasons: list[str] = []
    if not forecast_available:
        reasons.append("upstream_asset_forecast_unavailable")
        return MappingStatus.UNAVAILABLE.value, _canonical_json(reasons)
    if current["freshness_status"] != "fresh":
        reasons.append("stale_current_mapping")
        return MappingStatus.UNAVAILABLE.value, _canonical_json(reasons)
    if (
        current["mapping_status"] == MappingStatus.UNAVAILABLE.value
        or current["transferability_status"] == MappingStatus.UNAVAILABLE.value
    ):
        reasons.append("upstream_mapping_unavailable")
        return MappingStatus.UNAVAILABLE.value, _canonical_json(reasons)
    if not bool(current["baseline_gate_passed"]):
        reasons.append("baseline_gate_failed")
        return MappingStatus.RETROSPECTIVE_ONLY.value, _canonical_json(reasons)
    if current["transferability_status"] == MappingStatus.RETROSPECTIVE_ONLY.value or (
        current["mapping_status"] == MappingStatus.RETROSPECTIVE_ONLY.value
    ):
        reasons.append("transferability_retrospective_only")
        return MappingStatus.RETROSPECTIVE_ONLY.value, _canonical_json(reasons)
    status = str(current["transferability_status"])
    if status not in {MappingStatus.FORMAL.value, MappingStatus.CONDITIONAL.value}:
        reasons.append("transferability_not_publishable")
        return MappingStatus.UNAVAILABLE.value, _canonical_json(reasons)
    reasons.append("stable_oos_increment")
    reasons.append(f"transferability_{status}")
    return status, _canonical_json(sorted(reasons))


def _suffix_factors(monthly_returns: np.ndarray) -> np.ndarray:
    factors = np.ones(len(monthly_returns), dtype="float64")
    running = 1.0
    for position in range(len(monthly_returns) - 1, -1, -1):
        factors[position] = running
        running *= 1.0 + monthly_returns[position]
    return factors


def _contribution_entry(
    component_type: str,
    component_id: str,
    values: np.ndarray,
    *,
    scenario_id: str,
    kind: str,
) -> dict[str, object]:
    q10, q25, q50, q75, q90 = np.quantile(
        values,
        [0.10, 0.25, 0.50, 0.75, 0.90],
    )
    return {
        "aggregation_method": CONTRIBUTION_AGGREGATION_METHOD,
        "component_id": component_id,
        "component_type": component_type,
        "contribution_kind": kind,
        "draw_count": int(len(values)),
        "expected_contribution": float(np.mean(values)),
        "interval50_lower": float(q25),
        "interval50_upper": float(q75),
        "interval80_lower": float(q10),
        "interval80_upper": float(q90),
        "median": float(q50),
        "scenario_id": scenario_id,
    }


def _contribution_payload(
    result: AssetForecastResult,
    *,
    asset_id: str,
    horizon: int,
    available: bool,
    absolute_expected_return: float,
) -> tuple[
    str,
    str,
    str,
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
    int,
    float | None,
    bool,
]:
    scenario_id = result.forecast_input.scenario_id
    components = result.components
    components = components.loc[
        components["asset_id"].eq(asset_id) & components["month_number"].le(horizon)
    ]
    baseline_keys = tuple(
        sorted(
            {
                (str(row.source_type), str(row.component_id))
                for row in components.itertuples(index=False)
            }
        )
    )
    scenario_component_ids = sorted(
        components.loc[components["scenario_contribution"].ne(0.0), "component_id"]
        .drop_duplicates()
        .astype(str)
        .tolist()
    )
    scenario_keys = tuple(
        ("scenario_shock", component_id) for component_id in scenario_component_ids
    )
    if not available:
        if baseline_keys or scenario_keys:
            raise ValueError("unavailable Task 26 forecast retained component keys")
        return "[]", "[]", "[]", baseline_keys, scenario_keys, 0, None, False
    monthly = result.monthly_draws
    draws = result.draws
    monthly = monthly.loc[
        monthly["asset_id"].eq(asset_id) & monthly["month_number"].le(horizon)
    ]
    horizon_draws = draws.loc[
        draws["asset_id"].eq(asset_id) & draws["horizon_months"].eq(horizon)
    ].sort_values("draw_id", kind="stable")
    if horizon_draws.empty:
        raise ValueError("available asset forecast must retain horizon draws")
    if not components["cycle_contribution"].eq(0.0).all():
        raise ValueError("Task 26 scenario contributions cannot masquerade as cycles")
    non_channel_scenarios = components.loc[
        components["scenario_contribution"].ne(0.0)
        & ~components["component_type"].eq("channel")
    ]
    if not non_channel_scenarios.empty:
        raise ValueError(
            "scenario contributions cannot masquerade as non-channel terms"
        )
    if not baseline_keys or not {
        component_type for component_type, _ in baseline_keys
    }.issubset(_BASELINE_COMPONENT_TYPES):
        raise ValueError("Task 26 baseline component types are invalid")
    baseline_values = {key: [] for key in baseline_keys}
    scenario_values = {
        ("scenario_shock", component_id): [] for component_id in scenario_component_ids
    }
    path_max_error = 0.0
    for draw_row in horizon_draws.itertuples(index=False):
        draw_id = int(draw_row.draw_id)
        monthly_draw = monthly.loc[monthly["draw_id"].eq(draw_id)].sort_values(
            "month_number", kind="stable"
        )
        if list(monthly_draw["month_number"]) != list(range(1, horizon + 1)):
            raise ValueError("contributions must use one shared monthly prefix")
        returns = monthly_draw["asset_monthly_return"].to_numpy(dtype="float64")
        factors = _suffix_factors(returns)
        factor_by_month = dict(zip(monthly_draw["month_number"], factors, strict=True))
        draw_components = components.loc[components["draw_id"].eq(draw_id)].copy()
        draw_components["_suffix_factor"] = draw_components["month_number"].map(
            factor_by_month
        )
        suffix = draw_components["_suffix_factor"].to_numpy(dtype="float64")
        baseline_allocated = (
            draw_components["baseline_contribution"].to_numpy(dtype="float64") * suffix
        )
        scenario_allocated = (
            draw_components["scenario_contribution"].to_numpy(dtype="float64") * suffix
        )
        path_max_error = max(
            path_max_error,
            abs(
                float(baseline_allocated.sum() + scenario_allocated.sum())
                - float(draw_row.absolute_return)
            ),
        )
        for component_type, component_id in baseline_keys:
            rows = draw_components.loc[
                draw_components["source_type"].eq(component_type)
                & draw_components["component_id"].eq(component_id)
            ]
            baseline_values[(component_type, component_id)].append(
                float(
                    (
                        rows["baseline_contribution"].to_numpy(dtype="float64")
                        * rows["_suffix_factor"].to_numpy(dtype="float64")
                    ).sum()
                )
            )
        for component_id in scenario_component_ids:
            rows = draw_components.loc[
                draw_components["component_type"].eq("channel")
                & draw_components["component_id"].eq(component_id)
            ]
            scenario_values[("scenario_shock", component_id)].append(
                float(
                    (
                        rows["scenario_contribution"].to_numpy(dtype="float64")
                        * rows["_suffix_factor"].to_numpy(dtype="float64")
                    ).sum()
                )
            )
    baseline_entries = [
        _contribution_entry(
            component_type,
            component_id,
            np.asarray(
                baseline_values[(component_type, component_id)],
                dtype="float64",
            ),
            scenario_id=scenario_id,
            kind="baseline_component",
        )
        for component_type, component_id in baseline_keys
    ]
    channel_entries = [
        entry for entry in baseline_entries if entry["component_type"] == "channel"
    ]
    scenario_entries = [
        _contribution_entry(
            component_type,
            component_id,
            np.asarray(
                scenario_values[(component_type, component_id)],
                dtype="float64",
            ),
            scenario_id=scenario_id,
            kind="scenario_shock",
        )
        for component_type, component_id in sorted(scenario_values)
    ]
    public_expected_sum = sum(
        float(entry["expected_contribution"])
        for entry in baseline_entries + scenario_entries
    )
    expected_sum_error = abs(public_expected_sum - float(absolute_expected_return))
    max_error = max(path_max_error, expected_sum_error)
    tolerance = min(
        float(result.config.conservation_tolerance),
        CONTRIBUTION_CONSERVATION_TOLERANCE,
    )
    if max_error > tolerance:
        raise ValueError("retained Task 26 contribution paths do not conserve")
    return (
        _canonical_json(baseline_entries),
        _canonical_json(channel_entries),
        _canonical_json(scenario_entries),
        baseline_keys,
        scenario_keys,
        len(horizon_draws),
        max_error,
        True,
    )


def _summary_values(row: pd.Series, *, basis: str) -> dict[str, object]:
    return {
        f"{basis}_median": row["median"],
        f"{basis}_interval50_lower": row["interval50_lower"],
        f"{basis}_interval50_upper": row["interval50_upper"],
        f"{basis}_interval80_lower": row["interval80_lower"],
        f"{basis}_interval80_upper": row["interval80_upper"],
        f"{basis}_expected_return": row["expected_return"],
        f"{basis}_volatility": row["volatility"],
        f"{basis}_var95": row["var95"],
        f"{basis}_cvar95": row["cvar95"],
        f"{basis}_drawdown_q50": row["drawdown_q50"],
        f"{basis}_drawdown_q80": row["drawdown_q80"],
        f"{basis}_drawdown_q95": row["drawdown_q95"],
    }


@dataclass(frozen=True)
class AssetMappingFutureProduct:
    """Detached one-row-per-scenario/future-date/asset frame."""

    mapping: pd.DataFrame
    _context: RunContext | None = field(default=None, repr=False, compare=False)
    _forecasts: tuple[AssetForecastResult, ...] = field(
        default=(),
        repr=False,
        compare=False,
    )
    _current_mapping: pd.DataFrame | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _validation_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _VALIDATED_PRODUCT_TOKEN:
            raise TypeError(
                "AssetMappingFutureProduct must be created by "
                "build_asset_mapping_future"
            )
        context = _context(self._context)
        if set(result.forecast_input.scenario_id for result in self._forecasts) != set(
            STANDARD_SCENARIO_IDS
        ):
            raise ValueError("validated product must retain all six forecasts")
        if not isinstance(self._current_mapping, pd.DataFrame):
            raise TypeError("validated product must retain current Mapping")
        normalized = _normalize_frame(object.__getattribute__(self, "mapping"))
        _validate_provenance(normalized, context)
        object.__setattr__(self, "mapping", normalized.copy(deep=True))
        object.__setattr__(
            self, "_current_mapping", self._current_mapping.copy(deep=True)
        )

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    def __iter__(self) -> Iterator[pd.DataFrame]:
        yield self.mapping

    @property
    def frame(self) -> pd.DataFrame:
        return self.mapping


def build_asset_mapping_future(
    forecasts: Sequence[AssetForecastResult],
    current_mapping: object,
    *,
    context: RunContext,
) -> AssetMappingFutureProduct:
    """Build future Mapping from governed scenario draws and current Mapping."""

    run_context = _context(context)
    if isinstance(forecasts, (str, bytes, bytearray)):
        raise TypeError("forecasts must be a sequence of AssetForecastResult values")
    rebuilt = tuple(_rebuild_asset_result(value) for value in tuple(forecasts))
    if len(rebuilt) != len(STANDARD_SCENARIO_IDS):
        raise ValueError("forecasts must contain exactly the six standard scenarios")
    scenario_ids = tuple(result.forecast_input.scenario_id for result in rebuilt)
    if set(scenario_ids) != set(STANDARD_SCENARIO_IDS) or len(set(scenario_ids)) != len(
        scenario_ids
    ):
        raise ValueError("forecasts must contain isolated standard scenarios")
    by_scenario = {result.forecast_input.scenario_id: result for result in rebuilt}
    ordered_results = tuple(by_scenario[scenario] for scenario in STANDARD_SCENARIO_IDS)
    baseline = ordered_results[0]
    if tuple(baseline.config.horizons) != _HORIZONS:
        raise ValueError("Task 28 requires exact 3/6/12 asset forecast horizons")
    catalog_hash = baseline.forecast_input.scenario_catalog.config_hash
    for result in ordered_results:
        if result.forecast_input.as_of != run_context.as_of:
            raise ValueError("asset forecast origin must match RunContext as_of")
        if tuple(result.config.horizons) != _HORIZONS:
            raise ValueError("all scenarios must retain exact 3/6/12 horizons")
        if result.forecast_input.scenario_catalog.config_hash != catalog_hash:
            raise ValueError("scenario results cannot mix governed catalogs")
    current = _current_mapping_frame(current_mapping)
    if not current["as_of"].eq(run_context.as_of).all():
        raise ValueError("current Mapping as_of must match forecast origin")
    current_index = current.set_index(["asset_id", "horizon_months"])
    dimensions = sorted(current_index.index.tolist())
    records: list[dict[str, object]] = []
    for result in ordered_results:
        summary = result.summary.set_index(
            ["asset_id", "horizon_months", "return_basis"]
        )
        for asset_id, horizon in dimensions:
            absolute_key = (asset_id, horizon, "absolute")
            excess_key = (asset_id, horizon, "excess")
            if absolute_key not in summary.index or excess_key not in summary.index:
                raise ValueError("asset forecast is missing current Mapping dimensions")
            absolute = summary.loc[absolute_key]
            excess = summary.loc[excess_key]
            current_row = current_index.loc[(asset_id, horizon)]
            available = absolute["status"] == "available" and excess["status"] == (
                "available"
            )
            if absolute["status"] != excess["status"]:
                raise ValueError("absolute and excess forecast statuses must align")
            mapping_status, mapping_reasons = _mapping_decision(
                current_row,
                forecast_available=available,
            )
            if available:
                metrics = {
                    **_summary_values(absolute, basis="absolute"),
                    **_summary_values(excess, basis="excess"),
                }
                status = "available"
                unavailable_reason = None
                effective_samples = int(absolute["effective_samples"])
            else:
                metrics = {column: np.nan for column in _METRIC_COLUMNS}
                status = "unavailable"
                unavailable_reason = str(
                    absolute["unavailable_reason"] or excess["unavailable_reason"]
                )
                effective_samples = 0
            (
                baseline_component_json,
                channel_json,
                scenario_json,
                baseline_component_keys,
                scenario_component_keys,
                contribution_draw_count,
                conservation_error,
                conservation_passed,
            ) = _contribution_payload(
                result,
                asset_id=str(asset_id),
                horizon=int(horizon),
                available=available,
                absolute_expected_return=float(absolute["expected_return"])
                if available
                else 0.0,
            )
            source_identity = {
                column: absolute[column]
                for column in CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
            }
            component_contract_hash = compute_contribution_component_contract_hash(
                asset_id=asset_id,
                scenario_id=result.forecast_input.scenario_id,
                horizon_months=int(horizon),
                baseline_keys=baseline_component_keys,
                scenario_keys=scenario_component_keys,
                source_identity=source_identity,
            )
            records.append(
                {
                    "scenario_id": result.forecast_input.scenario_id,
                    "future_date": (
                        pd.Timestamp(run_context.as_of)
                        + pd.offsets.MonthEnd(int(horizon))
                    ).date(),
                    "asset_id": asset_id,
                    "horizon_months": int(horizon),
                    "status": status,
                    "unavailable_reason": unavailable_reason,
                    **metrics,
                    "interval50_nominal_coverage": 0.50,
                    "interval80_nominal_coverage": 0.80,
                    "effective_samples": effective_samples,
                    "contribution_draw_count": contribution_draw_count,
                    "contribution_component_contract_hash": component_contract_hash,
                    "baseline_component_contribution_json": baseline_component_json,
                    "channel_contribution_json": channel_json,
                    "scenario_contribution_json": scenario_json,
                    "contribution_aggregation_method": (
                        CONTRIBUTION_AGGREGATION_METHOD
                    ),
                    "contribution_conservation_max_abs_error": conservation_error,
                    "contribution_conservation_passed": conservation_passed,
                    "transferability_status": current_row["transferability_status"],
                    "mapping_status": mapping_status,
                    "mapping_status_reason_codes": mapping_reasons,
                    "evidence_level": current_row["evidence_level"],
                    "freshness_status": current_row["freshness_status"],
                    "freshness_reason_codes": current_row["freshness_reason_codes"],
                    "baseline_gate_passed": bool(current_row["baseline_gate_passed"]),
                    "oos_increment_score": current_row["oos_increment_score"],
                    "transferability_score": current_row["transferability_score"],
                    "transferability_evidence_date": current_row[
                        "transferability_evidence_date"
                    ],
                    "transferability_validation_end": current_row[
                        "transferability_validation_end"
                    ],
                    "current_mapping_run_id": current_row["run_id"],
                    "current_mapping_model_version": current_row["model_version"],
                    "current_mapping_snapshot_config_hash": current_row[
                        "snapshot_config_hash"
                    ],
                    "current_mapping_distribution_config_hash": current_row[
                        "distribution_config_hash"
                    ],
                    "current_mapping_transferability_config_hash": current_row[
                        "transferability_config_hash"
                    ],
                    "scenario_version": absolute["scenario_version"],
                    "catalog_version": absolute["catalog_version"],
                    "scenario_config_hash": absolute["scenario_config_hash"],
                    "asset_forecast_model_version": absolute[
                        "asset_forecast_model_version"
                    ],
                    "asset_forecast_config_hash": absolute[
                        "asset_forecast_config_hash"
                    ],
                    "channel_forecast_model_version": absolute[
                        "channel_forecast_model_version"
                    ],
                    "channel_forecast_config_hash": absolute[
                        "channel_forecast_config_hash"
                    ],
                    "channel_registry_hash": absolute["channel_registry_hash"],
                    "cycle_forecast_model_version": absolute[
                        "cycle_forecast_model_version"
                    ],
                    "cycle_forecast_config_hash": absolute[
                        "cycle_forecast_config_hash"
                    ],
                    "cycle_registry_hash": absolute["cycle_registry_hash"],
                    "stage2_posterior_date": absolute["stage2_posterior_date"],
                    "stage2_estimation_method": absolute["stage2_estimation_method"],
                    "forecast_origin": absolute["forecast_origin"],
                    "source_data_vintage": absolute["data_vintage"],
                    "feature_visible_date": absolute["feature_visible_date"],
                    "feature_generated_date": absolute["feature_generated_date"],
                    "feature_vintage_date": absolute["feature_vintage_date"],
                    "model_provenance": absolute["model_provenance"],
                    "data_provenance": absolute["data_provenance"],
                    "run_id": run_context.run_id,
                    "as_of": run_context.as_of,
                    "data_vintage": run_context.data_vintage,
                    "model_version": run_context.model_version,
                    "config_hash": run_context.config_hash,
                    "created_at": run_context.created_at,
                }
            )
    frame = pd.DataFrame(records, columns=ASSET_MAPPING_FUTURE_COLUMNS)
    product = AssetMappingFutureProduct(
        mapping=frame,
        _context=run_context,
        _forecasts=ordered_results,
        _current_mapping=current,
        _validation_token=_VALIDATED_PRODUCT_TOKEN,
    )
    validate_asset_mapping_future(product, context=run_context)
    return product


def _product_frame(product: object) -> tuple[pd.DataFrame, RunContext | None]:
    if isinstance(product, AssetMappingFutureProduct):
        return product.mapping, object.__getattribute__(product, "_context")
    if isinstance(product, pd.DataFrame):
        return product.copy(deep=True), None
    raise TypeError("product must be AssetMappingFutureProduct or pandas DataFrame")


def validate_asset_mapping_future(
    product: object,
    *,
    context: RunContext | None = None,
) -> None:
    """Validate scenario isolation, intervals, status, and provenance."""

    frame, retained_context = _product_frame(product)
    normalized = _normalize_frame(frame)
    if context is not None:
        run_context = _context(context)
        _validate_provenance(normalized, run_context)
        if retained_context is not None and retained_context != run_context:
            raise ValueError("product context does not match supplied RunContext")


def _arrow_table(values: pd.DataFrame) -> pa.Table:
    arrays = [
        pa.array(values[field.name].tolist(), type=field.type, from_pandas=True)
        for field in ASSET_MAPPING_FUTURE_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=ASSET_MAPPING_FUTURE_SCHEMA)


def _require_run_directory(run_dir: Path, context: RunContext) -> tuple[int, int]:
    try:
        run_stat = run_dir.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(run_stat.st_mode):
        raise ValueError("run_dir must be an existing real directory")
    if run_dir.name != context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")
    return run_stat.st_dev, run_stat.st_ino


def _write_table_exclusive(directory: Path, values: pd.DataFrame) -> Path:
    target = directory / ASSET_MAPPING_FUTURE_FILENAME
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"refuse accidental overwrite of {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{ASSET_MAPPING_FUTURE_FILENAME}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as product_file:
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
        if pq.read_schema(temporary) != ASSET_MAPPING_FUTURE_SCHEMA:
            raise ValueError("persisted asset mapping future schema mismatch")
        os.link(temporary, target)
        linked = True
        temporary.unlink()
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return target
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite or concurrent publish of {target}"
        ) from error
    except BaseException:
        if linked:
            target.unlink(missing_ok=True)
        raise
    finally:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def write_asset_mapping_future(
    run_dir: Path,
    product: AssetMappingFutureProduct,
    *,
    context: RunContext,
) -> Path:
    """Write ``asset_mapping_future.parquet`` under one immutable run."""

    run_context = _context(context)
    directory = Path(run_dir)
    identity = _require_run_directory(directory, run_context)
    if not isinstance(product, AssetMappingFutureProduct):
        raise TypeError(
            "write_asset_mapping_future requires build_asset_mapping_future output"
        )
    validate_asset_mapping_future(product, context=run_context)
    path = _write_table_exclusive(directory, _normalize_frame(product.mapping))
    if _require_run_directory(directory, run_context) != identity:
        path.unlink(missing_ok=True)
        raise ValueError("run directory changed during future Mapping publication")
    return path


def write_mapping_reference(
    run_dir: Path,
    *,
    context: RunContext,
    mapping_id: str,
) -> Path:
    """Write Task 27 canonical Mapping reference JSON for this artifact."""

    run_context = _context(context)
    directory = Path(run_dir)
    identity = _require_run_directory(directory, run_context)
    expected_metadata = mapping_manifest_metadata(mapping_id)
    metadata = run_context.quality_summary.get(MAPPING_MANIFEST_METADATA_KEY)
    if not isinstance(metadata, Mapping) or dict(metadata) != expected_metadata:
        raise ValueError("RunContext quality_summary Mapping metadata is invalid")
    artifact = directory / ASSET_MAPPING_FUTURE_FILENAME
    try:
        artifact_stat = artifact.lstat()
    except OSError as error:
        raise ValueError(
            "future Mapping artifact must be written before reference"
        ) from error
    if not stat.S_ISREG(artifact_stat.st_mode):
        raise ValueError("future Mapping artifact must be a regular file")
    payload = {
        **expected_metadata,
        "version": run_context.model_version,
        "run_id": run_context.run_id,
        "config_hash": run_context.config_hash,
        "artifact_hash": sha256_file(artifact),
        "as_of": run_context.as_of.isoformat(),
    }
    reference_path = directory / MAPPING_REFERENCE_FILENAME
    try:
        with reference_path.open("xb") as reference_file:
            reference_file.write(canonical_json_bytes(payload) + b"\n")
            reference_file.flush()
            os.fsync(reference_file.fileno())
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite of {reference_path}"
        ) from error
    if _require_run_directory(directory, run_context) != identity:
        reference_path.unlink(missing_ok=True)
        raise ValueError("run directory changed during Mapping reference publication")
    return reference_path


def build_and_write_asset_mapping_future(
    run_dir: Path,
    forecasts: Sequence[AssetForecastResult],
    current_mapping: object,
    *,
    context: RunContext,
) -> Path:
    """Build, validate, and exclusively write ``asset_mapping_future``."""

    product = build_asset_mapping_future(
        forecasts,
        current_mapping,
        context=context,
    )
    return write_asset_mapping_future(run_dir, product, context=context)


__all__ = [
    "ASSET_MAPPING_FUTURE_COLUMNS",
    "ASSET_MAPPING_FUTURE_FILENAME",
    "ASSET_MAPPING_FUTURE_PRODUCT",
    "ASSET_MAPPING_FUTURE_SCHEMA",
    "CONTRIBUTION_AGGREGATION_METHOD",
    "CONTRIBUTION_COMPONENT_CONTRACT_SCHEMA_VERSION",
    "CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS",
    "CONTRIBUTION_CONSERVATION_TOLERANCE",
    "AssetMappingFutureProduct",
    "build_and_write_asset_mapping_future",
    "build_asset_mapping_future",
    "compute_contribution_component_contract_hash",
    "mapping_manifest_metadata",
    "validate_asset_mapping_future",
    "write_asset_mapping_future",
    "write_mapping_reference",
]
