from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.attribution import (
    ATTRIBUTION_DRAW_COLUMNS,
    ATTRIBUTION_INTERVAL_COLUMNS,
    ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
    AttributionIntervalResult,
    ContributionConfig,
    CycleToChannelConfig,
    HierarchicalTVPConfig,
    IdentifiabilityConfig,
    UncertaintyConfig,
    compose_attribution_paths,
    estimate_attribution_intervals,
    estimate_channel_to_asset,
    estimate_cycle_to_channel,
)
from seven_cycle_platform.products.asset_attribution import (
    ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
    ASSET_ATTRIBUTION_FILENAME,
    build_asset_attribution,
    write_asset_attribution,
)
from seven_cycle_platform.contracts.arrow import ASSET_ATTRIBUTION_SCHEMA
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import (
    MANIFEST_FILENAME,
    RunManifest,
    verify_manifest,
)


pytestmark = pytest.mark.integration

REPORT_ID = "baijiu_2019"
REPORT_MARKDOWN_FILENAME = f"{REPORT_ID}.md"
REPORT_JSON_FILENAME = f"{REPORT_ID}.json"
PERIOD_START = pd.Timestamp("2019-01-31")
PERIOD_END = pd.Timestamp("2019-12-31")
HORIZON_MONTHS = 12
DRAW_COUNT = 500

REALTIME = "realtime"
LATEST_HISTORICAL = "latest_historical"
INTERPRETATIONS = (REALTIME, LATEST_HISTORICAL)

BENCHMARK_ASSET_ID = "cn_equity_hs300"
BENCHMARK_SYMBOL = "000300.SH"


@dataclass(frozen=True)
class AssetFixture:
    asset_id: str
    symbol: str
    proxy_status: str
    proxy_for: str | None
    history_status: str
    shrinkage_status: str
    confidence: str


PRIMARY = AssetFixture(
    asset_id="cn_equity_baijiu",
    symbol="399997.SZ",
    proxy_status="primary",
    proxy_for=None,
    history_status="short_history",
    shrinkage_status="strong",
    confidence="low",
)
PROXY = AssetFixture(
    asset_id="cn_equity_baijiu_citic_food_beverage",
    symbol="CI005019.CI",
    proxy_status="proxy",
    proxy_for=PRIMARY.asset_id,
    history_status="longer_history",
    shrinkage_status="standard",
    confidence="medium_high",
)
ASSETS = (PRIMARY, PROXY)
ASSET_BY_ID = {asset.asset_id: asset for asset in ASSETS}

CYCLE_IDS = tuple(f"C{cycle}" for cycle in range(1, 8))
CHANNEL_IDS = (
    "growth_demand",
    "real_rate_discount",
    "liquidity_credit",
    "earnings_margin",
    "risk_premium_crowding",
)
CONTROL_IDS = ("foreign_flow_funding", "valuation_repricing")
EVENT_IDS = ("industry_event",)
RESIDUAL_ID = "asset_residual"

BASE_NONBENCHMARK_COMPONENTS = (
    ("cycle", "C1", 0.012),
    ("cycle", "C2", -0.007),
    ("cycle", "C3", 0.019),
    ("cycle", "C4", 0.008),
    ("cycle", "C5", -0.004),
    ("cycle", "C6", 0.011),
    ("cycle", "C7", 0.006),
    ("channel_residual_path", "growth_demand", 0.014),
    ("channel_residual_path", "real_rate_discount", -0.009),
    ("channel_residual_path", "liquidity_credit", 0.013),
    ("channel_residual_path", "earnings_margin", 0.021),
    ("channel_residual_path", "risk_premium_crowding", -0.006),
    ("control", "foreign_flow_funding", 0.005),
    ("control", "valuation_repricing", 0.010),
    ("event", "industry_event", 0.017),
)

MODELED_RETURNS = {
    REALTIME: {
        "benchmark": 0.036,
        PRIMARY.asset_id: 0.137,
        PROXY.asset_id: 0.224,
    },
    LATEST_HISTORICAL: {
        "benchmark": 0.042,
        PRIMARY.asset_id: 0.161,
        PROXY.asset_id: 0.247,
    },
}
COMPONENT_MULTIPLIERS = {
    REALTIME: {PRIMARY.asset_id: 0.75, PROXY.asset_id: 1.45},
    LATEST_HISTORICAL: {PRIMARY.asset_id: 0.90, PROXY.asset_id: 1.60},
}

INTERPRETATION_CONTEXT = {
    REALTIME: {
        "as_of": date(2020, 1, 31),
        "data_vintage": date(2020, 1, 31),
        "created_at": datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
    },
    LATEST_HISTORICAL: {
        "as_of": date(2026, 6, 30),
        "data_vintage": date(2026, 6, 30),
        "created_at": datetime(2026, 7, 13, 8, 5, tzinfo=timezone.utc),
    },
}


@dataclass(frozen=True)
class PublishedBaijiuCase:
    product_root: Path
    requested_run_id: str
    manifests: dict[str, RunManifest]

    def run_dir(self, interpretation: str) -> Path:
        return self.product_root / "runs" / self.manifests[interpretation].run_id

    def report_dir(self) -> Path:
        return self.product_root / "reports" / self.requested_run_id


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unavailable_reason_key(
    asset_id: str,
    return_basis: str,
    component_type: str = "control",
    component_id: str = "foreign_flow_funding",
) -> str:
    return "|".join((asset_id, return_basis, component_type, component_id))


def _unavailable_reason(
    interpretation: str,
    asset_id: str,
    return_basis: str,
) -> str:
    return (
        f"{interpretation} {asset_id} {return_basis}: foreign-flow/funding "
        "interval unavailable because governed 2019 support is below the "
        "Task17 minimum."
    )


def _asset_manifest_metadata() -> dict[str, dict[str, object]]:
    return {
        asset.asset_id: {
            "symbol": asset.symbol,
            "proxy_status": asset.proxy_status,
            "proxy_for": asset.proxy_for,
            "history_status": asset.history_status,
            "shrinkage_status": asset.shrinkage_status,
            "confidence": asset.confidence,
        }
        for asset in ASSETS
    }


