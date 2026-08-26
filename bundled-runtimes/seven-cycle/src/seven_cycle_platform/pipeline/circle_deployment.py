"""Publish one immutable Circle deployment from governed and browser products."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import shutil
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ASSET_ATTRIBUTION_SCHEMA,
    CYCLE_PHASE_VINTAGE_SCHEMA,
)
from seven_cycle_platform.products.asset_attribution import (
    ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
    ASSET_ATTRIBUTION_FILENAME,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_FILENAME,
    ASSET_MAPPING_CURRENT_SCHEMA,
)
from seven_cycle_platform.products.cycle_forecast import (
    CYCLE_FORECAST_FILENAME,
    CYCLE_FORECAST_SCHEMA,
)
from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_FILENAME,
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME,
    DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME,
    PUBLICATION_GATE_SCHEMA,
)
from seven_cycle_platform.storage.manifest import (
    load_manifest,
    sha256_file,
    verify_manifest,
)
from seven_cycle_platform.storage.publisher import publish_run
from seven_cycle_platform.storage.run_context import RunContext, canonical_json_bytes


RESEARCH_DATA_FILENAMES = (
    "market-surface.json",
    "cycle-research.json",
    "asset-statistics.json",
    "forecast-extension.json",
    "data-calibration.json",
)
_FOUNDATION_SCHEMAS = {
    "cycle_phase_vintage.parquet": CYCLE_PHASE_VINTAGE_SCHEMA,
    CYCLE_EVIDENCE_FILENAME: CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME: DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME: PUBLICATION_GATE_SCHEMA,
    CALIBRATION_LOG_FILENAME: CALIBRATION_LOG_SCHEMA,
}


@dataclass(frozen=True, slots=True)
class CircleDeploymentResult:
    run_id: str
    run_dir: Path
    reused: bool


def _month_end(value: str) -> date:
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, calendar.monthrange(year, month)[1])


def _context_values(context: RunContext) -> dict[str, object]:
    return {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }


def _rewrite_table(
    source_path: Path,
    schema: pa.Schema,
    context: RunContext,
) -> pa.Table:
    rows = pq.read_table(source_path).to_pylist()
    provenance = _context_values(context)
    for row in rows:
        for name, value in provenance.items():
            if name in schema.names:
                row[name] = value
    return pa.Table.from_pylist(rows, schema=schema)


def _cycle_phase_table(
    source_path: Path,
    cycle_research: dict[str, Any],
    context: RunContext,
) -> pa.Table:
    rows = _rewrite_table(
        source_path,
        CYCLE_PHASE_VINTAGE_SCHEMA,
        context,
    ).to_pylist()
    latest_date = max(row["date"] for row in rows)
    prior_level: float | None = None
    provenance = _context_values(context)
    for item in cycle_research["C4Realtime"]["timeline"]:
        item_date = _month_end(item["date"])
        level = float(item["rt_level"])
        slope = 0.0 if prior_level is None else level - prior_level
        prior_level = level
        if item_date <= latest_date:
            continue
        row = _empty_row(CYCLE_PHASE_VINTAGE_SCHEMA)
        row.update(
            {
                "date": item_date,
                "cycle_id": "C4",
                "vintage": "pseudo_vintage",
                "vintage_caveat": (
                    "Indicator-family realtime bridge; not a true historical release vintage."
                ),
                "angle": float(item["rt_angle"]),
                "phase": str(item["rt_phase"]),
                "level": level,
                "slope": slope,
                "uncertainty": float(item["rt_uncertainty"]),
                "center_period": 42.0,
                "confidence": float(item["confidence"]),
                **provenance,
            }
        )
        rows.append(row)
    return pa.Table.from_pylist(rows, schema=CYCLE_PHASE_VINTAGE_SCHEMA)


def _empty_row(schema: pa.Schema) -> dict[str, object]:
    return {name: None for name in schema.names}


def _asset_mapping_table(
    payload: dict[str, Any],
    context: RunContext,
) -> pa.Table:
    rows: list[dict[str, object]] = []
    provenance = _context_values(context)
    for asset in payload["assets"]:
        data_end = _month_end(asset["dataEnd"])
        freshness_status = "fresh" if data_end >= context.data_vintage else "stale"
        for horizon_text, horizon in asset["horizons"].items():
            forecast = horizon.get("forecast")
            row = _empty_row(ASSET_MAPPING_CURRENT_SCHEMA)
            row.update(
                {
                    "asset_id": asset["assetId"],
                    "horizon_months": int(horizon_text),
                    "absolute_distribution_status": (
                        "available" if forecast is not None else "unavailable"
                    ),
                    "absolute_calibration_version": "cycle-state-neighbor-v1",
                    "excess_distribution_status": "unavailable",
                    "influence_status": "unavailable",
                    "influence_evidence_level": "retrospective_only",
                    "influence_reason_codes": '["not_causal_attribution"]',
                    "range_status": "unavailable",
                    "range_scope": "none",
                    "range_reason_codes": '["portfolio_weights_not_produced"]',
                    "transferability_status": "unavailable",
                    "mapping_status": (
                        "conditional" if horizon["status"] == "limited" else "unavailable"
                    ),
                    "evidence_level": "retrospective_only",
                    "freshness_status": freshness_status,
                    "stale_feature_count": int(freshness_status == "stale"),
                    "freshness_reason_codes": (
                        "[]" if freshness_status == "fresh" else '["source_stale"]'
                    ),
                    "stale_feature_json": "[]",
                    "publication_status": "partial",
                    "publication_reason_codes": (
                        '["qualified_limited_research"]'
                        if horizon["status"] == "limited"
                        else '["model_gate_blocked"]'
                    ),
                    "caveat_codes": '["not_portfolio_backtest","not_causal"]',
                    "snapshot_config_hash": context.config_hash,
                    "distribution_config_hash": context.config_hash,
                    "transferability_config_hash": context.config_hash,
                    "weight_config_hash": context.config_hash,
                    "forecast_origin": context.data_vintage,
                    **provenance,
                }
            )
            if forecast is not None:
                probability_up = float(forecast["probabilityUp"])
                row.update(
                    {
                        "absolute_up_probability": probability_up,
                        "absolute_neutral_probability": 0.0,
                        "absolute_down_probability": 1.0 - probability_up,
                        "absolute_q50": float(forecast["medianReturn"]),
                        "absolute_expected_return": float(forecast["medianReturn"]),
                        "absolute_volatility": float(forecast["conditionalVol"]),
                        "absolute_effective_samples": int(forecast["analogs"]),
                        "cycle_influence_json": json.dumps(
                            {
                                "conditional_return_interval": {
                                    "p20": float(forecast["low20"]),
                                    "p80": float(forecast["high80"]),
                                },
                                "state_model": "C4_C5_C7_neighbor_state",
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    }
                )
            rows.append(row)
    return pa.Table.from_pylist(rows, schema=ASSET_MAPPING_CURRENT_SCHEMA)


def _asset_attribution_tables(
    payload: dict[str, Any],
    context: RunContext,
) -> tuple[pa.Table, pa.Table]:
    attribution_rows: list[dict[str, object]] = []
    conservation_rows: list[dict[str, object]] = []
    provenance = _context_values(context)
    period_start = date(2019, 1, 31)
    period_end = date(2019, 12, 31)
    for asset in payload["assets"]:
        observed = asset.get("actual_2019")
        association = asset.get("c4_assoc_contribution_2019")
        if observed is None or association is None:
            continue
        observed_return = float(observed)
        c4_contribution = float(association)
        residual = observed_return - c4_contribution
        asset_id = f"{asset['category']}::{asset['name']}"
        common = {
            "asset_id": asset_id,
            "period_start": period_start,
            "period_end": period_end,
            "horizon_months": 12,
            "return_basis": "absolute",
            "observed_return": observed_return,
            "reconstructed_return": observed_return,
            "interval_status": "unavailable",
            "status": "degraded",
            "evidence_level": "low",
            "effective_samples": int(asset["n_months"]),
            "draw_count": 1,
            **provenance,
        }
        for component_type, component_id, contribution, is_explained, is_residual in (
            (
                "cycle",
                "C4_statistical_association_not_causal",
                c4_contribution,
                True,
                False,
            ),
            (
                "asset_residual",
                "unexplained_residual",
                residual,
                False,
                True,
            ),
        ):
            row = _empty_row(ASSET_ATTRIBUTION_SCHEMA)
            row.update(
                {
                    **common,
                    "component_type": component_type,
                    "component_id": component_id,
                    "point_contribution": contribution,
                    "significance": "unavailable",
                    "is_explained": is_explained,
                    "is_residual": is_residual,
                }
            )
            attribution_rows.append(row)
        diagnostic = _empty_row(ASSET_ATTRIBUTION_CONSERVATION_SCHEMA)
        diagnostic.update(
            {
                "asset_id": asset_id,
                "period_start": period_start,
                "period_end": period_end,
                "horizon_months": 12,
                "return_basis": "absolute",
                "point_component_sum": observed_return,
                "observed_return": observed_return,
                "point_conservation_error": 0.0,
                "available_component_count": 0,
                "unavailable_component_count": 2,
                "status": "unavailable",
                **provenance,
            }
        )
        conservation_rows.append(diagnostic)
    return (
        pa.Table.from_pylist(attribution_rows, schema=ASSET_ATTRIBUTION_SCHEMA),
        pa.Table.from_pylist(
            conservation_rows,
            schema=ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
        ),
    )


def _cycle_forecast_table(
    payload: dict[str, Any],
    context: RunContext,
) -> pa.Table:
    rows: list[dict[str, object]] = []
    provenance = _context_values(context)
    for horizon_months, forecast in enumerate(payload["forecast"], start=1):
        row = _empty_row(CYCLE_FORECAST_SCHEMA)
        row.update(
            {
                "cycle_id": "C4",
                "horizon_months": horizon_months,
                "forecast_date": _month_end(forecast["date"]),
                "status": "available",
                "recovery_probability": float(forecast["p_recovery"]),
                "expansion_probability": float(forecast["p_expansion"]),
                "downturn_probability": float(forecast["p_downturn"]),
                "contraction_probability": float(forecast["p_contraction"]),
                "turning_status": "unavailable",
                "forecast_uncertainty": float(forecast["high"] - forecast["low"]),
                "draw_count": 500,
                "probability_support_count": 500,
                "calibration_method": "correlated_residual_bootstrap",
                "calibration_version": "c4-ridge-v2",
                "calibration_reason": "limited stale-input research forecast",
                "forecast_value_source_role": "live_limited",
                "forecast_value_source_model_id": "ridge",
                "forecast_value_source_model_version": "c4-ridge-v2",
                "live_model_id": "ridge",
                "live_model_role": "limited",
                "live_model_version": "c4-ridge-v2",
                "promotion_decision": "limited",
                "source_data_vintage": context.data_vintage,
                **provenance,
            }
        )
        rows.append(row)
    return pa.Table.from_pylist(rows, schema=CYCLE_FORECAST_SCHEMA)


def _existing_run(
    product_root: Path,
    context: RunContext,
) -> CircleDeploymentResult | None:
    run_dir = product_root / "runs" / context.run_id
    if not run_dir.exists():
        return None
    manifest = load_manifest(run_dir)
    verify_manifest(run_dir, expected=manifest)
    if (
        manifest.as_of != context.as_of
        or manifest.data_vintage != context.data_vintage
        or manifest.model_version != context.model_version
        or manifest.config_hash != context.config_hash
        or dict(manifest.input_checksums) != dict(context.input_checksums)
    ):
        raise ValueError("existing deployment run does not match current inputs")
    latest_path = product_root / "latest.json"
    temporary_path = product_root / ".latest.deployment.tmp"
    temporary_path.write_bytes(
        canonical_json_bytes({"run_id": context.run_id}) + b"\n"
    )
    temporary_path.replace(latest_path)
    return CircleDeploymentResult(
        run_id=context.run_id,
        run_dir=run_dir,
        reused=True,
    )


def build_circle_deployment(
    *,
    product_root: Path,
    foundation_run_dir: Path,
    web_data_dir: Path,
    asset_forecast_path: Path,
    asset_statistics_path: Path,
    c4_forecast_path: Path,
    as_of: date,
) -> CircleDeploymentResult:
    foundation_manifest = load_manifest(foundation_run_dir)
    verify_manifest(foundation_run_dir, expected=foundation_manifest)
    asset_forecast = json.loads(asset_forecast_path.read_bytes())
    asset_statistics = json.loads(asset_statistics_path.read_bytes())
    c4_forecast = json.loads(c4_forecast_path.read_bytes())
    cycle_research = json.loads((web_data_dir / "cycle-research.json").read_bytes())
    data_vintage = _month_end(asset_forecast["meta"]["asOf"])
    web_paths = [web_data_dir / filename for filename in RESEARCH_DATA_FILENAMES]
    input_paths = [
        foundation_run_dir / "manifest.json",
        asset_forecast_path,
        asset_statistics_path,
        c4_forecast_path,
        *web_paths,
    ]
    input_checksums = {
        path.relative_to(path.parents[2]).as_posix()
        if len(path.parents) > 2
        else path.name: sha256_file(path)
        for path in input_paths
    }
    context = RunContext.create(
        as_of=as_of,
        data_vintage=data_vintage,
        model_version="circle-deployment-v5",
        config={
            "asset_count": len(asset_forecast["assets"]),
            "attribution_kind": "C4_statistical_association_not_causal",
            "attribution_period": "2019",
            "foundation_run_id": foundation_manifest.run_id,
            "research_data_files": list(RESEARCH_DATA_FILENAMES),
        },
        input_checksums=input_checksums,
        quality_summary={
            "asset_count": len(asset_forecast["assets"]),
            "asset_attribution_count": sum(
                asset.get("actual_2019") is not None
                and asset.get("c4_assoc_contribution_2019") is not None
                for asset in asset_statistics["assets"]
            ),
            "asset_attribution_status": "degraded_not_causal",
            "asset_forecast_status": asset_forecast["governance"]["publicationStatus"],
            "cycle_forecast_count": len(c4_forecast["forecast"]),
            "cycle_realtime_date": cycle_research["C4Realtime"]["latest"]["date"],
            "foundation_run_id": foundation_manifest.run_id,
        },
        created_at=datetime.combine(as_of, time.min, tzinfo=timezone.utc),
    )
    existing = _existing_run(product_root, context)
    if existing is not None:
        return existing

    def write_staging(staging_dir: Path) -> None:
        for filename, schema in _FOUNDATION_SCHEMAS.items():
            table = (
                _cycle_phase_table(
                    foundation_run_dir / filename,
                    cycle_research,
                    context,
                )
                if filename == "cycle_phase_vintage.parquet"
                else _rewrite_table(foundation_run_dir / filename, schema, context)
            )
            pq.write_table(table, staging_dir / filename)
        pq.write_table(
            _asset_mapping_table(asset_forecast, context),
            staging_dir / ASSET_MAPPING_CURRENT_FILENAME,
        )
        attribution, conservation = _asset_attribution_tables(
            asset_statistics,
            context,
        )
        pq.write_table(attribution, staging_dir / ASSET_ATTRIBUTION_FILENAME)
        pq.write_table(
            conservation,
            staging_dir / ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
        )
        pq.write_table(
            _cycle_forecast_table(c4_forecast, context),
            staging_dir / CYCLE_FORECAST_FILENAME,
        )
        research_data_dir = staging_dir / "research_data"
        research_data_dir.mkdir()
        for source in web_paths:
            shutil.copyfile(source, research_data_dir / source.name)

    manifest = publish_run(product_root, context, write_staging=write_staging)
    return CircleDeploymentResult(
        run_id=manifest.run_id,
        run_dir=product_root / "runs" / manifest.run_id,
        reused=False,
    )


__all__ = ["CircleDeploymentResult", "build_circle_deployment"]
