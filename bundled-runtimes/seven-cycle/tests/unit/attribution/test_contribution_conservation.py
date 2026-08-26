from dataclasses import FrozenInstanceError
from importlib import import_module
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest


CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))
REQUIRED_API = (
    "ATTRIBUTION_COMPONENT_COLUMNS",
    "ATTRIBUTION_PATH_COLUMNS",
    "AttributionContributionResult",
    "ContributionConfig",
    "IdentifiabilityConfig",
    "compose_attribution_paths",
)


def _api() -> ModuleType:
    module = import_module("seven_cycle_platform.attribution")
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"Task 16 contribution API is missing: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _stage1_paths(
    *,
    history_count: int = 24,
    correlated: bool = False,
    seed: int = 20260713,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    generator = np.random.default_rng(seed)
    dates = pd.date_range("2019-01-31", periods=history_count + 1, freq="ME")
    innovations = generator.normal(size=(history_count + 1, len(CYCLE_IDS)))
    if correlated:
        innovations[:-1, 1] = innovations[:-1, 0]
    innovations[-1] = np.asarray([1.0, 2.0, -1.0, 0.5, -0.5, 1.5, -2.0])
    coefficient_map = {
        "growth": np.asarray([0.30, -0.05, 0.0, 0.0, 0.0, 0.0, 0.0]),
        "inflation": np.asarray([0.20, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0]),
    }
    intercept_map = {"growth": 0.20, "inflation": -0.10}
    residual_map = {"growth": 0.05, "inflation": -0.05}
    rows: list[dict[str, object]] = []
    for date_position, date in enumerate(dates):
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
                        "date": date,
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
                        "status": "estimated",
                    }
                )
    return pd.DataFrame(rows), dates[-1]


