from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
import pandas as pd

from cycle_robustness_core import annual_category


ROOT = Path(__file__).resolve().parents[1]
_SOURCE_DIRECTORY = ROOT / "src"
if str(_SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIRECTORY))

_preprocess = import_module("seven_cycle_platform.cycles.preprocess")
_state_space = import_module("seven_cycle_platform.cycles.state_space")
_package_causal_transform = _preprocess._legacy_causal_transform
_package_harmonic_state_filter = _state_space.harmonic_state_filter
_package_regularize_panel = _preprocess._legacy_regularize_panel
expanding_standardize = _preprocess.expanding_standardize


PHASE_LABELS = {
    1: "Expansion",
    2: "Downturn",
    3: "Contraction",
    4: "Recovery",
}


@dataclass(frozen=True)
class PeriodSpec:
    label: str
    period: float


MONTHLY_PERIODS = (
    PeriodSpec("16_5m", 16.5),
    PeriodSpec("20m", 20.0),
    PeriodSpec("21m", 21.0),
    PeriodSpec("42m", 42.0),
)


ANNUAL_PERIODS = (
    PeriodSpec("8_33y", 100.0 / 12.0),
    PeriodSpec("9y", 9.0),
    PeriodSpec("14y", 14.0),
    PeriodSpec("16_67y", 200.0 / 12.0),
)


MONTHLY_GROWTH_CATEGORIES = ("宏观增长类（Macro Growth）",)
ANNUAL_GROWTH_CATEGORIES = (
    "real_activity",
    "real_aggregate",
    "real_per_capita",
    "labor_productivity",
)


def static_standardize(values: pd.Series) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    standard_deviation = float(series.std(ddof=0))
    if not np.isfinite(standard_deviation) or standard_deviation == 0.0:
        return pd.Series(index=series.index, dtype="float64")
    return (series - float(series.mean())) / standard_deviation


def regularize_panel(panel: pd.DataFrame, frequency: str) -> pd.DataFrame:
    return _package_regularize_panel(panel, frequency)


def causal_transform(values: pd.Series, value_type: str, frequency: str) -> pd.Series:
    return _package_causal_transform(values, value_type, frequency)


def prepare_transformed_panel(
    panel: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    frequency: str,
    min_history: int,
) -> tuple[pd.DataFrame, pd.Series]:
    regular = regularize_panel(panel, frequency)
    transformed: dict[str, pd.Series] = {}
    categories: dict[str, str] = {}

    if frequency == "M":
        selected = metadata[metadata["status"].eq("selected")].copy()
        selected = selected.drop_duplicates("panel_main_column").set_index("panel_main_column")
    else:
        selected = metadata[metadata["status"].eq("selected")].copy()
        selected = selected.drop_duplicates("column").set_index("column")

    for column in regular.columns:
        if column not in selected.index:
            continue
        value_type = str(selected.loc[column, "value_type"])
        transformed_values = causal_transform(regular[column], value_type, frequency)
        standardized = expanding_standardize(transformed_values, min_history)
        transformed[str(column)] = standardized.rename(str(column))
        if frequency == "M":
            categories[str(column)] = str(selected.loc[column, "universe_category"])
        else:
            categories[str(column)] = annual_category(str(column))

    if not transformed:
        raise RuntimeError(f"No usable {frequency} series for real-time cycle estimation")

    transformed_panel = pd.concat(transformed.values(), axis=1).sort_index()
    category_series = pd.Series(categories, name="category").reindex(transformed_panel.columns)
    return transformed_panel, category_series


