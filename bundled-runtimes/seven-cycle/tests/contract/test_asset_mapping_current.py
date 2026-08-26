from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.mapping.distribution import (
    CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    CurrentDistributionConfig,
    CurrentDistributionResult,
    direction_probabilities,
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
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.mapping.transferability import (
    TransferabilityConfig,
    score_transferability,
)
from seven_cycle_platform.mapping.weights import (
    WEIGHT_POLICY_COLUMNS,
    suggest_weight_ranges,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


AS_OF = date(2024, 6, 30)
ASSET_ID = "asset_alpha"
HORIZONS = (3, 6, 12)
M3_RUN_ID = "2024-06-28-aaaaaaaaaaaa-bbbbbbbbbbbb"
M3_CONFIG_HASH = "e" * 64

EXPECTED_COLUMNS = [
    "asset_id",
    "horizon_months",
    "absolute_up_probability",
    "absolute_neutral_probability",
    "absolute_down_probability",
    "absolute_q10",
    "absolute_q25",
    "absolute_q50",
    "absolute_q75",
    "absolute_q90",
    "absolute_expected_return",
    "absolute_volatility",
    "absolute_var95",
    "absolute_cvar95",
    "absolute_drawdown_q50",
    "absolute_drawdown_q80",
    "absolute_drawdown_q95",
    "absolute_distribution_status",
    "absolute_effective_samples",
    "absolute_calibration_version",
    "excess_up_probability",
    "excess_neutral_probability",
    "excess_down_probability",
    "excess_q10",
    "excess_q25",
    "excess_q50",
    "excess_q75",
    "excess_q90",
    "excess_expected_return",
    "excess_volatility",
    "excess_var95",
    "excess_cvar95",
    "excess_drawdown_q50",
    "excess_drawdown_q80",
    "excess_drawdown_q95",
    "excess_distribution_status",
    "excess_effective_samples",
    "excess_calibration_version",
    "cycle_influence_json",
    "channel_influence_json",
    "influence_status",
    "influence_evidence_level",
    "influence_reason_codes",
    "influence_source_stage",
    "influence_run_id",
    "influence_source_date",
    "influence_model_version",
    "influence_config_hash",
    "published_min_weight",
    "published_max_weight",
    "neutral_min_weight",
    "neutral_max_weight",
    "source_range_status",
    "range_status",
    "range_scope",
    "range_reason_codes",
    "range_caveat_codes",
    "policy_date",
    "policy_version",
    "policy_hash",
    "transferability_score",
    "transferability_status",
    "sign_score",
    "magnitude_score",
    "neighbor_score",
    "constituent_score",
    "valuation_positioning_score",
    "structural_score",
    "cycle_confidence_score",
    "channel_confidence_score",
    "proxy_quality_score",
    "oos_increment_score",
    "baseline_gate_passed",
    "formal_hard_gates_passed",
    "transferability_reason_codes",
    "transferability_evidence_date",
    "transferability_validation_end",
    "mapping_status",
    "evidence_level",
    "freshness_status",
    "stale_feature_count",
    "freshness_reason_codes",
    "stale_feature_json",
    "publication_status",
    "publication_reason_codes",
    "caveat_codes",
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "snapshot_config_hash",
    "distribution_config_hash",
    "transferability_config_hash",
    "weight_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
    "created_at",
]

M3_INFLUENCE_COLUMNS = [
    "asset_id",
    "horizon_months",
    "component_type",
    "component_id",
    "influence_score",
    "status",
    "evidence_level",
    "reason_code",
    "source_stage",
    "source_run_id",
    "source_date",
    "source_model_version",
    "source_config_hash",
]


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context() -> RunContext:
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF - timedelta(days=1),
        model_version="asset-mapping-current-contract-v1",
        config={"mapping": "current", "as_of": AS_OF.isoformat()},
        input_checksums={"fixture.json": _checksum(b"asset-mapping-current")},
        quality_summary={"failed": 0, "passed": 1},
        created_at=datetime(2026, 7, 14, 4, 0, tzinfo=timezone.utc),
    )


def _feature(
    *,
    kind: FeatureKind,
    feature_id: str,
    entity_id: str | None = None,
) -> FeatureInput:
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values={"value": 0.25},
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=AS_OF - timedelta(days=5),
        release_date=AS_OF - timedelta(days=4),
        vintage_date=AS_OF - timedelta(days=3),
        source="contract-fixture-archive",
        unit="score",
        retrieval_time=datetime.combine(
            AS_OF - timedelta(days=2),
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=VintageKind.REALTIME,
        methodology="point_in_time_contract_fixture",
    )
    return FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=30,
            max_visible_age_days=30,
        ),
        structural_drift=StructuralDriftFlag(
            detected=False,
            score=0.10,
            threshold=0.50,
            method="rolling_population_stability_index",
            baseline_id="mapping-baseline-v1",
            evaluated_at=AS_OF - timedelta(days=2),
            reason="within threshold",
        ),
    )


