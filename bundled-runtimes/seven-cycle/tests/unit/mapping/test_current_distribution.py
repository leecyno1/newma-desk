from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timezone
import hashlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.attribution.stage1 import (
    CYCLE_IDS,
    CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS,
    CYCLE_TO_CHANNEL_PATH_COLUMNS,
    CycleToChannelResult,
)
from seven_cycle_platform.attribution.stage2 import (
    CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    ChannelToAssetResult,
)
from seven_cycle_platform.mapping.distribution import (
    BENCHMARK_FORECAST_COLUMNS,
    CHANNEL_RESIDUAL_FORECAST_COLUMNS,
    CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    CYCLE_FORECAST_COLUMNS,
    PREDICTOR_FORECAST_COLUMNS,
    RESIDUAL_HISTORY_COLUMNS,
    CurrentDistributionConfig,
    CurrentDistributionResult,
    direction_probabilities,
    estimate_current_distribution,
)
from seven_cycle_platform.mapping.features import (
    CurrentFeatureSnapshot,
    FeatureInput,
    FeatureKind,
    FeaturePayload,
    FeatureProvenance,
    FreshnessPolicy,
    StructuralDriftFlag,
)
from seven_cycle_platform.mapping.risk import (
    RiskMetrics,
    compute_max_drawdown,
    summarize_risk,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


AS_OF = date(2024, 6, 30)
POSTERIOR_DATE = pd.Timestamp(AS_OF)
FUTURE_DATES = pd.date_range("2024-07-31", periods=12, freq="ME")
ASSET_ID = "asset_alpha"
CHANNEL_ID = "growth_transmission"


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_context() -> RunContext:
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF,
        model_version="current-distribution-fixture-v1",
        config={"mapping": "current-distribution", "as_of": AS_OF.isoformat()},
        input_checksums={"fixture.json": _checksum(b"current-distribution")},
        quality_summary={"failed": 0, "passed": 1},
        created_at=datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc),
    )


def _feature(
    *,
    kind: FeatureKind,
    feature_id: str,
    entity_id: str | None = None,
    values: dict[str, object] | None = None,
) -> FeatureInput:
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values=values or {"value": 0.25},
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=date(2024, 6, 1),
        release_date=date(2024, 6, 5),
        vintage_date=date(2024, 6, 6),
        source="unit-test-archive",
        unit="score",
        retrieval_time=datetime.combine(
            date(2024, 6, 7),
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=VintageKind.REALTIME,
        methodology="point_in_time_fixture",
    )
    return FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=45,
            max_visible_age_days=45,
        ),
        structural_drift=StructuralDriftFlag(
            detected=False,
            score=0.10,
            threshold=0.50,
            method="rolling_population_stability_index",
            baseline_id="mapping-baseline-v1",
            evaluated_at=date(2024, 6, 6),
            reason="within threshold",
        ),
    )


def _snapshot(*, include_beta: bool = False) -> CurrentFeatureSnapshot:
    historical_posterior = [
        _feature(
            kind=FeatureKind.HISTORICAL_POSTERIOR,
            feature_id="asset_alpha_posterior",
            entity_id=ASSET_ID,
            values={"coefficient_count": 3, "status": "estimated"},
        )
    ]
    if include_beta:
        historical_posterior.append(
            _feature(
                kind=FeatureKind.HISTORICAL_POSTERIOR,
                feature_id="asset_beta_posterior",
                entity_id="asset_beta",
                values={"coefficient_count": 3, "status": "estimated"},
            )
        )
    return CurrentFeatureSnapshot(
        as_of=AS_OF,
        cycle_states=tuple(
            _feature(
                kind=FeatureKind.CYCLE,
                feature_id=f"C{position}",
                values={"level": position / 10.0, "confidence": 0.8},
            )
            for position in range(1, 8)
        ),
        channel_states=(
            _feature(
                kind=FeatureKind.CHANNEL,
                feature_id=CHANNEL_ID,
                values={"state": 0.4, "innovation": 0.08},
            ),
        ),
        valuation_controls=(
            _feature(
                kind=FeatureKind.VALUATION,
                feature_id="forward_pe",
                entity_id=ASSET_ID,
                values={"z_score": -0.35},
            ),
        ),
        earnings_controls=(
            _feature(
                kind=FeatureKind.EARNINGS,
                feature_id="earnings_revision",
                entity_id=ASSET_ID,
                values={"revision_breadth": 0.22},
            ),
        ),
        positioning_controls=(
            _feature(
                kind=FeatureKind.POSITIONING,
                feature_id="fund_positioning",
                entity_id=ASSET_ID,
                values={"percentile": 0.61},
            ),
        ),
        liquidity_controls=(
            _feature(
                kind=FeatureKind.LIQUIDITY,
                feature_id="market_liquidity",
                entity_id=ASSET_ID,
                values={"impulse": -0.18},
            ),
        ),
        event_scenarios=(
            _feature(
                kind=FeatureKind.EVENT,
                feature_id="policy_surprise",
                entity_id=ASSET_ID,
                values={"probability": 0.2, "shock": -0.45},
            ),
        ),
        historical_posterior=tuple(historical_posterior),
        run_context=_run_context(),
    )


