"""Causal preprocessing for monthly and annual cycle panels."""

from datetime import date, datetime
from numbers import Integral, Real
import warnings

import numpy as np
import pandas as pd


_MIN_YEAR = 1
_MAX_YEAR = 9999
_MAX_ANNUAL_SPAN = 5000


def _frequency_kind(frequency: str) -> str:
    normalized = str(frequency).strip().upper()
    if normalized in {"M", "ME", "MONTHLY"}:
        return "monthly"
    if normalized in {"A", "Y", "YE", "ANNUAL"}:
        return "annual"
    raise ValueError("frequency must be monthly ('M') or annual ('A'/'Y')")


def _empty_monthly(
    panel: pd.DataFrame,
    *,
    preserve_index_name: bool,
) -> pd.DataFrame:
    empty = panel.iloc[0:0].copy()
    empty.index = pd.DatetimeIndex(
        [],
        dtype="datetime64[ns]",
        name=panel.index.name if preserve_index_name else None,
    )
    return empty


def _empty_annual(panel: pd.DataFrame) -> pd.DataFrame:
    empty = panel.iloc[0:0].copy()
    empty.index = pd.Index([], dtype="int64", name="year")
    return empty


def _is_timezone_aware(index: pd.Index) -> bool:
    if isinstance(index, pd.DatetimeIndex):
        return index.tz is not None
    for value in index:
        if isinstance(value, (datetime, pd.Timestamp)):
            if value.tzinfo is not None and value.utcoffset() is not None:
                return True
        elif isinstance(value, str):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    parsed = pd.Timestamp(value)
                except (TypeError, ValueError):
                    continue
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return True
    return False


def _bounded_year(value: object) -> int | None:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("boolean year values are not supported")
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and missing:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return int(value.year)
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            return None
        return int(pd.Timestamp(value).year)
    try:
        numeric = pd.to_numeric(value, errors="coerce")
        numeric_float = float(numeric)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("year values must be within supported bounds") from None
    if not np.isfinite(numeric_float) or numeric_float != np.floor(numeric_float):
        return None
    if numeric_float < _MIN_YEAR or numeric_float > _MAX_YEAR:
        raise ValueError(
            f"year values must be between {_MIN_YEAR} and {_MAX_YEAR}"
        )
    return int(numeric_float)


def _coerce_annual_years(index: pd.Index) -> np.ndarray:
    years = np.full(len(index), np.nan, dtype="float64")
    for position, value in enumerate(index):
        year = _bounded_year(value)
        if year is not None:
            years[position] = year
    return years


def _regularize_panel(
    panel: pd.DataFrame,
    frequency: str,
    *,
    preserve_final_row: bool,
) -> pd.DataFrame:
    frequency_kind = _frequency_kind(frequency)
    values = panel.copy(deep=True)

    if frequency_kind == "monthly":
        if preserve_final_row and _is_timezone_aware(values.index):
            raise ValueError("timezone-aware monthly indexes are not supported")
        index_name = values.index.name if preserve_final_row else None
        converted_index = pd.to_datetime(values.index, errors="coerce", format="mixed")
        if preserve_final_row and _is_timezone_aware(pd.Index(converted_index)):
            raise ValueError("timezone-aware monthly indexes are not supported")
        valid = np.asarray(pd.notna(converted_index), dtype=bool)
        if not valid.any():
            return _empty_monthly(
                values,
                preserve_index_name=preserve_final_row,
            )

        values = values.iloc[np.flatnonzero(valid)].copy()
        values.index = pd.DatetimeIndex(converted_index[valid], name=index_name)
        values = values.sort_index(kind="stable")
        monthly_groups = values.index.to_period("M")
        if preserve_final_row:
            values = values.groupby(
                monthly_groups,
                sort=True,
                group_keys=False,
            ).tail(1)
            values.index = values.index.to_period("M").to_timestamp("M")
        else:
            values = values.groupby(monthly_groups, sort=True).last()
            values.index = values.index.to_timestamp("M")
        full_index = pd.date_range(
            values.index.min(),
            values.index.max(),
            freq="ME",
            name=index_name,
        )
        return values.reindex(full_index)

    numeric_years = _coerce_annual_years(pd.Index(values.index))
    valid = np.isfinite(numeric_years) & (numeric_years == np.floor(numeric_years))
    if not valid.any():
        return _empty_annual(values)

    values = values.iloc[np.flatnonzero(valid)].copy()
    values.index = pd.Index(numeric_years[valid].astype("int64"), name="year")
    values = values.sort_index(kind="stable")
    if preserve_final_row:
        values = values.groupby(level=0, sort=True, group_keys=False).tail(1)
    else:
        values = values.groupby(level=0, sort=True).last()
    year_span = int(values.index.max()) - int(values.index.min()) + 1
    if year_span > _MAX_ANNUAL_SPAN:
        raise ValueError(
            f"annual year span cannot exceed {_MAX_ANNUAL_SPAN} years"
        )
    full_index = pd.Index(
        range(int(values.index.min()), int(values.index.max()) + 1),
        name="year",
    )
    return values.reindex(full_index)