def _snapshot(
    *,
    channel_ids: tuple[str, ...] = ("growth_transmission",),
) -> CurrentFeatureSnapshot:
    context = _context()
    return CurrentFeatureSnapshot(
        as_of=AS_OF,
        cycle_states=tuple(
            _feature(kind=FeatureKind.CYCLE, feature_id=f"C{position}")
            for position in range(1, 8)
        ),
        channel_states=tuple(
            _feature(kind=FeatureKind.CHANNEL, feature_id=channel_id)
            for channel_id in channel_ids
        ),
        valuation_controls=(
            _feature(
                kind=FeatureKind.VALUATION,
                feature_id="forward_pe",
                entity_id=ASSET_ID,
            ),
        ),
        earnings_controls=(
            _feature(
                kind=FeatureKind.EARNINGS,
                feature_id="earnings_revision",
                entity_id=ASSET_ID,
            ),
        ),
        positioning_controls=(
            _feature(
                kind=FeatureKind.POSITIONING,
                feature_id="fund_positioning",
                entity_id=ASSET_ID,
            ),
        ),
        liquidity_controls=(
            _feature(
                kind=FeatureKind.LIQUIDITY,
                feature_id="market_liquidity",
                entity_id=ASSET_ID,
            ),
        ),
        event_scenarios=(
            _feature(
                kind=FeatureKind.EVENT,
                feature_id="policy_surprise",
                entity_id=ASSET_ID,
            ),
        ),
        historical_posterior=(
            _feature(
                kind=FeatureKind.HISTORICAL_POSTERIOR,
                feature_id="asset_posterior",
                entity_id=ASSET_ID,
            ),
        ),
        run_context=context,
    )


def _distribution(snapshot: CurrentFeatureSnapshot) -> CurrentDistributionResult:
    monthly_rates = (0.025, 0.010, -0.015, 0.005, 0.020)
    config = CurrentDistributionConfig(
        draw_count=len(monthly_rates),
        seed=0,
        residual_block_length=1,
        min_effective_samples=1,
    )
    future_dates = pd.date_range("2024-07-31", periods=12, freq="ME")
    monthly_rows: list[dict[str, object]] = []
    draw_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for draw_id, monthly_return in enumerate(monthly_rates):
        for month_number, forecast_date in enumerate(future_dates, start=1):
            monthly_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "draw_id": draw_id,
                    "month_number": month_number,
                    "date": forecast_date,
                    "forecast_origin": AS_OF,
                    "asset_monthly_return": monthly_return,
                    "benchmark_monthly_return": 0.0,
                    "relative_monthly_return": monthly_return,
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                }
            )

    for horizon_months in HORIZONS:
        returns: list[float] = []
        drawdowns: list[float] = []
        for draw_id, monthly_return in enumerate(monthly_rates):
            horizon_return = (1.0 + monthly_return) ** horizon_months - 1.0
            drawdown = float(
                compute_max_drawdown(np.repeat(monthly_return, horizon_months))
            )
            returns.append(horizon_return)
            drawdowns.append(drawdown)
            draw_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "draw_id": draw_id,
                    "horizon_months": horizon_months,
                    "absolute_return": horizon_return,
                    "benchmark_return": 0.0,
                    "excess_return": horizon_return,
                    "absolute_max_drawdown": drawdown,
                    "excess_max_drawdown": drawdown,
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                }
            )
        return_values = np.asarray(returns, dtype="float64")
        drawdown_values = np.asarray(drawdowns, dtype="float64")
        q10, q25, q50, q75, q90 = np.quantile(
            return_values,
            [0.10, 0.25, 0.50, 0.75, 0.90],
        )
        risk = summarize_risk(return_values, drawdown_values)
        for return_basis in ("absolute", "excess"):
            probabilities = direction_probabilities(
                return_values,
                neutral_band=config.neutral_bands[(return_basis, horizon_months)],
            )
            summary_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "horizon_months": horizon_months,
                    "return_basis": return_basis,
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
                    "expected_return": float(np.mean(return_values)),
                    "volatility": risk.volatility,
                    "var95": risk.var95,
                    "cvar95": risk.cvar95,
                    "drawdown_q50": risk.drawdown_q50,
                    "drawdown_q80": risk.drawdown_q80,
                    "drawdown_q95": risk.drawdown_q95,
                    "effective_samples": 36,
                    "stage1_training_count": 36,
                    "stage2_effective_training_count": 36,
                    "residual_history_count": 36,
                    "status": "available",
                    "calibration_version": "identity-v1",
                    "run_id": snapshot.provenance.run_id,
                    "snapshot_as_of": AS_OF,
                    "snapshot_data_vintage": snapshot.provenance.data_vintage,
                    "snapshot_model_version": snapshot.provenance.model_version,
                    "snapshot_config_hash": snapshot.provenance.config_hash,
                    "stage1_posterior_date": AS_OF - timedelta(days=2),
                    "stage2_posterior_date": AS_OF - timedelta(days=2),
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


