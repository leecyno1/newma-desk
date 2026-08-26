from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
import importlib
from typing import Any

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
from seven_cycle_platform.mapping.transferability import (
    TransferabilityConfig,
    TransferabilityResult,
    score_transferability,
)


AS_OF = date(2024, 6, 30)
RUN_ID = "2024-06-30-aaaaaaaaaaaa-bbbbbbbbbbbb"
ALT_RUN_ID = "2024-06-30-cccccccccccc-dddddddddddd"
MODEL_VERSION = "weight-range-fixture-v1"
DISTRIBUTION_CONFIG_HASH = "d" * 64
POSITIVE_RATES = (0.03, 0.03, 0.03, 0.03, 0.03)
NEGATIVE_RATES = (-0.03, -0.03, -0.03, -0.03, -0.03)
ZERO_RATES = (0.0, 0.0, 0.0, 0.0, 0.0)
HIGH_DOWNSIDE_RATES = (0.12, 0.12, 0.12, 0.12, -0.30)


def _weights_module():
    try:
        return importlib.import_module("seven_cycle_platform.mapping.weights")
    except ModuleNotFoundError:
        pytest.fail("weight-range API is not implemented")


def _distribution_config(draw_count: int) -> CurrentDistributionConfig:
    return CurrentDistributionConfig(
        draw_count=draw_count,
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


def _current_distribution(
    asset_monthly_returns: dict[str, tuple[float, ...] | None] | None = None,
    *,
    as_of: date = AS_OF,
    run_id: str = RUN_ID,
    config_hash: str = DISTRIBUTION_CONFIG_HASH,
) -> CurrentDistributionResult:
    rates_by_asset = asset_monthly_returns or {"asset_alpha": POSITIVE_RATES}
    available_lengths = {
        len(rates) for rates in rates_by_asset.values() if rates is not None
    }
    if len(available_lengths) > 1:
        raise ValueError("available fixture assets must use the same draw count")
    draw_count = next(iter(available_lengths), 5)
    config = _distribution_config(draw_count)
    first_forecast_month = pd.Timestamp(as_of) + pd.offsets.MonthEnd(1)
    future_dates = pd.date_range(first_forecast_month, periods=12, freq="ME")
    monthly_rows: list[dict[str, object]] = []
    draw_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for asset_id, monthly_rates in rates_by_asset.items():
        available = monthly_rates is not None
        if available:
            assert monthly_rates is not None
            for draw_id, monthly_return in enumerate(monthly_rates):
                for month_number, forecast_date in enumerate(future_dates, start=1):
                    monthly_rows.append(
                        {
                            "asset_id": asset_id,
                            "draw_id": draw_id,
                            "month_number": month_number,
                            "date": forecast_date,
                            "forecast_origin": as_of,
                            "asset_monthly_return": monthly_return,
                            "benchmark_monthly_return": 0.0,
                            "relative_monthly_return": monthly_return,
                            "run_id": run_id,
                            "snapshot_as_of": as_of,
                        }
                    )
            for horizon_months in (3, 6, 12):
                for draw_id, monthly_return in enumerate(monthly_rates):
                    horizon_return = (1.0 + monthly_return) ** horizon_months - 1.0
                    drawdown = compute_max_drawdown(
                        np.repeat(monthly_return, horizon_months)
                    )
                    draw_rows.append(
                        {
                            "asset_id": asset_id,
                            "draw_id": draw_id,
                            "horizon_months": horizon_months,
                            "absolute_return": horizon_return,
                            "benchmark_return": 0.0,
                            "excess_return": horizon_return,
                            "absolute_max_drawdown": drawdown,
                            "excess_max_drawdown": drawdown,
                            "run_id": run_id,
                            "snapshot_as_of": as_of,
                        }
                    )

        for horizon_months in (3, 6, 12):
            if available:
                horizon_draws = [
                    row
                    for row in draw_rows
                    if row["asset_id"] == asset_id
                    and row["horizon_months"] == horizon_months
                ]
                returns = np.asarray(
                    [row["excess_return"] for row in horizon_draws],
                    dtype="float64",
                )
                drawdowns = np.asarray(
                    [row["excess_max_drawdown"] for row in horizon_draws],
                    dtype="float64",
                )
                q10, q25, q50, q75, q90 = np.quantile(
                    returns,
                    [0.10, 0.25, 0.50, 0.75, 0.90],
                )
                risk = summarize_risk(returns, drawdowns)
                support = 36
                status = "available"
            else:
                returns = np.asarray([], dtype="float64")
                q10 = q25 = q50 = q75 = q90 = np.nan
                risk = None
                support = 0
                status = "unavailable"

            for return_basis in ("absolute", "excess"):
                if available:
                    probabilities = direction_probabilities(
                        returns,
                        neutral_band=config.neutral_bands[
                            (return_basis, horizon_months)
                        ],
                    )
                    metrics = {
                        "raw_up_probability": probabilities["up"],
                        "raw_neutral_probability": probabilities["neutral"],
                        "raw_down_probability": probabilities["down"],
                        "up_probability": probabilities["up"],
                        "neutral_probability": probabilities["neutral"],
                        "down_probability": probabilities["down"],
                        "q10": float(q10),
                        "q25": float(q25),
                        "q50": float(q50),
                        "q75": float(q75),
                        "q90": float(q90),
                        "expected_return": float(np.mean(returns)),
                        "volatility": risk.volatility,
                        "var95": risk.var95,
                        "cvar95": risk.cvar95,
                        "drawdown_q50": risk.drawdown_q50,
                        "drawdown_q80": risk.drawdown_q80,
                        "drawdown_q95": risk.drawdown_q95,
                    }
                else:
                    metrics = {
                        column: np.nan
                        for column in (
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
                        )
                    }
                summary_rows.append(
                    {
                        "asset_id": asset_id,
                        "horizon_months": horizon_months,
                        "return_basis": return_basis,
                        **metrics,
                        "effective_samples": support,
                        "stage1_training_count": support,
                        "stage2_effective_training_count": support,
                        "residual_history_count": support,
                        "status": status,
                        "calibration_version": "identity-v1",
                        "run_id": run_id,
                        "snapshot_as_of": as_of,
                        "snapshot_data_vintage": as_of - timedelta(days=1),
                        "snapshot_model_version": MODEL_VERSION,
                        "snapshot_config_hash": config_hash,
                        "stage1_posterior_date": as_of - timedelta(days=2),
                        "stage2_posterior_date": as_of - timedelta(days=2),
                        "forecast_origin": as_of,
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
    distribution_as_of = distribution.summary["snapshot_as_of"].iloc[0]
    validation_end = (pd.Timestamp(distribution_as_of) - pd.offsets.MonthEnd(1)).date()
    dimensions = (
        distribution.summary[["asset_id", "horizon_months"]]
        .drop_duplicates()
        .sort_values(["asset_id", "horizon_months"], kind="stable")
    )
    rows: list[dict[str, object]] = []
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
            "proxy_discount": 0.0,
            "model_oos_loss": 0.70,
            "baseline_oos_loss": 1.00,
            "oos_validation_count": 24,
            "evidence_date": distribution_as_of - timedelta(days=1),
            "validation_end": validation_end,
        }
        row.update(overrides)
        rows.append(row)
    return pd.DataFrame(rows)


def _transferability(
    distribution: CurrentDistributionResult,
    *,
    outcome: str = "formal",
    proxy_discount: float = 0.0,
) -> TransferabilityResult:
    evidence_overrides: dict[str, object] = {"proxy_discount": proxy_discount}
    config = TransferabilityConfig()
    if outcome == "conditional":
        evidence_overrides["valuation_positioning_similarity"] = 0.40
    elif outcome == "retrospective_only":
        evidence_overrides["model_oos_loss"] = 1.00
    elif outcome == "unavailable":
        config = TransferabilityConfig(min_effective_samples=100)
    elif outcome != "formal":
        raise ValueError(f"unsupported fixture outcome: {outcome}")
    return score_transferability(
        distribution,
        _evidence(distribution, **evidence_overrides),
        config,
    )


def _policy(
    distribution: CurrentDistributionResult,
    **overrides: Any,
) -> pd.DataFrame:
    distribution_as_of = distribution.summary["snapshot_as_of"].iloc[0]
    dimensions = (
        distribution.summary[["asset_id", "horizon_months"]]
        .drop_duplicates()
        .sort_values(["asset_id", "horizon_months"], kind="stable")
    )
    rows: list[dict[str, object]] = []
    for dimension in dimensions.itertuples(index=False):
        row: dict[str, object] = {
            "asset_id": dimension.asset_id,
            "horizon_months": dimension.horizon_months,
            "neutral_min_weight": 0.40,
            "neutral_max_weight": 0.50,
            "max_active_tilt": 0.20,
            "active_risk_budget_cap": 0.20,
            "model_disagreement": 0.0,
            "leveraged": False,
            "liquidity_constrained": False,
            "currency_exposed": False,
            "policy_date": distribution_as_of,
            "policy_version": "weight-policy-v1",
        }
        for key, value in overrides.items():
            row[key] = value(dimension) if callable(value) else value
        rows.append(row)
    return pd.DataFrame(rows)


def _row(result: Any, *, asset_id: str = "asset_alpha", horizon: int = 3):
    selected = result.summary.loc[
        result.summary["asset_id"].eq(asset_id)
        & result.summary["horizon_months"].eq(horizon)
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def _active_midpoint(row: pd.Series) -> float:
    return float(
        (
            row["min_weight"]
            - row["neutral_min_weight"]
            + row["max_weight"]
            - row["neutral_max_weight"]
        )
        / 2.0
    )


def test_zero_signal_preserves_the_neutral_range() -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": ZERO_RATES})
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(distribution, model_disagreement=0.80),
    )

    row = _row(result)
    assert row["raw_signal"] == pytest.approx(0.0)
    assert row["min_weight"] == pytest.approx(row["neutral_min_weight"])
    assert row["max_weight"] == pytest.approx(row["neutral_max_weight"])
    assert row["lower_active_tilt"] == pytest.approx(0.0)
    assert row["upper_active_tilt"] == pytest.approx(0.0)


def test_positive_and_negative_signals_move_ranges_directionally() -> None:
    module = _weights_module()
    positive_distribution = _current_distribution({"asset_alpha": POSITIVE_RATES})
    negative_distribution = _current_distribution({"asset_alpha": NEGATIVE_RATES})

    positive = _row(
        module.suggest_weight_ranges(
            positive_distribution,
            _transferability(positive_distribution),
            _policy(positive_distribution),
        )
    )
    negative = _row(
        module.suggest_weight_ranges(
            negative_distribution,
            _transferability(negative_distribution),
            _policy(negative_distribution),
        )
    )

    assert positive["min_weight"] > positive["neutral_min_weight"]
    assert positive["max_weight"] > positive["neutral_max_weight"]
    assert negative["min_weight"] < negative["neutral_min_weight"]
    assert negative["max_weight"] < negative["neutral_max_weight"]


def test_max_active_tilt_binds_the_entire_range() -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": (0.20,) * 5})
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(
            distribution,
            max_active_tilt=0.025,
            active_risk_budget_cap=1.0,
        ),
    )

    row = _row(result)
    assert bool(row["max_active_tilt_bound"])
    assert not bool(row["risk_budget_cap_bound"])
    assert abs(row["lower_active_tilt"]) <= 0.025 + 1e-12
    assert abs(row["upper_active_tilt"]) <= 0.025 + 1e-12
    assert row["lower_active_tilt"] == pytest.approx(0.025)
    assert row["upper_active_tilt"] == pytest.approx(0.025)


def test_active_risk_budget_binds_using_retained_downside_risk() -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": HIGH_DOWNSIDE_RATES})
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(
            distribution,
            max_active_tilt=0.20,
            active_risk_budget_cap=0.006,
        ),
    )

    row = _row(result)
    expected_cap = row["active_risk_budget_cap"] / row["downside_risk"]
    assert bool(row["risk_budget_cap_bound"])
    assert not bool(row["max_active_tilt_bound"])
    assert row["risk_budget_tilt_cap"] == pytest.approx(expected_cap)
    assert abs(row["lower_active_tilt"]) <= expected_cap + 1e-12
    assert abs(row["upper_active_tilt"]) <= expected_cap + 1e-12