def _stage1(
    *,
    coefficient_variance: float = 0.0004,
    non_psd: bool = False,
    training_count: int = 48,
) -> CycleToChannelResult:
    coefficient_means = {cycle_id: 0.0 for cycle_id in CYCLE_IDS}
    coefficient_means["C1"] = 0.6
    path_rows = []
    for cycle_id in CYCLE_IDS:
        path_rows.append(
            {
                "date": POSTERIOR_DATE,
                "channel_id": CHANNEL_ID,
                "cycle_id": cycle_id,
                "cycle_innovation": 0.0,
                "coefficient_mean": coefficient_means[cycle_id],
                "contribution": 0.0,
                "intercept": 0.001,
                "observed_channel_innovation": 0.001,
                "predicted_channel_innovation": 0.001,
                "channel_residual": 0.0,
                "training_start": pd.Timestamp("2020-01-31"),
                "training_end": pd.Timestamp("2024-05-31"),
                "training_count": training_count,
                "alpha": 0.1,
                "condition_number": 12.0,
                "validation_count": 12,
                "window": "expanding",
                "estimation_method": "batch",
                "forgetting_factor": 1.0,
                "status": "estimated",
            }
        )
    covariance = np.eye(len(CYCLE_IDS), dtype="float64") * coefficient_variance
    if non_psd:
        covariance[0, 0] = coefficient_variance
        covariance[1, 1] = coefficient_variance
        covariance[0, 1] = 2.0 * coefficient_variance
        covariance[1, 0] = 2.0 * coefficient_variance
    covariance_rows = []
    for row, cycle_i in enumerate(CYCLE_IDS):
        for column, cycle_j in enumerate(CYCLE_IDS):
            covariance_rows.append(
                {
                    "date": POSTERIOR_DATE,
                    "channel_id": CHANNEL_ID,
                    "cycle_i": cycle_i,
                    "cycle_j": cycle_j,
                    "coefficient_covariance": covariance[row, column],
                    "training_start": pd.Timestamp("2020-01-31"),
                    "training_end": pd.Timestamp("2024-05-31"),
                    "training_count": training_count,
                    "alpha": 0.1,
                    "condition_number": 12.0,
                    "validation_count": 12,
                    "window": "expanding",
                    "estimation_method": "batch",
                    "forgetting_factor": 1.0,
                    "status": "estimated",
                }
            )
    return CycleToChannelResult(
        paths=pd.DataFrame(path_rows, columns=CYCLE_TO_CHANNEL_PATH_COLUMNS),
        covariance=pd.DataFrame(
            covariance_rows,
            columns=CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS,
        ),
    )


