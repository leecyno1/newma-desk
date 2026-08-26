from dataclasses import FrozenInstanceError
from datetime import date
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.forecast.cycles import (
    CALIBRATION_HISTORY_COLUMNS,
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
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _api():
    return import_module("seven_cycle_platform.forecast.channels")


def _registry():
    return load_registry_bundle(PROJECT_ROOT / "config" / "seven_cycle")


def _forecast_date(origin: object, horizon: int) -> pd.Timestamp:
    return pd.Timestamp(origin).normalize() + pd.offsets.MonthEnd(horizon)


def _cycle_state_rows(cycle_specs, *, as_of: date = AS_OF) -> pd.DataFrame:
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
                "as_of": as_of,
                "state_date": as_of,
                "visible_date": as_of,
                "data_vintage": as_of,
                "cycle_id": cycle.cycle_id,
                "status": "available",
                "unavailable_reason": None,
                "level": 0.55 - 0.05 * position,
                "quadrature": 0.15 + 0.025 * position,
                "covariance_00": 0.025,
                "covariance_01": 0.003,
                "covariance_11": 0.020,
                "phase_velocity": 2.0 * np.pi / period_months,
                "acceleration": 0.0,
                "phase_duration_months": 3.0,
                "confidence": 0.85,
                "center_period": center_period,
                "state_model_version": "cycle-state-v1",
                "state_config_hash": HASH_A,
            }
        )
    return pd.DataFrame(rows, columns=CYCLE_STATE_COLUMNS)


def _cycle_forecast(
    *,
    as_of: date = AS_OF,
    draw_count: int = 24,
    seed: int = 17,
) -> CycleForecastResult:
    registry = _registry()
    forecast_input = CycleForecastInput(
        as_of=as_of,
        cycle_specs=registry.cycles,
        indicator_specs=registry.indicators,
        states=_cycle_state_rows(registry.cycles, as_of=as_of),
        leading_signals=pd.DataFrame(columns=LEADING_SIGNAL_COLUMNS),
        calibration_history=pd.DataFrame(columns=CALIBRATION_HISTORY_COLUMNS),
    )
    return forecast_cycle_phases(
        forecast_input,
        config=CycleForecastConfig(draw_count=draw_count, seed=seed),
    )


def _origin_state(origin_number: int, channel_number: int) -> float:
    return float(
        0.35 * np.sin(0.31 * origin_number + 0.17 * channel_number)
        + 0.04 * channel_number
    )


def _cycle_value(
    origin_number: int,
    horizon: int,
    cycle_number: int,
) -> tuple[float, float]:
    angle = 0.23 * (origin_number + horizon) + 0.29 * cycle_number
    return float(np.sin(angle)), float(0.23 * np.cos(angle))


def _exogenous_value(origin_number: int, horizon: int) -> float:
    return float(np.cos(0.19 * (origin_number + horizon)))


def _target_state(
    *,
    origin_number: int,
    channel_number: int,
    horizon: int,
    target_mode: str,
) -> float:
    origin_state = _origin_state(origin_number, channel_number)
    if target_mode == "persistence":
        return origin_state
    cycle_level, cycle_slope = _cycle_value(origin_number, horizon, 3)
    exogenous = _exogenous_value(origin_number, horizon)
    noise = 0.01 * np.sin(0.71 * origin_number + channel_number)
    return float(
        0.28 * origin_state
        + 1.35 * cycle_level
        - 0.75 * cycle_slope
        + 0.80 * exogenous
        + 0.03 * channel_number
        + noise
    )


