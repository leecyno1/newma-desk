from __future__ import annotations

import numpy as np
import pandas as pd

from seven_cycle_platform.cycles.c2_regime import (
    _confirm_transitions,
    bis_area_code,
    build_c2_historical_dating,
    build_direct_c2_state,
    date_c2_turning_points,
    estimate_c2_lead_lag,
)


def test_c2_bis_country_codes_use_two_letter_areas() -> None:
    assert {
        iso: bis_area_code(iso)
        for iso in ("CHN", "USA", "JPN", "GBR")
    } == {
        "CHN": "CN",
        "USA": "US",
        "JPN": "JP",
        "GBR": "GB",
    }


def test_c2_uses_multi_window_momentum_consensus() -> None:
    years = pd.Index(range(1980, 2027), name="year")
    activity = pd.Series(
        np.r_[np.linspace(0.8, 0.0, 44), -1.0, -0.9, -0.8],
        index=years,
    )

    state = build_direct_c2_state(activity)
    latest = state.iloc[-1]

    assert latest["slope1Y"] > 0
    assert latest["slope3Y"] < 0
    assert latest["slopeConsensus"] < 1.0
    assert latest["phase"] == "contraction"


def test_c2_transition_needs_two_consecutive_periods() -> None:
    raw = pd.Series(
        ["contraction", "recovery", "contraction", "recovery", "recovery"],
        index=pd.Index(range(2022, 2027), name="year"),
    )

    confirmed, confirmed_at = _confirm_transitions(raw, confirmation_periods=2)

    assert confirmed.tolist() == [
        "contraction",
        "contraction",
        "contraction",
        "contraction",
        "recovery",
    ]
    assert confirmed_at.iloc[-1] == 2026


def test_c2_four_phase_state_does_not_skip_two_phases() -> None:
    raw = pd.Series(
        ["expansion", "contraction", "contraction", "contraction"],
        index=pd.Index(range(2023, 2027), name="year"),
    )

    confirmed, _ = _confirm_transitions(raw, confirmation_periods=2)

    assert confirmed.tolist() == [
        "expansion",
        "expansion",
        "slowdown",
        "slowdown",
    ]


def test_c2_causal_state_does_not_rewrite_appended_history() -> None:
    years = pd.Index(range(1900, 2027), name="year")
    activity = pd.Series(
        np.sin(np.arange(len(years)) / 4.0) + np.arange(len(years)) * 0.002,
        index=years,
    )

    full = build_direct_c2_state(activity)
    truncated = build_direct_c2_state(activity.loc[:2000])

    pd.testing.assert_frame_equal(
        full.loc[:2000],
        truncated,
    )


def test_c2_historical_dating_is_consensus_based_and_alternating() -> None:
    years = pd.Index(range(1900, 2027), name="year")
    activity = pd.Series(
        np.sin(2.0 * np.pi * np.arange(len(years)) / 18.0)
        + 0.15 * np.sin(2.0 * np.pi * np.arange(len(years)) / 5.0),
        index=years,
    )

    dating = build_c2_historical_dating(activity)
    turns = dating["turningPoints"]
    realtime_turns = date_c2_turning_points(build_direct_c2_state(activity))

    assert dating["lookAhead"] is True
    assert dating["specificationCount"] >= 12
    assert len(turns) >= 8
    assert all(turn["support"] >= dating["minimumSupport"] for turn in turns)
    assert all(
        left["kind"] != right["kind"]
        for left, right in zip(turns, turns[1:], strict=False)
    )
    assert len({(turn["year"], turn["kind"]) for turn in realtime_turns}) == len(
        realtime_turns
    )


def test_c2_lead_lag_detects_material_lead() -> None:
    years = pd.Index(range(1980, 2026), name="year")
    source = pd.Series(np.sin(np.arange(len(years)) / 3.0), index=years)
    target = source.shift(2)

    result = estimate_c2_lead_lag(source, target)

    assert result["leadYears"] == 2
    assert result["materialLag"] is True
    assert float(result["correlationImprovement"]) > 0.10
