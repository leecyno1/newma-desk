from dataclasses import FrozenInstanceError, fields
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles import HarmonicStateResult, harmonic_state_filter


CAUSAL_FIELDS = (
    "level",
    "quadrature",
    "slope",
    "acceleration",
    "amplitude",
    "angle",
    "innovation",
    "uncertainty",
)
ALL_FIELDS = (*CAUSAL_FIELDS, "smoothed_level")


def _result_series() -> dict[str, pd.Series]:
    index = pd.Index(["first", "second"], name="sample")
    return {
        field_name: pd.Series(
            [1.0, 2.0],
            index=index,
            name="cycle",
            dtype="float64",
        )
        for field_name in ALL_FIELDS
    }


def test_harmonic_state_result_is_frozen_and_aligned() -> None:
    index = pd.date_range("2022-01-31", periods=4, freq="ME", name="date")
    values = pd.Series([0.0, 1.0, 0.0, -1.0], index=index, name="cycle")

    result = harmonic_state_filter(values, period=4.0)

    assert isinstance(result, HarmonicStateResult)
    assert [field.name for field in fields(HarmonicStateResult)] == list(ALL_FIELDS)
    for field_name in ALL_FIELDS:
        series = getattr(result, field_name)
        assert series.index.equals(index)
        assert series.name == "cycle"
        assert series.dtype == "float64"
    with pytest.raises(FrozenInstanceError):
        result.level = values


def test_harmonic_state_result_defensively_copies_and_is_deeply_immutable() -> None:
    source_fields = _result_series()
    result = HarmonicStateResult(**source_fields)
    expected = result.level

    source_fields["level"].iloc[0] = 100.0
    via_iloc = result.level
    via_iloc.iloc[0] = 200.0
    via_setitem = result.level
    via_setitem[via_setitem.index[0]] = 300.0
    via_array = result.level.to_numpy(copy=False)
    try:
        via_array[0] = 400.0
    except ValueError:
        pass

    pd.testing.assert_series_equal(result.level, expected, check_exact=True)
    internal = object.__getattribute__(result, "level")
    internal_array = internal.to_numpy(copy=False)
    assert not internal_array.flags.writeable
    with pytest.raises(ValueError):
        internal_array[0] = 500.0


def test_harmonic_state_result_is_independent_from_filter_input() -> None:
    values = pd.Series([0.0, 1.0, 0.0, -1.0], name="cycle")
    result = harmonic_state_filter(values, period=4.0)
    expected = result.level

    values.iloc[:] = 999.0

    pd.testing.assert_series_equal(result.level, expected, check_exact=True)


@pytest.mark.parametrize(
    ("field_name", "replacement", "message"),
    [
        (
            "quadrature",
            pd.Series([1.0, 2.0], index=["second", "first"], name="cycle"),
            "index",
        ),
        (
            "slope",
            pd.Series(
                [1.0, 2.0],
                index=pd.Index(["first", "second"], name="sample"),
                name="other",
            ),
            "name",
        ),
        (
            "acceleration",
            pd.Series(
                [1.0, 2.0],
                index=pd.Index(["first", "second"], name="sample"),
                name="cycle",
                dtype="float32",
            ),
            "dtype",
        ),
    ],
)
def test_harmonic_state_result_validates_field_alignment(
    field_name: str,
    replacement: pd.Series,
    message: str,
) -> None:
    source_fields = _result_series()
    source_fields[field_name] = replacement

    with pytest.raises(ValueError, match=message):
        HarmonicStateResult(**source_fields)


def test_harmonic_state_filter_returns_aligned_empty_float_series() -> None:
    values = pd.Series(
        index=pd.Index([], name="sample"),
        dtype="float64",
        name="empty_cycle",
    )

    result = harmonic_state_filter(values, period=12.0)

    for field_name in ALL_FIELDS:
        series = getattr(result, field_name)
        assert series.empty
        assert series.index.equals(values.index)
        assert series.name == values.name
        assert series.dtype == "float64"


@pytest.mark.parametrize("period", [0.0, -1.0, np.nan, np.inf])
def test_harmonic_state_filter_validates_period(period: float) -> None:
    with pytest.raises(ValueError, match="period"):
        harmonic_state_filter(pd.Series([1.0]), period=period)


@pytest.mark.parametrize("parameter", ["cycle_variance", "observation_variance"])
@pytest.mark.parametrize("value", [-1.0, np.nan, np.inf])
def test_harmonic_state_filter_validates_variances(
    parameter: str,
    value: float,
) -> None:
    with pytest.raises(ValueError, match=parameter):
        harmonic_state_filter(pd.Series([1.0]), period=12.0, **{parameter: value})


