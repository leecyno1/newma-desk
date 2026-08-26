from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
import importlib

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.mapping.distribution import (
    CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    CurrentDistributionConfig,
    CurrentDistributionResult,
    direction_probabilities,
)
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.types import MappingStatus


AS_OF = date(2024, 6, 30)
ASSET_ID = "asset_alpha"
RUN_ID = "2024-06-30-aaaaaaaaaaaa-bbbbbbbbbbbb"
MODEL_VERSION = "transferability-fixture-v1"
DISTRIBUTION_CONFIG_HASH = "c" * 64


def _transferability_module():
    try:
        return importlib.import_module("seven_cycle_platform.mapping.transferability")
    except ModuleNotFoundError:
        pytest.fail("transferability API is not implemented")


def _distribution_config() -> CurrentDistributionConfig:
    return CurrentDistributionConfig(
        draw_count=1,
        seed=0,
        residual_block_length=1,
        min_effective_samples=1,
        neutral_bands={
            ("absolute", 3): 0.015,
            ("absolute", 6): 0.025,
            ("absolute", 12): 0.040,
            ("excess", 3): 0.010,
            ("excess", 6): 0.018,
            ("excess", 12): 0.030,
        },
    )


def _available_distribution(
    *,
    asset_ids: tuple[str, ...] = (ASSET_ID,),
    effective_samples: int = 36,
) -> CurrentDistributionResult:
    config = _distribution_config()
    future_dates = pd.date_range("2024-07-31", periods=12, freq="ME")
    monthly_rows: list[dict[str, object]] = []
    draw_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for asset_position, asset_id in enumerate(asset_ids):
        asset_monthly_return = 0.008 + 0.001 * asset_position
        benchmark_monthly_return = 0.002
        relative_monthly_return = (1.0 + asset_monthly_return) / (
            1.0 + benchmark_monthly_return
        ) - 1.0
        for month_number, forecast_date in enumerate(future_dates, start=1):
            monthly_rows.append(
                {
                    "asset_id": asset_id,
                    "draw_id": 0,
                    "month_number": month_number,
                    "date": forecast_date,
                    "forecast_origin": AS_OF,
                    "asset_monthly_return": asset_monthly_return,
                    "benchmark_monthly_return": benchmark_monthly_return,
                    "relative_monthly_return": relative_monthly_return,
                    "run_id": RUN_ID,
                    "snapshot_as_of": AS_OF,
                }
            )

        for horizon_months in (3, 6, 12):
            absolute_return = (1.0 + asset_monthly_return) ** horizon_months - 1.0
            benchmark_return = (1.0 + benchmark_monthly_return) ** horizon_months - 1.0
            excess_return = (1.0 + absolute_return) / (1.0 + benchmark_return) - 1.0
            absolute_drawdown = compute_max_drawdown(
                np.repeat(asset_monthly_return, horizon_months)
            )
            excess_drawdown = compute_max_drawdown(
                np.repeat(relative_monthly_return, horizon_months)
            )
            draw_rows.append(
                {
                    "asset_id": asset_id,
                    "draw_id": 0,
                    "horizon_months": horizon_months,
                    "absolute_return": absolute_return,
                    "benchmark_return": benchmark_return,
                    "excess_return": excess_return,
                    "absolute_max_drawdown": absolute_drawdown,
                    "excess_max_drawdown": excess_drawdown,
                    "run_id": RUN_ID,
                    "snapshot_as_of": AS_OF,
                }
            )
            for return_basis, horizon_return, drawdown in (
                ("absolute", absolute_return, absolute_drawdown),
                ("excess", excess_return, excess_drawdown),
            ):
                probabilities = direction_probabilities(
                    np.asarray([horizon_return]),
                    neutral_band=config.neutral_bands[(return_basis, horizon_months)],
                )
                risk = summarize_risk(
                    np.asarray([horizon_return]),
                    np.asarray([drawdown]),
                )
                summary_rows.append(
                    {
                        "asset_id": asset_id,
                        "horizon_months": horizon_months,
                        "return_basis": return_basis,
                        "raw_up_probability": probabilities["up"],
                        "raw_neutral_probability": probabilities["neutral"],
                        "raw_down_probability": probabilities["down"],
                        "up_probability": probabilities["up"],
                        "neutral_probability": probabilities["neutral"],
                        "down_probability": probabilities["down"],
                        "q10": horizon_return,
                        "q25": horizon_return,
                        "q50": horizon_return,
                        "q75": horizon_return,
                        "q90": horizon_return,
                        "expected_return": horizon_return,
                        "volatility": risk.volatility,
                        "var95": risk.var95,
                        "cvar95": risk.cvar95,
                        "drawdown_q50": risk.drawdown_q50,
                        "drawdown_q80": risk.drawdown_q80,
                        "drawdown_q95": risk.drawdown_q95,
                        "effective_samples": effective_samples,
                        "stage1_training_count": effective_samples,
                        "stage2_effective_training_count": effective_samples,
                        "residual_history_count": effective_samples,
                        "status": "available",
                        "calibration_version": "identity-v1",
                        "run_id": RUN_ID,
                        "snapshot_as_of": AS_OF,
                        "snapshot_data_vintage": date(2024, 6, 29),
                        "snapshot_model_version": MODEL_VERSION,
                        "snapshot_config_hash": DISTRIBUTION_CONFIG_HASH,
                        "stage1_posterior_date": date(2024, 6, 28),
                        "stage2_posterior_date": date(2024, 6, 28),
                        "forecast_origin": AS_OF,
                    }
                )

    return CurrentDistributionResult(
        summary=pd.DataFrame(
            summary_rows,
            columns=CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
        ),
        monthly_draws=pd.DataFrame(
            monthly_rows,
            columns=CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
        ),
        draws=pd.DataFrame(draw_rows, columns=CURRENT_DISTRIBUTION_DRAW_COLUMNS),
        config=config,
    )