def _case_quality_summary(
    interpretation: str,
    interpretation_runs: dict[str, str],
) -> dict[str, object]:
    unavailable_reasons = {
        _unavailable_reason_key(asset.asset_id, return_basis): _unavailable_reason(
            interpretation,
            asset.asset_id,
            return_basis,
        )
        for asset in ASSETS
        for return_basis in ("absolute", "excess")
    }
    return {
        "failed": 0,
        "passed": 8,
        REPORT_ID: {
            "interpretation": interpretation,
            "vintage_kind": interpretation,
            "interpretation_runs": interpretation_runs,
            "period": {
                "period_start": PERIOD_START.date().isoformat(),
                "period_end": PERIOD_END.date().isoformat(),
                "horizon_months": HORIZON_MONTHS,
            },
            "benchmark": {
                "asset_id": BENCHMARK_ASSET_ID,
                "symbol": BENCHMARK_SYMBOL,
            },
            "assets": _asset_manifest_metadata(),
            "unavailable_reasons": unavailable_reasons,
        },
    }


def _make_context(
    interpretation: str,
    *,
    fixture_variant: str,
    quality_summary: dict[str, object],
) -> RunContext:
    context_values = INTERPRETATION_CONTEXT[interpretation]
    input_name = f"fixtures/{REPORT_ID}/{fixture_variant}/{interpretation}.json"
    return RunContext.create(
        as_of=context_values["as_of"],
        data_vintage=context_values["data_vintage"],
        model_version="seven-cycle-attribution-v1",
        config={
            "case": REPORT_ID,
            "fixture_variant": fixture_variant,
            "horizon_months": HORIZON_MONTHS,
            "interpretation": interpretation,
            "period_end": PERIOD_END.date().isoformat(),
            "period_start": PERIOD_START.date().isoformat(),
        },
        input_checksums={
            input_name: _digest(
                f"{fixture_variant}|{interpretation}|modeled-input".encode()
            )
        },
        quality_summary=quality_summary,
        created_at=context_values["created_at"],
    )


def _interval_bounds(
    point_contribution: float,
    *,
    asset: AssetFixture,
    component_position: int,
) -> tuple[float, float, float, float]:
    if asset.proxy_status == "primary":
        half_width_50 = 0.0060 + component_position * 0.00010
    else:
        half_width_50 = 0.0030 + component_position * 0.00005
    half_width_80 = half_width_50 * 2.0
    return (
        round(point_contribution - half_width_50, 12),
        round(point_contribution + half_width_50, 12),
        round(point_contribution - half_width_80, 12),
        round(point_contribution + half_width_80, 12),
    )


def _significance(lower_80: float, upper_80: float) -> str:
    if lower_80 > 0.0:
        return "positive"
    if upper_80 < 0.0:
        return "negative"
    return "not_significant"


def _component_points(
    interpretation: str,
    asset: AssetFixture,
) -> tuple[float, list[tuple[str, str, float]]]:
    benchmark_return = float(MODELED_RETURNS[interpretation]["benchmark"])
    absolute_return = float(MODELED_RETURNS[interpretation][asset.asset_id])
    excess_return = round(absolute_return - benchmark_return, 12)
    multiplier = COMPONENT_MULTIPLIERS[interpretation][asset.asset_id]
    modeled = [
        (component_type, component_id, round(base_point * multiplier, 12))
        for component_type, component_id, base_point in BASE_NONBENCHMARK_COMPONENTS
    ]
    residual = round(
        excess_return - sum(point for _, _, point in modeled),
        12,
    )
    return excess_return, [*modeled, ("asset_residual", RESIDUAL_ID, residual)]


def _interval_result(
    interpretation: str,
    *,
    include_primary: bool,
) -> AttributionIntervalResult:
    interval_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    included_assets = tuple(
        asset for asset in ASSETS if include_primary or asset is not PRIMARY
    )

    for asset in included_assets:
        benchmark_return = float(MODELED_RETURNS[interpretation]["benchmark"])
        absolute_return = float(MODELED_RETURNS[interpretation][asset.asset_id])
        excess_return, nonbenchmark_points = _component_points(
            interpretation,
            asset,
        )
        for return_basis, observed_return, benchmark_point in (
            ("absolute", absolute_return, benchmark_return),
            ("excess", excess_return, 0.0),
        ):
            component_points = [
                ("benchmark", BENCHMARK_ASSET_ID, benchmark_point),
                *nonbenchmark_points,
            ]
            for position, (component_type, component_id, point) in enumerate(
                component_points
            ):
                unavailable = (
                    component_type == "control"
                    and component_id == "foreign_flow_funding"
                )
                if unavailable:
                    lower_50 = upper_50 = lower_80 = upper_80 = np.nan
                    interval_status = "unavailable"
                    significance = "unavailable"
                    status = "insufficient_history"
                    evidence_level = "low"
                    effective_samples = 5
                else:
                    lower_50, upper_50, lower_80, upper_80 = _interval_bounds(
                        point,
                        asset=asset,
                        component_position=position,
                    )
                    interval_status = (
                        "degraded" if asset.proxy_status == "primary" else "available"
                    )
                    significance = _significance(lower_80, upper_80)
                    status = (
                        "parent_informed"
                        if asset.proxy_status == "primary"
                        else "estimated"
                    )
                    if asset.proxy_status == "primary":
                        evidence_level = "low"
                        effective_samples = 8
                    else:
                        evidence_level = (
                            "high"
                            if component_type in {"benchmark", "control", "event"}
                            else "medium"
                        )
                        effective_samples = 72 if evidence_level == "high" else 48
                interval_rows.append(
                    {
                        "asset_id": asset.asset_id,
                        "period_start": PERIOD_START,
                        "period_end": PERIOD_END,
                        "horizon_months": HORIZON_MONTHS,
                        "return_basis": return_basis,
                        "component_type": component_type,
                        "component_id": component_id,
                        "point_contribution": point,
                        "lower_50": lower_50,
                        "upper_50": upper_50,
                        "lower_80": lower_80,
                        "upper_80": upper_80,
                        "interval_status": interval_status,
                        "significance": significance,
                        "effective_samples": effective_samples,
                        "draw_count": DRAW_COUNT,
                        "status": status,
                        "evidence_level": evidence_level,
                        "observed_return": observed_return,
                        "reconstructed_return": observed_return,
                        "is_explained": component_type != "asset_residual",
                        "is_residual": component_type == "asset_residual",
                    }
                )
            point_sum = sum(point for _, _, point in component_points)
            diagnostic_rows.append(
                {
                    "asset_id": asset.asset_id,
                    "period_start": PERIOD_START,
                    "period_end": PERIOD_END,
                    "horizon_months": HORIZON_MONTHS,
                    "return_basis": return_basis,
                    "point_component_sum": point_sum,
                    "observed_return": observed_return,
                    "point_conservation_error": abs(point_sum - observed_return),
                    "max_draw_conservation_error": np.nan,
                    "available_component_count": len(component_points) - 1,
                    "unavailable_component_count": 1,
                    "status": "partial",
                }
            )

    intervals = pd.DataFrame.from_records(
        interval_rows,
        columns=ATTRIBUTION_INTERVAL_COLUMNS,
    )
    diagnostics = pd.DataFrame.from_records(
        diagnostic_rows,
        columns=ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
    )
    draws = pd.DataFrame(columns=ATTRIBUTION_DRAW_COLUMNS)
    return AttributionIntervalResult(
        intervals=intervals,
        diagnostics=diagnostics,
        draws=draws,
        draw_count=DRAW_COUNT,
        seed=18,
    )


