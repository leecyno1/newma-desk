from dataclasses import FrozenInstanceError
from importlib import import_module
from types import ModuleType

import numpy as np
import pandas as pd
import pytest


CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))
REQUIRED_API = (
    "CYCLE_IDS",
    "CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS",
    "CYCLE_TO_CHANNEL_PATH_COLUMNS",
    "CycleToChannelConfig",
    "CycleToChannelResult",
    "estimate_cycle_to_channel",
)


def _api() -> ModuleType:
    try:
        module = import_module("seven_cycle_platform.attribution")
    except ModuleNotFoundError:
        pytest.fail("Task 14 attribution package is missing", pytrace=False)
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"Task 14 public API is missing: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _synthetic_innovations(
    *,
    count: int = 168,
    seed: int = 20260713,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, float]:
    generator = np.random.default_rng(seed)
    dates = pd.date_range("2010-01-31", periods=count, freq="ME")
    independent = generator.normal(size=(count, 7))
    common_growth = generator.normal(size=count)
    common_prices = generator.normal(size=count)
    base = independent.copy()
    base[:, 0] += 0.40 * common_growth
    base[:, 1] += 0.30 * common_growth + 0.20 * common_prices
    base[:, 2] += 0.35 * common_prices
    base[:, 3] += 0.25 * common_growth - 0.20 * common_prices
    base[:, 4] += 0.30 * common_growth
    base[:, 5] += 0.25 * common_prices
    base[:, 6] += 0.20 * common_growth + 0.20 * common_prices
    scales = np.asarray([0.7, 1.8, 0.5, 1.2, 2.4, 0.9, 1.5])
    innovations = base * scales
    coefficients = np.asarray([0.80, -0.35, 0.55, 0.00, 0.22, -0.40, 0.15])
    intercept = 0.18
    channel = (
        intercept
        + innovations @ coefficients
        + generator.normal(scale=0.08, size=count)
    )
    cycle_wide = pd.DataFrame(
        innovations,
        index=dates,
        columns=CYCLE_IDS,
        dtype="float64",
    )
    cycles = (
        cycle_wide.rename_axis("date")
        .reset_index()
        .melt(
            id_vars="date",
            var_name="cycle_id",
            value_name="innovation",
        )
    )
    channels = pd.DataFrame(
        {
            "date": dates,
            "channel_id": "growth_activity",
            "innovation": channel,
        }
    )
    return cycles, channels, coefficients, intercept


def _config(api: ModuleType, **updates: object) -> object:
    values: dict[str, object] = {
        "window": "expanding",
        "rolling_window": None,
        "min_training_count": 42,
        "alpha_grid": (0.001, 0.01, 0.1, 1.0),
        "validation_window": 12,
        "condition_number_threshold": 1_000.0,
        "recursive": False,
        "forgetting_factor": 1.0,
    }
    values.update(updates)
    return api.CycleToChannelConfig(**values)


def _latest_paths(result: object) -> pd.DataFrame:
    paths = result.paths
    latest_date = paths["date"].max()
    return paths.loc[paths["date"].eq(latest_date)].reset_index(drop=True)


def _latest_covariance(result: object) -> pd.DataFrame:
    covariance = result.covariance
    latest_date = covariance["date"].max()
    return covariance.loc[covariance["date"].eq(latest_date)].reset_index(drop=True)


def _small_ridge_data() -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray(
        [
            [0.2, 1.0, -0.5],
            [0.4, 0.7, -0.1],
            [0.8, 0.2, 0.3],
            [1.1, -0.1, 0.8],
            [1.4, -0.4, 1.0],
            [1.8, -0.8, 1.3],
            [2.1, -1.0, 1.7],
            [2.5, -1.3, 2.0],
        ],
        dtype="float64",
    )
    target = np.asarray(
        [0.5, 0.8, 1.0, 1.5, 1.7, 2.2, 2.5, 3.1],
        dtype="float64",
    )
    return features, target