@pytest.mark.parametrize("half_life_cycles", [0.0, -1.0, np.nan, np.inf])
def test_harmonic_state_filter_validates_half_life(half_life_cycles: float) -> None:
    with pytest.raises(ValueError, match="half_life_cycles"):
        harmonic_state_filter(
            pd.Series([1.0]),
            period=12.0,
            half_life_cycles=half_life_cycles,
        )


@pytest.mark.parametrize(
    "parameter",
    [
        "period",
        "cycle_variance",
        "observation_variance",
        "half_life_cycles",
    ],
)
@pytest.mark.parametrize("value", [True, False, "1.0"])
def test_harmonic_state_filter_rejects_non_real_parameter_types(
    parameter: str,
    value: object,
) -> None:
    arguments: dict[str, object] = {"period": 12.0, parameter: value}

    with pytest.raises(TypeError, match=parameter):
        harmonic_state_filter(pd.Series([1.0]), **arguments)


def test_harmonic_state_filter_accepts_numpy_real_scalars() -> None:
    result = harmonic_state_filter(
        pd.Series([1.0, 2.0]),
        period=np.float64(12.0),
        cycle_variance=np.float32(0.35),
        observation_variance=np.int64(1),
        half_life_cycles=np.float64(2.0),
    )

    assert len(result.level) == 2


def test_harmonic_state_filter_missing_observation_uses_prediction() -> None:
    values = pd.Series([1.0, np.nan], name="cycle")
    period = 8.0
    cycle_variance = 0.4
    observation_variance = 0.6
    half_life_cycles = 2.0

    result = harmonic_state_filter(
        values,
        period=period,
        cycle_variance=cycle_variance,
        observation_variance=observation_variance,
        half_life_cycles=half_life_cycles,
    )

    angular_frequency = 2.0 * np.pi / period
    damping = 0.5 ** (1.0 / (half_life_cycles * period))
    transition = damping * np.array(
        [
            [np.cos(angular_frequency), np.sin(angular_frequency)],
            [-np.sin(angular_frequency), np.cos(angular_frequency)],
        ]
    )
    filtered_first = np.array([result.level.iloc[0], result.quadrature.iloc[0]])
    predicted_second = transition @ filtered_first

    assert result.innovation.iloc[0] == 1.0
    assert np.isnan(result.innovation.iloc[1])
    np.testing.assert_array_equal(
        [result.level.iloc[1], result.quadrature.iloc[1]],
        predicted_second,
    )

    gain = cycle_variance / (cycle_variance + observation_variance)
    first_covariance = np.diag(
        [
            (1.0 - gain) ** 2 * cycle_variance
            + gain**2 * observation_variance,
            cycle_variance,
        ]
    )
    process_covariance = np.eye(2) * cycle_variance * (1.0 - damping**2)
    predicted_second_covariance = (
        transition @ first_covariance @ transition.T + process_covariance
    )
    assert result.uncertainty.iloc[1] == pytest.approx(
        np.sqrt(predicted_second_covariance[0, 0])
    )


def test_harmonic_state_filter_uncertainty_is_covariance_derived() -> None:
    cycle_variance = 0.35
    observation_variance = 0.65

    result = harmonic_state_filter(
        pd.Series([2.0]),
        period=12.0,
        cycle_variance=cycle_variance,
        observation_variance=observation_variance,
    )

    posterior_variance = (
        cycle_variance * observation_variance
        / (cycle_variance + observation_variance)
    )
    assert result.uncertainty.iloc[0] == pytest.approx(np.sqrt(posterior_variance))


def test_harmonic_state_filter_causal_fields_are_exactly_cutoff_invariant() -> None:
    history_index = pd.date_range("2000-01-31", periods=32, freq="ME", name="date")
    history = pd.Series(
        np.sin(np.arange(32) * 2.0 * np.pi / 12.0),
        index=history_index,
        name="cycle",
    )
    history.iloc[[5, 11, 24]] = np.nan
    future = pd.Series(
        [1e9, np.nan, -1e9, 7.0, -3.0, 0.0, 50.0, np.nan],
        index=pd.date_range("2002-09-30", periods=8, freq="ME", name="date"),
        name="cycle",
    )

    history_result = harmonic_state_filter(
        history,
        period=12.0,
        cycle_variance=0.2,
        observation_variance=0.8,
        half_life_cycles=1.5,
    )
    full_result = harmonic_state_filter(
        pd.concat([history, future]),
        period=12.0,
        cycle_variance=0.2,
        observation_variance=0.8,
        half_life_cycles=1.5,
    )

    for field_name in CAUSAL_FIELDS:
        expected = getattr(history_result, field_name)
        actual = getattr(full_result, field_name).loc[history.index]
        pd.testing.assert_series_equal(expected, actual, check_exact=True)
        assert expected.isna().equals(actual.isna())
        assert expected.to_numpy().tobytes() == actual.to_numpy().tobytes()