def test_downside_floor_is_explicit_and_reconciles_the_risk_cap() -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": POSITIVE_RATES})
    config = module.WeightRangeConfig(downside_risk_floor=0.02)
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(
            distribution,
            max_active_tilt=0.20,
            active_risk_budget_cap=0.0002,
        ),
        config,
    )

    row = _row(result)
    assert row["downside_risk"] == pytest.approx(0.0)
    assert row["downside_risk_floor"] == pytest.approx(0.02)
    assert row["effective_downside_scale"] == pytest.approx(
        max(row["downside_risk"], row["downside_risk_floor"])
    )
    assert row["raw_signal"] == pytest.approx(
        np.tanh(row["expected_excess_return"] / row["effective_downside_scale"])
    )
    expected_cap = row["active_risk_budget_cap"] / row["effective_downside_scale"]
    assert row["risk_budget_tilt_cap"] == pytest.approx(expected_cap)
    assert bool(row["risk_budget_cap_bound"])
    assert not bool(row["max_active_tilt_bound"])
    assert row["lower_active_tilt"] == pytest.approx(expected_cap)
    assert row["upper_active_tilt"] == pytest.approx(expected_cap)
    assert row["min_weight"] == pytest.approx(row["neutral_min_weight"] + expected_cap)
    assert row["max_weight"] == pytest.approx(row["neutral_max_weight"] + expected_cap)