def test_public_api_is_available() -> None:
    api = _api()

    assert api.CYCLE_IDS == CYCLE_IDS


def test_expanding_ridge_recovers_latest_coefficients_and_conserves_paths() -> None:
    api = _api()
    cycles, channels, coefficients, _ = _synthetic_innovations()
    config = _config(api)

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    assert tuple(result.paths.columns) == api.CYCLE_TO_CHANNEL_PATH_COLUMNS
    assert tuple(result.covariance.columns) == api.CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS
    path_counts = result.paths.groupby(["date", "channel_id"]).size()
    covariance_counts = result.covariance.groupby(["date", "channel_id"]).size()
    assert path_counts.eq(7).all()
    assert covariance_counts.eq(49).all()

    latest = _latest_paths(result).set_index("cycle_id").loc[list(CYCLE_IDS)]
    assert latest["status"].eq("estimated").all()
    assert latest["training_end"].max() < latest["date"].min()
    assert latest["training_count"].eq(len(channels) - 1).all()
    assert latest["alpha"].iloc[0] in config.alpha_grid
    assert latest["validation_count"].iloc[0] > 0
    np.testing.assert_allclose(
        latest["coefficient_mean"].to_numpy(),
        coefficients,
        atol=0.10,
        rtol=0.0,
    )
    np.testing.assert_allclose(
        latest["contribution"].to_numpy(),
        latest["cycle_innovation"].to_numpy() * latest["coefficient_mean"].to_numpy(),
        atol=1e-12,
        rtol=0.0,
    )
    predicted = float(latest["predicted_channel_innovation"].iloc[0])
    observed = float(latest["observed_channel_innovation"].iloc[0])
    residual = float(latest["channel_residual"].iloc[0])
    reconstructed = float(latest["intercept"].iloc[0]) + float(
        latest["contribution"].sum()
    )
    assert predicted == pytest.approx(reconstructed, abs=1e-12)
    assert residual == pytest.approx(observed - predicted, abs=1e-12)

    covariance = _latest_covariance(result)
    matrix = covariance.pivot(
        index="cycle_i",
        columns="cycle_j",
        values="coefficient_covariance",
    ).loc[list(CYCLE_IDS), list(CYCLE_IDS)]
    np.testing.assert_allclose(matrix, matrix.T, atol=1e-12, rtol=0.0)
    assert np.diag(matrix).min() >= -1e-12
    assert covariance["status"].eq("estimated").all()


def test_rolling_ridge_bounds_training_window_and_recovers_coefficients() -> None:
    api = _api()
    cycles, channels, coefficients, _ = _synthetic_innovations(count=180)
    config = _config(
        api,
        window="rolling",
        rolling_window=72,
        min_training_count=48,
        validation_window=18,
    )

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result).set_index("cycle_id").loc[list(CYCLE_IDS)]
    expected_training_dates = channels["date"].iloc[-73:-1]
    assert latest["status"].eq("estimated").all()
    assert latest["training_count"].eq(72).all()
    assert latest["training_start"].eq(expected_training_dates.iloc[0]).all()
    assert latest["training_end"].eq(expected_training_dates.iloc[-1]).all()
    np.testing.assert_allclose(
        latest["coefficient_mean"].to_numpy(),
        coefficients,
        atol=0.16,
        rtol=0.0,
    )


def test_future_channel_perturbation_leaves_cutoff_outputs_exactly_unchanged() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=132)
    cutoff = channels["date"].iloc[100]
    perturbed = channels.copy(deep=True)
    future = perturbed["date"].gt(cutoff)
    perturbed.loc[future, "innovation"] += np.linspace(100.0, 500.0, future.sum())
    config = _config(api, min_training_count=36)

    baseline = api.estimate_cycle_to_channel(cycles, channels, config=config)
    changed = api.estimate_cycle_to_channel(cycles, perturbed, config=config)

    baseline_paths = baseline.paths.loc[baseline.paths["date"].le(cutoff)]
    changed_paths = changed.paths.loc[changed.paths["date"].le(cutoff)]
    baseline_covariance = baseline.covariance.loc[
        baseline.covariance["date"].le(cutoff)
    ]
    changed_covariance = changed.covariance.loc[changed.covariance["date"].le(cutoff)]
    pd.testing.assert_frame_equal(
        baseline_paths.reset_index(drop=True),
        changed_paths.reset_index(drop=True),
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        baseline_covariance.reset_index(drop=True),
        changed_covariance.reset_index(drop=True),
        check_exact=True,
    )