def _publish_case(
    base_dir: Path,
    *,
    missing_primary_interpretation: str | None = None,
) -> PublishedBaijiuCase:
    fixture_variant = (
        "complete"
        if missing_primary_interpretation is None
        else f"missing-primary-{missing_primary_interpretation}"
    )
    identity_contexts = {
        interpretation: _make_context(
            interpretation,
            fixture_variant=fixture_variant,
            quality_summary={"identity_probe": interpretation},
        )
        for interpretation in INTERPRETATIONS
    }
    interpretation_runs = {
        interpretation: context.run_id
        for interpretation, context in identity_contexts.items()
    }
    contexts = {
        interpretation: _make_context(
            interpretation,
            fixture_variant=fixture_variant,
            quality_summary=_case_quality_summary(
                interpretation,
                interpretation_runs,
            ),
        )
        for interpretation in INTERPRETATIONS
    }
    assert {
        interpretation: context.run_id for interpretation, context in contexts.items()
    } == interpretation_runs

    product_root = base_dir / "products" / "seven_cycle"
    manifests: dict[str, RunManifest] = {}
    for interpretation in (LATEST_HISTORICAL, REALTIME):
        context = contexts[interpretation]
        interval_result = _interval_result(
            interpretation,
            include_primary=interpretation != missing_primary_interpretation,
        )
        product = build_asset_attribution(interval_result, context=context)

        def write_staging(
            staging_dir: Path,
            *,
            product=product,
            context=context,
        ) -> None:
            write_asset_attribution(staging_dir, product, context=context)

        manifests[interpretation] = publish_run(
            product_root,
            context,
            write_staging=write_staging,
        )

    case = PublishedBaijiuCase(
        product_root=product_root,
        requested_run_id=manifests[REALTIME].run_id,
        manifests=manifests,
    )
    for interpretation, manifest in manifests.items():
        verify_manifest(case.run_dir(interpretation), expected=manifest)
    return case


