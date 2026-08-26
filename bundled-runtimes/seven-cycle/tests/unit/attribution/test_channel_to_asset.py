from dataclasses import FrozenInstanceError
from importlib import import_module
from types import ModuleType

import numpy as np
import pandas as pd
import pytest


REQUIRED_API = (
    "CHANNEL_TO_ASSET_COMPONENT_COLUMNS",
    "CHANNEL_TO_ASSET_COVARIANCE_COLUMNS",
    "CHANNEL_TO_ASSET_POSTERIOR_COLUMNS",
    "ChannelToAssetResult",
    "HierarchicalTVPConfig",
    "estimate_channel_to_asset",
)


def _api() -> ModuleType:
    module = import_module("seven_cycle_platform.attribution")
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"Task 15 public API is missing: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _config(api: ModuleType, **updates: object) -> object:
    values: dict[str, object] = {
        "window": "expanding",
        "rolling_window": None,
        "min_asset_training_count": 18,
        "min_parent_training_count": 24,
        "root_ridge": 1.0,
        "industry_prior_strength": 12.0,
        "asset_prior_strength": 18.0,
        "condition_number_threshold": 10_000.0,
        "forgetting_factor": 1.0,
    }
    values.update(updates)
    return api.HierarchicalTVPConfig(**values)


def _synthetic_fixture(
    *,
    count: int = 84,
    proxy_history: int = 14,
    seed: int = 20260713,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, float],
]:
    generator = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-31", periods=count, freq="ME")
    asset_ids = ("long_asset", "proxy_asset", "bank_asset", "bond_asset")
    growth = generator.normal(size=count)
    inflation = 0.25 * growth + generator.normal(size=count)
    channel_innovations = pd.DataFrame(
        {
            "date": np.repeat(dates, 2),
            "channel_id": np.tile(["growth", "inflation"], count),
            "innovation": np.column_stack([growth, inflation]).reshape(-1),
        }
    )
    stable_interaction = growth * inflation
    interactions = pd.DataFrame(
        {
            "date": np.repeat(dates, 2),
            "interaction_id": np.tile(["growth_x_inflation", "unvalidated"], count),
            "value": np.column_stack(
                [stable_interaction, generator.normal(size=count)]
            ).reshape(-1),
            "validated": np.tile([True, False], count),
        }
    )
    hierarchy = pd.DataFrame(
        [
            ("long_asset", "equity", "software", False, 0.0),
            ("proxy_asset", "equity", "software", True, 0.65),
            ("bank_asset", "equity", "banks", False, 0.0),
            ("bond_asset", "fixed_income", "government", False, 0.0),
        ],
        columns=[
            "asset_id",
            "asset_class_id",
            "industry_id",
            "is_proxy",
            "confidence_discount",
        ],
    )
    benchmark: dict[str, np.ndarray] = {}
    controls_values: dict[str, np.ndarray] = {}
    event_values: dict[str, np.ndarray] = {}
    for position, asset_id in enumerate(asset_ids):
        benchmark[asset_id] = 0.35 * growth + generator.normal(
            scale=0.75 + 0.05 * position, size=count
        )
        controls_values[asset_id] = generator.normal(size=count)
        event = generator.binomial(1, 0.08, size=count).astype("float64")
        event[-1] = 1.0 + 0.1 * position
        event_values[asset_id] = event
    controls = pd.DataFrame(
        [
            (date, asset_id, "momentum", controls_values[asset_id][date_position])
            for date_position, date in enumerate(dates)
            for asset_id in asset_ids
        ],
        columns=["date", "asset_id", "control_id", "value"],
    )
    event_shocks = pd.DataFrame(
        [
            (date, asset_id, "policy", event_values[asset_id][date_position])
            for date_position, date in enumerate(dates)
            for asset_id in asset_ids
        ],
        columns=["date", "asset_id", "event_id", "value"],
    )
    growth_coefficients = {
        "long_asset": 1.20,
        "proxy_asset": -0.80,
        "bank_asset": 0.30,
        "bond_asset": -0.20,
    }
    return_rows: list[dict[str, object]] = []
    for asset_id in asset_ids:
        start = count - proxy_history if asset_id == "proxy_asset" else 0
        for date_position in range(start, count):
            observed = (
                0.05
                + 0.28 * benchmark[asset_id][date_position]
                + growth_coefficients[asset_id] * growth[date_position]
                - 0.35 * inflation[date_position]
                + 0.18 * stable_interaction[date_position]
                + 0.12 * controls_values[asset_id][date_position]
                + 0.45 * event_values[asset_id][date_position]
                + generator.normal(scale=0.025)
            )
            return_rows.append(
                {
                    "date": dates[date_position],
                    "asset_id": asset_id,
                    "return": observed,
                    "benchmark_return": benchmark[asset_id][date_position],
                }
            )
    asset_returns = pd.DataFrame(return_rows)
    return (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        growth_coefficients,
    )


def _estimate_fixture(api: ModuleType, **config_updates: object) -> object:
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    return api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api, **config_updates),
    )


def _latest_asset_posterior(result: object, asset_id: str) -> pd.DataFrame:
    posteriors = result.posteriors
    latest_date = posteriors["date"].max()
    return posteriors.loc[
        posteriors["date"].eq(latest_date)
        & posteriors["node_level"].eq("asset")
        & posteriors["node_id"].eq(asset_id)
    ].reset_index(drop=True)