def test_current_observation_changes_only_observed_value_and_residual() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=120)
    cutoff = channels["date"].iloc[-1]
    perturbed = channels.copy(deep=True)
    perturbed.loc[perturbed["date"].eq(cutoff), "innovation"] += 250.0
    config = _config(api, min_training_count=36)

    baseline = api.estimate_cycle_to_channel(cycles, channels, config=config)
    changed = api.estimate_cycle_to_channel(cycles, perturbed, config=config)

    stable_columns = [
        "cycle_id",
        "cycle_innovation",
        "coefficient_mean",
        "contribution",
        "intercept",
        "predicted_channel_innovation",
        "training_start",
        "training_end",
        "training_count",
        "alpha",
        "condition_number",
        "validation_count",
        "window",
        "estimation_method",
        "forgetting_factor",
        "status",
    ]
    pd.testing.assert_frame_equal(
        _latest_paths(baseline)[stable_columns],
        _latest_paths(changed)[stable_columns],
        check_exact=True,
    )
    difference = (
        _latest_paths(changed)["observed_channel_innovation"]
        - _latest_paths(baseline)["observed_channel_innovation"]
    )
    residual_difference = (
        _latest_paths(changed)["channel_residual"]
        - _latest_paths(baseline)["channel_residual"]
    )
    np.testing.assert_allclose(difference, 250.0, atol=0.0, rtol=0.0)
    np.testing.assert_allclose(residual_difference, 250.0, atol=1e-12, rtol=0.0)


def test_recursive_coefficient_updating_is_supported() -> None:
    api = _api()
    cycles, channels, coefficients, _ = _synthetic_innovations(count=156)
    config = _config(
        api,
        recursive=True,
        forgetting_factor=0.995,
        min_training_count=42,
    )

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result).set_index("cycle_id").loc[list(CYCLE_IDS)]
    assert latest["status"].eq("estimated").all()
    assert latest["estimation_method"].eq("recursive").all()
    assert latest["forgetting_factor"].eq(0.995).all()
    np.testing.assert_allclose(
        latest["coefficient_mean"].to_numpy(),
        coefficients,
        atol=0.16,
        rtol=0.0,
    )
    assert np.isfinite(_latest_covariance(result)["coefficient_covariance"]).all()


def test_recursive_fixed_penalty_matches_closed_form_ew_ridge() -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()
    alpha = 0.75
    forgetting_factor = 0.82
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0, ddof=0)
    standardized = (features - feature_mean) / feature_scale
    design = np.column_stack([np.ones(len(features), dtype="float64"), standardized])
    powers = np.arange(len(features) - 1, -1, -1, dtype="float64")
    weights = np.power(forgetting_factor, powers)
    data_gram = design.T @ (weights[:, None] * design)
    penalty = np.diag([0.0, alpha, alpha, alpha])
    inverse = np.linalg.pinv(data_gram + penalty, hermitian=True)
    parameters = inverse @ design.T @ (weights * target)
    fitted = design @ parameters
    effective_degrees = float(np.trace(inverse @ data_gram))
    residual_variance = float(
        np.dot(weights, np.square(target - fitted))
        / max(float(weights.sum()) - effective_degrees, 1.0)
    )
    standardized_covariance = residual_variance * inverse @ data_gram @ inverse
    expected_coefficients = parameters[1:] / feature_scale
    expected_intercept = parameters[0] - float(feature_mean @ expected_coefficients)
    expected_covariance = standardized_covariance[1:, 1:] / np.outer(
        feature_scale,
        feature_scale,
    )

    estimate = walk_forward.fit_standardized_ridge(
        features,
        target,
        alpha=alpha,
        recursive=True,
        forgetting_factor=forgetting_factor,
    )

    np.testing.assert_allclose(
        estimate.coefficients,
        expected_coefficients,
        atol=1e-12,
        rtol=1e-12,
    )
    assert estimate.intercept == pytest.approx(
        expected_intercept,
        abs=1e-12,
        rel=1e-12,
    )
    np.testing.assert_allclose(
        estimate.covariance,
        expected_covariance,
        atol=1e-12,
        rtol=1e-12,
    )


def test_batch_ridge_matches_closed_form_effective_df_covariance() -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()
    alpha = 0.75
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0, ddof=0)
    standardized = (features - feature_mean) / feature_scale
    target_mean = float(target.mean())
    centered_target = target - target_mean
    gram = standardized.T @ standardized
    inverse = np.linalg.pinv(
        gram + alpha * np.eye(standardized.shape[1]),
        hermitian=True,
    )
    standardized_coefficients = inverse @ standardized.T @ centered_target
    fitted = target_mean + standardized @ standardized_coefficients
    effective_degrees = float(np.trace(inverse @ gram))
    residual_variance = float(
        np.dot(target - fitted, target - fitted)
        / max(len(target) - 1 - effective_degrees, 1.0)
    )
    standardized_covariance = residual_variance * inverse @ gram @ inverse
    expected_coefficients = standardized_coefficients / feature_scale
    expected_intercept = target_mean - float(feature_mean @ expected_coefficients)
    expected_covariance = standardized_covariance / np.outer(
        feature_scale,
        feature_scale,
    )

    estimate = walk_forward.fit_standardized_ridge(
        features,
        target,
        alpha=alpha,
        recursive=False,
        forgetting_factor=1.0,
    )

    np.testing.assert_allclose(
        estimate.coefficients,
        expected_coefficients,
        atol=1e-12,
        rtol=1e-12,
    )
    assert estimate.intercept == pytest.approx(
        expected_intercept,
        abs=1e-12,
        rel=1e-12,
    )
    np.testing.assert_allclose(
        estimate.covariance,
        expected_covariance,
        atol=1e-12,
        rtol=1e-12,
    )


@pytest.mark.parametrize("alpha", [True, np.nan, np.inf, -0.01])
def test_low_level_fit_rejects_invalid_alpha(alpha: object) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()

    with pytest.raises((TypeError, ValueError)):
        walk_forward.fit_standardized_ridge(
            features,
            target,
            alpha=alpha,
            recursive=False,
            forgetting_factor=1.0,
        )


@pytest.mark.parametrize("recursive", [0, 1, "yes"])
def test_low_level_fit_rejects_non_boolean_recursive(recursive: object) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()

    with pytest.raises(TypeError):
        walk_forward.fit_standardized_ridge(
            features,
            target,
            alpha=0.1,
            recursive=recursive,
            forgetting_factor=1.0,
        )


@pytest.mark.parametrize(
    "forgetting_factor",
    [True, 0.0, -0.5, 1.01, np.nan, np.inf],
)
def test_low_level_fit_rejects_invalid_forgetting_factor(
    forgetting_factor: object,
) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()

    with pytest.raises((TypeError, ValueError)):
        walk_forward.fit_standardized_ridge(
            features,
            target,
            alpha=0.1,
            recursive=False,
            forgetting_factor=forgetting_factor,
        )


@pytest.mark.parametrize(
    "alpha_grid",
    ["0.1", (), (True,), (np.nan,), (np.inf,), (-0.1,), (0.1, 0.1)],
)
def test_low_level_selector_rejects_invalid_alpha_grid(alpha_grid: object) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()

    with pytest.raises((TypeError, ValueError)):
        walk_forward.select_alpha_walk_forward(
            features,
            target,
            alpha_grid=alpha_grid,
            min_training_count=6,
            validation_window=2,
            recursive=False,
            forgetting_factor=1.0,
        )


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("min_training_count", True),
        ("min_training_count", 0),
        ("validation_window", True),
        ("validation_window", 0),
        ("recursive", 1),
        ("forgetting_factor", 0.0),
        ("forgetting_factor", np.inf),
    ],
)
def test_low_level_selector_rejects_invalid_controls(
    parameter: str,
    value: object,
) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    features, target = _small_ridge_data()
    controls: dict[str, object] = {
        "alpha_grid": (0.1, 1.0),
        "min_training_count": 6,
        "validation_window": 2,
        "recursive": False,
        "forgetting_factor": 1.0,
    }
    controls[parameter] = value

    with pytest.raises((TypeError, ValueError)):
        walk_forward.select_alpha_walk_forward(
            features,
            target,
            **controls,
        )


@pytest.mark.parametrize(
    ("features", "target"),
    [
        (np.ones(4), np.ones(4)),
        (np.ones((4, 2)), np.ones((4, 1))),
        (np.ones((4, 2)), np.ones(3)),
        (np.empty((0, 2)), np.empty(0)),
        (np.empty((4, 0)), np.ones(4)),
    ],
)
def test_low_level_ridge_functions_reject_invalid_dimensions(
    features: np.ndarray,
    target: np.ndarray,
) -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")

    with pytest.raises(ValueError):
        walk_forward.fit_standardized_ridge(
            features,
            target,
            alpha=0.1,
            recursive=False,
            forgetting_factor=1.0,
        )
    with pytest.raises(ValueError):
        walk_forward.select_alpha_walk_forward(
            features,
            target,
            alpha_grid=(0.1, 1.0),
            min_training_count=3,
            validation_window=1,
            recursive=False,
            forgetting_factor=1.0,
        )


def test_ridge_estimate_arrays_are_detached_and_read_only() -> None:
    walk_forward = import_module("seven_cycle_platform.attribution.walk_forward")
    coefficients = np.asarray([0.2, -0.1], dtype="float64")
    covariance = np.asarray([[0.3, 0.1], [0.1, 0.4]], dtype="float64")
    estimate = walk_forward.RidgeEstimate(
        coefficients=coefficients,
        intercept=0.5,
        covariance=covariance,
    )
    coefficients[0] = 99.0
    covariance[0, 0] = 99.0

    assert estimate.coefficients[0] == pytest.approx(0.2)
    assert estimate.covariance[0, 0] == pytest.approx(0.3)
    assert not estimate.coefficients.flags.writeable
    assert not estimate.covariance.flags.writeable
    with pytest.raises(ValueError):
        estimate.coefficients[0] = 1.0
    with pytest.raises(ValueError):
        estimate.covariance[0, 0] = 1.0


def test_rolling_window_is_normalized_to_python_int() -> None:
    api = _api()

    config = _config(
        api,
        window="rolling",
        rolling_window=np.int64(48),
    )

    assert type(config.rolling_window) is int
    assert config.rolling_window == 48


def test_collinear_cycles_are_explicitly_not_identifiable() -> None:
    api = _api()
    dates = pd.date_range("2015-01-31", periods=72, freq="ME")
    base = np.linspace(-2.0, 2.0, len(dates))
    cycle_wide = pd.DataFrame(
        {cycle_id: base * number for number, cycle_id in enumerate(CYCLE_IDS, 1)},
        index=dates,
    )
    cycles = (
        cycle_wide.rename_axis("date")
        .reset_index()
        .melt(
            id_vars="date",
            var_name="cycle_id",
            value_name="innovation",
        )
    )
    channels = pd.DataFrame(
        {
            "date": dates,
            "channel_id": "liquidity_credit",
            "innovation": 0.4 + 0.8 * base,
        }
    )
    config = _config(
        api,
        min_training_count=24,
        condition_number_threshold=100.0,
    )

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result)
    covariance = _latest_covariance(result)
    assert latest["status"].eq("not_identifiable").all()
    assert bool((latest["condition_number"] > 100.0).all())
    assert latest["coefficient_mean"].isna().all()
    assert latest["contribution"].isna().all()
    assert latest["predicted_channel_innovation"].isna().all()
    assert latest["channel_residual"].isna().all()
    assert covariance["status"].eq("not_identifiable").all()
    assert covariance["coefficient_covariance"].isna().all()