def _stage2_components(current_date: pd.Timestamp) -> pd.DataFrame:
    rows = [
        ("intercept", "intercept", 1.0, 0.07, 0.07),
        ("benchmark", "benchmark_return", 0.5, 0.20, 0.10),
        ("channel", "growth", 0.45, 2.00, 0.90),
        ("channel", "inflation", 0.15, -1.00, -0.15),
        ("interaction", "growth_x_inflation", 1.0, -0.02, -0.02),
        ("control", "momentum", 0.3, 0.10, 0.03),
        ("event", "policy", 1.0, 1.20, 1.20),
        ("residual", "asset_residual", -1.13, 1.0, -1.13),
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
                "predicted_return": 2.13,
                "asset_residual": -1.13,
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


def _config(api: ModuleType, **updates: object) -> object:
    values: dict[str, object] = {
        "identifiability": api.IdentifiabilityConfig(
            min_history_count=12,
            correlation_threshold=0.999,
            condition_number_threshold=1_000_000.0,
        ),
        "conservation_tolerance": 1e-10,
        "direct_min_oos_gain": 0.05,
        "direct_min_stability_score": 0.80,
        "direct_min_validation_count": 12,
    }
    values.update(updates)
    return api.ContributionConfig(**values)


def _evidence(
    date: pd.Timestamp,
    *,
    contribution: float = 0.20,
    oos_gain: float = 0.08,
    stability_score: float = 0.90,
    validation_count: int = 18,
    validated: bool = True,
    validation_end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    normalized_validation_end = (
        date - pd.Timedelta(days=1)
        if validation_end_date is None
        else validation_end_date
    )
    return pd.DataFrame(
        {
            "date": [date],
            "asset_id": ["asset_a"],
            "contribution": [contribution],
            "oos_gain": [oos_gain],
            "stability_score": [stability_score],
            "validation_count": [validation_count],
            "validated": [validated],
            "validation_end_date": [normalized_validation_end],
        }
    )


def _compose(
    api: ModuleType,
    *,
    correlated: bool = False,
    direct_evidence: pd.DataFrame | None = None,
) -> tuple[object, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    stage1, current_date = _stage1_paths(correlated=correlated)
    stage2 = _stage2_components(current_date)
    result = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=direct_evidence,
        config=_config(api),
    )
    return result, stage1, stage2, current_date


def test_exact_path_multiplication_and_complete_conservation() -> None:
    api = _api()
    result, _, _, current_date = _compose(api)
    paths = result.paths
    components = result.components

    assert tuple(paths.columns) == api.ATTRIBUTION_PATH_COLUMNS
    assert tuple(components.columns) == api.ATTRIBUTION_COMPONENT_COLUMNS
    growth_c1 = paths.loc[
        paths["date"].eq(current_date)
        & paths["channel_id"].eq("growth")
        & paths["cycle_id"].eq("C1")
    ].iloc[0]
    assert growth_c1["raw_path_contribution"] == pytest.approx(0.60, abs=1e-12)
    assert growth_c1["raw_path_contribution"] == pytest.approx(
        growth_c1["cycle_innovation"]
        * growth_c1["cycle_to_channel_coefficient"]
        * growth_c1["channel_to_asset_coefficient"],
        abs=1e-12,
    )
    cycle_components = components.loc[components["component_type"].eq("cycle")]
    cycle_lookup = cycle_components.set_index("component_id")["contribution"]
    assert cycle_lookup["C1"] == pytest.approx(0.40, abs=1e-12)
    assert cycle_lookup["C2"] == pytest.approx(-0.30, abs=1e-12)
    assert float(components["contribution"].sum()) == pytest.approx(1.0, abs=1e-10)
    assert components["observed_return"].eq(1.0).all()
    assert components["reconstructed_return"].eq(1.0).all()


def test_channel_baseline_and_residual_paths_expand_stage2_channels() -> None:
    api = _api()
    result, _, stage2, _ = _compose(api)
    components = result.components

    baselines = components.loc[
        components["component_type"].eq("channel_baseline_path")
    ].set_index("component_id")["contribution"]
    residuals = components.loc[
        components["component_type"].eq("channel_residual_path")
    ].set_index("component_id")["contribution"]
    assert baselines["growth"] == pytest.approx(0.40, abs=1e-12)
    assert baselines["inflation"] == pytest.approx(0.10, abs=1e-12)
    assert residuals["growth"] == pytest.approx(0.10, abs=1e-12)
    assert residuals["inflation"] == pytest.approx(0.05, abs=1e-12)
    channel_total = float(
        stage2.loc[stage2["component_type"].eq("channel"), "contribution"].sum()
    )
    expanded_total = float(
        components.loc[
            components["component_type"].isin(
                ["cycle", "channel_baseline_path", "channel_residual_path"]
            ),
            "contribution",
        ].sum()
    )
    assert expanded_total == pytest.approx(channel_total, abs=1e-10)


def test_correlated_cycles_publish_only_the_merged_group() -> None:
    api = _api()
    result, _, _, _ = _compose(api, correlated=True)
    components = result.components

    assert not bool(
        (
            components["component_type"].eq("cycle")
            & components["component_id"].isin(["C1", "C2"])
        ).any()
    )
    merged = components.loc[
        components["component_type"].eq("cycle_group")
        & components["component_id"].eq("C1+C2")
    ].iloc[0]
    assert merged["contribution"] == pytest.approx(0.10, abs=1e-12)
    assert merged["status"] == "merged_cycles"
    assert merged["allocation_method"] == "correlation_union_find"


def test_missing_stage1_channel_is_unresolved_without_breaking_conservation() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage1 = stage1.loc[
        ~(stage1["date"].eq(current_date) & stage1["channel_id"].eq("inflation"))
    ]
    stage2 = _stage2_components(current_date)

    result = api.compose_attribution_paths(stage1, stage2, config=_config(api))

    unresolved = result.components.loc[
        result.components["component_type"].eq("unresolved_channel")
    ]
    assert len(unresolved) == 1
    assert unresolved.iloc[0]["component_id"] == "inflation"
    assert unresolved.iloc[0]["contribution"] == pytest.approx(-0.15, abs=1e-12)
    assert unresolved.iloc[0]["status"] == "unavailable"
    assert float(result.components["contribution"].sum()) == pytest.approx(
        1.0,
        abs=1e-10,
    )


def test_direct_residual_is_reclassified_only_after_all_thresholds_pass() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)

    accepted = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date),
        config=_config(api),
    )
    accepted_direct = accepted.components.loc[
        accepted.components["component_type"].eq("unobserved_channel_residual")
    ]
    accepted_residual = accepted.components.loc[
        accepted.components["component_type"].eq("asset_residual")
    ].iloc[0]
    assert accepted_direct.iloc[0]["contribution"] == pytest.approx(0.20)
    assert accepted_residual["contribution"] == pytest.approx(-1.33)
    assert float(accepted.components["contribution"].sum()) == pytest.approx(1.0)

    rejected = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date, stability_score=0.79),
        config=_config(api),
    )
    assert "unobserved_channel_residual" not in set(
        rejected.components["component_type"]
    )
    rejected_residual = rejected.components.loc[
        rejected.components["component_type"].eq("asset_residual")
    ].iloc[0]
    assert rejected_residual["contribution"] == pytest.approx(-1.13)

    no_validation = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date, validation_count=0),
        config=_config(api),
    )
    assert "unobserved_channel_residual" not in set(
        no_validation.components["component_type"]
    )

    equal_gain = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date, oos_gain=0.05),
        config=_config(api),
    )
    assert "unobserved_channel_residual" not in set(
        equal_gain.components["component_type"]
    )

    negative_gain = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date, oos_gain=-0.01),
        config=_config(api),
    )
    assert "unobserved_channel_residual" not in set(
        negative_gain.components["component_type"]
    )


