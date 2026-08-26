"""Governed C1-C7 state computation from causal annual and monthly panels."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.cycles.aggregation import (
    CategoryAggregationResult,
    aggregate_category_balanced,
)
from seven_cycle_platform.cycles.phase import phase_from_level_slope
from seven_cycle_platform.cycles.state_space import (
    HarmonicStateResult,
    harmonic_state_filter,
)
from seven_cycle_platform.registry.models import CycleSpec
from seven_cycle_platform.types import EvidenceLevel, MappingStatus


_CYCLE_COUNT = 7
_MINIMUM_STATE_OBSERVATIONS = 3
_LOW_EVIDENCE_CAP = 0.44
_MEDIUM_EVIDENCE_THRESHOLD = 0.45
_HIGH_EVIDENCE_THRESHOLD = 0.75
_CAUSAL_STATE_FIELDS = (
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "angle",
    "innovation",
    "uncertainty",
)
_CAUSAL_HISTORY_FIELD_NAMES = (
    "level",
    "quadrature",
    "slope",
    "acceleration",
    "amplitude",
    "angle",
    "innovation",
    "uncertainty",
)


def _same_index(left: pd.Index, right: pd.Index) -> bool:
    return left.equals(right) and left.names == right.names


def _readonly_series(values: pd.Series) -> pd.Series:
    copied = values.copy(deep=True)
    copied.to_numpy(copy=False).setflags(write=False)
    return copied


def _readonly_frame(values: pd.DataFrame) -> pd.DataFrame:
    copied = values.copy(deep=True)
    for block in copied._mgr.blocks:
        block.values.setflags(write=False)
    return copied


@dataclass(frozen=True)
class CausalStateHistory:
    """Immutable second-pass state history containing causal fields only."""

    level: pd.Series
    quadrature: pd.Series
    slope: pd.Series
    acceleration: pd.Series
    amplitude: pd.Series
    angle: pd.Series
    innovation: pd.Series
    uncertainty: pd.Series

    def __post_init__(self) -> None:
        reference = object.__getattribute__(self, "level")
        if not isinstance(reference, pd.Series):
            raise TypeError("level must be a pandas Series")
        for field_name in _CAUSAL_HISTORY_FIELD_NAMES:
            values = object.__getattribute__(self, field_name)
            if not isinstance(values, pd.Series):
                raise TypeError(f"{field_name} must be a pandas Series")
            if not _same_index(values.index, reference.index):
                raise ValueError(f"{field_name} index must align with level")
            if values.name != reference.name:
                raise ValueError(f"{field_name} name must match level")
            if values.dtype != reference.dtype:
                raise ValueError(f"{field_name} dtype must match level")
            object.__setattr__(self, field_name, _readonly_series(values))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _CAUSAL_HISTORY_FIELD_NAMES and isinstance(value, pd.Series):
            return value.copy(deep=True)
        return value


@dataclass(frozen=True)
class CycleComputationDiagnostics:
    """Detached snapshot of one cycle's two-pass causal computation."""

    cycle_id: str
    frequency: str
    center_period: float
    member_components: pd.DataFrame
    aggregation: CategoryAggregationResult
    state_history: CausalStateHistory

    def __post_init__(self) -> None:
        cycle_id = object.__getattribute__(self, "cycle_id")
        member_components = object.__getattribute__(self, "member_components")
        aggregation = object.__getattribute__(self, "aggregation")
        state_history = object.__getattribute__(self, "state_history")
        if not isinstance(cycle_id, str):
            raise TypeError("cycle_id must be str")
        if not isinstance(member_components, pd.DataFrame):
            raise TypeError("member_components must be a pandas DataFrame")
        if not isinstance(aggregation, CategoryAggregationResult):
            raise TypeError("aggregation must be a CategoryAggregationResult")
        if not isinstance(state_history, CausalStateHistory):
            raise TypeError("state_history must be a CausalStateHistory")

        aggregate = object.__getattribute__(aggregation, "aggregate")
        aligned_members = object.__getattribute__(
            aggregation,
            "aligned_members",
        )
        state_level = object.__getattribute__(state_history, "level")
        if not _same_index(member_components.index, aggregate.index):
            raise ValueError("member_components index must align with aggregation")
        if not member_components.columns.equals(aligned_members.columns) or (
            member_components.columns.names != aligned_members.columns.names
        ):
            raise ValueError("member_components columns must align with aggregation")
        if not _same_index(member_components.index, state_level.index):
            raise ValueError("member_components index must align with state_history")
        object.__setattr__(
            self,
            "member_components",
            _readonly_frame(member_components),
        )

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == "member_components" and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def _cycle_number(cycle_id: str) -> int:
    try:
        return int(cycle_id.removeprefix("C"))
    except ValueError as error:
        raise ValueError(f"invalid cycle_id: {cycle_id}") from error