def _low_level_parent() -> object:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    return hierarchy_module.HierarchicalPosterior(
        mean=np.asarray([0.25, 0.70], dtype="float64"),
        covariance=np.asarray([[0.20, 0.03], [0.03, 0.10]], dtype="float64"),
        parent_mean=np.asarray([np.nan, np.nan], dtype="float64"),
        training_count=40,
        effective_training_count=40.0,
        condition_number=1.5,
        prior_precision=1.0,
        own_weight=1.0,
        parent_weight=0.0,
        confidence=0.8,
        status="estimated",
    )


def test_public_api_and_hierarchical_shrinkage_contract() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        truth,
    ) = _synthetic_fixture()

    config = _config(api)
    result = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=config,
    )

    assert tuple(result.components.columns) == api.CHANNEL_TO_ASSET_COMPONENT_COLUMNS
    assert tuple(result.posteriors.columns) == api.CHANNEL_TO_ASSET_POSTERIOR_COLUMNS
    assert tuple(result.covariance.columns) == api.CHANNEL_TO_ASSET_COVARIANCE_COLUMNS
    long_growth = (
        _latest_asset_posterior(result, "long_asset")
        .query("component_type == 'channel' and component_id == 'growth'")
        .iloc[0]
    )
    proxy_growth = (
        _latest_asset_posterior(result, "proxy_asset")
        .query("component_type == 'channel' and component_id == 'growth'")
        .iloc[0]
    )

    assert long_growth["status"] == "estimated"
    assert proxy_growth["status"] == "parent_informed"
    assert long_growth["own_weight"] > proxy_growth["own_weight"]
    assert long_growth["parent_weight"] < proxy_growth["parent_weight"]
    assert abs(long_growth["coefficient_mean"] - truth["long_asset"]) < abs(
        long_growth["parent_coefficient_mean"] - truth["long_asset"]
    )
    assert abs(
        proxy_growth["coefficient_mean"] - proxy_growth["parent_coefficient_mean"]
    ) < abs(proxy_growth["coefficient_mean"] - truth["proxy_asset"])
    assert proxy_growth["confidence"] < long_growth["confidence"]
    assert proxy_growth["proxy_discount"] == pytest.approx(0.65)
    assert long_growth["proxy_discount"] == pytest.approx(0.0)
    assert long_growth["effective_training_count"] == pytest.approx(
        long_growth["training_count"]
    )
    assert proxy_growth["effective_training_count"] == pytest.approx(
        proxy_growth["training_count"] * 0.35
    )
    assert proxy_growth["prior_precision"] == pytest.approx(config.asset_prior_strength)


def test_components_are_explicit_and_conserve_observed_returns() -> None:
    api = _api()
    result = _estimate_fixture(api)
    components = result.components
    latest_date = components["date"].max()
    latest = components.loc[components["date"].eq(latest_date)]

    assert {
        "intercept",
        "benchmark",
        "channel",
        "interaction",
        "control",
        "event",
        "residual",
    }.issubset(set(latest["component_type"]))
    assert "unvalidated" not in set(
        latest.loc[latest["component_type"].eq("interaction"), "component_id"]
    )
    for _, group in latest.groupby("asset_id", sort=False):
        predicted = float(group["predicted_return"].iloc[0])
        observed = float(group["observed_return"].iloc[0])
        residual = float(group["asset_residual"].iloc[0])
        non_residual = group.loc[group["component_type"].ne("residual")]
        residual_row = group.loc[group["component_type"].eq("residual")].iloc[0]
        assert predicted == pytest.approx(
            float(non_residual["contribution"].sum()), abs=1e-10
        )
        assert observed == pytest.approx(predicted + residual, abs=1e-10)
        assert residual_row["contribution"] == pytest.approx(residual, abs=1e-10)
        assert group["training_end"].max() < latest_date


def test_three_level_posteriors_and_covariance_are_complete() -> None:
    api = _api()
    result = _estimate_fixture(api)
    posteriors = result.posteriors
    covariance = result.covariance
    latest_date = posteriors["date"].max()
    latest_posteriors = posteriors.loc[posteriors["date"].eq(latest_date)]
    latest_covariance = covariance.loc[covariance["date"].eq(latest_date)]

    assert set(latest_posteriors["node_level"]) == {
        "asset_class",
        "industry",
        "asset",
    }
    assert set(
        latest_posteriors.loc[
            latest_posteriors["node_level"].eq("asset_class"), "node_id"
        ]
    ) == {"equity", "fixed_income"}
    assert set(
        latest_posteriors.loc[latest_posteriors["node_level"].eq("industry"), "node_id"]
    ) == {"software", "banks", "government"}
    assert set(
        latest_posteriors.loc[latest_posteriors["node_level"].eq("asset"), "node_id"]
    ) == {"long_asset", "proxy_asset", "bank_asset", "bond_asset"}
    assert (
        latest_posteriors.loc[
            latest_posteriors["node_level"].ne("asset"), "proxy_discount"
        ]
        .eq(0.0)
        .all()
    )
    for keys, posterior_group in latest_posteriors.groupby(
        ["node_level", "node_id"], sort=False
    ):
        covariance_group = latest_covariance.loc[
            latest_covariance["node_level"].eq(keys[0])
            & latest_covariance["node_id"].eq(keys[1])
        ]
        component_count = len(posterior_group)
        assert len(covariance_group) == component_count**2
        labels = list(
            zip(
                posterior_group["component_type"],
                posterior_group["component_id"],
                strict=True,
            )
        )
        matrix = covariance_group.assign(
            component_i=list(
                zip(
                    covariance_group["component_i_type"],
                    covariance_group["component_i_id"],
                    strict=True,
                )
            ),
            component_j=list(
                zip(
                    covariance_group["component_j_type"],
                    covariance_group["component_j_id"],
                    strict=True,
                )
            ),
        ).pivot(
            index="component_i",
            columns="component_j",
            values="coefficient_covariance",
        )
        matrix = matrix.loc[labels, labels].to_numpy(dtype="float64")
        np.testing.assert_allclose(matrix, matrix.T, atol=1e-10, rtol=0.0)
        assert np.linalg.eigvalsh(matrix).min() >= -1e-10