def test_default_config_rejects_zero_oos_gain() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    config = api.ContributionConfig(
        identifiability=api.IdentifiabilityConfig(
            min_history_count=12,
            correlation_threshold=0.999,
        )
    )

    result = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date, oos_gain=0.0),
        config=config,
    )

    assert config.direct_min_oos_gain > 0.0
    assert "unobserved_channel_residual" not in set(result.components["component_type"])


def test_direct_evidence_requires_strictly_past_validation_cutoff() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)

    past = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(
            current_date,
            validation_end_date=current_date - pd.Timedelta(days=1),
        ),
        config=_config(api),
    )
    same_day = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(
            current_date,
            validation_end_date=current_date,
        ),
        config=_config(api),
    )
    future = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(
            current_date,
            validation_end_date=current_date + pd.Timedelta(days=1),
        ),
        config=_config(api),
    )

    assert "unobserved_channel_residual" in set(past.components["component_type"])
    assert "unobserved_channel_residual" not in set(
        same_day.components["component_type"]
    )
    assert "unobserved_channel_residual" not in set(future.components["component_type"])


@pytest.mark.parametrize("stability_score", [-0.01, 1.01])
def test_direct_evidence_rejects_out_of_range_stability(
    stability_score: float,
) -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)

    with pytest.raises(ValueError, match="stability_score"):
        api.compose_attribution_paths(
            stage1,
            stage2,
            direct_evidence=_evidence(
                current_date,
                stability_score=stability_score,
            ),
            config=_config(api),
        )


def test_shares_preserve_negative_and_greater_than_one_values() -> None:
    api = _api()
    result, _, _, _ = _compose(api)
    components = result.components
    event_share = components.loc[
        components["component_type"].eq("event"), "contribution_share"
    ].iloc[0]
    residual_share = components.loc[
        components["component_type"].eq("asset_residual"), "contribution_share"
    ].iloc[0]
    assert event_share == pytest.approx(1.20)
    assert residual_share == pytest.approx(-1.13)


def test_zero_observed_return_produces_nan_shares_without_normalization() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    stage2["observed_return"] = 0.0
    stage2["asset_residual"] = -2.13
    residual = stage2["component_type"].eq("residual")
    stage2.loc[residual, "component_value"] = -2.13
    stage2.loc[residual, "contribution"] = -2.13

    result = api.compose_attribution_paths(stage1, stage2, config=_config(api))

    assert result.components["contribution_share"].isna().all()
    assert result.components["reconstructed_return"].eq(0.0).all()