def _governed_inputs(
    *,
    channel_ids: tuple[str, ...] = ("growth_transmission",),
):
    snapshot = _snapshot(channel_ids=channel_ids)
    distribution = _distribution(snapshot)
    evidence_rows = []
    for horizon_months in HORIZONS:
        evidence_rows.append(
            {
                "asset_id": ASSET_ID,
                "horizon_months": horizon_months,
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
                "evidence_date": AS_OF - timedelta(days=1),
                "validation_end": date(2024, 5, 31),
            }
        )
    transferability = score_transferability(
        distribution,
        pd.DataFrame(evidence_rows),
        TransferabilityConfig(),
    )
    policy = pd.DataFrame(
        [
            {
                "asset_id": ASSET_ID,
                "horizon_months": horizon_months,
                "neutral_min_weight": 0.40,
                "neutral_max_weight": 0.50,
                "max_active_tilt": 0.20,
                "active_risk_budget_cap": 0.20,
                "model_disagreement": 0.0,
                "leveraged": False,
                "liquidity_constrained": False,
                "currency_exposed": False,
                "policy_date": AS_OF,
                "policy_version": "weight-policy-v1",
            }
            for horizon_months in HORIZONS
        ],
        columns=WEIGHT_POLICY_COLUMNS,
    )
    weight_ranges = suggest_weight_ranges(distribution, transferability, policy)
    influence_rows = []
    for horizon_months in HORIZONS:
        for component_id in tuple(f"C{position}" for position in range(1, 8)):
            influence_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "horizon_months": horizon_months,
                    "component_type": "cycle",
                    "component_id": component_id,
                    "influence_score": 0.10,
                    "status": "available",
                    "evidence_level": "high",
                    "reason_code": "score_available",
                    "source_stage": "m3_asset_attribution",
                    "source_run_id": M3_RUN_ID,
                    "source_date": AS_OF - timedelta(days=2),
                    "source_model_version": "m3-attribution-v1",
                    "source_config_hash": M3_CONFIG_HASH,
                }
            )
        for channel_id in channel_ids:
            influence_rows.append(
                {
                    "asset_id": ASSET_ID,
                    "horizon_months": horizon_months,
                    "component_type": "channel",
                    "component_id": channel_id,
                    "influence_score": -0.20,
                    "status": "available",
                    "evidence_level": "high",
                    "reason_code": "score_available",
                    "source_stage": "m3_asset_attribution",
                    "source_run_id": M3_RUN_ID,
                    "source_date": AS_OF - timedelta(days=2),
                    "source_model_version": "m3-attribution-v1",
                    "source_config_hash": M3_CONFIG_HASH,
                }
            )
    influence = pd.DataFrame(influence_rows, columns=M3_INFLUENCE_COLUMNS)
    return snapshot, distribution, transferability, weight_ranges, influence


