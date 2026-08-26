from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.indicator_cycle_contribution import build_indicator_cycle_contribution
from scripts.indicator_cycle_realtime_confirmation import (
    _causal_orthogonalize_components,
    _causal_nearest_peer_factor,
    _causal_peer_factor,
    _component_collinearity,
    _state_space_ensemble,
    build_peer_shared_error_pools,
    build_realtime_indicator_confirmation,
    build_realtime_indicator_peer_pool_input,
    _rolling_variant_diagnostics,
)


def test_state_space_ensemble_weights_are_causal() -> None:
    short_index = pd.date_range("1990-01-31", periods=240, freq="ME")
    short_time = np.arange(len(short_index), dtype=float)
    short_target = pd.Series(
        np.sin(2.0 * np.pi * short_time / 42.0)
        + 0.25 * np.sin(2.0 * np.pi * short_time / 12.0),
        index=short_index,
    )
    future_index = pd.date_range(short_index[-1] + pd.offsets.MonthEnd(), periods=36, freq="ME")
    future = pd.Series(np.linspace(5.0, -5.0, len(future_index)), index=future_index)
    extended_target = pd.concat([short_target, future])

    short_level, _, _, _, short_weights = _state_space_ensemble(short_target, 42.0)
    extended_level, _, _, _, extended_weights = _state_space_ensemble(
        extended_target,
        42.0,
    )

    np.testing.assert_allclose(
        short_level.to_numpy(),
        extended_level.iloc[: len(short_level)].to_numpy(),
        atol=1e-12,
    )
    np.testing.assert_allclose(
        short_weights.to_numpy(),
        extended_weights.iloc[: len(short_weights)].to_numpy(),
        atol=1e-12,
    )
    np.testing.assert_allclose(short_weights.sum(axis=1).to_numpy(), 1.0)


def test_realtime_confirmation_conserves_current_indicator() -> None:
    index = pd.date_range("1960-01-31", periods=780, freq="ME")
    time = np.arange(len(index), dtype=float)
    periods = {
        "C2": 200.0,
        "C3": 100.0,
        "C4": 42.0,
        "C5": 20.0,
        "C6": 12.0,
        "C7": 6.0,
    }
    components = {
        cycle_id: pd.Series(np.sin(2.0 * np.pi * time / period), index=index)
        for cycle_id, period in periods.items()
    }
    target = sum(
        weight * components[cycle_id]
        for cycle_id, weight in {
            "C2": 0.6,
            "C3": 0.5,
            "C4": 0.4,
            "C5": 0.3,
            "C6": 0.2,
            "C7": 0.1,
        }.items()
    )
    retrospective = build_indicator_cycle_contribution(target, components)

    result = build_realtime_indicator_confirmation(target, retrospective)

    assert result["status"] == "causal_realtime_confirmation"
    assert abs(result["current"]["conservationError"]) < 1e-10
    assert result["training"]["originCount"] >= 8
    assert result["training"]["originCount"] <= 12
    assert result["training"]["latestTrainEnd"] < result["current"]["date"]
    assert np.isfinite(result["training"]["rollingReconstructionR2"])
    assert np.isfinite(
        result["training"]["equalMedianRollingReconstructionR2"]
    )
    assert np.isfinite(
        result["training"]["rollingR2ImprovementVsEqualMedian"]
    )
    assert set(result["current"]["components"]) == set(periods)
    assert all(
        "rollingDirectionAgreement" in component
        and "rollingContributionCorrelation" in component
        and "medianAbsoluteRevision" in component
        and "coefficientSignAgreement" in component
        and component["stateSpecificationCount"] == 3
        and abs(sum(component["stateSpecificationWeights"].values()) - 1.0)
        < 1e-10
        and 1.0 <= component["stateSpecificationEffectiveCount"] <= 3.0
        and "stateSpecificationDirectionAgreement" in component
        and "rollingStateSpecificationDirectionAgreement" in component
        and component["uncertainty"] >= component["stateUncertainty"]
        and component["uncertainty"] >= component["coefficientUncertainty"]
        and component["uncertainty"]
        >= component["stateSpecificationUncertainty"]
        for component in result["current"]["components"].values()
    )


def test_realtime_confirmation_rejects_short_history() -> None:
    index = pd.date_range("2010-01-31", periods=100, freq="ME")
    time = np.arange(len(index), dtype=float)
    components = {
        "C5": pd.Series(np.sin(2.0 * np.pi * time / 20.0), index=index),
        "C6": pd.Series(np.sin(2.0 * np.pi * time / 12.0), index=index),
        "C7": pd.Series(np.sin(2.0 * np.pi * time / 6.0), index=index),
    }
    target = components["C5"] + components["C6"] + components["C7"]
    periods = {"C5": 20.0, "C6": 12.0, "C7": 6.0}
    retrospective = build_indicator_cycle_contribution(
        target,
        components,
        periods=periods,
    )

    result = build_realtime_indicator_confirmation(
        target,
        retrospective,
        periods=periods,
    )

    assert result["status"] == "unavailable"