def _evidence(
    distribution: CurrentDistributionResult,
    **overrides: object,
) -> pd.DataFrame:
    dimensions = (
        distribution.summary[["asset_id", "horizon_months"]]
        .drop_duplicates()
        .sort_values(["asset_id", "horizon_months"])
    )
    rows = []
    for dimension in dimensions.itertuples(index=False):
        row = {
            "asset_id": dimension.asset_id,
            "horizon_months": dimension.horizon_months,
            "sign_stability": 0.95,
            "magnitude_stability": 0.95,
            "historical_neighbor_similarity": 0.95,
            "constituent_business_model_stability": 0.95,
            "valuation_positioning_similarity": 0.95,
            "structural_stability": 0.95,
            "cycle_confidence": 0.95,
            "channel_confidence": 0.95,
            "proxy_discount": 0.05,
            "model_oos_loss": 0.70,
            "baseline_oos_loss": 1.00,
            "oos_validation_count": 24,
            "evidence_date": date(2024, 6, 29),
            "validation_end": date(2024, 5, 31),
        }
        row.update(overrides)
        rows.append(row)
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("expected_status", "evidence_overrides", "config_overrides"),
    [
        (MappingStatus.FORMAL, {}, {}),
        (
            MappingStatus.CONDITIONAL,
            {"valuation_positioning_similarity": 0.40},
            {},
        ),
        (
            MappingStatus.RETROSPECTIVE_ONLY,
            {"model_oos_loss": 1.00},
            {},
        ),
        (
            MappingStatus.UNAVAILABLE,
            {},
            {"min_effective_samples": 40},
        ),
    ],
)
def test_transferability_status_table(
    expected_status: MappingStatus,
    evidence_overrides: dict[str, object],
    config_overrides: dict[str, object],
) -> None:
    module = _transferability_module()

    distribution = _available_distribution()
    config = module.TransferabilityConfig(**config_overrides)
    result = module.score_transferability(
        distribution,
        _evidence(distribution, **evidence_overrides),
        config,
    )

    assert set(result.summary["status"]) == {expected_status}


def test_baseline_gate_blocks_formal_with_sufficient_validation() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(
        distribution,
        sign_stability=1.0,
        magnitude_stability=1.0,
        historical_neighbor_similarity=1.0,
        constituent_business_model_stability=1.0,
        valuation_positioning_similarity=1.0,
        structural_stability=1.0,
        cycle_confidence=1.0,
        channel_confidence=1.0,
        proxy_discount=0.0,
        model_oos_loss=1.0,
        baseline_oos_loss=1.0,
    )

    result = module.score_transferability(distribution, evidence)

    assert set(result.summary["historical_score"]) == {1.0}
    assert set(result.summary["baseline_gate_passed"]) == {False}
    assert set(result.summary["status"]) == {MappingStatus.RETROSPECTIVE_ONLY}
    assert result.summary.loc[0, "reason_codes"] == (
        module.TransferabilityReason.BASELINE_NOT_BEATEN,
        module.TransferabilityReason.LOW_OOS_INCREMENT,
        module.TransferabilityReason.OUTCOME_RETROSPECTIVE_ONLY,
    )


