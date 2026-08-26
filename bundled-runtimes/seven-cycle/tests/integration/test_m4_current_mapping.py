from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
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
    WeightRangeConfig,
    suggest_weight_ranges,
)
from seven_cycle_platform.products import asset_mapping_current as product_api
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import ReleaseStatus, VintageKind


AS_OF = date(2024, 6, 30)
ASSETS = ("asset_alpha", "asset_beta")
HORIZONS = (3, 6, 12)
M3_RUN_ID = "2024-06-28-cccccccccccc-dddddddddddd"
M3_CONFIG_HASH = "f" * 64


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context(*, model_version: str = "m4-current-mapping-v1") -> RunContext:
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF - timedelta(days=1),
        model_version=model_version,
        config={"mapping": "m4-current", "as_of": AS_OF.isoformat()},
        input_checksums={"fixture.json": _checksum(b"m4-current-mapping")},
        quality_summary={"failed": 0, "passed": 2},
        created_at=datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc),
    )


def _feature(
    *,
    kind: FeatureKind,
    feature_id: str,
    entity_id: str | None = None,
    stale: bool = False,
) -> FeatureInput:
    age_days = 90 if stale else 5
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values={"value": 0.25},
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=AS_OF - timedelta(days=age_days),
        release_date=AS_OF - timedelta(days=age_days - 1),
        vintage_date=AS_OF - timedelta(days=age_days - 2),
        source="integration-fixture-archive",
        unit="score",
        retrieval_time=datetime.combine(
            AS_OF - timedelta(days=1),
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=VintageKind.REALTIME,
        methodology="point_in_time_integration_fixture",
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
            evaluated_at=AS_OF - timedelta(days=1),
            reason="within threshold",
        ),
    )