def _resolved_center(cycle: CycleSpec) -> float:
    center = (
        float(cycle.initial_center)
        if cycle.initial_center is not None
        else (float(cycle.search_min) + float(cycle.search_max)) / 2.0
    )
    if not np.isfinite(center) or not (
        float(cycle.search_min) <= center <= float(cycle.search_max)
    ):
        raise ValueError(
            f"Resolved center for {cycle.cycle_id} must fall inside its search band"
        )
    return center


def _copy_panel(panel: pd.DataFrame, name: str) -> pd.DataFrame:
    if not isinstance(panel, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if panel.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    if panel.index.has_duplicates:
        raise ValueError(f"{name} index must be unique")
    return panel.copy(deep=True)


def _annual_panel(panel: pd.DataFrame) -> pd.DataFrame:
    values = _copy_panel(panel, "annual_panel")
    years: list[int] = []
    for value in values.index:
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (Integral, np.integer),
        ):
            raise ValueError("annual_panel index must contain integer years")
        years.append(int(value))
    values.index = pd.Index(years, name=values.index.name, dtype="int64")
    return values.sort_index(kind="stable")


def _monthly_panel(panel: pd.DataFrame) -> pd.DataFrame:
    values = _copy_panel(panel, "monthly_panel")
    if not isinstance(values.index, pd.DatetimeIndex):
        raise ValueError("monthly_panel index must contain month-end timestamps")
    if values.index.tz is not None:
        raise ValueError("monthly_panel index must be timezone-naive")
    normalized = values.index.to_period("M").to_timestamp("M")
    if not values.index.equals(normalized):
        raise ValueError("monthly_panel index must contain month-end timestamps")
    return values.sort_index(kind="stable")


def _as_of_dates(as_of: object) -> tuple[pd.Timestamp, ...]:
    scalar_types = (str, date, datetime, np.datetime64, pd.Timestamp)
    if isinstance(as_of, scalar_types):
        raw_dates = [as_of]
    elif isinstance(as_of, Iterable):
        raw_dates = list(as_of)
    else:
        raise TypeError("as_of must be a date or an iterable of dates")
    if not raw_dates:
        raise ValueError("as_of must contain at least one date")

    normalized_dates: list[pd.Timestamp] = []
    for raw_date in raw_dates:
        try:
            timestamp = pd.Timestamp(raw_date)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid as_of date: {raw_date}") from error
        if pd.isna(timestamp):
            raise ValueError("as_of dates cannot be missing")
        if timestamp.tzinfo is not None:
            raise ValueError("as_of dates must be timezone-naive")
        normalized_dates.append(timestamp.normalize())
    if len(normalized_dates) != len(set(normalized_dates)):
        raise ValueError("duplicate as_of dates are not supported")
    return tuple(sorted(normalized_dates))


def _latest_native_index(
    index: pd.Index,
    cutoff: int | pd.Timestamp,
) -> object | None:
    eligible = index[index <= cutoff]
    if eligible.empty:
        return None
    return eligible[-1]