def _historical_frames(
    api,
    *,
    horizons: tuple[int, ...],
    periods: int,
    target_mode: str,
    exogenous_feature_ids: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    registry = _registry()
    origins = pd.date_range("2020-01-31", periods=periods, freq="ME")
    channel_rows = []
    cycle_rows = []
    exogenous_rows = []
    for origin_number, origin in enumerate(origins):
        for horizon in horizons:
            target_date = _forecast_date(origin, horizon)
            target_visible_date = target_date + pd.Timedelta(days=8)
            revision_window_end = target_date + pd.Timedelta(days=25)
            if target_visible_date <= pd.Timestamp(AS_OF):
                data_vintage = min(revision_window_end, pd.Timestamp(AS_OF))
                for channel_number, channel in enumerate(registry.channels):
                    origin_state = _origin_state(origin_number, channel_number)
                    target_state = _target_state(
                        origin_number=origin_number,
                        channel_number=channel_number,
                        horizon=horizon,
                        target_mode=target_mode,
                    )
                    channel_rows.append(
                        {
                            "forecast_origin": origin,
                            "origin_state_date": origin,
                            "origin_visible_date": origin,
                            "target_date": target_date,
                            "target_visible_date": target_visible_date,
                            "target_revision_window_end": revision_window_end,
                            "channel_id": channel.channel_id,
                            "horizon_months": horizon,
                            "origin_state": origin_state,
                            "origin_innovation": origin_state
                            - _origin_state(
                                max(origin_number - 1, 0),
                                channel_number,
                            ),
                            "origin_uncertainty": 0.12,
                            "origin_status": "available",
                            "origin_status_reason": None,
                            "target_state": target_state,
                            "target_innovation": target_state - origin_state,
                            "target_uncertainty": 0.10,
                            "target_status": "available",
                            "target_status_reason": None,
                            "data_vintage": data_vintage,
                        }
                    )
            for cycle_number, cycle in enumerate(registry.cycles, start=1):
                if horizon > max(cycle.horizons):
                    continue
                level, slope = _cycle_value(
                    origin_number,
                    horizon,
                    cycle_number,
                )
                for draw_id, draw_shift in enumerate((-0.02, 0.0, 0.02)):
                    cycle_rows.append(
                        {
                            "forecast_origin": origin,
                            "date": target_date,
                            "visible_date": origin,
                            "generated_date": origin,
                            "cycle_id": cycle.cycle_id,
                            "draw_id": draw_id,
                            "horizon_months": horizon,
                            "level": level + draw_shift,
                            "slope": slope + draw_shift / 4.0,
                            "predictor_kind": "forecast",
                            "forecast_model_version": "cycle-archive-v1",
                            "forecast_config_hash": HASH_B,
                            "registry_hash": HASH_C,
                            "data_vintage": origin,
                        }
                    )
            for feature_id in exogenous_feature_ids:
                exogenous_rows.append(
                    {
                        "forecast_origin": origin,
                        "date": target_date,
                        "visible_date": origin,
                        "generated_date": origin,
                        "feature_id": feature_id,
                        "draw_id": 0,
                        "horizon_months": horizon,
                        "value": _exogenous_value(origin_number, horizon),
                        "is_deterministic": True,
                        "path_kind": "forecast",
                    }
                )
    return (
        pd.DataFrame(channel_rows, columns=api.CHANNEL_HISTORY_COLUMNS),
        pd.DataFrame(cycle_rows, columns=api.CYCLE_PREDICTOR_ARCHIVE_COLUMNS),
        pd.DataFrame(
            exogenous_rows,
            columns=api.EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
        ),
        origins,
    )


def _current_channel_states(api, *, origins: pd.DatetimeIndex) -> pd.DataFrame:
    registry = _registry()
    rows = []
    for channel_number, channel in enumerate(registry.channels):
        state = _origin_state(len(origins), channel_number)
        rows.append(
            {
                "as_of": AS_OF,
                "state_date": AS_OF,
                "visible_date": AS_OF,
                "revision_window_end": AS_OF,
                "channel_id": channel.channel_id,
                "state": state,
                "innovation": state
                - _origin_state(max(len(origins) - 1, 0), channel_number),
                "uncertainty": 0.14,
                "status": "available",
                "status_reason": None,
                "data_vintage": AS_OF,
            }
        )
    return pd.DataFrame(rows, columns=api.CURRENT_CHANNEL_STATE_COLUMNS)


def _current_exogenous_paths(
    api,
    *,
    horizons: tuple[int, ...],
    draw_count: int,
    origin_number: int,
    exogenous_feature_ids: tuple[str, ...],
) -> pd.DataFrame:
    rows = []
    for horizon in horizons:
        target_date = _forecast_date(AS_OF, horizon)
        for feature_id in exogenous_feature_ids:
            for draw_id in range(draw_count):
                rows.append(
                    {
                        "forecast_origin": AS_OF,
                        "date": target_date,
                        "visible_date": AS_OF,
                        "generated_date": AS_OF,
                        "feature_id": feature_id,
                        "draw_id": draw_id,
                        "horizon_months": horizon,
                        "value": _exogenous_value(origin_number, horizon)
                        + 0.015 * (draw_id - (draw_count - 1) / 2.0),
                        "is_deterministic": False,
                        "path_kind": "forecast",
                    }
                )
    return pd.DataFrame(rows, columns=api.CURRENT_EXOGENOUS_PATH_COLUMNS)


def _forecast_input(
    api,
    *,
    horizons: tuple[int, ...] = (1,),
    periods: int = 40,
    draw_count: int = 24,
    target_mode: str = "arx",
    exogenous_feature_ids: tuple[str, ...] = ("policy_impulse",),
):
    registry = _registry()
    channel_history, cycle_archive, exogenous_archive, origins = _historical_frames(
        api,
        horizons=horizons,
        periods=periods,
        target_mode=target_mode,
        exogenous_feature_ids=exogenous_feature_ids,
    )
    return api.ChannelForecastInput(
        as_of=AS_OF,
        channel_specs=registry.channels,
        cycle_forecast=_cycle_forecast(draw_count=draw_count),
        channel_history=channel_history,
        cycle_predictor_archive=cycle_archive,
        exogenous_forecast_archive=exogenous_archive,
        current_channel_states=_current_channel_states(api, origins=origins),
        current_exogenous_paths=_current_exogenous_paths(
            api,
            horizons=horizons,
            draw_count=draw_count,
            origin_number=len(origins),
            exogenous_feature_ids=exogenous_feature_ids,
        ),
        exogenous_feature_ids=exogenous_feature_ids,
    )


def _rebuild_input(api, source, **overrides):
    values = {
        "as_of": source.as_of,
        "channel_specs": source.channel_specs,
        "cycle_forecast": source.cycle_forecast,
        "channel_history": source.channel_history,
        "cycle_predictor_archive": source.cycle_predictor_archive,
        "exogenous_forecast_archive": source.exogenous_forecast_archive,
        "current_channel_states": source.current_channel_states,
        "current_exogenous_paths": source.current_exogenous_paths,
        "exogenous_feature_ids": source.exogenous_feature_ids,
        **overrides,
    }
    return api.ChannelForecastInput(**values)


def _config(api, *, horizons: tuple[int, ...] = (1,), **overrides):
    values = {
        "horizons": horizons,
        "alpha_grid": (0.05, 0.5, 5.0),
        "min_training_count": 8,
        "alpha_validation_window": 6,
        "embargo_days": 3,
        "covariance_min_samples": 4,
        "covariance_shrinkage": 0.15,
        "seed": 29,
        **overrides,
    }
    return api.ChannelForecastConfig(**values)


def test_task_25_module_and_public_contract_exist() -> None:
    api = _api()

    assert api.CHANNEL_HISTORY_COLUMNS
    assert api.CYCLE_PREDICTOR_ARCHIVE_COLUMNS
    assert api.EXOGENOUS_FORECAST_ARCHIVE_COLUMNS
    assert api.CURRENT_CHANNEL_STATE_COLUMNS
    assert api.CURRENT_EXOGENOUS_PATH_COLUMNS
    assert api.CHANNEL_FORECAST_SUMMARY_COLUMNS
    assert api.CHANNEL_FORECAST_DRAW_COLUMNS
    assert api.CHANNEL_FORECAST_COVARIANCE_COLUMNS
    assert api.CHANNEL_FORECAST_EVALUATION_COLUMNS
    assert api.ChannelForecastConfig
    assert api.ChannelForecastInput
    assert api.ChannelForecastResult
    assert api.forecast_transmission_channels


def test_synthetic_walk_forward_champion_beats_both_baselines() -> None:
    api = _api()
    forecast_input = _forecast_input(api, periods=44, target_mode="arx")
    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(api),
    )
    available = result.evaluation.loc[result.evaluation["status"].eq("available")]

    losses = available[
        ["champion_loss", "historical_mean_loss", "persistence_loss"]
    ].mean()
    assert losses["champion_loss"] < losses["historical_mean_loss"]
    assert losses["champion_loss"] < losses["persistence_loss"]
    assert set(result.summary["selected_model"]) == {"champion"}
    assert (
        available[["champion_loss", "historical_mean_loss", "persistence_loss"]]
        .notna()
        .all()
        .all()
    )


