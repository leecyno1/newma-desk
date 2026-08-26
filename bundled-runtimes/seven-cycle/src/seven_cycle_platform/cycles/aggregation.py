"""Causal category-balanced aggregation for transformed feature panels."""

from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.cycles.preprocess import expanding_standardize


_RESULT_FIELD_NAMES = (
    "aggregate",
    "aligned_members",
    "member_signs",
    "aligned_categories",
    "category_signs",
    "orientation_sign",
    "member_breadth",
    "category_breadth",
)


def _same_index(left: pd.Index, right: pd.Index) -> bool:
    return left.equals(right) and left.names == right.names


def _readonly_copy(value: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    copied = value.copy(deep=True)
    if isinstance(copied, pd.DataFrame):
        for block in copied._mgr.blocks:
            block.values.setflags(write=False)
    else:
        copied.to_numpy(copy=False).setflags(write=False)
    return copied


@dataclass(frozen=True)
class CategoryAggregationResult:
    """Immutable aligned aggregate history and causal diagnostics."""

    aggregate: pd.Series
    aligned_members: pd.DataFrame
    member_signs: pd.DataFrame
    aligned_categories: pd.DataFrame
    category_signs: pd.DataFrame
    orientation_sign: pd.Series
    member_breadth: pd.Series
    category_breadth: pd.Series

    def __post_init__(self) -> None:
        aggregate = object.__getattribute__(self, "aggregate")
        if not isinstance(aggregate, pd.Series):
            raise TypeError("aggregate must be a pandas Series")

        frame_names = (
            "aligned_members",
            "member_signs",
            "aligned_categories",
            "category_signs",
        )
        series_names = (
            "orientation_sign",
            "member_breadth",
            "category_breadth",
        )
        for field_name in frame_names:
            value = object.__getattribute__(self, field_name)
            if not isinstance(value, pd.DataFrame):
                raise TypeError(f"{field_name} must be a pandas DataFrame")
        for field_name in series_names:
            value = object.__getattribute__(self, field_name)
            if not isinstance(value, pd.Series):
                raise TypeError(f"{field_name} must be a pandas Series")
            if not _same_index(value.index, aggregate.index):
                raise ValueError(f"{field_name} index must align with aggregate")

        aligned_members = object.__getattribute__(self, "aligned_members")
        member_signs = object.__getattribute__(self, "member_signs")
        if (
            not _same_index(member_signs.index, aligned_members.index)
            or not member_signs.columns.equals(aligned_members.columns)
            or member_signs.columns.names != aligned_members.columns.names
        ):
            raise ValueError("member_signs must align with aligned_members")
        aligned_categories = object.__getattribute__(self, "aligned_categories")
        category_signs = object.__getattribute__(self, "category_signs")
        if (
            not _same_index(category_signs.index, aligned_categories.index)
            or not category_signs.columns.equals(aligned_categories.columns)
            or category_signs.columns.names != aligned_categories.columns.names
        ):
            raise ValueError("category_signs must align with aligned_categories")
        for field_name in frame_names:
            value = object.__getattribute__(self, field_name)
            if not _same_index(value.index, aggregate.index):
                raise ValueError(f"{field_name} index must align with aggregate")

        for field_name in _RESULT_FIELD_NAMES:
            value = object.__getattribute__(self, field_name)
            object.__setattr__(self, field_name, _readonly_copy(value))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELD_NAMES and isinstance(
            value,
            (pd.Series, pd.DataFrame),
        ):
            return value.copy(deep=True)
        return value


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    if int(value) < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _nonnegative_finite(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a nonnegative finite number")
    numeric = float(value)
    if not np.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be a nonnegative finite number")
    return numeric


def _numeric_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel must be a pandas DataFrame")
    if panel.columns.has_duplicates:
        raise ValueError("panel columns must be unique")
    if panel.index.has_duplicates:
        raise ValueError("panel index must be unique")
    if not panel.index.is_monotonic_increasing:
        raise ValueError("panel index must be monotonic increasing")
    return (
        panel.copy(deep=True)
        .apply(pd.to_numeric, errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )


def _availability_frame(
    panel: pd.DataFrame,
    availability_mask: pd.DataFrame | None,
) -> pd.DataFrame:
    if availability_mask is None:
        return panel.notna()
    if not isinstance(availability_mask, pd.DataFrame):
        raise TypeError("availability_mask must be a pandas DataFrame or None")

    mask = availability_mask.copy(deep=True)
    if mask.index.has_duplicates or mask.columns.has_duplicates:
        raise ValueError("availability_mask axes must be unique")
    if not mask.index.equals(panel.index) or mask.index.names != panel.index.names:
        raise ValueError(
            "availability_mask index labels and order must exactly match panel"
        )
    if (
        not mask.columns.equals(panel.columns)
        or mask.columns.names != panel.columns.names
    ):
        raise ValueError(
            "availability_mask column labels and order must exactly match panel"
        )

    normalized = np.zeros(mask.shape, dtype="bool")
    for row_position in range(mask.shape[0]):
        for column_position in range(mask.shape[1]):
            value = mask.iat[row_position, column_position]
            missing = pd.isna(value)
            if isinstance(missing, (bool, np.bool_)) and missing:
                normalized[row_position, column_position] = False
            elif isinstance(value, (bool, np.bool_)):
                normalized[row_position, column_position] = bool(value)
            else:
                raise ValueError(
                    "availability_mask values must be boolean or missing"
                )
    return pd.DataFrame(
        normalized,
        index=panel.index,
        columns=panel.columns,
        dtype="bool",
    )


def _category_series(
    columns: pd.Index,
    categories: Mapping[object, str] | pd.Series,
) -> pd.Series:
    if isinstance(categories, pd.Series):
        mapping = categories.copy(deep=True)
    elif isinstance(categories, Mapping):
        mapping = pd.Series(dict(categories), dtype="object")
    else:
        raise TypeError("categories must be a mapping or pandas Series")

    if mapping.index.has_duplicates:
        raise ValueError("category mapping keys must be unique")
    missing_columns = columns.difference(mapping.index)
    if not missing_columns.empty:
        missing = ", ".join(map(str, missing_columns.tolist()))
        raise ValueError(f"missing categories for panel columns: {missing}")
    extra_columns = mapping.index.difference(columns)
    if not extra_columns.empty:
        extra = ", ".join(map(str, extra_columns.tolist()))
        raise ValueError(f"category mapping contains unknown columns: {extra}")

    normalized = mapping.reindex(columns).astype("object")
    category_values: list[str] = []
    for column, category in normalized.items():
        if pd.isna(category):
            raise ValueError(f"blank category for panel column: {column}")
        label = str(category).strip()
        if not label:
            raise ValueError(f"blank category for panel column: {column}")
        category_values.append(label)
    return pd.Series(category_values, index=columns, name="category", dtype="object")


def _stable_signs(correlation: pd.Series, hysteresis: float) -> pd.Series:
    current_sign = 1.0
    signs = np.ones(len(correlation), dtype="float64")
    for position, value in enumerate(correlation.to_numpy(dtype="float64")):
        if np.isfinite(value):
            if value > hysteresis:
                current_sign = 1.0
            elif value < -hysteresis:
                current_sign = -1.0
        signs[position] = current_sign
    return pd.Series(signs, index=correlation.index, dtype="float64")


def _align_matrix(
    matrix: pd.DataFrame,
    *,
    min_observations: int,
    hysteresis: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    normalized = matrix.apply(
        lambda column: expanding_standardize(column, min_observations),
        axis=0,
    ).astype("float64")
    reference = normalized.mean(axis=1, skipna=True)
    sign_columns: list[pd.Series] = []
    for column in normalized.columns:
        correlation = (
            normalized[column]
            .expanding(min_periods=min_observations)
            .corr(reference)
            .shift(1)
        )
        sign_columns.append(
            _stable_signs(correlation, hysteresis).rename(column)
        )
    sign_matrix = pd.concat(sign_columns, axis=1).reindex(columns=normalized.columns)
    return normalized * sign_matrix, sign_matrix


def _orientation_sign(
    aggregate: pd.Series,
    orientation_anchor: pd.Series | None,
    *,
    min_observations: int,
    hysteresis: float,
) -> pd.Series:
    if orientation_anchor is None:
        return pd.Series(1.0, index=aggregate.index, dtype="float64")
    if not isinstance(orientation_anchor, pd.Series):
        raise TypeError("orientation_anchor must be a pandas Series or None")
    anchor = (
        pd.to_numeric(orientation_anchor.copy(deep=True), errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
        .reindex(aggregate.index)
    )
    normalized_anchor = expanding_standardize(anchor, min_observations)
    correlation = (
        aggregate.expanding(min_periods=min_observations)
        .corr(normalized_anchor)
        .shift(1)
    )
    return _stable_signs(correlation, hysteresis)


def aggregate_category_balanced(
    panel: pd.DataFrame,
    categories: Mapping[object, str] | pd.Series,
    *,
    min_observations: int = 3,
    hysteresis: float = 0.10,
    orientation_anchor: pd.Series | None = None,
    availability_mask: pd.DataFrame | None = None,
) -> CategoryAggregationResult:
    """Build a causal composite in which every available category has equal weight.

    Member and category orientations use expanding correlations shifted by one
    observation. ``availability_mask`` affects breadth diagnostics only; causal
    aggregation and sign alignment continue to use the supplied panel values.
    """

    minimum = _positive_integer(min_observations, "min_observations")
    threshold = _nonnegative_finite(hysteresis, "hysteresis")
    if threshold > 1.0:
        raise ValueError("hysteresis cannot exceed 1")

    values = _numeric_panel(panel)
    availability = _availability_frame(values, availability_mask)
    category_map = _category_series(values.columns, categories)
    if values.shape[1] == 0:
        raise ValueError("panel must contain at least one column")

    aligned_members, member_signs = _align_matrix(
        values,
        min_observations=minimum,
        hysteresis=threshold,
    )
    category_components: list[pd.Series] = []
    category_labels = sorted(category_map.unique().tolist())
    category_minimum = max(2, minimum // 2)
    for category in category_labels:
        members = category_map[category_map.eq(category)].index
        component = aligned_members.loc[:, members].mean(axis=1, skipna=True)
        category_components.append(
            expanding_standardize(component, category_minimum).rename(category)
        )
    category_matrix = pd.concat(category_components, axis=1)
    aligned_categories, category_signs = _align_matrix(
        category_matrix,
        min_observations=minimum,
        hysteresis=threshold,
    )
    aggregate = aligned_categories.mean(axis=1, skipna=True).rename("aggregate")
    orientation_sign = _orientation_sign(
        aggregate,
        orientation_anchor,
        min_observations=minimum,
        hysteresis=threshold,
    ).rename("orientation_sign")
    aligned_categories = aligned_categories.mul(orientation_sign, axis=0)
    aggregate = (aggregate * orientation_sign).rename("aggregate")

    available_members = availability
    member_breadth = (
        available_members.sum(axis=1).astype("float64") / float(values.shape[1])
    ).rename("member_breadth")
    category_available = pd.DataFrame(
        {
            category: available_members.loc[
                :,
                category_map[category_map.eq(category)].index,
            ].any(axis=1)
            for category in category_labels
        },
        index=values.index,
    )
    category_breadth = (
        category_available.sum(axis=1).astype("float64")
        / float(len(category_labels))
    ).rename("category_breadth")

    return CategoryAggregationResult(
        aggregate=aggregate,
        aligned_members=aligned_members,
        member_signs=member_signs,
        aligned_categories=aligned_categories,
        category_signs=category_signs,
        orientation_sign=orientation_sign,
        member_breadth=member_breadth,
        category_breadth=category_breadth,
    )
