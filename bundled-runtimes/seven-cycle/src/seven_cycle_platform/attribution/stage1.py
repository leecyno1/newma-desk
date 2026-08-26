"""Causal cycle-to-channel path attribution."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.walk_forward import (
    RidgeEstimate,
    fit_standardized_ridge,
    select_alpha_walk_forward,
    standardized_condition_number,
)


CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))

CYCLE_TO_CHANNEL_PATH_COLUMNS = (
    "date",
    "channel_id",
    "cycle_id",
    "cycle_innovation",
    "coefficient_mean",
    "contribution",
    "intercept",
    "observed_channel_innovation",
    "predicted_channel_innovation",
    "channel_residual",
    "training_start",
    "training_end",
    "training_count",
    "alpha",
    "condition_number",
    "validation_count",
    "window",
    "estimation_method",
    "forgetting_factor",
    "status",
)

CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS = (
    "date",
    "channel_id",
    "cycle_i",
    "cycle_j",
    "coefficient_covariance",
    "training_start",
    "training_end",
    "training_count",
    "alpha",
    "condition_number",
    "validation_count",
    "window",
    "estimation_method",
    "forgetting_factor",
    "status",
)

_RESULT_FIELDS = ("paths", "covariance")
_VALID_STATUSES = frozenset(
    {
        "estimated",
        "insufficient_history",
        "not_identifiable",
        "unavailable",
    }
)


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


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


def _alpha_grid(values: object) -> tuple[float, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("alpha_grid must be an iterable of real numbers")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError("alpha_grid must be an iterable of real numbers") from error
    if not supplied:
        raise ValueError("alpha_grid must contain at least one alpha")
    normalized = tuple(_finite_real(value, "alpha") for value in supplied)
    if any(alpha < 0.0 for alpha in normalized):
        raise ValueError("alpha values must be nonnegative")
    if len(normalized) != len(set(normalized)):
        raise ValueError("alpha_grid values must be unique")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class CycleToChannelConfig:
    """Configuration for causal batch or recursive ridge path estimation."""

    window: str = "expanding"
    rolling_window: int | None = None
    min_training_count: int = 36
    alpha_grid: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0)
    validation_window: int = 12
    condition_number_threshold: float = 1_000_000.0
    recursive: bool = False
    forgetting_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.window not in {"expanding", "rolling"}:
            raise ValueError("window must be 'expanding' or 'rolling'")
        minimum_count = _positive_integer(
            self.min_training_count,
            "min_training_count",
        )
        if minimum_count < len(CYCLE_IDS) + 3:
            raise ValueError("min_training_count must be at least 10")
        validation_window = _positive_integer(
            self.validation_window,
            "validation_window",
        )
        normalized_rolling_window: int | None = None
        if self.window == "rolling":
            normalized_rolling_window = _positive_integer(
                self.rolling_window,
                "rolling_window",
            )
            if normalized_rolling_window < minimum_count:
                raise ValueError(
                    "rolling_window cannot be smaller than min_training_count"
                )
        elif self.rolling_window is not None:
            raise ValueError("rolling_window is only valid for a rolling window")
        if not isinstance(self.recursive, (bool, np.bool_)):
            raise TypeError("recursive must be a boolean")
        forgetting_factor = _finite_real(
            self.forgetting_factor,
            "forgetting_factor",
        )
        if not 0.0 < forgetting_factor <= 1.0:
            raise ValueError("forgetting_factor must be in (0, 1]")
        if not self.recursive and forgetting_factor != 1.0:
            raise ValueError("forgetting_factor must be 1 when recursive is disabled")
        threshold = _finite_real(
            self.condition_number_threshold,
            "condition_number_threshold",
        )
        if threshold <= 0.0:
            raise ValueError("condition_number_threshold must be positive")
        object.__setattr__(self, "rolling_window", normalized_rolling_window)
        object.__setattr__(self, "min_training_count", minimum_count)
        object.__setattr__(self, "validation_window", validation_window)
        object.__setattr__(self, "alpha_grid", _alpha_grid(self.alpha_grid))
        object.__setattr__(self, "condition_number_threshold", threshold)
        object.__setattr__(self, "recursive", bool(self.recursive))
        object.__setattr__(self, "forgetting_factor", forgetting_factor)


def _validate_group_shapes(
    paths: pd.DataFrame,
    covariance: pd.DataFrame,
) -> None:
    path_keys: set[tuple[object, object]] = set()
    for key, group in paths.groupby(["date", "channel_id"], sort=False):
        path_keys.add(key)
        if set(group["cycle_id"]) != set(CYCLE_IDS) or len(group) != 7:
            raise ValueError("paths must retain C1 through C7 for every group")
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("paths status must be constant within each group")
        predicted = group["predicted_channel_innovation"].iloc[0]
        if np.isfinite(predicted):
            if not group["predicted_channel_innovation"].eq(predicted).all():
                raise ValueError("predicted channel innovation must be grouped")
            intercept = group["intercept"].iloc[0]
            contributions = group["contribution"].to_numpy(dtype="float64")
            expected = float(intercept) + float(contributions.sum())
            if not np.isclose(predicted, expected, atol=1e-10, rtol=1e-10):
                raise ValueError("predicted channel innovation does not conserve")
            observed = group["observed_channel_innovation"].iloc[0]
            residual = group["channel_residual"].iloc[0]
            if np.isfinite(observed):
                expected_residual = float(observed) - float(predicted)
                if not np.isfinite(residual) or not np.isclose(
                    residual,
                    expected_residual,
                    atol=1e-10,
                    rtol=1e-10,
                ):
                    raise ValueError("channel residual does not conserve")
        training_rows = group.loc[group["training_end"].notna()]
        if bool((training_rows["training_end"] >= training_rows["date"]).any()):
            raise ValueError("training_end must be earlier than attribution date")

    covariance_keys: set[tuple[object, object]] = set()
    for key, group in covariance.groupby(["date", "channel_id"], sort=False):
        covariance_keys.add(key)
        if len(group) != 49:
            raise ValueError("covariance must retain a 7 by 7 matrix per group")
        pairs = set(zip(group["cycle_i"], group["cycle_j"], strict=True))
        expected_pairs = {
            (cycle_i, cycle_j) for cycle_i in CYCLE_IDS for cycle_j in CYCLE_IDS
        }
        if pairs != expected_pairs:
            raise ValueError("covariance must retain every C1 through C7 pair")
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("covariance status must be constant within each group")
        values = group["coefficient_covariance"]
        if values.notna().any():
            if values.isna().any():
                raise ValueError("covariance matrices cannot be partially missing")
            matrix = group.pivot(
                index="cycle_i",
                columns="cycle_j",
                values="coefficient_covariance",
            ).loc[list(CYCLE_IDS), list(CYCLE_IDS)]
            if not np.allclose(matrix, matrix.T, atol=1e-10, rtol=1e-10):
                raise ValueError("coefficient covariance must be symmetric")
    if path_keys != covariance_keys:
        raise ValueError("paths and covariance groups must align")


@dataclass(frozen=True)
class CycleToChannelResult:
    """Detached path contributions and coefficient covariance matrices."""

    paths: pd.DataFrame
    covariance: pd.DataFrame

    def __post_init__(self) -> None:
        paths = object.__getattribute__(self, "paths")
        covariance = object.__getattribute__(self, "covariance")
        if not isinstance(paths, pd.DataFrame):
            raise TypeError("paths must be a pandas DataFrame")
        if not isinstance(covariance, pd.DataFrame):
            raise TypeError("covariance must be a pandas DataFrame")
        if tuple(paths.columns) != CYCLE_TO_CHANNEL_PATH_COLUMNS:
            raise ValueError("paths columns do not match the attribution contract")
        if tuple(covariance.columns) != CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS:
            raise ValueError("covariance columns do not match the attribution contract")
        if paths.duplicated(["date", "channel_id", "cycle_id"]).any():
            raise ValueError("date × channel_id × cycle_id paths must be unique")
        if covariance.duplicated(["date", "channel_id", "cycle_i", "cycle_j"]).any():
            raise ValueError(
                "date × channel_id × cycle_i × cycle_j covariance must be unique"
            )
        if not set(paths["status"]).issubset(_VALID_STATUSES):
            raise ValueError("paths contain an unknown attribution status")
        if not set(covariance["status"]).issubset(_VALID_STATUSES):
            raise ValueError("covariance contains an unknown attribution status")
        _validate_group_shapes(paths, covariance)
        object.__setattr__(self, "paths", _copy_frame(paths))
        object.__setattr__(self, "covariance", _copy_frame(covariance))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.paths

    @property
    def coefficient_covariance(self) -> pd.DataFrame:
        return self.covariance


def _normalize_dates(values: pd.Series, name: str) -> pd.Series:
    normalized: list[pd.Timestamp] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            raise ValueError(f"{name} dates cannot be missing")
        if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
            raise TypeError(f"{name} dates must be date-like values")
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{name} dates must be valid date-like values") from error
        if timestamp.tzinfo is not None:
            raise ValueError(f"{name} dates must be timezone-naive")
        normalized.append(timestamp.normalize())
    return pd.Series(normalized, index=values.index, dtype="datetime64[ns]")


def _normalize_innovations(values: pd.Series, name: str) -> pd.Series:
    normalized: list[float] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            normalized.append(np.nan)
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (Real, np.integer, np.floating),
        ):
            raise TypeError(f"{name} innovations must be numeric or missing")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"{name} innovations must be finite or missing")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _required_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, str, str],
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")
    if values.empty:
        raise ValueError(f"{name} must contain at least one row")
    return values.loc[:, list(columns)].copy(deep=True)


def _normalize_cycles(values: object) -> pd.DataFrame:
    cycles = _required_frame(
        values,
        name="cycle_innovations",
        columns=("date", "cycle_id", "innovation"),
    )
    cycles["date"] = _normalize_dates(cycles["date"], "cycle innovation")
    if any(
        not isinstance(cycle_id, str) or not cycle_id for cycle_id in cycles["cycle_id"]
    ):
        raise TypeError("cycle_id values must be non-empty strings")
    if cycles.duplicated(["date", "cycle_id"]).any():
        raise ValueError("date × cycle_id cycle innovations must be unique")
    cycles["innovation"] = _normalize_innovations(
        cycles["innovation"],
        "cycle",
    )
    for _, group in cycles.groupby("date", sort=False):
        if len(group) != len(CYCLE_IDS) or set(group["cycle_id"]) != set(CYCLE_IDS):
            raise ValueError(
                "cycle innovations must contain exactly C1 through C7 for every date"
            )
    cycle_order = {cycle_id: order for order, cycle_id in enumerate(CYCLE_IDS)}
    cycles["_cycle_order"] = cycles["cycle_id"].map(cycle_order)
    return (
        cycles.sort_values(
            ["date", "_cycle_order"],
            kind="stable",
        )
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )


def _normalize_channels(values: object) -> pd.DataFrame:
    channels = _required_frame(
        values,
        name="channel_innovations",
        columns=("date", "channel_id", "innovation"),
    )
    channels["date"] = _normalize_dates(
        channels["date"],
        "channel innovation",
    )
    if any(
        not isinstance(channel_id, str) or not channel_id
        for channel_id in channels["channel_id"]
    ):
        raise TypeError("channel_id values must be non-empty strings")
    if channels.duplicated(["date", "channel_id"]).any():
        raise ValueError("date × channel_id channel innovations must be unique")
    channels["innovation"] = _normalize_innovations(
        channels["innovation"],
        "channel",
    )
    return channels.sort_values(
        ["date", "channel_id"],
        kind="stable",
    ).reset_index(drop=True)


def _training_metadata(
    training: pd.DataFrame,
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, int]:
    if training.empty:
        return pd.NaT, pd.NaT, 0
    return training.index[0], training.index[-1], len(training)


def _fit_training_window(
    training: pd.DataFrame,
    config: CycleToChannelConfig,
) -> tuple[RidgeEstimate | None, float, float, int, str]:
    training_count = len(training)
    if training_count < config.min_training_count:
        return None, np.nan, np.nan, 0, "insufficient_history"
    features = training.loc[:, list(CYCLE_IDS)].to_numpy(dtype="float64")
    target = training["channel_innovation"].to_numpy(dtype="float64")
    condition_number = standardized_condition_number(features)
    if condition_number > config.condition_number_threshold:
        return None, np.nan, condition_number, 0, "not_identifiable"
    selection = select_alpha_walk_forward(
        features,
        target,
        alpha_grid=config.alpha_grid,
        min_training_count=config.min_training_count,
        validation_window=config.validation_window,
        recursive=config.recursive,
        forgetting_factor=config.forgetting_factor,
    )
    if selection is None:
        return None, np.nan, condition_number, 0, "insufficient_history"
    try:
        estimate = fit_standardized_ridge(
            features,
            target,
            alpha=selection.alpha,
            recursive=config.recursive,
            forgetting_factor=config.forgetting_factor,
        )
    except (ValueError, np.linalg.LinAlgError):
        return (
            None,
            selection.alpha,
            condition_number,
            selection.validation_count,
            "not_identifiable",
        )
    return (
        estimate,
        selection.alpha,
        condition_number,
        selection.validation_count,
        "estimated",
    )


def _windowed_history(
    eligible: pd.DataFrame,
    current_date: pd.Timestamp,
    config: CycleToChannelConfig,
) -> pd.DataFrame:
    history = eligible.loc[eligible.index < current_date]
    if config.window == "rolling":
        return history.tail(config.rolling_window)
    return history


def _path_records(
    *,
    current_date: pd.Timestamp,
    channel_id: str,
    current_cycles: np.ndarray,
    observed: float,
    estimate: RidgeEstimate | None,
    training_start: pd.Timestamp | pd.NaT,
    training_end: pd.Timestamp | pd.NaT,
    training_count: int,
    alpha: float,
    condition_number: float,
    validation_count: int,
    status: str,
    config: CycleToChannelConfig,
) -> list[dict[str, object]]:
    coefficients = np.full(len(CYCLE_IDS), np.nan, dtype="float64")
    contributions = np.full(len(CYCLE_IDS), np.nan, dtype="float64")
    intercept = np.nan
    predicted = np.nan
    residual = np.nan
    if estimate is not None:
        coefficients = estimate.coefficients
        intercept = estimate.intercept
        if np.isfinite(current_cycles).all():
            contributions = current_cycles * coefficients
            predicted = intercept + float(contributions.sum())
            if np.isfinite(observed):
                residual = observed - predicted
    method = "recursive" if config.recursive else "batch"
    return [
        {
            "date": current_date,
            "channel_id": channel_id,
            "cycle_id": cycle_id,
            "cycle_innovation": float(current_cycles[position]),
            "coefficient_mean": float(coefficients[position]),
            "contribution": float(contributions[position]),
            "intercept": float(intercept),
            "observed_channel_innovation": float(observed),
            "predicted_channel_innovation": float(predicted),
            "channel_residual": float(residual),
            "training_start": training_start,
            "training_end": training_end,
            "training_count": training_count,
            "alpha": float(alpha),
            "condition_number": float(condition_number),
            "validation_count": validation_count,
            "window": config.window,
            "estimation_method": method,
            "forgetting_factor": config.forgetting_factor,
            "status": status,
        }
        for position, cycle_id in enumerate(CYCLE_IDS)
    ]


def _covariance_records(
    *,
    current_date: pd.Timestamp,
    channel_id: str,
    estimate: RidgeEstimate | None,
    training_start: pd.Timestamp | pd.NaT,
    training_end: pd.Timestamp | pd.NaT,
    training_count: int,
    alpha: float,
    condition_number: float,
    validation_count: int,
    status: str,
    config: CycleToChannelConfig,
) -> list[dict[str, object]]:
    covariance = (
        estimate.covariance
        if estimate is not None
        else np.full((len(CYCLE_IDS), len(CYCLE_IDS)), np.nan, dtype="float64")
    )
    method = "recursive" if config.recursive else "batch"
    return [
        {
            "date": current_date,
            "channel_id": channel_id,
            "cycle_i": cycle_i,
            "cycle_j": cycle_j,
            "coefficient_covariance": float(covariance[row, column]),
            "training_start": training_start,
            "training_end": training_end,
            "training_count": training_count,
            "alpha": float(alpha),
            "condition_number": float(condition_number),
            "validation_count": validation_count,
            "window": config.window,
            "estimation_method": method,
            "forgetting_factor": config.forgetting_factor,
            "status": status,
        }
        for row, cycle_i in enumerate(CYCLE_IDS)
        for column, cycle_j in enumerate(CYCLE_IDS)
    ]


def _sort_outputs(
    paths: pd.DataFrame,
    covariance: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cycle_order = {cycle_id: order for order, cycle_id in enumerate(CYCLE_IDS)}
    paths["_cycle_order"] = paths["cycle_id"].map(cycle_order)
    paths = (
        paths.sort_values(
            ["date", "channel_id", "_cycle_order"],
            kind="stable",
        )
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )
    covariance["_cycle_i_order"] = covariance["cycle_i"].map(cycle_order)
    covariance["_cycle_j_order"] = covariance["cycle_j"].map(cycle_order)
    covariance = (
        covariance.sort_values(
            ["date", "channel_id", "_cycle_i_order", "_cycle_j_order"],
            kind="stable",
        )
        .drop(columns=["_cycle_i_order", "_cycle_j_order"])
        .reset_index(drop=True)
    )
    return paths, covariance


def estimate_cycle_to_channel(
    cycle_innovations: pd.DataFrame,
    channel_innovations: pd.DataFrame,
    *,
    config: CycleToChannelConfig | None = None,
) -> CycleToChannelResult:
    """Estimate date-specific causal C1-C7 paths into channel innovations."""

    if config is None:
        normalized_config = CycleToChannelConfig()
    elif isinstance(config, CycleToChannelConfig):
        normalized_config = config
    else:
        raise TypeError("config must be a CycleToChannelConfig")
    cycles = _normalize_cycles(cycle_innovations)
    channels = _normalize_channels(channel_innovations)
    cycle_wide = cycles.pivot(
        index="date",
        columns="cycle_id",
        values="innovation",
    ).loc[:, list(CYCLE_IDS)]
    path_rows: list[dict[str, object]] = []
    covariance_rows: list[dict[str, object]] = []
    for channel_id, channel_group in channels.groupby("channel_id", sort=True):
        channel_series = channel_group.set_index("date")["innovation"].sort_index()
        aligned = cycle_wide.join(
            channel_series.rename("channel_innovation"),
            how="inner",
        )
        finite_training = np.isfinite(
            aligned.loc[:, [*CYCLE_IDS, "channel_innovation"]].to_numpy(dtype="float64")
        ).all(axis=1)
        eligible = aligned.loc[finite_training]
        for current_date, observed in channel_series.items():
            training = _windowed_history(
                eligible,
                current_date,
                normalized_config,
            )
            training_start, training_end, training_count = _training_metadata(training)
            estimate, alpha, condition_number, validation_count, fit_status = (
                _fit_training_window(training, normalized_config)
            )
            if current_date in cycle_wide.index:
                current_cycles = cycle_wide.loc[
                    current_date,
                    list(CYCLE_IDS),
                ].to_numpy(dtype="float64")
            else:
                current_cycles = np.full(
                    len(CYCLE_IDS),
                    np.nan,
                    dtype="float64",
                )
            current_available = np.isfinite(current_cycles).all() and np.isfinite(
                observed
            )
            status = fit_status if current_available else "unavailable"
            path_rows.extend(
                _path_records(
                    current_date=current_date,
                    channel_id=channel_id,
                    current_cycles=current_cycles,
                    observed=float(observed),
                    estimate=estimate,
                    training_start=training_start,
                    training_end=training_end,
                    training_count=training_count,
                    alpha=alpha,
                    condition_number=condition_number,
                    validation_count=validation_count,
                    status=status,
                    config=normalized_config,
                )
            )
            covariance_rows.extend(
                _covariance_records(
                    current_date=current_date,
                    channel_id=channel_id,
                    estimate=estimate,
                    training_start=training_start,
                    training_end=training_end,
                    training_count=training_count,
                    alpha=alpha,
                    condition_number=condition_number,
                    validation_count=validation_count,
                    status=status,
                    config=normalized_config,
                )
            )
    paths = pd.DataFrame(path_rows, columns=CYCLE_TO_CHANNEL_PATH_COLUMNS)
    covariance = pd.DataFrame(
        covariance_rows,
        columns=CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS,
    )
    paths, covariance = _sort_outputs(paths, covariance)
    return CycleToChannelResult(paths=paths, covariance=covariance)


__all__ = [
    "CYCLE_IDS",
    "CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS",
    "CYCLE_TO_CHANNEL_PATH_COLUMNS",
    "CycleToChannelConfig",
    "CycleToChannelResult",
    "estimate_cycle_to_channel",
]