def test_no_incremental_signal_selects_persistence_without_hiding_losses() -> None:
    api = _api()
    forecast_input = _forecast_input(api, periods=34, target_mode="persistence")
    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(api),
    )
    available = result.evaluation.loc[result.evaluation["status"].eq("available")]

    assert set(result.summary["selected_model"]) == {"persistence"}
    assert np.allclose(available["persistence_loss"], 0.0)
    assert (
        available[["champion_loss", "historical_mean_loss", "persistence_loss"]]
        .notna()
        .all()
        .all()
    )
    persistence_residual_variance = (
        available.assign(
            selected_residual=(
                available["realized_state"] - available["persistence_prediction"]
            )
        )
        .groupby("channel_id")["selected_residual"]
        .var(ddof=1)
        .sort_index()
    )
    covariance_diagonal = (
        result.covariance.loc[
            result.covariance["channel_i"].eq(result.covariance["channel_j"])
        ]
        .set_index("channel_i")["covariance"]
        .sort_index()
    )
    assert np.allclose(covariance_diagonal, persistence_residual_variance)
    assert set(result.covariance["method"]) == {"shrunk_oos_selected_model_residual"}
    assert set(result.covariance["status"]) == {"estimated"}


def test_embargo_excludes_equal_boundary_and_allows_strictly_earlier_rows() -> None:
    api = _api()
    base = _forecast_input(api, periods=30)
    validation_origin = pd.Timestamp("2021-12-31")
    candidate_origin = pd.Timestamp("2021-10-31")
    cutoff = validation_origin - pd.Timedelta(days=5)
    history = base.channel_history
    candidate = history["forecast_origin"].eq(candidate_origin)
    history.loc[candidate, "target_visible_date"] = cutoff - pd.Timedelta(days=1)
    history.loc[candidate, "target_revision_window_end"] = cutoff
    history.loc[candidate, "data_vintage"] = cutoff - pd.Timedelta(days=1)
    excluded_input = _rebuild_input(api, base, channel_history=history)
    included_history = history.copy(deep=True)
    included_history.loc[candidate, "target_revision_window_end"] = (
        cutoff - pd.Timedelta(days=1)
    )
    included_input = _rebuild_input(
        api,
        base,
        channel_history=included_history,
    )
    config = _config(api, embargo_days=5, min_training_count=4)

    excluded = api.forecast_transmission_channels(excluded_input, config=config)
    included = api.forecast_transmission_channels(included_input, config=config)
    channel_id = _registry().channels[0].channel_id
    excluded_fold = excluded.evaluation.loc[
        excluded.evaluation["validation_origin"].eq(validation_origin)
        & excluded.evaluation["channel_id"].eq(channel_id)
    ].iloc[0]
    included_fold = included.evaluation.loc[
        included.evaluation["validation_origin"].eq(validation_origin)
        & included.evaluation["channel_id"].eq(channel_id)
    ].iloc[0]

    assert excluded_fold["embargo_cutoff"] == cutoff
    assert excluded_fold["training_end"] < candidate_origin
    assert included_fold["training_end"] == candidate_origin
    assert included_fold["training_count"] == excluded_fold["training_count"] + 1


def test_open_revision_window_targets_do_not_change_current_result() -> None:
    api = _api()
    base = _forecast_input(api, periods=53)
    provisional = base.channel_history
    latest_origin = provisional["forecast_origin"].max()
    open_revision = provisional["forecast_origin"].eq(latest_origin)
    provisional.loc[open_revision, "target_revision_window_end"] = pd.Timestamp(
        AS_OF
    ) + pd.Timedelta(days=10)
    provisional.loc[open_revision, "data_vintage"] = pd.Timestamp(AS_OF)
    reference_input = _rebuild_input(api, base, channel_history=provisional)
    contaminated = provisional.copy(deep=True)
    contaminated.loc[open_revision, "target_state"] = 1_000_000.0
    contaminated.loc[open_revision, "target_innovation"] = -1_000_000.0
    contaminated_input = _rebuild_input(
        api,
        base,
        channel_history=contaminated,
    )
    config = _config(api)

    reference = api.forecast_transmission_channels(reference_input, config=config)
    result = api.forecast_transmission_channels(contaminated_input, config=config)

    pd.testing.assert_frame_equal(result.summary, reference.summary)
    pd.testing.assert_frame_equal(result.draws, reference.draws)
    pd.testing.assert_frame_equal(result.covariance, reference.covariance)
    pd.testing.assert_frame_equal(result.evaluation, reference.evaluation)


@pytest.mark.parametrize(
    ("frame_name", "column", "bad_value", "message"),
    [
        (
            "cycle_predictor_archive",
            "predictor_kind",
            "actual",
            "forecast predictors",
        ),
        (
            "cycle_predictor_archive",
            "visible_date",
            pd.Timestamp("2030-01-01"),
            "visible",
        ),
        (
            "exogenous_forecast_archive",
            "path_kind",
            "actual",
            "forecast",
        ),
        (
            "exogenous_forecast_archive",
            "path_kind",
            "scenario",
            "forecast",
        ),
        (
            "exogenous_forecast_archive",
            "generated_date",
            pd.Timestamp("2030-01-01"),
            "generated",
        ),
    ],
)
def test_historical_predictor_archives_reject_actual_or_future_visible_values(
    frame_name: str,
    column: str,
    bad_value: object,
    message: str,
) -> None:
    api = _api()
    base = _forecast_input(api, periods=16)
    frame = getattr(base, frame_name)
    frame.loc[0, column] = bad_value

    with pytest.raises(ValueError, match=message):
        _rebuild_input(api, base, **{frame_name: frame})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("future_vintage", "data_vintage cannot follow as_of"),
        (
            "after_revision_window",
            "data_vintage cannot follow target_revision_window_end",
        ),
    ],
)
def test_target_label_vintage_must_be_current_and_inside_revision_window(
    mutation: str,
    message: str,
) -> None:
    api = _api()
    base = _forecast_input(api, periods=16)
    history = base.channel_history
    if mutation == "future_vintage":
        history.loc[0, "target_revision_window_end"] = pd.Timestamp(
            AS_OF
        ) + pd.Timedelta(days=10)
        history.loc[0, "data_vintage"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=1)
    else:
        history.loc[0, "data_vintage"] = history.loc[
            0, "target_revision_window_end"
        ] + pd.Timedelta(days=1)

    with pytest.raises(ValueError, match=message):
        _rebuild_input(api, base, channel_history=history)