def test_formal_stronger_transferability_has_more_conviction_than_conditional() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    policy = _policy(
        distribution,
        max_active_tilt=0.30,
        active_risk_budget_cap=1.0,
    )

    formal = _row(
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution, outcome="formal"),
            policy,
        )
    )
    conditional = _row(
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution, outcome="conditional"),
            policy,
        )
    )

    assert formal["transferability_score"] > conditional["transferability_score"]
    assert formal["confidence_factor"] > conditional["confidence_factor"]
    assert _active_midpoint(formal) > _active_midpoint(conditional) > 0.0


def test_higher_disagreement_reduces_center_and_broadens_interval() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    transferability = _transferability(distribution)
    common_policy = {
        "max_active_tilt": 0.30,
        "active_risk_budget_cap": 1.0,
    }

    low = _row(
        module.suggest_weight_ranges(
            distribution,
            transferability,
            _policy(distribution, model_disagreement=0.05, **common_policy),
        )
    )
    high = _row(
        module.suggest_weight_ranges(
            distribution,
            transferability,
            _policy(distribution, model_disagreement=0.80, **common_policy),
        )
    )

    assert abs(_active_midpoint(high)) < abs(_active_midpoint(low))
    assert high["range_width"] > low["range_width"]
    assert high["range_width"] >= high["neutral_range_width"]