def regularize_panel(panel: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Return a last-row grid, preserving monthly names and rejecting timezones."""

    return _regularize_panel(panel, frequency, preserve_final_row=True)


def _legacy_regularize_panel(panel: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Retain legacy column-wise last-non-null period selection."""

    return _regularize_panel(panel, frequency, preserve_final_row=False)


def _numeric_series(values: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(values, errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )


def _causal_level_difference(values: pd.Series) -> pd.Series:
    ordinary_difference = values.diff()
    log_difference = np.log(values.where(values > 0.0)).diff()
    nonpositive_seen = (values.notna() & values.le(0.0)).cummax()
    return log_difference.where(~nonpositive_seen, ordinary_difference)


def _full_sample_level_difference(values: pd.Series) -> pd.Series:
    available = values.dropna()
    if not available.empty and bool((available > 0.0).all()):
        return np.log(values).diff()
    return values.diff()


def _transform(
    values: pd.Series,
    value_type: str,
    frequency: str,
    *,
    legacy_full_sample_positive: bool,
) -> pd.Series:
    frequency_kind = _frequency_kind(frequency)
    series = _numeric_series(values)
    normalized_type = str(value_type).strip().lower()

    if normalized_type in {"level", "price", "price_adj"}:
        if legacy_full_sample_positive:
            return _full_sample_level_difference(series)
        return _causal_level_difference(series)
    if frequency_kind == "monthly" and normalized_type == "rate_level":
        return series.diff()
    return series


def causal_transform(
    values: pd.Series,
    value_type: str,
    frequency: str,
) -> pd.Series:
    """Apply a one-sided transformation suitable for cycle estimation."""

    return _transform(
        values,
        value_type,
        frequency,
        legacy_full_sample_positive=False,
    )


def _legacy_causal_transform(
    values: pd.Series,
    value_type: str,
    frequency: str,
) -> pd.Series:
    """Retain the former full-sample positivity rule for legacy artifacts."""

    return _transform(
        values,
        value_type,
        frequency,
        legacy_full_sample_positive=True,
    )


def expanding_standardize(
    values: pd.Series,
    min_periods: int,
    clip: float = 6.0,
) -> pd.Series:
    """Standardize each value against lagged expanding moments."""

    if isinstance(min_periods, bool) or not isinstance(min_periods, Integral):
        raise TypeError("min_periods must be a positive integer")
    if min_periods < 1:
        raise ValueError("min_periods must be a positive integer")
    if isinstance(clip, bool) or not isinstance(clip, Real):
        raise TypeError("clip must be a positive finite number")
    if not np.isfinite(clip) or clip <= 0.0:
        raise ValueError("clip must be a positive finite number")

    series = _numeric_series(values)
    expanding = series.expanding(min_periods=int(min_periods))
    prior_mean = expanding.mean().shift(1)
    prior_standard_deviation = expanding.std(ddof=0).shift(1).replace(0.0, np.nan)
    standardized = (series - prior_mean) / prior_standard_deviation
    return standardized.clip(-float(clip), float(clip))