def test_current_exogenous_scenarios_are_rejected() -> None:
    api = _api()
    base = _forecast_input(api, periods=16)
    paths = base.current_exogenous_paths
    paths.loc[0, "path_kind"] = "scenario"

    with pytest.raises(ValueError, match="forecast"):
        _rebuild_input(api, base, current_exogenous_paths=paths)


def test_channel_forecast_requires_at_least_two_cycle_draws() -> None:
    api = _api()

    with pytest.raises(ValueError, match="at least 2"):
        _forecast_input(api, periods=16, draw_count=1)


def test_current_cycle_result_is_rebuilt_and_forged_paths_are_rejected() -> None:
    api = _api()
    base = _forecast_input(api, periods=16)
    forged_cycle = base.cycle_forecast
    raw_paths = object.__getattribute__(forged_cycle, "monthly_paths")
    raw_paths.loc[0, "level"] += 10.0

    with pytest.raises(ValueError, match="deterministic replay"):
        _rebuild_input(api, base, cycle_forecast=forged_cycle)


def test_current_cycle_origin_must_equal_channel_forecast_as_of() -> None:
    api = _api()
    base = _forecast_input(api, periods=16)

    with pytest.raises(ValueError, match="cycle forecast as_of"):
        _rebuild_input(api, base, as_of=date(2024, 5, 31))


def test_dynamic_cycle_support_never_extrapolates_short_cycles() -> None:
    api = _api()
    horizons = (1, 4, 7, 12)
    forecast_input = _forecast_input(api, horizons=horizons, periods=34)
    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(api, horizons=horizons),
    )
    first_channel = _registry().channels[0].channel_id
    summary = result.summary.loc[result.summary["channel_id"].eq(first_channel)]
    rows = summary.set_index("horizon_months")

    assert rows.at[1, "active_cycle_ids"] == (
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    )
    assert rows.at[4, "missing_cycle_ids"] == ("C7",)
    assert rows.at[7, "active_cycle_ids"] == ("C1", "C2", "C3", "C4", "C6")
    assert rows.at[12, "active_cycle_ids"] == ("C1", "C2", "C3", "C4", "C6")
    assert "cycle:C7:level" not in rows.at[4, "feature_labels"]
    assert "cycle:C5:slope" not in rows.at[7, "feature_labels"]
    assert (
        rows.at[7, "support_uncertainty_multiplier"]
        > rows.at[4, "support_uncertainty_multiplier"]
    )


@pytest.fixture(scope="module")
def joint_bundle():
    api = _api()
    horizons = (1, 4)
    forecast_input = _forecast_input(
        api,
        horizons=horizons,
        periods=38,
        draw_count=24,
    )
    config = _config(api, horizons=horizons)
    result = api.forecast_transmission_channels(forecast_input, config=config)
    return api, forecast_input, config, result