def test_unavailable_stage2_retains_zero_placeholder_skeleton() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    stage2["contribution"] = np.nan
    stage2["predicted_return"] = np.nan
    stage2["asset_residual"] = np.nan
    stage2["status"] = "unavailable"

    result = api.compose_attribution_paths(stage1, stage2, config=_config(api))

    assert result.paths.empty
    placeholders = result.components.loc[
        result.components["component_type"].ne("asset_residual")
    ]
    expected = {
        ("asset_intercept", "asset_intercept"),
        ("benchmark", "benchmark_return"),
        ("unresolved_channel", "growth"),
        ("unresolved_channel", "inflation"),
        ("interaction", "growth_x_inflation"),
        ("control", "momentum"),
        ("event", "policy"),
    }
    assert (
        set(
            zip(
                placeholders["component_type"],
                placeholders["component_id"],
                strict=True,
            )
        )
        == expected
    )
    assert placeholders["contribution"].eq(0.0).all()
    assert placeholders["status"].eq("unavailable").all()
    assert (~placeholders["is_explained"]).all()
    assert placeholders["source"].eq("unavailable_placeholder").all()
    assert placeholders["allocation_method"].eq("unavailable_placeholder").all()
    residual = result.components.loc[
        result.components["component_type"].eq("asset_residual")
    ].iloc[0]
    assert residual["contribution"] == pytest.approx(1.0)
    assert float(result.components["contribution"].sum()) == pytest.approx(1.0)


def test_stage2_status_requires_matching_contribution_shape() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    finite_unavailable = _stage2_components(current_date)
    finite_unavailable["status"] = "unavailable"

    with pytest.raises(ValueError, match="failed stage2"):
        api.compose_attribution_paths(
            stage1,
            finite_unavailable,
            config=_config(api),
        )

    missing_usable = _stage2_components(current_date)
    missing_usable["contribution"] = np.nan
    missing_usable["predicted_return"] = np.nan
    missing_usable["asset_residual"] = np.nan
    with pytest.raises(ValueError, match="usable stage2"):
        api.compose_attribution_paths(stage1, missing_usable, config=_config(api))


def test_not_identifiable_stage2_skeleton_preserves_failed_status() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    stage2["contribution"] = np.nan
    stage2["predicted_return"] = np.nan
    stage2["asset_residual"] = np.nan
    stage2["status"] = "not_identifiable"

    result = api.compose_attribution_paths(stage1, stage2, config=_config(api))

    placeholders = result.components.loc[
        result.components["component_type"].ne("asset_residual")
    ]
    assert placeholders["status"].eq("not_identifiable").all()
    assert placeholders["source"].eq("unavailable_placeholder").all()
    assert float(result.components["contribution"].sum()) == pytest.approx(1.0)


def test_completely_missing_current_stage1_is_unavailable_and_unresolved() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage1 = stage1.loc[stage1["date"].lt(current_date)]
    stage2 = _stage2_components(current_date)

    result = api.compose_attribution_paths(stage1, stage2, config=_config(api))

    assert result.identifiability["status"].eq("unavailable").all()
    assert result.identifiability["group_id"].eq("C1+C2+C3+C4+C5+C6+C7").all()
    unresolved = result.components.loc[
        result.components["component_type"].eq("unresolved_channel")
    ]
    assert set(unresolved["component_id"]) == {"growth", "inflation"}
    assert "cycle" not in set(result.components["component_type"])
    assert "cycle_group" not in set(result.components["component_type"])
    assert result.paths["raw_path_contribution"].isna().all()
    assert float(result.components["contribution"].sum()) == pytest.approx(1.0)


def test_result_conservation_tolerance_is_used_end_to_end() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    result = api.compose_attribution_paths(
        stage1,
        stage2,
        config=_config(api, conservation_tolerance=1e-6),
    )
    jittered_stage2 = stage2.copy(deep=True)
    jittered_stage2.loc[jittered_stage2.index[0], "observed_return"] += 5e-8
    jittered = api.compose_attribution_paths(
        stage1,
        jittered_stage2,
        config=_config(api, conservation_tolerance=1e-6),
    )
    components = result.components
    components.loc[0, "contribution"] += 5e-8

    accepted = api.AttributionContributionResult(
        paths=result.paths,
        components=components,
        identifiability=result.identifiability,
        conservation_tolerance=1e-6,
    )

    assert accepted.conservation_tolerance == pytest.approx(1e-6)
    assert len(jittered.components) == len(result.components)
    with pytest.raises(ValueError, match="conserve"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=components,
            identifiability=result.identifiability,
            conservation_tolerance=1e-10,
        )
    with pytest.raises(FrozenInstanceError):
        accepted.conservation_tolerance = 1.0