def test_posterior_and_result_reject_indefinite_covariance() -> None:
    api = _api()
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    with pytest.raises(ValueError, match="positive semidefinite"):
        hierarchy_module.HierarchicalPosterior(
            mean=np.asarray([0.1, 0.2]),
            covariance=np.asarray([[1.0, 2.0], [2.0, 1.0]]),
            parent_mean=np.asarray([np.nan, np.nan]),
            training_count=24,
            effective_training_count=24.0,
            condition_number=2.0,
            prior_precision=1.0,
            own_weight=1.0,
            parent_weight=0.0,
            confidence=0.8,
            status="estimated",
        )

    result = _estimate_fixture(api)
    covariance = result.covariance
    latest_date = covariance["date"].max()
    node_mask = (
        covariance["date"].eq(latest_date)
        & covariance["node_level"].eq("asset")
        & covariance["node_id"].eq("long_asset")
    )
    node_group = covariance.loc[node_mask]
    labels = list(
        dict.fromkeys(
            zip(
                node_group["component_i_type"],
                node_group["component_i_id"],
                strict=True,
            )
        )
    )
    first, second = labels[:2]
    covariance.loc[
        node_mask
        & covariance["component_i_type"].eq(first[0])
        & covariance["component_i_id"].eq(first[1])
        & covariance["component_j_type"].eq(first[0])
        & covariance["component_j_id"].eq(first[1]),
        "coefficient_covariance",
    ] = 1.0
    covariance.loc[
        node_mask
        & covariance["component_i_type"].eq(second[0])
        & covariance["component_i_id"].eq(second[1])
        & covariance["component_j_type"].eq(second[0])
        & covariance["component_j_id"].eq(second[1]),
        "coefficient_covariance",
    ] = 1.0
    cross_mask = node_mask & (
        (
            covariance["component_i_type"].eq(first[0])
            & covariance["component_i_id"].eq(first[1])
            & covariance["component_j_type"].eq(second[0])
            & covariance["component_j_id"].eq(second[1])
        )
        | (
            covariance["component_i_type"].eq(second[0])
            & covariance["component_i_id"].eq(second[1])
            & covariance["component_j_type"].eq(first[0])
            & covariance["component_j_id"].eq(first[1])
        )
    )
    covariance.loc[cross_mask, "coefficient_covariance"] = 2.0
    with pytest.raises(ValueError, match="positive semidefinite"):
        api.ChannelToAssetResult(
            components=result.components,
            posteriors=result.posteriors,
            covariance=covariance,
        )


def test_future_inputs_and_future_validation_do_not_rewrite_history() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture(count=76)
    cutoff = asset_returns["date"].sort_values().unique()[55]
    changed_returns = asset_returns.copy(deep=True)
    changed_returns.loc[changed_returns["date"].gt(cutoff), "return"] += 100.0
    changed_channels = channel_innovations.copy(deep=True)
    changed_channels.loc[changed_channels["date"].gt(cutoff), "innovation"] -= 75.0
    future_dates = pd.DatetimeIndex(
        sorted(interactions.loc[interactions["date"].gt(cutoff), "date"].unique())
    )
    future_interaction = pd.DataFrame(
        {
            "date": future_dates,
            "interaction_id": "future_approved",
            "value": np.linspace(1.0, 2.0, len(future_dates)),
            "validated": True,
        }
    )
    changed_interactions = pd.concat(
        [interactions, future_interaction], ignore_index=True
    )
    config = _config(api)

    baseline = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=config,
    )
    changed = api.estimate_channel_to_asset(
        changed_returns,
        changed_channels,
        hierarchy,
        interactions=changed_interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=config,
    )

    for field in ("components", "posteriors", "covariance"):
        baseline_frame = getattr(baseline, field)
        changed_frame = getattr(changed, field)
        pd.testing.assert_frame_equal(
            baseline_frame.loc[baseline_frame["date"].le(cutoff)].reset_index(
                drop=True
            ),
            changed_frame.loc[changed_frame["date"].le(cutoff)].reset_index(drop=True),
            check_exact=True,
        )
    historical_interactions = changed.components.loc[
        changed.components["date"].le(cutoff)
        & changed.components["component_type"].eq("interaction")
    ]
    assert "future_approved" not in set(historical_interactions["component_id"])


