"""Past-only cycle identifiability and deterministic merged groups."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.stage1 import CYCLE_IDS


IDENTIFIABILITY_COLUMNS = (
    "date",
    "asset_id",
    "group_id",
    "cycle_id",
    "group_size",
    "history_count",
    "condition_number",
    "max_abs_correlation",
    "method",
    "status",
)

_ALL_CYCLES_GROUP = "+".join(CYCLE_IDS)
_VALID_STAGE1_STATUSES = frozenset(
    {
        "estimated",
        "insufficient_history",
        "not_identifiable",
        "unavailable",
    }
)


def _positive_integer(value: object, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be an integer")
    numeric = int(value)
    if numeric < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
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


@dataclass(frozen=True)
class IdentifiabilityConfig:
    """Thresholds for past-only correlation grouping."""

    min_history_count: int = 12
    correlation_threshold: float = 0.95
    condition_number_threshold: float = 1_000_000.0

    def __post_init__(self) -> None:
        minimum_history = _positive_integer(
            self.min_history_count,
            "min_history_count",
            minimum=2,
        )
        correlation_threshold = _finite_real(
            self.correlation_threshold,
            "correlation_threshold",
        )
        if not 0.0 < correlation_threshold <= 1.0:
            raise ValueError("correlation_threshold must be in (0, 1]")
        condition_threshold = _finite_real(
            self.condition_number_threshold,
            "condition_number_threshold",
        )
        if condition_threshold <= 0.0:
            raise ValueError("condition_number_threshold must be positive")
        object.__setattr__(self, "min_history_count", minimum_history)
        object.__setattr__(self, "correlation_threshold", correlation_threshold)
        object.__setattr__(
            self,
            "condition_number_threshold",
            condition_threshold,
        )


def _source_frame(values: object, attribute: str, name: str) -> pd.DataFrame:
    if isinstance(values, pd.DataFrame):
        return values.copy(deep=True)
    frame = getattr(values, attribute, None)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame or expose .{attribute}")
    return frame.copy(deep=True)


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


def _validate_identifiers(values: pd.Series, name: str) -> None:
    if any(not isinstance(value, str) or not value for value in values.tolist()):
        raise TypeError(f"{name} values must be non-empty strings")


def _normalize_numeric(values: pd.Series, name: str) -> pd.Series:
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
            raise TypeError(f"{name} values must be numeric or missing")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"{name} values must be finite or missing")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _normalize_stage1_paths(values: object) -> pd.DataFrame:
    frame = _source_frame(values, "paths", "stage1_paths")
    required = ("date", "channel_id", "cycle_id", "cycle_innovation", "status")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"stage1_paths is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError("stage1_paths must contain at least one row")
    frame = frame.loc[:, list(required)].copy(deep=True)
    frame["date"] = _normalize_dates(frame["date"], "stage1 path")
    _validate_identifiers(frame["channel_id"], "channel_id")
    _validate_identifiers(frame["cycle_id"], "cycle_id")
    _validate_identifiers(frame["status"], "status")
    if not set(frame["cycle_id"]).issubset(CYCLE_IDS):
        raise ValueError("stage1_paths cycle_id values must be C1 through C7")
    if not set(frame["status"]).issubset(_VALID_STAGE1_STATUSES):
        raise ValueError("stage1_paths contain an unknown status")
    if frame.duplicated(["date", "channel_id", "cycle_id"]).any():
        raise ValueError("stage1 path rows must be unique")
    frame["cycle_innovation"] = _normalize_numeric(
        frame["cycle_innovation"],
        "cycle innovation",
    )
    for _, group in frame.groupby(["date", "channel_id"], sort=False):
        if len(group) != len(CYCLE_IDS) or set(group["cycle_id"]) != set(CYCLE_IDS):
            raise ValueError(
                "each present stage1 channel group must contain C1 through C7"
            )
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("stage1 status must be constant within a channel group")
    for _, group in frame.groupby(["date", "cycle_id"], sort=False):
        innovations = group["cycle_innovation"]
        if innovations.isna().all():
            continue
        if innovations.isna().any():
            raise ValueError("cycle innovation must agree across channels")
        values_array = innovations.to_numpy(dtype="float64")
        if not np.allclose(
            values_array,
            values_array[0],
            atol=1e-12,
            rtol=0.0,
        ):
            raise ValueError("cycle innovation must agree across channels")
    return frame.sort_values(
        ["date", "channel_id", "cycle_id"],
        kind="stable",
    ).reset_index(drop=True)


def _normalize_attribution_index(values: object) -> pd.DataFrame:
    frame = _source_frame(values, "components", "attribution_index")
    required = ("date", "asset_id")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"attribution_index is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError("attribution_index must contain at least one row")
    frame = frame.loc[:, list(required)].copy(deep=True)
    frame["date"] = _normalize_dates(frame["date"], "attribution")
    _validate_identifiers(frame["asset_id"], "asset_id")
    return (
        frame.drop_duplicates()
        .sort_values(
            ["date", "asset_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _unique_cycle_history(paths: pd.DataFrame) -> pd.DataFrame:
    history = paths.drop_duplicates(["date", "cycle_id"])[
        ["date", "cycle_id", "cycle_innovation"]
    ]
    return history.pivot(
        index="date",
        columns="cycle_id",
        values="cycle_innovation",
    ).reindex(columns=list(CYCLE_IDS))


def _unallocated_records(
    *,
    current_date: pd.Timestamp,
    asset_id: str,
    history_count: int,
    condition_number: float,
    max_abs_correlation: float,
    status: str,
) -> list[dict[str, object]]:
    return [
        {
            "date": current_date,
            "asset_id": asset_id,
            "group_id": _ALL_CYCLES_GROUP,
            "cycle_id": cycle_id,
            "group_size": len(CYCLE_IDS),
            "history_count": history_count,
            "condition_number": condition_number,
            "max_abs_correlation": max_abs_correlation,
            "method": "unallocated_total",
            "status": status,
        }
        for cycle_id in CYCLE_IDS
    ]


def _current_stage1_failure(
    paths: pd.DataFrame, current_date: pd.Timestamp
) -> str | None:
    current = paths.loc[paths["date"].eq(current_date)]
    if current.empty:
        return "unavailable"
    if current["status"].eq("estimated").any():
        return None
    if current["status"].eq("insufficient_history").all():
        return "insufficient_history"
    return "not_identifiable"


def _correlation_matrix(history: pd.DataFrame) -> np.ndarray:
    values = history.to_numpy(dtype="float64")
    centered = values - values.mean(axis=0)
    scales = np.sqrt(np.sum(np.square(centered), axis=0))
    denominator = np.outer(scales, scales)
    numerator = centered.T @ centered
    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = numerator / denominator
    np.fill_diagonal(correlation, 1.0)
    return correlation


def _condition_number(correlation: np.ndarray) -> float:
    if not np.isfinite(correlation).all():
        return np.inf
    if np.linalg.matrix_rank(correlation) < correlation.shape[0]:
        return np.inf
    try:
        condition_number = float(np.linalg.cond(correlation))
    except np.linalg.LinAlgError:
        return np.inf
    return condition_number if np.isfinite(condition_number) else np.inf


def _maximum_abs_correlation(correlation: np.ndarray) -> float:
    off_diagonal = np.abs(correlation.copy())
    np.fill_diagonal(off_diagonal, np.nan)
    finite = off_diagonal[np.isfinite(off_diagonal)]
    maximum = float(finite.max()) if finite.size else np.nan
    return 1.0 if np.isclose(maximum, 1.0, atol=1e-12, rtol=0.0) else maximum


def _merged_groups(
    correlation: np.ndarray,
    threshold: float,
) -> list[tuple[str, ...]]:
    positions = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    parents = {cycle_id: cycle_id for cycle_id in CYCLE_IDS}

    def find(cycle_id: str) -> str:
        parent = parents[cycle_id]
        while parent != parents[parent]:
            parent = parents[parent]
        while cycle_id != parent:
            next_cycle = parents[cycle_id]
            parents[cycle_id] = parent
            cycle_id = next_cycle
        return parent

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if positions[left_root] <= positions[right_root]:
            parents[right_root] = left_root
        else:
            parents[left_root] = right_root

    for left_position, left_cycle in enumerate(CYCLE_IDS):
        for right_position in range(left_position + 1, len(CYCLE_IDS)):
            value = correlation[left_position, right_position]
            if np.isfinite(value) and abs(value) >= threshold:
                union(left_cycle, CYCLE_IDS[right_position])
    grouped: dict[str, list[str]] = {}
    for cycle_id in CYCLE_IDS:
        grouped.setdefault(find(cycle_id), []).append(cycle_id)
    return [tuple(grouped[root]) for root in sorted(grouped, key=positions.__getitem__)]


def _reduced_condition_number(
    history: pd.DataFrame,
    groups: list[tuple[str, ...]],
) -> float:
    representatives = [group[0] for group in groups]
    if len(representatives) == 1:
        return 1.0
    reduced_correlation = _correlation_matrix(history.loc[:, representatives])
    return _condition_number(reduced_correlation)


def _identified_records(
    *,
    current_date: pd.Timestamp,
    asset_id: str,
    history_count: int,
    condition_number: float,
    correlation: np.ndarray,
    groups: list[tuple[str, ...]],
) -> list[dict[str, object]]:
    cycle_positions = {
        cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)
    }
    records: list[dict[str, object]] = []
    for group in groups:
        group_id = "+".join(group)
        status = "merged_cycles" if len(group) > 1 else "independent"
        if len(group) > 1:
            group_positions = [cycle_positions[cycle_id] for cycle_id in group]
            values = [
                abs(correlation[left, right])
                for left_position, left in enumerate(group_positions)
                for right in group_positions[left_position + 1 :]
                if np.isfinite(correlation[left, right])
            ]
            maximum = float(max(values)) if values else np.nan
        else:
            position = cycle_positions[group[0]]
            values = [
                abs(correlation[position, other_position])
                for other_position in range(len(CYCLE_IDS))
                if other_position != position
                and np.isfinite(correlation[position, other_position])
            ]
            maximum = float(max(values)) if values else np.nan
        if np.isclose(maximum, 1.0, atol=1e-12, rtol=0.0):
            maximum = 1.0
        for cycle_id in group:
            records.append(
                {
                    "date": current_date,
                    "asset_id": asset_id,
                    "group_id": group_id,
                    "cycle_id": cycle_id,
                    "group_size": len(group),
                    "history_count": history_count,
                    "condition_number": condition_number,
                    "max_abs_correlation": maximum,
                    "method": "correlation_union_find",
                    "status": status,
                }
            )
    return records


def _date_records(
    *,
    current_date: pd.Timestamp,
    paths: pd.DataFrame,
    cycle_history: pd.DataFrame,
    config: IdentifiabilityConfig,
) -> list[dict[str, object]]:
    past = cycle_history.loc[cycle_history.index < current_date].dropna(how="any")
    history_count = len(past)
    current_failure = _current_stage1_failure(paths, current_date)
    if current_failure is not None:
        return _unallocated_records(
            current_date=current_date,
            asset_id="",
            history_count=history_count,
            condition_number=np.nan,
            max_abs_correlation=np.nan,
            status=current_failure,
        )
    if history_count < config.min_history_count:
        return _unallocated_records(
            current_date=current_date,
            asset_id="",
            history_count=history_count,
            condition_number=np.nan,
            max_abs_correlation=np.nan,
            status="insufficient_history",
        )
    correlation = _correlation_matrix(past)
    condition_number = _condition_number(correlation)
    maximum_correlation = _maximum_abs_correlation(correlation)
    groups = _merged_groups(correlation, config.correlation_threshold)
    has_merged_group = any(len(group) > 1 for group in groups)
    reduced_condition_number = _reduced_condition_number(past, groups)
    if condition_number > config.condition_number_threshold and (
        not has_merged_group
        or reduced_condition_number > config.condition_number_threshold
    ):
        return _unallocated_records(
            current_date=current_date,
            asset_id="",
            history_count=history_count,
            condition_number=condition_number,
            max_abs_correlation=maximum_correlation,
            status="not_identifiable",
        )
    return _identified_records(
        current_date=current_date,
        asset_id="",
        history_count=history_count,
        condition_number=condition_number,
        correlation=correlation,
        groups=groups,
    )


def identify_cycle_groups(
    stage1_paths: object,
    attribution_index: object,
    *,
    config: IdentifiabilityConfig | None = None,
) -> pd.DataFrame:
    """Identify stable single cycles or deterministic merged cycle groups."""

    normalized_config = config or IdentifiabilityConfig()
    if not isinstance(normalized_config, IdentifiabilityConfig):
        raise TypeError("config must be an IdentifiabilityConfig")
    paths = _normalize_stage1_paths(stage1_paths)
    attribution = _normalize_attribution_index(attribution_index)
    cycle_history = _unique_cycle_history(paths)
    templates = {
        current_date: _date_records(
            current_date=current_date,
            paths=paths,
            cycle_history=cycle_history,
            config=normalized_config,
        )
        for current_date in attribution["date"].drop_duplicates().tolist()
    }
    records: list[dict[str, object]] = []
    for current_date, asset_id in attribution.itertuples(index=False, name=None):
        records.extend(
            {**record, "asset_id": asset_id} for record in templates[current_date]
        )
    result = pd.DataFrame.from_records(records, columns=IDENTIFIABILITY_COLUMNS)
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    result["_cycle_order"] = result["cycle_id"].map(cycle_order)
    return (
        result.sort_values(
            ["date", "asset_id", "_cycle_order"],
            kind="stable",
        )
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )
