from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles.phase import phase_from_level_slope
from seven_cycle_platform.forecast.cycles import (
    CALIBRATION_HISTORY_COLUMNS,
    CYCLE_FORECAST_SUMMARY_COLUMNS,
    CYCLE_MONTHLY_PATH_COLUMNS,
    CYCLE_STATE_COLUMNS,
    LEADING_SIGNAL_COLUMNS,
    CycleForecastConfig,
    CycleForecastInput,
    CycleForecastResult,
    forecast_cycle_phases,
)
from seven_cycle_platform.registry.loader import load_registry_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AS_OF = date(2024, 6, 30)
PHASES = ("expansion", "downturn", "contraction", "recovery")


def _registry():
    return load_registry_bundle(PROJECT_ROOT / "config" / "seven_cycle")


def _state_rows(cycle_specs) -> pd.DataFrame:
    rows = []
    for position, cycle in enumerate(cycle_specs, start=1):
        center_period = (
            float(cycle.initial_center)
            if cycle.initial_center is not None
            else (float(cycle.search_min) + float(cycle.search_max)) / 2.0
        )
        period_months = (
            center_period * 12.0 if cycle.frequency == "A" else center_period
        )
        rows.append(
            {
                "as_of": AS_OF,
                "state_date": AS_OF,
                "visible_date": AS_OF,
                "data_vintage": AS_OF,
                "cycle_id": cycle.cycle_id,
                "status": "available",
                "unavailable_reason": None,
                "level": 0.45 - 0.04 * position,
                "quadrature": 0.20 + 0.02 * position,
                "covariance_00": 0.035,
                "covariance_01": 0.004,
                "covariance_11": 0.030,
                "phase_velocity": 2.0 * np.pi / period_months,
                "acceleration": 0.0,
                "phase_duration_months": 3.0,
                "confidence": 0.82,
                "center_period": center_period,
                "state_model_version": "cycle-state-v1",
                "state_config_hash": "a" * 64,
            }
        )
    return pd.DataFrame(rows, columns=CYCLE_STATE_COLUMNS)


def _forecast_input(
    *,
    cycle_specs=None,
    indicator_specs=None,
    states: pd.DataFrame | None = None,
    leading_signals: pd.DataFrame | None = None,
    calibration_history: pd.DataFrame | None = None,
) -> CycleForecastInput:
    registry = _registry()
    cycles = registry.cycles if cycle_specs is None else cycle_specs
    indicators = registry.indicators if indicator_specs is None else indicator_specs
    return CycleForecastInput(
        as_of=AS_OF,
        cycle_specs=cycles,
        indicator_specs=indicators,
        states=_state_rows(cycles) if states is None else states,
        leading_signals=(
            pd.DataFrame(columns=LEADING_SIGNAL_COLUMNS)
            if leading_signals is None
            else leading_signals
        ),
        calibration_history=(
            pd.DataFrame(columns=CALIBRATION_HISTORY_COLUMNS)
            if calibration_history is None
            else calibration_history
        ),
    )


def _config(**overrides) -> CycleForecastConfig:
    values = {"draw_count": 64, "seed": 24, **overrides}
    return CycleForecastConfig(**values)


def _replace_state(
    states: pd.DataFrame,
    cycle_id: str,
    **updates: object,
) -> pd.DataFrame:
    replaced = states.copy(deep=True)
    row_index = replaced.index[replaced["cycle_id"].eq(cycle_id)].item()
    for column, value in updates.items():
        replaced.at[row_index, column] = value
    return replaced


def _leading_signal(
    *,
    cycle_id: str = "C5",
    indicator_id: str = "cn_m1",
    signal_value: float = 1.0,
    direction_prior: float = 1.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "as_of": AS_OF,
                "observation_date": date(2024, 6, 1),
                "release_date": date(2024, 6, 5),
                "visible_date": date(2024, 6, 6),
                "cycle_id": cycle_id,
                "indicator_id": indicator_id,
                "signal_value": signal_value,
                "direction_prior": direction_prior,
            }
        ],
        columns=LEADING_SIGNAL_COLUMNS,
    )


def _calibration_history(
    *,
    count: int,
    cycle_id: str = "C5",
    horizon: int = 3,
    realized_offset: int = 1,
) -> pd.DataFrame:
    rows = []
    for position in range(count):
        forecast_origin = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(position)
        first_target = forecast_origin + pd.offsets.MonthEnd(1)
        target_date = first_target + pd.offsets.MonthEnd(horizon - 1)
        predicted_position = position % len(PHASES)
        probabilities = np.full(len(PHASES), 0.10, dtype="float64")
        probabilities[predicted_position] = 0.70
        probabilities /= probabilities.sum()
        realized_phase = PHASES[(predicted_position + realized_offset) % len(PHASES)]
        rows.append(
            {
                "forecast_origin": forecast_origin,
                "target_date": target_date,
                "cycle_id": cycle_id,
                "horizon_months": horizon,
                **{
                    f"raw_{phase}_probability": probabilities[phase_position]
                    for phase_position, phase in enumerate(PHASES)
                },
                "realized_phase": realized_phase,
                "fold_id": f"fold-{cycle_id}-{horizon}-{position:03d}",
            }
        )
    return pd.DataFrame(rows, columns=CALIBRATION_HISTORY_COLUMNS)


def test_forecast_uses_registry_horizons_and_normalized_phase_probabilities() -> None:
    forecast_input = _forecast_input()

    result = forecast_cycle_phases(
        forecast_input,
        config=CycleForecastConfig(draw_count=256, seed=24),
    )

    expected_dimensions = {
        (cycle.cycle_id, horizon)
        for cycle in forecast_input.cycle_specs
        for horizon in cycle.horizons
    }
    summary = result.summary
    assert set(zip(summary["cycle_id"], summary["horizon_months"], strict=True)) == (
        expected_dimensions
    )
    for prefix in ("raw_", ""):
        columns = [f"{prefix}{phase}_probability" for phase in PHASES]
        probabilities = summary.loc[:, columns].to_numpy(dtype="float64")
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_shared_paths_drive_horizon_probabilities_and_turning_windows() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    paths = result.monthly_paths
    summary = result.summary

    for cycle in result.forecast_input.cycle_specs:
        cycle_paths = paths.loc[paths["cycle_id"].eq(cycle.cycle_id)]
        assert set(cycle_paths["month_number"]) == set(
            range(1, max(cycle.horizons) + 1)
        )
        for draw_id, draw_path in cycle_paths.groupby("draw_id", sort=False):
            assert draw_id in range(result.config.draw_count)
            assert draw_path.sort_values("month_number")["month_number"].tolist() == (
                list(range(1, max(cycle.horizons) + 1))
            )

        for horizon in cycle.horizons:
            row = summary.loc[
                summary["cycle_id"].eq(cycle.cycle_id)
                & summary["horizon_months"].eq(horizon)
            ].iloc[0]
            endpoint = cycle_paths.loc[cycle_paths["month_number"].eq(horizon)]
            for phase in PHASES:
                assert row[f"raw_{phase}_probability"] == pytest.approx(
                    endpoint["phase"].eq(phase).mean()
                )

            first_turns = cycle_paths.loc[
                cycle_paths["is_first_turn"] & cycle_paths["month_number"].le(horizon)
            ]
            assert row["turning_probability"] == pytest.approx(
                first_turns["draw_id"].nunique() / result.config.draw_count
            )
            if first_turns.empty:
                assert row["turning_status"] == "none"
                assert pd.isna(row["turning_median_date"])
            else:
                expected_median = int(
                    np.ceil(np.quantile(first_turns["month_number"], 0.50))
                )
                expected_start = int(
                    np.ceil(np.quantile(first_turns["month_number"], 0.10))
                )
                expected_end = int(
                    np.ceil(np.quantile(first_turns["month_number"], 0.90))
                )
                assert row["turning_status"] == "available"
                assert row["turning_start_month"] == expected_start
                assert row["turning_end_month"] == expected_end
                assert row["turning_median_month"] == expected_median
                assert row["turning_median_date"] == pd.Timestamp(
                    first_turns.loc[
                        first_turns["month_number"].eq(expected_median), "date"
                    ].iloc[0]
                )


def test_per_draw_origin_and_turning_replay_seeded_initial_posterior() -> None:
    registry = _registry()
    cycle = next(cycle for cycle in registry.cycles if cycle.cycle_id == "C5")
    center_period = float(cycle.initial_center)
    base_velocity = 2.0 * np.pi / center_period
    states = _replace_state(
        _state_rows(registry.cycles),
        "C5",
        level=0.0,
        quadrature=0.0,
        covariance_00=0.20,
        covariance_01=0.05,
        covariance_11=0.18,
        phase_velocity=base_velocity,
        acceleration=0.0,
        phase_duration_months=center_period / 4.0,
        confidence=0.90,
    )
    config = _config(draw_count=256, seed=91, process_noise_scale=0.02)
    result = forecast_cycle_phases(_forecast_input(states=states), config=config)

    covariance = np.asarray([[0.20, 0.05], [0.05, 0.18]], dtype="float64")
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    covariance_root = (
        eigenvectors @ np.diag(np.sqrt(np.maximum(eigenvalues, 0.0))) @ eigenvectors.T
    )
    generator = np.random.default_rng(np.random.SeedSequence([config.seed, 5, 24]))
    initial_states = generator.standard_normal((config.draw_count, 2)) @ (
        covariance_root.T
    )
    damping = 0.5 ** (1.0 / (config.half_life_cycles * center_period))
    decay_rate = float(np.log(damping))
    expected_origin_slopes = (
        decay_rate * initial_states[:, 0] + base_velocity * initial_states[:, 1]
    )
    expected_origin_phases = np.asarray(
        [
            phase_from_level_slope(level, slope).value
            for level, slope in zip(
                initial_states[:, 0],
                expected_origin_slopes,
                strict=True,
            )
        ],
        dtype=object,
    )

    cycle_paths = result.monthly_paths.loc[
        result.monthly_paths["cycle_id"].eq("C5")
    ].sort_values(["draw_id", "month_number"], kind="stable")
    origins = cycle_paths.groupby("draw_id", sort=True).first()
    np.testing.assert_allclose(
        origins["origin_slope"].to_numpy(dtype="float64"),
        expected_origin_slopes,
    )
    np.testing.assert_array_equal(
        origins["origin_phase"].to_numpy(dtype=object),
        expected_origin_phases,
    )
    assert origins["origin_slope"].nunique() > config.draw_count // 2
    assert origins["origin_phase"].nunique() > 1

    expected_phase_transition = (
        cycle_paths["phase"].to_numpy(dtype=object)
        != (expected_origin_phases[cycle_paths["draw_id"].to_numpy(dtype="int64")])
    )
    expected_slope_turn = cycle_paths["slope"].ge(0.0).to_numpy() != (
        expected_origin_slopes[cycle_paths["draw_id"].to_numpy(dtype="int64")] >= 0.0
    )
    expected_event = expected_phase_transition | expected_slope_turn
    event_counts = (
        pd.Series(expected_event, index=cycle_paths.index)
        .groupby(
            cycle_paths["draw_id"],
            sort=False,
        )
        .cumsum()
    )
    expected_first_turn = expected_event & event_counts.eq(1).to_numpy()
    np.testing.assert_array_equal(
        cycle_paths["is_phase_transition"].to_numpy(dtype=bool),
        expected_phase_transition,
    )
    np.testing.assert_array_equal(
        cycle_paths["is_slope_turn"].to_numpy(dtype=bool),
        expected_slope_turn,
    )
    np.testing.assert_array_equal(
        cycle_paths["is_first_turn"].to_numpy(dtype=bool),
        expected_first_turn,
    )

    horizon = 3
    turning_draws = cycle_paths.loc[
        cycle_paths["month_number"].le(horizon)
        & pd.Series(expected_first_turn, index=cycle_paths.index),
        "draw_id",
    ].nunique()
    row = result.summary.loc[
        result.summary["cycle_id"].eq("C5")
        & result.summary["horizon_months"].eq(horizon)
    ].iloc[0]
    assert row["turning_probability"] == pytest.approx(
        turning_draws / config.draw_count
    )


def test_angle_quantiles_remain_ordered_across_zero_degree_wrap() -> None:
    registry = _registry()
    states = _replace_state(
        _state_rows(registry.cycles),
        "C7",
        level=0.50,
        quadrature=0.005,
        covariance_00=0.0001,
        covariance_01=0.0,
        covariance_11=0.0001,
        confidence=1.0,
    )
    result = forecast_cycle_phases(
        _forecast_input(states=states),
        config=_config(draw_count=128, process_noise_scale=0.002),
    )

    row = result.summary.loc[
        result.summary["cycle_id"].eq("C7") & result.summary["horizon_months"].eq(1)
    ].iloc[0]
    quantiles = row[["angle_q10", "angle_q25", "angle_q50", "angle_q75", "angle_q90"]]
    assert quantiles.tolist() == sorted(quantiles.tolist())
    assert row["angle_anchor_degrees"] < 5.0
    assert row["angle_q50"] < 0.0

    endpoint = result.monthly_paths.loc[
        result.monthly_paths["cycle_id"].eq("C7")
        & result.monthly_paths["month_number"].eq(1)
    ]
    assert endpoint["angle_degrees"].between(0.0, 360.0, inclusive="left").all()
    assert endpoint["angle_unwrapped_degrees"].lt(0.0).mean() > 0.90


def test_uncertainty_is_non_decreasing_and_long_cycles_are_wider() -> None:
    registry = _registry()
    states = _state_rows(registry.cycles)
    for column, value in {
        "level": 0.40,
        "quadrature": 0.25,
        "covariance_00": 0.03,
        "covariance_01": 0.0,
        "covariance_11": 0.03,
        "confidence": 0.80,
    }.items():
        states[column] = value
    result = forecast_cycle_phases(_forecast_input(states=states), config=_config())
    summary = result.summary

    for _, cycle_summary in summary.groupby("cycle_id", sort=False):
        ordered = cycle_summary.sort_values("horizon_months")
        assert ordered["forecast_uncertainty"].diff().dropna().ge(0.0).all()

    uncertainty = summary.set_index(["cycle_id", "horizon_months"])[
        "forecast_uncertainty"
    ]
    assert uncertainty.loc[("C1", 12)] > uncertainty.loc[("C3", 12)]
    assert uncertainty.loc[("C2", 12)] > uncertainty.loc[("C3", 12)]


def test_full_latent_covariance_controls_forecast_spread() -> None:
    registry = _registry()
    states = _state_rows(registry.cycles)
    low_covariance = _replace_state(
        states,
        "C5",
        covariance_00=0.001,
        covariance_01=0.0002,
        covariance_11=0.001,
    )
    high_covariance = _replace_state(
        states,
        "C5",
        covariance_00=0.12,
        covariance_01=0.04,
        covariance_11=0.10,
    )
    config = _config(draw_count=256)
    low = forecast_cycle_phases(_forecast_input(states=low_covariance), config=config)
    high = forecast_cycle_phases(_forecast_input(states=high_covariance), config=config)

    low_row = low.summary.loc[
        low.summary["cycle_id"].eq("C5") & low.summary["horizon_months"].eq(6)
    ].iloc[0]
    high_row = high.summary.loc[
        high.summary["cycle_id"].eq("C5") & high.summary["horizon_months"].eq(6)
    ].iloc[0]
    assert high_row["forecast_uncertainty"] > low_row["forecast_uncertainty"]
    assert (high_row["angle_q90"] - high_row["angle_q10"]) > (
        low_row["angle_q90"] - low_row["angle_q10"]
    )


def test_input_shuffle_is_deterministic_and_inputs_are_not_modified() -> None:
    registry = _registry()
    states = _state_rows(registry.cycles).sample(frac=1.0, random_state=9)
    signals = pd.concat(
        [
            _leading_signal(cycle_id="C5", indicator_id="cn_m1", signal_value=0.6),
            _leading_signal(
                cycle_id="C4",
                indicator_id="cn_pmi_new_orders",
                signal_value=-0.4,
            ),
        ],
        ignore_index=True,
    ).sample(frac=1.0, random_state=8)
    states_before = states.copy(deep=True)
    signals_before = signals.copy(deep=True)
    config = _config()

    shuffled = _forecast_input(
        cycle_specs=list(reversed(registry.cycles)),
        indicator_specs=list(reversed(registry.indicators)),
        states=states,
        leading_signals=signals,
    )
    ordered = _forecast_input(
        cycle_specs=registry.cycles,
        indicator_specs=registry.indicators,
        states=_state_rows(registry.cycles),
        leading_signals=signals.sort_values(["cycle_id", "indicator_id"]),
    )
    first = forecast_cycle_phases(shuffled, config=config)
    second = forecast_cycle_phases(shuffled, config=config)
    reference = forecast_cycle_phases(ordered, config=config)

    pd.testing.assert_frame_equal(first.summary, second.summary)
    pd.testing.assert_frame_equal(first.monthly_paths, second.monthly_paths)
    pd.testing.assert_frame_equal(first.summary, reference.summary)
    pd.testing.assert_frame_equal(first.monthly_paths, reference.monthly_paths)
    pd.testing.assert_frame_equal(states, states_before)
    pd.testing.assert_frame_equal(signals, signals_before)


def test_result_is_defensive_and_rejects_forged_summary() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    original_summary = result.summary
    original_paths = result.monthly_paths

    detached_summary = result.summary
    detached_paths = result.monthly_paths
    detached_summary.loc[0, "raw_expansion_probability"] = 0.99
    detached_paths.loc[0, "level"] = 999.0
    pd.testing.assert_frame_equal(result.summary, original_summary)
    pd.testing.assert_frame_equal(result.monthly_paths, original_paths)

    forged = original_summary.copy(deep=True)
    forged.loc[0, "angle_q50"] += 1.0
    with pytest.raises(ValueError, match="inconsistent"):
        CycleForecastResult(
            summary=forged,
            monthly_paths=original_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )

    with pytest.raises(FrozenInstanceError):
        result.config.seed = 7


def test_unavailable_cycle_retains_all_registry_horizon_rows() -> None:
    registry = _registry()
    states = _state_rows(registry.cycles)
    unavailable = _replace_state(
        states,
        "C1",
        status="unavailable",
        unavailable_reason="insufficient_state_history",
        **{column: np.nan for column in CYCLE_STATE_COLUMNS[7:17]},
    )

    result = forecast_cycle_phases(
        _forecast_input(states=unavailable), config=_config()
    )

    c1 = result.summary.loc[result.summary["cycle_id"].eq("C1")]
    assert set(c1["horizon_months"]) == set(registry.cycles[0].horizons)
    assert set(c1["status"]) == {"unavailable"}
    assert set(c1["unavailable_reason"]) == {"insufficient_state_history"}
    assert c1[[f"{phase}_probability" for phase in PHASES]].isna().all().all()
    assert not result.monthly_paths["cycle_id"].eq("C1").any()


def test_point_in_time_state_dates_cannot_follow_as_of() -> None:
    registry = _registry()
    states = _replace_state(
        _state_rows(registry.cycles),
        "C5",
        visible_date=AS_OF + timedelta(days=1),
    )

    with pytest.raises(ValueError, match="visible_date cannot follow as_of"):
        _forecast_input(states=states)


def test_contract_constants_are_exact_and_stable() -> None:
    assert (
        tuple(pd.DataFrame(columns=CYCLE_STATE_COLUMNS).columns) == CYCLE_STATE_COLUMNS
    )
    assert (
        tuple(pd.DataFrame(columns=CYCLE_MONTHLY_PATH_COLUMNS).columns)
        == CYCLE_MONTHLY_PATH_COLUMNS
    )
    assert (
        tuple(pd.DataFrame(columns=CYCLE_FORECAST_SUMMARY_COLUMNS).columns)
        == CYCLE_FORECAST_SUMMARY_COLUMNS
    )


def test_annual_cycle_periods_are_converted_to_monthly_phase_velocity() -> None:
    registry = _registry()
    result = forecast_cycle_phases(_forecast_input(), config=_config())

    for cycle_id in ("C1", "C2", "C3"):
        cycle = next(cycle for cycle in registry.cycles if cycle.cycle_id == cycle_id)
        state = (
            _state_rows(registry.cycles)
            .loc[lambda frame: frame["cycle_id"].eq(cycle_id)]
            .iloc[0]
        )
        path_velocity = result.monthly_paths.loc[
            result.monthly_paths["cycle_id"].eq(cycle_id),
            "base_phase_velocity",
        ].iloc[0]
        assert path_velocity == pytest.approx(
            2.0 * np.pi / (float(state["center_period"]) * 12.0)
        )
        assert cycle.frequency == "A"


def test_turning_window_explicitly_reports_none_without_a_draw_turn() -> None:
    registry = _registry()
    states = _replace_state(
        _state_rows(registry.cycles),
        "C1",
        level=2.0,
        quadrature=2.0,
        covariance_00=1e-10,
        covariance_01=0.0,
        covariance_11=1e-10,
        confidence=1.0,
    )
    result = forecast_cycle_phases(
        _forecast_input(states=states),
        config=_config(draw_count=32, process_noise_scale=1e-8),
    )
    row = result.summary.loc[
        result.summary["cycle_id"].eq("C1") & result.summary["horizon_months"].eq(12)
    ].iloc[0]

    assert row["turning_status"] == "none"
    assert row["turning_probability"] == 0.0
    assert pd.isna(row["turning_start_month"])
    assert pd.isna(row["turning_end_date"])


def test_velocity_acceleration_duration_and_leading_signal_shift_paths_boundedly() -> (
    None
):
    registry = _registry()
    cycle = next(cycle for cycle in registry.cycles if cycle.cycle_id == "C5")
    base_velocity = 2.0 * np.pi / float(cycle.initial_center)
    states = _replace_state(
        _state_rows(registry.cycles),
        "C5",
        level=0.15,
        quadrature=0.60,
        covariance_00=0.0001,
        covariance_01=0.0,
        covariance_11=0.0001,
        confidence=1.0,
        phase_velocity=base_velocity,
        acceleration=0.0,
        phase_duration_months=float(cycle.initial_center) / 4.0,
    )
    config = _config(draw_count=128, process_noise_scale=0.002)

    def metrics(
        state_values: pd.DataFrame,
        signals: pd.DataFrame | None = None,
    ) -> tuple[pd.Series, float]:
        result = forecast_cycle_phases(
            _forecast_input(states=state_values, leading_signals=signals),
            config=config,
        )
        row = result.summary.loc[
            result.summary["cycle_id"].eq("C5") & result.summary["horizon_months"].eq(3)
        ].iloc[0]
        endpoint_level = result.monthly_paths.loc[
            result.monthly_paths["cycle_id"].eq("C5")
            & result.monthly_paths["month_number"].eq(3),
            "level",
        ].mean()
        return row, float(endpoint_level)

    faster, _ = metrics(
        _replace_state(states, "C5", phase_velocity=base_velocity * 1.25)
    )
    slower, _ = metrics(
        _replace_state(states, "C5", phase_velocity=base_velocity * 0.75)
    )
    positive_acceleration, _ = metrics(_replace_state(states, "C5", acceleration=1.0))
    negative_acceleration, _ = metrics(_replace_state(states, "C5", acceleration=-1.0))
    longer_duration, _ = metrics(
        _replace_state(states, "C5", phase_duration_months=12.0)
    )
    shorter_duration, _ = metrics(
        _replace_state(states, "C5", phase_duration_months=1.0)
    )
    positive_leading, positive_level = metrics(
        states,
        _leading_signal(signal_value=3.0),
    )
    negative_leading, negative_level = metrics(
        states,
        _leading_signal(signal_value=-3.0),
    )

    assert faster["angle_q50"] < slower["angle_q50"]
    assert positive_acceleration["angle_q50"] < negative_acceleration["angle_q50"]
    assert longer_duration["angle_q50"] < shorter_duration["angle_q50"]
    assert positive_level > negative_level
    assert positive_leading["leading_adjustment"] > 0.0
    assert negative_leading["leading_adjustment"] < 0.0
    assert abs(faster["phase_velocity_adjustment"]) <= (
        config.max_phase_velocity_fraction
    )
    assert abs(positive_acceleration["acceleration_adjustment"]) <= (
        config.max_acceleration_fraction
    )
    assert abs(longer_duration["duration_adjustment"]) <= config.max_duration_fraction
    assert abs(positive_leading["leading_adjustment"]) <= config.max_leading_fraction


@pytest.mark.parametrize(
    ("signal", "message"),
    [
        (
            _leading_signal(indicator_id="not_registered"),
            "indicator_id is not registered",
        ),
        (
            _leading_signal(
                cycle_id="C1",
                indicator_id="cn_m1",
            ),
            "not approved for the cycle",
        ),
        (
            _leading_signal(
                cycle_id="C5",
                indicator_id="cn_pmi_manufacturing",
            ),
            "coincident or lagging",
        ),
        (
            _leading_signal(direction_prior=-1.0),
            "direction_prior must match",
        ),
    ],
)
def test_unapproved_leading_signals_are_rejected(
    signal: pd.DataFrame,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _forecast_input(leading_signals=signal)


def test_future_visible_and_inactive_leading_signals_are_rejected() -> None:
    future = _leading_signal()
    future.loc[0, "visible_date"] = AS_OF + timedelta(days=1)
    with pytest.raises(ValueError, match="future-visible"):
        _forecast_input(leading_signals=future)

    registry = _registry()
    indicators = [
        indicator.model_copy(update={"active": False})
        if indicator.indicator_id == "cn_m1"
        else indicator
        for indicator in registry.indicators
    ]
    with pytest.raises(ValueError, match="active indicators"):
        _forecast_input(
            indicator_specs=indicators,
            leading_signals=_leading_signal(),
        )


def test_leading_indicator_without_registry_direction_prior_is_rejected() -> None:
    registry = _registry()
    indicator = next(
        indicator
        for indicator in registry.indicators
        if indicator.indicator_id == "global_crb_commodity"
    )
    assert indicator.active
    assert indicator.timing == "leading"
    assert "C5" in indicator.allowed_cycles
    assert indicator.direction_prior is None

    with pytest.raises(
        ValueError,
        match="leading signal indicators require an explicit direction prior",
    ):
        _forecast_input(
            leading_signals=_leading_signal(
                cycle_id="C5",
                indicator_id=indicator.indicator_id,
                direction_prior=1.0,
            )
        )


def test_insufficient_calibration_history_uses_audited_identity_fallback() -> None:
    history = _calibration_history(count=8)
    result = forecast_cycle_phases(
        _forecast_input(calibration_history=history),
        config=_config(min_calibration_samples=16),
    )

    row = result.summary.loc[
        result.summary["cycle_id"].eq("C5") & result.summary["horizon_months"].eq(3)
    ].iloc[0]
    assert row["calibration_method"] == "identity"
    assert row["calibration_version"] == "identity-v1"
    assert row["calibration_sample_count"] == 8
    assert row["calibration_reason"] == "insufficient_prior_folds"
    for phase in PHASES:
        assert row[f"{phase}_probability"] == pytest.approx(
            row[f"raw_{phase}_probability"]
        )


def test_walk_forward_logistic_calibration_changes_probabilities_only() -> None:
    history = _calibration_history(count=32)
    config = _config(
        draw_count=128,
        min_calibration_samples=16,
        min_calibration_class_count=3,
        calibration_method="logistic",
    )
    baseline = forecast_cycle_phases(_forecast_input(), config=config)
    calibrated = forecast_cycle_phases(
        _forecast_input(calibration_history=history),
        config=config,
    )

    pd.testing.assert_frame_equal(baseline.monthly_paths, calibrated.monthly_paths)
    target = calibrated.summary.loc[
        calibrated.summary["cycle_id"].eq("C5")
        & calibrated.summary["horizon_months"].eq(3)
    ].iloc[0]
    baseline_target = baseline.summary.loc[
        baseline.summary["cycle_id"].eq("C5") & baseline.summary["horizon_months"].eq(3)
    ].iloc[0]
    assert target["calibration_method"] == "walk_forward_logistic"
    assert target["calibration_version"] == "walk-forward-logistic-v1"
    assert target["calibration_sample_count"] == 32
    assert target["calibration_reason"] == "calibrated"
    calibrated_probabilities = np.asarray(
        [target[f"{phase}_probability"] for phase in PHASES]
    )
    raw_probabilities = np.asarray(
        [target[f"raw_{phase}_probability"] for phase in PHASES]
    )
    assert not np.allclose(calibrated_probabilities, raw_probabilities)
    np.testing.assert_allclose(calibrated_probabilities.sum(), 1.0)
    for column in (
        "angle_anchor_degrees",
        "angle_q10",
        "angle_q25",
        "angle_q50",
        "angle_q75",
        "angle_q90",
        "turning_probability",
        "forecast_uncertainty",
    ):
        assert target[column] == pytest.approx(baseline_target[column])

    untouched = calibrated.summary.loc[
        ~(
            calibrated.summary["cycle_id"].eq("C5")
            & calibrated.summary["horizon_months"].eq(3)
        )
    ]
    assert set(untouched["calibration_method"]) == {"identity"}


def test_walk_forward_isotonic_calibration_changes_probabilities_only() -> None:
    history = _calibration_history(count=32)
    config = _config(
        draw_count=128,
        min_calibration_samples=16,
        min_calibration_class_count=3,
        calibration_method="isotonic",
    )
    baseline = forecast_cycle_phases(_forecast_input(), config=config)
    calibrated = forecast_cycle_phases(
        _forecast_input(calibration_history=history),
        config=config,
    )

    pd.testing.assert_frame_equal(baseline.monthly_paths, calibrated.monthly_paths)
    target = calibrated.summary.loc[
        calibrated.summary["cycle_id"].eq("C5")
        & calibrated.summary["horizon_months"].eq(3)
    ].iloc[0]
    baseline_target = baseline.summary.loc[
        baseline.summary["cycle_id"].eq("C5") & baseline.summary["horizon_months"].eq(3)
    ].iloc[0]
    assert target["calibration_method"] == "walk_forward_isotonic"
    assert target["calibration_version"] == "walk-forward-isotonic-v1"
    assert target["calibration_sample_count"] == 32
    probabilities = np.asarray(
        [target[f"{phase}_probability"] for phase in PHASES],
        dtype="float64",
    )
    raw_probabilities = np.asarray(
        [target[f"raw_{phase}_probability"] for phase in PHASES],
        dtype="float64",
    )
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
    np.testing.assert_allclose(probabilities.sum(), 1.0)
    assert not np.allclose(probabilities, raw_probabilities)
    for phase in PHASES:
        assert target[f"raw_{phase}_probability"] == pytest.approx(
            baseline_target[f"raw_{phase}_probability"]
        )
    audit_columns = [
        "angle_anchor_degrees",
        "angle_q10",
        "angle_q25",
        "angle_q50",
        "angle_q75",
        "angle_q90",
        "turning_status",
        "turning_probability",
        "turning_start_month",
        "turning_end_month",
        "turning_median_month",
        "turning_start_date",
        "turning_end_date",
        "turning_median_date",
        "forecast_uncertainty",
    ]
    pd.testing.assert_series_equal(
        target.loc[audit_columns],
        baseline_target.loc[audit_columns],
        check_names=False,
    )


def test_future_calibration_outcomes_are_rejected() -> None:
    history = _calibration_history(count=1)
    history.loc[0, "forecast_origin"] = pd.Timestamp("2024-05-31")
    history.loc[0, "target_date"] = pd.Timestamp("2024-08-31")

    with pytest.raises(ValueError, match="future calibration outcomes"):
        _forecast_input(calibration_history=history)


def test_current_origin_calibration_fold_is_rejected_before_target_check() -> None:
    history = _calibration_history(count=1)
    forecast_origin = pd.Timestamp(AS_OF)
    horizon = int(history.loc[0, "horizon_months"])
    first_target = forecast_origin + pd.offsets.MonthEnd(1)
    history.loc[0, "forecast_origin"] = forecast_origin
    history.loc[0, "target_date"] = first_target + pd.offsets.MonthEnd(horizon - 1)

    with pytest.raises(
        ValueError,
        match="calibration folds must originate strictly before as_of",
    ):
        _forecast_input(calibration_history=history)


def test_overlapping_calibration_fold_ids_are_rejected() -> None:
    history = _calibration_history(count=2)
    history.loc[1, "fold_id"] = history.loc[0, "fold_id"]

    with pytest.raises(ValueError, match="overlapping calibration fold"):
        _forecast_input(calibration_history=history)


def test_calibration_uses_only_matching_cycle_horizon_prior_folds() -> None:
    matching = _calibration_history(count=20, cycle_id="C5", horizon=3)
    unrelated = _calibration_history(count=12, cycle_id="C4", horizon=3)
    result = forecast_cycle_phases(
        _forecast_input(
            calibration_history=pd.concat([matching, unrelated], ignore_index=True)
        ),
        config=_config(min_calibration_samples=16),
    )

    c5 = result.summary.loc[
        result.summary["cycle_id"].eq("C5") & result.summary["horizon_months"].eq(3)
    ].iloc[0]
    c4 = result.summary.loc[
        result.summary["cycle_id"].eq("C4") & result.summary["horizon_months"].eq(3)
    ].iloc[0]
    assert c5["calibration_sample_count"] == 20
    assert c4["calibration_sample_count"] == 12
    assert c5["calibration_method"] == "walk_forward_logistic"
    assert c4["calibration_method"] == "identity"


def test_same_cycle_wrong_horizon_history_is_isolated() -> None:
    matching = _calibration_history(count=20, cycle_id="C5", horizon=3)
    wrong_horizon = _calibration_history(count=24, cycle_id="C5", horizon=1)
    config = _config(min_calibration_samples=16)
    matching_result = forecast_cycle_phases(
        _forecast_input(calibration_history=matching),
        config=config,
    )
    mixed_result = forecast_cycle_phases(
        _forecast_input(
            calibration_history=pd.concat(
                [matching, wrong_horizon],
                ignore_index=True,
            )
        ),
        config=config,
    )

    matching_row = matching_result.summary.loc[
        matching_result.summary["cycle_id"].eq("C5")
        & matching_result.summary["horizon_months"].eq(3)
    ].iloc[0]
    mixed_row = mixed_result.summary.loc[
        mixed_result.summary["cycle_id"].eq("C5")
        & mixed_result.summary["horizon_months"].eq(3)
    ].iloc[0]
    assert matching_row["calibration_sample_count"] == 20
    assert mixed_row["calibration_sample_count"] == 20
    comparison_columns = [
        *[f"raw_{phase}_probability" for phase in PHASES],
        *[f"{phase}_probability" for phase in PHASES],
        "calibration_method",
        "calibration_version",
        "calibration_sample_count",
        "calibration_reason",
    ]
    pd.testing.assert_series_equal(
        matching_row.loc[comparison_columns],
        mixed_row.loc[comparison_columns],
        check_names=False,
    )


def test_calibration_history_shuffle_does_not_change_forecast() -> None:
    history = pd.concat(
        [
            _calibration_history(count=20, cycle_id="C5", horizon=1),
            _calibration_history(count=12, cycle_id="C4", horizon=3),
        ],
        ignore_index=True,
    )
    shuffled = history.sample(frac=1.0, random_state=17)
    config = _config(min_calibration_samples=16)

    ordered_result = forecast_cycle_phases(
        _forecast_input(calibration_history=history),
        config=config,
    )
    shuffled_result = forecast_cycle_phases(
        _forecast_input(calibration_history=shuffled),
        config=config,
    )

    pd.testing.assert_frame_equal(ordered_result.summary, shuffled_result.summary)
    pd.testing.assert_frame_equal(
        ordered_result.monthly_paths,
        shuffled_result.monthly_paths,
    )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda frame: _replace_state(
                frame,
                "C5",
                covariance_00=0.01,
                covariance_01=0.10,
                covariance_11=0.01,
            ),
            "positive semidefinite",
        ),
        (
            lambda frame: _replace_state(frame, "C5", level=np.inf),
            "finite real number",
        ),
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "duplicate cycle_id",
        ),
    ],
)
def test_invalid_state_covariance_values_and_duplicates_are_rejected(
    mutator,
    message: str,
) -> None:
    registry = _registry()
    with pytest.raises(ValueError, match=message):
        _forecast_input(states=mutator(_state_rows(registry.cycles)))