def _stage2(
    *,
    include_control: bool = False,
    coefficient_variance: float = 0.0001,
    effective_training_count: float = 40,
    intercept_mean: float = 0.002,
) -> ChannelToAssetResult:
    labels = [
        ("intercept", "intercept", intercept_mean, 1.0),
        ("benchmark", "benchmark_return", 0.2, 0.003),
        ("channel", CHANNEL_ID, 0.7, 0.01),
    ]
    if include_control:
        labels.append(("control", "valuation_z", 0.1, 0.2))
    predicted = float(sum(mean * value for _, _, mean, value in labels))
    residual = 0.001
    component_rows = []
    for component_type, component_id, coefficient_mean, component_value in labels:
        component_rows.append(
            {
                "date": POSTERIOR_DATE,
                "asset_id": ASSET_ID,
                "component_type": component_type,
                "component_id": component_id,
                "component_value": component_value,
                "coefficient_mean": coefficient_mean,
                "contribution": coefficient_mean * component_value,
                "observed_return": predicted + residual,
                "predicted_return": predicted,
                "asset_residual": residual,
                "training_start": pd.Timestamp("2020-01-31"),
                "training_end": pd.Timestamp("2024-05-31"),
                "training_count": 44,
                "effective_training_count": effective_training_count,
                "parent_node_id": "industry_alpha",
                "parent_coefficient_mean": np.nan,
                "own_weight": 0.8,
                "parent_weight": 0.2,
                "confidence": 0.9,
                "proxy_discount": 1.0,
                "condition_number": 10.0,
                "status": "estimated",
                "window": "expanding",
                "rolling_window": None,
                "forgetting_factor": 1.0,
                "estimation_method": "hierarchical_tvp_ridge",
            }
        )
    component_rows.append(
        {
            "date": POSTERIOR_DATE,
            "asset_id": ASSET_ID,
            "component_type": "residual",
            "component_id": "asset_residual",
            "component_value": residual,
            "coefficient_mean": 1.0,
            "contribution": residual,
            "observed_return": predicted + residual,
            "predicted_return": predicted,
            "asset_residual": residual,
            "training_start": pd.Timestamp("2020-01-31"),
            "training_end": pd.Timestamp("2024-05-31"),
            "training_count": 44,
            "effective_training_count": effective_training_count,
            "parent_node_id": "industry_alpha",
            "parent_coefficient_mean": np.nan,
            "own_weight": 0.8,
            "parent_weight": 0.2,
            "confidence": 0.9,
            "proxy_discount": 1.0,
            "condition_number": 10.0,
            "status": "estimated",
            "window": "expanding",
            "rolling_window": None,
            "forgetting_factor": 1.0,
            "estimation_method": "hierarchical_tvp_ridge",
        }
    )
    posterior_rows = []
    for position, (component_type, component_id, coefficient_mean, _) in enumerate(
        labels
    ):
        posterior_rows.append(
            {
                "date": POSTERIOR_DATE,
                "node_level": "asset",
                "node_id": ASSET_ID,
                "parent_node_id": "industry_alpha",
                "component_type": component_type,
                "component_id": component_id,
                "coefficient_mean": coefficient_mean,
                "parent_coefficient_mean": np.nan if position == 0 else 0.0,
                "prior_precision": 1.0,
                "own_weight": 0.8,
                "parent_weight": 0.2,
                "confidence": 0.9,
                "proxy_discount": 1.0,
                "training_start": pd.Timestamp("2020-01-31"),
                "training_end": pd.Timestamp("2024-05-31"),
                "training_count": 44,
                "effective_training_count": effective_training_count,
                "condition_number": 10.0,
                "status": "estimated",
                "window": "expanding",
                "rolling_window": None,
                "forgetting_factor": 1.0,
                "estimation_method": "hierarchical_tvp_ridge",
            }
        )
    covariance = np.eye(len(labels), dtype="float64") * coefficient_variance
    covariance_rows = []
    for row, (type_i, id_i, _, _) in enumerate(labels):
        for column, (type_j, id_j, _, _) in enumerate(labels):
            covariance_rows.append(
                {
                    "date": POSTERIOR_DATE,
                    "node_level": "asset",
                    "node_id": ASSET_ID,
                    "parent_node_id": "industry_alpha",
                    "component_i_type": type_i,
                    "component_i_id": id_i,
                    "component_j_type": type_j,
                    "component_j_id": id_j,
                    "coefficient_covariance": covariance[row, column],
                    "training_start": pd.Timestamp("2020-01-31"),
                    "training_end": pd.Timestamp("2024-05-31"),
                    "training_count": 44,
                    "effective_training_count": effective_training_count,
                    "prior_precision": 1.0,
                    "own_weight": 0.8,
                    "parent_weight": 0.2,
                    "confidence": 0.9,
                    "proxy_discount": 1.0,
                    "condition_number": 10.0,
                    "status": "estimated",
                    "window": "expanding",
                    "rolling_window": None,
                    "forgetting_factor": 1.0,
                    "estimation_method": "hierarchical_tvp_ridge",
                }
            )
    return ChannelToAssetResult(
        components=pd.DataFrame(
            component_rows,
            columns=CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
        ),
        posteriors=pd.DataFrame(
            posterior_rows,
            columns=CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
        ),
        covariance=pd.DataFrame(
            covariance_rows,
            columns=CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
        ),
    )


def _config(
    *,
    draw_count: int = 64,
    seed: int = 1729,
    min_effective_samples: int = 12,
    residual_block_length: int = 3,
) -> CurrentDistributionConfig:
    return CurrentDistributionConfig(
        draw_count=draw_count,
        seed=seed,
        residual_block_length=residual_block_length,
        min_effective_samples=min_effective_samples,
        neutral_bands={
            ("absolute", 3): 0.015,
            ("absolute", 6): 0.025,
            ("absolute", 12): 0.040,
            ("excess", 3): 0.010,
            ("excess", 6): 0.018,
            ("excess", 12): 0.030,
        },
    )


def _forecast_inputs(
    draw_count: int,
    *,
    constant: bool = False,
) -> dict[str, pd.DataFrame]:
    cycle_rows = []
    channel_rows = []
    benchmark_rows = []
    for draw_id in range(draw_count):
        for month_number, forecast_date in enumerate(FUTURE_DATES, start=1):
            for cycle_id in CYCLE_IDS:
                if cycle_id == "C1":
                    value = (
                        0.01 if constant else 0.003 * month_number + 0.0001 * draw_id
                    )
                else:
                    value = 0.0
                cycle_rows.append(
                    {
                        "forecast_origin": pd.Timestamp(AS_OF),
                        "date": forecast_date,
                        "draw_id": draw_id,
                        "cycle_id": cycle_id,
                        "cycle_forecast": value,
                    }
                )
            channel_rows.append(
                {
                    "forecast_origin": pd.Timestamp(AS_OF),
                    "date": forecast_date,
                    "draw_id": draw_id,
                    "channel_id": CHANNEL_ID,
                    "channel_residual": (
                        0.0 if constant else 0.0002 * ((draw_id + month_number) % 5 - 2)
                    ),
                }
            )
            benchmark_rows.append(
                {
                    "forecast_origin": pd.Timestamp(AS_OF),
                    "date": forecast_date,
                    "draw_id": draw_id,
                    "asset_id": ASSET_ID,
                    "benchmark_return": (
                        0.0
                        if constant
                        else 0.002 + 0.0002 * month_number + 0.00005 * (draw_id % 7)
                    ),
                }
            )
    return {
        "cycle_forecasts": pd.DataFrame(cycle_rows, columns=CYCLE_FORECAST_COLUMNS),
        "channel_residual_forecasts": pd.DataFrame(
            channel_rows,
            columns=CHANNEL_RESIDUAL_FORECAST_COLUMNS,
        ),
        "predictor_forecasts": pd.DataFrame(columns=PREDICTOR_FORECAST_COLUMNS),
        "benchmark_forecasts": pd.DataFrame(
            benchmark_rows,
            columns=BENCHMARK_FORECAST_COLUMNS,
        ),
    }


