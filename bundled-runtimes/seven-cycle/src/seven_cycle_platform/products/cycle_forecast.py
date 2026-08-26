"""Stable governed ``cycle_forecast`` product."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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

from seven_cycle_platform.forecast.cycles import CycleForecastResult
from seven_cycle_platform.forecast.evaluation import (
    PROMOTION_METRICS,
    PromotionResult,
)
from seven_cycle_platform.security.redaction import redact_secrets
from seven_cycle_platform.storage import RunContext


CYCLE_FORECAST_FILENAME = "cycle_forecast.parquet"
CYCLE_FORECAST_SCHEMA = pa.schema(
    [
        pa.field("as_of", pa.date32()),
        pa.field("cycle_id", pa.string()),
        pa.field("horizon_months", pa.int32()),
        pa.field("forecast_date", pa.date32()),
        pa.field("status", pa.string()),
        pa.field("unavailable_reason", pa.string()),
        pa.field("expansion_probability", pa.float64()),
        pa.field("downturn_probability", pa.float64()),
        pa.field("contraction_probability", pa.float64()),
        pa.field("recovery_probability", pa.float64()),
        pa.field("angle_anchor_degrees", pa.float64()),
        pa.field("angle_q10", pa.float64()),
        pa.field("angle_q25", pa.float64()),
        pa.field("angle_q50", pa.float64()),
        pa.field("angle_q75", pa.float64()),
        pa.field("angle_q90", pa.float64()),
        pa.field("turning_status", pa.string()),
        pa.field("turning_probability", pa.float64()),
        pa.field("turning_start_month", pa.int32()),
        pa.field("turning_median_month", pa.int32()),
        pa.field("turning_end_month", pa.int32()),
        pa.field("turning_start_date", pa.date32()),
        pa.field("turning_median_date", pa.date32()),
        pa.field("turning_end_date", pa.date32()),
        pa.field("forecast_uncertainty", pa.float64()),
        pa.field("draw_count", pa.int32()),
        pa.field("probability_support_count", pa.int32()),
        pa.field("calibration_method", pa.string()),
        pa.field("calibration_version", pa.string()),
        pa.field("calibration_sample_count", pa.int32()),
        pa.field("calibration_reason", pa.string()),
        pa.field("forecast_value_source_role", pa.string()),
        pa.field("forecast_value_source_model_id", pa.string()),
        pa.field("forecast_value_source_model_version", pa.string()),
        pa.field("live_model_id", pa.string()),
        pa.field("live_model_role", pa.string()),
        pa.field("live_model_version", pa.string()),
        pa.field("promotion_decision", pa.string()),
        pa.field("challenger_model_id", pa.string()),
        pa.field("challenger_model_version", pa.string()),
        pa.field("challenger_status", pa.string()),
        pa.field("challenger_failure_reason_codes", pa.string()),
        pa.field("promotion_metrics_json", pa.string()),
        pa.field("source_forecast_config_hash", pa.string()),
        pa.field("registry_hash", pa.string()),
        pa.field("state_model_version", pa.string()),
        pa.field("state_config_hash", pa.string()),
        pa.field("source_data_vintage", pa.date32()),
        pa.field("run_id", pa.string()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)
CYCLE_FORECAST_COLUMNS = tuple(CYCLE_FORECAST_SCHEMA.names)

_VALIDATED_PRODUCT_TOKEN = object()
_RESULT_FIELDS = frozenset({"forecast"})
_EXPECTED_CYCLE_IDS = frozenset(f"C{position}" for position in range(1, 8))
_PROBABILITY_COLUMNS = (
    "expansion_probability",
    "downturn_probability",
    "contraction_probability",
    "recovery_probability",
)
_ANGLE_COLUMNS = ("angle_q10", "angle_q25", "angle_q50", "angle_q75", "angle_q90")
_FORECAST_NUMERIC_COLUMNS = (
    *_PROBABILITY_COLUMNS,
    "angle_anchor_degrees",
    *_ANGLE_COLUMNS,
    "turning_probability",
    "forecast_uncertainty",
)
_TURNING_MONTH_COLUMNS = (
    "turning_start_month",
    "turning_median_month",
    "turning_end_month",
)
_TURNING_DATE_COLUMNS = (
    "turning_start_date",
    "turning_median_date",
    "turning_end_date",
)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_PROMOTION_METRIC_FIELDS = frozenset(
    {
        "metric",
        "champion_sample_count",
        "challenger_sample_count",
        "paired_sample_count",
        "fold_count",
        "champion_value",
        "challenger_value",
        "improvement",
        "champion_coverage_rate",
        "challenger_coverage_rate",
        "nominal_coverage",
    }
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


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _parse_canonical_json(value: object, *, name: str) -> object:
    raw = _text(value, name=name)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must contain valid JSON") from error
    if raw != _canonical_json(parsed):
        raise ValueError(f"{name} must contain canonical JSON")
    return parsed


def _promotion_metrics_json(result: PromotionResult) -> str:
    frame = result.aggregate_metrics
    records: list[dict[str, object]] = []
    by_metric = frame.set_index("metric")
    for metric in PROMOTION_METRICS:
        row = by_metric.loc[metric]
        record: dict[str, object] = {"metric": metric}
        for column in (
            "champion_sample_count",
            "challenger_sample_count",
            "paired_sample_count",
            "fold_count",
        ):
            record[column] = int(row[column])
        for column in (
            "champion_value",
            "challenger_value",
            "improvement",
            "champion_coverage_rate",
            "challenger_coverage_rate",
            "nominal_coverage",
        ):
            value = row[column]
            record[column] = None if pd.isna(value) else float(value)
        records.append(record)
    return _canonical_json(records)


def _validate_promotion_json(value: object) -> str:
    parsed = _parse_canonical_json(value, name="promotion_metrics_json")
    if not isinstance(parsed, list) or len(parsed) != len(PROMOTION_METRICS):
        raise ValueError("promotion metrics must contain all governed metrics")
    metric_names: list[str] = []
    for record in parsed:
        if not isinstance(record, dict) or set(record) != _PROMOTION_METRIC_FIELDS:
            raise ValueError("promotion metrics do not match the governed contract")
        metric_names.append(str(record["metric"]))
        for column in (
            "champion_sample_count",
            "challenger_sample_count",
            "paired_sample_count",
            "fold_count",
        ):
            _integer(record[column], name=f"promotion {column}")
        for column in (
            "champion_value",
            "challenger_value",
            "improvement",
            "champion_coverage_rate",
            "challenger_coverage_rate",
            "nominal_coverage",
        ):
            _real(record[column], name=f"promotion {column}", allow_none=True)
    if tuple(metric_names) != PROMOTION_METRICS:
        raise ValueError("promotion metrics must use stable governed ordering")
    return _canonical_json(parsed)


def _normalize_frame(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("cycle forecast product must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError("cycle forecast product columns must be unique")
    if tuple(values.columns) != CYCLE_FORECAST_COLUMNS:
        raise ValueError(
            "cycle forecast product columns do not match the stable schema"
        )
    if values.empty:
        raise ValueError("cycle forecast product cannot be empty")
    frame = values.copy(deep=True)
    if redact_secrets(frame.to_json(date_format="iso")) != frame.to_json(
        date_format="iso"
    ):
        raise ValueError("cycle forecast product cannot contain secret-like material")

    frame["as_of"] = [_date_value(value, name="as_of") for value in frame["as_of"]]
    frame["forecast_date"] = [
        _date_value(value, name="forecast_date") for value in frame["forecast_date"]
    ]
    frame["source_data_vintage"] = [
        _date_value(value, name="source_data_vintage")
        for value in frame["source_data_vintage"]
    ]
    frame["data_vintage"] = [
        _date_value(value, name="data_vintage") for value in frame["data_vintage"]
    ]
    for column in _TURNING_DATE_COLUMNS:
        frame[column] = [
            _date_value(value, name=column, allow_none=True) for value in frame[column]
        ]
    frame["cycle_id"] = [_text(value, name="cycle_id") for value in frame["cycle_id"]]
    if not set(frame["cycle_id"]).issubset(_EXPECTED_CYCLE_IDS):
        raise ValueError("cycle_id must be registry-approved C1-C7")
    frame["horizon_months"] = [
        _integer(value, name="horizon_months", minimum=1)
        for value in frame["horizon_months"]
    ]
    if frame.duplicated(["as_of", "cycle_id", "horizon_months"]).any():
        raise ValueError("cycle forecast dimensions must be unique")

    for row_index, row in frame.iterrows():
        expected_date = (
            pd.Timestamp(row["as_of"]) + pd.offsets.MonthEnd(int(row["horizon_months"]))
        ).date()
        if row["forecast_date"] != expected_date:
            raise ValueError("forecast_date must match as_of plus horizon_months")
        status = _text(row["status"], name="status")
        if status not in {"available", "unavailable"}:
            raise ValueError("status must be available or unavailable")
        reason = _text(
            row["unavailable_reason"],
            name="unavailable_reason",
            allow_none=True,
        )
        frame.loc[row_index, "unavailable_reason"] = reason
        draw_count = _integer(row["draw_count"], name="draw_count")
        support_count = _integer(
            row["probability_support_count"],
            name="probability_support_count",
        )
        calibration_count = _integer(
            row["calibration_sample_count"],
            name="calibration_sample_count",
        )
        if support_count > draw_count:
            raise ValueError("probability support cannot exceed draw_count")
        if calibration_count < 0:
            raise ValueError("calibration sample count cannot be negative")

        if status == "unavailable":
            if reason is None:
                raise ValueError("unavailable rows require unavailable_reason")
            if any(not pd.isna(row[column]) for column in _FORECAST_NUMERIC_COLUMNS):
                raise ValueError("unavailable rows cannot fabricate forecast numbers")
            if any(not pd.isna(row[column]) for column in _TURNING_MONTH_COLUMNS):
                raise ValueError("unavailable rows cannot fabricate turning months")
            if any(row[column] is not None for column in _TURNING_DATE_COLUMNS):
                raise ValueError("unavailable rows cannot fabricate turning dates")
            if draw_count != 0 or support_count != 0:
                raise ValueError("unavailable rows must have zero forecast support")
            if row["turning_status"] != "unavailable":
                raise ValueError("unavailable rows require unavailable turning status")
        else:
            if reason is not None:
                raise ValueError("available rows cannot carry unavailable_reason")
            probabilities = np.asarray(
                [_real(row[column], name=column) for column in _PROBABILITY_COLUMNS]
            )
            if bool(((probabilities < 0.0) | (probabilities > 1.0)).any()) or not (
                np.isclose(probabilities.sum(), 1.0, atol=1e-10, rtol=1e-10)
            ):
                raise ValueError("phase probabilities must be bounded and sum to one")
            quantiles = [_real(row[column], name=column) for column in _ANGLE_COLUMNS]
            if quantiles != sorted(quantiles):
                raise ValueError("angle quantiles must be ordered")
            _real(row["angle_anchor_degrees"], name="angle_anchor_degrees")
            uncertainty = _real(
                row["forecast_uncertainty"], name="forecast_uncertainty"
            )
            if uncertainty < 0.0:
                raise ValueError("forecast uncertainty cannot be negative")
            if draw_count < 1 or support_count < 1:
                raise ValueError("available rows require positive forecast support")
            turning_status = _text(row["turning_status"], name="turning_status")
            turning_probability = _real(
                row["turning_probability"], name="turning_probability"
            )
            if not 0.0 <= turning_probability <= 1.0:
                raise ValueError("turning probability must be in [0, 1]")
            if turning_status == "none":
                if turning_probability != 0.0:
                    raise ValueError("turning status none requires zero probability")
                if any(not pd.isna(row[column]) for column in _TURNING_MONTH_COLUMNS):
                    raise ValueError("turning status none cannot carry turning months")
                if any(row[column] is not None for column in _TURNING_DATE_COLUMNS):
                    raise ValueError("turning status none cannot carry turning dates")
            elif turning_status in {"available", "expected"}:
                months = [
                    _integer(row[column], name=column, minimum=1)
                    for column in _TURNING_MONTH_COLUMNS
                ]
                dates = [row[column] for column in _TURNING_DATE_COLUMNS]
                if months != sorted(months) or dates != sorted(dates):
                    raise ValueError("turning start, median, and end must be ordered")
                if months[-1] > int(row["horizon_months"]):
                    raise ValueError("turning window cannot exceed forecast horizon")
            else:
                raise ValueError("turning_status is invalid")

        for column in (
            "calibration_method",
            "calibration_version",
            "calibration_reason",
            "forecast_value_source_model_id",
            "forecast_value_source_model_version",
            "live_model_id",
            "live_model_version",
            "challenger_model_id",
            "challenger_model_version",
            "state_model_version",
            "model_version",
            "run_id",
        ):
            frame.loc[row_index, column] = _text(row[column], name=column)
        if row["forecast_value_source_role"] != "champion":
            raise ValueError("forecast values must retain their Champion source label")
        if (
            row["promotion_decision"] != "rejected"
            or row["live_model_role"] != "champion"
            or row["challenger_status"] != "experimental"
        ):
            raise ValueError(
                "Task 28 Champion publication requires rejected experimental Challenger"
            )
        if row["live_model_id"] != row["forecast_value_source_model_id"]:
            raise ValueError("live Champion identity must match forecast value source")
        if row["live_model_version"] != row["forecast_value_source_model_version"]:
            raise ValueError("live Champion version must match forecast value source")
        failures = _parse_canonical_json(
            row["challenger_failure_reason_codes"],
            name="challenger_failure_reason_codes",
        )
        if not isinstance(failures, list) or not failures:
            raise ValueError("rejected Challenger requires failure reason codes")
        if any(not isinstance(code, str) or not code for code in failures):
            raise ValueError("Challenger failure reason codes are invalid")
        frame.loc[row_index, "challenger_failure_reason_codes"] = _canonical_json(
            failures
        )
        frame.loc[row_index, "promotion_metrics_json"] = _validate_promotion_json(
            row["promotion_metrics_json"]
        )
        for column in (
            "source_forecast_config_hash",
            "registry_hash",
            "state_config_hash",
            "config_hash",
        ):
            value = _text(row[column], name=column)
            if _HASH_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{column} must be a lowercase SHA-256 digest")

    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    return frame.sort_values(
        ["as_of", "cycle_id", "horizon_months"], kind="stable"
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


def _rebuild_cycle_result(value: object) -> CycleForecastResult:
    if not isinstance(value, CycleForecastResult):
        raise TypeError("forecast_result must be a CycleForecastResult")
    return CycleForecastResult(
        summary=value.summary,
        monthly_paths=value.monthly_paths,
        forecast_input=value.forecast_input,
        config=value.config,
    )


def _rebuild_promotion(value: object) -> PromotionResult:
    if not isinstance(value, PromotionResult):
        raise TypeError("promotion_result must be a PromotionResult")
    return PromotionResult(
        fold_metrics=value.fold_metrics,
        aggregate_metrics=value.aggregate_metrics,
        gate_results=value.gate_results,
        champion_artifacts=value.champion_artifacts,
        challenger_artifacts=value.challenger_artifacts,
        champion_model_card=value.champion_model_card,
        challenger_model_card=value.challenger_model_card,
        champion_feature_audit=value.champion_feature_audit,
        challenger_feature_audit=value.challenger_feature_audit,
        evidence_context=value.evidence_context,
        config=value.config,
        promotion_decision=value.promotion_decision,
        live_model=value.live_model,
        live_model_role=value.live_model_role,
        challenger_status=value.challenger_status,
        failure_reason_codes=value.failure_reason_codes,
        champion_replay_artifacts=value.champion_replay_artifacts,
        challenger_replay_artifacts=value.challenger_replay_artifacts,
    )


@dataclass(frozen=True)
class CycleForecastProduct:
    """Detached one-row-per-cycle/horizon publication frame."""

    forecast: pd.DataFrame
    _context: RunContext | None = field(default=None, repr=False, compare=False)
    _forecast_result: CycleForecastResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _promotion_result: PromotionResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _validation_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _VALIDATED_PRODUCT_TOKEN:
            raise TypeError(
                "CycleForecastProduct must be created by build_cycle_forecast"
            )
        context = _context(self._context)
        if not isinstance(self._forecast_result, CycleForecastResult):
            raise TypeError("validated product must retain CycleForecastResult")
        if not isinstance(self._promotion_result, PromotionResult):
            raise TypeError("validated product must retain PromotionResult")
        normalized = _normalize_frame(object.__getattribute__(self, "forecast"))
        _validate_provenance(normalized, context)
        object.__setattr__(self, "forecast", normalized.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    def __iter__(self) -> Iterator[pd.DataFrame]:
        yield self.forecast

    @property
    def frame(self) -> pd.DataFrame:
        return self.forecast


def build_cycle_forecast(
    forecast_result: CycleForecastResult,
    promotion_result: PromotionResult,
    *,
    context: RunContext,
) -> CycleForecastProduct:
    """Build ``cycle_forecast`` only from governed deterministic replay."""

    run_context = _context(context)
    result = _rebuild_cycle_result(forecast_result)
    promotion = _rebuild_promotion(promotion_result)
    champion_card = promotion.champion_model_card
    challenger_card = promotion.challenger_model_card
    if champion_card.scope != "cycle" or challenger_card.scope != "cycle":
        raise ValueError("cycle_forecast requires a cycle-scope promotion decision")
    if promotion.promoted:
        raise ValueError(
            "promoted Challenger requires corresponding governed Challenger forecast input"
        )
    if (
        promotion.live_model_role != "champion"
        or promotion.challenger_status != "experimental"
        or not promotion.failure_reason_codes
    ):
        raise ValueError("rejected Challenger governance is inconsistent")
    source = result.summary
    if not source["model_role"].eq("champion").all():
        raise ValueError("Task 24 forecast values must retain Champion model_role")
    if not source["forecast_model_version"].eq(champion_card.version).all():
        raise ValueError(
            "Champion model card version must match Task 24 forecast values"
        )
    if pd.Timestamp(result.forecast_input.as_of).date() != run_context.as_of:
        raise ValueError("CycleForecastResult as_of must match RunContext")
    cycle_specs = tuple(result.forecast_input.cycle_specs)
    expected_dimensions = {
        (cycle.cycle_id, int(horizon))
        for cycle in cycle_specs
        for horizon in cycle.horizons
    }
    actual_dimensions = set(
        zip(source["cycle_id"], source["horizon_months"], strict=True)
    )
    if actual_dimensions != expected_dimensions:
        raise ValueError("cycle forecast must publish only registry-approved horizons")

    metrics_json = _promotion_metrics_json(promotion)
    failures_json = _canonical_json(list(promotion.failure_reason_codes))
    records: list[dict[str, object]] = []
    for row in source.itertuples(index=False):
        records.append(
            {
                "as_of": pd.Timestamp(row.as_of).date(),
                "cycle_id": row.cycle_id,
                "horizon_months": int(row.horizon_months),
                "forecast_date": pd.Timestamp(row.forecast_date).date(),
                "status": row.status,
                "unavailable_reason": row.unavailable_reason,
                **{column: getattr(row, column) for column in _PROBABILITY_COLUMNS},
                "angle_anchor_degrees": row.angle_anchor_degrees,
                **{column: getattr(row, column) for column in _ANGLE_COLUMNS},
                "turning_status": row.turning_status,
                "turning_probability": row.turning_probability,
                "turning_start_month": row.turning_start_month,
                "turning_median_month": row.turning_median_month,
                "turning_end_month": row.turning_end_month,
                "turning_start_date": row.turning_start_date,
                "turning_median_date": row.turning_median_date,
                "turning_end_date": row.turning_end_date,
                "forecast_uncertainty": row.forecast_uncertainty,
                "draw_count": int(row.draw_count),
                "probability_support_count": int(row.probability_support_count),
                "calibration_method": row.calibration_method,
                "calibration_version": row.calibration_version,
                "calibration_sample_count": int(row.calibration_sample_count),
                "calibration_reason": row.calibration_reason,
                "forecast_value_source_role": "champion",
                "forecast_value_source_model_id": champion_card.model_id,
                "forecast_value_source_model_version": row.forecast_model_version,
                "live_model_id": promotion.live_model,
                "live_model_role": promotion.live_model_role,
                "live_model_version": champion_card.version,
                "promotion_decision": promotion.promotion_decision,
                "challenger_model_id": challenger_card.model_id,
                "challenger_model_version": challenger_card.version,
                "challenger_status": promotion.challenger_status,
                "challenger_failure_reason_codes": failures_json,
                "promotion_metrics_json": metrics_json,
                "source_forecast_config_hash": row.forecast_config_hash,
                "registry_hash": row.registry_hash,
                "state_model_version": row.state_model_version,
                "state_config_hash": row.state_config_hash,
                "source_data_vintage": pd.Timestamp(row.data_vintage).date(),
                "run_id": run_context.run_id,
                "data_vintage": run_context.data_vintage,
                "model_version": run_context.model_version,
                "config_hash": run_context.config_hash,
                "created_at": run_context.created_at,
            }
        )
    frame = pd.DataFrame(records, columns=CYCLE_FORECAST_COLUMNS)
    product = CycleForecastProduct(
        forecast=frame,
        _context=run_context,
        _forecast_result=result,
        _promotion_result=promotion,
        _validation_token=_VALIDATED_PRODUCT_TOKEN,
    )
    validate_cycle_forecast(product, context=run_context)
    return product


def _product_frame(product: object) -> tuple[pd.DataFrame, RunContext | None]:
    if isinstance(product, CycleForecastProduct):
        return product.forecast, object.__getattribute__(product, "_context")
    if isinstance(product, pd.DataFrame):
        return product.copy(deep=True), None
    raise TypeError("product must be CycleForecastProduct or pandas DataFrame")


def validate_cycle_forecast(
    product: object,
    *,
    context: RunContext | None = None,
) -> None:
    """Validate stable schema, forecast invariants, and provenance."""

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
        for field in CYCLE_FORECAST_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=CYCLE_FORECAST_SCHEMA)


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


def _write_table_exclusive(
    directory: Path,
    filename: str,
    values: pd.DataFrame,
    schema: pa.Schema,
) -> Path:
    target = directory / filename
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"refuse accidental overwrite of {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{filename}.",
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
        if pq.read_schema(temporary) != schema:
            raise ValueError("persisted cycle forecast schema mismatch")
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


def write_cycle_forecast(
    run_dir: Path,
    product: CycleForecastProduct,
    *,
    context: RunContext,
) -> Path:
    """Write ``cycle_forecast.parquet`` exclusively under one run."""

    run_context = _context(context)
    directory = Path(run_dir)
    identity = _require_run_directory(directory, run_context)
    if not isinstance(product, CycleForecastProduct):
        raise TypeError("write_cycle_forecast requires build_cycle_forecast output")
    validate_cycle_forecast(product, context=run_context)
    values = _normalize_frame(product.forecast)
    path = _write_table_exclusive(
        directory,
        CYCLE_FORECAST_FILENAME,
        values,
        CYCLE_FORECAST_SCHEMA,
    )
    if _require_run_directory(directory, run_context) != identity:
        path.unlink(missing_ok=True)
        raise ValueError("run directory changed during cycle forecast publication")
    return path


def build_and_write_cycle_forecast(
    run_dir: Path,
    forecast_result: CycleForecastResult,
    promotion_result: PromotionResult,
    *,
    context: RunContext,
) -> Path:
    """Build, validate, and exclusively write ``cycle_forecast``."""

    product = build_cycle_forecast(
        forecast_result,
        promotion_result,
        context=context,
    )
    return write_cycle_forecast(run_dir, product, context=context)


__all__ = [
    "CYCLE_FORECAST_COLUMNS",
    "CYCLE_FORECAST_FILENAME",
    "CYCLE_FORECAST_SCHEMA",
    "CycleForecastProduct",
    "build_and_write_cycle_forecast",
    "build_cycle_forecast",
    "validate_cycle_forecast",
    "write_cycle_forecast",
]