@pytest.mark.parametrize(
    ("evidence_overrides", "reason_name"),
    [
        ({"sign_stability": 0.79}, "LOW_SIGN_STABILITY"),
        ({"magnitude_stability": 0.79}, "LOW_MAGNITUDE_STABILITY"),
        (
            {"constituent_business_model_stability": 0.79},
            "CONSTITUENT_DRIFT",
        ),
        ({"structural_stability": 0.79}, "STRUCTURAL_BREAK"),
        ({"cycle_confidence": 0.79}, "LOW_CYCLE_CONFIDENCE"),
        ({"channel_confidence": 0.79}, "LOW_CHANNEL_CONFIDENCE"),
        ({"proxy_discount": 0.21}, "PROXY_DISCOUNT"),
    ],
)
def test_general_instability_is_retrospective_despite_high_overall_score(
    evidence_overrides: dict[str, float],
    reason_name: str,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(
        formal_sign_threshold=0.80,
        formal_magnitude_threshold=0.80,
        formal_constituent_threshold=0.80,
        formal_structural_threshold=0.80,
        formal_cycle_confidence_threshold=0.80,
        formal_channel_confidence_threshold=0.80,
        formal_proxy_discount_max=0.20,
    )
    evidence_values = {
        "magnitude_stability": 1.0,
        "historical_neighbor_similarity": 1.0,
        "constituent_business_model_stability": 1.0,
        "valuation_positioning_similarity": 1.0,
        "structural_stability": 1.0,
        "cycle_confidence": 1.0,
        "channel_confidence": 1.0,
        "proxy_discount": 0.0,
        "model_oos_loss": 0.0,
        **evidence_overrides,
    }
    evidence = _evidence(distribution, **evidence_values)

    result = module.score_transferability(distribution, evidence, config)

    assert result.summary["overall_score"].min() >= config.formal_overall_threshold
    assert set(result.summary["formal_hard_gates_passed"]) == {False}
    assert set(result.summary["status"]) == {MappingStatus.RETROSPECTIVE_ONLY}
    assert result.summary.loc[0, "reason_codes"] == (
        getattr(module.TransferabilityReason, reason_name),
        module.TransferabilityReason.OUTCOME_RETROSPECTIVE_ONLY,
    )


@pytest.mark.parametrize(
    ("evidence_overrides", "reason_names"),
    [
        (
            {"historical_neighbor_similarity": 0.40},
            ("LOW_NEIGHBOR_SIMILARITY",),
        ),
        (
            {"valuation_positioning_similarity": 0.40},
            ("VALUATION_POSITIONING_DISTANCE",),
        ),
        (
            {
                "historical_neighbor_similarity": 0.40,
                "valuation_positioning_similarity": 0.40,
            },
            ("LOW_NEIGHBOR_SIMILARITY", "VALUATION_POSITIONING_DISTANCE"),
        ),
    ],
)
def test_context_specific_weaknesses_are_conditional(
    evidence_overrides: dict[str, float],
    reason_names: tuple[str, ...],
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()

    result = module.score_transferability(
        distribution,
        _evidence(distribution, **evidence_overrides),
    )

    expected_reasons = tuple(
        getattr(module.TransferabilityReason, name) for name in reason_names
    ) + (module.TransferabilityReason.OUTCOME_CONDITIONAL,)
    assert set(result.summary["status"]) == {MappingStatus.CONDITIONAL}
    assert result.summary.loc[0, "reason_codes"] == expected_reasons


def test_overall_weakness_without_context_condition_is_retrospective() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(formal_overall_threshold=0.97)

    result = module.score_transferability(
        distribution,
        _evidence(distribution),
        config,
    )

    assert set(result.summary["formal_hard_gates_passed"]) == {True}
    assert result.summary["overall_score"].min() >= config.conditional_overall_threshold
    assert result.summary["overall_score"].max() < config.formal_overall_threshold
    assert set(result.summary["status"]) == {MappingStatus.RETROSPECTIVE_ONLY}
    assert result.summary.loc[0, "reason_codes"] == (
        module.TransferabilityReason.LOW_OVERALL_SCORE,
        module.TransferabilityReason.OUTCOME_RETROSPECTIVE_ONLY,
    )


def test_insufficient_oos_validation_is_unavailable() -> None:
    module = _transferability_module()
    distribution = _available_distribution()

    result = module.score_transferability(
        distribution,
        _evidence(distribution, oos_validation_count=11),
    )

    assert set(result.summary["baseline_gate_passed"]) == {False}
    assert set(result.summary["status"]) == {MappingStatus.UNAVAILABLE}
    assert result.summary.loc[0, "reason_codes"] == (
        module.TransferabilityReason.INSUFFICIENT_OOS_VALIDATION,
        module.TransferabilityReason.OUTCOME_UNAVAILABLE,
    )


def test_any_unavailable_distribution_basis_makes_transferability_unavailable() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    summary = distribution.summary
    unavailable = summary["horizon_months"].eq(3) & summary["return_basis"].eq("excess")
    summary.loc[unavailable, "status"] = "unavailable"
    object.__setattr__(distribution, "summary", summary)

    result = module.score_transferability(distribution, _evidence(distribution))
    horizon = result.summary.loc[result.summary["horizon_months"].eq(3)].iloc[0]

    assert horizon["distribution_status"] == "unavailable"
    assert horizon["status"] == MappingStatus.UNAVAILABLE
    assert horizon["reason_codes"] == (
        module.TransferabilityReason.DISTRIBUTION_UNAVAILABLE,
        module.TransferabilityReason.OUTCOME_UNAVAILABLE,
    )


def test_effective_samples_use_conservative_basis_minimum() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    summary = distribution.summary
    absolute = summary["horizon_months"].eq(3) & summary["return_basis"].eq("absolute")
    excess = summary["horizon_months"].eq(3) & summary["return_basis"].eq("excess")
    summary.loc[absolute, "effective_samples"] = 36
    summary.loc[excess, "effective_samples"] = 20
    object.__setattr__(distribution, "summary", summary)

    result = module.score_transferability(distribution, _evidence(distribution))
    horizon = result.summary.loc[result.summary["horizon_months"].eq(3)].iloc[0]

    assert horizon["absolute_effective_samples"] == 36
    assert horizon["excess_effective_samples"] == 20
    assert horizon["effective_samples"] == 20
    assert horizon["status"] == MappingStatus.UNAVAILABLE
    assert (
        module.TransferabilityReason.INSUFFICIENT_EFFECTIVE_SAMPLES
        in horizon["reason_codes"]
    )


@pytest.mark.parametrize(
    ("column", "replacement", "message"),
    [
        ("evidence_date", date(2024, 7, 1), "evidence_date|cutoff|as_of"),
        (
            "validation_end",
            date(2024, 6, 30),
            "validation_end|strictly earlier|forecast_origin",
        ),
    ],
)
def test_evidence_dates_cannot_look_forward(
    column: str,
    replacement: date,
    message: str,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(distribution)
    evidence[column] = replacement

    with pytest.raises(ValueError, match=message):
        module.score_transferability(distribution, evidence)


def test_validation_end_cannot_follow_evidence_date() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(
        distribution,
        evidence_date=date(2024, 5, 1),
        validation_end=date(2024, 5, 31),
    )

    with pytest.raises(ValueError, match="validation_end|evidence_date|order"):
        module.score_transferability(distribution, evidence)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_evidence_dimensions_must_exactly_align(
    mutation: str,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(distribution)
    if mutation == "missing":
        evidence = evidence.iloc[:-1].copy()
    elif mutation == "extra":
        extra = evidence.iloc[[0]].copy()
        extra["asset_id"] = "asset_beta"
        evidence = pd.concat([evidence, extra], ignore_index=True)
    else:
        evidence = pd.concat([evidence, evidence.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="evidence.*dimension|unique|align|coverage"):
        module.score_transferability(distribution, evidence)


def test_distribution_requires_exact_basis_rows_and_consistent_provenance() -> None:
    module = _transferability_module()
    missing_basis = _available_distribution()
    missing_summary = missing_basis.summary
    missing_summary = missing_summary.loc[
        ~(
            missing_summary["horizon_months"].eq(3)
            & missing_summary["return_basis"].eq("excess")
        )
    ].copy()
    object.__setattr__(missing_basis, "summary", missing_summary)

    with pytest.raises(ValueError, match="absolute|excess|basis|distribution"):
        module.score_transferability(missing_basis, _evidence(missing_basis))

    mixed_provenance = _available_distribution()
    mixed_summary = mixed_provenance.summary
    changed = mixed_summary["horizon_months"].eq(3) & mixed_summary["return_basis"].eq(
        "excess"
    )
    mixed_summary.loc[changed, "run_id"] = "2024-06-30-dddddddddddd-eeeeeeeeeeee"
    object.__setattr__(mixed_provenance, "summary", mixed_summary)

    with pytest.raises(ValueError, match="provenance|run_id|basis"):
        module.score_transferability(
            mixed_provenance,
            _evidence(mixed_provenance),
        )


def test_unsupported_distribution_horizon_is_rejected() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    summary = distribution.summary
    summary.loc[summary["horizon_months"].eq(3), "horizon_months"] = 9
    object.__setattr__(distribution, "summary", summary)

    with pytest.raises(ValueError, match="horizon|supported|3|6|12"):
        module.score_transferability(distribution, _evidence(distribution))


def test_config_rejects_missing_extra_duplicate_and_bad_weight_totals() -> None:
    module = _transferability_module()
    defaults = module.TransferabilityConfig()
    weights = dict(defaults.weights)

    missing = dict(weights)
    missing.pop("sign")
    with pytest.raises(ValueError, match="weights|missing|exactly"):
        module.TransferabilityConfig(weights=missing)

    extra = dict(weights)
    extra["unexpected"] = 0.0
    with pytest.raises(ValueError, match="weights|extra|exactly"):
        module.TransferabilityConfig(weights=extra)

    duplicate = list(weights.items())
    duplicate[-1] = ("sign", duplicate[-1][1])
    with pytest.raises(ValueError, match="duplicate|weights"):
        module.TransferabilityConfig(weights=duplicate)

    wrong_total = dict(weights)
    wrong_total["sign"] -= 0.01
    with pytest.raises(ValueError, match="sum|one|1"):
        module.TransferabilityConfig(weights=wrong_total)


@pytest.mark.parametrize(
    ("overrides", "exception"),
    [
        (
            {"formal_overall_threshold": 0.60, "conditional_overall_threshold": 0.60},
            ValueError,
        ),
        ({"formal_overall_threshold": True}, TypeError),
        ({"formal_sign_threshold": float("nan")}, ValueError),
        ({"formal_proxy_discount_max": float("inf")}, ValueError),
        ({"min_effective_samples": 1.0}, TypeError),
        ({"min_oos_validation_count": True}, TypeError),
        ({"min_oos_increment": 0.0}, ValueError),
        ({"min_oos_increment": 0.30, "full_score_oos_increment": 0.20}, ValueError),
        ({"full_score_oos_increment": 1.01}, ValueError),
    ],
)
def test_config_strictly_validates_thresholds_and_policy_numbers(
    overrides: dict[str, object],
    exception: type[Exception],
) -> None:
    module = _transferability_module()

    with pytest.raises(exception):
        module.TransferabilityConfig(**overrides)


@pytest.mark.parametrize(
    ("discount", "quality", "formal"),
    [
        (0.0, 1.0, True),
        (0.25, 0.75, True),
        (0.250001, 0.749999, False),
        (1.0, 0.0, False),
    ],
)
def test_proxy_discount_boundaries(
    discount: float,
    quality: float,
    formal: bool,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(formal_proxy_discount_max=0.25)

    result = module.score_transferability(
        distribution,
        _evidence(distribution, proxy_discount=discount),
        config,
    )

    assert result.summary.loc[0, "proxy_quality_score"] == pytest.approx(quality)
    assert bool(result.summary.loc[0, "formal_hard_gates_passed"]) is formal
    if formal:
        assert (
            module.TransferabilityReason.PROXY_DISCOUNT
            not in result.summary.loc[0, "reason_codes"]
        )
    else:
        assert (
            module.TransferabilityReason.PROXY_DISCOUNT
            in result.summary.loc[0, "reason_codes"]
        )


@pytest.mark.parametrize("discount", [-0.01, 1.01])
def test_proxy_discount_rejects_out_of_range_values(discount: float) -> None:
    module = _transferability_module()
    distribution = _available_distribution()

    with pytest.raises(ValueError, match=r"proxy_discount|\[0, 1\]"):
        module.score_transferability(
            distribution,
            _evidence(distribution, proxy_discount=discount),
        )


@pytest.mark.parametrize(
    ("model_loss", "expected_increment", "expected_score"),
    [
        (0.0, 1.0, 1.0),
        (0.8, 0.2, 1.0),
        (0.9, 0.1, 0.5),
        (1.2, -0.2, 0.0),
    ],
)
def test_oos_increment_and_score_are_objectively_derived(
    model_loss: float,
    expected_increment: float,
    expected_score: float,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(full_score_oos_increment=0.20)
    evidence = _evidence(
        distribution,
        model_oos_loss=model_loss,
        baseline_oos_loss=1.0,
    )
    evidence["baseline_gate_passed"] = True

    result = module.score_transferability(distribution, evidence, config)

    assert result.summary.loc[0, "oos_increment"] == pytest.approx(expected_increment)
    assert result.summary.loc[0, "oos_increment_score"] == pytest.approx(expected_score)
    assert bool(result.summary.loc[0, "baseline_gate_passed"]) is (
        expected_increment >= config.min_oos_increment
    )


@pytest.mark.parametrize(
    ("baseline_loss", "model_loss"),
    [(0.3, 0.285), (3.0, 2.85), (30.0, 28.5)],
)
def test_oos_minimum_boundary_is_scale_invariant(
    baseline_loss: float,
    model_loss: float,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(min_oos_increment=0.05)

    result = module.score_transferability(
        distribution,
        _evidence(
            distribution,
            model_oos_loss=model_loss,
            baseline_oos_loss=baseline_loss,
        ),
        config,
    )
    row = result.summary.iloc[0]

    assert row["oos_increment"] == (baseline_loss - model_loss) / baseline_loss
    assert bool(row["baseline_gate_passed"]) is True
    assert row["status"] == MappingStatus.FORMAL
    assert module.TransferabilityReason.LOW_OOS_INCREMENT not in row["reason_codes"]


def test_oos_increment_below_boundary_beyond_tolerance_fails() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(min_oos_increment=0.05)
    expected_increment = config.min_oos_increment - 1e-8
    baseline_loss = 3.0
    model_loss = baseline_loss * (1.0 - expected_increment)

    result = module.score_transferability(
        distribution,
        _evidence(
            distribution,
            model_oos_loss=model_loss,
            baseline_oos_loss=baseline_loss,
        ),
        config,
    )
    row = result.summary.iloc[0]

    assert row["oos_increment"] == pytest.approx(expected_increment)
    assert bool(row["baseline_gate_passed"]) is False
    assert row["status"] == MappingStatus.RETROSPECTIVE_ONLY
    assert module.TransferabilityReason.LOW_OOS_INCREMENT in row["reason_codes"]


def test_zero_increment_cannot_pass_a_tiny_positive_minimum() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    config = module.TransferabilityConfig(min_oos_increment=5e-13)

    result = module.score_transferability(
        distribution,
        _evidence(
            distribution,
            model_oos_loss=1.0,
            baseline_oos_loss=1.0,
        ),
        config,
    )
    row = result.summary.iloc[0]

    assert row["oos_increment"] == 0.0
    assert bool(row["baseline_gate_passed"]) is False
    assert row["status"] == MappingStatus.RETROSPECTIVE_ONLY
    assert module.TransferabilityReason.BASELINE_NOT_BEATEN in row["reason_codes"]
    assert module.TransferabilityReason.LOW_OOS_INCREMENT in row["reason_codes"]
    assert module.TransferabilityReason.OUTCOME_FORMAL not in row["reason_codes"]


@pytest.mark.parametrize(
    ("overrides", "exception"),
    [
        ({"model_oos_loss": -0.01}, ValueError),
        ({"baseline_oos_loss": 0.0}, ValueError),
        ({"model_oos_loss": True}, TypeError),
        ({"oos_validation_count": -1}, ValueError),
        ({"oos_validation_count": 24.5}, TypeError),
        ({"oos_validation_count": float("inf")}, ValueError),
        ({"oos_validation_count": True}, TypeError),
        ({"sign_stability": 1.01}, ValueError),
        ({"sign_stability": True}, TypeError),
    ],
)
def test_evidence_strictly_validates_numeric_contracts(
    overrides: dict[str, object],
    exception: type[Exception],
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()

    with pytest.raises(exception):
        module.score_transferability(
            distribution,
            _evidence(distribution, **overrides),
        )


def test_mixed_missing_and_integral_float_validation_counts_are_row_local() -> None:
    module = _transferability_module()
    distribution = _available_distribution(asset_ids=(ASSET_ID, "asset_beta"))
    evidence = _evidence(distribution)
    missing = evidence["asset_id"].eq(ASSET_ID) & evidence["horizon_months"].eq(3)
    evidence.loc[missing, "oos_validation_count"] = np.nan

    assert evidence.loc[~missing, "oos_validation_count"].iloc[0] == 24.0

    result = module.score_transferability(distribution, evidence)
    missing_row = result.summary.loc[
        result.summary["asset_id"].eq(ASSET_ID) & result.summary["horizon_months"].eq(3)
    ].iloc[0]
    valid_rows = result.summary.loc[
        ~(
            result.summary["asset_id"].eq(ASSET_ID)
            & result.summary["horizon_months"].eq(3)
        )
    ]

    assert missing_row["status"] == MappingStatus.UNAVAILABLE
    assert missing_row["reason_codes"] == (
        module.TransferabilityReason.INCOMPLETE_EVIDENCE,
        module.TransferabilityReason.OUTCOME_UNAVAILABLE,
    )
    assert set(valid_rows["oos_validation_count"]) == {24}
    assert set(valid_rows["status"]) == {MappingStatus.FORMAL}


def test_incomplete_evidence_is_unavailable_not_silently_dropped() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(distribution)
    evidence.loc[evidence["horizon_months"].eq(3), "sign_stability"] = np.nan

    result = module.score_transferability(distribution, evidence)
    horizon = result.summary.loc[result.summary["horizon_months"].eq(3)].iloc[0]

    assert horizon["status"] == MappingStatus.UNAVAILABLE
    assert np.isnan(horizon["overall_score"])
    assert horizon["reason_codes"] == (
        module.TransferabilityReason.INCOMPLETE_EVIDENCE,
        module.TransferabilityReason.OUTCOME_UNAVAILABLE,
    )


def test_weak_relationship_falls_back_to_retrospective_with_reason() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(
        distribution,
        sign_stability=0.10,
        magnitude_stability=0.10,
        historical_neighbor_similarity=0.10,
        constituent_business_model_stability=0.10,
        valuation_positioning_similarity=0.10,
        structural_stability=0.10,
        cycle_confidence=0.10,
        channel_confidence=0.10,
        proxy_discount=0.90,
        model_oos_loss=0.70,
    )

    result = module.score_transferability(distribution, evidence)

    assert set(result.summary["baseline_gate_passed"]) == {True}
    assert set(result.summary["status"]) == {MappingStatus.RETROSPECTIVE_ONLY}
    assert (
        module.TransferabilityReason.LOW_OVERALL_SCORE
        in result.summary.loc[0, "reason_codes"]
    )


def test_reason_codes_are_complete_stably_ordered_and_unique() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(
        distribution,
        sign_stability=0.10,
        magnitude_stability=0.10,
        historical_neighbor_similarity=0.10,
        constituent_business_model_stability=0.10,
        valuation_positioning_similarity=0.10,
        structural_stability=0.10,
        cycle_confidence=0.10,
        channel_confidence=0.10,
        proxy_discount=0.90,
        model_oos_loss=1.10,
        baseline_oos_loss=1.00,
        oos_validation_count=0,
    )

    reasons = module.score_transferability(distribution, evidence).summary.loc[
        0, "reason_codes"
    ]

    assert reasons == (
        module.TransferabilityReason.INSUFFICIENT_OOS_VALIDATION,
        module.TransferabilityReason.BASELINE_NOT_BEATEN,
        module.TransferabilityReason.LOW_OOS_INCREMENT,
        module.TransferabilityReason.LOW_SIGN_STABILITY,
        module.TransferabilityReason.LOW_MAGNITUDE_STABILITY,
        module.TransferabilityReason.LOW_NEIGHBOR_SIMILARITY,
        module.TransferabilityReason.CONSTITUENT_DRIFT,
        module.TransferabilityReason.VALUATION_POSITIONING_DISTANCE,
        module.TransferabilityReason.STRUCTURAL_BREAK,
        module.TransferabilityReason.LOW_CYCLE_CONFIDENCE,
        module.TransferabilityReason.LOW_CHANNEL_CONFIDENCE,
        module.TransferabilityReason.PROXY_DISCOUNT,
        module.TransferabilityReason.LOW_OVERALL_SCORE,
        module.TransferabilityReason.OUTCOME_UNAVAILABLE,
    )
    assert len(reasons) == len(set(reasons))


def test_output_contract_scores_and_provenance_are_explicit() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    evidence = _evidence(distribution)
    evidence["analyst_note"] = "ignored extra input"

    result = module.score_transferability(distribution, evidence)
    row = result.summary.iloc[0]
    weights = result.config.weights
    expected_overall = sum(
        weights[dimension] * row[f"{dimension}_score"]
        for dimension in module.TRANSFERABILITY_DIMENSIONS
    )
    historical_dimensions = tuple(
        dimension
        for dimension in module.TRANSFERABILITY_DIMENSIONS
        if dimension != "oos_increment"
    )
    expected_historical = sum(
        weights[dimension] * row[f"{dimension}_score"]
        for dimension in historical_dimensions
    ) / sum(weights[dimension] for dimension in historical_dimensions)

    assert tuple(result.summary.columns) == module.TRANSFERABILITY_SUMMARY_COLUMNS
    assert tuple(result.evidence.columns) == module.TRANSFERABILITY_EVIDENCE_COLUMNS
    assert row["oos_increment"] == pytest.approx(0.30)
    assert row["overall_score"] == pytest.approx(expected_overall)
    assert row["historical_score"] == pytest.approx(expected_historical)
    assert row["effective_samples"] == 36
    assert row["run_id"] == RUN_ID
    assert row["as_of"] == AS_OF
    assert row["data_vintage"] == date(2024, 6, 29)
    assert row["model_version"] == MODEL_VERSION
    assert row["config_hash"] == result.config.config_hash
    assert row["distribution_config_hash"] == DISTRIBUTION_CONFIG_HASH
    assert row["forecast_origin"] == AS_OF


def test_historical_score_excludes_oos_subscore() -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    strong = module.score_transferability(
        distribution,
        _evidence(distribution, model_oos_loss=0.0),
    ).summary
    weak = module.score_transferability(
        distribution,
        _evidence(distribution, model_oos_loss=1.0),
    ).summary

    assert strong["historical_score"].equals(weak["historical_score"])
    assert not strong["overall_score"].equals(weak["overall_score"])


def test_input_shuffle_is_deterministic() -> None:
    module = _transferability_module()
    baseline_distribution = _available_distribution(asset_ids=(ASSET_ID, "asset_beta"))
    evidence = _evidence(baseline_distribution)
    baseline = module.score_transferability(
        baseline_distribution,
        evidence,
    )

    shuffled_distribution = _available_distribution(asset_ids=(ASSET_ID, "asset_beta"))
    shuffled_summary = shuffled_distribution.summary.sample(
        frac=1.0,
        random_state=17,
    ).reset_index(drop=True)
    object.__setattr__(shuffled_distribution, "summary", shuffled_summary)
    shuffled = module.score_transferability(
        shuffled_distribution,
        evidence.sample(frac=1.0, random_state=19).reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(baseline.summary, shuffled.summary)
    pd.testing.assert_frame_equal(baseline.evidence, shuffled.evidence)


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("sign_score", 0.123),
        ("status", MappingStatus.CONDITIONAL),
        ("reason_codes", ("forged",)),
        ("run_id", "2024-06-30-dddddddddddd-eeeeeeeeeeee"),
        ("config_hash", "f" * 64),
        ("model_oos_loss", 0.123),
    ],
)
def test_result_constructor_rejects_tampered_output(
    column: str,
    replacement: object,
) -> None:
    module = _transferability_module()
    distribution = _available_distribution()
    result = module.score_transferability(distribution, _evidence(distribution))
    tampered = result.summary
    tampered.loc[0, column] = replacement

    with pytest.raises(ValueError, match="summary|recomputed|inconsistent|retained"):
        module.TransferabilityResult(
            summary=tampered,
            evidence=result.evidence,
            distribution=result.distribution,
            config=result.config,
        )


def test_config_and_result_are_immutable_and_defensive() -> None:
    module = _transferability_module()
    weights = dict(module.TransferabilityConfig().weights)
    config = module.TransferabilityConfig(weights=weights)
    weights["sign"] = 0.0

    assert config.weights["sign"] != 0.0
    with pytest.raises(TypeError):
        config.weights["sign"] = 0.0
    with pytest.raises(FrozenInstanceError):
        config.min_effective_samples = 99

    distribution = _available_distribution()
    evidence = _evidence(distribution)
    result = module.score_transferability(distribution, evidence, config)
    evidence.loc[0, "sign_stability"] = 0.0
    visible_summary = result.summary
    visible_evidence = result.evidence
    visible_summary.loc[0, "sign_score"] = 0.0
    visible_evidence.loc[0, "sign_stability"] = 0.0

    assert result.summary.loc[0, "sign_score"] == pytest.approx(0.95)
    assert result.evidence.loc[0, "sign_stability"] == pytest.approx(0.95)
    with pytest.raises(FrozenInstanceError):
        result.config = module.TransferabilityConfig()


def test_score_requires_current_distribution_result() -> None:
    module = _transferability_module()

    with pytest.raises(TypeError, match="CurrentDistributionResult|distribution"):
        module.score_transferability(object(), pd.DataFrame())
