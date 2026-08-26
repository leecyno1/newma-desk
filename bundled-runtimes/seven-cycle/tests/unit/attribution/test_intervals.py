from dataclasses import FrozenInstanceError
from importlib import import_module
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest


CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))
REQUIRED_API = (
    "ATTRIBUTION_INTERVAL_COLUMNS",
    "ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS",
    "CHANNEL_UNCERTAINTY_COLUMNS",
    "CYCLE_UNCERTAINTY_COLUMNS",
    "AttributionIntervalResult",
    "UncertaintyConfig",
    "estimate_attribution_intervals",
)


def _api() -> ModuleType:
    try:
        module = import_module("seven_cycle_platform.attribution")
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 17 uncertainty module is missing: {error}", pytrace=False)
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"Task 17 uncertainty API is missing: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _stage1_paths(
    *,
    history_count: int = 30,
    correlated_cycles: bool = False,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    generator = np.random.default_rng(20260713)
    dates = pd.date_range("2021-01-31", periods=history_count + 1, freq="ME")
    innovations = generator.normal(size=(len(dates), len(CYCLE_IDS)))
    if correlated_cycles:
        innovations[:-1, 1] = innovations[:-1, 0]
    innovations[-1] = np.asarray([1.0, 2.0, -1.0, 0.5, -0.5, 1.5, -2.0])
    coefficient_map = {
        "growth": np.asarray([0.30, -0.05, 0.02, 0.0, 0.0, 0.0, 0.0]),
        "inflation": np.asarray([0.20, 0.05, -0.01, 0.0, 0.0, 0.0, 0.0]),
    }
    intercept_map = {"growth": 0.20, "inflation": -0.10}
    residual_map = {"growth": 0.05, "inflation": -0.05}
    rows: list[dict[str, object]] = []
    for date_position, current_date in enumerate(dates):
        for channel_id in ("growth", "inflation"):
            coefficients = coefficient_map[channel_id]
            contributions = innovations[date_position] * coefficients
            intercept = intercept_map[channel_id]
            residual = residual_map[channel_id]
            predicted = intercept + float(contributions.sum())
            observed = predicted + residual
            for cycle_position, cycle_id in enumerate(CYCLE_IDS):
                rows.append(
                    {
                        "date": current_date,
                        "channel_id": channel_id,
                        "cycle_id": cycle_id,
                        "cycle_innovation": float(
                            innovations[date_position, cycle_position]
                        ),
                        "coefficient_mean": float(coefficients[cycle_position]),
                        "contribution": float(contributions[cycle_position]),
                        "intercept": intercept,
                        "observed_channel_innovation": observed,
                        "predicted_channel_innovation": predicted,
                        "channel_residual": residual,
                        "training_count": history_count,
                        "status": "estimated",
                    }
                )
    return pd.DataFrame(rows), dates[-1]


def _stage2_components(current_date: pd.Timestamp) -> pd.DataFrame:
    rows = [
        ("intercept", "intercept", 1.0, 0.07, 0.07),
        ("benchmark", "benchmark_return", 0.5, 0.20, 0.10),
        ("channel", "growth", 0.43, 2.00, 0.86),
        ("channel", "inflation", 0.16, -1.00, -0.16),
        ("interaction", "growth_x_inflation", 1.0, -0.02, -0.02),
        ("control", "momentum", 0.3, 0.10, 0.03),
        ("event", "policy", 1.0, 1.20, 1.20),
        ("residual", "asset_residual", -1.08, 1.0, -1.08),
    ]
    return pd.DataFrame(
        [
            {
                "date": current_date,
                "asset_id": "asset_a",
                "component_type": component_type,
                "component_id": component_id,
                "component_value": component_value,
                "coefficient_mean": coefficient_mean,
                "contribution": contribution,
                "observed_return": 1.0,
                "predicted_return": 2.08,
                "asset_residual": -1.08,
                "training_count": 40,
                "effective_training_count": 36,
                "status": "parent_informed",
            }
            for (
                component_type,
                component_id,
                component_value,
                coefficient_mean,
                contribution,
            ) in rows
        ]
    )


def _contribution_result(
    api: ModuleType,
    *,
    correlated_cycles: bool = False,
    direct: bool = False,
) -> tuple[object, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    stage1, current_date = _stage1_paths(correlated_cycles=correlated_cycles)
    stage2 = _stage2_components(current_date)
    evidence = None
    if direct:
        evidence = pd.DataFrame(
            {
                "date": [current_date],
                "asset_id": ["asset_a"],
                "contribution": [0.20],
                "oos_gain": [0.10],
                "stability_score": [0.95],
                "validation_count": [24],
                "validated": [True],
                "validation_end_date": [current_date - pd.Timedelta(days=1)],
            }
        )
    result = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=evidence,
        config=api.ContributionConfig(
            identifiability=api.IdentifiabilityConfig(
                min_history_count=18,
                correlation_threshold=0.999,
                condition_number_threshold=1_000_000.0,
            ),
            direct_min_oos_gain=0.05,
            direct_min_stability_score=0.80,
            direct_min_validation_count=12,
        ),
    )
    return result, stage1, stage2, current_date