def _residual_history(*, zero: bool = False) -> pd.DataFrame:
    dates = pd.date_range("2021-06-30", periods=36, freq="ME")
    values = (
        np.zeros(len(dates)) if zero else ((np.arange(len(dates)) % 7) - 3) * 0.0004
    )
    return pd.DataFrame(
        {
            "date": dates,
            "asset_id": ASSET_ID,
            "residual": values,
        },
        columns=RESIDUAL_HISTORY_COLUMNS,
    )


def _estimate(
    *,
    snapshot: CurrentFeatureSnapshot | None = None,
    config: CurrentDistributionConfig | None = None,
    stage1: CycleToChannelResult | None = None,
    stage2: ChannelToAssetResult | None = None,
    residual_history: pd.DataFrame | None = None,
    inputs: dict[str, pd.DataFrame] | None = None,
    calibrator: object | None = None,
) -> CurrentDistributionResult:
    normalized_config = config or _config()
    forecast_inputs = inputs or _forecast_inputs(normalized_config.draw_count)
    return estimate_current_distribution(
        snapshot=snapshot or _snapshot(),
        stage1=stage1 or _stage1(),
        stage2=stage2 or _stage2(),
        residual_history=(
            _residual_history() if residual_history is None else residual_history
        ),
        config=normalized_config,
        calibrator=calibrator,
        **forecast_inputs,
    )


def test_risk_metrics_use_loss_var_and_full_path_drawdown() -> None:
    monthly = np.asarray([0.10, -0.20, 0.05], dtype="float64")
    assert compute_max_drawdown(monthly) == pytest.approx(0.20)

    metrics = summarize_risk(
        np.asarray([-0.30, -0.10, 0.0, 0.20, 0.40], dtype="float64"),
        np.asarray([0.35, 0.20, 0.10, 0.0, 0.05], dtype="float64"),
    )

    assert metrics.volatility >= 0.0
    assert metrics.var95 >= 0.0
    assert metrics.cvar95 >= metrics.var95
    assert 0.0 <= metrics.drawdown_q50 <= metrics.drawdown_q80
    assert metrics.drawdown_q80 <= metrics.drawdown_q95


def test_max_drawdown_is_stable_for_extreme_positive_returns() -> None:
    drawdown = compute_max_drawdown([1e308, 1e308])

    assert np.isfinite(drawdown)
    assert drawdown == pytest.approx(0.0)


def test_risk_rejects_drawdowns_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match=r"drawdown|\[0, 1\]"):
        summarize_risk(
            np.asarray([-0.1, 0.2]),
            np.asarray([0.2, 1.01]),
        )

    with pytest.raises(ValueError, match=r"drawdown|\[0, 1\]"):
        RiskMetrics(
            volatility=0.1,
            var95=0.2,
            cvar95=0.3,
            drawdown_q50=0.2,
            drawdown_q80=0.8,
            drawdown_q95=1.01,
        )


def test_neutral_band_includes_both_boundaries() -> None:
    probabilities = direction_probabilities(
        np.asarray([-0.0201, -0.02, 0.0, 0.02, 0.0201]),
        neutral_band=0.02,
    )

    assert probabilities == pytest.approx({"up": 0.2, "neutral": 0.6, "down": 0.2})


def test_distribution_outputs_joint_horizons_and_coherent_summary() -> None:
    result = _estimate()

    assert tuple(result.summary.columns) == CURRENT_DISTRIBUTION_SUMMARY_COLUMNS
    assert (
        tuple(result.monthly_draws.columns) == CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS
    )
    assert tuple(result.draws.columns) == CURRENT_DISTRIBUTION_DRAW_COLUMNS
    assert result.summary[
        ["asset_id", "horizon_months", "return_basis"]
    ].values.tolist() == [
        [ASSET_ID, 3, "absolute"],
        [ASSET_ID, 3, "excess"],
        [ASSET_ID, 6, "absolute"],
        [ASSET_ID, 6, "excess"],
        [ASSET_ID, 12, "absolute"],
        [ASSET_ID, 12, "excess"],
    ]
    assert len(result.monthly_draws) == 64 * 12
    assert len(result.draws) == 64 * 3

    for row in result.summary.itertuples(index=False):
        assert (
            row.raw_up_probability
            + row.raw_neutral_probability
            + row.raw_down_probability
            == pytest.approx(1.0)
        )
        assert (
            row.up_probability + row.neutral_probability + row.down_probability
            == pytest.approx(1.0)
        )
        assert row.q10 <= row.q25 <= row.q50 <= row.q75 <= row.q90
        assert row.volatility >= 0.0
        assert row.var95 >= 0.0
        assert row.cvar95 >= row.var95
        assert 0.0 <= row.drawdown_q50 <= row.drawdown_q80 <= row.drawdown_q95
        assert row.effective_samples == 36
        assert row.status == "available"
        assert row.calibration_version == "identity-v1"
        assert row.run_id == _snapshot().provenance.run_id
        assert row.snapshot_as_of == AS_OF
        assert row.snapshot_data_vintage == AS_OF
        assert row.snapshot_model_version == _snapshot().provenance.model_version
        assert row.snapshot_config_hash == _snapshot().provenance.config_hash