def _causal_state_history(result: HarmonicStateResult) -> CausalStateHistory:
    return CausalStateHistory(
        **{
            field_name: object.__getattribute__(result, field_name)
            for field_name in _CAUSAL_HISTORY_FIELD_NAMES
        }
    )


def _state_value(result: CausalStateHistory, field: str, index: object) -> float:
    values = object.__getattribute__(result, field)
    return float(values.loc[index])


def _period_filtered_level(values: pd.Series, period: float) -> pd.Series:
    numeric = (
        pd.to_numeric(values.copy(deep=True), errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )
    finite_positions = np.flatnonzero(
        np.isfinite(numeric.to_numpy(dtype="float64"))
    )
    if finite_positions.size == 0:
        return pd.Series(
            np.nan,
            index=numeric.index,
            name=numeric.name,
            dtype="float64",
        )

    component = harmonic_state_filter(numeric, period=period).level
    component.iloc[: int(finite_positions[0])] = np.nan
    return component


def _period_filtered_panel(panel: pd.DataFrame, period: float) -> pd.DataFrame:
    return pd.concat(
        [
            _period_filtered_level(panel[column], period).rename(column)
            for column in panel.columns
        ],
        axis=1,
    )


def _native_source_availability(panel: pd.DataFrame) -> pd.DataFrame:
    numeric = (
        panel.copy(deep=True)
        .apply(pd.to_numeric, errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )
    return numeric.notna()


def _period_filtered_anchor(
    anchor: pd.Series | None,
    index: pd.Index,
    period: float,
) -> pd.Series | None:
    if anchor is None:
        return None
    if not isinstance(anchor, pd.Series):
        raise TypeError("orientation anchors must be pandas Series or None")
    if anchor.index.has_duplicates:
        raise ValueError("orientation anchor index must be unique")
    return _period_filtered_level(anchor.reindex(index), period)


def _confidence(
    *,
    effective_cycles: float,
    member_breadth: float,
    category_breadth: float,
    uncertainty: float,
) -> float:
    """Return an uncalibrated deterministic diagnostics score in ``[0, 1]``.

    Formula: 45% observed-cycle coverage (full at three cycles), 35% equal
    member/category breadth, and 20% inverse state uncertainty ``1 / (1 + u)``.
    The result is a governance score, not a calibrated probability.
    """

    cycle_score = float(np.clip(effective_cycles / 3.0, 0.0, 1.0))
    breadth_score = float(
        np.clip((member_breadth + category_breadth) / 2.0, 0.0, 1.0)
    )
    uncertainty_score = (
        1.0 / (1.0 + max(uncertainty, 0.0))
        if np.isfinite(uncertainty)
        else 0.0
    )
    score = (
        0.45 * cycle_score
        + 0.35 * breadth_score
        + 0.20 * uncertainty_score
    )
    return float(np.clip(score, 0.0, 1.0))


def _evidence_level(confidence: float) -> EvidenceLevel:
    if confidence >= _HIGH_EVIDENCE_THRESHOLD:
        return EvidenceLevel.HIGH
    if confidence >= _MEDIUM_EVIDENCE_THRESHOLD:
        return EvidenceLevel.MEDIUM
    return EvidenceLevel.LOW


def _usage_status(
    cycle: CycleSpec,
    *,
    available: bool,
    effective_cycles: float,
) -> MappingStatus:
    if not available:
        return MappingStatus.UNAVAILABLE
    if cycle.cycle_id in {"C1", "C2"} and effective_cycles < 2.0:
        return MappingStatus.CONDITIONAL
    if cycle.cycle_id == "C7":
        return MappingStatus.CONDITIONAL
    return cycle.default_usage


class SevenCycleEngine:
    """Compute deterministic governed long-form states for C1 through C7."""

    def __init__(
        self,
        cycle_specs: Sequence[CycleSpec],
        *,
        min_sign_observations: int = 3,
        sign_hysteresis: float = 0.10,
    ) -> None:
        supplied_specs = tuple(cycle_specs)
        if any(not isinstance(cycle, CycleSpec) for cycle in supplied_specs):
            raise TypeError("cycle_specs must contain CycleSpec objects")
        specifications = tuple(
            cycle.model_copy(deep=True) for cycle in supplied_specs
        )
        if len(specifications) != _CYCLE_COUNT:
            raise ValueError("cycle_specs must contain exactly seven cycles")
        cycle_numbers = [_cycle_number(cycle.cycle_id) for cycle in specifications]
        if len(set(cycle_numbers)) != _CYCLE_COUNT or sorted(cycle_numbers) != list(
            range(1, _CYCLE_COUNT + 1)
        ):
            raise ValueError("cycle_specs must contain exactly C1 through C7")
        ordered = tuple(
            sorted(specifications, key=lambda cycle: _cycle_number(cycle.cycle_id))
        )
        centers = tuple(_resolved_center(cycle) for cycle in ordered)
        if isinstance(min_sign_observations, (bool, np.bool_)) or not isinstance(
            min_sign_observations,
            (Integral, np.integer),
        ):
            raise TypeError("min_sign_observations must be a positive integer")
        if int(min_sign_observations) < 1:
            raise ValueError("min_sign_observations must be a positive integer")
        if isinstance(sign_hysteresis, (bool, np.bool_)) or not isinstance(
            sign_hysteresis,
            (Real, np.integer, np.floating),
        ):
            raise TypeError("sign_hysteresis must be between 0 and 1")
        numeric_hysteresis = float(sign_hysteresis)
        if not np.isfinite(numeric_hysteresis) or not 0.0 <= numeric_hysteresis <= 1.0:
            raise ValueError("sign_hysteresis must be between 0 and 1")
        self._cycle_specs = ordered
        self._center_periods = centers
        self._min_sign_observations = int(min_sign_observations)
        self._sign_hysteresis = numeric_hysteresis

    @property
    def cycle_specs(self) -> tuple[CycleSpec, ...]:
        """Return defensive copies of the governed cycle definitions."""

        return tuple(cycle.model_copy(deep=True) for cycle in self._cycle_specs)

    @property
    def center_periods(self) -> tuple[float, ...]:
        """Return the resolved center used for each governed cycle."""

        return self._center_periods

    def _aggregation(
        self,
        panel: pd.DataFrame,
        categories: Mapping[object, str] | pd.Series,
        orientation_anchor: pd.Series | None,
        availability_mask: pd.DataFrame | None = None,
    ) -> CategoryAggregationResult:
        return aggregate_category_balanced(
            panel,
            categories,
            min_observations=self._min_sign_observations,
            hysteresis=self._sign_hysteresis,
            orientation_anchor=orientation_anchor,
            availability_mask=availability_mask,
        )

    def _cycle_and_center(self, cycle_id: str) -> tuple[CycleSpec, float]:
        for cycle, center in zip(
            self._cycle_specs,
            self._center_periods,
            strict=True,
        ):
            if cycle.cycle_id == cycle_id:
                return cycle, center
        raise ValueError(f"unknown cycle_id: {cycle_id}")

    def _cycle_diagnostics(
        self,
        cycle: CycleSpec,
        center: float,
        panel: pd.DataFrame,
        categories: Mapping[object, str] | pd.Series,
        orientation_anchor: pd.Series | None,
    ) -> CycleComputationDiagnostics:
        member_components = _period_filtered_panel(panel, center)
        source_availability = _native_source_availability(panel)
        filtered_anchor = _period_filtered_anchor(
            orientation_anchor,
            panel.index,
            center,
        )
        aggregation = self._aggregation(
            member_components,
            categories,
            filtered_anchor,
            source_availability,
        )
        aggregate = object.__getattribute__(aggregation, "aggregate")
        state_history = _causal_state_history(
            harmonic_state_filter(aggregate, center)
        )
        return CycleComputationDiagnostics(
            cycle_id=str(cycle.cycle_id),
            frequency=cycle.frequency,
            center_period=center,
            member_components=member_components,
            aggregation=aggregation,
            state_history=state_history,
        )

    def compute_cycle_diagnostics(
        self,
        cycle_id: str,
        *,
        annual_panel: pd.DataFrame,
        monthly_panel: pd.DataFrame,
        annual_categories: Mapping[object, str] | pd.Series,
        monthly_categories: Mapping[object, str] | pd.Series,
        annual_orientation_anchor: pd.Series | None = None,
        monthly_orientation_anchor: pd.Series | None = None,
    ) -> CycleComputationDiagnostics:
        """Return a detached two-pass diagnostic snapshot for one cycle.

        Pass one filters and masks every native member at the governed center,
        then category-balances those member-period components. Pass two filters
        that composite again to estimate the rich governed cycle state history.
        """

        if not isinstance(cycle_id, str):
            raise TypeError("cycle_id must be str")
        annual_values = _annual_panel(annual_panel)
        monthly_values = _monthly_panel(monthly_panel)
        cycle, center = self._cycle_and_center(cycle_id)
        if cycle.frequency == "A":
            return self._cycle_diagnostics(
                cycle,
                center,
                annual_values,
                annual_categories,
                annual_orientation_anchor,
            )
        return self._cycle_diagnostics(
            cycle,
            center,
            monthly_values,
            monthly_categories,
            monthly_orientation_anchor,
        )

    def compute(
        self,
        *,
        annual_panel: pd.DataFrame,
        monthly_panel: pd.DataFrame,
        annual_categories: Mapping[object, str] | pd.Series,
        monthly_categories: Mapping[object, str] | pd.Series,
        as_of: object,
        annual_orientation_anchor: pd.Series | None = None,
        monthly_orientation_anchor: pd.Series | None = None,
    ) -> pd.DataFrame:
        """Compute seven rows for each unique normalized ``as_of`` date.

        Duplicate dates after midnight normalization are rejected. Annual cutoffs
        use integer year and monthly cutoffs use the corresponding month end. The
        first causal filter isolates member-period components; category balancing
        follows per cycle, and a second causal filter extracts the composite state.
        Effective-cycle counts include a finite composite row only when at least
        one native source category is available; prediction-only rows are excluded.
        """

        annual_values = _annual_panel(annual_panel)
        monthly_values = _monthly_panel(monthly_panel)
        dates = _as_of_dates(as_of)
        panels = {"A": annual_values, "M": monthly_values}
        category_maps = {
            "A": annual_categories,
            "M": monthly_categories,
        }
        orientation_anchors = {
            "A": annual_orientation_anchor,
            "M": monthly_orientation_anchor,
        }
        diagnostics = {
            cycle.cycle_id: self._cycle_diagnostics(
                cycle,
                center,
                panels[cycle.frequency],
                category_maps[cycle.frequency],
                orientation_anchors[cycle.frequency],
            )
            for cycle, center in zip(
                self._cycle_specs,
                self._center_periods,
                strict=True,
            )
        }

        rows: list[dict[str, object]] = []
        for as_of_date in dates:
            for cycle, center in zip(
                self._cycle_specs,
                self._center_periods,
                strict=True,
            ):
                cycle_diagnostics = diagnostics[cycle.cycle_id]
                aggregation = cycle_diagnostics.aggregation
                aggregate_history = object.__getattribute__(
                    aggregation,
                    "aggregate",
                )
                member_breadth_history = object.__getattribute__(
                    aggregation,
                    "member_breadth",
                )
                category_breadth_history = object.__getattribute__(
                    aggregation,
                    "category_breadth",
                )
                aligned_members = object.__getattribute__(
                    aggregation,
                    "aligned_members",
                )
                aligned_categories = object.__getattribute__(
                    aggregation,
                    "aligned_categories",
                )
                cutoff: int | pd.Timestamp = (
                    int(as_of_date.year)
                    if cycle.frequency == "A"
                    else as_of_date.to_period("M").to_timestamp("M")
                )
                native_index = _latest_native_index(aggregate_history.index, cutoff)
                observed_history = aggregate_history.loc[
                    aggregate_history.index <= cutoff
                ]
                observed_category_breadth = category_breadth_history.loc[
                    category_breadth_history.index <= cutoff
                ]
                observed_count = int(
                    (
                        np.isfinite(observed_history)
                        & observed_category_breadth.gt(0.0)
                    ).sum()
                )
                effective_cycles = float(observed_count / center)
                total_members = int(aligned_members.shape[1])
                total_categories = int(aligned_categories.shape[1])

                state_values = {
                    field: np.nan for field in _CAUSAL_STATE_FIELDS
                }
                member_breadth = 0.0
                category_breadth = 0.0
                available = False
                if native_index is not None:
                    member_breadth = float(member_breadth_history.loc[native_index])
                    category_breadth = float(
                        category_breadth_history.loc[native_index]
                    )
                    if observed_count >= _MINIMUM_STATE_OBSERVATIONS:
                        history = cycle_diagnostics.state_history
                        state_values = {
                            field: _state_value(history, field, native_index)
                            for field in _CAUSAL_STATE_FIELDS
                        }
                        available = all(
                            np.isfinite(state_values[field])
                            for field in (
                                "level",
                                "slope",
                                "acceleration",
                                "amplitude",
                                "angle",
                                "uncertainty",
                            )
                        )

                confidence = 0.0
                if available:
                    confidence = _confidence(
                        effective_cycles=effective_cycles,
                        member_breadth=member_breadth,
                        category_breadth=category_breadth,
                        uncertainty=state_values["uncertainty"],
                    )
                    if (
                        cycle.cycle_id in {"C1", "C2"}
                        and effective_cycles < 2.0
                    ):
                        confidence = min(confidence, _LOW_EVIDENCE_CAP)
                phase = phase_from_level_slope(
                    state_values["level"],
                    state_values["slope"],
                )
                usage_status = _usage_status(
                    cycle,
                    available=available,
                    effective_cycles=effective_cycles,
                )
                rows.append(
                    {
                        "cycle_id": str(cycle.cycle_id),
                        "as_of": as_of_date,
                        "frequency": cycle.frequency,
                        "angle": state_values["angle"],
                        "phase": phase.value if phase is not None else None,
                        "level": state_values["level"],
                        "slope": state_values["slope"],
                        "acceleration": state_values["acceleration"],
                        "amplitude": state_values["amplitude"],
                        "innovation": state_values["innovation"],
                        "uncertainty": state_values["uncertainty"],
                        "center_period": center,
                        "bandwidth": float(cycle.search_max - cycle.search_min),
                        "confidence": confidence,
                        "evidence_level": _evidence_level(confidence).value,
                        "usage_status": usage_status.value,
                        "effective_cycles": effective_cycles,
                        "observed_observations": observed_count,
                        "member_breadth": member_breadth,
                        "category_breadth": category_breadth,
                        "total_members": total_members,
                        "total_categories": total_categories,
                    }
                )
        output = pd.DataFrame(rows)
        output["as_of"] = pd.to_datetime(output["as_of"])
        return output.reset_index(drop=True)


def compute_seven_cycle_states(
    *,
    cycle_specs: Sequence[CycleSpec],
    annual_panel: pd.DataFrame,
    monthly_panel: pd.DataFrame,
    annual_categories: Mapping[object, str] | pd.Series,
    monthly_categories: Mapping[object, str] | pd.Series,
    as_of: object,
    annual_orientation_anchor: pd.Series | None = None,
    monthly_orientation_anchor: pd.Series | None = None,
    min_sign_observations: int = 3,
    sign_hysteresis: float = 0.10,
) -> pd.DataFrame:
    """Convenience wrapper around :class:`SevenCycleEngine`."""

    return SevenCycleEngine(
        cycle_specs,
        min_sign_observations=min_sign_observations,
        sign_hysteresis=sign_hysteresis,
    ).compute(
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=as_of,
        annual_orientation_anchor=annual_orientation_anchor,
        monthly_orientation_anchor=monthly_orientation_anchor,
    )