def test_joint_draws_align_ids_quantiles_and_full_covariance(joint_bundle) -> None:
    _, forecast_input, config, result = joint_bundle
    channel_ids = tuple(
        sorted(channel.channel_id for channel in forecast_input.channel_specs)
    )
    draw_ids = set(range(forecast_input.cycle_forecast.config.draw_count))

    assert len(result.summary) == len(channel_ids) * len(config.horizons)
    assert len(result.draws) == len(channel_ids) * len(config.horizons) * len(draw_ids)
    for _, group in result.draws.groupby(["channel_id", "horizon_months"]):
        assert set(group["draw_id"]) == draw_ids
        assert np.array_equal(group["draw_id"], group["cycle_draw_id"])
        summary_row = result.summary.loc[
            result.summary["channel_id"].eq(group.iloc[0]["channel_id"])
            & result.summary["horizon_months"].eq(group.iloc[0]["horizon_months"])
        ].iloc[0]
        assert np.isclose(
            summary_row["forecast_std"],
            group["forecast_state"].std(ddof=1),
        )
    quantiles = result.summary[["q10", "q25", "q50", "q75", "q90"]]
    assert (np.diff(quantiles.to_numpy(dtype="float64"), axis=1) >= 0.0).all()
    assert result.summary["probability_positive"].between(0.0, 1.0).all()
    assert np.allclose(
        result.summary["probability_positive"] + result.summary["probability_negative"],
        1.0,
    )

    for horizon in config.horizons:
        retained = result.draws.loc[result.draws["horizon_months"].eq(horizon)].pivot(
            index="draw_id", columns="channel_id", values="residual"
        )
        retained = retained.loc[:, channel_ids]
        empirical = np.cov(retained.to_numpy(dtype="float64"), rowvar=False, ddof=1)
        covariance = result.covariance.loc[
            result.covariance["horizon_months"].eq(horizon)
        ].pivot(index="channel_i", columns="channel_j", values="covariance")
        covariance = covariance.loc[channel_ids, channel_ids]
        matrix = covariance.to_numpy(dtype="float64")
        assert matrix.shape == (len(channel_ids), len(channel_ids))
        assert np.allclose(matrix, matrix.T, atol=1e-12, rtol=1e-12)
        assert np.linalg.eigvalsh(matrix).min() >= -1e-10
        assert np.allclose(matrix, empirical, atol=1e-10, rtol=1e-10)
        assert set(
            result.covariance.loc[
                result.covariance["horizon_months"].eq(horizon),
                "method",
            ]
        ) == {"shrunk_oos_selected_model_residual"}
    pd.testing.assert_frame_equal(result.covariance, result.residual_covariance)


def test_single_channel_residual_covariance_is_auditable() -> None:
    api = _api()
    base = _forecast_input(api, periods=38, draw_count=24)
    channel_spec = base.channel_specs[0]
    channel_id = channel_spec.channel_id
    forecast_input = _rebuild_input(
        api,
        base,
        channel_specs=(channel_spec,),
        channel_history=base.channel_history.loc[
            base.channel_history["channel_id"].eq(channel_id)
        ].reset_index(drop=True),
        current_channel_states=base.current_channel_states.loc[
            base.current_channel_states["channel_id"].eq(channel_id)
        ].reset_index(drop=True),
    )

    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(api),
    )

    assert len(result.covariance) == 1
    assert result.covariance.loc[0, "channel_i"] == channel_id
    assert result.covariance.loc[0, "channel_j"] == channel_id
    assert np.isclose(
        result.covariance.loc[0, "covariance"],
        result.draws["residual"].var(ddof=1),
    )
    assert result.covariance.loc[0, "status"] == "estimated"


def test_unavailable_current_channel_does_not_publish_forged_covariance() -> None:
    api = _api()
    base = _forecast_input(api, periods=38, draw_count=24)
    states = base.current_channel_states
    unavailable_channel = states.loc[0, "channel_id"]
    states.loc[0, ["state", "innovation", "uncertainty"]] = np.nan
    states.loc[0, "status"] = "unavailable"
    states.loc[0, "status_reason"] = "current_state_unavailable"
    forecast_input = _rebuild_input(api, base, current_channel_states=states)

    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(api),
    )

    unavailable_draws = result.draws.loc[
        result.draws["channel_id"].eq(unavailable_channel)
    ]
    assert unavailable_draws["forecast_state"].isna().all()
    assert unavailable_draws["residual"].isna().all()

    unavailable_covariance = result.covariance.loc[
        result.covariance["channel_i"].eq(unavailable_channel)
        | result.covariance["channel_j"].eq(unavailable_channel)
    ]
    assert unavailable_covariance["covariance"].isna().all()
    assert unavailable_covariance["correlation"].isna().all()
    assert set(unavailable_covariance["status"]) == {"unavailable"}
    assert set(unavailable_covariance["method"]) == {"not_estimated"}
    assert set(unavailable_covariance["sample_count"]) == {0}
    assert set(unavailable_covariance["fallback_reason"]) == {
        "current_channel_unavailable"
    }

    available_channels = tuple(
        channel_id
        for channel_id in sorted(result.draws["channel_id"].unique())
        if channel_id != unavailable_channel
    )
    retained = result.draws.loc[
        result.draws["channel_id"].isin(available_channels)
    ].pivot(index="draw_id", columns="channel_id", values="residual")
    retained = retained.loc[:, available_channels]
    empirical = np.cov(retained.to_numpy(dtype="float64"), rowvar=False, ddof=1)
    published = result.covariance.loc[
        result.covariance["channel_i"].isin(available_channels)
        & result.covariance["channel_j"].isin(available_channels)
    ].pivot(index="channel_i", columns="channel_j", values="covariance")
    published = published.loc[available_channels, available_channels]
    matrix = published.to_numpy(dtype="float64")
    assert np.isfinite(matrix).all()
    assert np.linalg.eigvalsh(matrix).min() >= -1e-10
    assert np.allclose(matrix, empirical, atol=1e-10, rtol=1e-10)
    available_covariance = result.covariance.loc[
        result.covariance["channel_i"].isin(available_channels)
        & result.covariance["channel_j"].isin(available_channels)
    ]
    assert set(available_covariance["status"]) == {"estimated"}
    assert available_covariance["fallback_reason"].isna().all()

    unavailable_summary = result.summary.loc[
        result.summary["channel_id"].eq(unavailable_channel)
    ].iloc[0]
    assert unavailable_summary["covariance_status"] == "unavailable"
    assert unavailable_summary["covariance_method"] == "not_estimated"
    assert unavailable_summary["covariance_sample_count"] == 0