@pytest.mark.parametrize(
    ("outcome", "minimum_score", "reason_name"),
    [
        (
            "retrospective_only",
            0.60,
            "TRANSFERABILITY_RETROSPECTIVE_ONLY",
        ),
        ("unavailable", 0.60, "TRANSFERABILITY_UNAVAILABLE"),
        ("formal", 0.99, "BELOW_MIN_TRANSFERABILITY_SCORE"),
    ],
)
def test_ineligible_transferability_has_explicit_reason_and_no_numeric_range(
    outcome: str,
    minimum_score: float,
    reason_name: str,
) -> None:
    module = _weights_module()
    distribution = _current_distribution()
    config = module.WeightRangeConfig(min_transferability_score=minimum_score)
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution, outcome=outcome),
        _policy(distribution),
        config,
    )

    row = _row(result)
    assert row["range_status"] == "unavailable"
    assert np.isnan(row["min_weight"])
    assert np.isnan(row["max_weight"])
    assert getattr(module.WeightRangeReason, reason_name) in row["reason_codes"]


def test_distribution_unavailable_has_no_numeric_range() -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": None})
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(distribution),
    )

    row = _row(result)
    assert row["range_status"] == "unavailable"
    assert np.isnan(row["expected_excess_return"])
    assert np.isnan(row["downside_risk"])
    assert np.isnan(row["min_weight"])
    assert np.isnan(row["max_weight"])
    assert module.WeightRangeReason.DISTRIBUTION_UNAVAILABLE in row["reason_codes"]