def test_horizons_are_shared_path_prefixes_and_relative_wealth_is_conserved() -> None:
    result = _estimate()
    monthly = result.monthly_draws.loc[
        result.monthly_draws["draw_id"].eq(0)
    ].sort_values("month_number")
    horizons = result.draws.loc[result.draws["draw_id"].eq(0)].set_index(
        "horizon_months"
    )

    first_month_return = float(monthly["asset_monthly_return"].iloc[0])
    for horizon in (3, 6, 12):
        prefix = monthly.iloc[:horizon]
        absolute = float(np.prod(1.0 + prefix["asset_monthly_return"]) - 1.0)
        benchmark = float(np.prod(1.0 + prefix["benchmark_monthly_return"]) - 1.0)
        excess = (1.0 + absolute) / (1.0 + benchmark) - 1.0
        row = horizons.loc[horizon]

        assert row["absolute_return"] == pytest.approx(absolute)
        assert row["benchmark_return"] == pytest.approx(benchmark)
        assert row["excess_return"] == pytest.approx(excess)
        assert row["absolute_max_drawdown"] == pytest.approx(
            compute_max_drawdown(prefix["asset_monthly_return"].to_numpy())
        )
        relative_monthly = (1.0 + prefix["asset_monthly_return"]) / (
            1.0 + prefix["benchmark_monthly_return"]
        ) - 1.0
        assert row["excess_max_drawdown"] == pytest.approx(
            compute_max_drawdown(relative_monthly.to_numpy())
        )
        assert not np.isclose(row["absolute_return"], first_month_return * horizon)


def test_seed_and_input_shuffle_are_deterministic() -> None:
    config = _config(seed=91)
    inputs = _forecast_inputs(config.draw_count)
    baseline = _estimate(config=config, inputs=inputs)
    shuffled_inputs = {
        name: frame.sample(frac=1.0, random_state=position).reset_index(drop=True)
        for position, (name, frame) in enumerate(inputs.items(), start=1)
    }
    shuffled_history = _residual_history().sample(
        frac=1.0,
        random_state=19,
    )
    shuffled = _estimate(
        config=config,
        inputs=shuffled_inputs,
        residual_history=shuffled_history,
    )

    pd.testing.assert_frame_equal(baseline.monthly_draws, shuffled.monthly_draws)
    pd.testing.assert_frame_equal(baseline.draws, shuffled.draws)
    pd.testing.assert_frame_equal(baseline.summary, shuffled.summary)


def test_cycle_forecasts_enter_the_numeric_path() -> None:
    config = _config(seed=123)
    inputs = _forecast_inputs(config.draw_count)
    baseline = _estimate(config=config, inputs=inputs)
    changed_inputs = {name: frame.copy(deep=True) for name, frame in inputs.items()}
    c1 = changed_inputs["cycle_forecasts"]["cycle_id"].eq("C1")
    changed_inputs["cycle_forecasts"].loc[c1, "cycle_forecast"] += 0.02
    changed = _estimate(config=config, inputs=changed_inputs)

    assert not baseline.monthly_draws["asset_monthly_return"].equals(
        changed.monthly_draws["asset_monthly_return"]
    )
    assert not baseline.summary["expected_return"].equals(
        changed.summary["expected_return"]
    )


def test_future_residual_contamination_is_ignored() -> None:
    history = _residual_history()
    contaminated = pd.concat(
        [
            history,
            pd.DataFrame(
                {
                    "date": [pd.Timestamp(AS_OF), FUTURE_DATES[0]],
                    "asset_id": [ASSET_ID, ASSET_ID],
                    "residual": [1000.0, -1000.0],
                },
                columns=RESIDUAL_HISTORY_COLUMNS,
            ),
        ],
        ignore_index=True,
    )

    baseline = _estimate(residual_history=history)
    result = _estimate(residual_history=contaminated)

    pd.testing.assert_frame_equal(baseline.monthly_draws, result.monthly_draws)
    pd.testing.assert_frame_equal(baseline.draws, result.draws)
    pd.testing.assert_frame_equal(baseline.summary, result.summary)


def test_gapped_residual_history_is_rejected() -> None:
    history = _residual_history().drop(index=10).reset_index(drop=True)

    with pytest.raises(ValueError, match="consecutive|gap"):
        _estimate(residual_history=history)


