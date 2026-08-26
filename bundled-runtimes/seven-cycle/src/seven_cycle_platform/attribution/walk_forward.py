"""Past-only ridge fitting and nested walk-forward alpha selection."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np


_RIDGE_ARRAY_FIELDS = frozenset({"coefficients", "covariance"})


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _nonnegative_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _forgetting_factor(value: object) -> float:
    numeric = _finite_real(value, "forgetting_factor")
    if not 0.0 < numeric <= 1.0:
        raise ValueError("forgetting_factor must be in (0, 1]")
    return numeric


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a boolean")
    return bool(value)


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _normalize_alpha_grid(values: object) -> tuple[float, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("alpha_grid must be an iterable of real numbers")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError("alpha_grid must be an iterable of real numbers") from error
    if not supplied:
        raise ValueError("alpha_grid must contain at least one alpha")
    normalized = tuple(_nonnegative_real(value, "alpha") for value in supplied)
    if len(normalized) != len(set(normalized)):
        raise ValueError("alpha_grid values must be unique")
    return normalized


def _training_arrays(
    features: object,
    target: object,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        normalized_features = np.asarray(features, dtype="float64")
        normalized_target = np.asarray(target, dtype="float64")
    except (TypeError, ValueError) as error:
        raise TypeError("features and target must be numeric arrays") from error
    if normalized_features.ndim != 2:
        raise ValueError("features must be two-dimensional")
    if normalized_features.shape[0] == 0 or normalized_features.shape[1] == 0:
        raise ValueError("features must be non-empty")
    if normalized_target.ndim != 1:
        raise ValueError("target must be one-dimensional")
    if len(normalized_features) != len(normalized_target):
        raise ValueError("features and target must have equal length")
    if (
        not np.isfinite(normalized_features).all()
        or not np.isfinite(normalized_target).all()
    ):
        raise ValueError("training data must be finite")
    return normalized_features, normalized_target


def _read_only_array(
    values: object,
    *,
    name: str,
    dimensions: int,
) -> np.ndarray:
    try:
        normalized = np.asarray(values, dtype="float64")
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a numeric array") from error
    if normalized.ndim != dimensions:
        raise ValueError(f"{name} must be {dimensions}-dimensional")
    if not np.isfinite(normalized).all():
        raise ValueError(f"{name} must be finite")
    copied = normalized.copy()
    copied.setflags(write=False)
    return copied


@dataclass(frozen=True)
class RidgeEstimate:
    """A ridge estimate expressed on the original feature scale."""

    coefficients: np.ndarray
    intercept: float
    covariance: np.ndarray

    def __post_init__(self) -> None:
        coefficients = _read_only_array(
            object.__getattribute__(self, "coefficients"),
            name="coefficients",
            dimensions=1,
        )
        covariance = _read_only_array(
            object.__getattribute__(self, "covariance"),
            name="covariance",
            dimensions=2,
        )
        if covariance.shape != (len(coefficients), len(coefficients)):
            raise ValueError("covariance shape must match the coefficient dimension")
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "intercept", _finite_real(self.intercept, "intercept"))
        object.__setattr__(self, "covariance", covariance)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RIDGE_ARRAY_FIELDS and isinstance(value, np.ndarray):
            copied = value.copy()
            copied.setflags(write=False)
            return copied
        return value


@dataclass(frozen=True)
class WalkForwardSelection:
    """Selected alpha and the number of strictly past validation predictions."""

    alpha: float
    validation_count: int


def _standardize(
    features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0, ddof=0)
    scale_tolerance = np.finfo("float64").eps * max(len(features), 1)
    if bool((feature_scale <= scale_tolerance).any()):
        raise ValueError("training features contain a constant cycle")
    standardized = (features - feature_mean) / feature_scale
    return feature_mean, feature_scale, standardized


def standardized_condition_number(features: np.ndarray) -> float:
    """Return the condition number of the centered, standardized design."""

    normalized = np.asarray(features, dtype="float64")
    if normalized.ndim != 2 or normalized.shape[0] == 0 or normalized.shape[1] == 0:
        raise ValueError("features must be a non-empty two-dimensional array")
    if not np.isfinite(normalized).all():
        raise ValueError("features must be finite")
    try:
        _, _, standardized = _standardize(normalized)
        condition_number = float(np.linalg.cond(standardized))
    except (ValueError, np.linalg.LinAlgError):
        return float("inf")
    if not np.isfinite(condition_number):
        return float("inf")
    return condition_number


def _symmetric(values: np.ndarray) -> np.ndarray:
    return (values + values.T) / 2.0


def _batch_ridge(
    standardized: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
) -> tuple[np.ndarray, float, np.ndarray]:
    target_mean = float(target.mean())
    centered_target = target - target_mean
    gram = standardized.T @ standardized
    penalized = gram + alpha * np.eye(standardized.shape[1])
    inverse = np.linalg.pinv(penalized, hermitian=True)
    coefficients = inverse @ standardized.T @ centered_target
    fitted = target_mean + standardized @ coefficients
    residuals = target - fitted
    effective_degrees = float(np.trace(inverse @ gram))
    degrees_of_freedom = max(
        len(target) - 1 - effective_degrees,
        1.0,
    )
    residual_variance = float(residuals @ residuals / degrees_of_freedom)
    covariance = residual_variance * inverse @ gram @ inverse
    return coefficients, target_mean, _symmetric(covariance)


def _recursive_ridge(
    standardized: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
    forgetting_factor: float,
) -> tuple[np.ndarray, float, np.ndarray]:
    feature_count = standardized.shape[1]
    design = np.column_stack(
        [np.ones(len(standardized), dtype="float64"), standardized]
    )
    penalty = np.zeros(feature_count + 1, dtype="float64")
    penalty[1:] = alpha
    penalty_matrix = np.diag(penalty)
    data_gram = np.zeros(
        (feature_count + 1, feature_count + 1),
        dtype="float64",
    )
    data_target = np.zeros(feature_count + 1, dtype="float64")
    parameters = np.zeros(feature_count + 1, dtype="float64")
    for row, observed in zip(design, target, strict=True):
        data_gram *= forgetting_factor
        data_target *= forgetting_factor
        data_gram += np.outer(row, row)
        data_target += row * observed
        penalized = data_gram + penalty_matrix
        parameters = np.linalg.pinv(penalized, hermitian=True) @ data_target
    fitted = design @ parameters
    residuals = target - fitted
    powers = np.arange(len(target) - 1, -1, -1, dtype="float64")
    weights = np.power(forgetting_factor, powers)
    penalized = data_gram + penalty_matrix
    inverse = np.linalg.pinv(penalized, hermitian=True)
    effective_degrees = float(np.trace(inverse @ data_gram))
    degrees_of_freedom = max(
        float(weights.sum()) - effective_degrees,
        1.0,
    )
    residual_variance = float(
        np.dot(weights, residuals * residuals) / degrees_of_freedom
    )
    parameter_covariance = residual_variance * inverse @ data_gram @ inverse
    coefficient_covariance = parameter_covariance[1:, 1:]
    return (
        parameters[1:],
        float(parameters[0]),
        _symmetric(coefficient_covariance),
    )


def fit_standardized_ridge(
    features: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
    recursive: bool,
    forgetting_factor: float,
) -> RidgeEstimate:
    """Fit ridge on standardized data and return original-scale parameters."""

    normalized_alpha = _nonnegative_real(alpha, "alpha")
    normalized_recursive = _boolean(recursive, "recursive")
    normalized_forgetting_factor = _forgetting_factor(forgetting_factor)
    normalized_features, normalized_target = _training_arrays(features, target)
    feature_mean, feature_scale, standardized = _standardize(normalized_features)
    if normalized_recursive:
        standardized_coefficients, standardized_intercept, covariance = (
            _recursive_ridge(
                standardized,
                normalized_target,
                alpha=normalized_alpha,
                forgetting_factor=normalized_forgetting_factor,
            )
        )
    else:
        standardized_coefficients, standardized_intercept, covariance = _batch_ridge(
            standardized,
            normalized_target,
            alpha=normalized_alpha,
        )
    coefficients = standardized_coefficients / feature_scale
    intercept = standardized_intercept - float(feature_mean @ coefficients)
    original_covariance = covariance / np.outer(feature_scale, feature_scale)
    return RidgeEstimate(
        coefficients=np.asarray(coefficients, dtype="float64"),
        intercept=float(intercept),
        covariance=np.asarray(_symmetric(original_covariance), dtype="float64"),
    )


def select_alpha_walk_forward(
    features: np.ndarray,
    target: np.ndarray,
    *,
    alpha_grid: tuple[float, ...],
    min_training_count: int,
    validation_window: int,
    recursive: bool,
    forgetting_factor: float,
) -> WalkForwardSelection | None:
    """Choose alpha using nested one-step predictions from past prefixes only."""

    normalized_features, normalized_target = _training_arrays(features, target)
    normalized_alpha_grid = _normalize_alpha_grid(alpha_grid)
    normalized_minimum_count = _positive_integer(
        min_training_count,
        "min_training_count",
    )
    normalized_validation_window = _positive_integer(
        validation_window,
        "validation_window",
    )
    normalized_recursive = _boolean(recursive, "recursive")
    normalized_forgetting_factor = _forgetting_factor(forgetting_factor)
    feature_count = normalized_features.shape[1]
    minimum_inner_count = max(
        feature_count + 2,
        normalized_minimum_count - normalized_validation_window,
    )
    first_validation = max(
        minimum_inner_count,
        len(normalized_target) - normalized_validation_window,
    )
    if first_validation >= len(normalized_target):
        return None
    scores: dict[float, list[float]] = {alpha: [] for alpha in normalized_alpha_grid}
    for validation_position in range(first_validation, len(normalized_target)):
        inner_features = normalized_features[:validation_position]
        inner_target = normalized_target[:validation_position]
        if len(inner_target) < minimum_inner_count:
            continue
        validation_features = normalized_features[validation_position]
        validation_target = float(normalized_target[validation_position])
        for alpha in normalized_alpha_grid:
            try:
                estimate = fit_standardized_ridge(
                    inner_features,
                    inner_target,
                    alpha=alpha,
                    recursive=normalized_recursive,
                    forgetting_factor=normalized_forgetting_factor,
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            prediction = estimate.intercept + float(
                validation_features @ estimate.coefficients
            )
            if np.isfinite(prediction):
                scores[alpha].append((validation_target - prediction) ** 2)
    eligible = [
        (float(np.mean(alpha_scores)), alpha, len(alpha_scores))
        for alpha, alpha_scores in scores.items()
        if alpha_scores
    ]
    if not eligible:
        return None
    _, selected_alpha, validation_count = min(
        eligible,
        key=lambda item: (item[0], item[1]),
    )
    return WalkForwardSelection(
        alpha=float(selected_alpha),
        validation_count=int(validation_count),
    )


__all__ = [
    "RidgeEstimate",
    "WalkForwardSelection",
    "fit_standardized_ridge",
    "select_alpha_walk_forward",
    "standardized_condition_number",
]