def test_leverage_liquidity_currency_and_proxy_caveats_are_explicit() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    policy = _policy(
        distribution,
        leveraged=True,
        liquidity_constrained=True,
        currency_exposed=True,
        proxy_asset=False,
    )
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution, proxy_discount=0.10),
        policy,
    )

    caveats = _row(result)["caveat_codes"]
    assert caveats == (
        module.WeightRangeCaveat.STANDALONE_RESEARCH,
        module.WeightRangeCaveat.LEVERAGE,
        module.WeightRangeCaveat.LIQUIDITY,
        module.WeightRangeCaveat.CURRENCY,
        module.WeightRangeCaveat.PROXY,
    )


def test_multiple_assets_are_not_normalized_and_keep_standalone_scope() -> None:
    module = _weights_module()
    distribution = _current_distribution(
        {
            "asset_alpha": POSITIVE_RATES,
            "asset_beta": POSITIVE_RATES,
        }
    )
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(
            distribution,
            neutral_min_weight=0.55,
            neutral_max_weight=0.65,
            max_active_tilt=0.02,
        ),
    )
    horizon = result.summary.loc[result.summary["horizon_months"].eq(3)]

    assert horizon["min_weight"].sum() > 1.0
    assert horizon["max_weight"].sum() > 1.0
    assert set(horizon["scope"]) == {module.STANDALONE_RESEARCH_SCOPE}
    assert all(
        module.WeightRangeCaveat.STANDALONE_RESEARCH in caveats
        for caveats in horizon["caveat_codes"]
    )


@pytest.mark.parametrize(
    "metric",
    ["cvar95", "drawdown_q95", "max_cvar95_drawdown_q95"],
)
def test_configured_downside_metric_is_retained_and_auditable(metric: str) -> None:
    module = _weights_module()
    distribution = _current_distribution({"asset_alpha": HIGH_DOWNSIDE_RATES})
    result = module.suggest_weight_ranges(
        distribution,
        _transferability(distribution),
        _policy(distribution),
        module.WeightRangeConfig(downside_risk_metric=metric),
    )

    row = _row(result)
    expected = {
        "cvar95": row["cvar95"],
        "drawdown_q95": row["drawdown_q95"],
        "max_cvar95_drawdown_q95": max(row["cvar95"], row["drawdown_q95"]),
    }[metric]
    assert row["downside_risk_metric"] == metric
    assert row["downside_risk"] == pytest.approx(expected)


def test_output_contract_is_exact_auditable_bounded_and_provenanced() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    transferability = _transferability(distribution)
    policy = _policy(distribution, model_disagreement=0.25)
    result = module.suggest_weight_ranges(
        distribution,
        transferability,
        policy,
    )

    assert tuple(result.summary.columns) == module.WEIGHT_RANGE_SUMMARY_COLUMNS
    assert tuple(result.policy.columns) == module.WEIGHT_POLICY_COLUMNS
    row = _row(result)
    assert 0.0 <= row["min_weight"] < row["max_weight"] <= 1.0
    assert row["range_width"] >= row["neutral_range_width"]
    assert row["expected_excess_return"] == pytest.approx(
        distribution.summary.loc[
            distribution.summary["return_basis"].eq("excess")
            & distribution.summary["horizon_months"].eq(3),
            "expected_return",
        ].item()
    )
    assert row["run_id"] == RUN_ID
    assert row["as_of"] == AS_OF
    assert row["data_vintage"] == AS_OF - timedelta(days=1)
    assert row["model_version"] == MODEL_VERSION
    assert row["distribution_config_hash"] == DISTRIBUTION_CONFIG_HASH
    assert row["transferability_config_hash"] == (transferability.config.config_hash)
    assert row["weight_config_hash"] == result.config.config_hash
    assert row["policy_hash"] == result.policy_hash
    assert row["policy_version"] == "weight-policy-v1"
    assert row["policy_date"] == AS_OF
    assert row["transferability_reason_codes"] == (
        transferability.summary.loc[
            transferability.summary["horizon_months"].eq(3),
            "reason_codes",
        ].item()
    )