def test_latest_only_asset_features_do_not_pollute_training_universe() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    latest_date = asset_returns["date"].max()
    baseline = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )
    changed_controls = pd.concat(
        [
            controls,
            pd.DataFrame(
                [[latest_date, "long_asset", "new_control", 1.25]],
                columns=controls.columns,
            ),
        ],
        ignore_index=True,
    )
    changed_events = pd.concat(
        [
            event_shocks,
            pd.DataFrame(
                [[latest_date, "long_asset", "new_event", -0.75]],
                columns=event_shocks.columns,
            ),
        ],
        ignore_index=True,
    )

    changed = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=changed_controls,
        event_shocks=changed_events,
        config=_config(api),
    )

    pd.testing.assert_frame_equal(
        baseline.posteriors, changed.posteriors, check_exact=True
    )
    pd.testing.assert_frame_equal(
        baseline.covariance, changed.covariance, check_exact=True
    )
    long_components = changed.components.loc[
        changed.components["date"].eq(latest_date)
        & changed.components["asset_id"].eq("long_asset")
    ]
    pending = long_components.loc[
        long_components["component_id"].isin({"new_control", "new_event"})
    ]
    assert set(pending["component_id"]) == {"new_control", "new_event"}
    assert pending["coefficient_mean"].isna().all()
    assert pending["contribution"].isna().all()
    assert long_components["status"].eq("unavailable").all()
    assert long_components["predicted_return"].isna().all()
    for asset_id in ("proxy_asset", "bank_asset", "bond_asset"):
        baseline_group = baseline.components.loc[
            baseline.components["date"].eq(latest_date)
            & baseline.components["asset_id"].eq(asset_id)
        ].reset_index(drop=True)
        changed_group = changed.components.loc[
            changed.components["date"].eq(latest_date)
            & changed.components["asset_id"].eq(asset_id)
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(baseline_group, changed_group, check_exact=True)


def test_first_current_validated_interaction_is_pending_not_trained() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    latest_date = asset_returns["date"].max()
    baseline = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )
    changed_interactions = pd.concat(
        [
            interactions,
            pd.DataFrame(
                [[latest_date, "first_validated_now", 0.8, True]],
                columns=interactions.columns,
            ),
        ],
        ignore_index=True,
    )

    changed = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=changed_interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )

    pd.testing.assert_frame_equal(
        baseline.posteriors, changed.posteriors, check_exact=True
    )
    pd.testing.assert_frame_equal(
        baseline.covariance, changed.covariance, check_exact=True
    )
    latest_components = changed.components.loc[
        changed.components["date"].eq(latest_date)
    ]
    pending = latest_components.loc[
        latest_components["component_id"].eq("first_validated_now")
    ]
    assert set(pending["asset_id"]) == set(asset_returns["asset_id"])
    assert pending["component_type"].eq("interaction").all()
    assert pending["coefficient_mean"].isna().all()
    assert pending["contribution"].isna().all()
    assert latest_components["status"].eq("unavailable").all()
    assert latest_components["predicted_return"].isna().all()


def test_current_return_only_changes_observed_and_residual() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture(count=72)
    current_date = asset_returns["date"].max()
    changed_returns = asset_returns.copy(deep=True)
    selected = changed_returns["date"].eq(current_date) & changed_returns[
        "asset_id"
    ].eq("long_asset")
    changed_returns.loc[selected, "return"] += 25.0
    config = _config(api)
    baseline = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=config,
    )
    changed = api.estimate_channel_to_asset(
        changed_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=config,
    )

    pd.testing.assert_frame_equal(
        baseline.posteriors, changed.posteriors, check_exact=True
    )
    pd.testing.assert_frame_equal(
        baseline.covariance, changed.covariance, check_exact=True
    )
    base_group = baseline.components.loc[
        baseline.components["date"].eq(current_date)
        & baseline.components["asset_id"].eq("long_asset")
    ].reset_index(drop=True)
    changed_group = changed.components.loc[
        changed.components["date"].eq(current_date)
        & changed.components["asset_id"].eq("long_asset")
    ].reset_index(drop=True)
    assert changed_group["observed_return"].iloc[0] - base_group[
        "observed_return"
    ].iloc[0] == pytest.approx(25.0)
    assert changed_group["asset_residual"].iloc[0] - base_group["asset_residual"].iloc[
        0
    ] == pytest.approx(25.0)
    assert changed_group["predicted_return"].iloc[0] == pytest.approx(
        base_group["predicted_return"].iloc[0], abs=0.0
    )
    non_residual = base_group["component_type"].ne("residual")
    pd.testing.assert_series_equal(
        base_group.loc[non_residual, "contribution"].reset_index(drop=True),
        changed_group.loc[non_residual, "contribution"].reset_index(drop=True),
        check_exact=True,
    )


def test_parent_only_asset_is_still_predicted_from_industry() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    current_date = asset_returns["date"].max()
    new_return = pd.DataFrame(
        {
            "date": [current_date],
            "asset_id": ["new_proxy"],
            "return": [0.15],
            "benchmark_return": [0.04],
        }
    )
    asset_returns = pd.concat([asset_returns, new_return], ignore_index=True)
    hierarchy = pd.concat(
        [
            hierarchy,
            pd.DataFrame(
                [["new_proxy", "equity", "software", True, 0.2]],
                columns=hierarchy.columns,
            ),
        ],
        ignore_index=True,
    )

    result = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )

    posterior = _latest_asset_posterior(result, "new_proxy")
    components = result.components.loc[
        result.components["date"].eq(current_date)
        & result.components["asset_id"].eq("new_proxy")
    ]
    assert posterior["status"].eq("parent_only").all()
    assert posterior["training_count"].eq(0).all()
    non_intercept = posterior["component_type"].ne("intercept")
    np.testing.assert_allclose(
        posterior.loc[non_intercept, "coefficient_mean"],
        posterior.loc[non_intercept, "parent_coefficient_mean"],
        atol=0.0,
        rtol=0.0,
    )
    assert components["status"].eq("parent_only").all()
    assert np.isfinite(components["predicted_return"]).all()