def test_insufficient_residual_samples_use_explicit_fallback() -> None:
    api = _api()
    forecast_input = _forecast_input(api, periods=13, draw_count=16)
    result = api.forecast_transmission_channels(
        forecast_input,
        config=_config(
            api,
            min_training_count=5,
            covariance_min_samples=50,
        ),
    )

    assert set(result.covariance["status"]) == {"fallback"}
    assert set(result.covariance["method"]) == {"diagonal_fallback"}
    assert result.covariance["fallback_reason"].str.contains("insufficient").all()


def test_joint_residual_draws_handle_rank_deficient_sample_without_warnings() -> None:
    api = _api()
    covariance = np.eye(4, dtype="float64")

    with np.errstate(divide="raise", invalid="raise"):
        draws = api._joint_residual_draws(
            covariance,
            draw_count=2,
            seed=17,
            horizon=3,
        )

    assert draws.shape == (2, 4)
    assert np.isfinite(draws).all()


def test_input_shuffle_repeat_and_inputs_are_deterministic_and_unchanged() -> None:
    api = _api()
    base = _forecast_input(api, periods=24, draw_count=12)
    original_history = base.channel_history
    shuffled = api.ChannelForecastInput(
        as_of=base.as_of,
        channel_specs=tuple(reversed(base.channel_specs)),
        cycle_forecast=base.cycle_forecast,
        channel_history=base.channel_history.sample(frac=1.0, random_state=1),
        cycle_predictor_archive=base.cycle_predictor_archive.sample(
            frac=1.0,
            random_state=2,
        ),
        exogenous_forecast_archive=base.exogenous_forecast_archive.sample(
            frac=1.0,
            random_state=3,
        ),
        current_channel_states=base.current_channel_states.sample(
            frac=1.0,
            random_state=4,
        ),
        current_exogenous_paths=base.current_exogenous_paths.sample(
            frac=1.0,
            random_state=5,
        ),
        exogenous_feature_ids=tuple(reversed(base.exogenous_feature_ids)),
    )
    config = _config(api)

    first = api.forecast_transmission_channels(base, config=config)
    repeated = api.forecast_transmission_channels(base, config=config)
    reordered = api.forecast_transmission_channels(shuffled, config=config)

    pd.testing.assert_frame_equal(base.channel_history, original_history)
    for field in ("summary", "draws", "covariance", "evaluation"):
        pd.testing.assert_frame_equal(getattr(first, field), getattr(repeated, field))
        pd.testing.assert_frame_equal(getattr(first, field), getattr(reordered, field))


def test_result_is_defensive_and_config_is_frozen(joint_bundle) -> None:
    _, _, _, result = joint_bundle
    originals = {
        field: getattr(result, field)
        for field in ("summary", "draws", "covariance", "evaluation")
    }
    detached_summary = result.summary
    detached_draws = result.draws
    detached_covariance = result.covariance
    detached_evaluation = result.evaluation
    detached_summary.loc[0, "forecast_mean"] = 999.0
    detached_draws.loc[0, "forecast_state"] = 999.0
    detached_covariance.loc[0, "covariance"] = 999.0
    detached_evaluation.loc[0, "champion_loss"] = 999.0

    for field, original in originals.items():
        pd.testing.assert_frame_equal(getattr(result, field), original)
    with pytest.raises(FrozenInstanceError):
        result.config.seed = 3