def test_no_exact_single_weight_output_field_is_published() -> None:
    module = _weights_module()
    columns = set(module.WEIGHT_RANGE_SUMMARY_COLUMNS)

    assert {"min_weight", "max_weight"}.issubset(columns)
    assert columns.isdisjoint(
        {
            "weight",
            "target_weight",
            "optimized_weight",
            "recommended_weight",
            "range_center_weight",
        }
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "duplicate", "unsupported_horizon"],
)
def test_policy_dimensions_must_exactly_match_asset_horizons(
    mutation: str,
) -> None:
    module = _weights_module()
    distribution = _current_distribution()
    policy = _policy(distribution)
    if mutation == "missing":
        policy = policy.iloc[:-1].copy()
    elif mutation == "extra":
        extra = policy.iloc[[0]].copy()
        extra["asset_id"] = "asset_extra"
        policy = pd.concat([policy, extra], ignore_index=True)
    elif mutation == "duplicate":
        policy = pd.concat([policy, policy.iloc[[0]]], ignore_index=True)
    else:
        policy.loc[policy.index[-1], "horizon_months"] = 9

    with pytest.raises(ValueError, match="policy.*(dimension|coverage|horizon|unique)"):
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution),
            policy,
        )


@pytest.mark.parametrize("field", ["run_id", "as_of", "asset_id"])
def test_distribution_and_transferability_must_align_exactly(field: str) -> None:
    module = _weights_module()
    distribution = _current_distribution()
    if field == "run_id":
        other = _current_distribution(run_id=ALT_RUN_ID)
    elif field == "as_of":
        other = _current_distribution(
            as_of=date(2024, 5, 31),
            run_id="2024-05-31-cccccccccccc-dddddddddddd",
        )
    else:
        other = _current_distribution({"asset_beta": POSITIVE_RATES})

    with pytest.raises(ValueError, match="align|provenance|dimension|run_id|as_of"):
        module.suggest_weight_ranges(
            distribution,
            _transferability(other),
            _policy(distribution),
        )


@pytest.mark.parametrize("field", ["run_id", "as_of"])
def test_optional_policy_provenance_must_align_when_supplied(field: str) -> None:
    module = _weights_module()
    distribution = _current_distribution()
    policy = _policy(distribution)
    if field == "run_id":
        policy[field] = ALT_RUN_ID
    else:
        policy[field] = date(2024, 5, 31)

    with pytest.raises(ValueError, match="policy.*(run_id|as_of|provenance|align)"):
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution),
            policy,
        )


def test_future_dated_policy_evidence_is_rejected() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    policy = _policy(distribution, policy_date=AS_OF + timedelta(days=1))

    with pytest.raises(ValueError, match="policy_date.*as_of|future"):
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution),
            policy,
        )


def test_post_construction_distribution_summary_forgery_is_rejected() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    transferability = _transferability(distribution)
    policy = _policy(distribution)
    forged_summary = distribution.summary
    forged_summary.loc[
        forged_summary["horizon_months"].eq(3)
        & forged_summary["return_basis"].eq("excess"),
        "expected_return",
    ] = 0.99
    object.__setattr__(distribution, "summary", forged_summary)

    with pytest.raises(
        ValueError,
        match="inconsistent retained distribution inputs|distribution.*inconsistent",
    ):
        module.suggest_weight_ranges(
            distribution,
            transferability,
            policy,
        )


def test_input_shuffle_is_deterministic() -> None:
    module = _weights_module()
    distribution = _current_distribution(
        {
            "asset_alpha": POSITIVE_RATES,
            "asset_beta": HIGH_DOWNSIDE_RATES,
        }
    )
    transferability = _transferability(distribution)
    policy = _policy(distribution, model_disagreement=0.30)
    baseline = module.suggest_weight_ranges(
        distribution,
        transferability,
        policy,
    )

    shuffled_distribution = _current_distribution(
        {
            "asset_alpha": POSITIVE_RATES,
            "asset_beta": HIGH_DOWNSIDE_RATES,
        }
    )
    object.__setattr__(
        shuffled_distribution,
        "summary",
        shuffled_distribution.summary.sample(frac=1.0, random_state=11),
    )
    shuffled_transferability = _transferability(shuffled_distribution)
    object.__setattr__(
        shuffled_transferability,
        "summary",
        shuffled_transferability.summary.sample(frac=1.0, random_state=13),
    )
    object.__setattr__(
        shuffled_transferability,
        "evidence",
        shuffled_transferability.evidence.sample(frac=1.0, random_state=17),
    )
    shuffled = module.suggest_weight_ranges(
        shuffled_distribution,
        shuffled_transferability,
        policy.sample(frac=1.0, random_state=19),
    )

    pd.testing.assert_frame_equal(baseline.summary, shuffled.summary)
    pd.testing.assert_frame_equal(baseline.policy, shuffled.policy)


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("min_weight", 0.123),
        ("confidence_factor", 0.123),
        ("reason_codes", ("forged",)),
        ("caveat_codes", ("forged",)),
        ("weight_config_hash", "f" * 64),
    ],
)
def test_result_constructor_rejects_forged_summary(
    column: str,
    replacement: object,
) -> None:
    module = _weights_module()
    distribution = _current_distribution()
    transferability = _transferability(distribution)
    result = module.suggest_weight_ranges(
        distribution,
        transferability,
        _policy(distribution),
    )
    forged = result.summary
    forged.loc[0, column] = replacement

    with pytest.raises(ValueError, match="summary|recomputed|inconsistent|retained"):
        module.WeightRangeResult(
            summary=forged,
            policy=result.policy,
            distribution=distribution,
            transferability=transferability,
            config=result.config,
        )