def _snapshot(
    *,
    stale_asset: str | None = None,
    global_stale: bool = False,
    model_version: str = "m4-current-mapping-v1",
) -> CurrentFeatureSnapshot:
    controls: dict[FeatureKind, list[FeatureInput]] = {
        FeatureKind.VALUATION: [],
        FeatureKind.EARNINGS: [],
        FeatureKind.POSITIONING: [],
        FeatureKind.LIQUIDITY: [],
    }
    for asset_id in ASSETS:
        controls[FeatureKind.VALUATION].append(
            _feature(
                kind=FeatureKind.VALUATION,
                feature_id="forward_pe",
                entity_id=asset_id,
                stale=asset_id == stale_asset,
            )
        )
        controls[FeatureKind.EARNINGS].append(
            _feature(
                kind=FeatureKind.EARNINGS,
                feature_id="earnings_revision",
                entity_id=asset_id,
            )
        )
        controls[FeatureKind.POSITIONING].append(
            _feature(
                kind=FeatureKind.POSITIONING,
                feature_id="fund_positioning",
                entity_id=asset_id,
            )
        )
        controls[FeatureKind.LIQUIDITY].append(
            _feature(
                kind=FeatureKind.LIQUIDITY,
                feature_id="market_liquidity",
                entity_id=asset_id,
            )
        )
    return CurrentFeatureSnapshot(
        as_of=AS_OF,
        cycle_states=tuple(
            _feature(kind=FeatureKind.CYCLE, feature_id=f"C{position}")
            for position in range(1, 8)
        ),
        channel_states=(
            _feature(
                kind=FeatureKind.CHANNEL,
                feature_id="growth_transmission",
                stale=global_stale,
            ),
        ),
        valuation_controls=tuple(controls[FeatureKind.VALUATION]),
        earnings_controls=tuple(controls[FeatureKind.EARNINGS]),
        positioning_controls=tuple(controls[FeatureKind.POSITIONING]),
        liquidity_controls=tuple(controls[FeatureKind.LIQUIDITY]),
        event_scenarios=tuple(
            _feature(
                kind=FeatureKind.EVENT,
                feature_id="policy_surprise",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        historical_posterior=tuple(
            _feature(
                kind=FeatureKind.HISTORICAL_POSTERIOR,
                feature_id="asset_posterior",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        run_context=_context(model_version=model_version),
    )


def _distribution(
    snapshot: CurrentFeatureSnapshot,
    *,
    unavailable_assets: frozenset[str] = frozenset(),
) -> CurrentDistributionResult:
    rates_by_asset = {
        "asset_alpha": (0.025, 0.015, -0.010, 0.005, 0.020),
        "asset_beta": (0.015, 0.005, -0.020, 0.010, 0.000),
    }
    draw_count = len(next(iter(rates_by_asset.values())))
    config = CurrentDistributionConfig(
        draw_count=draw_count,
        seed=0,
        residual_block_length=1,
        min_effective_samples=1,
    )
    future_dates = pd.date_range("2024-07-31", periods=12, freq="ME")
    monthly_rows: list[dict[str, object]] = []
    draw_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for asset_id, monthly_rates in rates_by_asset.items():
        available = asset_id not in unavailable_assets
        if available:
            for draw_id, monthly_return in enumerate(monthly_rates):
                for month_number, forecast_date in enumerate(future_dates, start=1):
                    monthly_rows.append(
                        {
                            "asset_id": asset_id,
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
            if available:
                for draw_id, monthly_return in enumerate(monthly_rates):
                    horizon_return = (1.0 + monthly_return) ** horizon_months - 1.0
                    drawdown = float(
                        compute_max_drawdown(np.repeat(monthly_return, horizon_months))
                    )
                    returns.append(horizon_return)
                    drawdowns.append(drawdown)
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
                support = 36
                status = "available"
            else:
                return_values = np.asarray([], dtype="float64")
                q10 = q25 = q50 = q75 = q90 = np.nan
                risk = None
                support = 0
                status = "unavailable"

            for return_basis in ("absolute", "excess"):
                if available:
                    probabilities = direction_probabilities(
                        return_values,
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
                        "expected_return": float(np.mean(return_values)),
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


def _transferability(
    distribution: CurrentDistributionResult,
    *,
    outcomes: dict[str, str] | None = None,
):
    selected_outcomes = outcomes or {}
    rows: list[dict[str, object]] = []
    for asset_id in ASSETS:
        outcome = selected_outcomes.get(asset_id, "formal")
        for horizon_months in HORIZONS:
            row: dict[str, object] = {
                "asset_id": asset_id,
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
            if outcome in {"conditional", "low_confidence"}:
                row["valuation_positioning_similarity"] = 0.40
            elif outcome == "retrospective_only":
                row["model_oos_loss"] = 1.00
            elif outcome == "unavailable":
                row["sign_stability"] = np.nan
            elif outcome != "formal":
                raise ValueError(f"unsupported fixture outcome: {outcome}")
            rows.append(row)
    return score_transferability(
        distribution,
        pd.DataFrame(rows),
        TransferabilityConfig(),
    )


def _policy(distribution: CurrentDistributionResult) -> pd.DataFrame:
    dimensions = (
        distribution.summary[["asset_id", "horizon_months"]]
        .drop_duplicates()
        .sort_values(["asset_id", "horizon_months"], kind="stable")
    )
    return pd.DataFrame(
        [
            {
                "asset_id": row.asset_id,
                "horizon_months": row.horizon_months,
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
            for row in dimensions.itertuples(index=False)
        ],
        columns=WEIGHT_POLICY_COLUMNS,
    )


def _influence() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for asset_id in ASSETS:
        for horizon_months in HORIZONS:
            for component_id in tuple(f"C{position}" for position in range(1, 8)):
                rows.append(
                    {
                        "asset_id": asset_id,
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
            rows.append(
                {
                    "asset_id": asset_id,
                    "horizon_months": horizon_months,
                    "component_type": "channel",
                    "component_id": "growth_transmission",
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
    return pd.DataFrame(rows, columns=product_api.M3_INFLUENCE_COLUMNS)


def _inputs(
    *,
    stale_asset: str | None = None,
    global_stale: bool = False,
    outcomes: dict[str, str] | None = None,
    unavailable_assets: frozenset[str] = frozenset(),
    model_version: str = "m4-current-mapping-v1",
):
    snapshot = _snapshot(
        stale_asset=stale_asset,
        global_stale=global_stale,
        model_version=model_version,
    )
    distribution = _distribution(snapshot, unavailable_assets=unavailable_assets)
    transferability = _transferability(distribution, outcomes=outcomes)
    low_confidence = outcomes is not None and "low_confidence" in outcomes.values()
    weight_config = (
        WeightRangeConfig(min_transferability_score=0.94)
        if low_confidence
        else WeightRangeConfig()
    )
    weight_ranges = suggest_weight_ranges(
        distribution,
        transferability,
        _policy(distribution),
        weight_config,
    )
    return snapshot, distribution, transferability, weight_ranges, _influence()


def _verification_api():
    try:
        return importlib.import_module(
            "seven_cycle_platform.verification.current_mapping"
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 23 verification module is missing: {error}", pytrace=False)


def _pipeline_api():
    try:
        return importlib.import_module("seven_cycle_platform.pipeline.current_mapping")
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 23 pipeline module is missing: {error}", pytrace=False)


def _run_dir(tmp_path: Path, snapshot: CurrentFeatureSnapshot, name: str) -> Path:
    path = tmp_path / name / snapshot.provenance.run_id
    path.mkdir(parents=True)
    return path


def test_fully_fresh_inputs_publish_live_readable_parquet(tmp_path: Path) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    run_dir = _run_dir(tmp_path, snapshot, "live")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.LIVE
    assert result.report.release_status is ReleaseStatus.LIVE
    assert result.report.total_asset_count == 2
    assert result.report.live_asset_count == 2
    assert result.report.affected_asset_count == 0
    assert result.report.live_row_count == 6
    assert result.report.partial_row_count == 0
    assert result.written_path is not None and result.written_path.exists()
    assert (
        pq.read_schema(result.written_path) == product_api.ASSET_MAPPING_CURRENT_SCHEMA
    )
    persisted = pd.read_parquet(result.written_path)
    assert len(persisted) == 6
    assert persisted["publication_status"].eq("live").all()
    assert persisted["range_status"].eq("available").all()
    assert persisted["influence_source_stage"].eq("m3_asset_attribution").all()
    assert persisted["influence_source_date"].le(AS_OF).all()
    assert not hasattr(result, "product")
    with pytest.raises(FrozenInstanceError):
        result.report.live_asset_count = 0


def test_asset_specific_stale_feature_degrades_only_that_asset(
    tmp_path: Path,
) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs(
        stale_asset="asset_beta"
    )
    run_dir = _run_dir(tmp_path, snapshot, "partial")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.PARTIAL
    assert result.report.live_asset_count == 1
    assert result.report.affected_asset_count == 1
    persisted = pd.read_parquet(result.written_path)
    alpha = persisted.loc[persisted["asset_id"].eq("asset_alpha")]
    beta = persisted.loc[persisted["asset_id"].eq("asset_beta")]
    assert len(alpha) == len(beta) == 3
    assert alpha["published_min_weight"].notna().all()
    assert alpha["publication_status"].eq("live").all()
    assert beta["published_min_weight"].isna().all()
    assert beta["published_max_weight"].isna().all()
    assert beta["freshness_status"].eq("stale").all()
    assert beta["publication_status"].eq("partial").all()


def test_global_stale_evidence_blocks_when_no_safe_rows_remain(tmp_path: Path) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs(
        global_stale=True
    )
    run_dir = _run_dir(tmp_path, snapshot, "blocked-global")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.BLOCKED
    assert result.report.live_row_count == 0
    assert result.report.partial_row_count == 6
    assert result.report.affected_asset_count == 2
    assert result.written_path is None
    assert not (run_dir / product_api.ASSET_MAPPING_CURRENT_FILENAME).exists()


@pytest.mark.parametrize(
    "outcome",
    ["retrospective_only", "unavailable", "low_confidence"],
)
def test_ineligible_transferability_rows_never_publish_ranges(
    tmp_path: Path,
    outcome: str,
) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs(
        outcomes={"asset_beta": outcome}
    )
    run_dir = _run_dir(tmp_path, snapshot, f"ineligible-{outcome}")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.PARTIAL
    persisted = pd.read_parquet(result.written_path)
    alpha = persisted.loc[persisted["asset_id"].eq("asset_alpha")]
    beta = persisted.loc[persisted["asset_id"].eq("asset_beta")]
    assert alpha["published_min_weight"].notna().all()
    assert beta["published_min_weight"].isna().all()
    assert beta["published_max_weight"].isna().all()
    assert beta["range_status"].eq("unavailable").all()


@pytest.mark.parametrize("failure", ["missing", "invalid", "future"])
def test_missing_invalid_or_future_m3_influence_blocks(
    tmp_path: Path,
    failure: str,
) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    if failure == "missing":
        influence = influence.iloc[1:].reset_index(drop=True)
    elif failure == "invalid":
        influence.loc[0, "component_type"] = "manual"
    else:
        influence["source_date"] = AS_OF + timedelta(days=1)
    run_dir = _run_dir(tmp_path, snapshot, f"bad-influence-{failure}")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.BLOCKED
    assert result.written_path is None
    assert "build_failed" in result.report.issue_codes
    assert not (run_dir / product_api.ASSET_MAPPING_CURRENT_FILENAME).exists()


def test_forged_governed_and_product_inputs_reject() -> None:
    api = _verification_api()

    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    object.__setattr__(snapshot, "as_of", AS_OF - timedelta(days=1))
    with pytest.raises(ValueError, match="snapshot|RunContext|inconsistent"):
        product_api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )

    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    forged_distribution = distribution.summary
    forged_distribution.loc[0, "q50"] += 0.01
    object.__setattr__(distribution, "summary", forged_distribution)
    with pytest.raises(ValueError, match="distribution|inconsistent"):
        product_api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )

    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    forged_transferability = transferability.summary
    forged_transferability.loc[0, "overall_score"] = 0.01
    object.__setattr__(transferability, "summary", forged_transferability)
    with pytest.raises(ValueError, match="transferability|inconsistent"):
        product_api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )

    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    forged_weight = weight_ranges.summary
    forged_weight.loc[0, "min_weight"] += 0.01
    object.__setattr__(weight_ranges, "summary", forged_weight)
    with pytest.raises(ValueError, match="weight-range|inconsistent"):
        product_api.build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )

    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    product = product_api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    forged_product = product.mapping
    forged_product.loc[0, "absolute_up_probability"] = 2.0
    report = api.verify_current_mapping(
        forged_product,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    assert report.release_status is ReleaseStatus.BLOCKED
    assert report.total_row_count == 6
    assert report.live_row_count == 0
    assert report.partial_row_count == 6
    assert report.total_asset_count == 2
    assert report.live_asset_count == 0
    assert report.affected_asset_count == 2
    assert report.issue_codes


def test_writer_failure_leaves_no_partial_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    run_dir = _run_dir(tmp_path, snapshot, "writer-failure")

    def fail_write(*args, **kwargs):
        raise OSError("simulated writer failure")

    monkeypatch.setattr(product_api.pq, "write_table", fail_write)
    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.BLOCKED
    assert "write_failed" in result.report.issue_codes
    assert result.written_path is None
    assert not (run_dir / product_api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert not list(run_dir.glob(".*.tmp"))


def test_no_overwrite_preserves_existing_immutable_file(tmp_path: Path) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    run_dir = _run_dir(tmp_path, snapshot, "no-overwrite")
    first = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    original_bytes = first.written_path.read_bytes()

    second = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert second.release_status is ReleaseStatus.BLOCKED
    assert "write_failed" in second.report.issue_codes
    assert first.written_path.read_bytes() == original_bytes


def test_shuffle_and_repeat_verification_are_deterministic() -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    product = product_api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    shuffled = product_api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence.sample(frac=1.0, random_state=31).reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(product.mapping, shuffled.mapping, check_exact=True)
    first = api.verify_current_mapping(
        product,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    second = api.verify_current_mapping(
        shuffled,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    assert first == second
    assert first.release_status is ReleaseStatus.LIVE


def test_every_published_range_implies_fresh_and_eligible_inputs() -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs(
        stale_asset="asset_beta",
        outcomes={"asset_beta": "retrospective_only"},
    )
    product = product_api.build_asset_mapping_current(
        snapshot,
        distribution,
        transferability,
        weight_ranges,
        influence,
    )
    report = api.verify_current_mapping(
        product,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert report.release_status is ReleaseStatus.PARTIAL
    published = product.mapping.loc[product.mapping["range_status"].eq("available")]
    assert not published.empty
    assert published["freshness_status"].eq("fresh").all()
    assert published["transferability_status"].isin({"formal", "conditional"}).all()
    assert published["absolute_distribution_status"].eq("available").all()
    assert published["excess_distribution_status"].eq("available").all()


def test_secret_like_source_values_are_blocked_and_never_exposed(
    tmp_path: Path,
) -> None:
    api = _verification_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    secret_value = "TUSHARE_TOKEN=do-not-persist"
    influence["source_model_version"] = secret_value
    run_dir = _run_dir(tmp_path, snapshot, "secret")

    result = api.publish_current_mapping(
        run_dir,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )

    assert result.release_status is ReleaseStatus.BLOCKED
    assert result.written_path is None
    assert secret_value not in repr(result)
    assert not (run_dir / product_api.ASSET_MAPPING_CURRENT_FILENAME).exists()
    assert json.dumps(result.report.issue_codes) == '["build_failed"]'


def test_governed_pipeline_requires_m3_input_and_publishes_live(tmp_path: Path) -> None:
    api = _pipeline_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    source_before = influence.copy(deep=True)
    pipeline_input = api.CurrentMappingPipelineInput(
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        m3_influence=influence,
    )
    run_dir = _run_dir(tmp_path, snapshot, "pipeline-live")

    result = api.build_current_mapping(pipeline_input, run_dir=run_dir)

    assert result.release_status is ReleaseStatus.LIVE
    assert result.written_path is not None and result.written_path.exists()
    pd.testing.assert_frame_equal(influence, source_before, check_exact=True)
    detached = pipeline_input.m3_influence
    detached.loc[0, "influence_score"] = 0.99
    pd.testing.assert_frame_equal(
        pipeline_input.m3_influence,
        source_before,
        check_exact=True,
    )
    package = importlib.import_module("seven_cycle_platform.pipeline")
    assert package.build_current_mapping is api.build_current_mapping


def test_governed_pipeline_keeps_safe_assets_when_one_asset_is_stale(
    tmp_path: Path,
) -> None:
    api = _pipeline_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs(
        stale_asset="asset_beta"
    )
    pipeline_input = api.CurrentMappingPipelineInput(
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        m3_influence=influence,
    )
    run_dir = _run_dir(tmp_path, snapshot, "pipeline-partial")

    result = api.build_current_mapping(pipeline_input, run_dir=run_dir)

    assert result.release_status is ReleaseStatus.PARTIAL
    persisted = pd.read_parquet(result.written_path)
    assert (
        persisted.loc[persisted["asset_id"].eq("asset_alpha"), "published_min_weight"]
        .notna()
        .all()
    )
    assert (
        persisted.loc[persisted["asset_id"].eq("asset_beta"), "published_min_weight"]
        .isna()
        .all()
    )


def test_governed_pipeline_blocks_invalid_m3_dependency(tmp_path: Path) -> None:
    api = _pipeline_api()
    snapshot, distribution, transferability, weight_ranges, influence = _inputs()
    incomplete = influence.iloc[1:].reset_index(drop=True)
    pipeline_input = api.CurrentMappingPipelineInput(
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        m3_influence=incomplete,
    )
    run_dir = _run_dir(tmp_path, snapshot, "pipeline-blocked")

    result = api.build_current_mapping(pipeline_input, run_dir=run_dir)

    assert result.release_status is ReleaseStatus.BLOCKED
    assert result.written_path is None
    assert "build_failed" in result.report.issue_codes
    assert not (run_dir / product_api.ASSET_MAPPING_CURRENT_FILENAME).exists()