def harmonic_state_filter(
    values: pd.Series,
    period: float,
    *,
    cycle_variance: float = 0.35,
    observation_variance: float = 0.65,
    half_life_cycles: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    result = _package_harmonic_state_filter(
        values,
        period,
        cycle_variance=cycle_variance,
        observation_variance=observation_variance,
        half_life_cycles=half_life_cycles,
    )
    return result.level, result.smoothed_level, result.uncertainty


def build_component_cache(
    transformed: pd.DataFrame,
    periods: Iterable[PeriodSpec],
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}
    for period_spec in periods:
        filtered: dict[str, pd.Series] = {}
        smoothed: dict[str, pd.Series] = {}
        uncertainty: dict[str, pd.Series] = {}
        for column in transformed.columns:
            filtered_series, smoothed_series, uncertainty_series = harmonic_state_filter(
                transformed[column],
                period_spec.period,
            )
            filtered[str(column)] = filtered_series
            smoothed[str(column)] = smoothed_series
            uncertainty[str(column)] = uncertainty_series
        cache[period_spec.label] = (
            pd.concat(filtered.values(), axis=1),
            pd.concat(smoothed.values(), axis=1),
            pd.concat(uncertainty.values(), axis=1),
        )
    return cache


def _stable_signs(correlation: pd.Series, hysteresis: float = 0.10) -> pd.Series:
    current = 1.0
    signs = []
    for value in correlation:
        if np.isfinite(value):
            if value > hysteresis:
                current = 1.0
            elif value < -hysteresis:
                current = -1.0
        signs.append(current)
    return pd.Series(signs, index=correlation.index, dtype="float64")


def _dynamic_align(
    matrix: pd.DataFrame,
    min_observations: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    normalized = matrix.apply(
        lambda column: expanding_standardize(column, min_observations),
        axis=0,
    )
    reference = normalized.mean(axis=1)
    sign_columns: dict[str, pd.Series] = {}
    diagnostic_rows = []
    for column in normalized.columns:
        correlation = (
            normalized[column]
            .expanding(min_periods=min_observations)
            .corr(reference)
            .shift(1)
        )
        signs = _stable_signs(correlation)
        sign_columns[str(column)] = signs.rename(str(column))
        valid_correlation = correlation.dropna()
        diagnostic_rows.append(
            {
                "member": str(column),
                "final_sign": float(signs.iloc[-1]),
                "sign_flips": int((signs.diff().abs() > 0.0).sum()),
                "median_expanding_correlation": float(valid_correlation.median())
                if not valid_correlation.empty
                else np.nan,
            }
        )
    sign_matrix = pd.concat(sign_columns.values(), axis=1)
    return normalized * sign_matrix, sign_matrix, pd.DataFrame(diagnostic_rows)


def _static_align(matrix: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    normalized = matrix.apply(static_standardize, axis=0)
    reference = normalized.mean(axis=1)
    signs: dict[str, float] = {}
    for column in normalized.columns:
        correlation = normalized[column].corr(reference)
        signs[str(column)] = -1.0 if np.isfinite(correlation) and correlation < 0.0 else 1.0
    aligned = normalized.mul(pd.Series(signs), axis=1)
    return aligned, signs


def aggregate_dynamic_components(
    components: pd.DataFrame,
    categories: pd.Series,
    *,
    growth_categories: Iterable[str],
    included_categories: Iterable[str] | None,
    min_observations: int,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    allowed = set(included_categories) if included_categories is not None else None
    category_components: dict[str, pd.Series] = {}
    member_diagnostics = []

    for category in sorted(categories.dropna().unique()):
        if allowed is not None and category not in allowed:
            continue
        columns = categories[categories.eq(category)].index.intersection(components.columns)
        if columns.empty:
            continue
        aligned, _signs, diagnostics = _dynamic_align(components.loc[:, columns], min_observations)
        category_component = aligned.mean(axis=1)
        category_component = expanding_standardize(
            category_component,
            max(12, min_observations // 2),
        )
        category_components[str(category)] = category_component.rename(str(category))
        diagnostics["category"] = str(category)
        member_diagnostics.append(diagnostics)

    if not category_components:
        raise RuntimeError("No category components available for dynamic aggregation")

    category_matrix = pd.concat(category_components.values(), axis=1)
    aligned_categories, _category_signs, category_diagnostics = _dynamic_align(
        category_matrix,
        min_observations,
    )
    composite = aligned_categories.mean(axis=1)
    growth_columns = [column for column in growth_categories if column in category_matrix.columns]
    if growth_columns:
        growth_anchor = category_matrix[growth_columns].mean(axis=1)
        orientation_correlation = (
            composite.expanding(min_periods=min_observations).corr(growth_anchor).shift(1)
        )
        orientation = _stable_signs(orientation_correlation)
        composite = composite * orientation

    composite = expanding_standardize(composite, max(12, min_observations // 2))
    category_diagnostics["category"] = "__category_alignment__"
    diagnostics = pd.concat(member_diagnostics + [category_diagnostics], ignore_index=True)
    return composite, category_matrix, diagnostics


def aggregate_static_components(
    components: pd.DataFrame,
    categories: pd.Series,
    *,
    growth_categories: Iterable[str],
    included_categories: Iterable[str] | None,
) -> pd.Series:
    allowed = set(included_categories) if included_categories is not None else None
    category_components: dict[str, pd.Series] = {}
    for category in sorted(categories.dropna().unique()):
        if allowed is not None and category not in allowed:
            continue
        columns = categories[categories.eq(category)].index.intersection(components.columns)
        if columns.empty:
            continue
        aligned, _signs = _static_align(components.loc[:, columns])
        category_components[str(category)] = static_standardize(aligned.mean(axis=1)).rename(
            str(category)
        )

    category_matrix = pd.concat(category_components.values(), axis=1)
    aligned_categories, _category_signs = _static_align(category_matrix)
    composite = aligned_categories.mean(axis=1)
    growth_columns = [column for column in growth_categories if column in category_matrix.columns]
    if growth_columns:
        growth_anchor = category_matrix[growth_columns].mean(axis=1)
        correlation = composite.corr(growth_anchor)
        if np.isfinite(correlation) and correlation < 0.0:
            composite = -composite
    return static_standardize(composite)


def quadrant_phase(component: pd.Series, smooth: int) -> pd.Series:
    level = pd.to_numeric(component, errors="coerce")
    change = level.diff().rolling(smooth, min_periods=1).mean()
    phase = pd.Series(index=level.index, dtype="float64")
    phase[(level >= 0.0) & (change >= 0.0)] = 1.0
    phase[(level >= 0.0) & (change < 0.0)] = 2.0
    phase[(level < 0.0) & (change < 0.0)] = 3.0
    phase[(level < 0.0) & (change >= 0.0)] = 4.0
    return phase


def confirm_phase(phases: pd.Series, required_observations: int) -> pd.Series:
    if required_observations <= 1:
        return phases.copy()

    confirmed = pd.Series(index=phases.index, dtype="float64")
    active_phase = np.nan
    candidate_phase = np.nan
    candidate_count = 0
    for index, phase in phases.items():
        if not np.isfinite(phase):
            confirmed.loc[index] = active_phase
            continue
        if np.isfinite(candidate_phase) and phase == candidate_phase:
            candidate_count += 1
        else:
            candidate_phase = phase
            candidate_count = 1
        if candidate_count >= required_observations:
            active_phase = candidate_phase
        confirmed.loc[index] = active_phase
    return confirmed


def build_signal_view(
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]],
    periods: Iterable[PeriodSpec],
    categories: pd.Series,
    *,
    view_name: str,
    growth_categories: Iterable[str],
    included_categories: Iterable[str] | None,
    min_observations: int,
    phase_smoothing: int,
    confirmation_observations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_columns: list[pd.Series] = []
    diagnostic_frames = []
    for period_spec in periods:
        filtered, smoothed, uncertainty = cache[period_spec.label]
        realtime, _category_matrix, diagnostics = aggregate_dynamic_components(
            filtered,
            categories,
            growth_categories=growth_categories,
            included_categories=included_categories,
            min_observations=min_observations,
        )
        final_smoother = aggregate_static_components(
            smoothed,
            categories,
            growth_categories=growth_categories,
            included_categories=included_categories,
        )
        realtime_phase = quadrant_phase(realtime, phase_smoothing)
        confirmed_phase = confirm_phase(realtime_phase, confirmation_observations)
        smoother_phase = quadrant_phase(final_smoother, phase_smoothing)

        uncertainty_mean = uncertainty.mean(axis=1)
        uncertainty_mean = expanding_standardize(
            uncertainty_mean,
            max(12, min_observations // 2),
        )

        output_columns.extend(
            [
                realtime.rename(f"RT_Cycle_{view_name}_{period_spec.label}"),
                realtime_phase.rename(f"RT_Phase_{view_name}_{period_spec.label}"),
                confirmed_phase.rename(f"Confirmed_Phase_{view_name}_{period_spec.label}"),
                final_smoother.rename(f"Smooth_Cycle_{view_name}_{period_spec.label}"),
                smoother_phase.rename(f"Smooth_Phase_{view_name}_{period_spec.label}"),
                uncertainty_mean.rename(f"RT_Uncertainty_{view_name}_{period_spec.label}"),
            ]
        )
        diagnostics["view"] = view_name
        diagnostics["period_label"] = period_spec.label
        diagnostics["period"] = period_spec.period
        diagnostic_frames.append(diagnostics)

    return pd.concat(output_columns, axis=1), pd.concat(diagnostic_frames, ignore_index=True)


def map_annual_to_monthly(
    annual_signals: pd.DataFrame,
    monthly_index: pd.DatetimeIndex,
    *,
    availability_lag_years: int = 1,
) -> pd.DataFrame:
    available = annual_signals.copy()
    available.index = pd.Index(
        pd.to_numeric(available.index, errors="raise").astype(int) + availability_lag_years,
        name="available_year",
    )
    monthly_years = pd.Index(monthly_index.year.astype(int), name="available_year")
    mapped = available.reindex(monthly_years)
    mapped.index = monthly_index
    return mapped


def phase_label(value: float | int | None) -> str:
    if value is None or not np.isfinite(value):
        return "NA"
    return PHASE_LABELS.get(int(value), "NA")