def test_constant_cycle_in_training_window_is_not_identifiable() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=96)
    training_dates = set(channels["date"].iloc[-49:-1])
    constant_cycle = cycles["cycle_id"].eq("C3") & cycles["date"].isin(training_dates)
    cycles.loc[constant_cycle, "innovation"] = 1.25
    config = _config(
        api,
        window="rolling",
        rolling_window=48,
        min_training_count=36,
    )

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result)
    covariance = _latest_covariance(result)
    assert latest["status"].eq("not_identifiable").all()
    assert np.isinf(latest["condition_number"]).all()
    assert latest["coefficient_mean"].isna().all()
    assert latest["contribution"].isna().all()
    assert latest["predicted_channel_innovation"].isna().all()
    assert latest["channel_residual"].isna().all()
    assert covariance["status"].eq("not_identifiable").all()
    assert covariance["coefficient_covariance"].isna().all()


def test_missing_current_cycle_input_is_marked_unavailable() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=96)
    latest_date = channels["date"].iloc[-1]
    missing = cycles["date"].eq(latest_date) & cycles["cycle_id"].eq("C4")
    cycles.loc[missing, "innovation"] = np.nan
    config = _config(api, min_training_count=36)

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result).set_index("cycle_id").loc[list(CYCLE_IDS)]
    assert latest["status"].eq("unavailable").all()
    assert np.isnan(latest.loc["C4", "cycle_innovation"])
    assert latest["coefficient_mean"].notna().all()
    assert latest["contribution"].isna().all()
    assert latest["predicted_channel_innovation"].isna().all()
    assert latest["channel_residual"].isna().all()
    assert latest["training_end"].max() < latest["date"].min()


def test_channels_are_estimated_independently_with_mixed_current_availability() -> None:
    api = _api()
    cycles, growth_channel, _, _ = _synthetic_innovations(count=96)
    inflation_channel = growth_channel.copy(deep=True)
    inflation_channel["channel_id"] = "inflation_prices"
    inflation_channel["innovation"] = -0.4 * inflation_channel["innovation"] + 0.2
    inflation_channel.loc[inflation_channel.index[-1], "innovation"] = np.nan
    channels = pd.concat(
        [growth_channel, inflation_channel],
        ignore_index=True,
    )
    config = _config(api, min_training_count=36)

    combined = api.estimate_cycle_to_channel(cycles, channels, config=config)
    growth_only = api.estimate_cycle_to_channel(
        cycles,
        growth_channel,
        config=config,
    )

    latest_date = growth_channel["date"].iloc[-1]
    latest_paths = combined.paths.loc[combined.paths["date"].eq(latest_date)]
    latest_covariance = combined.covariance.loc[
        combined.covariance["date"].eq(latest_date)
    ]
    assert latest_paths.groupby("channel_id").size().eq(7).all()
    assert latest_covariance.groupby("channel_id").size().eq(49).all()
    assert (
        latest_paths.loc[
            latest_paths["channel_id"].eq("growth_activity"),
            "status",
        ]
        .eq("estimated")
        .all()
    )
    assert (
        latest_paths.loc[
            latest_paths["channel_id"].eq("inflation_prices"),
            "status",
        ]
        .eq("unavailable")
        .all()
    )
    combined_growth_paths = combined.paths.loc[
        combined.paths["channel_id"].eq("growth_activity")
    ].reset_index(drop=True)
    combined_growth_covariance = combined.covariance.loc[
        combined.covariance["channel_id"].eq("growth_activity")
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        combined_growth_paths,
        growth_only.paths.reset_index(drop=True),
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        combined_growth_covariance,
        growth_only.covariance.reset_index(drop=True),
        check_exact=True,
    )