def _api():
    try:
        return importlib.import_module(
            "seven_cycle_platform.products.asset_mapping_current"
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 23 product module is missing: {error}", pytrace=False)


def _canonical_json(value: str) -> object:
    parsed = json.loads(value)
    assert value == json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return parsed


def test_asset_mapping_current_arrow_schema_is_exact_and_stable() -> None:
    api = _api()
    string_columns = {
        name
        for name in EXPECTED_COLUMNS
        if name
        not in {
            "horizon_months",
            "absolute_up_probability",
            "absolute_neutral_probability",
            "absolute_down_probability",
            "absolute_q10",
            "absolute_q25",
            "absolute_q50",
            "absolute_q75",
            "absolute_q90",
            "absolute_expected_return",
            "absolute_volatility",
            "absolute_var95",
            "absolute_cvar95",
            "absolute_drawdown_q50",
            "absolute_drawdown_q80",
            "absolute_drawdown_q95",
            "absolute_effective_samples",
            "excess_up_probability",
            "excess_neutral_probability",
            "excess_down_probability",
            "excess_q10",
            "excess_q25",
            "excess_q50",
            "excess_q75",
            "excess_q90",
            "excess_expected_return",
            "excess_volatility",
            "excess_var95",
            "excess_cvar95",
            "excess_drawdown_q50",
            "excess_drawdown_q80",
            "excess_drawdown_q95",
            "excess_effective_samples",
            "published_min_weight",
            "published_max_weight",
            "neutral_min_weight",
            "neutral_max_weight",
            "transferability_score",
            "sign_score",
            "magnitude_score",
            "neighbor_score",
            "constituent_score",
            "valuation_positioning_score",
            "structural_score",
            "cycle_confidence_score",
            "channel_confidence_score",
            "proxy_quality_score",
            "oos_increment_score",
            "baseline_gate_passed",
            "formal_hard_gates_passed",
            "stale_feature_count",
            "influence_source_date",
            "policy_date",
            "transferability_evidence_date",
            "transferability_validation_end",
            "as_of",
            "data_vintage",
            "stage1_posterior_date",
            "stage2_posterior_date",
            "forecast_origin",
            "created_at",
        }
    }
    expected_types = {name: pa.string() for name in string_columns}
    expected_types.update(
        {
            "horizon_months": pa.int32(),
            "absolute_effective_samples": pa.int32(),
            "excess_effective_samples": pa.int32(),
            "stale_feature_count": pa.int32(),
            "baseline_gate_passed": pa.bool_(),
            "formal_hard_gates_passed": pa.bool_(),
            "influence_source_date": pa.date32(),
            "policy_date": pa.date32(),
            "transferability_evidence_date": pa.date32(),
            "transferability_validation_end": pa.date32(),
            "as_of": pa.date32(),
            "data_vintage": pa.date32(),
            "stage1_posterior_date": pa.date32(),
            "stage2_posterior_date": pa.date32(),
            "forecast_origin": pa.date32(),
            "created_at": pa.timestamp("us", tz="UTC"),
        }
    )
    for name in EXPECTED_COLUMNS:
        if name not in expected_types:
            expected_types[name] = pa.float64()

    assert api.ASSET_MAPPING_CURRENT_COLUMNS == tuple(EXPECTED_COLUMNS)
    assert api.M3_INFLUENCE_COLUMNS == tuple(M3_INFLUENCE_COLUMNS)
    assert api.ASSET_MAPPING_CURRENT_SCHEMA.names == EXPECTED_COLUMNS
    assert {
        field.name: field.type for field in api.ASSET_MAPPING_CURRENT_SCHEMA
    } == expected_types
    forbidden = {
        "target_weight",
        "recommended_weight",
        "optimal_weight",
        "exact_weight",
        "automatic_weight",
    }
    assert forbidden.isdisjoint(api.ASSET_MAPPING_CURRENT_COLUMNS)


def test_builder_is_deterministic_defensive_and_locks_numeric_invariants() -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    influence_before = influence.copy(deep=True)

    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    repeated = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence.sample(frac=1.0, random_state=17).reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(influence, influence_before, check_exact=True)
    pd.testing.assert_frame_equal(product.mapping, repeated.mapping, check_exact=True)
    assert list(product.mapping.columns) == EXPECTED_COLUMNS
    assert len(product.mapping) == 3
    assert not product.mapping.duplicated(["asset_id", "horizon_months"]).any()
    assert set(product.mapping["horizon_months"]) == set(HORIZONS)
    assert product.mapping["run_id"].eq(snapshot.provenance.run_id).all()
    assert product.mapping["as_of"].eq(AS_OF).all()
    assert product.mapping["created_at"].eq(snapshot.provenance.created_at).all()

    for row in product.mapping.itertuples(index=False):
        for basis in ("absolute", "excess"):
            probabilities = np.asarray(
                [
                    getattr(row, f"{basis}_up_probability"),
                    getattr(row, f"{basis}_neutral_probability"),
                    getattr(row, f"{basis}_down_probability"),
                ]
            )
            assert np.isclose(probabilities.sum(), 1.0)
            assert bool(((probabilities >= 0.0) & (probabilities <= 1.0)).all())
            quantiles = [
                getattr(row, f"{basis}_{name}")
                for name in ("q10", "q25", "q50", "q75", "q90")
            ]
            assert quantiles == sorted(quantiles)
            assert getattr(row, f"{basis}_volatility") >= 0.0
            assert getattr(row, f"{basis}_cvar95") >= getattr(row, f"{basis}_var95")
            drawdowns = [
                getattr(row, f"{basis}_{name}")
                for name in ("drawdown_q50", "drawdown_q80", "drawdown_q95")
            ]
            assert drawdowns == sorted(drawdowns)
        cycles = _canonical_json(row.cycle_influence_json)
        channels = _canonical_json(row.channel_influence_json)
        assert [entry["component_id"] for entry in cycles] == [
            f"C{position}" for position in range(1, 8)
        ]
        assert [entry["component_id"] for entry in channels] == ["growth_transmission"]
        assert row.range_status == "available"
        assert 0.0 <= row.published_min_weight < row.published_max_weight <= 1.0
        assert row.freshness_status == "fresh"
        assert row.transferability_status in {"formal", "conditional"}
        assert row.publication_status == "live"
        for json_column in (
            "influence_reason_codes",
            "range_reason_codes",
            "range_caveat_codes",
            "transferability_reason_codes",
            "freshness_reason_codes",
            "stale_feature_json",
            "publication_reason_codes",
            "caveat_codes",
        ):
            _canonical_json(getattr(row, json_column))

    detached = product.mapping
    detached.loc[0, "absolute_up_probability"] = 0.0
    assert product.mapping.loc[0, "absolute_up_probability"] != 0.0
    api.validate_asset_mapping_current(
        product,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    signature = inspect.signature(api.build_asset_mapping_current)
    assert "context" not in signature.parameters
    assert "run_id" not in signature.parameters


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda frame: frame.iloc[1:].reset_index(drop=True),
            "coverage|C1-C7",
        ),
        (
            lambda frame: frame.assign(source_date=AS_OF + timedelta(days=1)),
            "source_date|future",
        ),
        (
            lambda frame: frame.assign(source_stage="manual_narrative"),
            "M3|source_stage",
        ),
        (
            lambda frame: frame.assign(
                source_model_version="TUSHARE_TOKEN=must-not-persist"
            ),
            "secret",
        ),
    ],
)
def test_builder_rejects_invalid_or_non_m3_influence(mutate, message: str) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )

    with pytest.raises((TypeError, ValueError), match=message):
        api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            mutate(influence.copy(deep=True)),
        )