@pytest.mark.parametrize("field", ["summary", "draws", "covariance", "evaluation"])
def test_result_rejects_forged_retained_outputs(joint_bundle, field: str) -> None:
    api, forecast_input, config, result = joint_bundle
    frames = {
        name: getattr(result, name)
        for name in ("summary", "draws", "covariance", "evaluation")
    }
    numeric_column = {
        "summary": "forecast_mean",
        "draws": "forecast_state",
        "covariance": "covariance",
        "evaluation": "champion_loss",
    }[field]
    available = frames[field][numeric_column].notna()
    row_index = frames[field].index[available][0]
    frames[field].loc[row_index, numeric_column] += 1.0

    with pytest.raises(ValueError, match="inconsistent"):
        api.ChannelForecastResult(
            summary=frames["summary"],
            draws=frames["draws"],
            covariance=frames["covariance"],
            evaluation=frames["evaluation"],
            forecast_input=forecast_input,
            config=config,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("nonfinite_state", "finite"),
        ("duplicate_history", "duplicate"),
        ("wrong_channel", "coverage"),
        ("wrong_target_date", "target_date"),
        ("duplicate_cycle_predictor", "duplicate"),
    ],
)
def test_malformed_channel_and_cycle_archives_are_rejected(
    mutation: str,
    message: str,
) -> None:
    api = _api()
    base = _forecast_input(api, periods=14, draw_count=12)
    overrides = {}
    if mutation == "nonfinite_state":
        states = base.current_channel_states
        states.loc[0, "state"] = np.inf
        overrides["current_channel_states"] = states
    elif mutation == "duplicate_history":
        history = pd.concat(
            [base.channel_history, base.channel_history.iloc[[0]]],
            ignore_index=True,
        )
        overrides["channel_history"] = history
    elif mutation == "wrong_channel":
        states = base.current_channel_states
        states.loc[0, "channel_id"] = "not_registered"
        overrides["current_channel_states"] = states
    elif mutation == "wrong_target_date":
        history = base.channel_history
        history.loc[0, "target_date"] += pd.offsets.MonthEnd(1)
        overrides["channel_history"] = history
    else:
        archive = pd.concat(
            [
                base.cycle_predictor_archive,
                base.cycle_predictor_archive.iloc[[0]],
            ],
            ignore_index=True,
        )
        overrides["cycle_predictor_archive"] = archive

    with pytest.raises(ValueError, match=message):
        _rebuild_input(api, base, **overrides)


def test_current_exogenous_draw_coverage_and_dates_are_exact() -> None:
    api = _api()
    base = _forecast_input(api, periods=14, draw_count=12)
    paths = base.current_exogenous_paths.iloc[1:].reset_index(drop=True)

    with pytest.raises(ValueError, match="draw_id coverage"):
        _rebuild_input(api, base, current_exogenous_paths=paths)

    wrong_date = base.current_exogenous_paths
    wrong_date.loc[0, "date"] += pd.offsets.MonthEnd(1)
    with pytest.raises(ValueError, match="date must match"):
        _rebuild_input(api, base, current_exogenous_paths=wrong_date)


def test_registry_and_horizon_output_coverage_are_exact(joint_bundle) -> None:
    _, forecast_input, config, result = joint_bundle
    channel_ids = {channel.channel_id for channel in forecast_input.channel_specs}

    assert set(result.summary["channel_id"]) == channel_ids
    assert set(result.summary["horizon_months"]) == set(config.horizons)
    coverage = result.summary.groupby("horizon_months")["channel_id"].agg(set)
    assert all(group == channel_ids for group in coverage)
    covariance_pairs = len(channel_ids) ** 2 * len(config.horizons)
    assert len(result.covariance) == covariance_pairs

    missing = forecast_input.current_channel_states.iloc[1:].reset_index(drop=True)
    with pytest.raises(ValueError, match="coverage"):
        _rebuild_input(
            _api(),
            forecast_input,
            current_channel_states=missing,
        )


def test_contract_columns_are_exact_and_stable() -> None:
    api = _api()
    constants = (
        api.CHANNEL_HISTORY_COLUMNS,
        api.CYCLE_PREDICTOR_ARCHIVE_COLUMNS,
        api.EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
        api.CURRENT_CHANNEL_STATE_COLUMNS,
        api.CURRENT_EXOGENOUS_PATH_COLUMNS,
        api.CHANNEL_FORECAST_SUMMARY_COLUMNS,
        api.CHANNEL_FORECAST_DRAW_COLUMNS,
        api.CHANNEL_FORECAST_COVARIANCE_COLUMNS,
        api.CHANNEL_FORECAST_EVALUATION_COLUMNS,
    )

    for columns in constants:
        assert tuple(pd.DataFrame(columns=columns).columns) == columns
