"""Auditable transferability scoring for current distribution forecasts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
import hashlib
import json
from numbers import Integral, Real
from types import MappingProxyType

import numpy as np
import pandas as pd

from seven_cycle_platform.mapping.distribution import (
    HORIZONS,
    CurrentDistributionResult,
)
from seven_cycle_platform.storage import RUN_ID_PATTERN
from seven_cycle_platform.types import MappingStatus


TRANSFERABILITY_DIMENSIONS = (
    "sign",
    "magnitude",
    "neighbor",
    "constituent",
    "valuation_positioning",
    "structural",
    "cycle_confidence",
    "channel_confidence",
    "proxy_quality",
    "oos_increment",
)

TRANSFERABILITY_EVIDENCE_COLUMNS = (
    "asset_id",
    "horizon_months",
    "sign_stability",
    "magnitude_stability",
    "historical_neighbor_similarity",
    "constituent_business_model_stability",
    "valuation_positioning_similarity",
    "structural_stability",
    "cycle_confidence",
    "channel_confidence",
    "proxy_discount",
    "model_oos_loss",
    "baseline_oos_loss",
    "oos_validation_count",
    "evidence_date",
    "validation_end",
)

TRANSFERABILITY_SUMMARY_COLUMNS = (
    "asset_id",
    "horizon_months",
    "status",
    "overall_score",
    "historical_score",
    "sign_score",
    "magnitude_score",
    "neighbor_score",
    "constituent_score",
    "valuation_positioning_score",
    "structural_score",
    "cycle_confidence_score",
    "channel_confidence_score",
    "proxy_quality_score",
    "oos_increment_score",
    "sign_stability",
    "magnitude_stability",
    "historical_neighbor_similarity",
    "constituent_business_model_stability",
    "valuation_positioning_similarity",
    "structural_stability",
    "cycle_confidence",
    "channel_confidence",
    "proxy_discount",
    "model_oos_loss",
    "baseline_oos_loss",
    "oos_increment",
    "oos_validation_count",
    "absolute_effective_samples",
    "excess_effective_samples",
    "effective_samples",
    "absolute_distribution_status",
    "excess_distribution_status",
    "distribution_status",
    "baseline_gate_passed",
    "formal_hard_gates_passed",
    "reason_codes",
    "evidence_date",
    "validation_end",
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "distribution_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)

_DIRECT_SCORE_SOURCES = (
    ("sign", "sign_stability"),
    ("magnitude", "magnitude_stability"),
    ("neighbor", "historical_neighbor_similarity"),
    ("constituent", "constituent_business_model_stability"),
    ("valuation_positioning", "valuation_positioning_similarity"),
    ("structural", "structural_stability"),
    ("cycle_confidence", "cycle_confidence"),
    ("channel_confidence", "channel_confidence"),
)
_UNIT_EVIDENCE_COLUMNS = tuple(source for _, source in _DIRECT_SCORE_SOURCES) + (
    "proxy_discount",
)
_EVIDENCE_VALUE_COLUMNS = _UNIT_EVIDENCE_COLUMNS + (
    "model_oos_loss",
    "baseline_oos_loss",
    "oos_validation_count",
    "evidence_date",
    "validation_end",
)
_HISTORICAL_DIMENSIONS = tuple(
    dimension
    for dimension in TRANSFERABILITY_DIMENSIONS
    if dimension != "oos_increment"
)
_RESULT_FRAME_FIELDS = frozenset({"summary", "evidence"})
_RETURN_BASES = ("absolute", "excess")
_DISTRIBUTION_REQUIRED_COLUMNS = (
    "asset_id",
    "horizon_months",
    "return_basis",
    "effective_samples",
    "status",
    "run_id",
    "snapshot_as_of",
    "snapshot_data_vintage",
    "snapshot_model_version",
    "snapshot_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)
_DISTRIBUTION_DATE_COLUMNS = (
    "snapshot_as_of",
    "snapshot_data_vintage",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)
_DISTRIBUTION_TEXT_COLUMNS = (
    "run_id",
    "snapshot_model_version",
    "snapshot_config_hash",
)
_POLICY_THRESHOLD_REL_TOLERANCE = 1e-12


class TransferabilityReason(StrEnum):
    """Stable machine-readable transferability audit reasons."""

    DISTRIBUTION_UNAVAILABLE = "distribution_unavailable"
    INSUFFICIENT_EFFECTIVE_SAMPLES = "insufficient_effective_samples"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"
    INSUFFICIENT_OOS_VALIDATION = "insufficient_oos_validation"
    BASELINE_NOT_BEATEN = "baseline_not_beaten"
    LOW_OOS_INCREMENT = "low_oos_increment"
    LOW_SIGN_STABILITY = "low_sign_stability"
    LOW_MAGNITUDE_STABILITY = "low_magnitude_stability"
    LOW_NEIGHBOR_SIMILARITY = "low_neighbor_similarity"
    CONSTITUENT_DRIFT = "constituent_drift"
    VALUATION_POSITIONING_DISTANCE = "valuation_positioning_distance"
    STRUCTURAL_BREAK = "structural_break"
    LOW_CYCLE_CONFIDENCE = "low_cycle_confidence"
    LOW_CHANNEL_CONFIDENCE = "low_channel_confidence"
    PROXY_DISCOUNT = "proxy_discount"
    LOW_OVERALL_SCORE = "low_overall_score"
    OUTCOME_FORMAL = "outcome_formal"
    OUTCOME_CONDITIONAL = "outcome_conditional"
    OUTCOME_RETROSPECTIVE_ONLY = "outcome_retrospective_only"
    OUTCOME_UNAVAILABLE = "outcome_unavailable"


def _default_weights() -> dict[str, float]:
    return {
        "sign": 0.12,
        "magnitude": 0.10,
        "neighbor": 0.10,
        "constituent": 0.10,
        "valuation_positioning": 0.08,
        "structural": 0.12,
        "cycle_confidence": 0.08,
        "channel_confidence": 0.08,
        "proxy_quality": 0.07,
        "oos_increment": 0.15,
    }


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    missing = pd.isna(value)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


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


def _unit_interval(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return numeric


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


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


def _identifier(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must contain non-empty strings")
    return value.strip()


def _date_value(value: object, *, name: str, allow_missing: bool) -> date | None:
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


def _weight_items(values: object) -> list[tuple[object, object]]:
    if isinstance(values, Mapping):
        return list(values.items())
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        items: list[tuple[object, object]] = []
        for item in values:
            if (
                not isinstance(item, Sequence)
                or isinstance(item, (str, bytes))
                or len(item) != 2
            ):
                raise TypeError("weights must be a mapping or key/value pairs")
            items.append((item[0], item[1]))
        return items
    raise TypeError("weights must be a mapping or key/value pairs")


def _normalized_weights(values: object) -> Mapping[str, float]:
    normalized: dict[str, float] = {}
    for raw_name, raw_weight in _weight_items(values):
        if not isinstance(raw_name, str):
            raise TypeError("weight names must be strings")
        name = raw_name.strip()
        if name in normalized:
            raise ValueError(f"duplicate weight for {name}")
        normalized[name] = _unit_interval(raw_weight, name=f"weight {name}")
    if set(normalized) != set(TRANSFERABILITY_DIMENSIONS):
        raise ValueError("weights must define every transferability dimension exactly")
    ordered = {
        dimension: normalized[dimension] for dimension in TRANSFERABILITY_DIMENSIONS
    }
    if not np.isclose(sum(ordered.values()), 1.0, atol=1e-12, rtol=0.0):
        raise ValueError("weights must sum to one")
    if sum(ordered[dimension] for dimension in _HISTORICAL_DIMENSIONS) <= 0.0:
        raise ValueError("historical dimension weights must have positive total")
    return MappingProxyType(ordered)


@dataclass(frozen=True)
class TransferabilityConfig:
    """Immutable transferability policy, hard gates, and explicit weights."""

    weights: object = field(default_factory=_default_weights)
    formal_overall_threshold: float = 0.80
    conditional_overall_threshold: float = 0.60
    formal_sign_threshold: float = 0.75
    formal_magnitude_threshold: float = 0.70
    formal_neighbor_threshold: float = 0.70
    formal_constituent_threshold: float = 0.75
    formal_valuation_positioning_threshold: float = 0.65
    formal_structural_threshold: float = 0.75
    formal_cycle_confidence_threshold: float = 0.70
    formal_channel_confidence_threshold: float = 0.70
    formal_proxy_discount_max: float = 0.25
    min_effective_samples: int = 24
    min_oos_validation_count: int = 12
    min_oos_increment: float = 0.05
    full_score_oos_increment: float = 0.20

    def __post_init__(self) -> None:
        weights = _normalized_weights(self.weights)
        formal_overall = _unit_interval(
            self.formal_overall_threshold,
            name="formal_overall_threshold",
        )
        conditional_overall = _unit_interval(
            self.conditional_overall_threshold,
            name="conditional_overall_threshold",
        )
        if conditional_overall >= formal_overall:
            raise ValueError(
                "conditional_overall_threshold must be below formal_overall_threshold"
            )
        hard_thresholds = {
            "formal_sign_threshold": _unit_interval(
                self.formal_sign_threshold,
                name="formal_sign_threshold",
            ),
            "formal_magnitude_threshold": _unit_interval(
                self.formal_magnitude_threshold,
                name="formal_magnitude_threshold",
            ),
            "formal_neighbor_threshold": _unit_interval(
                self.formal_neighbor_threshold,
                name="formal_neighbor_threshold",
            ),
            "formal_constituent_threshold": _unit_interval(
                self.formal_constituent_threshold,
                name="formal_constituent_threshold",
            ),
            "formal_valuation_positioning_threshold": _unit_interval(
                self.formal_valuation_positioning_threshold,
                name="formal_valuation_positioning_threshold",
            ),
            "formal_structural_threshold": _unit_interval(
                self.formal_structural_threshold,
                name="formal_structural_threshold",
            ),
            "formal_cycle_confidence_threshold": _unit_interval(
                self.formal_cycle_confidence_threshold,
                name="formal_cycle_confidence_threshold",
            ),
            "formal_channel_confidence_threshold": _unit_interval(
                self.formal_channel_confidence_threshold,
                name="formal_channel_confidence_threshold",
            ),
            "formal_proxy_discount_max": _unit_interval(
                self.formal_proxy_discount_max,
                name="formal_proxy_discount_max",
            ),
        }
        minimum_samples = _positive_integer(
            self.min_effective_samples,
            name="min_effective_samples",
        )
        minimum_validations = _positive_integer(
            self.min_oos_validation_count,
            name="min_oos_validation_count",
        )
        minimum_increment = _unit_interval(
            self.min_oos_increment,
            name="min_oos_increment",
        )
        full_score_increment = _unit_interval(
            self.full_score_oos_increment,
            name="full_score_oos_increment",
        )
        if minimum_increment <= 0.0:
            raise ValueError("min_oos_increment must be strictly positive")
        if full_score_increment < minimum_increment:
            raise ValueError(
                "full_score_oos_increment must be at least min_oos_increment"
            )

        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "formal_overall_threshold", formal_overall)
        object.__setattr__(self, "conditional_overall_threshold", conditional_overall)
        for name, value in hard_thresholds.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "min_effective_samples", minimum_samples)
        object.__setattr__(self, "min_oos_validation_count", minimum_validations)
        object.__setattr__(self, "min_oos_increment", minimum_increment)
        object.__setattr__(self, "full_score_oos_increment", full_score_increment)

    @property
    def config_hash(self) -> str:
        payload = {
            "weights": {
                dimension: self.weights[dimension]
                for dimension in TRANSFERABILITY_DIMENSIONS
            },
            "formal_overall_threshold": self.formal_overall_threshold,
            "conditional_overall_threshold": self.conditional_overall_threshold,
            "formal_sign_threshold": self.formal_sign_threshold,
            "formal_magnitude_threshold": self.formal_magnitude_threshold,
            "formal_neighbor_threshold": self.formal_neighbor_threshold,
            "formal_constituent_threshold": self.formal_constituent_threshold,
            "formal_valuation_positioning_threshold": (
                self.formal_valuation_positioning_threshold
            ),
            "formal_structural_threshold": self.formal_structural_threshold,
            "formal_cycle_confidence_threshold": (
                self.formal_cycle_confidence_threshold
            ),
            "formal_channel_confidence_threshold": (
                self.formal_channel_confidence_threshold
            ),
            "formal_proxy_discount_max": self.formal_proxy_discount_max,
            "min_effective_samples": self.min_effective_samples,
            "min_oos_validation_count": self.min_oos_validation_count,
            "min_oos_increment": self.min_oos_increment,
            "full_score_oos_increment": self.full_score_oos_increment,
        }
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()


def _distribution_rows(distribution: object) -> pd.DataFrame:
    if not isinstance(distribution, CurrentDistributionResult):
        raise TypeError("distribution must be a CurrentDistributionResult")
    summary = distribution.summary
    if not isinstance(summary, pd.DataFrame):
        raise TypeError("distribution.summary must be a pandas DataFrame")
    missing = set(_DISTRIBUTION_REQUIRED_COLUMNS) - set(summary.columns)
    if missing:
        raise ValueError("distribution summary is missing required columns")
    frame = summary.loc[:, _DISTRIBUTION_REQUIRED_COLUMNS].copy(deep=True)
    frame["asset_id"] = [
        _identifier(value, name="distribution asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _positive_integer(value, name="distribution horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError(
            "distribution horizon_months must use supported horizons 3, 6, and 12"
        )
    if any(
        set(group["horizon_months"]) != set(HORIZONS)
        for _, group in frame.groupby("asset_id", sort=False)
    ):
        raise ValueError(
            "distribution must contain supported horizons 3, 6, and 12 for every asset"
        )
    frame["return_basis"] = [
        _identifier(value, name="distribution return_basis")
        for value in frame["return_basis"].tolist()
    ]
    if frame.duplicated(["asset_id", "horizon_months", "return_basis"]).any():
        raise ValueError("distribution basis dimensions must be unique")
    if not set(frame["return_basis"]).issubset(set(_RETURN_BASES)):
        raise ValueError("distribution return_basis must be absolute or excess")

    frame["effective_samples"] = [
        _nonnegative_integer(value, name="distribution effective_samples")
        for value in frame["effective_samples"].tolist()
    ]
    normalized_statuses: list[str] = []
    for value in frame["status"].tolist():
        status = _identifier(value, name="distribution status")
        if status not in {"available", "unavailable"}:
            raise ValueError("distribution status is invalid")
        normalized_statuses.append(status)
    frame["status"] = normalized_statuses

    for column in _DISTRIBUTION_DATE_COLUMNS:
        frame[column] = [
            _date_value(value, name=f"distribution {column}", allow_missing=False)
            for value in frame[column].tolist()
        ]
    for column in _DISTRIBUTION_TEXT_COLUMNS:
        frame[column] = [
            _identifier(value, name=f"distribution {column}")
            for value in frame[column].tolist()
        ]
    if any(
        len(set(frame[column].tolist())) != 1
        for column in _DISTRIBUTION_DATE_COLUMNS + _DISTRIBUTION_TEXT_COLUMNS
    ):
        raise ValueError("distribution basis provenance must be consistent")

    run_id = str(frame["run_id"].iloc[0])
    distribution_hash = str(frame["snapshot_config_hash"].iloc[0])
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("distribution run_id provenance is invalid")
    if len(distribution_hash) != 64 or any(
        character not in "0123456789abcdef" for character in distribution_hash
    ):
        raise ValueError("distribution config hash provenance is invalid")
    as_of = frame["snapshot_as_of"].iloc[0]
    data_vintage = frame["snapshot_data_vintage"].iloc[0]
    stage1_date = frame["stage1_posterior_date"].iloc[0]
    stage2_date = frame["stage2_posterior_date"].iloc[0]
    forecast_origin = frame["forecast_origin"].iloc[0]
    if data_vintage > as_of:
        raise ValueError("distribution data_vintage cannot follow as_of")
    if stage1_date > as_of or stage2_date > as_of:
        raise ValueError("distribution posterior provenance cannot follow as_of")
    if forecast_origin != as_of:
        raise ValueError("distribution forecast_origin must equal as_of")

    records: list[dict[str, object]] = []
    for (asset_id, horizon_months), group in frame.groupby(
        ["asset_id", "horizon_months"],
        sort=True,
    ):
        if set(group["return_basis"]) != set(_RETURN_BASES) or len(group) != 2:
            raise ValueError(
                "distribution must contain one absolute and one excess basis row"
            )
        basis = group.set_index("return_basis")
        absolute_status = str(basis.loc["absolute", "status"])
        excess_status = str(basis.loc["excess", "status"])
        absolute_samples = int(basis.loc["absolute", "effective_samples"])
        excess_samples = int(basis.loc["excess", "effective_samples"])
        records.append(
            {
                "asset_id": asset_id,
                "horizon_months": int(horizon_months),
                "absolute_effective_samples": absolute_samples,
                "excess_effective_samples": excess_samples,
                "effective_samples": min(absolute_samples, excess_samples),
                "absolute_distribution_status": absolute_status,
                "excess_distribution_status": excess_status,
                "distribution_status": (
                    "available"
                    if absolute_status == excess_status == "available"
                    else "unavailable"
                ),
                "run_id": run_id,
                "as_of": as_of,
                "data_vintage": data_vintage,
                "model_version": str(frame["snapshot_model_version"].iloc[0]),
                "distribution_config_hash": distribution_hash,
                "stage1_posterior_date": stage1_date,
                "stage2_posterior_date": stage2_date,
                "forecast_origin": forecast_origin,
            }
        )
    if not records:
        raise ValueError("distribution summary cannot be empty")
    return (
        pd.DataFrame(records)
        .sort_values(
            ["asset_id", "horizon_months"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _optional_unit(value: object, *, name: str) -> float:
    if _is_missing(value):
        return np.nan
    return _unit_interval(value, name=name)


def _optional_loss(
    value: object,
    *,
    name: str,
    strictly_positive: bool,
) -> float:
    if _is_missing(value):
        return np.nan
    numeric = _finite_real(value, name=name)
    if strictly_positive and numeric <= 0.0:
        raise ValueError(f"{name} must be strictly positive")
    if not strictly_positive and numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _optional_count(value: object, *, name: str) -> int | float:
    if _is_missing(value):
        return np.nan
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite nonnegative integer")
    if numeric < 0.0:
        raise ValueError(f"{name} must be a nonnegative integer")
    if not numeric.is_integer():
        raise TypeError(f"{name} must be an integer-valued real number")
    return int(numeric)


def _normalize_evidence(
    evidence: object,
    distribution_rows: pd.DataFrame,
) -> pd.DataFrame:
    if not isinstance(evidence, pd.DataFrame):
        raise TypeError("evidence must be a pandas DataFrame")
    missing = set(TRANSFERABILITY_EVIDENCE_COLUMNS) - set(evidence.columns)
    if missing:
        raise ValueError("evidence is missing required columns")
    frame = evidence.loc[:, TRANSFERABILITY_EVIDENCE_COLUMNS].copy(deep=True)
    frame["asset_id"] = [
        _identifier(value, name="evidence asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _positive_integer(value, name="evidence horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError(
            "evidence horizon_months must use supported horizons 3, 6, and 12"
        )
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("evidence asset/horizon dimensions must be unique")
    expected_dimensions = set(
        map(
            tuple,
            distribution_rows[["asset_id", "horizon_months"]].to_numpy().tolist(),
        )
    )
    evidence_dimensions = set(
        map(
            tuple,
            frame[["asset_id", "horizon_months"]].to_numpy().tolist(),
        )
    )
    if evidence_dimensions != expected_dimensions:
        raise ValueError(
            "evidence asset/horizon coverage must exactly align with distribution"
        )

    for column in _UNIT_EVIDENCE_COLUMNS:
        frame[column] = [
            _optional_unit(value, name=column) for value in frame[column].tolist()
        ]
    frame["model_oos_loss"] = [
        _optional_loss(
            value,
            name="model_oos_loss",
            strictly_positive=False,
        )
        for value in frame["model_oos_loss"].tolist()
    ]
    frame["baseline_oos_loss"] = [
        _optional_loss(
            value,
            name="baseline_oos_loss",
            strictly_positive=True,
        )
        for value in frame["baseline_oos_loss"].tolist()
    ]
    frame["oos_validation_count"] = [
        _optional_count(value, name="oos_validation_count")
        for value in frame["oos_validation_count"].tolist()
    ]
    for column in ("evidence_date", "validation_end"):
        frame[column] = [
            _date_value(value, name=column, allow_missing=True)
            for value in frame[column].tolist()
        ]

    provenance = distribution_rows.iloc[0]
    cutoff = provenance["as_of"]
    forecast_origin = provenance["forecast_origin"]
    for evidence_date, validation_end in zip(
        frame["evidence_date"].tolist(),
        frame["validation_end"].tolist(),
        strict=True,
    ):
        if (
            evidence_date is not None
            and validation_end is not None
            and validation_end > evidence_date
        ):
            raise ValueError("validation_end cannot follow evidence_date")
    for evidence_date in frame["evidence_date"].tolist():
        if evidence_date is not None and evidence_date > cutoff:
            raise ValueError("evidence_date cannot follow distribution as_of cutoff")
    for validation_end in frame["validation_end"].tolist():
        if validation_end is not None and validation_end >= forecast_origin:
            raise ValueError(
                "validation_end must be strictly earlier than forecast_origin"
            )
    return frame.sort_values(
        ["asset_id", "horizon_months"],
        kind="stable",
    ).reset_index(drop=True)


def _append_reason(
    reasons: list[TransferabilityReason],
    reason: TransferabilityReason,
) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _meets_policy_minimum(value: float, threshold: float) -> bool:
    """Apply positive ratio minima with a 1e-12 relative float tolerance."""

    if value <= 0.0:
        return False
    return value >= threshold or bool(
        np.isclose(
            value,
            threshold,
            rtol=_POLICY_THRESHOLD_REL_TOLERANCE,
            atol=0.0,
        )
    )


def _score_record(
    row: Mapping[str, object],
    config: TransferabilityConfig,
) -> dict[str, object]:
    complete = not any(_is_missing(row[column]) for column in _EVIDENCE_VALUE_COLUMNS)
    scores: dict[str, float] = {}
    for dimension, source in _DIRECT_SCORE_SOURCES:
        value = row[source]
        scores[dimension] = np.nan if _is_missing(value) else float(value)
    proxy_discount = row["proxy_discount"]
    scores["proxy_quality"] = (
        np.nan if _is_missing(proxy_discount) else 1.0 - float(proxy_discount)
    )
    model_loss = row["model_oos_loss"]
    baseline_loss = row["baseline_oos_loss"]
    if _is_missing(model_loss) or _is_missing(baseline_loss):
        oos_increment = np.nan
        scores["oos_increment"] = np.nan
    else:
        oos_increment = (float(baseline_loss) - float(model_loss)) / float(
            baseline_loss
        )
        scores["oos_increment"] = float(
            np.clip(oos_increment / config.full_score_oos_increment, 0.0, 1.0)
        )

    if all(np.isfinite(scores[dimension]) for dimension in _HISTORICAL_DIMENSIONS):
        historical_weight = sum(
            config.weights[dimension] for dimension in _HISTORICAL_DIMENSIONS
        )
        historical_score = (
            sum(
                config.weights[dimension] * scores[dimension]
                for dimension in _HISTORICAL_DIMENSIONS
            )
            / historical_weight
        )
    else:
        historical_score = np.nan
    if all(np.isfinite(scores[dimension]) for dimension in TRANSFERABILITY_DIMENSIONS):
        overall_score = sum(
            config.weights[dimension] * scores[dimension]
            for dimension in TRANSFERABILITY_DIMENSIONS
        )
    else:
        overall_score = np.nan

    distribution_available = row["distribution_status"] == "available"
    support_available = int(row["effective_samples"]) >= config.min_effective_samples
    validation_count = row["oos_validation_count"]
    validation_sufficient = complete and int(validation_count) >= (
        config.min_oos_validation_count
    )
    increment_sufficient = complete and _meets_policy_minimum(
        float(oos_increment),
        config.min_oos_increment,
    )
    baseline_gate_passed = bool(
        distribution_available
        and support_available
        and complete
        and validation_sufficient
        and increment_sufficient
    )

    if complete:
        general_stability_gates_passed = bool(
            all(
                (
                    scores["sign"] >= config.formal_sign_threshold,
                    scores["magnitude"] >= config.formal_magnitude_threshold,
                    scores["constituent"] >= config.formal_constituent_threshold,
                    scores["structural"] >= config.formal_structural_threshold,
                    scores["cycle_confidence"]
                    >= config.formal_cycle_confidence_threshold,
                    scores["channel_confidence"]
                    >= config.formal_channel_confidence_threshold,
                    float(proxy_discount) <= config.formal_proxy_discount_max,
                )
            )
        )
        conditional_context_weakness = bool(
            scores["neighbor"] < config.formal_neighbor_threshold
            or scores["valuation_positioning"]
            < config.formal_valuation_positioning_threshold
        )
        formal_hard_gates_passed = bool(
            general_stability_gates_passed and not conditional_context_weakness
        )
    else:
        general_stability_gates_passed = False
        conditional_context_weakness = False
        formal_hard_gates_passed = False

    reasons: list[TransferabilityReason] = []
    if not distribution_available:
        _append_reason(reasons, TransferabilityReason.DISTRIBUTION_UNAVAILABLE)
    if not support_available:
        _append_reason(
            reasons,
            TransferabilityReason.INSUFFICIENT_EFFECTIVE_SAMPLES,
        )
    if not complete:
        _append_reason(reasons, TransferabilityReason.INCOMPLETE_EVIDENCE)
    else:
        if not validation_sufficient:
            _append_reason(
                reasons,
                TransferabilityReason.INSUFFICIENT_OOS_VALIDATION,
            )
        if float(oos_increment) <= 0.0:
            _append_reason(reasons, TransferabilityReason.BASELINE_NOT_BEATEN)
        if not _meets_policy_minimum(
            float(oos_increment),
            config.min_oos_increment,
        ):
            _append_reason(reasons, TransferabilityReason.LOW_OOS_INCREMENT)
        hard_reason_checks = (
            (
                scores["sign"] < config.formal_sign_threshold,
                TransferabilityReason.LOW_SIGN_STABILITY,
            ),
            (
                scores["magnitude"] < config.formal_magnitude_threshold,
                TransferabilityReason.LOW_MAGNITUDE_STABILITY,
            ),
            (
                scores["neighbor"] < config.formal_neighbor_threshold,
                TransferabilityReason.LOW_NEIGHBOR_SIMILARITY,
            ),
            (
                scores["constituent"] < config.formal_constituent_threshold,
                TransferabilityReason.CONSTITUENT_DRIFT,
            ),
            (
                scores["valuation_positioning"]
                < config.formal_valuation_positioning_threshold,
                TransferabilityReason.VALUATION_POSITIONING_DISTANCE,
            ),
            (
                scores["structural"] < config.formal_structural_threshold,
                TransferabilityReason.STRUCTURAL_BREAK,
            ),
            (
                scores["cycle_confidence"] < config.formal_cycle_confidence_threshold,
                TransferabilityReason.LOW_CYCLE_CONFIDENCE,
            ),
            (
                scores["channel_confidence"]
                < config.formal_channel_confidence_threshold,
                TransferabilityReason.LOW_CHANNEL_CONFIDENCE,
            ),
            (
                float(proxy_discount) > config.formal_proxy_discount_max,
                TransferabilityReason.PROXY_DISCOUNT,
            ),
        )
        for failed, reason in hard_reason_checks:
            if failed:
                _append_reason(reasons, reason)
        if float(overall_score) < config.formal_overall_threshold:
            _append_reason(reasons, TransferabilityReason.LOW_OVERALL_SCORE)

    if (
        not distribution_available
        or not support_available
        or not complete
        or not validation_sufficient
    ):
        status = MappingStatus.UNAVAILABLE
        outcome = TransferabilityReason.OUTCOME_UNAVAILABLE
    elif not baseline_gate_passed:
        status = MappingStatus.RETROSPECTIVE_ONLY
        outcome = TransferabilityReason.OUTCOME_RETROSPECTIVE_ONLY
    elif (
        formal_hard_gates_passed
        and float(overall_score) >= config.formal_overall_threshold
    ):
        status = MappingStatus.FORMAL
        outcome = TransferabilityReason.OUTCOME_FORMAL
    elif (
        general_stability_gates_passed
        and conditional_context_weakness
        and float(overall_score) >= config.conditional_overall_threshold
    ):
        status = MappingStatus.CONDITIONAL
        outcome = TransferabilityReason.OUTCOME_CONDITIONAL
    else:
        status = MappingStatus.RETROSPECTIVE_ONLY
        outcome = TransferabilityReason.OUTCOME_RETROSPECTIVE_ONLY
    _append_reason(reasons, outcome)

    record = {
        "asset_id": row["asset_id"],
        "horizon_months": int(row["horizon_months"]),
        "status": status,
        "overall_score": float(overall_score),
        "historical_score": float(historical_score),
        **{
            f"{dimension}_score": float(scores[dimension])
            for dimension in TRANSFERABILITY_DIMENSIONS
        },
        **{column: row[column] for column in _UNIT_EVIDENCE_COLUMNS},
        "model_oos_loss": row["model_oos_loss"],
        "baseline_oos_loss": row["baseline_oos_loss"],
        "oos_increment": float(oos_increment),
        "oos_validation_count": row["oos_validation_count"],
        "absolute_effective_samples": int(row["absolute_effective_samples"]),
        "excess_effective_samples": int(row["excess_effective_samples"]),
        "effective_samples": int(row["effective_samples"]),
        "absolute_distribution_status": row["absolute_distribution_status"],
        "excess_distribution_status": row["excess_distribution_status"],
        "distribution_status": row["distribution_status"],
        "baseline_gate_passed": baseline_gate_passed,
        "formal_hard_gates_passed": formal_hard_gates_passed,
        "reason_codes": tuple(reasons),
        "evidence_date": row["evidence_date"],
        "validation_end": row["validation_end"],
        "run_id": row["run_id"],
        "as_of": row["as_of"],
        "data_vintage": row["data_vintage"],
        "model_version": row["model_version"],
        "config_hash": config.config_hash,
        "distribution_config_hash": row["distribution_config_hash"],
        "stage1_posterior_date": row["stage1_posterior_date"],
        "stage2_posterior_date": row["stage2_posterior_date"],
        "forecast_origin": row["forecast_origin"],
    }
    return record


def _build_summary(
    distribution_rows: pd.DataFrame,
    evidence: pd.DataFrame,
    config: TransferabilityConfig,
) -> pd.DataFrame:
    merged = distribution_rows.merge(
        evidence,
        on=["asset_id", "horizon_months"],
        how="inner",
        validate="one_to_one",
        sort=False,
    ).sort_values(["asset_id", "horizon_months"], kind="stable")
    records = [
        _score_record(row._asdict(), config) for row in merged.itertuples(index=False)
    ]
    return pd.DataFrame(records, columns=TRANSFERABILITY_SUMMARY_COLUMNS).reset_index(
        drop=True
    )


def _supplied_summary(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("summary must be a pandas DataFrame")
    if tuple(values.columns) != TRANSFERABILITY_SUMMARY_COLUMNS:
        raise ValueError("summary columns do not match the transferability contract")
    frame = (
        values.copy(deep=True)
        .sort_values(
            ["asset_id", "horizon_months"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("summary asset/horizon dimensions must be unique")
    return frame


@dataclass(frozen=True)
class TransferabilityResult:
    """Defensive result rebuilt from retained evidence and distribution inputs."""

    summary: pd.DataFrame
    evidence: pd.DataFrame
    distribution: CurrentDistributionResult
    config: TransferabilityConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, TransferabilityConfig):
            raise TypeError("config must be a TransferabilityConfig")
        distribution_rows = _distribution_rows(self.distribution)
        evidence = _normalize_evidence(
            object.__getattribute__(self, "evidence"),
            distribution_rows,
        )
        expected = _build_summary(distribution_rows, evidence, self.config)
        supplied = _supplied_summary(object.__getattribute__(self, "summary"))
        try:
            pd.testing.assert_frame_equal(
                supplied,
                expected,
                check_dtype=True,
                check_exact=True,
            )
        except AssertionError as error:
            raise ValueError(
                "summary is inconsistent with recomputed retained inputs"
            ) from error
        object.__setattr__(self, "summary", expected.copy(deep=True))
        object.__setattr__(self, "evidence", evidence.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def score_transferability(
    distribution: CurrentDistributionResult,
    evidence: pd.DataFrame,
    config: TransferabilityConfig | None = None,
) -> TransferabilityResult:
    """Score current-distribution transferability without caller-supplied gates."""

    if not isinstance(distribution, CurrentDistributionResult):
        raise TypeError("distribution must be a CurrentDistributionResult")
    if config is None:
        normalized_config = TransferabilityConfig()
    elif isinstance(config, TransferabilityConfig):
        normalized_config = config
    else:
        raise TypeError("config must be a TransferabilityConfig or None")
    distribution_rows = _distribution_rows(distribution)
    normalized_evidence = _normalize_evidence(evidence, distribution_rows)
    summary = _build_summary(
        distribution_rows,
        normalized_evidence,
        normalized_config,
    )
    return TransferabilityResult(
        summary=summary,
        evidence=normalized_evidence,
        distribution=distribution,
        config=normalized_config,
    )


__all__ = [
    "TRANSFERABILITY_DIMENSIONS",
    "TRANSFERABILITY_EVIDENCE_COLUMNS",
    "TRANSFERABILITY_SUMMARY_COLUMNS",
    "TransferabilityConfig",
    "TransferabilityReason",
    "TransferabilityResult",
    "score_transferability",
]