def test_config_result_and_frames_are_immutable_and_defensive() -> None:
    module = _weights_module()
    config = module.WeightRangeConfig()
    assert config.config_hash == module.WeightRangeConfig().config_hash
    with pytest.raises(FrozenInstanceError):
        config.min_transferability_score = 0.0

    distribution = _current_distribution()
    transferability = _transferability(distribution)
    policy = _policy(distribution)
    result = module.suggest_weight_ranges(
        distribution,
        transferability,
        policy,
        config,
    )
    policy.loc[0, "neutral_min_weight"] = 0.0
    visible_summary = result.summary
    visible_policy = result.policy
    visible_summary.loc[0, "min_weight"] = 0.0
    visible_policy.loc[0, "neutral_min_weight"] = 0.0

    assert result.policy.loc[0, "neutral_min_weight"] == pytest.approx(0.40)
    assert result.summary.loc[0, "min_weight"] != 0.0
    with pytest.raises(FrozenInstanceError):
        result.config = module.WeightRangeConfig()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_transferability_score", -0.01),
        ("min_transferability_score", 1.01),
        ("conditional_confidence_multiplier", 1.01),
        ("max_signal_active_tilt", -0.01),
        ("downside_risk_floor", 0.0),
        ("disagreement_range_multiplier", -0.01),
        ("downside_risk_metric", "invented"),
    ],
)
def test_config_rejects_invalid_policy_numbers(field: str, value: object) -> None:
    module = _weights_module()

    with pytest.raises((TypeError, ValueError)):
        module.WeightRangeConfig(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("neutral_min_weight", -0.01),
        ("neutral_max_weight", 1.01),
        ("max_active_tilt", -0.01),
        ("active_risk_budget_cap", -0.01),
        ("model_disagreement", 1.01),
        ("leveraged", 1),
        ("liquidity_constrained", "yes"),
        ("currency_exposed", None),
        ("policy_version", ""),
    ],
)
def test_policy_strictly_validates_numbers_booleans_and_version(
    field: str,
    value: object,
) -> None:
    module = _weights_module()
    distribution = _current_distribution()

    with pytest.raises((TypeError, ValueError)):
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution),
            _policy(distribution, **{field: value}),
        )


def test_neutral_range_must_be_strictly_ordered() -> None:
    module = _weights_module()
    distribution = _current_distribution()

    with pytest.raises(ValueError, match="neutral.*min.*max|ordered"):
        module.suggest_weight_ranges(
            distribution,
            _transferability(distribution),
            _policy(
                distribution,
                neutral_min_weight=0.50,
                neutral_max_weight=0.50,
            ),
        )


def test_api_requires_governed_distribution_and_transferability_results() -> None:
    module = _weights_module()
    distribution = _current_distribution()
    transferability = _transferability(distribution)
    policy = _policy(distribution)

    with pytest.raises(TypeError, match="CurrentDistributionResult|distribution"):
        module.suggest_weight_ranges(object(), transferability, policy)
    with pytest.raises(
        TypeError,
        match="TransferabilityResult|transferability",
    ):
        module.suggest_weight_ranges(distribution, object(), policy)