def test_peer_shared_error_pool_uses_leave_one_out_category_first() -> None:
    index = pd.date_range("2000-01-31", periods=36, freq="ME")
    columns = ["responsive", "baseline", "smooth"]
    pool_inputs = {}
    metadata = {}
    for ordinal, track_id in enumerate(("a", "b", "c", "d", "e"), start=1):
        error = pd.DataFrame(
            np.full((len(index), len(columns)), float(ordinal)),
            index=index,
            columns=columns,
        )
        pool_inputs[track_id] = {
            "status": "available",
            "eligibleCycles": ["C4"],
            "rollingErrors": {"C4": error},
        }
        metadata[track_id] = {
            "category": "equity" if track_id != "e" else "commodity",
            "group": "market",
        }

    pools = build_peer_shared_error_pools(pool_inputs, metadata)

    category_pool = pools["a"]["C4"]
    assert category_pool["familyLevel"] == "category"
    assert category_pool["peerCount"] == 3
    np.testing.assert_allclose(
        category_pool["rollingError"].to_numpy(),
        3.0,
    )
    group_pool = pools["e"]["C4"]
    assert group_pool["familyLevel"] == "group"
    assert group_pool["peerCount"] == 4
    np.testing.assert_allclose(
        group_pool["rollingError"].to_numpy(),
        2.5,
    )


def test_peer_shared_pool_does_not_revise_history_after_future_append() -> None:
    index = pd.date_range("1980-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    targets = {
        track_id: pd.Series(
            np.sin(2.0 * np.pi * time / 42.0 + phase),
            index=index,
        )
        for track_id, phase in {
            "a": 0.0,
            "b": 0.2,
            "c": 0.4,
            "d": 0.6,
        }.items()
    }
    retrospective = {
        "status": "retrospective_diagnostic",
        "eligibleCycles": ["C4"],
    }
    short_inputs = {
        track_id: build_realtime_indicator_peer_pool_input(
            target,
            retrospective,
            periods={"C4": 42.0},
        )
        for track_id, target in targets.items()
    }
    future_index = pd.date_range(
        index[-1] + pd.offsets.MonthEnd(),
        periods=24,
        freq="ME",
    )
    extended_inputs = dict(short_inputs)
    extended_inputs["d"] = build_realtime_indicator_peer_pool_input(
        pd.concat(
            [
                targets["d"],
                pd.Series(
                    np.linspace(20.0, -20.0, len(future_index)),
                    index=future_index,
                ),
            ]
        ),
        retrospective,
        periods={"C4": 42.0},
    )
    metadata = {
        track_id: {"category": "growth", "group": "economic"}
        for track_id in targets
    }

    short_pool = build_peer_shared_error_pools(short_inputs, metadata)["a"]["C4"]
    extended_pool = build_peer_shared_error_pools(extended_inputs, metadata)["a"][
        "C4"
    ]

    pd.testing.assert_frame_equal(
        short_pool["rollingError"],
        extended_pool["rollingError"].loc[index],
    )