def test_no_date_intersection_emits_unavailable_groups_without_training() -> None:
    api = _api()
    cycles, _, _, _ = _synthetic_innovations(count=24)
    channel_dates = pd.date_range("2030-01-31", periods=3, freq="ME")
    channels = pd.DataFrame(
        {
            "date": channel_dates,
            "channel_id": "growth_activity",
            "innovation": [0.1, 0.2, 0.3],
        }
    )

    result = api.estimate_cycle_to_channel(
        cycles,
        channels,
        config=_config(api, min_training_count=12),
    )

    assert result.paths.groupby(["date", "channel_id"]).size().eq(7).all()
    assert result.covariance.groupby(["date", "channel_id"]).size().eq(49).all()
    assert result.paths["status"].eq("unavailable").all()
    assert result.covariance["status"].eq("unavailable").all()
    assert result.paths["cycle_innovation"].isna().all()
    assert result.paths["predicted_channel_innovation"].isna().all()
    assert result.paths["training_count"].eq(0).all()
    assert result.covariance["training_count"].eq(0).all()
    assert result.paths["training_start"].isna().all()
    assert result.paths["training_end"].isna().all()


def test_insufficient_history_preserves_full_output_shape() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=20)
    config = _config(api, min_training_count=24)

    result = api.estimate_cycle_to_channel(cycles, channels, config=config)

    latest = _latest_paths(result)
    covariance = _latest_covariance(result)
    assert len(latest) == 7
    assert len(covariance) == 49
    assert latest["status"].eq("insufficient_history").all()
    assert latest["coefficient_mean"].isna().all()
    assert covariance["coefficient_covariance"].isna().all()


def test_result_frames_are_frozen_and_defensively_copied() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=72)
    result = api.estimate_cycle_to_channel(
        cycles,
        channels,
        config=_config(api, min_training_count=30),
    )
    original_path = float(_latest_paths(result)["coefficient_mean"].iloc[0])
    original_covariance = float(
        _latest_covariance(result)["coefficient_covariance"].iloc[0]
    )

    detached_paths = result.paths
    detached_covariance = result.covariance
    detached_paths.loc[detached_paths.index[-1], "coefficient_mean"] = 999.0
    detached_covariance.loc[detached_covariance.index[-1], "coefficient_covariance"] = (
        999.0
    )

    assert float(_latest_paths(result)["coefficient_mean"].iloc[0]) == original_path
    assert (
        float(_latest_covariance(result)["coefficient_covariance"].iloc[0])
        == original_covariance
    )
    with pytest.raises(FrozenInstanceError):
        result.paths = pd.DataFrame()


def test_input_contract_rejects_duplicates_incomplete_cycles_and_infinity() -> None:
    api = _api()
    cycles, channels, _, _ = _synthetic_innovations(count=48)
    config = _config(api, min_training_count=24)

    duplicate_cycles = pd.concat([cycles, cycles.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="date.*cycle_id.*unique"):
        api.estimate_cycle_to_channel(
            duplicate_cycles,
            channels,
            config=config,
        )

    incomplete_cycles = cycles.loc[cycles["cycle_id"].ne("C7")]
    with pytest.raises(ValueError, match="exactly C1 through C7"):
        api.estimate_cycle_to_channel(
            incomplete_cycles,
            channels,
            config=config,
        )

    duplicate_channels = pd.concat(
        [channels, channels.iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="date.*channel_id.*unique"):
        api.estimate_cycle_to_channel(
            cycles,
            duplicate_channels,
            config=config,
        )

    infinite_channels = channels.copy(deep=True)
    infinite_channels.loc[0, "innovation"] = np.inf
    with pytest.raises(ValueError, match="finite or missing"):
        api.estimate_cycle_to_channel(
            cycles,
            infinite_channels,
            config=config,
        )