def _stage1_covariance(
    current_date: pd.Timestamp,
    *,
    training_count: int = 30,
) -> pd.DataFrame:
    standard_deviations = np.asarray([0.08, 0.06, 0.02, 0.01, 0.01, 0.01, 0.01])
    matrix = np.diag(standard_deviations**2)
    matrix[0, 1] = matrix[1, 0] = 0.5 * standard_deviations[0] * standard_deviations[1]
    rows = []
    for channel_id in ("growth", "inflation"):
        for row_position, cycle_i in enumerate(CYCLE_IDS):
            for column_position, cycle_j in enumerate(CYCLE_IDS):
                rows.append(
                    {
                        "date": current_date,
                        "channel_id": channel_id,
                        "cycle_i": cycle_i,
                        "cycle_j": cycle_j,
                        "coefficient_covariance": float(
                            matrix[row_position, column_position]
                        ),
                        "training_count": training_count,
                        "status": "estimated",
                    }
                )
    return pd.DataFrame(rows)


def _stage2_covariance(
    current_date: pd.Timestamp,
    *,
    correlated_channels: bool = True,
) -> pd.DataFrame:
    labels = (
        ("intercept", "intercept"),
        ("benchmark", "benchmark_return"),
        ("channel", "growth"),
        ("channel", "inflation"),
        ("interaction", "growth_x_inflation"),
        ("control", "momentum"),
        ("event", "policy"),
    )
    standard_deviations = np.asarray([0.02, 0.40, 0.30, 0.20, 0.001, 0.02, 0.05])
    matrix = np.diag(standard_deviations**2)
    if correlated_channels:
        matrix[2, 3] = matrix[3, 2] = (
            0.60 * standard_deviations[2] * standard_deviations[3]
        )
    rows = []
    for row_position, (component_i_type, component_i_id) in enumerate(labels):
        for column_position, (component_j_type, component_j_id) in enumerate(labels):
            rows.append(
                {
                    "date": current_date,
                    "node_level": "asset",
                    "node_id": "asset_a",
                    "component_i_type": component_i_type,
                    "component_i_id": component_i_id,
                    "component_j_type": component_j_type,
                    "component_j_id": component_j_id,
                    "coefficient_covariance": float(
                        matrix[row_position, column_position]
                    ),
                    "training_count": 40,
                    "effective_training_count": 36,
                    "status": "parent_informed",
                }
            )
    return pd.DataFrame(rows)


def _cycle_uncertainty(current_date: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [current_date] * len(CYCLE_IDS),
            "cycle_id": list(CYCLE_IDS),
            "uncertainty": [1.20, 0.80, 0.25, 0.20, 0.20, 0.20, 0.20],
            "effective_samples": [40] * len(CYCLE_IDS),
        }
    )


def _channel_uncertainty(current_date: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [current_date, current_date],
            "channel_id": ["growth", "inflation"],
            "uncertainty": [0.12, 0.10],
            "effective_samples": [32, 32],
        }
    )


def _residual_history(
    current_date: pd.Timestamp,
    *,
    count: int = 30,
    include_future: bool = False,
) -> pd.DataFrame:
    generator = np.random.default_rng(117)
    dates = pd.date_range(
        end=current_date - pd.offsets.MonthEnd(1), periods=count, freq="ME"
    )
    rows: list[dict[str, object]] = []
    specifications = (
        ("channel_residual_path", "growth", 0.04),
        ("channel_residual_path", "inflation", 0.03),
        ("asset_residual", "asset_residual", 0.15),
        ("unobserved_channel_residual", "direct_cycle_residual", 5.0),
    )
    for component_type, component_id, scale in specifications:
        for history_date, value in zip(
            dates,
            generator.normal(0.0, scale, size=count),
            strict=True,
        ):
            rows.append(
                {
                    "date": history_date,
                    "asset_id": "asset_a",
                    "component_type": component_type,
                    "component_id": component_id,
                    "residual": float(value),
                }
            )
    if include_future:
        rows.extend(
            [
                {
                    "date": current_date + pd.offsets.MonthEnd(offset),
                    "asset_id": "asset_a",
                    "component_type": "asset_residual",
                    "component_id": "asset_residual",
                    "residual": 1_000_000.0 * offset,
                }
                for offset in (1, 2, 3)
            ]
        )
    return pd.DataFrame(rows)


def _config(api: ModuleType, **updates: object) -> object:
    values: dict[str, object] = {
        "draw_count": 700,
        "seed": 917,
        "block_length": 2,
        "min_effective_samples": 12,
        "conservation_tolerance": 1e-10,
    }
    values.update(updates)
    return api.UncertaintyConfig(**values)


def _estimate(
    api: ModuleType,
    *,
    config: object | None = None,
    correlated_cycles: bool = False,
    correlated_stage2: bool = True,
    direct: bool = False,
    residual_history: pd.DataFrame | None = None,
) -> tuple[object, object, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    contribution, stage1, stage2, current_date = _contribution_result(
        api,
        correlated_cycles=correlated_cycles,
        direct=direct,
    )
    history = (
        _residual_history(current_date)
        if residual_history is None
        else residual_history
    )
    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=_stage2_covariance(
            current_date,
            correlated_channels=correlated_stage2,
        ),
        cycle_uncertainty=_cycle_uncertainty(current_date),
        channel_uncertainty=_channel_uncertainty(current_date),
        residual_history=history,
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=config or _config(api),
    )
    return result, contribution, stage1, stage2, current_date


def _stage2_components_for_date(
    stage1: pd.DataFrame,
    current_date: pd.Timestamp,
    observed_return: float,
) -> pd.DataFrame:
    frame = _stage2_components(current_date)
    for channel_id in ("growth", "inflation"):
        channel_value = float(
            stage1.loc[
                stage1["date"].eq(current_date) & stage1["channel_id"].eq(channel_id),
                "observed_channel_innovation",
            ].iloc[0]
        )
        row_mask = frame["component_type"].eq("channel") & frame["component_id"].eq(
            channel_id
        )
        frame.loc[row_mask, "component_value"] = channel_value
        frame.loc[row_mask, "contribution"] = (
            channel_value * frame.loc[row_mask, "coefficient_mean"]
        )
    predicted = float(
        frame.loc[frame["component_type"].ne("residual"), "contribution"].sum()
    )
    residual = observed_return - predicted
    residual_mask = frame["component_type"].eq("residual")
    frame.loc[residual_mask, "component_value"] = residual
    frame.loc[residual_mask, "contribution"] = residual
    frame["observed_return"] = observed_return
    frame["predicted_return"] = predicted
    frame["asset_residual"] = residual
    return frame


def _multi_period_inputs(
    api: ModuleType,
    *,
    month_count: int = 12,
) -> dict[str, object]:
    stage1, _ = _stage1_paths(history_count=48)
    dates = sorted(stage1["date"].drop_duplicates())[-month_count:]
    contribution_results = []
    stage2_frames = []
    for position, current_date in enumerate(dates):
        observed_return = 0.01 + 0.002 * np.sin(position)
        stage2 = _stage2_components_for_date(
            stage1,
            current_date,
            observed_return,
        )
        stage2_frames.append(stage2)
        contribution_results.append(
            api.compose_attribution_paths(
                stage1,
                stage2,
                config=api.ContributionConfig(
                    identifiability=api.IdentifiabilityConfig(
                        min_history_count=18,
                        correlation_threshold=0.999,
                        condition_number_threshold=1_000_000.0,
                    )
                ),
            )
        )
    contribution = SimpleNamespace(
        components=pd.concat(
            [result.components for result in contribution_results],
            ignore_index=True,
        ),
        paths=pd.concat(
            [result.paths for result in contribution_results],
            ignore_index=True,
        ),
    )
    stage2 = pd.concat(stage2_frames, ignore_index=True)
    stage1_covariance = pd.concat(
        [_stage1_covariance(current_date, training_count=48) for current_date in dates],
        ignore_index=True,
    )
    stage2_covariance = pd.concat(
        [_stage2_covariance(current_date) for current_date in dates],
        ignore_index=True,
    )
    cycle_uncertainty = pd.concat(
        [_cycle_uncertainty(current_date) for current_date in dates],
        ignore_index=True,
    )
    channel_uncertainty = pd.concat(
        [_channel_uncertainty(current_date) for current_date in dates],
        ignore_index=True,
    )
    residual_history = _residual_history(dates[0], count=48)
    return {
        "contribution": contribution,
        "stage1": stage1,
        "stage2": stage2,
        "stage1_covariance": stage1_covariance,
        "stage2_covariance": stage2_covariance,
        "cycle_uncertainty": cycle_uncertainty,
        "channel_uncertainty": channel_uncertainty,
        "residual_history": residual_history,
        "dates": dates,
    }


def test_seeded_intervals_are_nested_significant_and_conserved() -> None:
    api = _api()
    result, contribution, _, _, _ = _estimate(api)
    intervals = result.intervals

    assert tuple(intervals.columns) == api.ATTRIBUTION_INTERVAL_COLUMNS
    assert api.CYCLE_UNCERTAINTY_COLUMNS == (
        "date",
        "cycle_id",
        "uncertainty",
    )
    assert api.CHANNEL_UNCERTAINTY_COLUMNS == (
        "date",
        "channel_id",
        "uncertainty",
    )
    assert (
        tuple(result.diagnostics.columns) == api.ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS
    )
    point = contribution.components.rename(columns={"contribution": "expected"})
    merged = intervals.merge(
        point[["asset_id", "component_type", "component_id", "expected"]],
        on=["asset_id", "component_type", "component_id"],
        validate="one_to_one",
    )
    np.testing.assert_allclose(
        merged["point_contribution"],
        merged["expected"],
        atol=0.0,
        rtol=0.0,
    )
    available = intervals.loc[intervals["interval_status"].ne("unavailable")]
    assert (
        (available["lower_80"] <= available["lower_50"])
        & (available["lower_50"] <= available["upper_50"])
        & (available["upper_50"] <= available["upper_80"])
    ).all()
    significance = available.set_index(["component_type", "component_id"])[
        "significance"
    ]
    assert significance[("event", "policy")] == "positive"
    assert significance[("interaction", "growth_x_inflation")] == "negative"
    assert "not_significant" in set(significance)
    assert result.diagnostics["max_draw_conservation_error"].max() <= 1e-10
    assert result.diagnostics["point_conservation_error"].max() <= 1e-10
    assert intervals["observed_return"].eq(intervals["reconstructed_return"]).all()


def test_same_seed_and_shuffled_inputs_are_exactly_deterministic() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    inputs = {
        "stage1_paths": stage1,
        "stage1_covariance": _stage1_covariance(current_date),
        "stage2_components": stage2,
        "stage2_covariance": _stage2_covariance(current_date),
        "cycle_uncertainty": _cycle_uncertainty(current_date),
        "channel_uncertainty": _channel_uncertainty(current_date),
        "residual_history": _residual_history(current_date),
    }

    def run(shuffle: bool, seed: int) -> object:
        supplied = {
            name: (
                frame.sample(frac=1.0, random_state=37).reset_index(drop=True)
                if shuffle
                else frame.copy(deep=True)
            )
            for name, frame in inputs.items()
        }
        return api.estimate_attribution_intervals(
            contribution,
            **supplied,
            period_start=current_date,
            period_end=current_date,
            horizon_months=1,
            return_basis="absolute",
            config=_config(api, seed=seed),
        )

    first = run(False, 917)
    repeated = run(True, 917)
    changed_seed = run(True, 918)

    pd.testing.assert_frame_equal(first.intervals, repeated.intervals, check_exact=True)
    pd.testing.assert_frame_equal(first.draws, repeated.draws, check_exact=True)
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(
            first.intervals,
            changed_seed.intervals,
            check_exact=True,
        )


def test_twelve_month_period_uses_wealth_linked_point_and_draw_conservation() -> None:
    api = _api()
    inputs = _multi_period_inputs(api)
    dates = inputs["dates"]
    result = api.estimate_attribution_intervals(
        inputs["contribution"],
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=inputs["residual_history"],
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=300, block_length=3),
    )
    monthly_observed = (
        inputs["contribution"]
        .components.groupby("date")["observed_return"]
        .first()
        .sort_index()
    )
    expected_period_return = float(np.prod(1.0 + monthly_observed) - 1.0)
    intervals = result.intervals
    draws = result.draws

    assert intervals["period_start"].eq(dates[0]).all()
    assert intervals["period_end"].eq(dates[-1]).all()
    assert intervals["horizon_months"].eq(12).all()
    assert intervals["observed_return"].eq(expected_period_return).all()
    assert float(intervals["point_contribution"].sum()) == pytest.approx(
        expected_period_return,
        abs=1e-10,
    )
    available = intervals.loc[intervals["interval_status"].eq("available")]
    assert (
        (available["lower_80"] <= available["lower_50"])
        & (available["lower_50"] <= available["upper_50"])
        & (available["upper_50"] <= available["upper_80"])
    ).all()
    np.testing.assert_allclose(
        draws.groupby("draw")["contribution"].sum(),
        draws.groupby("draw")["target_return"].first(),
        atol=1e-10,
        rtol=0.0,
    )
    assert result.diagnostics["status"].eq("available").all()
    assert result.diagnostics["max_draw_conservation_error"].max() <= 1e-10


def test_multi_period_bootstrap_uses_past_only_moving_blocks() -> None:
    api = _api()
    inputs = _multi_period_inputs(api)
    dates = inputs["dates"]
    baseline = api.estimate_attribution_intervals(
        inputs["contribution"],
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=inputs["residual_history"],
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=250, block_length=4),
    )
    contaminated = inputs["residual_history"].copy(deep=True)
    future_rows = []
    for current_date in dates:
        for component_type, component_id in (
            ("channel_residual_path", "growth"),
            ("channel_residual_path", "inflation"),
            ("asset_residual", "asset_residual"),
        ):
            future_rows.append(
                {
                    "date": current_date,
                    "asset_id": "asset_a",
                    "component_type": component_type,
                    "component_id": component_id,
                    "residual": 1_000_000.0,
                }
            )
    contaminated = pd.concat(
        [contaminated, pd.DataFrame(future_rows)],
        ignore_index=True,
    )
    repeated = api.estimate_attribution_intervals(
        inputs["contribution"],
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=contaminated,
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=250, block_length=4),
    )
    different_block = api.estimate_attribution_intervals(
        inputs["contribution"],
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=inputs["residual_history"],
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=250, block_length=2),
    )

    pd.testing.assert_frame_equal(
        baseline.intervals, repeated.intervals, check_exact=True
    )
    pd.testing.assert_frame_equal(baseline.draws, repeated.draws, check_exact=True)
    with pytest.raises(AssertionError):
        pd.testing.assert_series_equal(
            baseline.draws.groupby("draw")["target_return"].first(),
            different_block.draws.groupby("draw")["target_return"].first(),
            check_exact=True,
        )


def test_multi_period_bootstrap_rejects_gapped_residual_history() -> None:
    api = _api()
    inputs = _multi_period_inputs(api)
    dates = inputs["dates"]
    residual_history = inputs["residual_history"].copy(deep=True)
    asset_residual = residual_history["component_type"].eq("asset_residual")
    residual_count = int(asset_residual.sum())
    residual_history.loc[asset_residual, "date"] = pd.date_range(
        end=dates[0] - pd.offsets.MonthEnd(1),
        periods=residual_count,
        freq="2ME",
    )

    result = api.estimate_attribution_intervals(
        inputs["contribution"],
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=residual_history,
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=120, block_length=3),
    )

    assert result.draws.empty
    assert result.diagnostics["status"].eq("unavailable").all()
    assert result.diagnostics["max_draw_conservation_error"].isna().all()


def test_multi_period_uses_the_governed_asset_residual_component_id() -> None:
    api = _api()
    inputs = _multi_period_inputs(api)
    dates = inputs["dates"]
    components = inputs["contribution"].components
    components.loc[
        components["component_type"].eq("asset_residual"), "component_id"
    ] = "resid_custom"
    residual_history = inputs["residual_history"].copy(deep=True)
    residual_history.loc[
        residual_history["component_type"].eq("asset_residual"), "component_id"
    ] = "resid_custom"
    contribution = SimpleNamespace(
        components=components,
        paths=inputs["contribution"].paths,
    )

    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=inputs["stage1"],
        stage1_covariance=inputs["stage1_covariance"],
        stage2_components=inputs["stage2"],
        stage2_covariance=inputs["stage2_covariance"],
        cycle_uncertainty=inputs["cycle_uncertainty"],
        channel_uncertainty=inputs["channel_uncertainty"],
        residual_history=residual_history,
        period_start=dates[0],
        period_end=dates[-1],
        horizon_months=12,
        return_basis="absolute",
        config=_config(api, draw_count=120, block_length=3),
    )

    residual = result.intervals.loc[
        result.intervals["component_type"].eq("asset_residual")
    ].iloc[0]
    assert residual["component_id"] == "resid_custom"
    assert residual["interval_status"] == "available"
    assert result.diagnostics["status"].eq("available").all()
    assert not result.draws.empty


def test_multi_period_rejects_noncontiguous_dates_and_invalid_compounding() -> None:
    api = _api()
    inputs = _multi_period_inputs(api)
    dates = inputs["dates"]
    missing_month = inputs["contribution"].components.loc[
        lambda values: values["date"].ne(dates[5])
    ]
    malformed = SimpleNamespace(
        components=missing_month,
        paths=inputs["contribution"].paths.loc[
            lambda values: values["date"].ne(dates[5])
        ],
    )
    with pytest.raises(ValueError, match="contiguous monthly dates"):
        api.estimate_attribution_intervals(
            malformed,
            stage1_paths=inputs["stage1"],
            stage1_covariance=inputs["stage1_covariance"],
            stage2_components=inputs["stage2"],
            stage2_covariance=inputs["stage2_covariance"],
            cycle_uncertainty=inputs["cycle_uncertainty"],
            channel_uncertainty=inputs["channel_uncertainty"],
            residual_history=inputs["residual_history"],
            period_start=dates[0],
            period_end=dates[-1],
            horizon_months=12,
            return_basis="absolute",
            config=_config(api, draw_count=100),
        )

    invalid_components = inputs["contribution"].components.copy(deep=True)
    invalid_date = dates[0]
    current = invalid_components["date"].eq(invalid_date)
    old_observed = float(invalid_components.loc[current, "observed_return"].iloc[0])
    delta = -1.0 - old_observed
    invalid_components.loc[current, "observed_return"] = -1.0
    invalid_components.loc[current, "reconstructed_return"] = -1.0
    residual = current & invalid_components["component_type"].eq("asset_residual")
    invalid_components.loc[residual, "contribution"] += delta
    invalid = SimpleNamespace(
        components=invalid_components,
        paths=inputs["contribution"].paths,
    )
    with pytest.raises(ValueError, match="greater than -100%"):
        api.estimate_attribution_intervals(
            invalid,
            stage1_paths=inputs["stage1"],
            stage1_covariance=inputs["stage1_covariance"],
            stage2_components=inputs["stage2"],
            stage2_covariance=inputs["stage2_covariance"],
            cycle_uncertainty=inputs["cycle_uncertainty"],
            channel_uncertainty=inputs["channel_uncertainty"],
            residual_history=inputs["residual_history"],
            period_start=dates[0],
            period_end=dates[-1],
            horizon_months=12,
            return_basis="absolute",
            config=_config(api, draw_count=100),
        )


def test_stage2_channel_beta_is_sampled_once_and_reused_across_paths() -> None:
    api = _api()
    config = _config(
        api,
        enable_cycle_state=False,
        enable_stage1_covariance=False,
        enable_channel_uncertainty=False,
        enable_residual_bootstrap=False,
    )
    result, _, _, _, _ = _estimate(api, config=config)
    draws = result.draws
    growth = draws.loc[
        draws["component_id"].eq("growth")
        & draws["component_type"].isin(
            ["channel_baseline_path", "channel_residual_path"]
        )
    ].pivot(index="draw", columns="component_type", values="contribution")

    np.testing.assert_allclose(
        growth["channel_baseline_path"] / growth["channel_residual_path"],
        4.0,
        atol=1e-12,
        rtol=0.0,
    )


def test_uncertainty_sources_affect_only_their_owned_components() -> None:
    api = _api()
    all_sources, _, _, _, _ = _estimate(api)
    no_channel, _, _, _, _ = _estimate(
        api,
        config=_config(api, enable_channel_uncertainty=False),
    )
    no_residual, _, _, _, _ = _estimate(
        api,
        config=_config(api, enable_residual_bootstrap=False),
    )

    def bounds(result: object, component_type: str, component_id: str) -> np.ndarray:
        row = result.intervals.loc[
            result.intervals["component_type"].eq(component_type)
            & result.intervals["component_id"].eq(component_id)
        ].iloc[0]
        return row[["lower_50", "upper_50", "lower_80", "upper_80"]].to_numpy(
            dtype="float64"
        )

    np.testing.assert_array_equal(
        bounds(all_sources, "cycle", "C1"),
        bounds(no_channel, "cycle", "C1"),
    )
    assert not np.array_equal(
        bounds(all_sources, "channel_residual_path", "growth"),
        bounds(no_channel, "channel_residual_path", "growth"),
    )
    np.testing.assert_array_equal(
        bounds(all_sources, "benchmark", "benchmark_return"),
        bounds(no_residual, "benchmark", "benchmark_return"),
    )
    assert not np.array_equal(
        bounds(all_sources, "asset_residual", "asset_residual"),
        bounds(no_residual, "asset_residual", "asset_residual"),
    )