def test_zero_like_share_uses_configured_tolerance() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)

    def with_observed(observed_return: float) -> pd.DataFrame:
        adjusted = stage2.copy(deep=True)
        predicted = float(adjusted["predicted_return"].iloc[0])
        residual_value = observed_return - predicted
        adjusted["observed_return"] = observed_return
        adjusted["asset_residual"] = residual_value
        residual = adjusted["component_type"].eq("residual")
        adjusted.loc[residual, "component_value"] = residual_value
        adjusted.loc[residual, "contribution"] = residual_value
        return adjusted

    near_zero = api.compose_attribution_paths(
        stage1,
        with_observed(5e-7),
        config=_config(api, conservation_tolerance=1e-6),
    )
    above_zero = api.compose_attribution_paths(
        stage1,
        with_observed(2e-6),
        config=_config(api, conservation_tolerance=1e-6),
    )

    assert near_zero.components["contribution_share"].isna().all()
    assert above_zero.components["contribution_share"].notna().all()
    first = above_zero.components.iloc[0]
    assert first["contribution_share"] == pytest.approx(first["contribution"] / 2e-6)


def test_public_result_constructor_rejects_forged_contract_rows() -> None:
    api = _api()
    result, _, _, _ = _compose(api)

    with pytest.raises(ValueError, match="C1 through C7"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=result.components,
            identifiability=result.identifiability.iloc[:-1],
        )

    fake_type = result.components
    fake_type.loc[0, "component_type"] = "forged_component"
    with pytest.raises(ValueError, match="component_type"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=fake_type,
            identifiability=result.identifiability,
        )

    fake_status = result.components
    fake_status.loc[0, "status"] = "forged_status"
    with pytest.raises(ValueError, match="status"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=fake_status,
            identifiability=result.identifiability,
        )

    string_bool = result.components
    string_bool["is_explained"] = string_bool["is_explained"].astype(object)
    string_bool.loc[0, "is_explained"] = "False"
    with pytest.raises(TypeError, match="boolean"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=string_bool,
            identifiability=result.identifiability,
        )

    wrong_path_group = result.paths
    wrong_path_group.loc[0, "allocation_group_id"] = "C1+C7"
    with pytest.raises(ValueError, match="identifiability"):
        api.AttributionContributionResult(
            paths=wrong_path_group,
            components=result.components,
            identifiability=result.identifiability,
        )

    fake_cycle = result.components
    cycle_row = fake_cycle["component_type"].eq("cycle")
    fake_cycle.loc[cycle_row.idxmax(), "component_id"] = "C1+C7"
    with pytest.raises(ValueError, match="cycle component"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=fake_cycle,
            identifiability=result.identifiability,
        )

    wrong_cycle_status = result.components
    cycle_index = wrong_cycle_status["component_type"].eq("cycle").idxmax()
    wrong_cycle_status.loc[cycle_index, "status"] = "merged_cycles"
    with pytest.raises(ValueError, match="cycle component"):
        api.AttributionContributionResult(
            paths=result.paths,
            components=wrong_cycle_status,
            identifiability=result.identifiability,
        )