def _rename_benchmark_components(
    components: pd.DataFrame,
    covariance: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    renamed_components = components.copy(deep=True)
    component_mask = renamed_components["component_type"].eq(
        "benchmark"
    ) & renamed_components["component_id"].eq("benchmark_return")
    renamed_components.loc[component_mask, "component_id"] = BENCHMARK_ASSET_ID

    renamed_covariance = covariance.copy(deep=True)
    for side in ("i", "j"):
        type_column = f"component_{side}_type"
        id_column = f"component_{side}_id"
        covariance_mask = renamed_covariance[type_column].eq(
            "benchmark"
        ) & renamed_covariance[id_column].eq("benchmark_return")
        renamed_covariance.loc[covariance_mask, id_column] = BENCHMARK_ASSET_ID
    return renamed_components, renamed_covariance


def _combine_interval_results(
    *results: AttributionIntervalResult,
) -> AttributionIntervalResult:
    assert results
    assert len({result.draw_count for result in results}) == 1
    assert len({result.seed for result in results}) == 1
    return AttributionIntervalResult(
        intervals=pd.concat(
            [result.intervals for result in results],
            ignore_index=True,
        ),
        diagnostics=pd.concat(
            [result.diagnostics for result in results],
            ignore_index=True,
        ),
        draws=pd.concat(
            [result.draws for result in results],
            ignore_index=True,
        ),
        draw_count=results[0].draw_count,
        seed=results[0].seed,
    )


def _full_chain_interval_result(
    interpretation: str,
) -> AttributionIntervalResult:
    generator = np.random.default_rng(20260718)
    dates = pd.date_range("2014-01-31", "2019-12-31", freq="ME")
    period_dates = pd.date_range(PERIOD_START, PERIOD_END, freq="ME")
    count = len(dates)
    revision = 0.0 if interpretation == REALTIME else 0.004

    cycle_wide = generator.normal(scale=0.40, size=(count, len(CYCLE_IDS)))
    cycles = (
        pd.DataFrame(cycle_wide, index=dates, columns=CYCLE_IDS)
        .rename_axis("date")
        .reset_index()
        .melt(
            id_vars="date",
            var_name="cycle_id",
            value_name="innovation",
        )
    )
    channel_coefficients = np.asarray(
        [
            [0.25, -0.10, 0.08, 0.03, 0.02, -0.04, 0.01],
            [-0.05, 0.18, -0.12, 0.04, 0.02, 0.01, -0.03],
            [0.10, 0.06, 0.15, -0.08, 0.03, 0.02, 0.05],
            [0.16, -0.03, 0.04, 0.11, -0.05, 0.06, 0.02],
            [-0.08, 0.05, -0.04, 0.06, 0.12, -0.02, 0.09],
        ],
        dtype="float64",
    )
    channel_matrix = cycle_wide @ channel_coefficients.T + generator.normal(
        scale=0.03, size=(count, len(CHANNEL_IDS))
    )
    channel_matrix[-HORIZON_MONTHS:] += revision
    channels = pd.DataFrame(
        {
            "date": np.repeat(dates, len(CHANNEL_IDS)),
            "channel_id": np.tile(CHANNEL_IDS, count),
            "innovation": channel_matrix.reshape(-1),
        }
    )
    stage1 = estimate_cycle_to_channel(
        cycles,
        channels,
        config=CycleToChannelConfig(
            window="expanding",
            rolling_window=None,
            min_training_count=24,
            alpha_grid=(0.01, 0.1),
            validation_window=6,
            condition_number_threshold=10_000.0,
            recursive=False,
            forgetting_factor=1.0,
        ),
    )

    benchmark = (
        0.015 + 0.20 * channel_matrix[:, 0] + generator.normal(scale=0.02, size=count)
    )
    valuation = generator.normal(scale=0.30, size=count)
    foreign_flow = generator.normal(scale=0.30, size=count)
    industry_event = np.zeros(count, dtype="float64")
    industry_event[[10, 28, 50, 67]] = 1.0
    asset_ids = (PRIMARY.asset_id, PROXY.asset_id)
    starts = {PRIMARY.asset_id: count - 36, PROXY.asset_id: 0}
    asset_channel_coefficients = {
        PRIMARY.asset_id: np.asarray([0.20, -0.12, 0.18, 0.28, -0.10]),
        PROXY.asset_id: np.asarray([0.18, -0.08, 0.15, 0.24, -0.06]),
    }
    absolute_returns: dict[str, np.ndarray] = {}
    controls: list[tuple[object, ...]] = []
    events: list[tuple[object, ...]] = []
    for asset_id in asset_ids:
        absolute_returns[asset_id] = (
            0.003
            + 0.45 * benchmark
            + channel_matrix @ asset_channel_coefficients[asset_id]
            + 0.08 * valuation
            + 0.05 * foreign_flow
            + 0.04 * industry_event
            + generator.normal(scale=0.012, size=count)
            + revision * 0.20
        )
        for position, current_date in enumerate(dates):
            controls.extend(
                [
                    (
                        current_date,
                        asset_id,
                        "valuation_repricing",
                        valuation[position],
                    ),
                    (
                        current_date,
                        asset_id,
                        "foreign_flow_funding",
                        foreign_flow[position],
                    ),
                ]
            )
            events.append(
                (
                    current_date,
                    asset_id,
                    "industry_event",
                    industry_event[position],
                )
            )

    hierarchy = pd.DataFrame(
        [
            (PRIMARY.asset_id, "equity", "food_beverage", False, 0.0),
            (PROXY.asset_id, "equity", "food_beverage", True, 0.25),
        ],
        columns=[
            "asset_id",
            "asset_class_id",
            "industry_id",
            "is_proxy",
            "confidence_discount",
        ],
    )
    control_frame = pd.DataFrame(
        controls,
        columns=["date", "asset_id", "control_id", "value"],
    )
    event_frame = pd.DataFrame(
        events,
        columns=["date", "asset_id", "event_id", "value"],
    )
    stage2_config = HierarchicalTVPConfig(
        window="expanding",
        rolling_window=None,
        min_asset_training_count=12,
        min_parent_training_count=18,
        root_ridge=1.0,
        industry_prior_strength=8.0,
        asset_prior_strength=12.0,
        condition_number_threshold=100_000.0,
        forgetting_factor=1.0,
    )
    contribution_config = ContributionConfig(
        identifiability=IdentifiabilityConfig(
            min_history_count=12,
            correlation_threshold=0.999,
            condition_number_threshold=1_000_000.0,
        ),
        conservation_tolerance=1e-10,
        direct_min_oos_gain=0.05,
        direct_min_stability_score=0.80,
        direct_min_validation_count=12,
    )
    uncertainty_config = UncertaintyConfig(
        draw_count=32,
        seed=18,
        block_length=3,
        min_effective_samples=8,
        enable_residual_bootstrap=False,
    )
    cycle_uncertainty = pd.DataFrame(
        {
            "date": np.repeat(period_dates, len(CYCLE_IDS)),
            "cycle_id": np.tile(CYCLE_IDS, len(period_dates)),
            "uncertainty": 0.02,
        }
    )
    channel_uncertainty = pd.DataFrame(
        {
            "date": np.repeat(period_dates, len(CHANNEL_IDS)),
            "channel_id": np.tile(CHANNEL_IDS, len(period_dates)),
            "uncertainty": 0.01,
        }
    )

    interval_results: list[AttributionIntervalResult] = []
    for return_basis in ("absolute", "excess"):
        return_rows: list[dict[str, object]] = []
        for asset_id in asset_ids:
            target = absolute_returns[asset_id]
            if return_basis == "excess":
                target = (1.0 + target) / (1.0 + benchmark) - 1.0
            for position in range(starts[asset_id], count):
                return_rows.append(
                    {
                        "date": dates[position],
                        "asset_id": asset_id,
                        "return": target[position],
                        "benchmark_return": benchmark[position],
                    }
                )
        stage2 = estimate_channel_to_asset(
            pd.DataFrame(return_rows),
            channels,
            hierarchy,
            controls=control_frame,
            event_shocks=event_frame,
            config=stage2_config,
        )
        stage2_components, stage2_covariance = _rename_benchmark_components(
            stage2.components,
            stage2.covariance,
        )
        contribution = compose_attribution_paths(
            stage1.paths,
            stage2_components,
            config=contribution_config,
        )
        period_contribution = SimpleNamespace(
            components=contribution.components.loc[
                contribution.components["date"].isin(period_dates)
            ],
            paths=contribution.paths.loc[contribution.paths["date"].isin(period_dates)],
        )
        interval_results.append(
            estimate_attribution_intervals(
                period_contribution,
                stage1_paths=stage1.paths,
                stage1_covariance=stage1.covariance,
                stage2_components=stage2_components,
                stage2_covariance=stage2_covariance,
                cycle_uncertainty=cycle_uncertainty,
                channel_uncertainty=channel_uncertainty,
                residual_history=None,
                period_start=PERIOD_START,
                period_end=PERIOD_END,
                horizon_months=HORIZON_MONTHS,
                return_basis=return_basis,
                config=uncertainty_config,
            )
        )
    return _combine_interval_results(*interval_results)


def _publish_full_chain_case(base_dir: Path) -> PublishedBaijiuCase:
    fixture_variant = "full-attribution-chain"
    identity_contexts = {
        interpretation: _make_context(
            interpretation,
            fixture_variant=fixture_variant,
            quality_summary={"identity_probe": interpretation},
        )
        for interpretation in INTERPRETATIONS
    }
    interpretation_runs = {
        interpretation: context.run_id
        for interpretation, context in identity_contexts.items()
    }
    contexts = {
        interpretation: _make_context(
            interpretation,
            fixture_variant=fixture_variant,
            quality_summary=_case_quality_summary(
                interpretation,
                interpretation_runs,
            ),
        )
        for interpretation in INTERPRETATIONS
    }
    product_root = base_dir / "products" / "seven_cycle"
    manifests: dict[str, RunManifest] = {}
    for interpretation in INTERPRETATIONS:
        context = contexts[interpretation]
        interval_result = _full_chain_interval_result(interpretation)
        product = build_asset_attribution(interval_result, context=context)

        def write_staging(
            staging_dir: Path,
            *,
            product=product,
            context=context,
        ) -> None:
            write_asset_attribution(staging_dir, product, context=context)

        manifests[interpretation] = publish_run(
            product_root,
            context,
            write_staging=write_staging,
        )
    return PublishedBaijiuCase(
        product_root=product_root,
        requested_run_id=manifests[LATEST_HISTORICAL].run_id,
        manifests=manifests,
    )


@pytest.fixture(scope="module")
def published_case(tmp_path_factory: pytest.TempPathFactory) -> PublishedBaijiuCase:
    return _publish_case(tmp_path_factory.mktemp("baijiu-2019-published"))


def _clone_case(
    published_case: PublishedBaijiuCase,
    destination: Path,
) -> PublishedBaijiuCase:
    product_root = destination / "products" / "seven_cycle"
    product_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(published_case.product_root, product_root)
    return PublishedBaijiuCase(
        product_root=product_root,
        requested_run_id=published_case.requested_run_id,
        manifests=dict(published_case.manifests),
    )


def _run_snapshot(run_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }


def _report_paths(case: PublishedBaijiuCase) -> tuple[Path, Path]:
    report_dir = case.report_dir()
    return (
        report_dir / REPORT_MARKDOWN_FILENAME,
        report_dir / REPORT_JSON_FILENAME,
    )


def _invoke_report_cli(
    case: PublishedBaijiuCase,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, pytest.CaptureResult[str]]:
    cli = importlib.import_module("seven_cycle_platform.cli")
    exit_code = cli.main(
        [
            "report-baijiu-2019",
            "--run-id",
            case.requested_run_id,
            "--product-root",
            str(case.product_root),
        ]
    )
    return exit_code, capsys.readouterr()


def _source_attribution(
    case: PublishedBaijiuCase,
    interpretation: str,
) -> pd.DataFrame:
    return pd.read_parquet(case.run_dir(interpretation) / ASSET_ATTRIBUTION_FILENAME)


def _source_conservation(
    case: PublishedBaijiuCase,
    interpretation: str,
) -> pd.DataFrame:
    return pd.read_parquet(
        case.run_dir(interpretation) / ASSET_ATTRIBUTION_CONSERVATION_FILENAME
    )


def _assert_json_number(actual: object, expected: object) -> None:
    if pd.isna(expected):
        assert actual is None
    else:
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool)
        assert float(actual) == float(expected)