def test_joint_covariance_changes_aggregated_cycle_interval() -> None:
    api = _api()
    config = _config(
        api,
        enable_cycle_state=False,
        enable_stage1_covariance=False,
        enable_channel_uncertainty=False,
        enable_residual_bootstrap=False,
    )
    correlated, _, _, _, _ = _estimate(
        api,
        config=config,
        correlated_stage2=True,
    )
    diagonal, _, _, _, _ = _estimate(
        api,
        config=config,
        correlated_stage2=False,
    )

    def width(result: object) -> float:
        row = result.intervals.loc[
            result.intervals["component_type"].eq("cycle")
            & result.intervals["component_id"].eq("C1")
        ].iloc[0]
        return float(row["upper_80"] - row["lower_80"])

    assert width(correlated) > width(diagonal)


def test_residual_bootstrap_uses_only_past_history() -> None:
    api = _api()
    _, _, _, current_date = _contribution_result(api)
    past = _residual_history(current_date)
    with_future = _residual_history(current_date, include_future=True)
    past_result, _, _, _, _ = _estimate(api, residual_history=past)
    future_result, _, _, _, _ = _estimate(api, residual_history=with_future)

    pd.testing.assert_frame_equal(
        past_result.intervals,
        future_result.intervals,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        past_result.draws, future_result.draws, check_exact=True
    )


def test_insufficient_residual_history_never_fabricates_bounds() -> None:
    api = _api()
    _, _, _, current_date = _contribution_result(api)
    result, _, _, _, _ = _estimate(
        api,
        residual_history=_residual_history(current_date, count=6),
    )
    residuals = result.intervals.loc[result.intervals["is_residual"]]

    assert residuals["interval_status"].eq("unavailable").all()
    assert (
        residuals[["lower_50", "upper_50", "lower_80", "upper_80"]]
        .isna()
        .all(axis=None)
    )
    assert residuals["evidence_level"].eq("low").all()
    assert residuals["effective_samples"].eq(6).all()


def test_invalid_covariance_and_missing_uncertainty_degrade_without_zero_variance() -> (
    None
):
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    stage2_covariance = _stage2_covariance(current_date)
    mask = (
        stage2_covariance["component_i_type"].eq("channel")
        & stage2_covariance["component_i_id"].eq("growth")
        & stage2_covariance["component_j_type"].eq("channel")
        & stage2_covariance["component_j_id"].eq("growth")
    )
    stage2_covariance.loc[mask, "coefficient_covariance"] = -1.0
    cycle_uncertainty = _cycle_uncertainty(current_date).loc[
        lambda values: values["cycle_id"].ne("C1")
    ]

    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=stage2_covariance,
        cycle_uncertainty=cycle_uncertainty,
        channel_uncertainty=_channel_uncertainty(current_date),
        residual_history=_residual_history(current_date),
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=_config(api),
    )
    affected = result.intervals.loc[
        result.intervals["component_type"].isin(
            ["cycle", "channel_baseline_path", "channel_residual_path", "benchmark"]
        )
    ]

    assert affected["interval_status"].eq("unavailable").all()
    assert (
        affected[["lower_50", "upper_50", "lower_80", "upper_80"]].isna().all(axis=None)
    )
    assert affected["evidence_level"].eq("low").all()


def test_validated_direct_residual_is_not_bootstrapped_again() -> None:
    api = _api()
    result, _, _, _, _ = _estimate(api, direct=True)
    direct_interval = result.intervals.loc[
        result.intervals["component_type"].eq("unobserved_channel_residual")
    ].iloc[0]
    assert direct_interval["interval_status"] == "unavailable"
    assert result.draws.empty
    assert result.diagnostics["status"].eq("partial").all()
    assert result.diagnostics["max_draw_conservation_error"].isna().all()


def test_independent_target_draws_balance_through_the_unique_asset_residual() -> None:
    api = _api()
    result, _, _, _, _ = _estimate(
        api,
        config=_config(api, enable_residual_bootstrap=False),
    )
    draws = result.draws
    dimensions = [
        "asset_id",
        "period_start",
        "period_end",
        "horizon_months",
        "return_basis",
        "draw",
    ]
    targets = draws.groupby(dimensions)["target_return"].first()
    sums = draws.groupby(dimensions)["contribution"].sum()
    np.testing.assert_allclose(sums, targets, atol=1e-12, rtol=0.0)
    assert targets.eq(1.0).all()

    residual = draws.loc[draws["component_type"].eq("asset_residual")].set_index(
        "draw"
    )["contribution"]
    explained = (
        draws.loc[draws["component_type"].ne("asset_residual")]
        .groupby("draw")["contribution"]
        .sum()
    )
    np.testing.assert_allclose(residual, 1.0 - explained, atol=1e-12, rtol=0.0)
    assert residual.nunique() > 1


def test_bootstrapped_target_is_independent_and_retained_draws_use_final_balance() -> (
    None
):
    api = _api()
    result, _, _, _, _ = _estimate(api)
    draws = result.draws
    targets = draws.groupby("draw")["target_return"].first()
    sums = draws.groupby("draw")["contribution"].sum()

    assert targets.nunique() > 1
    np.testing.assert_allclose(sums, targets, atol=1e-12, rtol=0.0)
    assert result.diagnostics["max_draw_conservation_error"].max() <= 1e-10