def test_dynamic_factor_does_not_revise_history_after_future_append() -> None:
    index = pd.date_range("1980-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    own = pd.Series(np.sin(2.0 * np.pi * time / 42.0), index=index, name="C4")
    peers = {
        f"peer_{ordinal}": pd.Series(
            sign * np.sin(2.0 * np.pi * time / 42.0 + phase),
            index=index,
        )
        for ordinal, (sign, phase) in enumerate(
            ((1.0, 0.1), (-1.0, 0.2), (1.0, 0.3)),
            start=1,
        )
    }
    future_index = pd.date_range(
        index[-1] + pd.offsets.MonthEnd(),
        periods=24,
        freq="ME",
    )
    extended_own = pd.concat(
        [own, pd.Series(np.linspace(8.0, -8.0, 24), index=future_index)]
    ).rename("C4")
    extended_peers = {
        peer_id: pd.concat(
            [peer, pd.Series(np.linspace(-10.0, 10.0, 24), index=future_index)]
        )
        for peer_id, peer in peers.items()
    }

    short_factor, short_dispersion = _causal_peer_factor(own, peers, 42.0)
    long_factor, long_dispersion = _causal_peer_factor(
        extended_own,
        extended_peers,
        42.0,
    )

    pd.testing.assert_series_equal(short_factor, long_factor.loc[index])
    pd.testing.assert_series_equal(short_dispersion, long_dispersion.loc[index])


def test_nearest_factor_does_not_revise_history_after_future_append() -> None:
    index = pd.date_range("1980-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    own = pd.Series(np.sin(2.0 * np.pi * time / 42.0), index=index, name="C4")
    peers = {
        f"peer_{ordinal}": pd.Series(
            sign * np.sin(2.0 * np.pi * time / 42.0 + phase),
            index=index,
        )
        for ordinal, (sign, phase) in enumerate(
            ((1.0, 0.1), (-1.0, 0.2), (1.0, 0.3), (1.0, 1.5)),
            start=1,
        )
    }
    future_index = pd.date_range(
        index[-1] + pd.offsets.MonthEnd(),
        periods=24,
        freq="ME",
    )
    extended_own = pd.concat(
        [own, pd.Series(np.linspace(8.0, -8.0, 24), index=future_index)]
    ).rename("C4")
    extended_peers = {
        peer_id: pd.concat(
            [peer, pd.Series(np.linspace(-10.0, 10.0, 24), index=future_index)]
        )
        for peer_id, peer in peers.items()
    }

    short_factor, short_dispersion, short_count = _causal_nearest_peer_factor(
        own,
        peers,
        42.0,
    )
    long_factor, long_dispersion, long_count = _causal_nearest_peer_factor(
        extended_own,
        extended_peers,
        42.0,
    )

    pd.testing.assert_series_equal(short_factor, long_factor.loc[index])
    pd.testing.assert_series_equal(short_dispersion, long_dispersion.loc[index])
    pd.testing.assert_series_equal(short_count, long_count.loc[index])
    assert short_count.dropna().eq(3.0).all()


def test_nearest_factor_precommitted_specifications_are_available() -> None:
    index = pd.date_range("1980-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    own = pd.Series(np.sin(2.0 * np.pi * time / 42.0), index=index, name="C4")
    peers = {
        f"peer_{ordinal}": pd.Series(
            np.sin(2.0 * np.pi * time / 42.0 + phase),
            index=index,
        )
        for ordinal, phase in enumerate((0.1, 0.2, 0.3, 0.4, 0.5), start=1)
    }

    primary = _causal_nearest_peer_factor(own, peers, 42.0)
    broader = _causal_nearest_peer_factor(
        own,
        peers,
        42.0,
        maximum_peers=5,
    )
    longer = _causal_nearest_peer_factor(
        own,
        peers,
        42.0,
        span_multiplier=1.5,
    )

    assert primary[2].dropna().eq(3.0).all()
    assert broader[2].dropna().eq(5.0).all()
    assert longer[2].dropna().eq(3.0).all()
    assert not primary[0].dropna().equals(broader[0].dropna())


def test_rolling_diagnostics_flags_low_target_variance() -> None:
    index = pd.date_range("2000-01-31", periods=180, freq="ME")
    time = np.arange(len(index), dtype=float)
    frame = pd.DataFrame(
        {
            "target": np.concatenate(
                [np.linspace(-2.0, 2.0, 168), np.full(12, 0.5)]
            ),
            "C4": np.sin(2.0 * np.pi * time / 42.0),
        },
        index=index,
    )
    origins = np.arange(168, 180, dtype=int)

    diagnostics = _rolling_variant_diagnostics(
        frame,
        ["C4"],
        origins,
        60,
    )

    assert diagnostics["lowTargetVarianceWarning"] is True
    assert diagnostics["targetVarianceRatio"] < 0.01
    assert np.isnan(diagnostics["r2"])


def test_realtime_confirmation_exposes_peer_shared_challenger() -> None:
    index = pd.date_range("1980-01-31", periods=420, freq="ME")
    time = np.arange(len(index), dtype=float)
    periods = {"C4": 42.0, "C5": 20.0}
    components = {
        cycle_id: pd.Series(
            np.sin(2.0 * np.pi * time / period),
            index=index,
        )
        for cycle_id, period in periods.items()
    }
    target = 0.7 * components["C4"] + 0.3 * components["C5"]
    retrospective = build_indicator_cycle_contribution(
        target,
        components,
        periods=periods,
    )
    peer_targets = {
        "target": target,
        "peer_1": target.shift(1).fillna(0.0),
        "peer_2": target.shift(2).fillna(0.0),
        "peer_3": target.shift(3).fillna(0.0),
    }
    pool_inputs = {
        track_id: build_realtime_indicator_peer_pool_input(
            peer_target,
            retrospective,
            periods=periods,
        )
        for track_id, peer_target in peer_targets.items()
    }
    metadata = {
        track_id: {"category": "growth", "group": "economic"}
        for track_id in peer_targets
    }
    peer_pool = build_peer_shared_error_pools(pool_inputs, metadata)["target"]

    result = build_realtime_indicator_confirmation(
        target,
        retrospective,
        periods=periods,
        peer_shared_errors=peer_pool,
    )

    assert result["status"] == "causal_realtime_confirmation"
    assert result["training"]["peerSharedStatus"] in {
        "adopted",
        "rejected",
    }
    assert result["training"]["dynamicFactorStatus"] in {
        "adopted",
        "rejected",
    }
    assert np.isfinite(result["training"]["dynamicFactorRollingReconstructionR2"])
    assert result["training"]["nearestFactorSpecificationCount"] == 3
    assert result["training"]["nearestFactorSpecificationStable"] in {
        True,
        False,
    }
    assert set(result["training"]["nearestFactorSpecifications"]) == {
        "primary",
        "broader_peer_set",
        "longer_correlation_window",
    }
    assert set(result["training"]["nearestFactorVintageSplits"]) == {
        "early",
        "late",
    }
    assert result["training"]["lowTargetVarianceWarning"] is False
    assert result["training"]["causalOrthogonalStatus"] in {
        "adopted",
        "rejected",
    }
    assert np.isfinite(
        result["training"]["orthogonalPrimaryRollingReconstructionR2"]
    )
    assert (
        result["training"]["orthogonalPrimaryComponentCollinearity"][
            "maximumAbsoluteCorrelation"
        ]
        <= result["training"]["baseComponentCollinearity"][
            "maximumAbsoluteCorrelation"
        ]
    )
    assert set(result["training"]["peerSharedEligibleCycles"]) == set(periods)
    assert np.isfinite(result["training"]["peerSharedRollingReconstructionR2"])
    assert all(
        component["peerSharedEligible"] is True
        and component["peerSharedFamilyLevel"] == "category"
        and component["peerSharedPeerCount"] == 3
        and 0.0 < component["peerSharedEvidenceWeight"] <= 0.5
        and abs(
            sum(component["peerSharedStateSpecificationWeights"].values())
            - 1.0
        )
        < 1e-10
        and 0.0 < component["dynamicFactorEvidenceWeight"] <= 0.35
        and component["uncertainty"] >= component["dynamicFactorUncertainty"]
        and "nearestFactorSpecificationUncertainty" in component
        and "nearestFactorSpecificationDirectionAgreement" in component
        for component in result["current"]["components"].values()
    )


def test_causal_orthogonalization_does_not_revise_past_after_future_append() -> None:
    index = pd.date_range("1990-01-31", periods=240, freq="ME")
    time = np.arange(len(index), dtype=float)
    components = {
        "C4": pd.Series(np.sin(2.0 * np.pi * time / 42.0), index=index),
        "C5": pd.Series(
            0.8 * np.sin(2.0 * np.pi * time / 42.0)
            + np.sin(2.0 * np.pi * time / 20.0),
            index=index,
        ),
        "C6": pd.Series(
            0.6 * np.sin(2.0 * np.pi * time / 20.0)
            + np.sin(2.0 * np.pi * time / 12.0),
            index=index,
        ),
    }
    periods = {"C4": 42.0, "C5": 20.0, "C6": 12.0}
    future_index = pd.date_range(
        index[-1] + pd.offsets.MonthEnd(),
        periods=24,
        freq="ME",
    )
    extended = {
        cycle_id: pd.concat(
            [
                component,
                pd.Series(
                    np.linspace(10.0, -10.0, len(future_index)),
                    index=future_index,
                ),
            ]
        )
        for cycle_id, component in components.items()
    }

    short, _ = _causal_orthogonalize_components(
        components,
        periods,
        span=60,
    )
    long, _ = _causal_orthogonalize_components(
        extended,
        periods,
        span=60,
    )

    for cycle_id in components:
        pd.testing.assert_series_equal(
            short[cycle_id],
            long[cycle_id].loc[index],
        )


def test_causal_orthogonalization_reduces_component_overlap() -> None:
    index = pd.date_range("1990-01-31", periods=360, freq="ME")
    time = np.arange(len(index), dtype=float)
    long_cycle = np.sin(2.0 * np.pi * time / 42.0)
    medium_cycle = np.sin(2.0 * np.pi * time / 20.0)
    components = {
        "C4": pd.Series(long_cycle, index=index),
        "C5": pd.Series(0.9 * long_cycle + medium_cycle, index=index),
        "C6": pd.Series(
            0.7 * medium_cycle + np.sin(2.0 * np.pi * time / 12.0),
            index=index,
        ),
    }
    periods = {"C4": 42.0, "C5": 20.0, "C6": 12.0}
    base_frame = pd.concat(components, axis=1)
    orthogonal, _ = _causal_orthogonalize_components(
        components,
        periods,
        span=60,
    )
    orthogonal_frame = pd.concat(orthogonal, axis=1)

    base = _component_collinearity(base_frame, list(periods))
    reduced = _component_collinearity(orthogonal_frame, list(periods))

    assert reduced["maximumAbsoluteCorrelation"] < base[
        "maximumAbsoluteCorrelation"
    ]
    assert reduced["conditionNumber"] < base["conditionNumber"]