def test_harmonic_state_filter_sinusoid_has_consistent_latent_geometry() -> None:
    period = 24.0
    angular_frequency = 2.0 * np.pi / period
    amplitude = 2.5
    positions = np.arange(240, dtype="float64")
    observations = amplitude * np.sin(angular_frequency * positions + 0.4)
    values = pd.Series(
        observations,
        index=pd.date_range("2000-01-31", periods=len(positions), freq="ME"),
        name="sinusoid",
    )

    result = harmonic_state_filter(
        values,
        period=period,
        cycle_variance=4.0,
        observation_variance=0.01,
        half_life_cycles=1_000.0,
    )

    tail = slice(120, None)
    expected_quadrature = amplitude * np.cos(angular_frequency * positions + 0.4)
    expected_slope = angular_frequency * expected_quadrature
    expected_acceleration = -(angular_frequency**2) * observations
    assert np.corrcoef(result.level.iloc[tail], observations[tail])[0, 1] > 0.995
    assert (
        np.corrcoef(result.quadrature.iloc[tail], expected_quadrature[tail])[0, 1]
        > 0.98
    )
    assert np.corrcoef(result.slope.iloc[tail], expected_slope[tail])[0, 1] > 0.98
    assert (
        np.corrcoef(result.acceleration.iloc[tail], expected_acceleration[tail])[0, 1]
        > 0.98
    )
    assert np.median(result.amplitude.iloc[tail]) == pytest.approx(amplitude, rel=0.08)
    assert bool((result.amplitude >= 0.0).all())
    assert bool(((result.angle >= 0.0) & (result.angle < 360.0)).all())
    np.testing.assert_allclose(
        result.level,
        result.amplitude * np.cos(np.deg2rad(result.angle)),
        atol=1e-12,
    )
    np.testing.assert_allclose(
        result.quadrature,
        result.amplitude * np.sin(np.deg2rad(result.angle)),
        atol=1e-12,
    )
    assert bool((result.uncertainty >= 0.0).all())


def test_harmonic_state_derivatives_follow_damped_oscillator_state() -> None:
    period = 10.0
    half_life_cycles = 3.0
    values = pd.Series([0.0, 0.5, 1.0, 0.5, 0.0], name="cycle")

    result = harmonic_state_filter(
        values,
        period=period,
        half_life_cycles=half_life_cycles,
    )

    angular_frequency = 2.0 * np.pi / period
    decay_rate = -np.log(2.0) / (half_life_cycles * period)
    expected_slope = decay_rate * result.level + angular_frequency * result.quadrature
    expected_acceleration = (
        (decay_rate**2 - angular_frequency**2) * result.level
        + 2.0 * decay_rate * angular_frequency * result.quadrature
    )
    pd.testing.assert_series_equal(result.slope, expected_slope.rename("cycle"))
    pd.testing.assert_series_equal(
        result.acceleration,
        expected_acceleration.rename("cycle"),
    )


def test_harmonic_state_filter_is_deterministic() -> None:
    values = pd.Series([0.0, 1.0, np.nan, -1.0, 0.0], name="cycle")

    first = harmonic_state_filter(values, period=4.0)
    second = harmonic_state_filter(values, period=4.0)

    for field_name in ALL_FIELDS:
        pd.testing.assert_series_equal(
            getattr(first, field_name),
            getattr(second, field_name),
            check_exact=True,
        )


def test_legacy_harmonic_wrapper_preserves_tuple_api(monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(project_root / "scripts"))
    legacy_module = import_module("cycle_realtime_core")
    values = pd.Series([0.0, 1.0, 0.0, -1.0], name="cycle")

    legacy_result = legacy_module.harmonic_state_filter(values, period=4.0)
    package_result = harmonic_state_filter(values, period=4.0)

    assert isinstance(legacy_result, tuple)
    assert len(legacy_result) == 3
    for actual, expected in zip(
        legacy_result,
        (
            package_result.level,
            package_result.smoothed_level,
            package_result.uncertainty,
        ),
        strict=True,
    ):
        pd.testing.assert_series_equal(actual, expected, check_exact=True)