def test_result_rejects_circular_or_truncated_draw_diagnostics() -> None:
    api = _api()
    result, _, _, _, _ = _estimate(api)
    intervals = result.intervals
    diagnostics = result.diagnostics
    draws = result.draws
    draws.loc[0, "contribution"] += 0.25

    with pytest.raises(ValueError, match="bounds|draw conservation"):
        api.AttributionIntervalResult(
            intervals=intervals,
            diagnostics=diagnostics,
            draws=draws,
            draw_count=result.draw_count,
            seed=result.seed,
        )

    truncated = result.draws.drop(index=result.draws.index[0]).reset_index(drop=True)
    with pytest.raises(ValueError, match="complete draw ids"):
        api.AttributionIntervalResult(
            intervals=intervals,
            diagnostics=diagnostics,
            draws=truncated,
            draw_count=result.draw_count,
            seed=result.seed,
        )

    fabricated_bounds = result.intervals
    benchmark_index = fabricated_bounds.index[
        fabricated_bounds["component_type"].eq("benchmark")
    ][0]
    fabricated_bounds.loc[benchmark_index, "lower_50"] = (
        fabricated_bounds.loc[benchmark_index, "lower_50"]
        + fabricated_bounds.loc[benchmark_index, "upper_50"]
    ) / 2.0
    with pytest.raises(ValueError, match="bounds.*retained draws"):
        api.AttributionIntervalResult(
            intervals=fabricated_bounds,
            diagnostics=result.diagnostics,
            draws=result.draws,
            draw_count=result.draw_count,
            seed=result.seed,
        )


def test_effective_samples_come_from_support_and_ignore_draw_count() -> None:
    api = _api()
    smaller, _, _, _, _ = _estimate(api, config=_config(api, draw_count=300))
    larger, _, _, _, _ = _estimate(api, config=_config(api, draw_count=900))
    keys = ["component_type", "component_id"]
    smaller_support = smaller.intervals.set_index(keys)[
        ["effective_samples", "evidence_level"]
    ]
    larger_support = larger.intervals.set_index(keys)[
        ["effective_samples", "evidence_level"]
    ]

    pd.testing.assert_frame_equal(smaller_support, larger_support, check_exact=True)
    assert (
        smaller_support.loc[("benchmark", "benchmark_return"), "effective_samples"]
        == 36
    )
    assert smaller_support.loc[("cycle", "C1"), "effective_samples"] == 30
    assert (
        smaller_support.loc[("channel_residual_path", "growth"), "effective_samples"]
        == 30
    )


def test_insufficient_statistical_support_makes_interval_unavailable() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    stage2["effective_training_count"] = 6
    covariance = _stage2_covariance(current_date)
    covariance["effective_training_count"] = 6
    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=covariance,
        cycle_uncertainty=_cycle_uncertainty(current_date),
        channel_uncertainty=_channel_uncertainty(current_date),
        residual_history=_residual_history(current_date),
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=_config(api),
    )
    benchmark = result.intervals.loc[
        result.intervals["component_type"].eq("benchmark")
    ].iloc[0]

    assert benchmark["effective_samples"] == 6
    assert benchmark["interval_status"] == "unavailable"
    assert benchmark["evidence_level"] == "low"
    assert result.draws.empty
    assert result.diagnostics["status"].eq("unavailable").all()
    assert result.diagnostics["max_draw_conservation_error"].isna().all()
    asset_residual = result.intervals.loc[
        result.intervals["component_type"].eq("asset_residual")
    ].iloc[0]
    assert asset_residual["interval_status"] == "unavailable"


def test_fractional_stage2_effective_support_is_conservatively_floored() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    stage2["effective_training_count"] = 36.8
    covariance = _stage2_covariance(current_date)
    covariance["effective_training_count"] = 36.8

    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=covariance,
        cycle_uncertainty=_cycle_uncertainty(current_date),
        channel_uncertainty=_channel_uncertainty(current_date),
        residual_history=_residual_history(current_date),
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=_config(api),
    )
    benchmark = result.intervals.loc[
        result.intervals["component_type"].eq("benchmark")
    ].iloc[0]

    assert benchmark["effective_samples"] == 36


def test_upstream_support_consistency_is_strictly_validated() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    mismatched_stage1 = _stage1_covariance(current_date)
    mismatched_stage1["training_count"] = 29
    with pytest.raises(ValueError, match="Stage1.*training_count.*consistent"):
        api.estimate_attribution_intervals(
            contribution,
            stage1_paths=stage1,
            stage1_covariance=mismatched_stage1,
            stage2_components=stage2,
            stage2_covariance=_stage2_covariance(current_date),
            cycle_uncertainty=_cycle_uncertainty(current_date),
            channel_uncertainty=_channel_uncertainty(current_date),
            residual_history=_residual_history(current_date),
            period_start=current_date,
            period_end=current_date,
            horizon_months=1,
            return_basis="absolute",
            config=_config(api),
        )

    invalid_stage2 = _stage2_covariance(current_date)
    invalid_stage2["effective_training_count"] = 41.0
    with pytest.raises(ValueError, match="effective_training_count.*training_count"):
        api.estimate_attribution_intervals(
            contribution,
            stage1_paths=stage1,
            stage1_covariance=_stage1_covariance(current_date),
            stage2_components=stage2,
            stage2_covariance=invalid_stage2,
            cycle_uncertainty=_cycle_uncertainty(current_date),
            channel_uncertainty=_channel_uncertainty(current_date),
            residual_history=_residual_history(current_date),
            period_start=current_date,
            period_end=current_date,
            horizon_months=1,
            return_basis="absolute",
            config=_config(api),
        )