def test_future_stage_rows_and_evidence_do_not_rewrite_cutoff_outputs() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    base = api.compose_attribution_paths(
        stage1,
        stage2,
        direct_evidence=_evidence(current_date),
        config=_config(api),
    )

    future_date = current_date + pd.offsets.MonthEnd(1)
    future_stage1 = stage1.loc[stage1["date"].eq(current_date)].copy(deep=True)
    future_stage1["date"] = future_date
    future_stage1.loc[future_stage1["cycle_id"].eq("C1"), "cycle_innovation"] = 50.0
    future_stage1.loc[future_stage1["cycle_id"].eq("C2"), "cycle_innovation"] = -50.0
    future_stage1["contribution"] = (
        future_stage1["cycle_innovation"] * future_stage1["coefficient_mean"]
    )
    for channel_id, channel_group in future_stage1.groupby("channel_id", sort=False):
        predicted = float(channel_group["intercept"].iloc[0]) + float(
            channel_group["contribution"].sum()
        )
        observed = predicted + float(channel_group["channel_residual"].iloc[0])
        channel_mask = future_stage1["channel_id"].eq(channel_id)
        future_stage1.loc[channel_mask, "predicted_channel_innovation"] = predicted
        future_stage1.loc[channel_mask, "observed_channel_innovation"] = observed
    future_stage2 = stage2.copy(deep=True)
    future_stage2["date"] = future_date
    for channel_id in ("growth", "inflation"):
        observed_channel = float(
            future_stage1.loc[
                future_stage1["channel_id"].eq(channel_id),
                "observed_channel_innovation",
            ].iloc[0]
        )
        channel_mask = future_stage2["component_type"].eq("channel") & future_stage2[
            "component_id"
        ].eq(channel_id)
        future_stage2.loc[channel_mask, "component_value"] = observed_channel
        future_stage2.loc[channel_mask, "contribution"] = observed_channel * float(
            future_stage2.loc[channel_mask, "coefficient_mean"].iloc[0]
        )
    non_residual = future_stage2["component_type"].ne("residual")
    future_predicted = float(future_stage2.loc[non_residual, "contribution"].sum())
    future_residual = float(future_stage2.loc[~non_residual, "contribution"].iloc[0])
    future_stage2["predicted_return"] = future_predicted
    future_stage2["asset_residual"] = future_residual
    future_stage2["observed_return"] = future_predicted + future_residual
    future_evidence = _evidence(
        future_date,
        contribution=50.0,
        oos_gain=1.0,
        stability_score=1.0,
        validation_count=100,
    )
    changed = api.compose_attribution_paths(
        pd.concat([stage1, future_stage1], ignore_index=True),
        pd.concat([stage2, future_stage2], ignore_index=True),
        direct_evidence=pd.concat(
            [_evidence(current_date), future_evidence],
            ignore_index=True,
        ),
        config=_config(api),
    )

    for field in ("paths", "components", "identifiability"):
        base_frame = getattr(base, field)
        changed_frame = getattr(changed, field)
        changed_cutoff = changed_frame.loc[changed_frame["date"].le(current_date)]
        pd.testing.assert_frame_equal(
            base_frame.reset_index(drop=True),
            changed_cutoff.reset_index(drop=True),
        )


def test_result_is_defensive_and_accepts_task_result_objects() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    result = api.compose_attribution_paths(
        SimpleNamespace(paths=stage1),
        SimpleNamespace(components=stage2),
        config=_config(api),
    )
    original = result.components.iloc[0]["contribution"]
    stage1.loc[:, "contribution"] = 999.0
    stage2.loc[:, "contribution"] = 999.0
    detached = result.components
    detached.loc[:, "contribution"] = 999.0

    assert result.components.iloc[0]["contribution"] == original
    with pytest.raises(FrozenInstanceError):
        result.paths = pd.DataFrame()
    with pytest.raises(FrozenInstanceError):
        _config(api).conservation_tolerance = 1.0
    with pytest.raises(ValueError, match="direct_min_oos_gain"):
        api.ContributionConfig(direct_min_oos_gain=-1.0)


def test_invalid_inputs_are_rejected_before_composition() -> None:
    api = _api()
    stage1, current_date = _stage1_paths()
    stage2 = _stage2_components(current_date)
    conflict = (
        stage1["date"].eq(stage1["date"].min())
        & stage1["channel_id"].eq("inflation")
        & stage1["cycle_id"].eq("C1")
    )
    inconsistent = stage1.copy(deep=True)
    inconsistent.loc[conflict, "cycle_innovation"] += 1.0
    with pytest.raises(ValueError, match="cycle innovation"):
        api.compose_attribution_paths(inconsistent, stage2, config=_config(api))

    duplicated = pd.concat([stage2, stage2.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        api.compose_attribution_paths(stage1, duplicated, config=_config(api))

    broken = stage2.copy(deep=True)
    broken.loc[broken["component_type"].eq("event"), "contribution"] += 0.01
    with pytest.raises(ValueError, match="conserve"):
        api.compose_attribution_paths(stage1, broken, config=_config(api))

    unknown_status = stage2.copy(deep=True)
    unknown_status["status"] = "mystery"
    with pytest.raises(ValueError, match="unknown status"):
        api.compose_attribution_paths(stage1, unknown_status, config=_config(api))