def _assert_json_date(actual: object, expected: object) -> None:
    assert isinstance(actual, str)
    assert pd.Timestamp(actual).date() == pd.Timestamp(expected).date()


def _assert_json_timestamp(actual: object, expected: object) -> None:
    assert isinstance(actual, str)
    assert pd.Timestamp(actual) == pd.Timestamp(expected)


def _assert_report_json_matches_sources(
    case: PublishedBaijiuCase,
    report: dict[str, object],
) -> None:
    assert report["report_id"] == REPORT_ID
    assert report["requested_run_id"] == case.requested_run_id
    assert report["interpretation_runs"] == {
        interpretation: case.manifests[interpretation].run_id
        for interpretation in INTERPRETATIONS
    }
    assert report["period"] == {
        "period_start": PERIOD_START.date().isoformat(),
        "period_end": PERIOD_END.date().isoformat(),
        "horizon_months": HORIZON_MONTHS,
    }
    assert report["benchmark"] == {
        "asset_id": BENCHMARK_ASSET_ID,
        "symbol": BENCHMARK_SYMBOL,
    }

    report_attribution = report["attribution"]
    assert isinstance(report_attribution, list)
    attribution_index = {
        (
            row["interpretation"],
            row["asset_id"],
            row["return_basis"],
            row["component_type"],
            row["component_id"],
        ): row
        for row in report_attribution
    }
    assert len(attribution_index) == len(report_attribution)

    expected_attribution_keys: set[tuple[object, ...]] = set()
    for interpretation in INTERPRETATIONS:
        source = _source_attribution(case, interpretation)
        for source_row in source.to_dict(orient="records"):
            key = (
                interpretation,
                source_row["asset_id"],
                source_row["return_basis"],
                source_row["component_type"],
                source_row["component_id"],
            )
            expected_attribution_keys.add(key)
            report_row = attribution_index[key]
            asset = ASSET_BY_ID[str(source_row["asset_id"])]
            assert report_row["symbol"] == asset.symbol
            assert report_row["proxy_status"] == asset.proxy_status
            assert report_row["proxy_for"] == asset.proxy_for
            for field_name in (
                "point_contribution",
                "lower_50",
                "upper_50",
                "lower_80",
                "upper_80",
                "observed_return",
                "reconstructed_return",
            ):
                _assert_json_number(report_row[field_name], source_row[field_name])
            for field_name in ("effective_samples", "draw_count"):
                assert report_row[field_name] == int(source_row[field_name])
            for field_name in (
                "interval_status",
                "significance",
                "status",
                "evidence_level",
                "run_id",
                "model_version",
                "config_hash",
            ):
                assert report_row[field_name] == source_row[field_name]
            for field_name in ("is_explained", "is_residual"):
                assert report_row[field_name] is bool(source_row[field_name])
            _assert_json_date(report_row["period_start"], source_row["period_start"])
            _assert_json_date(report_row["period_end"], source_row["period_end"])
            _assert_json_date(report_row["as_of"], source_row["as_of"])
            _assert_json_date(report_row["data_vintage"], source_row["data_vintage"])
            _assert_json_timestamp(report_row["created_at"], source_row["created_at"])
            assert report_row["horizon_months"] == HORIZON_MONTHS

            if source_row["interval_status"] == "unavailable":
                expected_reason = _unavailable_reason(
                    interpretation,
                    str(source_row["asset_id"]),
                    str(source_row["return_basis"]),
                )
                assert report_row["unavailable_reason"] == expected_reason
            else:
                assert report_row["unavailable_reason"] is None

    assert set(attribution_index) == expected_attribution_keys
    assert {row["interpretation"] for row in report_attribution} == set(INTERPRETATIONS)
    assert {row["proxy_status"] for row in report_attribution} == {
        "primary",
        "proxy",
    }
    assert {row["return_basis"] for row in report_attribution} == {
        "absolute",
        "excess",
    }

    report_conservation = report["conservation"]
    assert isinstance(report_conservation, list)
    conservation_index = {
        (
            row["interpretation"],
            row["asset_id"],
            row["return_basis"],
        ): row
        for row in report_conservation
    }
    assert len(conservation_index) == len(report_conservation)
    expected_conservation_keys: set[tuple[object, ...]] = set()
    for interpretation in INTERPRETATIONS:
        source = _source_conservation(case, interpretation)
        for source_row in source.to_dict(orient="records"):
            key = (
                interpretation,
                source_row["asset_id"],
                source_row["return_basis"],
            )
            expected_conservation_keys.add(key)
            report_row = conservation_index[key]
            asset = ASSET_BY_ID[str(source_row["asset_id"])]
            assert report_row["symbol"] == asset.symbol
            assert report_row["proxy_status"] == asset.proxy_status
            assert report_row["proxy_for"] == asset.proxy_for
            for field_name in (
                "point_component_sum",
                "observed_return",
                "point_conservation_error",
                "max_draw_conservation_error",
            ):
                _assert_json_number(report_row[field_name], source_row[field_name])
            for field_name in (
                "available_component_count",
                "unavailable_component_count",
            ):
                assert report_row[field_name] == int(source_row[field_name])
            for field_name in (
                "status",
                "run_id",
                "model_version",
                "config_hash",
            ):
                assert report_row[field_name] == source_row[field_name]
            _assert_json_date(report_row["period_start"], source_row["period_start"])
            _assert_json_date(report_row["period_end"], source_row["period_end"])
            _assert_json_date(report_row["as_of"], source_row["as_of"])
            _assert_json_date(report_row["data_vintage"], source_row["data_vintage"])
            _assert_json_timestamp(report_row["created_at"], source_row["created_at"])
            assert report_row["horizon_months"] == HORIZON_MONTHS
    assert set(conservation_index) == expected_conservation_keys

    comparison = report["vintage_comparison"]
    assert isinstance(comparison, list)
    comparison_index = {
        (
            row["asset_id"],
            row["return_basis"],
            row["component_type"],
            row["component_id"],
        ): row
        for row in comparison
    }
    realtime_source = _source_attribution(case, REALTIME).set_index(
        ["asset_id", "return_basis", "component_type", "component_id"]
    )
    historical_source = _source_attribution(case, LATEST_HISTORICAL).set_index(
        ["asset_id", "return_basis", "component_type", "component_id"]
    )
    assert set(realtime_source.index) == set(historical_source.index)
    assert set(comparison_index) == set(realtime_source.index)
    for key in realtime_source.index:
        realtime_row = realtime_source.loc[key]
        historical_row = historical_source.loc[key]
        comparison_row = comparison_index[key]
        asset = ASSET_BY_ID[str(key[0])]
        assert comparison_row["symbol"] == asset.symbol
        assert comparison_row["proxy_status"] == asset.proxy_status
        assert comparison_row["proxy_for"] == asset.proxy_for
        expected_values = {
            "realtime_point_contribution": realtime_row["point_contribution"],
            "latest_historical_point_contribution": historical_row[
                "point_contribution"
            ],
            "point_contribution_change": historical_row["point_contribution"]
            - realtime_row["point_contribution"],
            "realtime_observed_return": realtime_row["observed_return"],
            "latest_historical_observed_return": historical_row["observed_return"],
            "observed_return_change": historical_row["observed_return"]
            - realtime_row["observed_return"],
        }
        for field_name, expected in expected_values.items():
            _assert_json_number(comparison_row[field_name], expected)

    realtime_returns = {
        (row["asset_id"], row["return_basis"]): row["observed_return"]
        for row in report_attribution
        if row["interpretation"] == REALTIME
    }
    historical_returns = {
        (row["asset_id"], row["return_basis"]): row["observed_return"]
        for row in report_attribution
        if row["interpretation"] == LATEST_HISTORICAL
    }
    assert realtime_returns.keys() == historical_returns.keys()
    assert any(
        realtime_returns[key] != historical_returns[key] for key in realtime_returns
    ), "the two modeled source vintages must remain distinguishable"