def test_rolling_and_forgetting_track_recent_regime() -> None:
    api = _api()
    generator = np.random.default_rng(9182)
    dates = pd.date_range("2012-01-31", periods=90, freq="ME")
    channel = generator.normal(size=len(dates))
    benchmark = generator.normal(scale=0.4, size=len(dates))
    coefficient = np.where(np.arange(len(dates)) < 66, 0.2, 1.4)
    peer_return = 0.03 + 0.35 * channel + 0.1 * benchmark
    long_return = 0.02 + coefficient * channel + 0.1 * benchmark
    asset_returns = pd.DataFrame(
        {
            "date": np.repeat(dates, 2),
            "asset_id": np.tile(["long_asset", "peer_asset"], len(dates)),
            "return": np.column_stack([long_return, peer_return]).reshape(-1),
            "benchmark_return": np.column_stack([benchmark, benchmark]).reshape(-1),
        }
    )
    channels = pd.DataFrame(
        {"date": dates, "channel_id": "growth", "innovation": channel}
    )
    hierarchy = pd.DataFrame(
        [
            ("long_asset", "equity", "software", False, 0.0),
            ("peer_asset", "equity", "software", False, 0.0),
        ],
        columns=[
            "asset_id",
            "asset_class_id",
            "industry_id",
            "is_proxy",
            "confidence_discount",
        ],
    )
    expanding = api.estimate_channel_to_asset(
        asset_returns,
        channels,
        hierarchy,
        config=_config(
            api,
            min_asset_training_count=12,
            min_parent_training_count=12,
            industry_prior_strength=2.0,
            asset_prior_strength=2.0,
        ),
    )
    adaptive = api.estimate_channel_to_asset(
        asset_returns,
        channels,
        hierarchy,
        config=_config(
            api,
            window="rolling",
            rolling_window=24,
            min_asset_training_count=12,
            min_parent_training_count=12,
            industry_prior_strength=2.0,
            asset_prior_strength=2.0,
            forgetting_factor=0.85,
        ),
    )
    expanding_growth = (
        _latest_asset_posterior(expanding, "long_asset")
        .query("component_type == 'channel' and component_id == 'growth'")
        .iloc[0]
    )
    adaptive_growth = (
        _latest_asset_posterior(adaptive, "long_asset")
        .query("component_type == 'channel' and component_id == 'growth'")
        .iloc[0]
    )

    assert abs(adaptive_growth["coefficient_mean"] - 1.4) < abs(
        expanding_growth["coefficient_mean"] - 1.4
    )
    assert adaptive_growth["training_count"] == 24
    assert adaptive_growth["effective_training_count"] < 24
    assert adaptive_growth["window"] == "rolling"
    assert adaptive_growth["forgetting_factor"] == pytest.approx(0.85)


def test_constant_feature_is_explicitly_not_identifiable() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    latest_date = asset_returns["date"].max()
    constant = channel_innovations["channel_id"].eq("growth") & channel_innovations[
        "date"
    ].lt(latest_date)
    channel_innovations.loc[constant, "innovation"] = 1.0

    result = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )

    root = result.posteriors.loc[
        result.posteriors["date"].eq(latest_date)
        & result.posteriors["node_level"].eq("asset_class")
        & result.posteriors["node_id"].eq("equity")
    ]
    industry = result.posteriors.loc[
        result.posteriors["date"].eq(latest_date)
        & result.posteriors["node_level"].eq("industry")
        & result.posteriors["node_id"].eq("software")
    ]
    asset = _latest_asset_posterior(result, "long_asset")
    assert root["status"].eq("not_identifiable").all()
    assert np.isinf(root["condition_number"]).all()
    assert root["coefficient_mean"].isna().all()
    assert industry["status"].eq("not_identifiable").all()
    assert industry["coefficient_mean"].isna().all()
    assert asset["status"].eq("not_identifiable").all()
    assert np.isinf(asset["condition_number"]).all()
    assert asset["coefficient_mean"].isna().all()
    failed_nodes = result.covariance.loc[
        result.covariance["date"].eq(latest_date)
        & (
            (
                result.covariance["node_level"].eq("asset_class")
                & result.covariance["node_id"].eq("equity")
            )
            | (
                result.covariance["node_level"].eq("industry")
                & result.covariance["node_id"].eq("software")
            )
            | (
                result.covariance["node_level"].eq("asset")
                & result.covariance["node_id"].eq("long_asset")
            )
        )
    ]
    assert failed_nodes["coefficient_covariance"].isna().all()
    components = result.components.loc[
        result.components["date"].eq(latest_date)
        & result.components["asset_id"].eq("long_asset")
    ]
    assert components["status"].eq("not_identifiable").all()
    assert components["predicted_return"].isna().all()
    assert components["contribution"].isna().all()


def test_unidentifiable_asset_design_falls_back_to_valid_parent_only() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    latest_date = asset_returns["date"].max()
    proxy_dates = set(
        asset_returns.loc[
            asset_returns["asset_id"].eq("proxy_asset")
            & asset_returns["date"].lt(latest_date),
            "date",
        ]
    )
    constant_proxy_history = channel_innovations["channel_id"].eq(
        "growth"
    ) & channel_innovations["date"].isin(proxy_dates)
    channel_innovations.loc[constant_proxy_history, "innovation"] = 1.0

    result = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )

    proxy = _latest_asset_posterior(result, "proxy_asset")
    parent = result.posteriors.loc[
        result.posteriors["date"].eq(latest_date)
        & result.posteriors["node_level"].eq("industry")
        & result.posteriors["node_id"].eq("software")
    ].reset_index(drop=True)
    assert parent["status"].eq("estimated").all()
    assert proxy["status"].eq("parent_only").all()
    assert np.isinf(proxy["condition_number"]).all()
    assert proxy["own_weight"].eq(0.0).all()
    assert proxy["parent_weight"].eq(1.0).all()
    np.testing.assert_allclose(
        proxy["coefficient_mean"],
        parent["coefficient_mean"],
        atol=0.0,
        rtol=0.0,
    )
    assert proxy["confidence"].max() < parent["confidence"].min()
    proxy_covariance = result.covariance.loc[
        result.covariance["date"].eq(latest_date)
        & result.covariance["node_level"].eq("asset")
        & result.covariance["node_id"].eq("proxy_asset"),
        "coefficient_covariance",
    ].reset_index(drop=True)
    parent_covariance = result.covariance.loc[
        result.covariance["date"].eq(latest_date)
        & result.covariance["node_level"].eq("industry")
        & result.covariance["node_id"].eq("software"),
        "coefficient_covariance",
    ].reset_index(drop=True)
    pd.testing.assert_series_equal(
        proxy_covariance,
        parent_covariance,
        check_exact=True,
        check_names=False,
    )