def test_builder_requires_complete_dynamic_snapshot_channel_coverage() -> None:
    api = _api()
    channels = ("growth_transmission", "inflation_transmission")
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs(channel_ids=channels)
    )
    incomplete = influence.loc[
        ~(
            influence["asset_id"].eq(ASSET_ID)
            & influence["horizon_months"].eq(3)
            & influence["component_type"].eq("channel")
            & influence["component_id"].eq("inflation_transmission")
        )
    ].reset_index(drop=True)

    with pytest.raises(ValueError, match="channel.*snapshot|complete.*channel"):
        api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            incomplete,
        )


def test_product_is_builder_only_and_rejects_forged_inputs() -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )

    with pytest.raises(TypeError, match="build_asset_mapping_current"):
        api.AssetMappingCurrentProduct(mapping=product.mapping)

    forged_frame = product.mapping
    forged_frame.loc[0, "absolute_up_probability"] = 2.0
    with pytest.raises(ValueError, match="probabilit"):
        api.validate_asset_mapping_current(forged_frame)

    forged_summary = distribution.summary
    forged_summary.loc[0, "q50"] += 0.01
    object.__setattr__(distribution, "summary", forged_summary)
    with pytest.raises(ValueError, match="distribution|retained|inconsistent"):
        api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )


def test_standalone_validator_rejects_impossible_mapping_statuses() -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )

    unavailable_distribution = product.mapping
    row_index = unavailable_distribution.index[0]
    unavailable_distribution.loc[row_index, "absolute_distribution_status"] = (
        "unavailable"
    )
    for suffix in (
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
    ):
        unavailable_distribution.loc[row_index, f"absolute_{suffix}"] = np.nan
    unavailable_distribution.loc[row_index, "absolute_effective_samples"] = 0
    unavailable_distribution.loc[row_index, "range_status"] = "unavailable"
    unavailable_distribution.loc[row_index, "published_min_weight"] = np.nan
    unavailable_distribution.loc[row_index, "published_max_weight"] = np.nan
    unavailable_distribution.loc[row_index, "publication_status"] = "partial"
    unavailable_distribution.loc[row_index, "evidence_level"] = "low"
    unavailable_distribution.loc[row_index, "mapping_status"] = "formal"

    with pytest.raises(ValueError, match="mapping status|mapping_status"):
        api.validate_asset_mapping_current(unavailable_distribution)

    mismatched_transferability = product.mapping
    mismatched_transferability.loc[row_index, "mapping_status"] = "conditional"
    assert (
        mismatched_transferability.loc[row_index, "transferability_status"] == "formal"
    )

    with pytest.raises(ValueError, match="mapping status|mapping_status"):
        api.validate_asset_mapping_current(mismatched_transferability)


