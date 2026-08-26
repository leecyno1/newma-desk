"""Publish retrospective pseudo-vintage M3 asset attribution research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from types import SimpleNamespace

import numpy as np
import pandas as pd

from seven_cycle_platform.assets import (
    LEGACY_CORE_ASSET_MAP,
    build_core_asset_panel,
    load_legacy_monthly_returns,
)
from seven_cycle_platform.attribution import (
    ATTRIBUTION_DRAW_COLUMNS,
    CYCLE_IDS,
    AttributionIntervalResult,
    CycleToChannelConfig,
    HierarchicalTVPConfig,
    UncertaintyConfig,
    compose_attribution_paths,
    estimate_attribution_intervals,
    estimate_channel_to_asset,
    estimate_cycle_to_channel,
)
from seven_cycle_platform.channels import local_level_innovations
from seven_cycle_platform.cycles.preprocess import expanding_standardize
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.legacy.research_current_mapping_release import (
    METHOD_ID as CURRENT_MAPPING_METHOD_ID,
    RETROSPECTIVE_ANALOG_FILENAME,
    RetrospectiveAnalogConfig,
    build_research_current_mapping,
)
from seven_cycle_platform.pipeline.cycles import load_cycle_pipeline_input
from seven_cycle_platform.products.asset_attribution import (
    AssetAttributionProduct,
    build_asset_attribution,
    validate_asset_attribution,
    write_asset_attribution,
)
from seven_cycle_platform.products.asset_mapping_current import (
    M3_INFLUENCE_COLUMNS,
    validate_asset_mapping_current,
    write_asset_mapping_current,
)
from seven_cycle_platform.products.cycle_asset_surface import (
    CYCLE_ASSET_SURFACE_COLUMNS,
    build_cycle_asset_surface_product,
    write_cycle_asset_surface_product,
)
from seven_cycle_platform.products.cycle_phase import (
    build_and_write_cycle_phase_vintage,
)
from seven_cycle_platform.registry.models import RegistryBundle
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import (
    RunManifest,
    load_manifest,
    sha256_file,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import canonical_json_bytes


RESEARCH_CHANNEL_CATEGORY_MAP = {
    "growth": "growth_demand",
    "prices": "inflation_prices",
    "rates": "real_rate_discount",
    "credit": "liquidity_credit",
    "external": "fx_external_demand",
    "market": "risk_premium_crowding",
}
RESEARCH_CHANNEL_IDS = tuple(RESEARCH_CHANNEL_CATEGORY_MAP.values())
RESEARCH_CHANNEL_STATE_AUDIT_FILENAME = "research_channel_state_audit.json"
M3_INFLUENCE_FILENAME = "m3_influence.parquet"
RESEARCH_ATTRIBUTION_CONFIG_FILENAME = "research_attribution_config.json"
RESEARCH_CHANNEL_STATE_COLUMNS = (
    "date",
    "channel_id",
    "state",
    "innovation",
    "uncertainty",
    "member_count",
    "vintage_kind",
    "status",
    "status_reason",
)
_GOVERNED_ASSET_IDS = tuple(
    sorted(mapping.asset_id for mapping in LEGACY_CORE_ASSET_MAP.values())
)
_FAILED_ATTRIBUTION_STATUSES = frozenset(
    {"insufficient_history", "not_identifiable", "unavailable"}
)
_CHANNEL_COMPONENT_TYPES = frozenset(
    {
        "channel_baseline_path",
        "channel_residual_path",
        "unresolved_channel",
    }
)
_REQUIRED_SOURCE_FILES = (
    "cycle_phase_vintage.parquet",
    "cycle_asset_surface.parquet",
    "cycle_model_versions.json",
    "quality_findings.parquet",
    "verification_plan.json",
)
_SOURCE_AUDIT_FILES = (
    "cycle_model_versions.json",
    "quality_findings.parquet",
    "verification_plan.json",
)
_CYCLE_STATE_COLUMNS = (
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    "angle",
    "phase",
    "level",
    "slope",
    "amplitude",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
)


@dataclass(frozen=True, slots=True)
class ResearchAttributionReleaseResult:
    manifest: RunManifest
    run_dir: Path
    period_end: date
    asset_count: int
    channel_count: int


@dataclass(frozen=True, slots=True)
class _MemoryBundleSnapshot:
    observations: tuple[Observation, ...]
    monthly_categories: Mapping[str, str]


def _required_frame(
    values: object,
    *,
    name: str,
    columns: Sequence[str],
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame) or values.empty:
        raise ValueError(f"{name} must be a non-empty DataFrame")
    if values.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")
    return values.loc[:, list(columns)].copy(deep=True)


def _month_end_dates(values: pd.Series, *, name: str) -> pd.Series:
    try:
        dates = pd.to_datetime(values, errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain valid dates") from error
    if dates.isna().any():
        raise ValueError(f"{name} cannot contain missing dates")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_convert(timezone.utc).dt.tz_localize(None)
    return dates.dt.to_period("M").dt.to_timestamp("M")


def build_cycle_innovations(cycle_phase: pd.DataFrame) -> pd.DataFrame:
    """Build causal first differences of C1-C7 cycle levels."""

    frame = _required_frame(
        cycle_phase,
        name="cycle_phase",
        columns=("date", "cycle_id", "level"),
    )
    frame["date"] = _month_end_dates(frame["date"], name="cycle date")
    if frame.duplicated(["date", "cycle_id"]).any():
        raise ValueError("cycle_phase date × cycle_id rows must be unique")
    if set(frame["cycle_id"]) != set(CYCLE_IDS):
        raise ValueError("cycle_phase must contain exactly C1 through C7")
    for _, group in frame.groupby("date", sort=False):
        if len(group) != len(CYCLE_IDS) or set(group["cycle_id"]) != set(CYCLE_IDS):
            raise ValueError("every cycle date must contain exactly C1 through C7")
    frame["level"] = pd.to_numeric(frame["level"], errors="coerce")
    if not np.isfinite(frame["level"].to_numpy(dtype="float64")).all():
        raise ValueError("cycle levels must be finite")
    frame = frame.sort_values(["cycle_id", "date"], kind="stable")
    frame["innovation"] = frame.groupby("cycle_id", sort=False)["level"].diff()
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    output = frame.loc[frame["innovation"].notna(), ["date", "cycle_id", "innovation"]]
    output = output.assign(_cycle_order=output["cycle_id"].map(cycle_order))
    return (
        output.sort_values(["date", "_cycle_order"], kind="stable")
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )


def _observation_snapshot_key(record: Observation) -> tuple[object, ...]:
    return (
        record.entity_id,
        record.observation_date,
        record.release_date,
        record.vintage_date,
        record.revision_number,
        record.vintage_kind.value,
        record.value,
        record.unit,
        record.source,
        record.retrieval_time,
        record.quality_status,
    )


def _snapshot_memory_bundle(bundle: object) -> _MemoryBundleSnapshot:
    if isinstance(bundle, _MemoryBundleSnapshot):
        return bundle
    supplied_observations = getattr(bundle, "observations", None)
    categories = getattr(bundle, "monthly_categories", None)
    if isinstance(supplied_observations, (str, bytes, bytearray)):
        raise TypeError("bundle observations must be a non-empty iterable")
    try:
        observations = tuple(supplied_observations)
    except TypeError as error:
        raise TypeError("bundle observations must be a non-empty iterable") from error
    if not observations or any(
        not isinstance(record, Observation) for record in observations
    ):
        raise TypeError("bundle observations must contain Observation records")
    if not isinstance(categories, Mapping) or not categories:
        raise TypeError("bundle monthly_categories must be a non-empty mapping")
    normalized_categories: dict[str, str] = {}
    for entity_id, category in categories.items():
        if not isinstance(entity_id, str) or not entity_id:
            raise TypeError("monthly category entity ids must be non-empty strings")
        if category not in RESEARCH_CHANNEL_CATEGORY_MAP:
            raise ValueError(f"unsupported monthly category: {category}")
        normalized_categories[entity_id] = str(category)
    if len(normalized_categories) != 27:
        raise ValueError("monthly_categories must contain exactly 27 entities")
    if set(normalized_categories.values()) != set(RESEARCH_CHANNEL_CATEGORY_MAP):
        raise ValueError("monthly categories must cover all six research categories")
    observed_entities = {getattr(record, "entity_id", None) for record in observations}
    missing_entities = sorted(set(normalized_categories).difference(observed_entities))
    if missing_entities:
        raise ValueError(
            "all 27 monthly category entities must have observations: "
            + ", ".join(missing_entities)
        )
    detached_observations = tuple(
        sorted(
            (record.model_copy(deep=True) for record in observations),
            key=_observation_snapshot_key,
        )
    )
    detached_categories = MappingProxyType(dict(sorted(normalized_categories.items())))
    return _MemoryBundleSnapshot(
        observations=detached_observations,
        monthly_categories=detached_categories,
    )


def _bundle_parts(bundle: object) -> tuple[tuple[Observation, ...], Mapping[str, str]]:
    snapshot = _snapshot_memory_bundle(bundle)
    return snapshot.observations, snapshot.monthly_categories


def _vintage_value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def build_research_channel_states(
    bundle: object,
    *,
    min_periods: int = 24,
    process_variance: float = 0.05,
    observation_variance: float = 0.25,
) -> pd.DataFrame:
    """Build six category-driven causal channel states from pseudo-vintage data."""

    snapshot = _snapshot_memory_bundle(bundle)
    observations = snapshot.observations
    categories = snapshot.monthly_categories
    rows: list[dict[str, object]] = []
    for record in observations:
        entity_id = getattr(record, "entity_id", None)
        if entity_id not in categories:
            continue
        if _vintage_value(getattr(record, "vintage_kind", None)) != "pseudo_vintage":
            raise ValueError("research channel evidence must be pseudo_vintage")
        rows.append(
            {
                "entity_id": entity_id,
                "date": getattr(record, "observation_date", None),
                "value": getattr(record, "value", None),
                "vintage_date": getattr(record, "vintage_date", None),
                "revision_number": getattr(record, "revision_number", None),
            }
        )
    if not rows:
        raise ValueError("bundle contains no categorized monthly observations")
    observations_frame = pd.DataFrame(rows)
    observations_frame["date"] = _month_end_dates(
        observations_frame["date"], name="observation date"
    )
    observations_frame["vintage_date"] = pd.to_datetime(
        observations_frame["vintage_date"], errors="raise"
    )
    observations_frame["revision_number"] = pd.to_numeric(
        observations_frame["revision_number"], errors="raise"
    )
    observations_frame["value"] = pd.to_numeric(
        observations_frame["value"], errors="coerce"
    )
    if not np.isfinite(observations_frame["value"].to_numpy(dtype="float64")).all():
        raise ValueError("categorized monthly observations must be finite")
    if observations_frame.duplicated(["entity_id", "date"]).any():
        raise ValueError(
            "duplicate pseudo-vintage entity_id × date records are not allowed"
        )
    observations_frame = observations_frame.sort_values(
        ["entity_id", "date"], kind="stable"
    ).reset_index(drop=True)
    observed_entities = set(observations_frame["entity_id"])
    missing_entities = sorted(set(categories).difference(observed_entities))
    if missing_entities:
        raise ValueError(
            "monthly category entities have no observations: "
            + ", ".join(missing_entities)
        )
    months = pd.date_range(
        observations_frame["date"].min(),
        observations_frame["date"].max(),
        freq="ME",
    )
    standardized: dict[str, pd.Series] = {}
    for entity_id in sorted(categories):
        entity_values = (
            observations_frame.loc[
                observations_frame["entity_id"].eq(entity_id), ["date", "value"]
            ]
            .set_index("date")["value"]
            .reindex(months)
            .astype("float64")
        )
        entity_values.name = entity_id
        standardized[entity_id] = expanding_standardize(
            entity_values,
            min_periods=min_periods,
        )
    standardized_frame = pd.DataFrame(standardized, index=months)
    records: list[dict[str, object]] = []
    for category, channel_id in RESEARCH_CHANNEL_CATEGORY_MAP.items():
        members = sorted(
            entity_id
            for entity_id, member_category in categories.items()
            if member_category == category
        )
        member_values = standardized_frame.loc[:, members]
        member_count = member_values.notna().sum(axis=1).astype("int64")
        category_state = member_values.mean(axis=1, skipna=True).where(
            member_count.gt(0)
        )
        category_state.name = channel_id
        filtered = local_level_innovations(
            category_state,
            process_variance=process_variance,
            observation_variance=observation_variance,
        )
        for current_date in months:
            innovation = filtered.innovation.loc[current_date]
            count = int(member_count.loc[current_date])
            available = bool(np.isfinite(innovation))
            reason = (
                "available"
                if available
                else (
                    "no_finite_standardized_members"
                    if count == 0
                    else "local_level_innovation_unavailable"
                )
            )
            records.append(
                {
                    "date": current_date,
                    "channel_id": channel_id,
                    "state": (
                        float(filtered.state.loc[current_date]) if available else np.nan
                    ),
                    "innovation": float(innovation),
                    "uncertainty": (
                        float(filtered.uncertainty.loc[current_date])
                        if available
                        else np.nan
                    ),
                    "member_count": count,
                    "vintage_kind": "pseudo_vintage",
                    "status": "available" if available else "unavailable",
                    "status_reason": reason,
                }
            )
    channel_order = {
        channel_id: position for position, channel_id in enumerate(RESEARCH_CHANNEL_IDS)
    }
    output = pd.DataFrame(records, columns=RESEARCH_CHANNEL_STATE_COLUMNS)
    output["_channel_order"] = output["channel_id"].map(channel_order)
    return (
        output.sort_values(["date", "_channel_order"], kind="stable")
        .drop(columns="_channel_order")
        .reset_index(drop=True)
    )


def build_research_asset_hierarchy(
    registry_bundle: RegistryBundle,
    asset_ids: Sequence[str],
) -> pd.DataFrame:
    """Derive the stage-two hierarchy only from governed registry metadata."""

    if not isinstance(registry_bundle, RegistryBundle):
        raise TypeError("registry_bundle must be a RegistryBundle")
    normalized_ids = tuple(asset_ids)
    if not normalized_ids or any(
        not isinstance(asset_id, str) or not asset_id for asset_id in normalized_ids
    ):
        raise TypeError("asset_ids must contain non-empty strings")
    if len(normalized_ids) != len(set(normalized_ids)):
        raise ValueError("asset_ids must be unique")
    asset_by_id = {asset.asset_id: asset for asset in registry_bundle.assets}
    missing = sorted(set(normalized_ids).difference(asset_by_id))
    if missing:
        raise ValueError("asset_ids are missing from registry: " + ", ".join(missing))
    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "asset_class_id": f"asset_class:{asset_by_id[asset_id].asset_class}",
                "industry_id": (
                    f"segment:{asset_by_id[asset_id].asset_class}:"
                    f"{asset_by_id[asset_id].region}"
                ),
                "is_proxy": False,
                "confidence_discount": 0.0,
            }
            for asset_id in normalized_ids
        ]
    )


def build_absolute_asset_returns(
    returns_path: str | Path,
    registry_bundle: RegistryBundle,
) -> pd.DataFrame:
    """Build absolute returns with a leave-one-out governed asset benchmark."""

    if not isinstance(registry_bundle, RegistryBundle):
        raise TypeError("registry_bundle must be a RegistryBundle")
    legacy_segments = load_legacy_monthly_returns(
        returns_path,
        assets=registry_bundle.assets,
        mapping=LEGACY_CORE_ASSET_MAP,
        require_complete=True,
    )
    panel = build_core_asset_panel(
        registry_bundle,
        legacy_seeds=legacy_segments,
        strict=False,
    )
    returns = panel.returns.loc[
        panel.returns["asset_id"].isin(_GOVERNED_ASSET_IDS),
        ["date", "asset_id", "return"],
    ].copy()
    if set(returns["asset_id"]) != set(_GOVERNED_ASSET_IDS):
        raise ValueError("legacy returns must map all five governed assets")
    if returns.duplicated(["date", "asset_id"]).any():
        raise ValueError("governed asset returns must be unique by date and asset")
    returns["date"] = _month_end_dates(returns["date"], name="asset return date")
    complete_dates = (
        returns.groupby("date")["asset_id"]
        .nunique()
        .loc[lambda counts: counts.eq(len(_GOVERNED_ASSET_IDS))]
        .index
    )
    returns = returns.loc[returns["date"].isin(complete_dates)].copy()
    if returns.empty:
        raise ValueError("legacy returns have no complete five-asset months")
    monthly_sum = returns.groupby("date")["return"].transform("sum")
    returns["benchmark_return"] = (monthly_sum - returns["return"]) / float(
        len(_GOVERNED_ASSET_IDS) - 1
    )
    return returns.sort_values(["date", "asset_id"], kind="stable").reset_index(
        drop=True
    )


def _attribution_frame(product: object) -> pd.DataFrame:
    if isinstance(product, AssetAttributionProduct):
        return product.attribution
    if isinstance(product, pd.DataFrame):
        return product.copy(deep=True)
    frame = getattr(product, "attribution", None)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("product must be an asset attribution product or DataFrame")
    return frame.copy(deep=True)


def _usable_attribution_rows(values: pd.DataFrame) -> pd.Series:
    point = pd.to_numeric(values["point_contribution"], errors="coerce")
    usable = np.isfinite(point.to_numpy(dtype="float64"))
    if "interval_status" in values:
        usable &= values["interval_status"].ne("unavailable").to_numpy()
    if "status" in values:
        usable &= ~values["status"].isin(_FAILED_ATTRIBUTION_STATUSES).to_numpy()
    return pd.Series(usable, index=values.index, dtype="bool")


def _minimum_evidence(values: pd.DataFrame) -> str:
    if "evidence_level" not in values or values.empty:
        return "low"
    rank = {"low": 0, "medium": 1, "high": 2}
    levels = [str(value) for value in values["evidence_level"] if value in rank]
    return min(levels, key=rank.__getitem__) if levels else "low"


def build_m3_influence(
    product: object,
    *,
    context: RunContext,
    channel_ids: Sequence[str] = RESEARCH_CHANNEL_IDS,
    unavailable_channel_reasons: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Build complete C1-C7 and six-channel M3 influence evidence."""

    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    normalized_channels = tuple(channel_ids)
    if normalized_channels != RESEARCH_CHANNEL_IDS:
        raise ValueError("channel_ids must retain the fixed six-channel universe")
    reasons = dict(unavailable_channel_reasons or {})
    source = _attribution_frame(product)
    required = (
        "asset_id",
        "period_end",
        "horizon_months",
        "return_basis",
        "component_type",
        "component_id",
        "point_contribution",
    )
    missing = [column for column in required if column not in source]
    if missing:
        raise ValueError("asset attribution is missing columns: " + ", ".join(missing))
    source["period_end"] = _month_end_dates(
        source["period_end"], name="attribution period_end"
    )
    source = source.loc[source["return_basis"].eq("absolute")].copy()
    if source.empty:
        raise ValueError("asset attribution has no absolute-basis rows")
    latest_period_end = source["period_end"].max()
    source = source.loc[source["period_end"].eq(latest_period_end)].copy()
    source["point_contribution"] = pd.to_numeric(
        source["point_contribution"], errors="coerce"
    )
    records: list[dict[str, object]] = []
    dimensions = source.loc[:, ["asset_id", "horizon_months"]].drop_duplicates()
    for asset_id, horizon in dimensions.itertuples(index=False, name=None):
        group = source.loc[
            source["asset_id"].eq(asset_id) & source["horizon_months"].eq(horizon)
        ].copy()
        usable = _usable_attribution_rows(group)
        cycle_rows = group.loc[group["component_type"].isin(["cycle", "cycle_group"])]
        usable_cycle_rows = cycle_rows.loc[usable.reindex(cycle_rows.index)]
        cycle_denominator = float(usable_cycle_rows["point_contribution"].abs().sum())
        for cycle_id in CYCLE_IDS:
            direct = cycle_rows.loc[
                cycle_rows["component_type"].eq("cycle")
                & cycle_rows["component_id"].eq(cycle_id)
            ]
            usable_direct = direct.loc[usable.reindex(direct.index)]
            if usable_direct.empty:
                grouped = cycle_rows.loc[
                    cycle_rows["component_type"].eq("cycle_group")
                    & cycle_rows["component_id"]
                    .str.split("+")
                    .map(lambda members: cycle_id in members)
                ]
                score = np.nan
                status = "unavailable"
                reason = (
                    "cycle_not_individually_identifiable"
                    if not grouped.empty
                    else "cycle_component_not_available"
                )
                evidence = "low"
            elif cycle_denominator <= 0.0:
                score = np.nan
                status = "unavailable"
                reason = "cycle_zero_absolute_contribution_denominator"
                evidence = "low"
            else:
                score = (
                    float(usable_direct["point_contribution"].sum()) / cycle_denominator
                )
                status = "available"
                reason = "score_available"
                evidence = _minimum_evidence(usable_direct)
            records.append(
                _influence_record(
                    asset_id=str(asset_id),
                    horizon=int(horizon),
                    component_type="cycle",
                    component_id=cycle_id,
                    score=score,
                    status=status,
                    evidence=evidence,
                    reason=reason,
                    context=context,
                )
            )
        channel_rows = group.loc[group["component_type"].isin(_CHANNEL_COMPONENT_TYPES)]
        channel_totals: dict[str, float] = {}
        channel_evidence: dict[str, str] = {}
        for channel_id in normalized_channels:
            current = channel_rows.loc[channel_rows["component_id"].eq(channel_id)]
            usable_current = current.loc[usable.reindex(current.index)]
            if not usable_current.empty:
                channel_totals[channel_id] = float(
                    usable_current["point_contribution"].sum()
                )
                channel_evidence[channel_id] = _minimum_evidence(usable_current)
        channel_denominator = float(
            sum(abs(value) for value in channel_totals.values())
        )
        for channel_id in normalized_channels:
            explicit_reason = reasons.get(channel_id)
            if explicit_reason is not None:
                score = np.nan
                status = "unavailable"
                reason = explicit_reason
                evidence = "low"
            elif channel_id not in channel_totals:
                score = np.nan
                status = "unavailable"
                reason = "channel_component_not_available"
                evidence = "low"
            elif channel_denominator <= 0.0:
                score = np.nan
                status = "unavailable"
                reason = "channel_zero_absolute_contribution_denominator"
                evidence = "low"
            else:
                score = channel_totals[channel_id] / channel_denominator
                status = "available"
                reason = "score_available"
                evidence = channel_evidence[channel_id]
            records.append(
                _influence_record(
                    asset_id=str(asset_id),
                    horizon=int(horizon),
                    component_type="channel",
                    component_id=channel_id,
                    score=score,
                    status=status,
                    evidence=evidence,
                    reason=reason,
                    context=context,
                )
            )
    output = pd.DataFrame(records, columns=M3_INFLUENCE_COLUMNS)
    type_order = output["component_type"].map({"cycle": 0, "channel": 1})
    cycle_order = (
        output["component_id"]
        .map({cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)})
        .fillna(100)
    )
    output = output.assign(_type_order=type_order, _cycle_order=cycle_order)
    return (
        output.sort_values(
            [
                "asset_id",
                "horizon_months",
                "_type_order",
                "_cycle_order",
                "component_id",
            ],
            kind="stable",
        )
        .drop(columns=["_type_order", "_cycle_order"])
        .reset_index(drop=True)
    )