def _number_rendered(markdown: str, value: float) -> bool:
    candidates = {
        format(value, ".12g"),
        f"{value:.6f}",
        f"{value:.4f}",
        f"{value:.3f}",
        f"{value:.2%}",
        f"{value * 100.0:.2f}%",
    }
    return any(candidate in markdown for candidate in candidates)


def _assert_markdown_matches_sources(
    case: PublishedBaijiuCase,
    markdown: str,
) -> None:
    for token in (
        REPORT_ID,
        REALTIME,
        LATEST_HISTORICAL,
        PRIMARY.asset_id,
        PRIMARY.symbol,
        PROXY.asset_id,
        PROXY.symbol,
        BENCHMARK_ASSET_ID,
        BENCHMARK_SYMBOL,
        "primary",
        "proxy",
        "absolute",
        "excess",
        *CYCLE_IDS,
        *CHANNEL_IDS,
        *CONTROL_IDS,
        *EVENT_IDS,
        RESIDUAL_ID,
    ):
        assert token in markdown

    for interpretation in INTERPRETATIONS:
        manifest = case.manifests[interpretation]
        assert manifest.run_id in markdown
        assert manifest.data_vintage.isoformat() in markdown
        assert manifest.model_version in markdown
        source = _source_attribution(case, interpretation)
        for asset in ASSETS:
            for return_basis in ("absolute", "excess"):
                group = source.loc[
                    source["asset_id"].eq(asset.asset_id)
                    & source["return_basis"].eq(return_basis)
                ]
                assert len(group) > 0
                observed_return = float(group["observed_return"].iloc[0])
                assert _number_rendered(markdown, observed_return)
                cycle_one = group.loc[group["component_id"].eq("C1")].iloc[0]
                assert _number_rendered(
                    markdown,
                    float(cycle_one["point_contribution"]),
                )
                assert _number_rendered(markdown, float(cycle_one["lower_50"]))
                assert _number_rendered(markdown, float(cycle_one["upper_80"]))
                reason = _unavailable_reason(
                    interpretation,
                    asset.asset_id,
                    return_basis,
                )
                assert reason in markdown

    lowered = markdown.lower()
    assert "significance" in lowered
    assert "interval_status" in lowered
    assert "status" in lowered
    assert (
        "vintage comparison" in lowered
        or "vintage delta" in lowered
        or "版本对比" in markdown
        or "时点对比" in markdown
    )


