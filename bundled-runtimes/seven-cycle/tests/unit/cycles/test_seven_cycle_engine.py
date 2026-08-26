from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles import (
    CategoryAggregationResult,
    CyclePhase,
    SevenCycleEngine,
    aggregate_category_balanced,
    compute_seven_cycle_states,
    harmonic_state_filter,
    phase_from_level_slope,
)
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.registry.models import CycleSpec


REGISTRY_DIR = Path(__file__).resolve().parents[3] / "config" / "seven_cycle"
EXPECTED_CYCLE_IDS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
EXPECTED_CENTERS = [50.0, 16.6666667, 8.3333333, 42.0, 20.0, 12.0, 6.0]
EXPECTED_BANDWIDTHS = [16.5, 15.0, 8.0, 24.0, 18.0, 1.0, 6.0]
REQUIRED_COLUMNS = {
    "cycle_id",
    "as_of",
    "angle",
    "phase",
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "innovation",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
    "evidence_level",
    "usage_status",
}
CAUSAL_HISTORY_FIELDS = (
    "level",
    "quadrature",
    "slope",
    "acceleration",
    "amplitude",
    "angle",
    "innovation",
    "uncertainty",
)


@pytest.fixture(scope="module")
def cycle_specs() -> list[CycleSpec]:
    return load_registry_bundle(REGISTRY_DIR).cycles


@pytest.fixture()
def synthetic_panels() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
]:
    annual_years = pd.Index(range(1890, 2026), name="year")
    annual_time = np.arange(len(annual_years), dtype="float64")
    annual_base = (
        np.sin(2.0 * np.pi * annual_time / 9.0)
        + 0.45 * np.sin(2.0 * np.pi * annual_time / 14.0)
        + 0.20 * np.cos(2.0 * np.pi * annual_time / 45.0)
    )
    annual_panel = pd.DataFrame(
        {
            "annual_alpha_1": annual_base,
            "annual_alpha_2": 0.85 * annual_base
            + 0.15 * np.cos(2.0 * np.pi * annual_time / 7.0),
            "annual_alpha_inverse": -1.10 * annual_base,
            "annual_beta": np.cos(2.0 * np.pi * annual_time / 16.0)
            + 0.25 * annual_base,
            "annual_gamma": np.sin(2.0 * np.pi * annual_time / 11.0 + 0.6),
        },
        index=annual_years,
        dtype="float64",
    )
    annual_panel.loc[annual_years[8::17], "annual_alpha_2"] = np.nan
    annual_panel.loc[annual_years[5::19], "annual_beta"] = np.nan
    annual_categories = pd.Series(
        {
            "annual_alpha_1": "alpha",
            "annual_alpha_2": "alpha",
            "annual_alpha_inverse": "alpha",
            "annual_beta": "beta",
            "annual_gamma": "gamma",
        },
        name="category",
    )

    monthly_index = pd.date_range(
        "1995-01-31",
        "2025-12-31",
        freq="ME",
        name="month",
    )
    monthly_time = np.arange(len(monthly_index), dtype="float64")
    monthly_base = (
        np.sin(2.0 * np.pi * monthly_time / 42.0)
        + 0.55 * np.sin(2.0 * np.pi * monthly_time / 21.0)
        + 0.25 * np.cos(2.0 * np.pi * monthly_time / 6.0)
    )
    monthly_panel = pd.DataFrame(
        {
            "monthly_delta_1": monthly_base,
            "monthly_delta_2": 0.90 * monthly_base
            + 0.10 * np.cos(2.0 * np.pi * monthly_time / 12.0),
            "monthly_delta_inverse": -1.05 * monthly_base,
            "monthly_epsilon": np.cos(2.0 * np.pi * monthly_time / 30.0)
            + 0.20 * monthly_base,
            "monthly_zeta_1": np.sin(2.0 * np.pi * monthly_time / 15.0 + 0.4),
            "monthly_zeta_inverse": -np.sin(
                2.0 * np.pi * monthly_time / 15.0 + 0.4
            ),
        },
        index=monthly_index,
        dtype="float64",
    )
    monthly_panel.loc[monthly_index[9::23], "monthly_delta_2"] = np.nan
    monthly_panel.loc[monthly_index[4::29], "monthly_epsilon"] = np.nan
    monthly_panel.loc[monthly_index[7::31], "monthly_zeta_inverse"] = np.nan
    monthly_categories = pd.Series(
        {
            "monthly_delta_1": "delta",
            "monthly_delta_2": "delta",
            "monthly_delta_inverse": "delta",
            "monthly_epsilon": "epsilon",
            "monthly_zeta_1": "zeta",
            "monthly_zeta_inverse": "zeta",
        },
        name="category",
    )
    return annual_panel, monthly_panel, annual_categories, monthly_categories