def _influence_record(
    *,
    asset_id: str,
    horizon: int,
    component_type: str,
    component_id: str,
    score: float,
    status: str,
    evidence: str,
    reason: str,
    context: RunContext,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "horizon_months": horizon,
        "component_type": component_type,
        "component_id": component_id,
        "influence_score": score,
        "status": status,
        "evidence_level": evidence,
        "reason_code": reason,
        "source_stage": "m3_asset_attribution",
        "source_run_id": context.run_id,
        "source_date": context.as_of,
        "source_model_version": context.model_version,
        "source_config_hash": context.config_hash,
    }


def _load_pipeline_bundle(value: object) -> tuple[object, Path | None]:
    if isinstance(value, (str, Path)):
        supplied = Path(value)
        input_dir = supplied.parent if supplied.is_file() else supplied
        return load_cycle_pipeline_input(
            input_dir
        ), input_dir / "cycle_pipeline_input.json"
    _bundle_parts(value)
    return value, None


def _bundle_checksum(bundle: object) -> str:
    snapshot = _snapshot_memory_bundle(bundle)
    observations = snapshot.observations
    categories = snapshot.monthly_categories
    normalized_observations = [
        {
            "entity_id": str(getattr(record, "entity_id")),
            "observation_date": str(getattr(record, "observation_date")),
            "release_date": str(getattr(record, "release_date", "")),
            "vintage_date": str(getattr(record, "vintage_date", "")),
            "value": float(getattr(record, "value")),
            "unit": str(getattr(record, "unit", "")),
            "source": str(getattr(record, "source", "")),
            "retrieval_time": str(getattr(record, "retrieval_time", "")),
            "revision_number": int(getattr(record, "revision_number", 0)),
            "quality_status": str(getattr(record, "quality_status", "")),
            "vintage_kind": _vintage_value(getattr(record, "vintage_kind", None)),
        }
        for record in observations
        if getattr(record, "entity_id", None) in categories
    ]
    normalized_observations.sort(
        key=lambda record: (
            record["entity_id"],
            record["observation_date"],
            record["release_date"],
            record["vintage_date"],
            record["revision_number"],
            record["vintage_kind"],
            record["value"],
            record["unit"],
            record["source"],
            record["retrieval_time"],
            record["quality_status"],
        )
    )
    payload = {
        "monthly_categories": dict(sorted(categories.items())),
        "observations": normalized_observations,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _common_period_end(
    cycle_phase: pd.DataFrame,
    asset_returns: pd.DataFrame,
) -> pd.Timestamp:
    cycle_dates = _month_end_dates(cycle_phase["date"], name="cycle date")
    complete_cycle_dates = set(
        pd.DataFrame({"date": cycle_dates, "cycle_id": cycle_phase["cycle_id"]})
        .groupby("date")["cycle_id"]
        .nunique()
        .loc[lambda values: values.eq(len(CYCLE_IDS))]
        .index
    )
    complete_return_dates = set(
        asset_returns.groupby("date")["asset_id"]
        .nunique()
        .loc[lambda values: values.eq(len(_GOVERNED_ASSET_IDS))]
        .index
    )
    common = sorted(complete_cycle_dates.intersection(complete_return_dates))
    if not common:
        raise ValueError("cycle and governed returns have no complete common month")
    return pd.Timestamp(common[-1])


def _active_channels(
    channel_states: pd.DataFrame,
    cycle_innovations: pd.DataFrame,
    *,
    period_end: pd.Timestamp,
    horizon_months: int,
    min_training_count: int,
) -> tuple[tuple[str, ...], dict[str, str]]:
    attribution_dates = pd.date_range(
        end=period_end,
        periods=horizon_months,
        freq="ME",
    )
    cycle_wide = cycle_innovations.pivot(
        index="date", columns="cycle_id", values="innovation"
    ).reindex(columns=list(CYCLE_IDS))
    complete_cycle_history = cycle_wide.index[
        np.isfinite(cycle_wide.to_numpy(dtype="float64")).all(axis=1)
    ]
    active: list[str] = []
    unavailable: dict[str, str] = {}
    for channel_id in RESEARCH_CHANNEL_IDS:
        channel = (
            channel_states.loc[
                channel_states["channel_id"].eq(channel_id), ["date", "innovation"]
            ]
            .set_index("date")["innovation"]
            .sort_index()
        )
        window = channel.reindex(attribution_dates)
        if not np.isfinite(window.to_numpy(dtype="float64")).all():
            unavailable[channel_id] = "channel_missing_in_attribution_window"
            continue
        history_dates = complete_cycle_history[
            complete_cycle_history < attribution_dates[0]
        ]
        history = channel.reindex(history_dates)
        finite_history = int(np.isfinite(history.to_numpy(dtype="float64")).sum())
        if finite_history < min_training_count:
            unavailable[channel_id] = "channel_insufficient_attribution_history"
            continue
        active.append(channel_id)
    if not active:
        raise ValueError("no research channels satisfy the attribution window gates")
    return tuple(active), unavailable


def _slice_dates(values: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    return values.loc[pd.to_datetime(values["date"]).isin(dates)].copy()


def _attribution_intervals(
    contribution: object,
    stage1: object,
    stage2: object,
    cycle_uncertainty: pd.DataFrame,
    channel_uncertainty: pd.DataFrame,
    *,
    period_end: pd.Timestamp,
    horizons: tuple[int, ...],
    draw_count: int,
    seed: int,
) -> AttributionIntervalResult:
    interval_frames: list[pd.DataFrame] = []
    diagnostic_frames: list[pd.DataFrame] = []
    draw_frames: list[pd.DataFrame] = []
    residual_history = contribution.components.loc[
        :,
        ["date", "asset_id", "component_type", "component_id", "contribution"],
    ].rename(columns={"contribution": "value"})
    for horizon in horizons:
        dates = pd.date_range(end=period_end, periods=horizon, freq="ME")
        contribution_slice = SimpleNamespace(
            components=_slice_dates(contribution.components, dates),
            paths=_slice_dates(contribution.paths, dates),
        )
        result = estimate_attribution_intervals(
            contribution_slice,
            stage1_paths=_slice_dates(stage1.paths, dates),
            stage1_covariance=_slice_dates(stage1.covariance, dates),
            stage2_components=_slice_dates(stage2.components, dates),
            stage2_covariance=_slice_dates(stage2.covariance, dates),
            cycle_uncertainty=_slice_dates(cycle_uncertainty, dates),
            channel_uncertainty=_slice_dates(channel_uncertainty, dates),
            residual_history=residual_history,
            period_start=dates[0],
            period_end=dates[-1],
            horizon_months=horizon,
            return_basis="absolute",
            config=UncertaintyConfig(
                draw_count=draw_count,
                seed=seed,
                min_effective_samples=12,
            ),
        )
        interval_frames.append(result.intervals)
        diagnostic_frames.append(result.diagnostics)
        draw_frames.append(result.draws)
    return AttributionIntervalResult(
        intervals=pd.concat(interval_frames, ignore_index=True),
        diagnostics=pd.concat(diagnostic_frames, ignore_index=True),
        draws=_safe_draw_concat(draw_frames),
        draw_count=draw_count,
        seed=seed,
    )


def _safe_draw_concat(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [
        frame.loc[:, list(ATTRIBUTION_DRAW_COLUMNS)].copy()
        for frame in frames
        if not frame.empty and not frame.dropna(how="all").empty
    ]
    if not nonempty:
        return pd.DataFrame(
            {
                "asset_id": pd.Series(dtype="object"),
                "period_start": pd.Series(dtype="datetime64[ns]"),
                "period_end": pd.Series(dtype="datetime64[ns]"),
                "horizon_months": pd.Series(dtype="int64"),
                "return_basis": pd.Series(dtype="object"),
                "draw": pd.Series(dtype="int64"),
                "component_type": pd.Series(dtype="object"),
                "component_id": pd.Series(dtype="object"),
                "contribution": pd.Series(dtype="float64"),
                "target_return": pd.Series(dtype="float64"),
            },
            columns=ATTRIBUTION_DRAW_COLUMNS,
        )
    for frame in nonempty:
        frame["period_start"] = pd.to_datetime(frame["period_start"])
        frame["period_end"] = pd.to_datetime(frame["period_end"])
        frame["horizon_months"] = frame["horizon_months"].astype("int64")
        frame["draw"] = frame["draw"].astype("int64")
        frame["contribution"] = frame["contribution"].astype("float64")
        frame["target_return"] = frame["target_return"].astype("float64")
    return pd.concat(nonempty, ignore_index=True)


def _aggregate_attribution_status(
    diagnostics: pd.DataFrame,
    unavailable_channels: Mapping[str, str],
) -> str:
    statuses = set(diagnostics["status"])
    if statuses == {"unavailable"}:
        return "unavailable"
    if unavailable_channels or statuses != {"available"}:
        return "partial"
    return "available"


def _channel_state_audit_payload(values: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in values.loc[:, list(RESEARCH_CHANNEL_STATE_COLUMNS)].itertuples(
        index=False
    ):
        records.append(
            {
                "date": pd.Timestamp(row.date).date().isoformat(),
                "channel_id": row.channel_id,
                "state": None if pd.isna(row.state) else float(row.state),
                "innovation": (
                    None if pd.isna(row.innovation) else float(row.innovation)
                ),
                "uncertainty": (
                    None if pd.isna(row.uncertainty) else float(row.uncertainty)
                ),
                "member_count": int(row.member_count),
                "vintage_kind": row.vintage_kind,
                "status": row.status,
                "status_reason": row.status_reason,
            }
        )
    return records


def _require_source_products(source_run: Path) -> None:
    for relative in _REQUIRED_SOURCE_FILES:
        source = source_run / relative
        if not source.is_file():
            raise FileNotFoundError(f"source research run is missing {relative}")
    registries = source_run / "registries"
    if not registries.is_dir():
        raise FileNotFoundError("source research run is missing registries/")


def _copy_source_products(source_run: Path, staging_dir: Path) -> None:
    for relative in _SOURCE_AUDIT_FILES:
        shutil.copy2(source_run / relative, staging_dir / relative)
    shutil.copytree(source_run / "registries", staging_dir / "registries")


def _surface_payloads(source: pd.DataFrame) -> list[dict[str, object]]:
    if tuple(source.columns) != CYCLE_ASSET_SURFACE_COLUMNS:
        raise ValueError("source cycle asset surface columns do not match contract")
    payloads: list[dict[str, object]] = []
    for row in source.to_dict(orient="records"):
        current_point_value = row["current_point_json"]
        payloads.append(
            {
                "asset_id": row["asset_id"],
                "asset_label": row["asset_label"],
                "cycle_x": row["cycle_x"],
                "cycle_y": row["cycle_y"],
                "metric": row["metric"],
                "horizon_months": int(row["horizon_months"]),
                "scenario_id": row["scenario_id"],
                "window_months": int(row["window_months"]),
                "grid_size": int(row["grid_size"]),
                "status": row["status"],
                "estimator_version": row["estimator_version"],
                "observations": json.loads(row["observations_json"]),
                "grid": json.loads(row["grid_json"]),
                "current_point": (
                    None
                    if pd.isna(current_point_value)
                    else json.loads(current_point_value)
                ),
                "future_path": json.loads(row["future_path_json"]),
                "evidence": {
                    "sample_count": int(row["sample_count"]),
                    "bandwidth": (
                        None if pd.isna(row["bandwidth"]) else float(row["bandwidth"])
                    ),
                    "oos_score": (
                        None if pd.isna(row["oos_score"]) else float(row["oos_score"])
                    ),
                    "identifiable": bool(row["identifiable"]),
                    "reason": row["reason"],
                },
            }
        )
    return payloads


def _copy_snapshot_file(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)


def _snapshot_stable_file(
    source: Path,
    destination: Path,
    *,
    label: str,
) -> Path:
    resolved_source = source.resolve(strict=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum_before = sha256_file(resolved_source)
    _copy_snapshot_file(resolved_source, destination)
    checksum_after = sha256_file(resolved_source)
    snapshot_checksum = sha256_file(destination)
    if not (checksum_before == checksum_after == snapshot_checksum):
        raise ValueError(f"{label} changed during snapshot")
    return destination


def _snapshot_source_run(
    source_run: Path,
    snapshot_root: Path,
) -> Path:
    resolved_source = source_run.resolve(strict=True)
    source_manifest = load_manifest(resolved_source)
    verify_manifest(resolved_source, expected=source_manifest)
    snapshot_run = snapshot_root / "source" / source_manifest.run_id
    snapshot_run.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(resolved_source, snapshot_run)
    verify_manifest(snapshot_run, expected=source_manifest)
    return snapshot_run


def _snapshot_bundle_path(
    supplied: str | Path,
    snapshot_root: Path,
) -> Path:
    source = Path(supplied).resolve(strict=True)
    source_file = source if source.is_file() else source / "cycle_pipeline_input.json"
    return _snapshot_stable_file(
        source_file,
        snapshot_root / "bundle" / "cycle_pipeline_input.json",
        label="cycle pipeline input",
    )


def _publish_research_attribution_release_from_snapshots(
    *,
    source_research_run: str | Path,
    pipeline_input_bundle: object,
    returns_path: str | Path,
    registry_bundle: RegistryBundle,
    product_root: str | Path,
    horizons: tuple[int, ...] = (3, 6, 12),
    stage1_min_training_count: int = 36,
    stage2_min_asset_training_count: int = 18,
    stage2_min_parent_training_count: int = 24,
    draw_count: int = 2_000,
    seed: int = 0,
    created_at: datetime | None = None,
) -> ResearchAttributionReleaseResult:
    """Publish one immutable retrospective-only absolute-basis M3 release."""

    if horizons != (3, 6, 12):
        raise ValueError("research attribution horizons must be exactly 3, 6, and 12")
    source_run = Path(source_research_run).resolve(strict=True)
    source_manifest = load_manifest(source_run)
    verify_manifest(source_run, expected=source_manifest)
    _require_source_products(source_run)
    cycle_path = source_run / "cycle_phase_vintage.parquet"
    returns_source = Path(returns_path).resolve(strict=True)
    bundle, bundle_path = _load_pipeline_bundle(pipeline_input_bundle)
    cycle_phase = pd.read_parquet(cycle_path)
    if "vintage" in cycle_phase and set(cycle_phase["vintage"]) != {"pseudo_vintage"}:
        raise ValueError("source cycle evidence must be pseudo_vintage")
    cycle_innovations = build_cycle_innovations(cycle_phase)
    channel_states = build_research_channel_states(bundle)
    asset_returns = build_absolute_asset_returns(returns_source, registry_bundle)
    period_end = _common_period_end(cycle_phase, asset_returns)
    active_channels, unavailable_channels = _active_channels(
        channel_states,
        cycle_innovations,
        period_end=period_end,
        horizon_months=max(horizons),
        min_training_count=stage1_min_training_count,
    )
    cycle_innovations = cycle_innovations.loc[
        cycle_innovations["date"].le(period_end)
    ].reset_index(drop=True)
    active_channel_innovations = channel_states.loc[
        channel_states["channel_id"].isin(active_channels)
        & channel_states["date"].le(period_end),
        ["date", "channel_id", "innovation"],
    ].reset_index(drop=True)
    asset_returns = asset_returns.loc[asset_returns["date"].le(period_end)].reset_index(
        drop=True
    )
    hierarchy = build_research_asset_hierarchy(
        registry_bundle,
        _GOVERNED_ASSET_IDS,
    )
    stage1 = estimate_cycle_to_channel(
        cycle_innovations,
        active_channel_innovations,
        config=CycleToChannelConfig(
            window="expanding",
            min_training_count=stage1_min_training_count,
        ),
    )
    stage2 = estimate_channel_to_asset(
        asset_returns,
        active_channel_innovations,
        hierarchy,
        config=HierarchicalTVPConfig(
            window="expanding",
            min_asset_training_count=max(
                stage2_min_asset_training_count,
                len(active_channels) + 3,
            ),
            min_parent_training_count=max(
                stage2_min_parent_training_count,
                len(active_channels) + 3,
            ),
        ),
    )
    contribution = compose_attribution_paths(stage1.paths, stage2.components)
    cycle_uncertainty = cycle_phase.loc[:, ["date", "cycle_id", "uncertainty"]].copy()
    cycle_uncertainty["date"] = _month_end_dates(
        cycle_uncertainty["date"], name="cycle uncertainty date"
    )
    channel_uncertainty = channel_states.loc[
        channel_states["channel_id"].isin(active_channels),
        ["date", "channel_id", "uncertainty"],
    ].copy()
    intervals = _attribution_intervals(
        contribution,
        stage1,
        stage2,
        cycle_uncertainty,
        channel_uncertainty,
        period_end=period_end,
        horizons=horizons,
        draw_count=draw_count,
        seed=seed,
    )
    attribution_status = _aggregate_attribution_status(
        intervals.diagnostics,
        unavailable_channels,
    )
    config = {
        "active_channel_ids": list(active_channels),
        "benchmark_method": "leave_one_out_governed_asset_benchmark",
        "channel_ids": list(RESEARCH_CHANNEL_IDS),
        "cycle_innovation_method": "causal_first_difference_of_cycle_level",
        "current_mapping_analog_draw_count": 24,
        "current_mapping_method": CURRENT_MAPPING_METHOD_ID,
        "current_mapping_status": "retrospective_only",
        "draw_count": draw_count,
        "forecast_status": "not_published",
        "governed_channel_state_status": "not_published",
        "horizons": list(horizons),
        "period_end": period_end.date().isoformat(),
        "retrospective_only": True,
        "research_channel_state_role": "audit_sidecar",
        "return_basis": "absolute",
        "source_research_run": source_manifest.run_id,
        "stage1_min_training_count": stage1_min_training_count,
        "stage1_window": "expanding",
        "stage2_min_asset_training_count": max(
            stage2_min_asset_training_count,
            len(active_channels) + 3,
        ),
        "stage2_min_parent_training_count": max(
            stage2_min_parent_training_count,
            len(active_channels) + 3,
        ),
        "stage2_window": "expanding",
        "unavailable_channel_ids": list(unavailable_channels),
        "unavailable_channel_reasons": unavailable_channels,
        "vintage_kind": "pseudo_vintage",
    }
    input_checksums = {
        "monthly_returns_20y.parquet": sha256_file(returns_source),
        "source_manifest.json": sha256_file(source_run / "manifest.json"),
        "source_cycle_phase_vintage.parquet": sha256_file(cycle_path),
    }
    if bundle_path is not None:
        input_checksums["cycle_pipeline_input.json"] = sha256_file(bundle_path)
    else:
        input_checksums["cycle_pipeline_input_bundle"] = _bundle_checksum(bundle)
    context = RunContext.create(
        as_of=source_manifest.as_of,
        data_vintage=source_manifest.data_vintage,
        model_version=(
            f"{source_manifest.model_version}+m3-retrospective-attribution-v3"
            "+m4-retrospective-analog-v1"
        ),
        config=config,
        input_checksums=input_checksums,
        quality_summary={
            "active_channel_ids": list(active_channels),
            "asset_count": len(_GOVERNED_ASSET_IDS),
            "attribution_status": attribution_status,
            "benchmark_method": "leave_one_out_governed_asset_benchmark",
            "channel_count": len(RESEARCH_CHANNEL_IDS),
            "cycle_innovation_method": "causal_first_difference_of_cycle_level",
            "current_mapping_analog_draw_count": 24,
            "current_mapping_method": CURRENT_MAPPING_METHOD_ID,
            "current_mapping_status": "retrospective_only",
            "forecast_status": "not_published",
            "governed_channel_state_status": "not_published",
            "period_end": period_end.date().isoformat(),
            "retrospective_only": True,
            "research_channel_state_role": "audit_sidecar",
            "unavailable_channel_ids": list(unavailable_channels),
            "unavailable_channel_reasons": unavailable_channels,
            "vintage_kind": "pseudo_vintage",
            "vintage_status": "retrospective_only",
        },
        created_at=created_at or datetime.now(timezone.utc),
    )
    cycle_states = cycle_phase.loc[:, list(_CYCLE_STATE_COLUMNS)].copy()
    source_surface = pd.read_parquet(source_run / "cycle_asset_surface.parquet")
    surface_product = build_cycle_asset_surface_product(
        _surface_payloads(source_surface),
        context=context,
    )
    product = build_asset_attribution(intervals, context=context)
    influence = build_m3_influence(
        product,
        context=context,
        unavailable_channel_reasons=unavailable_channels,
    )
    current_cycle_phase = cycle_phase.copy(deep=True)
    current_cycle_phase["date"] = _month_end_dates(
        current_cycle_phase["date"],
        name="current mapping cycle date",
    )
    current_cycle_phase = current_cycle_phase.loc[
        current_cycle_phase["date"].le(period_end)
    ].reset_index(drop=True)
    current_mapping = build_research_current_mapping(
        context=context,
        cycle_phase=current_cycle_phase,
        channel_states=channel_states.loc[
            channel_states["date"].le(period_end)
        ].reset_index(drop=True),
        asset_returns=asset_returns,
        m3_influence=influence,
        analog_config=RetrospectiveAnalogConfig(
            draw_count=24,
            min_effective_samples=24,
        ),
    )
    published_channel_states = channel_states.loc[
        channel_states["date"].le(period_end)
    ].reset_index(drop=True)

    def write_staging(staging_dir: Path) -> None:
        _copy_source_products(source_run, staging_dir)
        build_and_write_cycle_phase_vintage(
            staging_dir,
            cycle_states,
            context=context,
        )
        write_cycle_asset_surface_product(
            staging_dir,
            surface_product,
            context=context,
        )
        write_asset_attribution(staging_dir, product, context=context)
        write_asset_mapping_current(staging_dir, current_mapping.product)
        current_mapping.analogs.to_parquet(
            staging_dir / RETROSPECTIVE_ANALOG_FILENAME,
            index=False,
        )
        (staging_dir / RESEARCH_CHANNEL_STATE_AUDIT_FILENAME).write_bytes(
            canonical_json_bytes(_channel_state_audit_payload(published_channel_states))
            + b"\n"
        )
        influence.to_parquet(staging_dir / M3_INFLUENCE_FILENAME, index=False)
        (staging_dir / RESEARCH_ATTRIBUTION_CONFIG_FILENAME).write_bytes(
            canonical_json_bytes(config) + b"\n"
        )
        (staging_dir / "source_research_run.json").write_bytes(
            canonical_json_bytes(
                {
                    "manifest_checksum": sha256_file(source_run / "manifest.json"),
                    "run_id": source_manifest.run_id,
                }
            )
            + b"\n"
        )

    def validate_staging(staging_dir: Path, manifest: RunManifest) -> None:
        validate_asset_attribution(
            pd.read_parquet(staging_dir / "asset_attribution.parquet"),
            pd.read_parquet(staging_dir / "asset_attribution_conservation.parquet"),
            context=manifest,
        )
        staged_channels = json.loads(
            (staging_dir / RESEARCH_CHANNEL_STATE_AUDIT_FILENAME).read_bytes()
        )
        if {str(row["channel_id"]) for row in staged_channels} != set(
            RESEARCH_CHANNEL_IDS
        ):
            raise ValueError(
                "research channel state lost the fixed six-channel universe"
            )
        staged_influence = pd.read_parquet(staging_dir / M3_INFLUENCE_FILENAME)
        if tuple(staged_influence.columns) != M3_INFLUENCE_COLUMNS:
            raise ValueError("m3 influence columns do not match the public contract")
        expected_rows = (
            len(_GOVERNED_ASSET_IDS)
            * len(horizons)
            * (len(CYCLE_IDS) + len(RESEARCH_CHANNEL_IDS))
        )
        if len(staged_influence) != expected_rows:
            raise ValueError("m3 influence does not retain complete coverage")
        validate_asset_mapping_current(
            pd.read_parquet(staging_dir / "asset_mapping_current.parquet"),
            snapshot=current_mapping.snapshot,
            distribution=current_mapping.distribution,
            transferability=current_mapping.transferability,
            weight_ranges=current_mapping.weight_ranges,
            influence=influence,
        )
        staged_analogs = pd.read_parquet(staging_dir / RETROSPECTIVE_ANALOG_FILENAME)
        if tuple(staged_analogs.columns) != tuple(current_mapping.analogs.columns):
            raise ValueError("retrospective analog columns changed during staging")
        if len(staged_analogs) != 24:
            raise ValueError("retrospective release must retain 24 analog paths")

    manifest = publish_run(
        Path(product_root),
        context,
        write_staging=write_staging,
        validate_staging=validate_staging,
    )
    run_dir = Path(product_root) / "runs" / manifest.run_id
    return ResearchAttributionReleaseResult(
        manifest=manifest,
        run_dir=run_dir,
        period_end=period_end.date(),
        asset_count=len(_GOVERNED_ASSET_IDS),
        channel_count=len(RESEARCH_CHANNEL_IDS),
    )


def publish_research_attribution_release(
    *,
    source_research_run: str | Path,
    pipeline_input_bundle: object,
    returns_path: str | Path,
    registry_bundle: RegistryBundle,
    product_root: str | Path,
    horizons: tuple[int, ...] = (3, 6, 12),
    stage1_min_training_count: int = 36,
    stage2_min_asset_training_count: int = 18,
    stage2_min_parent_training_count: int = 24,
    draw_count: int = 2_000,
    seed: int = 0,
    created_at: datetime | None = None,
) -> ResearchAttributionReleaseResult:
    """Snapshot all external files before modeling and immutable publication."""

    memory_bundle_snapshot = (
        None
        if isinstance(pipeline_input_bundle, (str, Path))
        else _snapshot_memory_bundle(pipeline_input_bundle)
    )
    with tempfile.TemporaryDirectory(prefix="m3-research-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        source_snapshot = _snapshot_source_run(
            Path(source_research_run),
            snapshot_root,
        )
        returns_snapshot = _snapshot_stable_file(
            Path(returns_path),
            snapshot_root / "returns" / "monthly_returns.parquet",
            label="monthly returns",
        )
        bundle_snapshot: object
        if isinstance(pipeline_input_bundle, (str, Path)):
            bundle_snapshot = _snapshot_bundle_path(
                pipeline_input_bundle,
                snapshot_root,
            )
        else:
            bundle_snapshot = memory_bundle_snapshot
        return _publish_research_attribution_release_from_snapshots(
            source_research_run=source_snapshot,
            pipeline_input_bundle=bundle_snapshot,
            returns_path=returns_snapshot,
            registry_bundle=registry_bundle,
            product_root=product_root,
            horizons=horizons,
            stage1_min_training_count=stage1_min_training_count,
            stage2_min_asset_training_count=stage2_min_asset_training_count,
            stage2_min_parent_training_count=stage2_min_parent_training_count,
            draw_count=draw_count,
            seed=seed,
            created_at=created_at,
        )


__all__ = [
    "M3_INFLUENCE_FILENAME",
    "RESEARCH_ATTRIBUTION_CONFIG_FILENAME",
    "RESEARCH_CHANNEL_CATEGORY_MAP",
    "RESEARCH_CHANNEL_IDS",
    "RESEARCH_CHANNEL_STATE_AUDIT_FILENAME",
    "RESEARCH_CHANNEL_STATE_COLUMNS",
    "ResearchAttributionReleaseResult",
    "build_absolute_asset_returns",
    "build_cycle_innovations",
    "build_m3_influence",
    "build_research_asset_hierarchy",
    "build_research_channel_states",
    "publish_research_attribution_release",
]