def _rewrite_manifest(
    run_dir: Path,
    mutation: Callable[[dict[str, object]], None],
) -> RunManifest:
    manifest_path = run_dir / MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutation(payload)
    updated = RunManifest.model_validate_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    manifest_path.write_bytes(updated.to_json_bytes())
    verify_manifest(run_dir, expected=updated)
    return updated


def test_task18_report_module_is_importable() -> None:
    try:
        module = importlib.import_module("seven_cycle_platform.reports.baijiu_2019")
    except ModuleNotFoundError as error:
        pytest.fail(f"Task18 report module is missing: {error}", pytrace=False)

    assert module.__name__ == "seven_cycle_platform.reports.baijiu_2019"


@pytest.mark.parametrize("requested_interpretation", INTERPRETATIONS)
def test_cli_writes_verified_two_vintage_report_outside_immutable_runs(
    requested_interpretation: str,
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    case = replace(
        case,
        requested_run_id=case.manifests[requested_interpretation].run_id,
    )
    snapshots = {
        interpretation: _run_snapshot(case.run_dir(interpretation))
        for interpretation in INTERPRETATIONS
    }

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 0, captured.err
    assert captured.err == ""
    cli_payload = json.loads(captured.out)
    assert captured.out == (
        json.dumps(
            cli_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    markdown_path, json_path = _report_paths(case)
    serialized_cli_payload = json.dumps(cli_payload, ensure_ascii=False)
    assert str(markdown_path) in serialized_cli_payload
    assert str(json_path) in serialized_cli_payload
    assert case.requested_run_id in serialized_cli_payload
    assert markdown_path.is_file()
    assert json_path.is_file()

    report_payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(report_payload, dict)
    _assert_report_json_matches_sources(case, report_payload)
    _assert_markdown_matches_sources(
        case,
        markdown_path.read_text(encoding="utf-8"),
    )

    for interpretation in INTERPRETATIONS:
        run_dir = case.run_dir(interpretation)
        verify_manifest(run_dir, expected=case.manifests[interpretation])
        assert _run_snapshot(run_dir) == snapshots[interpretation]
        assert not (run_dir / REPORT_MARKDOWN_FILENAME).exists()
        assert not (run_dir / REPORT_JSON_FILENAME).exists()


def test_full_stage1_stage2_path_and_interval_chain_publishes_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _publish_full_chain_case(tmp_path)

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 0, captured.err
    assert captured.err == ""
    markdown_path, json_path = _report_paths(case)
    assert markdown_path.is_file()
    assert json_path.is_file()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    _assert_report_json_matches_sources(case, report)
    assert {
        row["interval_status"]
        for row in report["attribution"]
        if row["asset_id"] == PRIMARY.asset_id
    } == {"available"}


@pytest.mark.parametrize(
    "mutation",
    ("tampered_attribution", "tampered_conservation", "missing_manifest"),
)
def test_report_rejects_unverified_interpretation_runs(
    mutation: str,
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    historical_run = case.run_dir(LATEST_HISTORICAL)
    if mutation == "tampered_attribution":
        target = historical_run / ASSET_ATTRIBUTION_FILENAME
        target.write_bytes(target.read_bytes() + b"tampered-attribution")
    elif mutation == "tampered_conservation":
        target = historical_run / ASSET_ATTRIBUTION_CONSERVATION_FILENAME
        target.write_bytes(target.read_bytes() + b"tampered-conservation")
    else:
        (historical_run / MANIFEST_FILENAME).unlink()

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    lowered = captured.err.lower()
    assert "manifest" in lowered
    if mutation.startswith("tampered"):
        assert "checksum" in lowered
    else:
        assert "missing" in lowered or "invalid" in lowered
    assert "traceback" not in lowered
    markdown_path, json_path = _report_paths(case)
    assert not markdown_path.exists()
    assert not json_path.exists()


@pytest.mark.parametrize(
    "metadata_gap",
    ("missing_interpretation_mapping", "missing_unavailable_reason"),
)
def test_report_rejects_incomplete_manifest_case_metadata(
    metadata_gap: str,
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    if metadata_gap == "missing_interpretation_mapping":

        def remove_mapping(payload: dict[str, object]) -> None:
            quality = payload["quality_summary"]
            assert isinstance(quality, dict)
            case_metadata = quality[REPORT_ID]
            assert isinstance(case_metadata, dict)
            mapping = case_metadata["interpretation_runs"]
            assert isinstance(mapping, dict)
            del mapping[LATEST_HISTORICAL]

        _rewrite_manifest(case.run_dir(REALTIME), remove_mapping)
    else:
        missing_key = _unavailable_reason_key(
            PRIMARY.asset_id,
            "absolute",
        )

        def remove_reason(payload: dict[str, object]) -> None:
            quality = payload["quality_summary"]
            assert isinstance(quality, dict)
            case_metadata = quality[REPORT_ID]
            assert isinstance(case_metadata, dict)
            reasons = case_metadata["unavailable_reasons"]
            assert isinstance(reasons, dict)
            del reasons[missing_key]

        _rewrite_manifest(case.run_dir(LATEST_HISTORICAL), remove_reason)

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    lowered = captured.err.lower()
    if metadata_gap == "missing_interpretation_mapping":
        assert "interpretation" in lowered
        assert LATEST_HISTORICAL in lowered
    else:
        assert "unavailable" in lowered
        assert "reason" in lowered
        assert PRIMARY.asset_id in lowered
        assert "foreign_flow_funding" in lowered
    assert "traceback" not in lowered
    markdown_path, json_path = _report_paths(case)
    assert not markdown_path.exists()
    assert not json_path.exists()


def test_report_refuses_to_promote_proxy_when_primary_rows_are_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _publish_case(
        tmp_path,
        missing_primary_interpretation=REALTIME,
    )
    realtime_source = _source_attribution(case, REALTIME)
    assert set(realtime_source["asset_id"]) == {PROXY.asset_id}
    assert realtime_source["asset_id"].ne(PRIMARY.asset_id).all()

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    lowered = captured.err.lower()
    assert "primary" in lowered or PRIMARY.asset_id in lowered
    assert "proxy" in lowered or PROXY.asset_id in lowered
    assert "traceback" not in lowered
    markdown_path, json_path = _report_paths(case)
    assert not markdown_path.exists()
    assert not json_path.exists()


def test_identical_report_pair_is_reused_without_rewriting(
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)

    first_code, first_capture = _invoke_report_cli(case, capsys)
    first_payload = json.loads(first_capture.out)
    markdown_path, json_path = _report_paths(case)
    first_bytes = (markdown_path.read_bytes(), json_path.read_bytes())
    second_code, second_capture = _invoke_report_cli(case, capsys)
    second_payload = json.loads(second_capture.out)

    assert first_code == second_code == 0
    assert first_payload["reused"] is False
    assert second_payload["reused"] is True
    assert (markdown_path.read_bytes(), json_path.read_bytes()) == first_bytes


@pytest.mark.parametrize(
    "symlink_location",
    ("runs_root", "reports_root", "report_destination", "report_file"),
)
def test_report_rejects_symlinked_path_components(
    symlink_location: str,
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    if symlink_location == "runs_root":
        runs_root = case.product_root / "runs"
        real_runs = case.product_root / "real-runs"
        runs_root.rename(real_runs)
        runs_root.symlink_to(real_runs, target_is_directory=True)
    elif symlink_location == "reports_root":
        external = tmp_path / "external-reports-root"
        external.mkdir()
        (case.product_root / "reports").symlink_to(
            external,
            target_is_directory=True,
        )
    elif symlink_location == "report_file":
        initial_code, initial_capture = _invoke_report_cli(case, capsys)
        assert initial_code == 0, initial_capture.err
        markdown_path, _ = _report_paths(case)
        external = tmp_path / "external-report.md"
        external.write_bytes(markdown_path.read_bytes())
        markdown_path.unlink()
        markdown_path.symlink_to(external)
    else:
        reports_root = case.product_root / "reports"
        reports_root.mkdir()
        external = tmp_path / "external-report"
        external.mkdir()
        case.report_dir().symlink_to(external, target_is_directory=True)

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    lowered = captured.err.lower()
    assert "symlink" in lowered or "real directory" in lowered
    assert "traceback" not in lowered


def test_source_replacement_after_manifest_verification_is_rejected_by_checksum(
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    report_module = importlib.import_module("seven_cycle_platform.reports.baijiu_2019")
    original_load = report_module._load_verified_manifest_at
    replaced = False

    def load_then_replace(
        runs_descriptor: int,
        run_id: str,
    ) -> tuple[int, object, RunManifest]:
        nonlocal replaced
        loaded = original_load(runs_descriptor, run_id)
        if not replaced and run_id == case.requested_run_id:
            target = case.product_root / "runs" / run_id / ASSET_ATTRIBUTION_FILENAME
            frame = pd.read_parquet(target)
            frame.loc[0, "point_contribution"] += 0.001
            table = pa.Table.from_arrays(
                [
                    pa.array(
                        frame[field.name].tolist(),
                        type=field.type,
                        from_pandas=True,
                    )
                    for field in ASSET_ATTRIBUTION_SCHEMA
                ],
                schema=ASSET_ATTRIBUTION_SCHEMA,
            )
            pq.write_table(table, target)
            replaced = True
        return loaded

    monkeypatch.setattr(
        report_module,
        "_load_verified_manifest_at",
        load_then_replace,
    )

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    assert "checksum" in captured.err.lower()
    assert not case.report_dir().exists()


def test_interrupted_report_publication_never_exposes_a_partial_pair(
    published_case: PublishedBaijiuCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _clone_case(published_case, tmp_path)
    report_module = importlib.import_module("seven_cycle_platform.reports.baijiu_2019")
    original_rename = report_module.os.rename

    def fail_final_promotion(
        source: object,
        destination: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        if destination == case.requested_run_id:
            raise OSError("simulated atomic report promotion failure")
        original_rename(source, destination, *args, **kwargs)

    monkeypatch.setattr(report_module.os, "rename", fail_final_promotion)

    exit_code, captured = _invoke_report_cli(case, capsys)

    assert exit_code == 1
    assert captured.out == ""
    assert not case.report_dir().exists()
    reports_root = case.product_root / "reports"
    assert not list(reports_root.glob(".*.tmp"))