def test_stage1_and_stage2_coefficient_vectors_are_reused_across_months() -> None:
    config = _config(draw_count=32, seed=7)
    result = _estimate(
        config=config,
        inputs=_forecast_inputs(config.draw_count, constant=True),
        residual_history=_residual_history(zero=True),
        stage1=_stage1(coefficient_variance=0.02),
        stage2=_stage2(coefficient_variance=0.01),
    )

    per_draw_unique = result.monthly_draws.groupby("draw_id", sort=True)[
        "asset_monthly_return"
    ].nunique()
    assert per_draw_unique.eq(1).all()
    assert (
        result.monthly_draws.groupby("draw_id")["asset_monthly_return"]
        .first()
        .nunique()
        > 1
    )


def test_missing_required_stage2_predictor_is_rejected() -> None:
    with pytest.raises(ValueError, match="predictor.*control.*valuation_z"):
        _estimate(stage2=_stage2(include_control=True))


class _InvalidCalibrator:
    version = "invalid-v1"

    def calibrate(self, **_: object) -> dict[str, float]:
        return {"up": 0.8, "neutral": 0.4, "down": -0.2}


class _UpTiltCalibrator:
    version = "up-tilt-v1"

    def calibrate(
        self,
        *,
        probabilities: dict[str, float],
        **_: object,
    ) -> dict[str, float]:
        return {
            "up": 0.5 + 0.5 * probabilities["up"],
            "neutral": 0.5 * probabilities["neutral"],
            "down": 0.5 * probabilities["down"],
        }


def test_probability_calibration_changes_only_probabilities() -> None:
    baseline = _estimate()
    calibrated = _estimate(calibrator=_UpTiltCalibrator())

    pd.testing.assert_frame_equal(baseline.monthly_draws, calibrated.monthly_draws)
    pd.testing.assert_frame_equal(baseline.draws, calibrated.draws)
    probability_columns = ["up_probability", "neutral_probability", "down_probability"]
    raw_columns = [
        "raw_up_probability",
        "raw_neutral_probability",
        "raw_down_probability",
    ]
    pd.testing.assert_frame_equal(
        baseline.summary.drop(columns=[*probability_columns, "calibration_version"]),
        calibrated.summary.drop(columns=[*probability_columns, "calibration_version"]),
    )
    pd.testing.assert_frame_equal(
        baseline.summary.loc[:, raw_columns],
        calibrated.summary.loc[:, raw_columns],
    )
    assert not baseline.summary.loc[:, probability_columns].equals(
        calibrated.summary.loc[:, probability_columns]
    )
    assert set(calibrated.summary["calibration_version"]) == {"up-tilt-v1"}


def test_invalid_probability_calibrator_is_rejected() -> None:
    with pytest.raises(ValueError, match="calibrat|probabilit"):
        _estimate(calibrator=_InvalidCalibrator())


def test_non_psd_and_misaligned_posteriors_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive semidefinite"):
        _estimate(stage1=_stage1(non_psd=True))

    stage2 = _stage2()
    object.__setattr__(
        stage2,
        "covariance",
        stage2.covariance.iloc[:-1].reset_index(drop=True),
    )
    with pytest.raises(ValueError, match="covariance|align|pair"):
        _estimate(stage2=stage2)


def test_public_entry_rejects_raw_stage1_frame_container() -> None:
    stage1 = _stage1()
    duplicate = stage1.covariance.iloc[[0]].copy(deep=True)
    duplicate["coefficient_covariance"] *= 2.0
    raw_stage1 = SimpleNamespace(
        paths=stage1.paths,
        covariance=pd.concat(
            [stage1.covariance, duplicate],
            ignore_index=True,
        ),
    )

    with pytest.raises(TypeError, match="stage1.*CycleToChannelResult"):
        _estimate(stage1=raw_stage1)


def test_public_entry_rejects_raw_stage2_frame_container() -> None:
    stage2 = _stage2()
    duplicate = stage2.covariance.iloc[[0]].copy(deep=True)
    duplicate["coefficient_covariance"] *= 2.0
    raw_stage2 = SimpleNamespace(
        components=stage2.components,
        posteriors=stage2.posteriors,
        covariance=pd.concat(
            [stage2.covariance, duplicate],
            ignore_index=True,
        ),
    )

    with pytest.raises(TypeError, match="stage2.*ChannelToAssetResult"):
        _estimate(stage2=raw_stage2)


def test_snapshot_asset_universe_cannot_be_silently_reduced() -> None:
    with pytest.raises(ValueError, match="stage2 assets|snapshot.*asset|align"):
        _estimate(snapshot=_snapshot(include_beta=True))


def test_fractional_stage2_effective_support_is_conservatively_floored() -> None:
    result = _estimate(stage2=_stage2(effective_training_count=18.75))

    assert set(result.summary["stage2_effective_training_count"]) == {18}
    assert set(result.summary["effective_samples"]) == {18}
    assert set(result.summary["status"]) == {"available"}