@pytest.fixture()
def period_sensitive_monthly_panel() -> tuple[pd.DataFrame, pd.Series]:
    monthly_index = pd.date_range(
        "1995-01-31",
        "2025-12-31",
        freq="ME",
        name="month",
    )
    time = np.arange(len(monthly_index), dtype="float64")
    long_wave = np.sin(2.0 * np.pi * time / 42.0)
    short_wave = np.sin(2.0 * np.pi * time / 6.0 + 0.2)
    c5_wave = np.sin(2.0 * np.pi * time / 21.0 + 0.4)
    alternate_c5_wave = np.sin(2.0 * np.pi * time / 29.0 - 0.3)
    panel = pd.DataFrame(
        {
            "long_short_direct_1": long_wave + short_wave,
            "long_short_direct_2": 0.9 * long_wave + 0.8 * short_wave,
            "long_short_mixed": 1.2 * long_wave - 1.4 * short_wave,
            "mid_direct_1": c5_wave + alternate_c5_wave,
            "mid_direct_2": 0.8 * c5_wave + 0.9 * alternate_c5_wave,
            "mid_mixed": -1.5 * c5_wave + 1.4 * alternate_c5_wave,
            "other": np.cos(2.0 * np.pi * time / 16.0),
        },
        index=monthly_index,
        dtype="float64",
    )
    categories = pd.Series(
        {
            "long_short_direct_1": "long_short",
            "long_short_direct_2": "long_short",
            "long_short_mixed": "long_short",
            "mid_direct_1": "mid_band",
            "mid_direct_2": "mid_band",
            "mid_mixed": "mid_band",
            "other": "other",
        },
        name="category",
    )
    return panel, categories


def _compute(
    engine: SevenCycleEngine,
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
    as_of: object,
) -> pd.DataFrame:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    return engine.compute(
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=as_of,
    )


