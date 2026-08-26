"""Pluggable, point-in-time forecast model contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import inspect
import math
from numbers import Integral, Real
from typing import (
    Callable,
    Literal,
    Protocol,
    Sequence,
    TypeGuard,
    cast,
    get_type_hints,
    runtime_checkable,
)

import numpy as np
import pandas as pd


ModelRole = Literal["champion", "challenger"]
ForecastScope = Literal["cycle", "channel"]
PredictionScope = ForecastScope
AuditStatus = Literal["passed", "failed"]
SeedPolicy = Literal[
    "fixed",
    "fixed_seed",
    "matched",
    "model_specific",
    "derived_from_train_vintage",
    "hash_derived",
]
DownstreamMappingRequirement = Literal["governed_mapping_required"]
GOVERNED_MAPPING_REQUIRED: DownstreamMappingRequirement = "governed_mapping_required"
GOVERNED_LEAKAGE_CHECKS = (
    "visible_date_lte_as_of",
    "generated_date_lte_as_of",
    "vintage_date_lte_as_of",
)

_DETERMINISTIC_SEED_POLICIES = frozenset(
    {
        "fixed",
        "fixed_seed",
        "matched",
        "model_specific",
        "derived_from_train_vintage",
        "hash_derived",
    }
)


def _normalize_date(value: object, *, name: str) -> date:
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    if not isinstance(value, (str, date, datetime, np.datetime64, pd.Timestamp)):
        raise TypeError(f"{name} must be date-like")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be missing")
    if timestamp.tzinfo is not None:
        raise ValueError(f"{name} must be timezone-naive")
    return timestamp.normalize().date()


def _normalize_text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def _normalize_hash(value: object, *, name: str) -> str:
    normalized = _normalize_text(value, name=name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _normalize_nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return normalized


def _normalize_positive_integer(value: object, *, name: str) -> int:
    normalized = _normalize_nonnegative_integer(value, name=name)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _normalize_boolean(value: object, *, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be boolean")
    return bool(value)


def _normalize_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    return normalized


def _normalize_role(value: object) -> ModelRole:
    role = _normalize_text(value, name="role")
    if role not in {"champion", "challenger"}:
        raise ValueError("role must be champion or challenger")
    return cast(ModelRole, role)


def _normalize_scope(value: object) -> ForecastScope:
    scope = _normalize_text(value, name="scope")
    if scope not in {"cycle", "channel"}:
        raise ValueError("scope must be cycle or channel")
    return cast(ForecastScope, scope)


def _normalize_seed_policy(value: object) -> SeedPolicy:
    policy = _normalize_text(value, name="seed_policy").lower()
    policy = policy.replace("-", "_").replace(" ", "_")
    if policy not in _DETERMINISTIC_SEED_POLICIES:
        raise ValueError("seed_policy must be deterministic")
    return cast(SeedPolicy, policy)


def _normalize_downstream_mapping_requirement(
    value: object,
) -> DownstreamMappingRequirement:
    try:
        requirement = _normalize_text(value, name="downstream_mapping_requirement")
    except (TypeError, ValueError) as error:
        raise ValueError(
            "downstream_mapping_requirement must be governed_mapping_required"
        ) from error
    if requirement != GOVERNED_MAPPING_REQUIRED:
        raise ValueError(
            "downstream_mapping_requirement must be governed_mapping_required"
        )
    return cast(DownstreamMappingRequirement, requirement)


def _normalize_audit_status(value: object) -> AuditStatus:
    status = _normalize_text(value, name="status")
    if status not in {"passed", "failed"}:
        raise ValueError("status must be passed or failed")
    return cast(AuditStatus, status)


def _normalize_text_sequence(
    values: object,
    *,
    name: str,
    allow_empty: bool,
    sort_values: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence of non-empty strings")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(f"{name} must be a sequence of non-empty strings") from error
    normalized = tuple(_normalize_text(value, name=name) for value in supplied)
    if not allow_empty and not normalized:
        raise ValueError(f"{name} cannot be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} cannot contain duplicates")
    if sort_values:
        return tuple(sorted(normalized))
    return normalized


def _normalize_feature_ids(
    values: object,
    *,
    name: str = "feature_ids",
    allow_empty: bool = False,
) -> tuple[str, ...]:
    return _normalize_text_sequence(
        values,
        name=name,
        allow_empty=allow_empty,
        sort_values=True,
    )


def _normalize_horizons(values: object) -> tuple[int, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("horizons must be a sequence of positive integers")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError("horizons must be a sequence of positive integers") from error
    normalized = {
        _normalize_positive_integer(value, name="horizon") for value in supplied
    }
    if not normalized:
        raise ValueError("horizons cannot be empty")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class TrainVintage:
    """Immutable metadata for one point-in-time model fit."""

    train_start: date
    train_end: date
    data_vintage: date
    feature_ids: Sequence[str]
    seed: int
    code_hash: str
    config_hash: str

    def __post_init__(self) -> None:
        train_start = _normalize_date(self.train_start, name="train_start")
        train_end = _normalize_date(self.train_end, name="train_end")
        data_vintage = _normalize_date(self.data_vintage, name="data_vintage")
        if train_start > train_end:
            raise ValueError("train_start cannot follow train_end")
        if train_end > data_vintage:
            raise ValueError("train_end cannot follow data_vintage")
        object.__setattr__(self, "train_start", train_start)
        object.__setattr__(self, "train_end", train_end)
        object.__setattr__(self, "data_vintage", data_vintage)
        object.__setattr__(
            self, "feature_ids", _normalize_feature_ids(self.feature_ids)
        )
        object.__setattr__(
            self,
            "seed",
            _normalize_nonnegative_integer(self.seed, name="seed"),
        )
        object.__setattr__(
            self,
            "code_hash",
            _normalize_hash(self.code_hash, name="code_hash"),
        )
        object.__setattr__(
            self,
            "config_hash",
            _normalize_hash(self.config_hash, name="config_hash"),
        )


TrainingVintage = TrainVintage
TrainingRequest = TrainVintage


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Immutable request for governed cycle or channel horizons."""

    as_of: date
    horizons: Sequence[int]
    scope: ForecastScope

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", _normalize_date(self.as_of, name="as_of"))
        object.__setattr__(self, "horizons", _normalize_horizons(self.horizons))
        object.__setattr__(self, "scope", _normalize_scope(self.scope))


