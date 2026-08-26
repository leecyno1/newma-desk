from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles import (
    AdaptiveHarmonicResult,
    adaptive_harmonic_state_filter,
)


RESULT_FIELDS = (
    "trend",
    "trend_slope",
    "level",
    "quadrature",
    "slope",
    "amplitude",
    "angle",
    "uncertainty",
    "period",
    "period_low",
    "period_high",
    "phase_agreement",
    "boundary_share",
    "selection_strength",
)


def _changing_period_series() -> pd.Series:
    count = 260
    periods = np.concatenate((np.full(130, 24.0), np.full(130, 12.0)))
    phase = np.zeros(count, dtype="float64")
    for position in range(1, count):
        phase[position] = phase[position - 1] + 2.0 * np.pi / periods[position]
    values = (
        0.02 * np.arange(count)
        + np.sin(phase)
        + 0.05 * np.cos(np.arange(count) * 0.7)
    )
    return pd.Series(values, name="adaptive_cycle", dtype="float64")


def test_adaptive_filter_tracks_period_change_without_absorbing_linear_trend() -> None:
    values = _changing_period_series()

    result = adaptive_harmonic_state_filter(
        values,
        period_min=8.0,
        period_max=30.0,
        score_window=60,
        min_score_observations=30,
    )

    assert isinstance(result, AdaptiveHarmonicResult)
    assert result.period.iloc[80:120].median() == pytest.approx(24.0, abs=1.0)
    assert result.period.iloc[-40:].median() == pytest.approx(12.0, abs=1.0)
    assert np.corrcoef(result.trend.iloc[80:], 0.02 * np.arange(80, 260))[0, 1] > 0.98
    assert bool(result.period.between(8.0, 30.0).all())
    assert bool(result.phase_agreement.between(0.0, 1.0).all())
    assert bool(result.boundary_share.between(0.0, 1.0).all())
    assert bool(result.selection_strength.between(0.0, 1.0).all())


def test_adaptive_filter_accepts_weak_period_prior() -> None:
    values = _changing_period_series()

    result = adaptive_harmonic_state_filter(
        values,
        period_min=8.0,
        period_max=30.0,
        period_prior=12.0,
        period_prior_weight=0.01,
        score_window=60,
        min_score_observations=30,
    )

    assert bool(result.period.between(8.0, 30.0).all())


def test_adaptive_filter_is_exactly_cutoff_invariant() -> None:
    history = _changing_period_series().iloc[:180]
    future = pd.Series(
        [1e6, -1e6, np.nan, 25.0] * 10,
        index=range(180, 220),
        name=history.name,
        dtype="float64",
    )

    history_result = adaptive_harmonic_state_filter(
        history,
        period_min=8.0,
        period_max=30.0,
        score_window=60,
        min_score_observations=30,
    )
    full_result = adaptive_harmonic_state_filter(
        pd.concat([history, future]),
        period_min=8.0,
        period_max=30.0,
        score_window=60,
        min_score_observations=30,
    )

    for field_name in RESULT_FIELDS:
        expected = getattr(history_result, field_name)
        actual = getattr(full_result, field_name).loc[history.index]
        pd.testing.assert_series_equal(expected, actual, check_exact=True)


def test_adaptive_result_is_frozen_and_defensive() -> None:
    values = _changing_period_series().iloc[:80]
    original = values.copy(deep=True)
    result = adaptive_harmonic_state_filter(
        values,
        period_min=8.0,
        period_max=30.0,
        score_window=40,
        min_score_observations=20,
    )
    expected = result.level

    values.iloc[:] = 999.0
    detached = result.level
    detached.iloc[:] = -999.0

    pd.testing.assert_series_equal(original, _changing_period_series().iloc[:80])
    pd.testing.assert_series_equal(result.level, expected, check_exact=True)
    with pytest.raises(FrozenInstanceError):
        result.model_count = 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"period_min": 10.0, "period_max": 10.0},
        {"period_min": 12.0, "period_max": 8.0},
        {"period_min": 8.0, "period_max": 12.0, "period_step": 0.0},
        {
            "period_min": 8.0,
            "period_max": 12.0,
            "score_window": 10,
            "min_score_observations": 11,
        },
    ],
)
def test_adaptive_filter_validates_search_contract(arguments: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        adaptive_harmonic_state_filter(pd.Series([1.0, 2.0]), **arguments)