def test_writer_is_atomic_deterministic_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    shuffled = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence.sample(frac=1.0, random_state=23).reset_index(drop=True),
    )
    first_dir = tmp_path / "first" / snapshot.provenance.run_id
    second_dir = tmp_path / "second" / snapshot.provenance.run_id
    failure_dir = tmp_path / "failure" / snapshot.provenance.run_id
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    failure_dir.mkdir(parents=True)

    first_path = api.write_asset_mapping_current(first_dir, product)
    second_path = api.write_asset_mapping_current(second_dir, shuffled)

    assert first_path.name == api.ASSET_MAPPING_CURRENT_FILENAME
    assert first_path.read_bytes() == second_path.read_bytes()
    assert pq.read_schema(first_path) == api.ASSET_MAPPING_CURRENT_SCHEMA
    persisted = pd.read_parquet(first_path)
    api.validate_asset_mapping_current(
        persisted,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    with pytest.raises(FileExistsError, match="overwrite"):
        api.write_asset_mapping_current(first_dir, product)

    def fail_write(*args, **kwargs):
        raise OSError("simulated parquet failure")

    monkeypatch.setattr(api.pq, "write_table", fail_write)
    with pytest.raises(OSError, match="simulated parquet failure"):
        api.write_asset_mapping_current(failure_dir, product)
    assert not (failure_dir / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not list(failure_dir.glob(".*.tmp"))


@pytest.mark.parametrize("symlink_location", ["ancestor", "run_dir"])
def test_writer_rejects_symlinked_path_components(
    tmp_path: Path,
    symlink_location: str,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    real_parent = tmp_path / f"real-{symlink_location}"
    real_run_dir = real_parent / snapshot.provenance.run_id
    real_run_dir.mkdir(parents=True)
    if symlink_location == "ancestor":
        alias_parent = tmp_path / "alias-parent"
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        supplied_run_dir = alias_parent / snapshot.provenance.run_id
    else:
        supplied_run_dir = tmp_path / snapshot.provenance.run_id
        supplied_run_dir.symlink_to(real_run_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink|real.*directory"):
        api.write_asset_mapping_current(supplied_run_dir, product)

    assert not (real_run_dir / api.ASSET_MAPPING_CURRENT_FILENAME).exists()


def test_writer_rejects_symlink_target_without_touching_external_file(
    tmp_path: Path,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    run_dir = tmp_path / snapshot.provenance.run_id
    run_dir.mkdir()
    external = tmp_path / "external.parquet"
    external_bytes = b"do-not-touch"
    external.write_bytes(external_bytes)
    target = run_dir / api.ASSET_MAPPING_CURRENT_FILENAME
    target.symlink_to(external)

    with pytest.raises((FileExistsError, ValueError), match="symlink|overwrite|target"):
        api.write_asset_mapping_current(run_dir, product)

    assert target.is_symlink()
    assert external.read_bytes() == external_bytes


def test_writer_rejects_non_directory_ancestor(tmp_path: Path) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    file_ancestor = tmp_path / "not-a-directory"
    file_ancestor.write_bytes(b"protected")
    supplied_run_dir = file_ancestor / snapshot.provenance.run_id

    with pytest.raises(ValueError, match="real.*director|only real directories"):
        api.write_asset_mapping_current(supplied_run_dir, product)

    assert file_ancestor.read_bytes() == b"protected"


def test_writer_removes_linked_target_when_post_publish_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    run_dir = tmp_path / snapshot.provenance.run_id
    run_dir.mkdir()

    def fail_post_publish(*args, **kwargs):
        raise ValueError("simulated post-publish validation failure")

    monkeypatch.setattr(
        api,
        "_validate_published_table_at",
        fail_post_publish,
        raising=False,
    )

    with pytest.raises(ValueError, match="post-publish validation failure"):
        api.write_asset_mapping_current(run_dir, product)

    assert not (run_dir / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not list(run_dir.glob(".*.tmp"))


def test_writer_rejects_run_directory_replacement_before_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    run_dir = tmp_path / snapshot.provenance.run_id
    displaced = tmp_path / "displaced-run"
    run_dir.mkdir()
    original = api._write_temporary_table_at

    def replace_after_temporary_write(directory_descriptor, values):
        result = original(directory_descriptor, values)
        run_dir.rename(displaced)
        run_dir.mkdir()
        return result

    monkeypatch.setattr(
        api,
        "_write_temporary_table_at",
        replace_after_temporary_write,
    )

    with pytest.raises(ValueError, match="replaced|changed"):
        api.write_asset_mapping_current(run_dir, product)

    assert not (run_dir / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not (displaced / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not list(run_dir.glob(".*.tmp"))
    assert not list(displaced.glob(".*.tmp"))


def test_writer_rejects_run_directory_rename_after_final_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    snapshot, distribution, transferability, weight_ranges, influence = (
        _governed_inputs()
    )
    product = api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    run_dir = tmp_path / snapshot.provenance.run_id
    displaced = tmp_path / "post-fsync-displaced-run"
    run_dir.mkdir()
    original_fsync = api.os.fsync
    renamed = False

    def rename_after_directory_fsync(descriptor: int) -> None:
        nonlocal renamed
        original_fsync(descriptor)
        descriptor_stat = api.os.fstat(descriptor)
        target = run_dir / api.ASSET_MAPPING_CURRENT_FILENAME
        if (
            not renamed
            and api.stat.S_ISDIR(descriptor_stat.st_mode)
            and target.exists()
        ):
            run_dir.rename(displaced)
            run_dir.mkdir()
            renamed = True

    monkeypatch.setattr(api.os, "fsync", rename_after_directory_fsync)

    with pytest.raises(ValueError, match="replaced|changed"):
        api.write_asset_mapping_current(run_dir, product)

    assert renamed is True
    assert not (run_dir / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not (displaced / api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not list(run_dir.glob(".*.tmp"))
    assert not list(displaced.glob(".*.tmp"))