def test_incomplete_registry_and_missing_covariance_contract_are_rejected() -> None:
    registry = _registry()
    with pytest.raises(ValueError, match="exactly C1 through C7"):
        _forecast_input(cycle_specs=registry.cycles[:-1])

    states = _state_rows(registry.cycles).drop(columns="covariance_11")
    with pytest.raises(ValueError, match="columns do not match"):
        _forecast_input(states=states)


def test_result_rejects_missing_or_duplicate_cycle_horizon_rows() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    for forged in (
        result.summary.iloc[1:].reset_index(drop=True),
        pd.concat([result.summary, result.summary.iloc[[0]]], ignore_index=True),
    ):
        with pytest.raises(ValueError, match="inconsistent"):
            CycleForecastResult(
                summary=forged,
                monthly_paths=result.monthly_paths,
                forecast_input=result.forecast_input,
                config=result.config,
            )


def test_result_rejects_forged_monthly_path_dates() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    forged_paths = result.monthly_paths
    forged_paths.loc[0, "date"] = forged_paths.loc[0, "date"] + pd.offsets.MonthEnd(1)

    with pytest.raises(ValueError, match="monthly path date"):
        CycleForecastResult(
            summary=result.summary,
            monthly_paths=forged_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )


def test_result_revalidates_retained_path_state_geometry() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    forged_paths = result.monthly_paths
    row_index = forged_paths.index[
        forged_paths["cycle_id"].eq("C1")
        & forged_paths["draw_id"].eq(0)
        & forged_paths["month_number"].eq(2)
    ].item()
    forged_paths.loc[row_index, "angle_degrees"] += 10.0

    with pytest.raises(ValueError, match="angle_degrees must align"):
        CycleForecastResult(
            summary=result.summary,
            monthly_paths=forged_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )


@pytest.mark.parametrize(
    "forgery",
    ["slope", "effective_velocity", "coherent_state_scale"],
)
def test_result_rejects_deterministic_monthly_path_forgeries(forgery: str) -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    forged_paths = result.monthly_paths
    row_index = forged_paths.index[
        forged_paths["cycle_id"].eq("C5")
        & forged_paths["draw_id"].eq(0)
        & forged_paths["month_number"].eq(2)
    ].item()
    if forgery == "slope":
        forged_paths.loc[row_index, "slope"] *= 1.01
    elif forgery == "effective_velocity":
        forged_paths.loc[row_index, "effective_phase_velocity"] *= 1.01
    else:
        forged_paths.loc[row_index, ["level", "quadrature", "slope"]] *= 1.10

    with pytest.raises(ValueError, match="deterministic replay"):
        CycleForecastResult(
            summary=result.summary,
            monthly_paths=forged_paths,
            forecast_input=result.forecast_input,
            config=result.config,
        )


def test_output_carries_champion_and_registry_model_config_provenance() -> None:
    result = forecast_cycle_phases(_forecast_input(), config=_config())
    summary = result.summary

    assert set(summary["model_role"]) == {"champion"}
    assert set(summary["forecast_model_version"]) == {"cycle-champion-v1"}
    for column in ("forecast_config_hash", "registry_hash", "state_config_hash"):
        assert summary[column].str.fullmatch(r"[0-9a-f]{64}").all()
    assert set(summary["state_model_version"]) == {"cycle-state-v1"}
    assert (summary["data_vintage"] <= summary["as_of"]).all()