def _period_filtered_level(values: pd.Series, period: float) -> pd.Series:
    numeric = (
        pd.to_numeric(values, errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )
    finite_positions = np.flatnonzero(np.isfinite(numeric.to_numpy(dtype="float64")))
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


def _native_availability(panel: pd.DataFrame) -> pd.DataFrame:
    numeric = (
        panel.copy(deep=True)
        .apply(pd.to_numeric, errors="coerce")
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
    )
    return numeric.notna()


def _assert_aggregation_exact(actual: object, expected: object) -> None:
    pd.testing.assert_series_equal(
        actual.aggregate,
        expected.aggregate,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        actual.aligned_members,
        expected.aligned_members,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        actual.member_signs,
        expected.member_signs,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        actual.aligned_categories,
        expected.aligned_categories,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        actual.category_signs,
        expected.category_signs,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        actual.orientation_sign,
        expected.orientation_sign,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        actual.member_breadth,
        expected.member_breadth,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        actual.category_breadth,
        expected.category_breadth,
        check_exact=True,
    )


def test_real_registry_has_exact_order_and_resolved_centers(
    cycle_specs: list[CycleSpec],
) -> None:
    engine = SevenCycleEngine(cycle_specs)

    assert [cycle.cycle_id for cycle in engine.cycle_specs] == EXPECTED_CYCLE_IDS
    assert list(engine.center_periods) == EXPECTED_CENTERS


def test_category_balanced_aggregation_gives_each_category_equal_weight() -> None:
    index = pd.RangeIndex(32, name="observation")
    time = np.arange(len(index), dtype="float64")
    alpha = np.sin(2.0 * np.pi * time / 9.0) + 0.04 * time
    beta = np.cos(2.0 * np.pi * time / 13.0) - 0.02 * time
    panel = pd.DataFrame(
        {
            "alpha_1": alpha,
            "alpha_2": 0.8 * alpha + 0.1,
            "alpha_3": 1.2 * alpha - 0.1,
            "beta_1": beta,
        },
        index=index,
    )
    categories = {
        "alpha_1": "alpha",
        "alpha_2": "alpha",
        "alpha_3": "alpha",
        "beta_1": "beta",
    }

    result = aggregate_category_balanced(
        panel,
        categories,
        min_observations=3,
    )

    usable = result.aligned_categories.dropna(how="any")
    assert not usable.empty
    selected_index = usable.index[-1]
    alpha_value = float(usable.loc[selected_index, "alpha"])
    beta_value = float(usable.loc[selected_index, "beta"])
    equal_category_mean = (alpha_value + beta_value) / 2.0
    member_count_weighted_mean = (3.0 * alpha_value + beta_value) / 4.0

    assert result.aggregate.loc[selected_index] == pytest.approx(equal_category_mean)
    assert not np.isclose(
        result.aggregate.loc[selected_index],
        member_count_weighted_mean,
    )


def test_explicit_availability_mask_changes_only_breadth_diagnostics() -> None:
    index = pd.RangeIndex(24, name="observation")
    time = np.arange(len(index), dtype="float64")
    panel = pd.DataFrame(
        {
            "alpha_1": np.sin(2.0 * np.pi * time / 8.0),
            "alpha_2": np.cos(2.0 * np.pi * time / 11.0),
            "beta_1": np.sin(2.0 * np.pi * time / 13.0 + 0.4),
        },
        index=index,
    )
    categories = {
        "alpha_1": "alpha",
        "alpha_2": "alpha",
        "beta_1": "beta",
    }
    availability = pd.DataFrame(True, index=index, columns=panel.columns)
    availability.loc[index[-1], ["alpha_1", "alpha_2"]] = False
    availability_before = availability.copy(deep=True)

    default = aggregate_category_balanced(panel, categories)
    masked = aggregate_category_balanced(
        panel,
        categories,
        availability_mask=availability,
    )

    pd.testing.assert_series_equal(default.aggregate, masked.aggregate, check_exact=True)
    pd.testing.assert_frame_equal(
        default.aligned_members,
        masked.aligned_members,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        default.member_signs,
        masked.member_signs,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        default.aligned_categories,
        masked.aligned_categories,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        default.category_signs,
        masked.category_signs,
        check_exact=True,
    )
    assert default.member_breadth.iloc[-1] == 1.0
    assert default.category_breadth.iloc[-1] == 1.0
    assert masked.member_breadth.iloc[-1] == pytest.approx(1.0 / 3.0)
    assert masked.category_breadth.iloc[-1] == pytest.approx(0.5)
    pd.testing.assert_frame_equal(availability, availability_before, check_exact=True)


def test_availability_mask_is_strictly_validated_and_missing_means_unavailable() -> None:
    panel = pd.DataFrame(
        {"first": [1.0, 2.0, 3.0], "second": [3.0, 2.0, 1.0]},
        index=pd.Index([2020, 2021, 2022], name="year"),
    )
    categories = {"first": "alpha", "second": "beta"}
    valid = pd.DataFrame(True, index=panel.index, columns=panel.columns, dtype="boolean")
    valid.loc[2022, "first"] = pd.NA
    result = aggregate_category_balanced(
        panel,
        categories,
        availability_mask=valid,
    )

    assert result.member_breadth.loc[2022] == 0.5
    assert result.category_breadth.loc[2022] == 0.5
    with pytest.raises(TypeError, match="availability_mask.*DataFrame"):
        aggregate_category_balanced(panel, categories, availability_mask=True)
    with pytest.raises(ValueError, match="index labels and order"):
        aggregate_category_balanced(
            panel,
            categories,
            availability_mask=valid.iloc[::-1],
        )
    with pytest.raises(ValueError, match="column labels and order"):
        aggregate_category_balanced(
            panel,
            categories,
            availability_mask=valid.loc[:, ["second", "first"]],
        )
    duplicate_index = valid.copy(deep=True)
    duplicate_index.index = pd.Index([2020, 2020, 2022], name="year")
    with pytest.raises(ValueError, match="axes must be unique"):
        aggregate_category_balanced(
            panel,
            categories,
            availability_mask=duplicate_index,
        )
    invalid_values = valid.astype("object")
    invalid_values.loc[2022, "first"] = 1
    with pytest.raises(ValueError, match="boolean or missing"):
        aggregate_category_balanced(
            panel,
            categories,
            availability_mask=invalid_values,
        )


def test_category_aggregation_result_is_deeply_immutable_and_copy_on_access() -> None:
    index = pd.RangeIndex(24, name="observation")
    time = np.arange(len(index), dtype="float64")
    base = aggregate_category_balanced(
        pd.DataFrame(
            {
                "alpha": np.sin(2.0 * np.pi * time / 8.0),
                "beta": np.cos(2.0 * np.pi * time / 11.0),
            },
            index=index,
        ),
        {"alpha": "first", "beta": "second"},
    )
    source_fields = {
        field.name: getattr(base, field.name)
        for field in fields(CategoryAggregationResult)
    }
    expected = {
        name: value.copy(deep=True) for name, value in source_fields.items()
    }
    result = CategoryAggregationResult(**source_fields)

    for value in source_fields.values():
        if isinstance(value, pd.DataFrame):
            value.iloc[0, 0] = 999.0
        else:
            value.iloc[0] = 999.0

    for name, expected_value in expected.items():
        actual = getattr(result, name)
        if isinstance(expected_value, pd.DataFrame):
            pd.testing.assert_frame_equal(actual, expected_value, check_exact=True)
            actual.iloc[0, 0] = -999.0
            pd.testing.assert_frame_equal(
                getattr(result, name),
                expected_value,
                check_exact=True,
            )
        else:
            pd.testing.assert_series_equal(actual, expected_value, check_exact=True)
            actual.iloc[0] = -999.0
            pd.testing.assert_series_equal(
                getattr(result, name),
                expected_value,
                check_exact=True,
            )
        internal = object.__getattribute__(result, name)
        assert not internal.to_numpy(copy=False).flags.writeable


def test_category_aggregation_result_validates_paired_alignment() -> None:
    index = pd.RangeIndex(16, name="observation")
    base = aggregate_category_balanced(
        pd.DataFrame(
            {"alpha": np.arange(16.0), "beta": np.arange(16.0)[::-1]},
            index=index,
        ),
        {"alpha": "first", "beta": "second"},
    )
    source_fields = {
        field.name: getattr(base, field.name)
        for field in fields(CategoryAggregationResult)
    }

    misaligned_members = dict(source_fields)
    misaligned_members["member_signs"] = source_fields["member_signs"].loc[
        :,
        ["beta", "alpha"],
    ]
    with pytest.raises(ValueError, match="member_signs.*aligned_members"):
        CategoryAggregationResult(**misaligned_members)

    misaligned_categories = dict(source_fields)
    misaligned_categories["category_signs"] = source_fields[
        "category_signs"
    ].iloc[::-1]
    with pytest.raises(ValueError, match="category_signs.*aligned_categories"):
        CategoryAggregationResult(**misaligned_categories)


def test_sign_alignment_is_past_only_and_future_append_invariant() -> None:
    history_index = pd.RangeIndex(36, name="observation")
    time = np.arange(len(history_index), dtype="float64")
    reference = np.sin(2.0 * np.pi * time / 10.0) + 0.03 * time
    history = pd.DataFrame(
        {
            "direct_1": reference,
            "direct_2": 0.9 * reference + 0.05,
            "inverse": -1.1 * reference,
            "other": np.cos(2.0 * np.pi * time / 14.0),
        },
        index=history_index,
    )
    categories = {
        "direct_1": "first",
        "direct_2": "first",
        "inverse": "first",
        "other": "second",
    }
    history_result = aggregate_category_balanced(
        history,
        categories,
        min_observations=4,
    )

    future_index = pd.RangeIndex(36, 48, name="observation")
    future_time = np.arange(len(future_index), dtype="float64")
    future = pd.DataFrame(
        {
            "direct_1": -1000.0 - future_time,
            "direct_2": 1200.0 + future_time,
            "inverse": 1500.0 + 10.0 * future_time,
            "other": -2000.0 + future_time,
        },
        index=future_index,
    )
    appended_result = aggregate_category_balanced(
        pd.concat([history, future]),
        categories,
        min_observations=4,
    )

    assert history_result.member_signs.loc[history_index[-1], "inverse"] == -1.0
    pd.testing.assert_series_equal(
        history_result.aggregate,
        appended_result.aggregate.loc[history_index],
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        history_result.member_signs,
        appended_result.member_signs.loc[history_index],
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        history_result.category_signs,
        appended_result.category_signs.loc[history_index],
        check_exact=True,
    )


def test_engine_cycle_aggregation_matches_independent_period_filtered_members(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    engine = SevenCycleEngine(cycle_specs)
    c5_center = engine.center_periods[4]
    orientation_anchor = monthly_panel["monthly_delta_1"].rename("anchor")
    expected_components = _period_filtered_panel(monthly_panel, c5_center)
    expected_anchor = _period_filtered_level(orientation_anchor, c5_center)
    expected_aggregation = aggregate_category_balanced(
        expected_components,
        monthly_categories,
        min_observations=3,
        hysteresis=0.10,
        orientation_anchor=expected_anchor,
        availability_mask=_native_availability(monthly_panel),
    )

    diagnostics = engine.compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        monthly_orientation_anchor=orientation_anchor,
    )

    pd.testing.assert_frame_equal(
        diagnostics.member_components,
        expected_components,
        check_exact=True,
    )
    _assert_aggregation_exact(diagnostics.aggregation, expected_aggregation)


def test_cycle_diagnostics_exposes_only_causal_immutable_state_history(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    diagnostics = SevenCycleEngine(cycle_specs).compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
    )
    expected_members = diagnostics.member_components
    expected_aggregate = diagnostics.aggregation.aggregate
    expected_member_signs = diagnostics.aggregation.member_signs
    expected_state = {
        field_name: getattr(diagnostics.state_history, field_name)
        for field_name in CAUSAL_HISTORY_FIELDS
    }

    assert [field.name for field in fields(type(diagnostics.state_history))] == list(
        CAUSAL_HISTORY_FIELDS
    )
    assert not hasattr(diagnostics.state_history, "smoothed_level")

    monthly_panel.iloc[:, :] = 999.0
    returned_members = diagnostics.member_components
    returned_members.iloc[0, 0] = -999.0
    returned_aggregate = diagnostics.aggregation.aggregate
    returned_aggregate.iloc[-1] = -999.0
    returned_signs = diagnostics.aggregation.member_signs
    returned_signs.iloc[-1, 0] = -999.0
    for field_name in CAUSAL_HISTORY_FIELDS:
        returned_state = getattr(diagnostics.state_history, field_name)
        returned_state.iloc[-1] = -999.0

    pd.testing.assert_frame_equal(
        diagnostics.member_components,
        expected_members,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        diagnostics.aggregation.aggregate,
        expected_aggregate,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        diagnostics.aggregation.member_signs,
        expected_member_signs,
        check_exact=True,
    )
    for field_name, expected_series in expected_state.items():
        pd.testing.assert_series_equal(
            getattr(diagnostics.state_history, field_name),
            expected_series,
            check_exact=True,
        )

    internal_members = object.__getattribute__(diagnostics, "member_components")
    internal_aggregate = object.__getattribute__(
        diagnostics.aggregation,
        "aggregate",
    )
    internal_state = object.__getattribute__(diagnostics.state_history, "level")
    assert not internal_members.to_numpy(copy=False).flags.writeable
    assert not internal_aggregate.to_numpy(copy=False).flags.writeable
    assert not internal_state.to_numpy(copy=False).flags.writeable


def test_different_cycle_periods_produce_distinct_member_signs_and_composites(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
    period_sensitive_monthly_panel: tuple[pd.DataFrame, pd.Series],
) -> None:
    annual_panel, _, annual_categories, _ = synthetic_panels
    monthly_panel, monthly_categories = period_sensitive_monthly_panel
    engine = SevenCycleEngine(cycle_specs)
    arguments = {
        "annual_panel": annual_panel,
        "monthly_panel": monthly_panel,
        "annual_categories": annual_categories,
        "monthly_categories": monthly_categories,
    }

    c4 = engine.compute_cycle_diagnostics("C4", **arguments)
    c7 = engine.compute_cycle_diagnostics("C7", **arguments)

    assert (
        c4.aggregation.member_signs.iloc[-1]["long_short_mixed"]
        != c7.aggregation.member_signs.iloc[-1]["long_short_mixed"]
    )
    assert not c4.member_components.equals(c7.member_components)
    assert not c4.aggregation.aggregate.equals(c7.aggregation.aggregate)


def test_engine_returns_exactly_seven_rows_per_as_of_with_governed_fields(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    engine = SevenCycleEngine(cycle_specs)
    requested_as_of = [pd.Timestamp("2024-10-07"), pd.Timestamp("2018-06-15")]

    states = _compute(engine, synthetic_panels, requested_as_of)

    assert REQUIRED_COLUMNS <= set(states.columns)
    assert states.groupby("as_of", sort=False).size().tolist() == [7, 7]
    assert states["as_of"].tolist() == sorted(states["as_of"].tolist())
    assert states.groupby("as_of", sort=False)["cycle_id"].agg(list).tolist() == [
        EXPECTED_CYCLE_IDS,
        EXPECTED_CYCLE_IDS,
    ]
    assert states.groupby("as_of", sort=False)["center_period"].agg(list).tolist() == [
        EXPECTED_CENTERS,
        EXPECTED_CENTERS,
    ]
    assert states.groupby("as_of", sort=False)["bandwidth"].agg(list).tolist() == [
        EXPECTED_BANDWIDTHS,
        EXPECTED_BANDWIDTHS,
    ]
    assert pd.api.types.is_datetime64_ns_dtype(states["as_of"].dtype)
    assert states["cycle_id"].map(type).eq(str).all()
    assert states["confidence"].between(0.0, 1.0).all()
    assert set(states["evidence_level"]) <= {"high", "medium", "low"}
    assert set(states["usage_status"]) <= {
        "formal",
        "conditional",
        "retrospective_only",
        "unavailable",
    }
    finite_angles = states["angle"].dropna()
    assert finite_angles.between(0.0, 360.0, inclusive="left").all()


@pytest.mark.parametrize(
    ("level", "slope", "expected"),
    [
        (1.0, 1.0, CyclePhase.EXPANSION),
        (1.0, -1.0, CyclePhase.DOWNTURN),
        (-1.0, -1.0, CyclePhase.CONTRACTION),
        (-1.0, 1.0, CyclePhase.RECOVERY),
        (0.0, 0.0, CyclePhase.EXPANSION),
    ],
)
def test_phase_is_derived_from_level_slope_quadrants(
    level: float,
    slope: float,
    expected: CyclePhase,
) -> None:
    assert phase_from_level_slope(level, slope) is expected


@pytest.mark.parametrize(
    ("level", "slope"),
    [
        (np.nan, 1.0),
        (1.0, np.nan),
        (np.inf, 1.0),
        (1.0, -np.inf),
    ],
)
def test_phase_returns_none_for_nonfinite_state(level: float, slope: float) -> None:
    assert phase_from_level_slope(level, slope) is None


@pytest.mark.parametrize(
    ("level", "slope"),
    [
        (True, 1.0),
        (np.bool_(False), 1.0),
        ("1.0", 1.0),
        (1.0, "-1.0"),
    ],
)
def test_phase_rejects_booleans_and_non_real_coercible_values(
    level: object,
    slope: object,
) -> None:
    with pytest.raises(TypeError, match="real number"):
        phase_from_level_slope(level, slope)


def test_engine_phase_uses_level_and_slope_while_angle_stays_numeric(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    states = _compute(
        SevenCycleEngine(cycle_specs),
        synthetic_panels,
        pd.Timestamp("2024-10-07"),
    )
    available = states.dropna(subset=["level", "slope", "angle"])

    assert not available.empty
    expected_phases = available.apply(
        lambda row: phase_from_level_slope(row["level"], row["slope"]).value,
        axis=1,
    )
    assert available["phase"].tolist() == expected_phases.tolist()
    assert pd.api.types.is_float_dtype(available["angle"].dtype)
    assert set(available["phase"]) <= {phase.value for phase in CyclePhase}


def test_short_history_caps_c1_c2_and_downgrades_c2_usage(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    short_annual = annual_panel.loc[annual_panel.index >= 2005]
    states = SevenCycleEngine(cycle_specs).compute(
        annual_panel=short_annual,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=pd.Timestamp("2024-10-07"),
    ).set_index("cycle_id")

    for cycle_id in ("C1", "C2"):
        assert states.loc[cycle_id, "effective_cycles"] < 2.0
        assert states.loc[cycle_id, "confidence"] < 0.45
        assert states.loc[cycle_id, "evidence_level"] == "low"
        assert states.loc[cycle_id, "usage_status"] == "conditional"
    assert states.loc["C3", "usage_status"] == "unavailable"
    assert states.loc["C7", "usage_status"] == "conditional"


def test_unavailable_cycle_still_emits_governed_row(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    unavailable_monthly = monthly_panel.copy(deep=True)
    unavailable_monthly.loc[:, :] = np.nan
    engine = SevenCycleEngine(cycle_specs)
    diagnostics = engine.compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel,
        monthly_panel=unavailable_monthly,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
    )
    states = engine.compute(
        annual_panel=annual_panel,
        monthly_panel=unavailable_monthly,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=pd.Timestamp("2024-10-07"),
    ).set_index("cycle_id")

    assert diagnostics.member_components.isna().all().all()
    required_nan_fields = [
        "angle",
        "level",
        "slope",
        "acceleration",
        "amplitude",
        "innovation",
        "uncertainty",
    ]
    for cycle_id in ("C4", "C5", "C6", "C7"):
        row = states.loc[cycle_id]
        assert row[required_nan_fields].isna().all()
        assert row["phase"] is None
        assert row["confidence"] == 0.0
        assert row["evidence_level"] == "low"
        assert row["usage_status"] == "unavailable"


def test_post_start_native_gap_keeps_prediction_but_lowers_breadth_and_confidence(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    target_month = pd.Timestamp("2024-10-31")
    fully_observed = monthly_panel.copy(deep=True)
    fully_observed.loc[target_month] = fully_observed.loc[target_month].fillna(0.0)
    missing_at_target = fully_observed.copy(deep=True)
    missing_at_target.loc[target_month, :] = np.nan
    engine = SevenCycleEngine(cycle_specs)
    common_arguments = {
        "annual_panel": annual_panel,
        "annual_categories": annual_categories,
        "monthly_categories": monthly_categories,
        "as_of": target_month,
    }

    full_states = engine.compute(
        monthly_panel=fully_observed,
        **common_arguments,
    ).set_index("cycle_id")
    missing_states = engine.compute(
        monthly_panel=missing_at_target,
        **common_arguments,
    ).set_index("cycle_id")
    diagnostics = engine.compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel,
        monthly_panel=missing_at_target,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
    )
    full_c5 = full_states.loc["C5"]
    missing_c5 = missing_states.loc["C5"]

    assert diagnostics.member_components.loc[target_month].notna().all()
    assert diagnostics.aggregation.member_breadth.loc[target_month] == 0.0
    assert diagnostics.aggregation.category_breadth.loc[target_month] == 0.0
    assert missing_c5[["level", "slope", "angle", "uncertainty"]].notna().all()
    assert full_c5["member_breadth"] == 1.0
    assert full_c5["category_breadth"] == 1.0
    assert missing_c5["member_breadth"] == 0.0
    assert missing_c5["category_breadth"] == 0.0
    assert missing_c5["confidence"] < full_c5["confidence"]
    assert (
        missing_c5["observed_observations"] + 1
        == full_c5["observed_observations"]
    )
    assert missing_c5["effective_cycles"] == pytest.approx(
        full_c5["effective_cycles"] - 1.0 / full_c5["center_period"]
    )

    adversarial_future = missing_at_target.copy(deep=True)
    future_mask = adversarial_future.index > target_month
    future_count = int(future_mask.sum())
    future_values = np.arange(1, future_count + 1, dtype="float64")[:, None]
    column_scales = np.arange(
        1,
        adversarial_future.shape[1] + 1,
        dtype="float64",
    )[None, :]
    adversarial_future.loc[future_mask, :] = 1000.0 * future_values * column_scales
    adversarial_states = engine.compute(
        monthly_panel=adversarial_future,
        **common_arguments,
    ).set_index("cycle_id")

    pd.testing.assert_frame_equal(
        missing_states,
        adversarial_states,
        check_exact=True,
    )


def test_engine_is_cutoff_equivalent_when_future_rows_are_removed(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    cutoff = pd.Timestamp("2018-06-15")
    engine = SevenCycleEngine(cycle_specs)
    full_result = engine.compute(
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=cutoff,
    )
    truncated_result = engine.compute(
        annual_panel=annual_panel.loc[annual_panel.index <= cutoff.year],
        monthly_panel=monthly_panel.loc[
            monthly_panel.index <= cutoff.to_period("M").to_timestamp("M")
        ],
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        as_of=cutoff,
    )
    full_diagnostics = engine.compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel,
        monthly_panel=monthly_panel,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
    )
    truncated_monthly = monthly_panel.loc[
        monthly_panel.index <= cutoff.to_period("M").to_timestamp("M")
    ]
    truncated_diagnostics = engine.compute_cycle_diagnostics(
        "C5",
        annual_panel=annual_panel.loc[annual_panel.index <= cutoff.year],
        monthly_panel=truncated_monthly,
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
    )

    pd.testing.assert_frame_equal(full_result, truncated_result, check_exact=True)
    pd.testing.assert_frame_equal(
        truncated_diagnostics.member_components,
        full_diagnostics.member_components.loc[truncated_monthly.index],
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        truncated_diagnostics.aggregation.aggregate,
        full_diagnostics.aggregation.aggregate.loc[truncated_monthly.index],
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        truncated_diagnostics.aggregation.member_signs,
        full_diagnostics.aggregation.member_signs.loc[truncated_monthly.index],
        check_exact=True,
    )
    for field_name in CAUSAL_HISTORY_FIELDS:
        pd.testing.assert_series_equal(
            getattr(truncated_diagnostics.state_history, field_name),
            getattr(full_diagnostics.state_history, field_name).loc[
                truncated_monthly.index
            ],
            check_exact=True,
        )
    assert not hasattr(full_diagnostics.state_history, "smoothed_level")


def test_repeatability_public_function_and_inputs_are_not_mutated(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    annual_before = annual_panel.copy(deep=True)
    monthly_before = monthly_panel.copy(deep=True)
    annual_categories_before = annual_categories.copy(deep=True)
    monthly_categories_before = monthly_categories.copy(deep=True)
    arguments = {
        "cycle_specs": cycle_specs,
        "annual_panel": annual_panel,
        "monthly_panel": monthly_panel,
        "annual_categories": annual_categories,
        "monthly_categories": monthly_categories,
        "as_of": [pd.Timestamp("2018-06-15"), pd.Timestamp("2024-10-07")],
    }

    first = compute_seven_cycle_states(**arguments)
    second = compute_seven_cycle_states(**arguments)

    pd.testing.assert_frame_equal(first, second, check_exact=True)
    pd.testing.assert_frame_equal(annual_panel, annual_before, check_exact=True)
    pd.testing.assert_frame_equal(monthly_panel, monthly_before, check_exact=True)
    pd.testing.assert_series_equal(
        annual_categories,
        annual_categories_before,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        monthly_categories,
        monthly_categories_before,
        check_exact=True,
    )


def test_duplicate_as_of_dates_are_rejected_after_normalization(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    engine = SevenCycleEngine(cycle_specs)

    with pytest.raises(ValueError, match="duplicate as_of"):
        _compute(
            engine,
            synthetic_panels,
            [pd.Timestamp("2024-10-07"), pd.Timestamp("2024-10-07 18:00")],
        )


@pytest.mark.parametrize("cycle_id", [5, True, np.int64(5), np.bool_(False)])
def test_cycle_diagnostics_requires_string_cycle_id(
    cycle_id: object,
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )

    with pytest.raises(TypeError, match="cycle_id.*str"):
        SevenCycleEngine(cycle_specs).compute_cycle_diagnostics(
            cycle_id,
            annual_panel=annual_panel,
            monthly_panel=monthly_panel,
            annual_categories=annual_categories,
            monthly_categories=monthly_categories,
        )


def test_invalid_or_missing_category_mappings_are_rejected() -> None:
    panel = pd.DataFrame(
        {"first": [1.0, 2.0, 3.0], "second": [3.0, 2.0, 1.0]}
    )

    with pytest.raises(ValueError, match="missing categories"):
        aggregate_category_balanced(panel, {"first": "alpha"})
    with pytest.raises(ValueError, match="blank category"):
        aggregate_category_balanced(
            panel,
            {"first": "alpha", "second": "  "},
        )


def test_engine_rejects_invalid_native_panel_indexes(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
) -> None:
    annual_panel, monthly_panel, annual_categories, monthly_categories = (
        synthetic_panels
    )
    invalid_annual = annual_panel.copy(deep=True)
    invalid_annual.index = pd.date_range(
        "1890-12-31",
        periods=len(invalid_annual),
        freq="YE",
    )
    invalid_monthly = monthly_panel.copy(deep=True)
    invalid_monthly.index = invalid_monthly.index - pd.Timedelta(days=1)
    engine = SevenCycleEngine(cycle_specs)

    with pytest.raises(ValueError, match="integer years"):
        engine.compute(
            annual_panel=invalid_annual,
            monthly_panel=monthly_panel,
            annual_categories=annual_categories,
            monthly_categories=monthly_categories,
            as_of=pd.Timestamp("2024-10-07"),
        )
    with pytest.raises(ValueError, match="month-end"):
        engine.compute(
            annual_panel=annual_panel,
            monthly_panel=invalid_monthly,
            annual_categories=annual_categories,
            monthly_categories=monthly_categories,
            as_of=pd.Timestamp("2024-10-07"),
        )


def test_changed_cycle_spec_center_drives_filter_without_period_constants(
    cycle_specs: list[CycleSpec],
    synthetic_panels: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
    period_sensitive_monthly_panel: tuple[pd.DataFrame, pd.Series],
) -> None:
    annual_panel, _, annual_categories, _ = synthetic_panels
    monthly_panel, monthly_categories = period_sensitive_monthly_panel
    changed_specs = [
        cycle.with_initial_center(29.0)
        if cycle.cycle_id == "C5"
        else cycle
        for cycle in cycle_specs
    ]
    original_engine = SevenCycleEngine(cycle_specs)
    changed_engine = SevenCycleEngine(changed_specs)
    arguments = {
        "annual_panel": annual_panel,
        "monthly_panel": monthly_panel,
        "annual_categories": annual_categories,
        "monthly_categories": monthly_categories,
    }
    original_c5 = original_engine.compute_cycle_diagnostics("C5", **arguments)
    changed_c5 = changed_engine.compute_cycle_diagnostics("C5", **arguments)
    original_c4 = original_engine.compute_cycle_diagnostics("C4", **arguments)
    changed_c4 = changed_engine.compute_cycle_diagnostics("C4", **arguments)
    original = original_engine.compute(
        **arguments,
        as_of=pd.Timestamp("2024-10-07"),
    ).set_index("cycle_id")
    changed = changed_engine.compute(
        **arguments,
        as_of=pd.Timestamp("2024-10-07"),
    ).set_index("cycle_id")

    assert changed.loc["C5", "center_period"] == 29.0
    assert changed.loc["C5", "bandwidth"] == 18.0
    assert changed.loc["C5", "level"] != pytest.approx(original.loc["C5", "level"])
    assert not original_c5.member_components.equals(changed_c5.member_components)
    assert (
        original_c5.aggregation.member_signs["mid_mixed"]
        != changed_c5.aggregation.member_signs["mid_mixed"]
    ).any()
    assert not original_c5.aggregation.aggregate.equals(
        changed_c5.aggregation.aggregate
    )
    pd.testing.assert_frame_equal(
        original_c4.member_components,
        changed_c4.member_components,
        check_exact=True,
    )
    _assert_aggregation_exact(original_c4.aggregation, changed_c4.aggregation)
    pd.testing.assert_series_equal(
        changed.loc["C4"],
        original.loc["C4"],
        check_exact=True,
    )


def test_engine_rejects_resolved_center_outside_governed_band(
    cycle_specs: list[CycleSpec],
) -> None:
    invalid_specs = [
        cycle.model_copy(update={"initial_center": cycle.search_max + 1.0})
        if cycle.cycle_id == "C3"
        else cycle
        for cycle in cycle_specs
    ]

    with pytest.raises(ValueError, match="center.*search band"):
        SevenCycleEngine(invalid_specs)