def test_missing_current_channel_marks_components_unavailable() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture()
    latest_date = asset_returns["date"].max()
    missing = channel_innovations["date"].eq(latest_date) & channel_innovations[
        "channel_id"
    ].eq("growth")
    channel_innovations.loc[missing, "innovation"] = np.nan

    result = api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions=interactions,
        controls=controls,
        event_shocks=event_shocks,
        config=_config(api),
    )

    latest = result.components.loc[result.components["date"].eq(latest_date)]
    assert latest["status"].eq("unavailable").all()
    assert latest["predicted_return"].isna().all()
    assert latest["asset_residual"].isna().all()
    assert latest["coefficient_mean"].notna().any()
    assert latest["training_end"].max() < latest_date


def test_asset_dates_before_first_channel_are_unavailable_without_schema_leakage() -> (
    None
):
    api = _api()
    dates = pd.date_range("2020-01-31", periods=18, freq="ME")
    asset_returns = pd.DataFrame(
        {
            "date": dates,
            "asset_id": "asset",
            "return": np.linspace(-0.2, 0.3, len(dates)),
            "benchmark_return": np.linspace(-0.1, 0.15, len(dates)),
        }
    )
    channels = pd.DataFrame(
        {
            "date": dates[-3:],
            "channel_id": "growth",
            "innovation": [0.1, 0.2, 0.3],
        }
    )
    hierarchy = pd.DataFrame(
        [["asset", "equity", "software", False, 0.0]],
        columns=[
            "asset_id",
            "asset_class_id",
            "industry_id",
            "is_proxy",
            "confidence_discount",
        ],
    )

    result = api.estimate_channel_to_asset(
        asset_returns,
        channels,
        hierarchy,
        config=_config(
            api,
            min_asset_training_count=6,
            min_parent_training_count=8,
        ),
    )

    historical = result.components.loc[result.components["date"].lt(dates[-3])]
    assert historical["status"].eq("unavailable").all()
    assert historical["predicted_return"].isna().all()
    assert "growth" not in set(historical["component_id"])
    first_channel_components = result.components.loc[
        result.components["date"].eq(dates[-3])
    ]
    first_channel = first_channel_components.loc[
        first_channel_components["component_id"].eq("growth")
    ]
    assert first_channel_components["status"].eq("unavailable").all()
    assert first_channel_components["predicted_return"].isna().all()
    assert first_channel["coefficient_mean"].isna().all()
    first_channel_posteriors = result.posteriors.loc[
        result.posteriors["date"].eq(dates[-3])
    ]
    assert "growth" not in set(first_channel_posteriors["component_id"])


def test_result_frames_are_frozen_and_defensively_copied() -> None:
    api = _api()
    result = _estimate_fixture(api)
    original_component = float(result.components["coefficient_mean"].dropna().iloc[-1])
    original_posterior = float(result.posteriors["coefficient_mean"].dropna().iloc[-1])
    original_covariance = float(
        result.covariance["coefficient_covariance"].dropna().iloc[-1]
    )

    components = result.components
    posteriors = result.posteriors
    covariance = result.covariance
    components.loc[components.index[-1], "coefficient_mean"] = 999.0
    posteriors.loc[posteriors.index[-1], "coefficient_mean"] = 999.0
    covariance.loc[covariance.index[-1], "coefficient_covariance"] = 999.0

    assert float(
        result.components["coefficient_mean"].dropna().iloc[-1]
    ) == pytest.approx(original_component)
    assert float(
        result.posteriors["coefficient_mean"].dropna().iloc[-1]
    ) == pytest.approx(original_posterior)
    assert float(
        result.covariance["coefficient_covariance"].dropna().iloc[-1]
    ) == pytest.approx(original_covariance)
    with pytest.raises(FrozenInstanceError):
        result.components = pd.DataFrame()