def test_forecast_boundaries_and_invalid_monthly_returns_are_rejected() -> None:
    config = _config(draw_count=8)
    wrong_origin = _forecast_inputs(config.draw_count)
    wrong_origin["cycle_forecasts"].loc[0, "forecast_origin"] = pd.Timestamp(
        "2024-06-29"
    )
    with pytest.raises(ValueError, match="forecast_origin"):
        _estimate(config=config, inputs=wrong_origin)

    gapped_dates = _forecast_inputs(config.draw_count)
    changed_date = gapped_dates["benchmark_forecasts"]["date"].eq(FUTURE_DATES[5])
    gapped_dates["benchmark_forecasts"].loc[changed_date, "date"] = pd.Timestamp(
        "2025-07-31"
    )
    with pytest.raises(ValueError, match="continuous|12|future"):
        _estimate(config=config, inputs=gapped_dates)

    invalid_benchmark = _forecast_inputs(config.draw_count)
    invalid_benchmark["benchmark_forecasts"].loc[0, "benchmark_return"] = -1.0
    with pytest.raises(ValueError, match="greater than -1|-100%"):
        _estimate(config=config, inputs=invalid_benchmark)

    with pytest.raises(ValueError, match="greater than -1|-100%"):
        _estimate(config=config, stage2=_stage2(intercept_mean=-1.2))


def test_support_is_not_inflated_by_monte_carlo_draw_count() -> None:
    config = _config(draw_count=128, min_effective_samples=50)
    result = _estimate(config=config)

    assert result.monthly_draws.empty
    assert result.draws.empty
    assert set(result.summary["effective_samples"]) == {36}
    assert set(result.summary["status"]) == {"unavailable"}
    metric_columns = [
        "raw_up_probability",
        "up_probability",
        "q50",
        "expected_return",
        "volatility",
        "var95",
        "cvar95",
        "drawdown_q95",
    ]
    assert result.summary.loc[:, metric_columns].isna().all().all()


def test_result_constructor_recomputes_summary_and_defensively_copies() -> None:
    result = _estimate()
    summary = result.summary
    monthly_draws = result.monthly_draws
    draws = result.draws
    summary.loc[0, "q50"] = 99.0
    monthly_draws.loc[0, "asset_monthly_return"] = 99.0
    draws.loc[0, "absolute_return"] = 99.0

    assert result.summary.loc[0, "q50"] != 99.0
    assert result.monthly_draws.loc[0, "asset_monthly_return"] != 99.0
    assert result.draws.loc[0, "absolute_return"] != 99.0

    tampered_summary = result.summary
    tampered_summary.loc[0, "q50"] += 0.5
    with pytest.raises(ValueError, match="summary.*draw|recomputed|inconsistent"):
        CurrentDistributionResult(
            summary=tampered_summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=result.config,
        )

    tampered_draws = result.draws
    tampered_draws.loc[0, "absolute_return"] += 0.5
    with pytest.raises(ValueError, match="draw|prefix|monthly|inconsistent"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=result.monthly_draws,
            draws=tampered_draws,
            config=result.config,
        )


@pytest.fixture(scope="module")
def available_distribution_result() -> CurrentDistributionResult:
    return _estimate()