PredictionRequest = ForecastRequest


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One framework-neutral scalar forecast output."""

    target_id: str
    horizon: int
    output_id: str
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id",
            _normalize_text(self.target_id, name="target_id"),
        )
        object.__setattr__(
            self,
            "horizon",
            _normalize_positive_integer(self.horizon, name="horizon"),
        )
        object.__setattr__(
            self,
            "output_id",
            _normalize_text(self.output_id, name="output_id"),
        )
        object.__setattr__(
            self,
            "value",
            _normalize_real(self.value, name="value"),
        )


@dataclass(frozen=True, slots=True)
class PredictionEnvelope:
    """Immutable prediction payload with governed identity and request metadata."""

    request: ForecastRequest
    model_id: str
    version: str
    role: ModelRole
    scope: ForecastScope
    output_contract: str
    predictions: Sequence[ForecastPoint]

    def __post_init__(self) -> None:
        if not isinstance(self.request, ForecastRequest):
            raise TypeError("request must be a ForecastRequest")
        scope = _normalize_scope(self.scope)
        if scope != self.request.scope:
            raise ValueError("prediction scope must match request scope")
        if isinstance(self.predictions, (str, bytes, bytearray)):
            raise TypeError("predictions must be a sequence of ForecastPoint values")
        try:
            predictions = tuple(self.predictions)
        except TypeError as error:
            raise TypeError(
                "predictions must be a sequence of ForecastPoint values"
            ) from error
        if not predictions:
            raise ValueError("predictions cannot be empty")
        if not all(isinstance(point, ForecastPoint) for point in predictions):
            raise TypeError("predictions must contain ForecastPoint values")
        keys = tuple(
            (point.target_id, point.horizon, point.output_id) for point in predictions
        )
        if len(keys) != len(set(keys)):
            raise ValueError("predictions cannot contain duplicates")
        if any(point.horizon not in self.request.horizons for point in predictions):
            raise ValueError("prediction horizon must be a requested horizon")
        object.__setattr__(
            self,
            "model_id",
            _normalize_text(self.model_id, name="model_id"),
        )
        object.__setattr__(
            self, "version", _normalize_text(self.version, name="version")
        )
        object.__setattr__(self, "role", _normalize_role(self.role))
        object.__setattr__(self, "scope", scope)
        object.__setattr__(
            self,
            "output_contract",
            _normalize_text(self.output_contract, name="output_contract"),
        )
        object.__setattr__(
            self,
            "predictions",
            tuple(
                sorted(
                    predictions,
                    key=lambda point: (
                        point.target_id,
                        point.horizon,
                        point.output_id,
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelCard:
    """Immutable model identity, reproducibility, and use-boundary contract."""

    model_id: str
    version: str
    role: ModelRole
    scope: ForecastScope
    algorithm: str
    code_hash: str
    config_hash: str
    seed_policy: SeedPolicy
    seed: int
    training_objective: str
    output_contract: str
    downstream_mapping_requirement: DownstreamMappingRequirement
    direct_asset_weights_allowed: bool
    direct_asset_prediction_bypass_allowed: bool
    historical_contribution_weights_allowed: bool
    feature_ids: Sequence[str]
    data_vintage: date
    training_cutoff: date

    def __post_init__(self) -> None:
        data_vintage = _normalize_date(self.data_vintage, name="data_vintage")
        training_cutoff = _normalize_date(
            self.training_cutoff,
            name="training_cutoff",
        )
        if training_cutoff > data_vintage:
            raise ValueError("training_cutoff cannot follow data_vintage")
        direct_asset_weights_allowed = _normalize_boolean(
            self.direct_asset_weights_allowed,
            name="direct_asset_weights_allowed",
        )
        direct_asset_prediction_bypass_allowed = _normalize_boolean(
            self.direct_asset_prediction_bypass_allowed,
            name="direct_asset_prediction_bypass_allowed",
        )
        historical_contribution_weights_allowed = _normalize_boolean(
            self.historical_contribution_weights_allowed,
            name="historical_contribution_weights_allowed",
        )
        if direct_asset_weights_allowed:
            raise ValueError("direct asset weights are prohibited")
        if direct_asset_prediction_bypass_allowed:
            raise ValueError("direct asset predictions must use governed asset Mapping")
        if historical_contribution_weights_allowed:
            raise ValueError("historical contribution shares cannot become weights")
        object.__setattr__(
            self,
            "model_id",
            _normalize_text(self.model_id, name="model_id"),
        )
        object.__setattr__(
            self, "version", _normalize_text(self.version, name="version")
        )
        object.__setattr__(self, "role", _normalize_role(self.role))
        object.__setattr__(self, "scope", _normalize_scope(self.scope))
        object.__setattr__(
            self,
            "algorithm",
            _normalize_text(self.algorithm, name="algorithm"),
        )
        object.__setattr__(
            self,
            "code_hash",
            _normalize_hash(self.code_hash, name="code_hash"),
        )
        object.__setattr__(
            self,
            "config_hash",
            _normalize_hash(self.config_hash, name="config_hash"),
        )
        object.__setattr__(
            self, "seed_policy", _normalize_seed_policy(self.seed_policy)
        )
        object.__setattr__(
            self,
            "seed",
            _normalize_nonnegative_integer(self.seed, name="seed"),
        )
        object.__setattr__(
            self,
            "training_objective",
            _normalize_text(self.training_objective, name="training_objective"),
        )
        object.__setattr__(
            self,
            "output_contract",
            _normalize_text(self.output_contract, name="output_contract"),
        )
        object.__setattr__(
            self,
            "downstream_mapping_requirement",
            _normalize_downstream_mapping_requirement(
                self.downstream_mapping_requirement
            ),
        )
        object.__setattr__(
            self,
            "direct_asset_weights_allowed",
            direct_asset_weights_allowed,
        )
        object.__setattr__(
            self,
            "direct_asset_prediction_bypass_allowed",
            direct_asset_prediction_bypass_allowed,
        )
        object.__setattr__(
            self,
            "historical_contribution_weights_allowed",
            historical_contribution_weights_allowed,
        )
        object.__setattr__(
            self, "feature_ids", _normalize_feature_ids(self.feature_ids)
        )
        object.__setattr__(self, "data_vintage", data_vintage)
        object.__setattr__(self, "training_cutoff", training_cutoff)


@dataclass(frozen=True, slots=True)
class FeatureAudit:
    """Immutable PIT audit whose leakage IDs denote checks reported as passed."""

    model_id: str
    version: str
    role: ModelRole
    scope: ForecastScope
    as_of: date
    feature_ids: Sequence[str]
    max_visible_date: date
    max_generated_date: date
    max_vintage_date: date
    train_start: date
    train_end: date
    data_vintage: date
    leakage_checks: Sequence[str]
    forbidden_features: Sequence[str]
    status: AuditStatus
    reasons: Sequence[str]
    code_hash: str
    config_hash: str

    def __post_init__(self) -> None:
        as_of = _normalize_date(self.as_of, name="as_of")
        train_start = _normalize_date(self.train_start, name="train_start")
        train_end = _normalize_date(self.train_end, name="train_end")
        data_vintage = _normalize_date(self.data_vintage, name="data_vintage")
        max_visible_date = _normalize_date(
            self.max_visible_date,
            name="max_visible_date",
        )
        max_generated_date = _normalize_date(
            self.max_generated_date,
            name="max_generated_date",
        )
        max_vintage_date = _normalize_date(
            self.max_vintage_date,
            name="max_vintage_date",
        )
        if train_start > train_end:
            raise ValueError("train_start cannot follow train_end")
        if train_end > as_of:
            raise ValueError("train_end cannot be after audit as_of")
        if data_vintage > as_of:
            raise ValueError("data_vintage cannot be after audit as_of")
        if train_end > data_vintage:
            raise ValueError("train_end cannot follow data_vintage")
        for field_name, value in (
            ("max_visible_date", max_visible_date),
            ("max_generated_date", max_generated_date),
            ("max_vintage_date", max_vintage_date),
        ):
            if value > as_of:
                raise ValueError(f"{field_name} cannot be after audit as_of")
        if max_vintage_date > data_vintage:
            raise ValueError("max_vintage_date cannot follow data_vintage")
        feature_ids = _normalize_feature_ids(self.feature_ids)
        leakage_checks = _normalize_text_sequence(
            self.leakage_checks,
            name="leakage_checks",
            allow_empty=False,
            sort_values=False,
        )
        forbidden_features = _normalize_feature_ids(
            self.forbidden_features,
            name="forbidden_features",
            allow_empty=True,
        )
        status = _normalize_audit_status(self.status)
        reasons = _normalize_text_sequence(
            self.reasons,
            name="reasons",
            allow_empty=True,
            sort_values=False,
        )
        if status == "passed" and reasons:
            raise ValueError("passed audit cannot contain failure reasons")
        if status == "passed" and forbidden_features:
            raise ValueError("forbidden features require failed audit status")
        if status == "failed" and not reasons:
            raise ValueError("failed audit status requires reasons")
        object.__setattr__(
            self,
            "model_id",
            _normalize_text(self.model_id, name="model_id"),
        )
        object.__setattr__(
            self, "version", _normalize_text(self.version, name="version")
        )
        object.__setattr__(self, "role", _normalize_role(self.role))
        object.__setattr__(self, "scope", _normalize_scope(self.scope))
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "feature_ids", feature_ids)
        object.__setattr__(self, "max_visible_date", max_visible_date)
        object.__setattr__(self, "max_generated_date", max_generated_date)
        object.__setattr__(self, "max_vintage_date", max_vintage_date)
        object.__setattr__(self, "train_start", train_start)
        object.__setattr__(self, "train_end", train_end)
        object.__setattr__(self, "data_vintage", data_vintage)
        object.__setattr__(self, "leakage_checks", leakage_checks)
        object.__setattr__(self, "forbidden_features", forbidden_features)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self,
            "code_hash",
            _normalize_hash(self.code_hash, name="code_hash"),
        )
        object.__setattr__(
            self,
            "config_hash",
            _normalize_hash(self.config_hash, name="config_hash"),
        )


@runtime_checkable
class ForecastModel(Protocol):
    """Runtime-checkable interface for Champion and Challenger implementations."""

    def fit(self, train_vintage: TrainVintage) -> None:
        """Fit using one explicit point-in-time training vintage."""
        ...

    def predict(
        self,
        as_of: date,
        horizons: Sequence[int],
    ) -> PredictionEnvelope:
        """Return governed cycle or channel predictions for requested horizons."""
        ...

    def model_card(self) -> ModelCard:
        """Return immutable model identity and reproducibility metadata."""
        ...

    def feature_audit(self) -> FeatureAudit:
        """Return immutable point-in-time feature and leakage metadata."""
        ...


_FORECAST_MODEL_SIGNATURES = {
    "fit": ("train_vintage",),
    "predict": ("as_of", "horizons"),
    "model_card": (),
    "feature_audit": (),
}
_FORECAST_MODEL_RETURN_TYPES = {
    "fit": (type(None), "None"),
    "predict": (PredictionEnvelope, "PredictionEnvelope"),
    "model_card": (ModelCard, "ModelCard"),
    "feature_audit": (FeatureAudit, "FeatureAudit"),
}


def _forecast_method_signature_error(
    value: object,
    *,
    method_name: str,
    parameter_names: tuple[str, ...],
) -> str | None:
    expected = f"{method_name}({', '.join(parameter_names)})"
    try:
        method = getattr(value, method_name)
    except (AttributeError, TypeError):
        return f"{method_name} must have signature {expected}"
    if not callable(method):
        return f"{method_name} must have signature {expected}"
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return f"{method_name} must have signature {expected}"
    parameters = tuple(signature.parameters.values())
    if tuple(parameter.name for parameter in parameters) != parameter_names:
        return f"{method_name} must have signature {expected}"
    if any(
        parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD
        or parameter.default is not inspect.Parameter.empty
        for parameter in parameters
    ):
        return f"{method_name} must have signature {expected}"
    return None


def _forecast_method_return_error(
    method: object,
    *,
    method_name: str,
    expected_type: type[object],
    expected_name: str,
) -> str | None:
    try:
        return_annotation = get_type_hints(method).get(
            "return", inspect.Signature.empty
        )
    except (NameError, TypeError):
        return_annotation = inspect.signature(method).return_annotation
    if return_annotation is not expected_type:
        return f"{method_name} must return {expected_name}"
    return None


def _forecast_method_runtime_return_error(
    method: object,
    *,
    method_name: str,
    expected_type: type[object],
    expected_name: str,
) -> str | None:
    try:
        result = cast(Callable[[], object], method)()
    except Exception:
        return f"{method_name} must return {expected_name} at runtime"
    if not isinstance(result, expected_type):
        return f"{method_name} must return {expected_name} at runtime"
    return None


def forecast_model_contract_errors(value: object) -> tuple[str, ...]:
    """Return exact runtime signature violations for a forecast model object."""

    errors: list[str] = []
    for method_name, parameter_names in _FORECAST_MODEL_SIGNATURES.items():
        signature_error = _forecast_method_signature_error(
            value,
            method_name=method_name,
            parameter_names=parameter_names,
        )
        if signature_error is not None:
            errors.append(signature_error)
            continue
        method = getattr(value, method_name)
        expected_type, expected_name = _FORECAST_MODEL_RETURN_TYPES[method_name]
        return_error = _forecast_method_return_error(
            method,
            method_name=method_name,
            expected_type=expected_type,
            expected_name=expected_name,
        )
        if return_error is not None:
            errors.append(return_error)
            continue
        if not parameter_names:
            runtime_error = _forecast_method_runtime_return_error(
                method,
                method_name=method_name,
                expected_type=expected_type,
                expected_name=expected_name,
            )
            if runtime_error is not None:
                errors.append(runtime_error)
    return tuple(errors)


def validate_forecast_model(value: object) -> ForecastModel:
    """Validate the exact Task 27 callable shape and return the typed model."""

    errors = forecast_model_contract_errors(value)
    if errors:
        raise TypeError("; ".join(errors))
    return cast(ForecastModel, value)


def is_forecast_model(value: object) -> TypeGuard[ForecastModel]:
    """Return whether an object satisfies the exact Task 27 runtime contract."""

    try:
        validate_forecast_model(value)
    except TypeError:
        return False
    return True


__all__ = [
    "AuditStatus",
    "DownstreamMappingRequirement",
    "FeatureAudit",
    "ForecastModel",
    "ForecastPoint",
    "ForecastRequest",
    "ForecastScope",
    "GOVERNED_LEAKAGE_CHECKS",
    "GOVERNED_MAPPING_REQUIRED",
    "ModelCard",
    "ModelRole",
    "PredictionEnvelope",
    "PredictionRequest",
    "PredictionScope",
    "SeedPolicy",
    "TrainVintage",
    "TrainingRequest",
    "TrainingVintage",
    "forecast_model_contract_errors",
    "is_forecast_model",
    "validate_forecast_model",
]