def test_input_validation_rejects_duplicates_conflicts_and_bad_values() -> None:
    api = _api()
    (
        asset_returns,
        channel_innovations,
        hierarchy,
        interactions,
        controls,
        event_shocks,
        _,
    ) = _synthetic_fixture(count=36)
    config = _config(
        api,
        min_asset_training_count=8,
        min_parent_training_count=10,
    )

    with pytest.raises(ValueError, match="date.*asset_id.*unique"):
        api.estimate_channel_to_asset(
            pd.concat([asset_returns, asset_returns.iloc[[0]]], ignore_index=True),
            channel_innovations,
            hierarchy,
            config=config,
        )
    with pytest.raises(ValueError, match="date.*channel_id.*unique"):
        api.estimate_channel_to_asset(
            asset_returns,
            pd.concat(
                [channel_innovations, channel_innovations.iloc[[0]]],
                ignore_index=True,
            ),
            hierarchy,
            config=config,
        )
    conflicting_hierarchy = pd.concat(
        [
            hierarchy,
            pd.DataFrame(
                [["conflict", "fixed_income", "software", False, 0.0]],
                columns=hierarchy.columns,
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="industry_id.*asset_class_id"):
        api.estimate_channel_to_asset(
            asset_returns,
            channel_innovations,
            conflicting_hierarchy,
            config=config,
        )
    non_proxy_discount = hierarchy.copy(deep=True)
    non_proxy_discount.loc[0, "confidence_discount"] = 0.1
    with pytest.raises(ValueError, match="non-proxy.*discount"):
        api.estimate_channel_to_asset(
            asset_returns,
            channel_innovations,
            non_proxy_discount,
            config=config,
        )
    proxy_index = hierarchy.index[hierarchy["is_proxy"]].item()
    for invalid_discount in (-0.01, 1.0):
        bad_proxy_discount = hierarchy.copy(deep=True)
        bad_proxy_discount.loc[proxy_index, "confidence_discount"] = invalid_discount
        with pytest.raises(ValueError, match="confidence_discount"):
            api.estimate_channel_to_asset(
                asset_returns,
                channel_innovations,
                bad_proxy_discount,
                config=config,
            )
    zero_proxy_discount = hierarchy.copy(deep=True)
    zero_proxy_discount.loc[proxy_index, "confidence_discount"] = 0.0
    api.estimate_channel_to_asset(
        asset_returns,
        channel_innovations,
        zero_proxy_discount,
        config=config,
    )
    overlapping_ids = hierarchy.copy(deep=True)
    overlapping_ids.loc[0, "asset_class_id"] = "long_asset"
    with pytest.raises(ValueError, match="hierarchy identifiers.*overlap"):
        api.estimate_channel_to_asset(
            asset_returns,
            channel_innovations,
            overlapping_ids,
            config=config,
        )
    infinite_channels = channel_innovations.copy(deep=True)
    infinite_channels.loc[0, "innovation"] = np.inf
    with pytest.raises(ValueError, match="finite or missing"):
        api.estimate_channel_to_asset(
            asset_returns,
            infinite_channels,
            hierarchy,
            config=config,
        )
    duplicate_controls = pd.concat([controls, controls.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="control_id.*unique"):
        api.estimate_channel_to_asset(
            asset_returns,
            channel_innovations,
            hierarchy,
            interactions=interactions,
            controls=duplicate_controls,
            event_shocks=event_shocks,
            config=config,
        )


def test_low_level_weighted_hierarchical_ridge_matches_closed_form() -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    parent = _low_level_parent()
    features = np.asarray([[0.0], [1.0], [2.0], [3.0]], dtype="float64")
    target = np.asarray([0.4, 1.0, 1.5, 2.3], dtype="float64")
    weights = np.full(len(target), 0.5, dtype="float64")
    prior_strength = 2.0
    feature_mean = np.average(features, axis=0, weights=weights)
    centered = features - feature_mean
    feature_scale = np.sqrt(
        np.sum(weights[:, None] * np.square(centered), axis=0) / weights.sum()
    )
    standardized = centered / feature_scale
    design = np.column_stack([np.ones(len(features)), standardized])
    penalty = np.diag([0.0, prior_strength])
    prior_mean = np.asarray([0.0, feature_scale[0] * parent.mean[1]])
    prior_covariance = np.zeros((2, 2), dtype="float64")
    prior_covariance[1, 1] = feature_scale[0] ** 2 * parent.covariance[1, 1]
    data_gram = design.T @ (weights[:, None] * design)
    inverse = np.linalg.pinv(data_gram + penalty, hermitian=True)
    standardized_mean = inverse @ (design.T @ (weights * target) + penalty @ prior_mean)
    residuals = target - design @ standardized_mean
    scores = design * (weights * residuals)[:, None]
    standardized_covariance = (
        inverse @ (scores.T @ scores + penalty @ prior_covariance @ penalty) @ inverse
    )
    transformation = np.asarray(
        [[1.0, -feature_mean[0] / feature_scale[0]], [0.0, 1.0 / feature_scale[0]]]
    )
    expected_mean = transformation @ standardized_mean
    expected_covariance = transformation @ standardized_covariance @ transformation.T
    expected_covariance = (expected_covariance + expected_covariance.T) / 2.0
    assert np.linalg.eigvalsh(expected_covariance).min() >= -1e-12

    discounted = hierarchy_module.fit_hierarchical_tvp_ridge(
        features,
        target,
        weights,
        min_training_count=2,
        prior_strength=prior_strength,
        condition_number_threshold=100.0,
        parent=parent,
        confidence_discount=0.5,
    )
    undiscounted = hierarchy_module.fit_hierarchical_tvp_ridge(
        features,
        target,
        np.ones(len(target), dtype="float64"),
        min_training_count=2,
        prior_strength=prior_strength,
        condition_number_threshold=100.0,
        parent=parent,
        confidence_discount=0.0,
    )

    np.testing.assert_allclose(discounted.mean, expected_mean, atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(
        discounted.covariance,
        expected_covariance,
        atol=1e-12,
        rtol=1e-12,
    )
    assert discounted.prior_precision == pytest.approx(prior_strength)
    assert discounted.own_weight == pytest.approx(0.5)
    assert discounted.parent_weight == pytest.approx(0.5)
    assert discounted.confidence == pytest.approx(0.9)
    assert discounted.confidence < undiscounted.confidence


def test_low_level_near_total_discount_remains_finite_without_double_shrink() -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    features = np.asarray([[0.0], [1.0], [2.0], [3.0]], dtype="float64")
    target = np.asarray([0.4, 1.0, 1.5, 2.3], dtype="float64")
    discount = 0.999999
    weights = np.full(len(target), 1.0 - discount, dtype="float64")

    posterior = hierarchy_module.fit_hierarchical_tvp_ridge(
        features,
        target,
        weights,
        min_training_count=2,
        prior_strength=2.0,
        condition_number_threshold=100.0,
        parent=_low_level_parent(),
        confidence_discount=discount,
    )

    assert posterior.status == "estimated"
    assert posterior.prior_precision == pytest.approx(2.0)
    assert np.isfinite(posterior.mean).all()
    assert np.isfinite(posterior.covariance).all()
    assert np.linalg.eigvalsh(posterior.covariance).min() >= -1e-10
    assert posterior.confidence > 0.79


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("min_training_count", True),
        ("min_training_count", 0),
        ("min_training_count", -1),
        ("prior_strength", True),
        ("prior_strength", 0.0),
        ("prior_strength", -1.0),
        ("prior_strength", np.nan),
        ("prior_strength", np.inf),
        ("condition_number_threshold", True),
        ("condition_number_threshold", 0.0),
        ("condition_number_threshold", -1.0),
        ("condition_number_threshold", np.nan),
        ("condition_number_threshold", np.inf),
        ("confidence_discount", True),
        ("confidence_discount", -0.01),
        ("confidence_discount", 1.0),
        ("confidence_discount", np.nan),
        ("confidence_discount", np.inf),
    ],
)
def test_low_level_fit_rejects_invalid_controls(
    parameter: str,
    value: object,
) -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    controls: dict[str, object] = {
        "min_training_count": 2,
        "prior_strength": 2.0,
        "condition_number_threshold": 100.0,
        "parent": _low_level_parent(),
        "confidence_discount": 0.0,
    }
    controls[parameter] = value

    with pytest.raises((TypeError, ValueError)):
        hierarchy_module.fit_hierarchical_tvp_ridge(
            np.asarray([[0.0], [1.0], [2.0], [3.0]]),
            np.asarray([0.4, 1.0, 1.5, 2.3]),
            np.ones(4),
            **controls,
        )


def test_low_level_fit_rejects_invalid_parent_type() -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")

    with pytest.raises(TypeError, match="parent.*HierarchicalPosterior"):
        hierarchy_module.fit_hierarchical_tvp_ridge(
            np.asarray([[0.0], [1.0], [2.0], [3.0]]),
            np.asarray([0.4, 1.0, 1.5, 2.3]),
            np.ones(4),
            min_training_count=2,
            prior_strength=2.0,
            condition_number_threshold=100.0,
            parent="invalid",
            confidence_discount=0.0,
        )


@pytest.mark.parametrize(
    ("features", "target", "weights"),
    [
        (np.ones(4), np.ones(4), np.ones(4)),
        (np.ones((4, 1)), np.ones((4, 1)), np.ones(4)),
        (np.ones((4, 1)), np.ones(4), np.ones((4, 1))),
        (np.ones((4, 1)), np.ones(3), np.ones(4)),
        (np.empty((0, 0)), np.empty(0), np.empty(0)),
    ],
)
def test_low_level_fit_rejects_invalid_observation_shapes(
    features: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
) -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")

    with pytest.raises(ValueError):
        hierarchy_module.fit_hierarchical_tvp_ridge(
            features,
            target,
            weights,
            min_training_count=2,
            prior_strength=2.0,
            condition_number_threshold=100.0,
            parent=None,
            confidence_discount=0.0,
        )


def test_low_level_empty_observations_have_explicit_status() -> None:
    hierarchy_module = import_module("seven_cycle_platform.attribution.hierarchy")
    features = np.empty((0, 1), dtype="float64")
    target = np.empty(0, dtype="float64")
    weights = np.empty(0, dtype="float64")

    root = hierarchy_module.fit_hierarchical_tvp_ridge(
        features,
        target,
        weights,
        min_training_count=2,
        prior_strength=2.0,
        condition_number_threshold=100.0,
        parent=None,
        confidence_discount=0.0,
    )
    child = hierarchy_module.fit_hierarchical_tvp_ridge(
        features,
        target,
        weights,
        min_training_count=2,
        prior_strength=2.0,
        condition_number_threshold=100.0,
        parent=_low_level_parent(),
        confidence_discount=0.5,
    )

    assert root.status == "insufficient_history"
    assert np.isnan(root.mean).all()
    assert child.status == "parent_only"
    np.testing.assert_allclose(child.mean, _low_level_parent().mean)
    assert child.confidence == pytest.approx(0.8 * 0.5 * 0.8)


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("window", "fixed"),
        ("rolling_window", 0),
        ("min_asset_training_count", True),
        ("min_parent_training_count", 0),
        ("root_ridge", 0.0),
        ("industry_prior_strength", np.inf),
        ("asset_prior_strength", -1.0),
        ("condition_number_threshold", 0.0),
        ("forgetting_factor", 1.01),
    ],
)
def test_config_rejects_invalid_parameters(parameter: str, value: object) -> None:
    api = _api()
    values: dict[str, object] = {
        "window": "rolling" if parameter == "rolling_window" else "expanding",
        "rolling_window": 24 if parameter != "rolling_window" else value,
        "min_asset_training_count": 12,
        "min_parent_training_count": 18,
        "root_ridge": 1.0,
        "industry_prior_strength": 4.0,
        "asset_prior_strength": 8.0,
        "condition_number_threshold": 1_000.0,
        "forgetting_factor": 1.0,
    }
    values[parameter] = value
    if values["window"] == "expanding":
        values["rolling_window"] = None

    with pytest.raises((TypeError, ValueError)):
        api.HierarchicalTVPConfig(**values)
