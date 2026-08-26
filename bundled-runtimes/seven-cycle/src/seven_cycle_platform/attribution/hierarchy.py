"""Low-level hierarchical time-varying ridge posteriors."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np


_ARRAY_FIELDS = frozenset({"mean", "covariance", "parent_mean"})
_PSD_TOLERANCE = 1e-10
_USABLE_STATUSES = frozenset({"estimated", "parent_informed", "parent_only"})
_FAILED_STATUSES = frozenset({"insufficient_history", "not_identifiable"})


def _read_only_array(
    values: object,
    *,
    name: str,
    dimensions: int,
    allow_nan: bool = False,
) -> np.ndarray:
    try:
        normalized = np.asarray(values, dtype="float64")
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a numeric array") from error
    if normalized.ndim != dimensions:
        raise ValueError(f"{name} must be {dimensions}-dimensional")
    if allow_nan:
        if np.isinf(normalized).any():
            raise ValueError(f"{name} cannot contain infinity")
    elif not np.isfinite(normalized).all():
        raise ValueError(f"{name} must be finite")
    copied = normalized.copy()
    copied.setflags(write=False)
    return copied


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    normalized = float(value)
    if not np.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _project_psd(values: np.ndarray) -> np.ndarray:
    symmetric = (values + values.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(eigenvalues, 0.0)
    projected = (eigenvectors * clipped) @ eigenvectors.T
    return (projected + projected.T) / 2.0


def _is_psd(values: np.ndarray) -> bool:
    symmetric = (values + values.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(symmetric)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    return bool(eigenvalues.min() >= -_PSD_TOLERANCE * scale)


@dataclass(frozen=True)
class HierarchicalPosterior:
    """Detached posterior parameters and hierarchy diagnostics."""

    mean: np.ndarray
    covariance: np.ndarray
    parent_mean: np.ndarray
    training_count: int
    effective_training_count: float
    condition_number: float
    prior_precision: float
    own_weight: float
    parent_weight: float
    confidence: float
    status: str

    def __post_init__(self) -> None:
        mean = _read_only_array(
            object.__getattribute__(self, "mean"),
            name="mean",
            dimensions=1,
            allow_nan=True,
        )
        covariance = _read_only_array(
            object.__getattribute__(self, "covariance"),
            name="covariance",
            dimensions=2,
            allow_nan=True,
        )
        parent_mean = _read_only_array(
            object.__getattribute__(self, "parent_mean"),
            name="parent_mean",
            dimensions=1,
            allow_nan=True,
        )
        if covariance.shape != (len(mean), len(mean)):
            raise ValueError("covariance shape must match mean")
        if parent_mean.shape != mean.shape:
            raise ValueError("parent_mean shape must match mean")
        mean_finite = np.isfinite(mean)
        covariance_finite = np.isfinite(covariance)
        if mean_finite.any() and not mean_finite.all():
            raise ValueError("mean cannot be partially missing")
        if covariance_finite.any() and not covariance_finite.all():
            raise ValueError("covariance cannot be partially missing")
        if covariance_finite.all():
            if not np.allclose(covariance, covariance.T, atol=1e-10, rtol=1e-10):
                raise ValueError("covariance must be symmetric")
            if not _is_psd(covariance):
                raise ValueError("covariance must be positive semidefinite")
        status = self.status
        if status in _USABLE_STATUSES:
            if not mean_finite.all() or not covariance_finite.all():
                raise ValueError("usable posteriors require finite mean and covariance")
        elif status in _FAILED_STATUSES:
            if mean_finite.any() or covariance_finite.any():
                raise ValueError(
                    "failed posteriors require missing mean and covariance"
                )
        else:
            raise ValueError("unknown hierarchical posterior status")
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "parent_mean", parent_mean)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _ARRAY_FIELDS and isinstance(value, np.ndarray):
            copied = value.copy()
            copied.setflags(write=False)
            return copied
        return value


def weighted_condition_number(
    features: np.ndarray,
    observation_weights: np.ndarray,
) -> float:
    """Return the condition number of a weighted standardized design."""

    normalized_features = np.asarray(features, dtype="float64")
    normalized_weights = np.asarray(observation_weights, dtype="float64")
    if normalized_features.ndim != 2 or normalized_features.shape[1] == 0:
        raise ValueError("features must be a two-dimensional non-empty design")
    if normalized_weights.ndim != 1 or len(normalized_weights) != len(
        normalized_features
    ):
        raise ValueError("observation_weights must align with features")
    if (
        not np.isfinite(normalized_features).all()
        or not np.isfinite(normalized_weights).all()
        or bool((normalized_weights <= 0.0).any())
    ):
        raise ValueError("features and observation_weights must be finite and positive")
    if len(normalized_features) <= normalized_features.shape[1]:
        return float("inf")
    total_weight = float(normalized_weights.sum())
    feature_mean = np.average(
        normalized_features,
        axis=0,
        weights=normalized_weights,
    )
    centered = normalized_features - feature_mean
    variance = np.sum(normalized_weights[:, None] * np.square(centered), axis=0)
    variance /= total_weight
    tolerance = np.finfo("float64").eps * max(len(normalized_features), 1)
    if bool((variance <= tolerance).any()):
        return float("inf")
    standardized = centered / np.sqrt(variance)
    try:
        condition_number = float(
            np.linalg.cond(np.sqrt(normalized_weights)[:, None] * standardized)
        )
    except np.linalg.LinAlgError:
        return float("inf")
    return condition_number if np.isfinite(condition_number) else float("inf")


def _missing_posterior(
    parameter_count: int,
    *,
    training_count: int,
    effective_training_count: float,
    condition_number: float,
    prior_precision: float,
    status: str,
) -> HierarchicalPosterior:
    return HierarchicalPosterior(
        mean=np.full(parameter_count, np.nan, dtype="float64"),
        covariance=np.full(
            (parameter_count, parameter_count),
            np.nan,
            dtype="float64",
        ),
        parent_mean=np.full(parameter_count, np.nan, dtype="float64"),
        training_count=training_count,
        effective_training_count=effective_training_count,
        condition_number=condition_number,
        prior_precision=prior_precision,
        own_weight=0.0,
        parent_weight=0.0,
        confidence=0.0,
        status=status,
    )


def _usable_parent(parent: HierarchicalPosterior | None) -> bool:
    if parent is None or parent.status not in _USABLE_STATUSES:
        return False
    mean = parent.mean
    covariance = parent.covariance
    return bool(
        np.isfinite(mean).all()
        and np.isfinite(covariance).all()
        and np.allclose(covariance, covariance.T, atol=1e-10, rtol=1e-10)
        and _is_psd(covariance)
    )


def _parent_only_posterior(
    parent: HierarchicalPosterior,
    *,
    training_count: int,
    effective_training_count: float,
    condition_number: float,
    prior_precision: float,
    effective_confidence: float,
    confidence_multiplier: float,
) -> HierarchicalPosterior:
    parent_mean = parent.mean
    parent_covariance = parent.covariance
    return HierarchicalPosterior(
        mean=parent_mean,
        covariance=parent_covariance,
        parent_mean=parent_mean,
        training_count=training_count,
        effective_training_count=effective_training_count,
        condition_number=condition_number,
        prior_precision=prior_precision,
        own_weight=0.0,
        parent_weight=1.0,
        confidence=float(
            np.clip(
                parent.confidence * effective_confidence * confidence_multiplier,
                0.0,
                1.0,
            )
        ),
        status="parent_only",
    )


def fit_hierarchical_tvp_ridge(
    features: np.ndarray,
    target: np.ndarray,
    observation_weights: np.ndarray,
    *,
    min_training_count: int,
    prior_strength: float,
    condition_number_threshold: float,
    parent: HierarchicalPosterior | None,
    confidence_discount: float,
) -> HierarchicalPosterior:
    """Fit a weighted ridge posterior around a parent posterior mean."""

    normalized_minimum_count = _positive_integer(
        min_training_count,
        "min_training_count",
    )
    normalized_prior_strength = _positive_real(prior_strength, "prior_strength")
    normalized_condition_threshold = _positive_real(
        condition_number_threshold,
        "condition_number_threshold",
    )
    if parent is not None and not isinstance(parent, HierarchicalPosterior):
        raise TypeError("parent must be None or a HierarchicalPosterior")
    normalized_features = np.asarray(features, dtype="float64")
    normalized_target = np.asarray(target, dtype="float64")
    normalized_weights = np.asarray(observation_weights, dtype="float64")
    if normalized_features.ndim != 2 or normalized_features.shape[1] == 0:
        raise ValueError("features must be a two-dimensional non-empty design")
    if normalized_target.ndim != 1 or len(normalized_target) != len(
        normalized_features
    ):
        raise ValueError("target must be one-dimensional and align with features")
    if normalized_weights.ndim != 1 or len(normalized_weights) != len(
        normalized_features
    ):
        raise ValueError("observation_weights must align with features")
    if (
        not np.isfinite(normalized_features).all()
        or not np.isfinite(normalized_target).all()
        or not np.isfinite(normalized_weights).all()
        or bool((normalized_weights <= 0.0).any())
    ):
        raise ValueError("training arrays must be finite with positive weights")
    if isinstance(confidence_discount, (bool, np.bool_)):
        raise TypeError("confidence_discount must be a finite real number")
    try:
        normalized_discount = float(confidence_discount)
    except (TypeError, ValueError) as error:
        raise TypeError("confidence_discount must be a finite real number") from error
    if not np.isfinite(normalized_discount):
        raise ValueError("confidence_discount must be a finite real number")
    if not 0.0 <= normalized_discount < 1.0:
        raise ValueError("confidence_discount must be in [0, 1)")
    effective_confidence = 1.0 - normalized_discount
    parameter_count = normalized_features.shape[1] + 1
    effective_training_count = float(normalized_weights.sum())
    condition_number = (
        weighted_condition_number(normalized_features, normalized_weights)
        if len(normalized_target)
        else float("nan")
    )
    root = parent is None
    adjusted_prior_strength = normalized_prior_strength
    identifiable = (
        np.isfinite(condition_number)
        and condition_number <= normalized_condition_threshold
    )
    if root and len(normalized_target) < normalized_minimum_count:
        return _missing_posterior(
            parameter_count,
            training_count=len(normalized_target),
            effective_training_count=effective_training_count,
            condition_number=condition_number,
            prior_precision=adjusted_prior_strength,
            status="insufficient_history",
        )
    if root and not identifiable:
        return _missing_posterior(
            parameter_count,
            training_count=len(normalized_target),
            effective_training_count=effective_training_count,
            condition_number=condition_number,
            prior_precision=adjusted_prior_strength,
            status="not_identifiable",
        )
    if not root and not _usable_parent(parent):
        failed_status = (
            "not_identifiable"
            if parent is not None and parent.status == "not_identifiable"
            else "insufficient_history"
        )
        return _missing_posterior(
            parameter_count,
            training_count=len(normalized_target),
            effective_training_count=effective_training_count,
            condition_number=condition_number,
            prior_precision=adjusted_prior_strength,
            status=failed_status,
        )
    if not root and len(normalized_target) == 0:
        return _parent_only_posterior(
            parent,
            training_count=0,
            effective_training_count=0.0,
            condition_number=float("nan"),
            prior_precision=adjusted_prior_strength,
            effective_confidence=effective_confidence,
            confidence_multiplier=0.8,
        )
    if not root and not identifiable:
        return _parent_only_posterior(
            parent,
            training_count=len(normalized_target),
            effective_training_count=effective_training_count,
            condition_number=condition_number,
            prior_precision=adjusted_prior_strength,
            effective_confidence=effective_confidence,
            confidence_multiplier=0.5,
        )

    total_weight = float(normalized_weights.sum())
    feature_mean = np.average(
        normalized_features,
        axis=0,
        weights=normalized_weights,
    )
    centered = normalized_features - feature_mean
    variance = np.sum(normalized_weights[:, None] * np.square(centered), axis=0)
    variance /= total_weight
    tolerance = np.finfo("float64").eps * max(len(normalized_features), 1)
    feature_scale = np.sqrt(np.maximum(variance, tolerance))
    standardized = centered / feature_scale
    design = np.column_stack(
        [np.ones(len(standardized), dtype="float64"), standardized]
    )
    penalty = np.zeros(parameter_count, dtype="float64")
    penalty[1:] = adjusted_prior_strength
    penalty_matrix = np.diag(penalty)
    prior_standardized = np.zeros(parameter_count, dtype="float64")
    prior_covariance = np.zeros((parameter_count, parameter_count), dtype="float64")
    if root:
        prior_covariance[1:, 1:] = np.eye(normalized_features.shape[1]) / float(
            normalized_prior_strength
        )
        parent_mean = np.full(parameter_count, np.nan, dtype="float64")
    else:
        parent_mean = parent.mean
        prior_standardized[1:] = feature_scale * parent_mean[1:]
        scale_matrix = np.diag(feature_scale)
        prior_covariance[1:, 1:] = (
            scale_matrix @ parent.covariance[1:, 1:] @ scale_matrix
        )
    weighted_design = normalized_weights[:, None] * design
    data_gram = design.T @ weighted_design
    penalized = data_gram + penalty_matrix
    inverse = np.linalg.pinv(penalized, hermitian=True)
    rhs = design.T @ (normalized_weights * normalized_target)
    rhs += penalty_matrix @ prior_standardized
    standardized_mean = inverse @ rhs
    fitted = design @ standardized_mean
    residuals = normalized_target - fitted
    scores = design * (normalized_weights * residuals)[:, None]
    data_meat = scores.T @ scores
    prior_meat = penalty_matrix @ prior_covariance @ penalty_matrix
    standardized_covariance = inverse @ (data_meat + prior_meat) @ inverse
    transformation = np.zeros((parameter_count, parameter_count), dtype="float64")
    transformation[0, 0] = 1.0
    transformation[0, 1:] = -feature_mean / feature_scale
    transformation[1:, 1:] = np.diag(1.0 / feature_scale)
    mean = transformation @ standardized_mean
    covariance = _project_psd(
        transformation @ standardized_covariance @ transformation.T
    )
    enough_history = len(normalized_target) >= normalized_minimum_count
    if root:
        status = "estimated"
        own_weight = 1.0
        parent_weight = 0.0
    else:
        status = "estimated" if enough_history else "parent_informed"
        own_weight = total_weight / (total_weight + adjusted_prior_strength)
        parent_weight = 1.0 - own_weight
    history_confidence = min(1.0, total_weight / float(normalized_minimum_count))
    if root:
        confidence = history_confidence
    else:
        confidence = own_weight * history_confidence + parent_weight * parent.confidence
    return HierarchicalPosterior(
        mean=np.asarray(mean, dtype="float64"),
        covariance=np.asarray(covariance, dtype="float64"),
        parent_mean=np.asarray(parent_mean, dtype="float64"),
        training_count=len(normalized_target),
        effective_training_count=total_weight,
        condition_number=float(condition_number),
        prior_precision=float(adjusted_prior_strength),
        own_weight=float(own_weight),
        parent_weight=float(parent_weight),
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        status=status,
    )


__all__ = [
    "HierarchicalPosterior",
    "fit_hierarchical_tvp_ridge",
    "weighted_condition_number",
]