def test_result_constructor_rejects_negative_support_metadata(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    summary = result.summary
    summary["stage1_training_count"] = -1
    summary["effective_samples"] = -1

    with pytest.raises(ValueError, match="support|nonnegative|integer"):
        CurrentDistributionResult(
            summary=summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=result.config,
        )


def test_result_constructor_rejects_noninteger_support_metadata(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    summary = result.summary
    summary[
        [
            "stage1_training_count",
            "stage2_effective_training_count",
            "residual_history_count",
        ]
    ] = 36.5
    summary["effective_samples"] = 36

    with pytest.raises(ValueError, match="support|nonnegative|integer"):
        CurrentDistributionResult(
            summary=summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=result.config,
        )


def test_result_constructor_rejects_inconsistent_asset_support_rows(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    summary = result.summary
    summary.loc[1, "stage1_training_count"] = 35

    with pytest.raises(ValueError, match="support|constant|consistent"):
        CurrentDistributionResult(
            summary=summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=result.config,
        )


def test_result_constructor_recomputes_effective_support_for_every_row(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    summary = result.summary
    summary.loc[0, "residual_history_count"] = 35
    summary["effective_samples"] = 35

    with pytest.raises(ValueError, match="effective_samples|support|minimum"):
        CurrentDistributionResult(
            summary=summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=result.config,
        )


@pytest.mark.parametrize(
    "config",
    [
        _config(min_effective_samples=40),
        _config(residual_block_length=40),
    ],
)
def test_available_result_must_meet_support_and_block_thresholds(
    available_distribution_result: CurrentDistributionResult,
    config: CurrentDistributionConfig,
) -> None:
    result = available_distribution_result

    with pytest.raises(ValueError, match="available|support|threshold|block"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=result.monthly_draws,
            draws=result.draws,
            config=config,
        )


def test_result_constructor_rejects_retained_asset_missing_from_summary(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    beta_monthly = result.monthly_draws
    beta_monthly["asset_id"] = "asset_beta"
    beta_draws = result.draws
    beta_draws["asset_id"] = "asset_beta"

    with pytest.raises(ValueError, match="asset|coverage|summary|available"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=pd.concat(
                [result.monthly_draws, beta_monthly],
                ignore_index=True,
            ),
            draws=pd.concat([result.draws, beta_draws], ignore_index=True),
            config=result.config,
        )


def test_result_constructor_requires_matching_monthly_and_horizon_asset_sets(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    beta_monthly = result.monthly_draws
    beta_monthly["asset_id"] = "asset_beta"

    with pytest.raises(ValueError, match="asset|monthly|horizon|draw"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=pd.concat(
                [result.monthly_draws, beta_monthly],
                ignore_index=True,
            ),
            draws=result.draws,
            config=result.config,
        )


def test_result_constructor_requires_exact_configured_draw_ids(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    monthly_draws = result.monthly_draws
    draws = result.draws
    monthly_draws["draw_id"] += 1
    draws["draw_id"] += 1

    with pytest.raises(ValueError, match="draw_id|draw_count|0"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=monthly_draws,
            draws=draws,
            config=result.config,
        )


@pytest.mark.parametrize(
    ("frame_name", "column", "replacement"),
    [
        ("summary", "run_id", "different-run"),
        ("summary", "snapshot_as_of", date(2024, 6, 29)),
        ("monthly_draws", "run_id", "different-run"),
        ("monthly_draws", "snapshot_as_of", date(2024, 6, 29)),
        ("draws", "run_id", "different-run"),
        ("draws", "snapshot_as_of", date(2024, 6, 29)),
        ("summary", "forecast_origin", date(2024, 6, 29)),
    ],
)
def test_result_constructor_rejects_cross_frame_provenance_mismatch(
    available_distribution_result: CurrentDistributionResult,
    frame_name: str,
    column: str,
    replacement: object,
) -> None:
    result = available_distribution_result
    frames = {
        "summary": result.summary,
        "monthly_draws": result.monthly_draws,
        "draws": result.draws,
    }
    frames[frame_name][column] = replacement

    with pytest.raises(ValueError, match="provenance|run_id|snapshot|forecast_origin"):
        CurrentDistributionResult(
            summary=frames["summary"],
            monthly_draws=frames["monthly_draws"],
            draws=frames["draws"],
            config=result.config,
        )


def test_result_constructor_rejects_monthly_forecast_origin_mismatch(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    monthly_draws = result.monthly_draws
    monthly_draws["forecast_origin"] = date(2024, 7, 31)
    monthly_draws["date"] = pd.to_datetime(monthly_draws["date"]) + pd.offsets.MonthEnd(
        1
    )

    with pytest.raises(ValueError, match="provenance|snapshot|forecast_origin"):
        CurrentDistributionResult(
            summary=result.summary,
            monthly_draws=monthly_draws,
            draws=result.draws,
            config=result.config,
        )


def test_result_constructor_allows_summary_only_unavailable_asset(
    available_distribution_result: CurrentDistributionResult,
) -> None:
    result = available_distribution_result
    unavailable = result.summary
    unavailable["asset_id"] = "asset_beta"
    unavailable["status"] = "unavailable"
    unavailable[
        [
            "raw_up_probability",
            "raw_neutral_probability",
            "raw_down_probability",
            "up_probability",
            "neutral_probability",
            "down_probability",
            "q10",
            "q25",
            "q50",
            "q75",
            "q90",
            "expected_return",
            "volatility",
            "var95",
            "cvar95",
            "drawdown_q50",
            "drawdown_q80",
            "drawdown_q95",
        ]
    ] = np.nan

    combined = CurrentDistributionResult(
        summary=pd.concat([result.summary, unavailable], ignore_index=True),
        monthly_draws=result.monthly_draws,
        draws=result.draws,
        config=result.config,
    )

    assert set(
        combined.summary.loc[combined.summary["status"].eq("available"), "asset_id"]
    ) == {ASSET_ID}
    assert set(
        combined.summary.loc[combined.summary["status"].eq("unavailable"), "asset_id"]
    ) == {"asset_beta"}
    assert set(combined.monthly_draws["asset_id"]) == {ASSET_ID}
    assert set(combined.draws["asset_id"]) == {ASSET_ID}


def test_configuration_is_frozen_and_copies_neutral_bands() -> None:
    bands = {
        ("absolute", 3): 0.01,
        ("absolute", 6): 0.02,
        ("absolute", 12): 0.03,
        ("excess", 3): 0.01,
        ("excess", 6): 0.02,
        ("excess", 12): 0.03,
    }
    config = CurrentDistributionConfig(neutral_bands=bands)
    bands[("absolute", 3)] = 99.0

    assert config.neutral_bands[("absolute", 3)] == 0.01
    with pytest.raises(TypeError):
        config.neutral_bands[("absolute", 3)] = 0.5
    with pytest.raises(FrozenInstanceError):
        config.seed = 10
