"""Confidence-aware bounded research weight ranges."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import hashlib
import json
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.mapping.distribution import (
    HORIZONS,
    CurrentDistributionResult,
)
from seven_cycle_platform.mapping.transferability import TransferabilityResult
from seven_cycle_platform.storage import RUN_ID_PATTERN
from seven_cycle_platform.types import MappingStatus


WEIGHT_POLICY_COLUMNS = (
    "asset_id",
    "horizon_months",
    "neutral_min_weight",
    "neutral_max_weight",
    "max_active_tilt",
    "active_risk_budget_cap",
    "model_disagreement",
    "leveraged",
    "liquidity_constrained",
    "currency_exposed",
    "policy_date",
    "policy_version",
)
WEIGHT_RANGE_POLICY_COLUMNS = WEIGHT_POLICY_COLUMNS

STANDALONE_RESEARCH_SCOPE = (
    "standalone_research_guidance_not_jointly_optimized_or_executable"
)

WEIGHT_RANGE_SUMMARY_COLUMNS = (
    "asset_id",
    "horizon_months",
    "range_status",
    "min_weight",
    "max_weight",
    "neutral_min_weight",
    "neutral_max_weight",
    "neutral_range_width",
    "expected_excess_return",
    "cvar95",
    "drawdown_q95",
    "downside_risk_metric",
    "downside_risk",
    "downside_risk_floor",
    "effective_downside_scale",
    "distribution_status",
    "distribution_effective_samples",
    "distribution_calibration_version",
    "transferability_score",
    "transferability_status",
    "transferability_reason_codes",
    "proxy_discount",
    "model_disagreement",
    "status_confidence_multiplier",
    "disagreement_confidence_multiplier",
    "confidence_factor",
    "raw_signal",
    "max_signal_active_tilt",
    "unconstrained_center_active_tilt",
    "requested_range_half_expansion",
    "max_active_tilt",
    "active_risk_budget_cap",
    "risk_budget_tilt_cap",
    "effective_active_tilt_cap",
    "lower_active_tilt_limit",
    "upper_active_tilt_limit",
    "max_active_tilt_bound",
    "risk_budget_cap_bound",
    "weight_boundary_bound",
    "lower_active_tilt",
    "upper_active_tilt",
    "range_width",
    "reason_codes",
    "caveat_codes",
    "scope",
    "leveraged",
    "liquidity_constrained",
    "currency_exposed",
    "policy_date",
    "policy_version",
    "policy_hash",
    "transferability_evidence_date",
    "transferability_validation_end",
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "distribution_config_hash",
    "transferability_config_hash",
    "weight_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)

_RESULT_FRAME_FIELDS = frozenset({"summary", "policy"})
_DOWNSIDE_METRICS = frozenset({"cvar95", "drawdown_q95", "max_cvar95_drawdown_q95"})
_DISTRIBUTION_REQUIRED_COLUMNS = (
    "asset_id",
    "horizon_months",
    "return_basis",
    "expected_return",
    "cvar95",
    "drawdown_q95",
    "effective_samples",
    "status",
    "calibration_version",
    "run_id",
    "snapshot_as_of",
    "snapshot_data_vintage",
    "snapshot_model_version",
    "snapshot_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)
_TRANSFERABILITY_REQUIRED_COLUMNS = (
    "asset_id",
    "horizon_months",
    "status",
    "overall_score",
    "proxy_discount",
    "effective_samples",
    "distribution_status",
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
_ALIGNMENT_COLUMNS = (
    "asset_id",
    "horizon_months",
    "expected_excess_return",
    "cvar95",
    "drawdown_q95",
    "distribution_effective_samples",
    "distribution_status",
    "distribution_calibration_version",
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "distribution_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)
_BOUND_TOLERANCE = 1e-12


class WeightRangeReason(StrEnum):
    """Stable machine-readable range availability reasons."""

    RANGE_AVAILABLE = "range_available"
    DISTRIBUTION_UNAVAILABLE = "distribution_unavailable"
    TRANSFERABILITY_RETROSPECTIVE_ONLY = "transferability_retrospective_only"
    TRANSFERABILITY_UNAVAILABLE = "transferability_unavailable"
    TRANSFERABILITY_STATUS_NOT_ELIGIBLE = "transferability_status_not_eligible"
    BELOW_MIN_TRANSFERABILITY_SCORE = "below_min_transferability_score"


class WeightRangeCaveat(StrEnum):
    """Stable machine-readable standalone range caveats."""

    STANDALONE_RESEARCH = "standalone_research_not_jointly_optimized"
    LEVERAGE = "leveraged_asset"
    LIQUIDITY = "liquidity_constrained"
    CURRENCY = "currency_exposed"
    PROXY = "proxy_asset"


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


def _nonnegative_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _positive_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be strictly positive")
    return numeric


def _unit_interval(value: object, *, name: str) -> float:
    numeric = _nonnegative_real(value, name=name)
    if numeric > 1.0:
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
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must contain non-empty trimmed strings")
    return value


def _strict_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must contain booleans")
    return bool(value)


def _date_value(
    value: object, *, name: str, allow_missing: bool = False
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


def _valid_hash(value: object, *, name: str) -> str:
    text = _identifier(value, name=name)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return text


def _dimensions(frame: pd.DataFrame) -> set[tuple[str, int]]:
    return set(
        map(
            tuple,
            frame[["asset_id", "horizon_months"]].to_numpy().tolist(),
        )
    )


def _serialized_hash(payload: object) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class WeightRangeConfig:
    """Immutable confidence, signal, and downside-risk range policy."""

    min_transferability_score: float = 0.60
    formal_confidence_multiplier: float = 1.00
    conditional_confidence_multiplier: float = 0.75
    max_signal_active_tilt: float = 0.20
    downside_risk_floor: float = 0.01
    downside_risk_metric: str = "max_cvar95_drawdown_q95"
    disagreement_range_multiplier: float = 0.50

    def __post_init__(self) -> None:
        minimum = _unit_interval(
            self.min_transferability_score,
            name="min_transferability_score",
        )
        formal = _unit_interval(
            self.formal_confidence_multiplier,
            name="formal_confidence_multiplier",
        )
        conditional = _unit_interval(
            self.conditional_confidence_multiplier,
            name="conditional_confidence_multiplier",
        )
        if conditional > formal:
            raise ValueError(
                "conditional_confidence_multiplier cannot exceed "
                "formal_confidence_multiplier"
            )
        maximum_signal = _unit_interval(
            self.max_signal_active_tilt,
            name="max_signal_active_tilt",
        )
        risk_floor = _positive_real(
            self.downside_risk_floor,
            name="downside_risk_floor",
        )
        metric = _identifier(
            self.downside_risk_metric,
            name="downside_risk_metric",
        )
        if metric not in _DOWNSIDE_METRICS:
            raise ValueError(
                "downside_risk_metric must be cvar95, drawdown_q95, or "
                "max_cvar95_drawdown_q95"
            )
        disagreement_multiplier = _nonnegative_real(
            self.disagreement_range_multiplier,
            name="disagreement_range_multiplier",
        )
        object.__setattr__(self, "min_transferability_score", minimum)
        object.__setattr__(self, "formal_confidence_multiplier", formal)
        object.__setattr__(self, "conditional_confidence_multiplier", conditional)
        object.__setattr__(self, "max_signal_active_tilt", maximum_signal)
        object.__setattr__(self, "downside_risk_floor", risk_floor)
        object.__setattr__(self, "downside_risk_metric", metric)
        object.__setattr__(
            self,
            "disagreement_range_multiplier",
            disagreement_multiplier,
        )

    @property
    def config_hash(self) -> str:
        return _serialized_hash(
            {
                "min_transferability_score": self.min_transferability_score,
                "formal_confidence_multiplier": self.formal_confidence_multiplier,
                "conditional_confidence_multiplier": (
                    self.conditional_confidence_multiplier
                ),
                "max_signal_active_tilt": self.max_signal_active_tilt,
                "downside_risk_floor": self.downside_risk_floor,
                "downside_risk_metric": self.downside_risk_metric,
                "disagreement_range_multiplier": (self.disagreement_range_multiplier),
            }
        )


def _validated_distribution(distribution: object) -> CurrentDistributionResult:
    if not isinstance(distribution, CurrentDistributionResult):
        raise TypeError("distribution must be a CurrentDistributionResult")
    try:
        return CurrentDistributionResult(
            summary=distribution.summary,
            monthly_draws=distribution.monthly_draws,
            draws=distribution.draws,
            config=distribution.config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "distribution has inconsistent retained distribution inputs"
        ) from error


def _distribution_rows_from_validated(
    distribution: CurrentDistributionResult,
) -> pd.DataFrame:
    summary = distribution.summary
    if not isinstance(summary, pd.DataFrame):
        raise TypeError("distribution.summary must be a pandas DataFrame")
    missing = set(_DISTRIBUTION_REQUIRED_COLUMNS) - set(summary.columns)
    if missing:
        raise ValueError("distribution summary is missing required columns")
    frame = summary.loc[:, _DISTRIBUTION_REQUIRED_COLUMNS].copy(deep=True)
    if frame.empty:
        raise ValueError("distribution summary cannot be empty")
    frame["asset_id"] = [
        _identifier(value, name="distribution asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _positive_integer(value, name="distribution horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError("distribution horizons must be supported 3/6/12 values")
    frame["return_basis"] = [
        _identifier(value, name="distribution return_basis")
        for value in frame["return_basis"].tolist()
    ]
    if frame.duplicated(["asset_id", "horizon_months", "return_basis"]).any():
        raise ValueError("distribution asset/horizon/basis dimensions must be unique")
    for _, asset_rows in frame.groupby("asset_id", sort=False):
        if set(asset_rows["horizon_months"]) != set(HORIZONS):
            raise ValueError("distribution must exactly cover 3/6/12 for every asset")
        for _, horizon_rows in asset_rows.groupby("horizon_months", sort=False):
            if len(horizon_rows) != 2 or set(horizon_rows["return_basis"]) != {
                "absolute",
                "excess",
            }:
                raise ValueError(
                    "distribution must retain one absolute and one excess row"
                )

    frame["effective_samples"] = [
        _nonnegative_integer(value, name="distribution effective_samples")
        for value in frame["effective_samples"].tolist()
    ]
    statuses: list[str] = []
    for value in frame["status"].tolist():
        status = _identifier(value, name="distribution status")
        if status not in {"available", "unavailable"}:
            raise ValueError("distribution status is invalid")
        statuses.append(status)
    frame["status"] = statuses
    frame["calibration_version"] = [
        _identifier(value, name="distribution calibration_version")
        for value in frame["calibration_version"].tolist()
    ]
    for column in (
        "snapshot_as_of",
        "snapshot_data_vintage",
        "stage1_posterior_date",
        "stage2_posterior_date",
        "forecast_origin",
    ):
        frame[column] = [
            _date_value(value, name=f"distribution {column}")
            for value in frame[column].tolist()
        ]
    for column in ("run_id", "snapshot_model_version", "snapshot_config_hash"):
        frame[column] = [
            _identifier(value, name=f"distribution {column}")
            for value in frame[column].tolist()
        ]
    provenance_columns = (
        "run_id",
        "snapshot_as_of",
        "snapshot_data_vintage",
        "snapshot_model_version",
        "snapshot_config_hash",
        "stage1_posterior_date",
        "stage2_posterior_date",
        "forecast_origin",
    )
    if any(frame[column].nunique(dropna=False) != 1 for column in provenance_columns):
        raise ValueError("distribution provenance must be constant")
    run_id = str(frame["run_id"].iloc[0])
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("distribution run_id provenance is invalid")
    config_hash = _valid_hash(
        frame["snapshot_config_hash"].iloc[0],
        name="distribution config hash",
    )
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

    excess = frame.loc[frame["return_basis"].eq("excess")].copy(deep=True)
    expected_returns: list[float] = []
    cvars: list[float] = []
    drawdowns: list[float] = []
    for row in excess.itertuples(index=False):
        if row.status == "available":
            expected_returns.append(
                _finite_real(
                    row.expected_return,
                    name="distribution expected excess return",
                )
            )
            cvars.append(
                _nonnegative_real(row.cvar95, name="distribution excess cvar95")
            )
            drawdowns.append(
                _unit_interval(
                    row.drawdown_q95,
                    name="distribution excess drawdown_q95",
                )
            )
        else:
            if not all(
                _is_missing(value)
                for value in (row.expected_return, row.cvar95, row.drawdown_q95)
            ):
                raise ValueError(
                    "unavailable distribution excess metrics must be missing"
                )
            expected_returns.append(np.nan)
            cvars.append(np.nan)
            drawdowns.append(np.nan)
    excess["expected_return"] = expected_returns
    excess["cvar95"] = cvars
    excess["drawdown_q95"] = drawdowns
    renamed = excess.rename(
        columns={
            "expected_return": "expected_excess_return",
            "effective_samples": "distribution_effective_samples",
            "status": "distribution_status",
            "calibration_version": "distribution_calibration_version",
            "snapshot_as_of": "as_of",
            "snapshot_data_vintage": "data_vintage",
            "snapshot_model_version": "model_version",
            "snapshot_config_hash": "distribution_config_hash",
        }
    )
    renamed["distribution_config_hash"] = config_hash
    return (
        renamed.loc[:, _ALIGNMENT_COLUMNS]
        .sort_values(["asset_id", "horizon_months"], kind="stable")
        .reset_index(drop=True)
    )


def _distribution_rows(distribution: object) -> pd.DataFrame:
    return _distribution_rows_from_validated(_validated_distribution(distribution))


def _validated_transferability(
    transferability: object,
) -> TransferabilityResult:
    if not isinstance(transferability, TransferabilityResult):
        raise TypeError("transferability must be a TransferabilityResult")
    try:
        return TransferabilityResult(
            summary=transferability.summary,
            evidence=transferability.evidence,
            distribution=transferability.distribution,
            config=transferability.config,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "transferability retained inputs or summary are inconsistent"
        ) from error


def _transferability_rows(
    transferability: object,
    distribution_rows: pd.DataFrame,
) -> pd.DataFrame:
    validated = _validated_transferability(transferability)
    validated_nested_distribution = _validated_distribution(validated.distribution)
    nested_distribution_rows = _distribution_rows_from_validated(
        validated_nested_distribution
    )
    try:
        pd.testing.assert_frame_equal(
            nested_distribution_rows.loc[:, _ALIGNMENT_COLUMNS],
            distribution_rows.loc[:, _ALIGNMENT_COLUMNS],
            check_dtype=True,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(
            "distribution and transferability inputs do not align"
        ) from error

    summary = validated.summary
    missing = set(_TRANSFERABILITY_REQUIRED_COLUMNS) - set(summary.columns)
    if missing:
        raise ValueError("transferability summary is missing required columns")
    frame = summary.loc[:, _TRANSFERABILITY_REQUIRED_COLUMNS].copy(deep=True)
    frame["asset_id"] = [
        _identifier(value, name="transferability asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _positive_integer(value, name="transferability horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError("transferability horizons must be supported 3/6/12 values")
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("transferability asset/horizon dimensions must be unique")
    if _dimensions(frame) != _dimensions(distribution_rows):
        raise ValueError(
            "transferability asset/horizon dimensions must align with distribution"
        )

    statuses: list[str] = []
    scores: list[float] = []
    proxy_discounts: list[float] = []
    for status_value, score_value, proxy_value in zip(
        frame["status"].tolist(),
        frame["overall_score"].tolist(),
        frame["proxy_discount"].tolist(),
        strict=True,
    ):
        status = _identifier(status_value, name="transferability status")
        if status not in {member.value for member in MappingStatus}:
            raise ValueError("transferability status is invalid")
        statuses.append(status)
        scores.append(
            np.nan
            if _is_missing(score_value)
            else _unit_interval(score_value, name="transferability overall_score")
        )
        proxy_discounts.append(
            np.nan
            if _is_missing(proxy_value)
            else _unit_interval(proxy_value, name="transferability proxy_discount")
        )
    frame["status"] = statuses
    frame["overall_score"] = scores
    frame["proxy_discount"] = proxy_discounts
    frame["effective_samples"] = [
        _nonnegative_integer(value, name="transferability effective_samples")
        for value in frame["effective_samples"].tolist()
    ]
    distribution_statuses: list[str] = []
    for value in frame["distribution_status"].tolist():
        status = _identifier(value, name="transferability distribution_status")
        if status not in {"available", "unavailable"}:
            raise ValueError("transferability distribution_status is invalid")
        distribution_statuses.append(status)
    frame["distribution_status"] = distribution_statuses
    for column in (
        "evidence_date",
        "validation_end",
        "as_of",
        "data_vintage",
        "stage1_posterior_date",
        "stage2_posterior_date",
        "forecast_origin",
    ):
        frame[column] = [
            _date_value(
                value,
                name=f"transferability {column}",
                allow_missing=column in {"evidence_date", "validation_end"},
            )
            for value in frame[column].tolist()
        ]
    for column in (
        "run_id",
        "model_version",
        "config_hash",
        "distribution_config_hash",
    ):
        frame[column] = [
            _identifier(value, name=f"transferability {column}")
            for value in frame[column].tolist()
        ]
    if any(
        frame[column].nunique(dropna=False) != 1
        for column in (
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
    ):
        raise ValueError("transferability provenance must be constant")
    if RUN_ID_PATTERN.fullmatch(str(frame["run_id"].iloc[0])) is None:
        raise ValueError("transferability run_id provenance is invalid")
    transferability_hash = _valid_hash(
        frame["config_hash"].iloc[0],
        name="transferability config hash",
    )
    if transferability_hash != validated.config.config_hash:
        raise ValueError("transferability config hash provenance is inconsistent")
    _valid_hash(
        frame["distribution_config_hash"].iloc[0],
        name="transferability distribution config hash",
    )

    aligned = frame.merge(
        distribution_rows,
        on=["asset_id", "horizon_months"],
        how="inner",
        validate="one_to_one",
        suffixes=("_transferability", "_distribution"),
        sort=False,
    )
    provenance_pairs = (
        ("run_id_transferability", "run_id_distribution"),
        ("as_of_transferability", "as_of_distribution"),
        ("data_vintage_transferability", "data_vintage_distribution"),
        ("model_version_transferability", "model_version_distribution"),
        (
            "distribution_config_hash_transferability",
            "distribution_config_hash_distribution",
        ),
        ("stage1_posterior_date_transferability", "stage1_posterior_date_distribution"),
        ("stage2_posterior_date_transferability", "stage2_posterior_date_distribution"),
        ("forecast_origin_transferability", "forecast_origin_distribution"),
        ("distribution_status_transferability", "distribution_status_distribution"),
    )
    if any(
        not aligned[left].equals(aligned[right]) for left, right in provenance_pairs
    ):
        raise ValueError(
            "distribution and transferability provenance must align exactly"
        )

    return (
        frame.rename(
            columns={
                "status": "transferability_status",
                "overall_score": "transferability_score",
                "reason_codes": "transferability_reason_codes",
                "evidence_date": "transferability_evidence_date",
                "validation_end": "transferability_validation_end",
                "config_hash": "transferability_config_hash",
            }
        )[
            [
                "asset_id",
                "horizon_months",
                "transferability_status",
                "transferability_score",
                "transferability_reason_codes",
                "proxy_discount",
                "transferability_evidence_date",
                "transferability_validation_end",
                "transferability_config_hash",
            ]
        ]
        .sort_values(["asset_id", "horizon_months"], kind="stable")
        .reset_index(drop=True)
    )


def _policy_hash(policy: pd.DataFrame) -> str:
    records: list[dict[str, object]] = []
    for row in policy.itertuples(index=False):
        records.append(
            {
                "asset_id": row.asset_id,
                "horizon_months": int(row.horizon_months),
                "neutral_min_weight": float(row.neutral_min_weight),
                "neutral_max_weight": float(row.neutral_max_weight),
                "max_active_tilt": float(row.max_active_tilt),
                "active_risk_budget_cap": float(row.active_risk_budget_cap),
                "model_disagreement": float(row.model_disagreement),
                "leveraged": bool(row.leveraged),
                "liquidity_constrained": bool(row.liquidity_constrained),
                "currency_exposed": bool(row.currency_exposed),
                "policy_date": row.policy_date.isoformat(),
                "policy_version": row.policy_version,
            }
        )
    return _serialized_hash({"columns": WEIGHT_POLICY_COLUMNS, "records": records})


def _normalize_policy(
    policy: object,
    distribution_rows: pd.DataFrame,
) -> pd.DataFrame:
    if not isinstance(policy, pd.DataFrame):
        raise TypeError("policy must be a pandas DataFrame")
    missing = set(WEIGHT_POLICY_COLUMNS) - set(policy.columns)
    if missing:
        raise ValueError("policy is missing required columns")
    optional_columns = tuple(
        column
        for column in ("run_id", "as_of", "distribution_config_hash")
        if column in policy.columns
    )
    frame = policy.loc[:, WEIGHT_POLICY_COLUMNS + optional_columns].copy(deep=True)
    frame["asset_id"] = [
        _identifier(value, name="policy asset_id")
        for value in frame["asset_id"].tolist()
    ]
    frame["horizon_months"] = [
        _positive_integer(value, name="policy horizon_months")
        for value in frame["horizon_months"].tolist()
    ]
    if not set(frame["horizon_months"]).issubset(set(HORIZONS)):
        raise ValueError("policy horizons must use supported 3/6/12 values")
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("policy asset/horizon dimensions must be unique")
    if _dimensions(frame) != _dimensions(distribution_rows):
        raise ValueError(
            "policy asset/horizon coverage must exactly align with distribution"
        )

    for column in ("neutral_min_weight", "neutral_max_weight"):
        frame[column] = [
            _unit_interval(value, name=f"policy {column}")
            for value in frame[column].tolist()
        ]
    if bool((frame["neutral_min_weight"] >= frame["neutral_max_weight"]).any()):
        raise ValueError("policy neutral min must be strictly below neutral max")
    for column in ("max_active_tilt", "active_risk_budget_cap"):
        frame[column] = [
            _nonnegative_real(value, name=f"policy {column}")
            for value in frame[column].tolist()
        ]
    frame["model_disagreement"] = [
        _unit_interval(value, name="policy model_disagreement")
        for value in frame["model_disagreement"].tolist()
    ]
    for column in ("leveraged", "liquidity_constrained", "currency_exposed"):
        frame[column] = [
            _strict_bool(value, name=f"policy {column}")
            for value in frame[column].tolist()
        ]
    frame["policy_date"] = [
        _date_value(value, name="policy policy_date")
        for value in frame["policy_date"].tolist()
    ]
    frame["policy_version"] = [
        _identifier(value, name="policy policy_version")
        for value in frame["policy_version"].tolist()
    ]

    run_id = str(distribution_rows["run_id"].iloc[0])
    as_of = distribution_rows["as_of"].iloc[0]
    distribution_hash = str(distribution_rows["distribution_config_hash"].iloc[0])
    if any(policy_date > as_of for policy_date in frame["policy_date"].tolist()):
        raise ValueError("policy_date cannot follow distribution as_of")
    if "run_id" in frame:
        supplied = [
            _identifier(value, name="policy run_id")
            for value in frame["run_id"].tolist()
        ]
        if any(value != run_id for value in supplied):
            raise ValueError("policy run_id provenance must align with distribution")
    if "as_of" in frame:
        supplied_dates = [
            _date_value(value, name="policy as_of") for value in frame["as_of"].tolist()
        ]
        if any(value != as_of for value in supplied_dates):
            raise ValueError("policy as_of provenance must align with distribution")
    if "distribution_config_hash" in frame:
        supplied_hashes = [
            _valid_hash(value, name="policy distribution_config_hash")
            for value in frame["distribution_config_hash"].tolist()
        ]
        if any(value != distribution_hash for value in supplied_hashes):
            raise ValueError(
                "policy distribution config provenance must align with distribution"
            )
    return (
        frame.loc[:, WEIGHT_POLICY_COLUMNS]
        .sort_values(["asset_id", "horizon_months"], kind="stable")
        .reset_index(drop=True)
    )


def _downside_risk(row: dict[str, object], config: WeightRangeConfig) -> float:
    cvar95 = float(row["cvar95"])
    drawdown_q95 = float(row["drawdown_q95"])
    if config.downside_risk_metric == "cvar95":
        return cvar95
    if config.downside_risk_metric == "drawdown_q95":
        return drawdown_q95
    return max(cvar95, drawdown_q95)


def _status_multiplier(status: str, config: WeightRangeConfig) -> float:
    if status == MappingStatus.FORMAL:
        return config.formal_confidence_multiplier
    if status == MappingStatus.CONDITIONAL:
        return config.conditional_confidence_multiplier
    return 0.0


def _reason_codes(
    row: dict[str, object], config: WeightRangeConfig
) -> tuple[WeightRangeReason, ...]:
    reasons: list[WeightRangeReason] = []
    if row["distribution_status"] != "available":
        reasons.append(WeightRangeReason.DISTRIBUTION_UNAVAILABLE)
    status = str(row["transferability_status"])
    if status == MappingStatus.RETROSPECTIVE_ONLY:
        reasons.append(WeightRangeReason.TRANSFERABILITY_RETROSPECTIVE_ONLY)
    elif status == MappingStatus.UNAVAILABLE:
        reasons.append(WeightRangeReason.TRANSFERABILITY_UNAVAILABLE)
    elif status not in {MappingStatus.FORMAL, MappingStatus.CONDITIONAL}:
        reasons.append(WeightRangeReason.TRANSFERABILITY_STATUS_NOT_ELIGIBLE)
    score = row["transferability_score"]
    if not _is_missing(score) and float(score) < config.min_transferability_score:
        reasons.append(WeightRangeReason.BELOW_MIN_TRANSFERABILITY_SCORE)
    if not reasons:
        reasons.append(WeightRangeReason.RANGE_AVAILABLE)
    return tuple(reasons)


def _caveat_codes(row: dict[str, object]) -> tuple[WeightRangeCaveat, ...]:
    caveats = [WeightRangeCaveat.STANDALONE_RESEARCH]
    if bool(row["leveraged"]):
        caveats.append(WeightRangeCaveat.LEVERAGE)
    if bool(row["liquidity_constrained"]):
        caveats.append(WeightRangeCaveat.LIQUIDITY)
    if bool(row["currency_exposed"]):
        caveats.append(WeightRangeCaveat.CURRENCY)
    proxy_discount = row["proxy_discount"]
    if not _is_missing(proxy_discount) and float(proxy_discount) > 0.0:
        caveats.append(WeightRangeCaveat.PROXY)
    return tuple(caveats)


def _range_record(
    row: dict[str, object],
    *,
    config: WeightRangeConfig,
    policy_hash: str,
) -> dict[str, object]:
    neutral_min = float(row["neutral_min_weight"])
    neutral_max = float(row["neutral_max_weight"])
    neutral_width = neutral_max - neutral_min
    disagreement = float(row["model_disagreement"])
    transferability_score = row["transferability_score"]
    transferability_status = str(row["transferability_status"])
    status_multiplier = _status_multiplier(transferability_status, config)
    disagreement_multiplier = 1.0 - disagreement
    confidence_factor = (
        0.0
        if _is_missing(transferability_score)
        else float(transferability_score) * status_multiplier * disagreement_multiplier
    )
    reasons = _reason_codes(row, config)
    eligible = reasons == (WeightRangeReason.RANGE_AVAILABLE,)
    caveats = _caveat_codes(row)

    if row["distribution_status"] == "available":
        downside_risk = _downside_risk(row, config)
        effective_downside_scale = max(
            downside_risk,
            config.downside_risk_floor,
        )
        raw_signal = float(
            np.tanh(float(row["expected_excess_return"]) / effective_downside_scale)
        )
        risk_budget_tilt_cap = (
            float(row["active_risk_budget_cap"]) / effective_downside_scale
        )
        effective_active_tilt_cap = min(
            float(row["max_active_tilt"]),
            risk_budget_tilt_cap,
        )
        lower_active_tilt_limit = max(
            -effective_active_tilt_cap,
            -neutral_min,
        )
        upper_active_tilt_limit = min(
            effective_active_tilt_cap,
            1.0 - neutral_max,
        )
        unconstrained_center = (
            config.max_signal_active_tilt * raw_signal * confidence_factor
        )
        score_for_expansion = (
            0.0 if _is_missing(transferability_score) else float(transferability_score)
        )
        requested_expansion = (
            config.max_signal_active_tilt
            * abs(raw_signal)
            * score_for_expansion
            * status_multiplier
            * disagreement
            * config.disagreement_range_multiplier
        )
    else:
        downside_risk = np.nan
        effective_downside_scale = np.nan
        raw_signal = np.nan
        risk_budget_tilt_cap = np.nan
        effective_active_tilt_cap = np.nan
        lower_active_tilt_limit = np.nan
        upper_active_tilt_limit = np.nan
        unconstrained_center = np.nan
        requested_expansion = np.nan

    if eligible:
        requested_lower = unconstrained_center - requested_expansion
        requested_upper = unconstrained_center + requested_expansion
        max_active_tilt = float(row["max_active_tilt"])
        max_active_tilt_bound = bool(
            max_active_tilt <= risk_budget_tilt_cap + _BOUND_TOLERANCE
            and (
                requested_lower < -max_active_tilt - _BOUND_TOLERANCE
                or requested_upper > max_active_tilt + _BOUND_TOLERANCE
            )
        )
        risk_budget_cap_bound = bool(
            risk_budget_tilt_cap <= max_active_tilt + _BOUND_TOLERANCE
            and (
                requested_lower < -risk_budget_tilt_cap - _BOUND_TOLERANCE
                or requested_upper > risk_budget_tilt_cap + _BOUND_TOLERANCE
            )
        )
        active_lower = float(
            np.clip(
                requested_lower,
                -effective_active_tilt_cap,
                effective_active_tilt_cap,
            )
        )
        active_upper = float(
            np.clip(
                requested_upper,
                -effective_active_tilt_cap,
                effective_active_tilt_cap,
            )
        )
        weight_boundary_bound = bool(
            active_lower < -neutral_min - _BOUND_TOLERANCE
            or active_upper > 1.0 - neutral_max + _BOUND_TOLERANCE
        )
        lower_active_tilt = float(
            np.clip(
                active_lower,
                lower_active_tilt_limit,
                upper_active_tilt_limit,
            )
        )
        upper_active_tilt = float(
            np.clip(
                active_upper,
                lower_active_tilt_limit,
                upper_active_tilt_limit,
            )
        )
        min_weight = neutral_min + lower_active_tilt
        max_weight = neutral_max + upper_active_tilt
        range_width = max_weight - min_weight
        if not 0.0 <= min_weight < max_weight <= 1.0:
            raise ValueError("derived available weight range is invalid")
        if range_width + _BOUND_TOLERANCE < neutral_width:
            raise ValueError("derived range cannot be narrower than neutral range")
        range_status = "available"
    else:
        max_active_tilt_bound = False
        risk_budget_cap_bound = False
        weight_boundary_bound = False
        lower_active_tilt = np.nan
        upper_active_tilt = np.nan
        min_weight = np.nan
        max_weight = np.nan
        range_width = np.nan
        range_status = "unavailable"

    return {
        "asset_id": row["asset_id"],
        "horizon_months": int(row["horizon_months"]),
        "range_status": range_status,
        "min_weight": min_weight,
        "max_weight": max_weight,
        "neutral_min_weight": neutral_min,
        "neutral_max_weight": neutral_max,
        "neutral_range_width": neutral_width,
        "expected_excess_return": row["expected_excess_return"],
        "cvar95": row["cvar95"],
        "drawdown_q95": row["drawdown_q95"],
        "downside_risk_metric": config.downside_risk_metric,
        "downside_risk": downside_risk,
        "downside_risk_floor": config.downside_risk_floor,
        "effective_downside_scale": effective_downside_scale,
        "distribution_status": row["distribution_status"],
        "distribution_effective_samples": int(row["distribution_effective_samples"]),
        "distribution_calibration_version": row["distribution_calibration_version"],
        "transferability_score": row["transferability_score"],
        "transferability_status": row["transferability_status"],
        "transferability_reason_codes": row["transferability_reason_codes"],
        "proxy_discount": row["proxy_discount"],
        "model_disagreement": disagreement,
        "status_confidence_multiplier": status_multiplier,
        "disagreement_confidence_multiplier": disagreement_multiplier,
        "confidence_factor": confidence_factor,
        "raw_signal": raw_signal,
        "max_signal_active_tilt": config.max_signal_active_tilt,
        "unconstrained_center_active_tilt": unconstrained_center,
        "requested_range_half_expansion": requested_expansion,
        "max_active_tilt": row["max_active_tilt"],
        "active_risk_budget_cap": row["active_risk_budget_cap"],
        "risk_budget_tilt_cap": risk_budget_tilt_cap,
        "effective_active_tilt_cap": effective_active_tilt_cap,
        "lower_active_tilt_limit": lower_active_tilt_limit,
        "upper_active_tilt_limit": upper_active_tilt_limit,
        "max_active_tilt_bound": max_active_tilt_bound,
        "risk_budget_cap_bound": risk_budget_cap_bound,
        "weight_boundary_bound": weight_boundary_bound,
        "lower_active_tilt": lower_active_tilt,
        "upper_active_tilt": upper_active_tilt,
        "range_width": range_width,
        "reason_codes": reasons,
        "caveat_codes": caveats,
        "scope": STANDALONE_RESEARCH_SCOPE,
        "leveraged": row["leveraged"],
        "liquidity_constrained": row["liquidity_constrained"],
        "currency_exposed": row["currency_exposed"],
        "policy_date": row["policy_date"],
        "policy_version": row["policy_version"],
        "policy_hash": policy_hash,
        "transferability_evidence_date": row["transferability_evidence_date"],
        "transferability_validation_end": row["transferability_validation_end"],
        "run_id": row["run_id"],
        "as_of": row["as_of"],
        "data_vintage": row["data_vintage"],
        "model_version": row["model_version"],
        "distribution_config_hash": row["distribution_config_hash"],
        "transferability_config_hash": row["transferability_config_hash"],
        "weight_config_hash": config.config_hash,
        "stage1_posterior_date": row["stage1_posterior_date"],
        "stage2_posterior_date": row["stage2_posterior_date"],
        "forecast_origin": row["forecast_origin"],
    }


def _build_summary(
    distribution_rows: pd.DataFrame,
    transferability_rows: pd.DataFrame,
    policy: pd.DataFrame,
    config: WeightRangeConfig,
) -> pd.DataFrame:
    merged = (
        distribution_rows.merge(
            transferability_rows,
            on=["asset_id", "horizon_months"],
            how="inner",
            validate="one_to_one",
            sort=False,
        )
        .merge(
            policy,
            on=["asset_id", "horizon_months"],
            how="inner",
            validate="one_to_one",
            sort=False,
        )
        .sort_values(["asset_id", "horizon_months"], kind="stable")
        .reset_index(drop=True)
    )
    policy_hash = _policy_hash(policy)
    records = [
        _range_record(row._asdict(), config=config, policy_hash=policy_hash)
        for row in merged.itertuples(index=False)
    ]
    return pd.DataFrame(records, columns=WEIGHT_RANGE_SUMMARY_COLUMNS)


def _supplied_summary(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("summary must be a pandas DataFrame")
    if tuple(values.columns) != WEIGHT_RANGE_SUMMARY_COLUMNS:
        raise ValueError("summary columns do not match the weight-range contract")
    frame = (
        values.copy(deep=True)
        .sort_values(["asset_id", "horizon_months"], kind="stable")
        .reset_index(drop=True)
    )
    if frame.duplicated(["asset_id", "horizon_months"]).any():
        raise ValueError("summary asset/horizon dimensions must be unique")
    return frame


@dataclass(frozen=True)
class WeightRangeResult:
    """Defensive ranges rebuilt from retained governed inputs."""

    summary: pd.DataFrame
    policy: pd.DataFrame
    distribution: CurrentDistributionResult
    transferability: TransferabilityResult
    config: WeightRangeConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, WeightRangeConfig):
            raise TypeError("config must be a WeightRangeConfig")
        validated_distribution = _validated_distribution(self.distribution)
        distribution_rows = _distribution_rows_from_validated(validated_distribution)
        transferability_rows = _transferability_rows(
            self.transferability,
            distribution_rows,
        )
        policy = _normalize_policy(
            object.__getattribute__(self, "policy"),
            distribution_rows,
        )
        expected = _build_summary(
            distribution_rows,
            transferability_rows,
            policy,
            self.config,
        )
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
        object.__setattr__(self, "policy", policy.copy(deep=True))
        object.__setattr__(self, "distribution", validated_distribution)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    @property
    def policy_hash(self) -> str:
        return _policy_hash(object.__getattribute__(self, "policy"))


def suggest_weight_ranges(
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    policy: pd.DataFrame,
    config: WeightRangeConfig | None = None,
) -> WeightRangeResult:
    """Derive standalone bounded ranges without portfolio normalization."""

    if not isinstance(distribution, CurrentDistributionResult):
        raise TypeError("distribution must be a CurrentDistributionResult")
    if not isinstance(transferability, TransferabilityResult):
        raise TypeError("transferability must be a TransferabilityResult")
    if config is None:
        normalized_config = WeightRangeConfig()
    elif isinstance(config, WeightRangeConfig):
        normalized_config = config
    else:
        raise TypeError("config must be a WeightRangeConfig or None")
    validated_distribution = _validated_distribution(distribution)
    distribution_rows = _distribution_rows_from_validated(validated_distribution)
    transferability_rows = _transferability_rows(
        transferability,
        distribution_rows,
    )
    normalized_policy = _normalize_policy(policy, distribution_rows)
    summary = _build_summary(
        distribution_rows,
        transferability_rows,
        normalized_policy,
        normalized_config,
    )
    return WeightRangeResult(
        summary=summary,
        policy=normalized_policy,
        distribution=validated_distribution,
        transferability=transferability,
        config=normalized_config,
    )


derive_weight_ranges = suggest_weight_ranges


__all__ = [
    "STANDALONE_RESEARCH_SCOPE",
    "WEIGHT_POLICY_COLUMNS",
    "WEIGHT_RANGE_POLICY_COLUMNS",
    "WEIGHT_RANGE_SUMMARY_COLUMNS",
    "WeightRangeCaveat",
    "WeightRangeConfig",
    "WeightRangeReason",
    "WeightRangeResult",
    "derive_weight_ranges",
    "suggest_weight_ranges",
]