def test_uncertainty_support_claims_cannot_raise_evidence() -> None:
    api = _api()
    baseline, _, _, _, _ = _estimate(api)
    contribution, stage1, stage2, current_date = _contribution_result(api)
    cycle_uncertainty = _cycle_uncertainty(current_date)
    channel_uncertainty = _channel_uncertainty(current_date)
    cycle_uncertainty["effective_samples"] = 1_000_000
    channel_uncertainty["effective_samples"] = 1_000_000
    inflated = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=_stage2_covariance(current_date),
        cycle_uncertainty=cycle_uncertainty,
        channel_uncertainty=channel_uncertainty,
        residual_history=_residual_history(current_date),
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=_config(api),
    )
    columns = ["component_type", "component_id", "effective_samples", "evidence_level"]

    pd.testing.assert_frame_equal(
        baseline.intervals.loc[:, columns],
        inflated.intervals.loc[:, columns],
        check_exact=True,
    )


def test_disabled_cycle_state_does_not_require_uncertainty_support() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    result = api.estimate_attribution_intervals(
        contribution,
        stage1_paths=stage1,
        stage1_covariance=_stage1_covariance(current_date),
        stage2_components=stage2,
        stage2_covariance=_stage2_covariance(current_date),
        cycle_uncertainty=None,
        channel_uncertainty=_channel_uncertainty(current_date),
        residual_history=_residual_history(current_date),
        period_start=current_date,
        period_end=current_date,
        horizon_months=1,
        return_basis="absolute",
        config=_config(api, enable_cycle_state=False),
    )
    cycles = result.intervals.loc[
        result.intervals["component_type"].isin(["cycle", "cycle_group"])
    ]

    assert cycles["interval_status"].eq("available").all()


def test_single_date_contract_rejects_mismatched_horizon_period() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)

    with pytest.raises(ValueError, match="horizon_months.*monthly dates"):
        api.estimate_attribution_intervals(
            contribution,
            stage1_paths=stage1,
            stage1_covariance=_stage1_covariance(current_date),
            stage2_components=stage2,
            stage2_covariance=_stage2_covariance(current_date),
            cycle_uncertainty=_cycle_uncertainty(current_date),
            channel_uncertainty=_channel_uncertainty(current_date),
            residual_history=_residual_history(current_date),
            period_start=current_date - pd.DateOffset(months=2),
            period_end=current_date,
            horizon_months=3,
            return_basis="absolute",
            config=_config(api),
        )


def test_estimator_requires_exactly_one_asset_residual_component() -> None:
    api = _api()
    contribution, stage1, stage2, current_date = _contribution_result(api)
    components = contribution.components
    residual_index = components.index[
        components["component_type"].eq("asset_residual")
    ][0]
    duplicate = components.loc[[residual_index]].copy(deep=True)
    duplicate["component_id"] = "asset_residual_duplicate"
    duplicate["contribution"] /= 2.0
    components.loc[residual_index, "contribution"] /= 2.0
    malformed = type("ContributionFrames", (), {})()
    malformed.components = pd.concat([components, duplicate], ignore_index=True)
    malformed.paths = contribution.paths

    with pytest.raises(ValueError, match="exactly one asset_residual"):
        api.estimate_attribution_intervals(
            malformed,
            stage1_paths=stage1,
            stage1_covariance=_stage1_covariance(current_date),
            stage2_components=stage2,
            stage2_covariance=_stage2_covariance(current_date),
            cycle_uncertainty=_cycle_uncertainty(current_date),
            channel_uncertainty=_channel_uncertainty(current_date),
            residual_history=_residual_history(current_date),
            period_start=current_date,
            period_end=current_date,
            horizon_months=1,
            return_basis="absolute",
            config=_config(api),
        )


def test_result_rejects_invalid_period_and_failed_available_status() -> None:
    api = _api()
    result, _, _, _, _ = _estimate(api)
    invalid_period = result.intervals
    invalid_period["period_start"] = invalid_period["period_end"] + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="period_start"):
        api.AttributionIntervalResult(
            intervals=invalid_period,
            diagnostics=result.diagnostics,
            draws=result.draws,
            draw_count=result.draw_count,
            seed=result.seed,
        )

    failed_status = result.intervals
    benchmark_index = failed_status.index[
        failed_status["component_type"].eq("benchmark")
    ][0]
    failed_status.loc[benchmark_index, "status"] = "unavailable"
    with pytest.raises(ValueError, match="failed attribution status"):
        api.AttributionIntervalResult(
            intervals=failed_status,
            diagnostics=result.diagnostics,
            draws=result.draws,
            draw_count=result.draw_count,
            seed=result.seed,
        )


def test_uncertainty_config_and_result_are_frozen_and_defensive() -> None:
    api = _api()
    config = _config(api)
    with pytest.raises(FrozenInstanceError):
        config.seed = 1

    result, _, _, _, _ = _estimate(api, config=config)
    mutated = result.intervals
    mutated.loc[0, "point_contribution"] = 999.0
    assert result.intervals.loc[0, "point_contribution"] != 999.0
    with pytest.raises(FrozenInstanceError):
        result.draw_count = 1
