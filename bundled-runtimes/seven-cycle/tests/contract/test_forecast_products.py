from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import importlib
import json

import pandas as pd
import pyarrow as pa
import pytest

from seven_cycle_platform.forecast.scenarios import STANDARD_SCENARIO_IDS
from seven_cycle_platform.storage import RunContext


AS_OF = date(2024, 6, 30)
CREATED_AT = datetime(2024, 7, 1, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
MAPPING_ID = "cn-core-assets"
COMPONENT_IDENTITY_COLUMNS = (
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "asset_forecast_model_version",
    "asset_forecast_config_hash",
    "channel_forecast_model_version",
    "channel_forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
)


def _cycle_api():
    return importlib.import_module("seven_cycle_platform.products.cycle_forecast")


def _future_api():
    return importlib.import_module("seven_cycle_platform.products.asset_mapping_future")


def _context() -> RunContext:
    metadata = {
        "schema_version": 1,
        "mapping_product": "asset_mapping_future",
        "mapping_id": MAPPING_ID,
        "artifact_filename": "asset_mapping_future.parquet",
    }
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=AS_OF,
        model_version="m5-forecast-products-v1",
        config={"mapping_id": MAPPING_ID, "release": "task-28"},
        input_checksums={"fixtures/task28.json": HASH_A},
        quality_summary={"mapping_reference": metadata},
        created_at=CREATED_AT,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _component_contract_hash(row: dict[str, object]) -> str:
    baseline_entries = json.loads(str(row["baseline_component_contribution_json"]))
    scenario_entries = json.loads(str(row["scenario_contribution_json"]))
    payload = {
        "schema_version": 1,
        "asset_id": row["asset_id"],
        "scenario_id": row["scenario_id"],
        "horizon_months": row["horizon_months"],
        "baseline_component_keys": sorted(
            [entry["component_type"], entry["component_id"]]
            for entry in baseline_entries
        ),
        "scenario_component_keys": sorted(
            [entry["component_type"], entry["component_id"]]
            for entry in scenario_entries
        ),
        "source_identity": {
            column: row[column] for column in COMPONENT_IDENTITY_COLUMNS
        },
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _promotion_metrics() -> str:
    records = []
    for metric in (
        "brier_score",
        "log_loss",
        "interval_coverage_error",
        "downstream_asset_oos_loss",
    ):
        records.append(
            {
                "challenger_coverage_rate": 0.75,
                "challenger_sample_count": 12,
                "challenger_value": 0.25,
                "champion_coverage_rate": 0.70,
                "champion_sample_count": 12,
                "champion_value": 0.20,
                "fold_count": 3,
                "improvement": -0.05,
                "metric": metric,
                "nominal_coverage": 0.75,
                "paired_sample_count": 12,
            }
        )
    return _canonical(records)


def _cycle_frame() -> pd.DataFrame:
    api = _cycle_api()
    context = _context()
    row = {
        "as_of": AS_OF,
        "cycle_id": "C3",
        "horizon_months": 3,
        "forecast_date": date(2024, 9, 30),
        "status": "available",
        "unavailable_reason": None,
        "expansion_probability": 0.40,
        "downturn_probability": 0.20,
        "contraction_probability": 0.15,
        "recovery_probability": 0.25,
        "angle_anchor_degrees": 35.0,
        "angle_q10": 40.0,
        "angle_q25": 50.0,
        "angle_q50": 60.0,
        "angle_q75": 70.0,
        "angle_q90": 80.0,
        "turning_status": "expected",
        "turning_probability": 0.65,
        "turning_start_month": 1,
        "turning_median_month": 2,
        "turning_end_month": 3,
        "turning_start_date": date(2024, 7, 31),
        "turning_median_date": date(2024, 8, 31),
        "turning_end_date": date(2024, 9, 30),
        "forecast_uncertainty": 0.30,
        "draw_count": 16,
        "probability_support_count": 16,
        "calibration_method": "walk_forward_logistic",
        "calibration_version": "walk-forward-logistic-v1",
        "calibration_sample_count": 48,
        "calibration_reason": "calibrated",
        "forecast_value_source_role": "champion",
        "forecast_value_source_model_id": "cycle-champion",
        "forecast_value_source_model_version": "cycle-champion-v1",
        "live_model_id": "cycle-champion",
        "live_model_role": "champion",
        "live_model_version": "cycle-champion-v1",
        "promotion_decision": "rejected",
        "challenger_model_id": "cycle-challenger",
        "challenger_model_version": "cycle-challenger-v1",
        "challenger_status": "experimental",
        "challenger_failure_reason_codes": _canonical(["BRIER_NOT_IMPROVED"]),
        "promotion_metrics_json": _promotion_metrics(),
        "source_forecast_config_hash": HASH_B,
        "registry_hash": HASH_C,
        "state_model_version": "cycle-state-v1",
        "state_config_hash": HASH_D,
        "source_data_vintage": AS_OF,
        "run_id": context.run_id,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }
    return pd.DataFrame([row], columns=api.CYCLE_FORECAST_COLUMNS)


def _contribution_entry(
    component_type: str,
    component_id: str,
    expected_contribution: float,
    *,
    scenario_id: str,
    kind: str,
) -> dict[str, object]:
    return {
        "aggregation_method": "geometric_shared_prefix_v1",
        "component_id": component_id,
        "component_type": component_type,
        "contribution_kind": kind,
        "draw_count": 16,
        "expected_contribution": expected_contribution,
        "interval50_lower": expected_contribution - 0.001,
        "interval50_upper": expected_contribution + 0.001,
        "interval80_lower": expected_contribution - 0.002,
        "interval80_upper": expected_contribution + 0.002,
        "median": expected_contribution,
        "scenario_id": scenario_id,
    }


def _baseline_contributions(scenario_id: str) -> list[dict[str, object]]:
    values = (
        ("intercept", "intercept", 0.001),
        ("benchmark", "benchmark_return", 0.002),
        ("channel", "growth_demand", 0.010),
        ("valuation", "valuation_z", 0.005),
        ("positioning", "positioning_score", 0.004),
        ("control", "liquidity_control", 0.006),
        ("interaction", "growth_x_valuation", 0.003),
        ("event", "event_shock", 0.010),
        ("residual", "asset_residual", 0.020),
    )
    entries = [
        _contribution_entry(
            component_type,
            component_id,
            expected,
            scenario_id=scenario_id,
            kind="baseline_component",
        )
        for component_type, component_id, expected in values
    ]
    return sorted(
        entries,
        key=lambda entry: (entry["component_type"], entry["component_id"]),
    )


def _scenario_contributions(scenario_id: str) -> list[dict[str, object]]:
    if scenario_id == "baseline":
        return []
    return [
        _contribution_entry(
            "scenario_shock",
            "growth_demand",
            0.005,
            scenario_id=scenario_id,
            kind="scenario_shock",
        )
    ]


def _future_frame() -> pd.DataFrame:
    api = _future_api()
    context = _context()
    records = []
    for scenario_id in STANDARD_SCENARIO_IDS:
        for horizon in (3, 6, 12):
            baseline_passed = horizon == 3
            freshness = "stale" if horizon == 12 else "fresh"
            mapping_status = (
                "formal"
                if horizon == 3
                else "retrospective_only"
                if horizon == 6
                else "unavailable"
            )
            records.append(
                {
                    "scenario_id": scenario_id,
                    "future_date": (
                        pd.Timestamp(AS_OF) + pd.offsets.MonthEnd(horizon)
                    ).date(),
                    "asset_id": "asset_alpha",
                    "horizon_months": horizon,
                    "status": "available",
                    "unavailable_reason": None,
                    "absolute_median": 0.06,
                    "absolute_interval50_lower": 0.03,
                    "absolute_interval50_upper": 0.09,
                    "absolute_interval80_lower": 0.00,
                    "absolute_interval80_upper": 0.12,
                    "absolute_expected_return": (
                        0.061 if scenario_id == "baseline" else 0.066
                    ),
                    "absolute_volatility": 0.04,
                    "absolute_var95": 0.02,
                    "absolute_cvar95": 0.03,
                    "absolute_drawdown_q50": 0.01,
                    "absolute_drawdown_q80": 0.02,
                    "absolute_drawdown_q95": 0.03,
                    "excess_median": 0.03,
                    "excess_interval50_lower": 0.01,
                    "excess_interval50_upper": 0.05,
                    "excess_interval80_lower": -0.01,
                    "excess_interval80_upper": 0.07,
                    "excess_expected_return": 0.031,
                    "excess_volatility": 0.03,
                    "excess_var95": 0.02,
                    "excess_cvar95": 0.025,
                    "excess_drawdown_q50": 0.01,
                    "excess_drawdown_q80": 0.02,
                    "excess_drawdown_q95": 0.03,
                    "interval50_nominal_coverage": 0.50,
                    "interval80_nominal_coverage": 0.80,
                    "effective_samples": 16,
                    "contribution_draw_count": 16,
                    "baseline_component_contribution_json": _canonical(
                        _baseline_contributions(scenario_id)
                    ),
                    "channel_contribution_json": _canonical(
                        [
                            entry
                            for entry in _baseline_contributions(scenario_id)
                            if entry["component_type"] == "channel"
                        ]
                    ),
                    "scenario_contribution_json": _canonical(
                        _scenario_contributions(scenario_id)
                    ),
                    "contribution_aggregation_method": ("geometric_shared_prefix_v1"),
                    "contribution_conservation_max_abs_error": 0.0,
                    "contribution_conservation_passed": True,
                    "transferability_status": "formal",
                    "mapping_status": mapping_status,
                    "mapping_status_reason_codes": _canonical(
                        [
                            "stable_oos_increment"
                            if horizon == 3
                            else "baseline_gate_failed"
                            if horizon == 6
                            else "stale_current_mapping"
                        ]
                    ),
                    "evidence_level": "high" if horizon == 3 else "low",
                    "freshness_status": freshness,
                    "freshness_reason_codes": _canonical(
                        [] if freshness == "fresh" else ["stale_current_features"]
                    ),
                    "baseline_gate_passed": baseline_passed,
                    "oos_increment_score": 0.25 if baseline_passed else -0.10,
                    "transferability_score": 0.90,
                    "transferability_evidence_date": date(2024, 6, 29),
                    "transferability_validation_end": date(2024, 5, 31),
                    "current_mapping_run_id": context.run_id,
                    "current_mapping_model_version": "m4-current-mapping-v1",
                    "current_mapping_snapshot_config_hash": HASH_A,
                    "current_mapping_distribution_config_hash": HASH_B,
                    "current_mapping_transferability_config_hash": HASH_C,
                    "scenario_version": f"{scenario_id}-v1",
                    "catalog_version": "seven-cycle-scenarios-v1",
                    "scenario_config_hash": HASH_D,
                    "asset_forecast_model_version": "asset-forecast-v1",
                    "asset_forecast_config_hash": HASH_A,
                    "channel_forecast_model_version": "channel-champion-v1",
                    "channel_forecast_config_hash": HASH_B,
                    "channel_registry_hash": HASH_C,
                    "cycle_forecast_model_version": "cycle-champion-v1",
                    "cycle_forecast_config_hash": HASH_D,
                    "cycle_registry_hash": HASH_A,
                    "stage2_posterior_date": date(2024, 6, 28),
                    "stage2_estimation_method": "hierarchical_bayesian",
                    "forecast_origin": AS_OF,
                    "source_data_vintage": AS_OF,
                    "feature_visible_date": date(2024, 6, 28),
                    "feature_generated_date": date(2024, 6, 28),
                    "feature_vintage_date": date(2024, 6, 28),
                    "model_provenance": "governed-small-fixture",
                    "data_provenance": "point-in-time-small-fixture",
                    "run_id": context.run_id,
                    "as_of": context.as_of,
                    "data_vintage": context.data_vintage,
                    "model_version": context.model_version,
                    "config_hash": context.config_hash,
                    "created_at": context.created_at,
                }
            )
    for record in records:
        record["contribution_component_contract_hash"] = _component_contract_hash(
            record
        )
    return pd.DataFrame(records, columns=api.ASSET_MAPPING_FUTURE_COLUMNS)


def test_task_28_product_schemas_are_exact_and_stable() -> None:
    cycle = _cycle_api()
    future = _future_api()

    assert cycle.CYCLE_FORECAST_SCHEMA.names == list(cycle.CYCLE_FORECAST_COLUMNS)
    assert future.ASSET_MAPPING_FUTURE_SCHEMA.names == list(
        future.ASSET_MAPPING_FUTURE_COLUMNS
    )
    assert cycle.CYCLE_FORECAST_COLUMNS[:3] == (
        "as_of",
        "cycle_id",
        "horizon_months",
    )
    assert future.ASSET_MAPPING_FUTURE_COLUMNS[:4] == (
        "scenario_id",
        "future_date",
        "asset_id",
        "horizon_months",
    )
    assert cycle.CYCLE_FORECAST_SCHEMA.field("created_at").type == pa.timestamp(
        "us", tz="UTC"
    )
    assert future.ASSET_MAPPING_FUTURE_SCHEMA.field("created_at").type == (
        pa.timestamp("us", tz="UTC")
    )
    assert "return_basis" not in future.ASSET_MAPPING_FUTURE_COLUMNS
    assert "contribution_component_contract_hash" in (
        future.ASSET_MAPPING_FUTURE_COLUMNS
    )


def test_products_are_builder_only() -> None:
    cycle = _cycle_api()
    future = _future_api()

    with pytest.raises(TypeError, match="build_cycle_forecast"):
        cycle.CycleForecastProduct(forecast=_cycle_frame())
    with pytest.raises(TypeError, match="build_asset_mapping_future"):
        future.AssetMappingFutureProduct(mapping=_future_frame())


def test_cycle_contract_accepts_valid_rows_and_rejects_numeric_forgeries() -> None:
    api = _cycle_api()
    frame = _cycle_frame()
    api.validate_cycle_forecast(frame, context=_context())

    bad_probability = frame.copy(deep=True)
    bad_probability.loc[0, "recovery_probability"] = 0.50
    with pytest.raises(ValueError, match="probabilit"):
        api.validate_cycle_forecast(bad_probability, context=_context())

    bad_quantile = frame.copy(deep=True)
    bad_quantile.loc[0, "angle_q25"] = 90.0
    with pytest.raises(ValueError, match="quantile|angle"):
        api.validate_cycle_forecast(bad_quantile, context=_context())

    bad_turning = frame.copy(deep=True)
    bad_turning.loc[0, "turning_start_month"] = 3
    with pytest.raises(ValueError, match="turning"):
        api.validate_cycle_forecast(bad_turning, context=_context())

    relabeled = frame.copy(deep=True)
    relabeled.loc[0, "forecast_value_source_role"] = "challenger"
    with pytest.raises(ValueError, match="Champion|champion|source"):
        api.validate_cycle_forecast(relabeled, context=_context())


def test_unavailable_cycle_rows_cannot_fabricate_forecast_numbers() -> None:
    api = _cycle_api()
    frame = _cycle_frame()
    frame.loc[0, "status"] = "unavailable"
    frame.loc[0, "unavailable_reason"] = "upstream_state_unavailable"
    for column in (
        "expansion_probability",
        "downturn_probability",
        "contraction_probability",
        "recovery_probability",
        "angle_anchor_degrees",
        "angle_q10",
        "angle_q25",
        "angle_q50",
        "angle_q75",
        "angle_q90",
        "turning_probability",
        "turning_start_month",
        "turning_median_month",
        "turning_end_month",
        "turning_start_date",
        "turning_median_date",
        "turning_end_date",
        "forecast_uncertainty",
    ):
        frame.loc[0, column] = None
    frame.loc[0, "turning_status"] = "unavailable"
    frame.loc[0, "draw_count"] = 0
    frame.loc[0, "probability_support_count"] = 0
    api.validate_cycle_forecast(frame, context=_context())

    forged = frame.copy(deep=True)
    forged.loc[0, "angle_q50"] = 45.0
    with pytest.raises(ValueError, match="unavailable"):
        api.validate_cycle_forecast(forged, context=_context())


def test_future_contract_pivots_bases_and_enforces_six_scenario_isolation() -> None:
    api = _future_api()
    frame = _future_frame()
    api.validate_asset_mapping_future(frame, context=_context())

    assert set(frame["scenario_id"]) == set(STANDARD_SCENARIO_IDS)
    assert len(frame) == len(STANDARD_SCENARIO_IDS) * 3
    assert not frame.duplicated(["scenario_id", "future_date", "asset_id"]).any()
    assert frame["absolute_median"].notna().all()
    assert frame["excess_median"].notna().all()

    mixed = frame.loc[~frame["scenario_id"].eq("inflation")].copy(deep=True)
    with pytest.raises(ValueError, match="scenario"):
        api.validate_asset_mapping_future(mixed, context=_context())

    bad_interval = frame.copy(deep=True)
    bad_interval.loc[0, "absolute_interval50_lower"] = 0.10
    with pytest.raises(ValueError, match="interval"):
        api.validate_asset_mapping_future(bad_interval, context=_context())


def test_future_mapping_status_must_downgrade_on_baseline_or_freshness_failure() -> (
    None
):
    api = _future_api()
    frame = _future_frame()

    baseline_failure = frame.copy(deep=True)
    selector = baseline_failure["horizon_months"].eq(6)
    baseline_failure.loc[selector, "mapping_status"] = "formal"
    with pytest.raises(ValueError, match="baseline|retrospective"):
        api.validate_asset_mapping_future(baseline_failure, context=_context())

    stale_failure = frame.copy(deep=True)
    selector = stale_failure["horizon_months"].eq(12)
    stale_failure.loc[selector, "mapping_status"] = "formal"
    with pytest.raises(ValueError, match="stale|unavailable"):
        api.validate_asset_mapping_future(stale_failure, context=_context())


def test_contribution_payloads_are_canonical_and_keep_scenario_shocks_separate() -> (
    None
):
    api = _future_api()
    frame = _future_frame()
    baseline = frame.loc[frame["scenario_id"].eq("baseline")].iloc[0]
    assert json.loads(baseline["scenario_contribution_json"]) == []

    for row in frame.itertuples(index=False):
        for column, kind in (
            ("baseline_component_contribution_json", "baseline_component"),
            ("channel_contribution_json", "baseline_component"),
            ("scenario_contribution_json", "scenario_shock"),
        ):
            raw = getattr(row, column)
            parsed = json.loads(raw)
            assert raw == _canonical(parsed)
            assert all(entry["contribution_kind"] == kind for entry in parsed)
        baseline_entries = json.loads(row.baseline_component_contribution_json)
        channel_entries = json.loads(row.channel_contribution_json)
        scenario_entries = json.loads(row.scenario_contribution_json)
        assert channel_entries == [
            entry for entry in baseline_entries if entry["component_type"] == "channel"
        ]
        assert sum(
            entry["expected_contribution"]
            for entry in baseline_entries + scenario_entries
        ) == pytest.approx(row.absolute_expected_return)

    missing_nonchannel = frame.copy(deep=True)
    selector = missing_nonchannel["scenario_id"].eq("baseline")
    payload = json.loads(
        missing_nonchannel.loc[
            selector,
            "baseline_component_contribution_json",
        ].iloc[0]
    )
    payload = [entry for entry in payload if entry["component_type"] != "residual"]
    missing_nonchannel.loc[
        selector,
        "baseline_component_contribution_json",
    ] = _canonical(payload)
    with pytest.raises(ValueError, match="expected|conservation|component"):
        api.validate_asset_mapping_future(missing_nonchannel, context=_context())

    duplicate_scenario = frame.copy(deep=True)
    selector = duplicate_scenario["scenario_id"].eq("growth")
    payload = json.loads(
        duplicate_scenario.loc[selector, "scenario_contribution_json"].iloc[0]
    )
    payload.append(payload[0].copy())
    duplicate_scenario.loc[selector, "scenario_contribution_json"] = _canonical(payload)
    with pytest.raises(ValueError, match="duplicate|unique|scenario"):
        api.validate_asset_mapping_future(duplicate_scenario, context=_context())

    forged_bool = frame.copy(deep=True)
    forged_bool.loc[0, "contribution_conservation_passed"] = False
    with pytest.raises(ValueError, match="conservation"):
        api.validate_asset_mapping_future(forged_bool, context=_context())

    renamed_component = frame.copy(deep=True)
    selector = renamed_component["scenario_id"].eq("baseline")
    payload = json.loads(
        renamed_component.loc[
            selector,
            "baseline_component_contribution_json",
        ].iloc[0]
    )
    residual = next(entry for entry in payload if entry["component_type"] == "residual")
    residual["component_id"] = "renamed_asset_residual"
    renamed_component.loc[
        selector,
        "baseline_component_contribution_json",
    ] = _canonical(payload)
    with pytest.raises(ValueError, match="fingerprint|contract hash"):
        api.validate_asset_mapping_future(renamed_component, context=_context())


def test_future_mapping_surface_forbids_retrospective_weights_and_shares() -> None:
    api = _future_api()
    forbidden_fragments = (
        "weight",
        "contribution_share",
        "suggested_allocation",
        "recommended_allocation",
        "historical_attribution",
    )

    assert not {
        column
        for column in api.ASSET_MAPPING_FUTURE_COLUMNS
        if any(fragment in column for fragment in forbidden_fragments)
    }
