"""Independent verification and publication orchestration for current mapping."""

from __future__ import annotations

from dataclasses import dataclass
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from seven_cycle_platform.mapping.distribution import CurrentDistributionResult
from seven_cycle_platform.mapping.features import CurrentFeatureSnapshot
from seven_cycle_platform.mapping.transferability import TransferabilityResult
from seven_cycle_platform.mapping.weights import WeightRangeResult
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_COLUMNS,
    ASSET_MAPPING_CURRENT_SCHEMA,
    AssetMappingCurrentProduct,
    build_asset_mapping_current,
    validate_asset_mapping_current,
    write_asset_mapping_current,
)
from seven_cycle_platform.types import EvidenceLevel, MappingStatus, ReleaseStatus


_RETURN_BASES = ("absolute", "excess")
_EXPECTED_CYCLES = tuple(f"C{position}" for position in range(1, 8))
_MAPPING_ELIGIBLE = frozenset(
    {MappingStatus.FORMAL.value, MappingStatus.CONDITIONAL.value}
)


def _count(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return numeric


@dataclass(frozen=True)
class CurrentMappingVerificationReport:
    """Frozen release decision and affected/live coverage counts."""

    release_status: ReleaseStatus
    total_row_count: int
    live_row_count: int
    partial_row_count: int
    total_asset_count: int
    live_asset_count: int
    affected_asset_count: int
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.release_status, ReleaseStatus):
            raise TypeError("release_status must be a ReleaseStatus")
        for field_name in (
            "total_row_count",
            "live_row_count",
            "partial_row_count",
            "total_asset_count",
            "live_asset_count",
            "affected_asset_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _count(getattr(self, field_name), name=field_name),
            )
        if self.live_row_count + self.partial_row_count != self.total_row_count:
            raise ValueError("live and partial row counts must cover every row")
        if self.live_asset_count > self.total_asset_count:
            raise ValueError("live_asset_count cannot exceed total_asset_count")
        if self.affected_asset_count > self.total_asset_count:
            raise ValueError("affected_asset_count cannot exceed total_asset_count")
        if isinstance(self.issue_codes, str):
            raise TypeError("issue_codes must be an iterable of strings")
        issues = tuple(sorted(set(self.issue_codes)))
        if any(not isinstance(issue, str) or not issue for issue in issues):
            raise ValueError("issue_codes must contain non-empty strings")
        object.__setattr__(self, "issue_codes", issues)


@dataclass(frozen=True)
class CurrentMappingPublicationResult:
    """Frozen Task 23 integration result without exposing an unwritten product."""

    report: CurrentMappingVerificationReport
    written_path: Path | None

    def __post_init__(self) -> None:
        if not isinstance(self.report, CurrentMappingVerificationReport):
            raise TypeError("report must be a CurrentMappingVerificationReport")
        if self.report.release_status is ReleaseStatus.BLOCKED:
            if self.written_path is not None:
                raise ValueError("blocked publication cannot expose a written path")
        elif not isinstance(self.written_path, Path):
            raise TypeError("live or partial publication requires a written Path")

    @property
    def release_status(self) -> ReleaseStatus:
        return self.report.release_status

    @property
    def live_asset_count(self) -> int:
        return self.report.live_asset_count

    @property
    def affected_asset_count(self) -> int:
        return self.report.affected_asset_count


def _product_frame(product: object) -> pd.DataFrame:
    if isinstance(product, AssetMappingCurrentProduct):
        return product.mapping
    if isinstance(product, pd.DataFrame):
        return product.copy(deep=True)
    raise TypeError("product must be AssetMappingCurrentProduct or pandas DataFrame")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _parse_json(value: object, *, column: str) -> object:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{column} must contain non-empty canonical JSON")
    parsed = json.loads(value)
    if value != _canonical_json(parsed):
        raise ValueError(f"{column} is not canonical JSON")
    return parsed


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    missing = pd.isna(value)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _safe_dimensions(
    distribution: object,
) -> tuple[set[tuple[str, int]], set[str]]:
    if not isinstance(distribution, CurrentDistributionResult):
        return set(), set()
    try:
        summary = distribution.summary
    except (AttributeError, TypeError, ValueError):
        return set(), set()
    required = {"asset_id", "horizon_months"}
    if not isinstance(summary, pd.DataFrame) or not required.issubset(summary.columns):
        return set(), set()
    dimensions: set[tuple[str, int]] = set()
    assets: set[str] = set()
    for asset_id, horizon_months in summary[["asset_id", "horizon_months"]].itertuples(
        index=False, name=None
    ):
        if isinstance(asset_id, str) and isinstance(
            horizon_months, (Integral, np.integer)
        ):
            dimensions.add((asset_id, int(horizon_months)))
            assets.add(asset_id)
    return dimensions, assets


def _blocked_report_from_inputs(
    distribution: object,
    *,
    issue_code: str,
) -> CurrentMappingVerificationReport:
    dimensions, assets = _safe_dimensions(distribution)
    return CurrentMappingVerificationReport(
        release_status=ReleaseStatus.BLOCKED,
        total_row_count=len(dimensions),
        live_row_count=0,
        partial_row_count=len(dimensions),
        total_asset_count=len(assets),
        live_asset_count=0,
        affected_asset_count=len(assets),
        issue_codes=(issue_code,),
    )


def _report_from_frame(
    frame: pd.DataFrame,
    *,
    issues: set[str],
) -> CurrentMappingVerificationReport:
    if {
        "asset_id",
        "publication_status",
    }.issubset(frame.columns):
        assets = {
            value for value in frame["asset_id"].tolist() if isinstance(value, str)
        }
        live_mask = frame["publication_status"].eq("live")
        partial_mask = frame["publication_status"].eq("partial")
        unclassified_count = len(frame) - int(live_mask.sum()) - int(partial_mask.sum())
        if unclassified_count:
            issues.add("publication_status_invalid")
            partial_mask = ~live_mask
        live_assets = set(frame.loc[live_mask, "asset_id"]).intersection(assets)
        affected_assets = set(frame.loc[partial_mask, "asset_id"]).intersection(assets)
        live_rows = int(live_mask.sum())
        partial_rows = len(frame) - live_rows
    else:
        assets = set()
        live_assets = set()
        affected_assets = set()
        live_rows = 0
        partial_rows = len(frame)
        issues.add("publication_dimensions_missing")
    if issues:
        live_assets = set()
        affected_assets = set(assets)
        live_rows = 0
        partial_rows = len(frame)
        release_status = ReleaseStatus.BLOCKED
    elif live_rows == 0:
        release_status = ReleaseStatus.BLOCKED
    elif live_rows == len(frame):
        release_status = ReleaseStatus.LIVE
    else:
        release_status = ReleaseStatus.PARTIAL
    return CurrentMappingVerificationReport(
        release_status=release_status,
        total_row_count=len(frame),
        live_row_count=live_rows,
        partial_row_count=partial_rows,
        total_asset_count=len(assets),
        live_asset_count=len(live_assets),
        affected_asset_count=len(affected_assets),
        issue_codes=tuple(issues),
    )


def _verify_arrow_surface(frame: pd.DataFrame, issues: set[str]) -> None:
    if tuple(frame.columns) != ASSET_MAPPING_CURRENT_COLUMNS:
        issues.add("schema_columns_invalid")
        return
    try:
        arrays = [
            pa.array(frame[field.name].tolist(), type=field.type, from_pandas=True)
            for field in ASSET_MAPPING_CURRENT_SCHEMA
        ]
        table = pa.Table.from_arrays(arrays, schema=ASSET_MAPPING_CURRENT_SCHEMA)
    except (TypeError, ValueError, pa.ArrowException):
        issues.add("schema_types_invalid")
        return
    if table.schema != ASSET_MAPPING_CURRENT_SCHEMA:
        issues.add("schema_types_invalid")


def _verify_probability_quantile_risk(row: pd.Series, issues: set[str]) -> None:
    for basis in _RETURN_BASES:
        status = row.get(f"{basis}_distribution_status")
        metrics = [
            row.get(f"{basis}_{name}")
            for name in (
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
        ]
        if status == "unavailable":
            if not all(_is_missing(value) for value in metrics):
                issues.add("unavailable_distribution_metrics_present")
            continue
        if status != "available":
            issues.add("distribution_status_invalid")
            continue
        try:
            probabilities = np.asarray(metrics[:3], dtype="float64")
            quantiles = np.asarray(metrics[3:8], dtype="float64")
            expected_return = float(metrics[8])
            volatility = float(metrics[9])
            var95 = float(metrics[10])
            cvar95 = float(metrics[11])
            drawdowns = np.asarray(metrics[12:15], dtype="float64")
        except (TypeError, ValueError):
            issues.add("distribution_numeric_invalid")
            continue
        if (
            not np.isfinite(probabilities).all()
            or bool(((probabilities < 0.0) | (probabilities > 1.0)).any())
            or not np.isclose(probabilities.sum(), 1.0, atol=1e-10, rtol=1e-10)
        ):
            issues.add("calibrated_probabilities_invalid")
        if (
            not np.isfinite(quantiles).all()
            or bool((np.diff(quantiles) < 0.0).any())
            or not np.isfinite(expected_return)
        ):
            issues.add("return_quantiles_invalid")
        if (
            not np.isfinite([volatility, var95, cvar95]).all()
            or volatility < 0.0
            or var95 < 0.0
            or cvar95 < var95
        ):
            issues.add("risk_metrics_invalid")
        if (
            not np.isfinite(drawdowns).all()
            or bool(((drawdowns < 0.0) | (drawdowns > 1.0)).any())
            or bool((np.diff(drawdowns) < 0.0).any())
        ):
            issues.add("drawdown_quantiles_invalid")


def _verify_influence(row: pd.Series, issues: set[str]) -> None:
    entries: list[dict[str, object]] = []
    for column, component_type in (
        ("cycle_influence_json", "cycle"),
        ("channel_influence_json", "channel"),
    ):
        try:
            parsed = _parse_json(row.get(column), column=column)
        except (TypeError, ValueError, json.JSONDecodeError):
            issues.add("influence_json_invalid")
            continue
        if not isinstance(parsed, list) or not parsed:
            issues.add("influence_json_invalid")
            continue
        for entry in parsed:
            if not isinstance(entry, dict):
                issues.add("influence_json_invalid")
                continue
            if (
                entry.get("asset_id") != row.get("asset_id")
                or entry.get("horizon_months") != row.get("horizon_months")
                or entry.get("component_type") != component_type
                or entry.get("source_stage") != "m3_asset_attribution"
                or entry.get("source_run_id") != row.get("influence_run_id")
                or entry.get("source_model_version")
                != row.get("influence_model_version")
                or entry.get("source_config_hash") != row.get("influence_config_hash")
            ):
                issues.add("influence_provenance_invalid")
            status = entry.get("status")
            score = entry.get("influence_score")
            if status == "available":
                if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not np.isfinite(float(score))
                    or not -1.0 <= float(score) <= 1.0
                ):
                    issues.add("influence_score_invalid")
            elif status == "unavailable":
                if score is not None or not entry.get("reason_code"):
                    issues.add("influence_unavailable_invalid")
            else:
                issues.add("influence_status_invalid")
            entries.append(entry)
        component_ids = [entry.get("component_id") for entry in parsed]
        if component_type == "cycle" and component_ids != list(_EXPECTED_CYCLES):
            issues.add("cycle_influence_coverage_invalid")
        if component_type == "channel" and component_ids != sorted(component_ids):
            issues.add("channel_influence_order_invalid")
    if not entries:
        return
    statuses = [entry.get("status") for entry in entries]
    expected_status = (
        "available"
        if all(status == "available" for status in statuses)
        else "unavailable"
        if all(status == "unavailable" for status in statuses)
        else "partial"
    )
    if row.get("influence_status") != expected_status:
        issues.add("influence_aggregate_status_invalid")
    levels = [entry.get("evidence_level") for entry in entries]
    rank = {"low": 0, "medium": 1, "high": 2}
    if any(level not in rank for level in levels):
        issues.add("influence_evidence_invalid")
    else:
        expected_level = min(levels, key=rank.__getitem__)
        if expected_status != "available":
            expected_level = "low"
        if row.get("influence_evidence_level") != expected_level:
            issues.add("influence_evidence_invalid")


def _freshness_by_asset(snapshot: object) -> dict[str, tuple[int, str]]:
    if not isinstance(snapshot, CurrentFeatureSnapshot):
        raise TypeError("snapshot must be a CurrentFeatureSnapshot")
    asset_ids = {
        feature.entity_id
        for feature in snapshot.features
        if feature.entity_id is not None
    }
    values: dict[str, tuple[int, str]] = {}
    for asset_id in asset_ids:
        stale_count = sum(
            1
            for feature in snapshot.features
            if (feature.entity_id is None or feature.entity_id == asset_id)
            and not feature.freshness.is_fresh
        )
        values[asset_id] = (stale_count, "fresh" if stale_count == 0 else "stale")
    return values


def _expected_evidence_level(row: pd.Series) -> str:
    if (
        row.get("range_status") == "available"
        and row.get("transferability_status") == MappingStatus.FORMAL.value
        and row.get("influence_status") == "available"
        and row.get("influence_evidence_level") == EvidenceLevel.HIGH.value
    ):
        return EvidenceLevel.HIGH.value
    if (
        row.get("range_status") == "available"
        and row.get("transferability_status") in _MAPPING_ELIGIBLE
        and row.get("influence_status") != "unavailable"
    ):
        return EvidenceLevel.MEDIUM.value
    return EvidenceLevel.LOW.value


def _verify_freshness_weight_and_status(
    frame: pd.DataFrame,
    *,
    snapshot: object,
    weight_ranges: object,
    issues: set[str],
) -> None:
    try:
        freshness = _freshness_by_asset(snapshot)
    except (TypeError, ValueError, AttributeError):
        issues.add("snapshot_freshness_invalid")
        return
    if not isinstance(weight_ranges, WeightRangeResult):
        issues.add("weight_source_invalid")
        return
    try:
        source_weights = weight_ranges.summary.set_index(["asset_id", "horizon_months"])
    except (AttributeError, KeyError, ValueError):
        issues.add("weight_source_invalid")
        return
    for _, row in frame.iterrows():
        asset_id = row.get("asset_id")
        horizon = row.get("horizon_months")
        if asset_id not in freshness:
            issues.add("snapshot_asset_alignment_invalid")
            continue
        stale_count, freshness_status = freshness[asset_id]
        if (
            row.get("stale_feature_count") != stale_count
            or row.get("freshness_status") != freshness_status
        ):
            issues.add("freshness_derivation_invalid")
        try:
            source = source_weights.loc[(asset_id, horizon)]
        except KeyError:
            issues.add("weight_dimension_alignment_invalid")
            continue
        source_available = (
            str(source["range_status"]) == "available"
            and not _is_missing(source["min_weight"])
            and not _is_missing(source["max_weight"])
        )
        distribution_available = (
            row.get("absolute_distribution_status") == "available"
            and row.get("excess_distribution_status") == "available"
        )
        transferability_eligible = row.get("transferability_status") in (
            _MAPPING_ELIGIBLE
        )
        expected_publish = bool(
            source_available
            and distribution_available
            and transferability_eligible
            and freshness_status == "fresh"
        )
        actual_publish = row.get("range_status") == "available"
        if actual_publish != expected_publish:
            issues.add("weight_publication_gate_invalid")
        if actual_publish:
            try:
                if not np.isclose(
                    float(row.get("published_min_weight")),
                    float(source["min_weight"]),
                    atol=0.0,
                    rtol=0.0,
                ) or not np.isclose(
                    float(row.get("published_max_weight")),
                    float(source["max_weight"]),
                    atol=0.0,
                    rtol=0.0,
                ):
                    issues.add("published_weight_value_invalid")
            except (TypeError, ValueError):
                issues.add("published_weight_value_invalid")
        elif not _is_missing(row.get("published_min_weight")) or not _is_missing(
            row.get("published_max_weight")
        ):
            issues.add("suppressed_weight_present")

        expected_mapping_status = (
            MappingStatus.UNAVAILABLE.value
            if freshness_status == "stale" or not distribution_available
            else row.get("transferability_status")
        )
        if row.get("mapping_status") != expected_mapping_status:
            issues.add("mapping_status_invalid")
        expected_publication = (
            "live"
            if actual_publish and row.get("influence_status") == "available"
            else "partial"
        )
        if row.get("publication_status") != expected_publication:
            issues.add("publication_status_invalid")
        if row.get("evidence_level") != _expected_evidence_level(row):
            issues.add("evidence_level_invalid")


def _verify_no_lookahead_and_provenance(
    frame: pd.DataFrame,
    issues: set[str],
) -> None:
    required = (
        "run_id",
        "as_of",
        "data_vintage",
        "model_version",
        "snapshot_config_hash",
        "distribution_config_hash",
        "transferability_config_hash",
        "weight_config_hash",
        "influence_source_stage",
        "influence_run_id",
        "influence_source_date",
        "influence_model_version",
        "influence_config_hash",
        "stage1_posterior_date",
        "stage2_posterior_date",
        "forecast_origin",
        "created_at",
    )
    if any(column not in frame.columns for column in required):
        issues.add("provenance_columns_missing")
        return
    if any(frame[column].nunique(dropna=False) != 1 for column in required):
        issues.add("provenance_not_constant")
    for _, row in frame.iterrows():
        try:
            as_of = pd.Timestamp(row["as_of"]).date()
            dates = {
                "data_vintage": pd.Timestamp(row["data_vintage"]).date(),
                "influence_source_date": pd.Timestamp(
                    row["influence_source_date"]
                ).date(),
                "stage1_posterior_date": pd.Timestamp(
                    row["stage1_posterior_date"]
                ).date(),
                "stage2_posterior_date": pd.Timestamp(
                    row["stage2_posterior_date"]
                ).date(),
                "forecast_origin": pd.Timestamp(row["forecast_origin"]).date(),
                "policy_date": pd.Timestamp(row["policy_date"]).date(),
            }
        except (TypeError, ValueError):
            issues.add("provenance_dates_invalid")
            continue
        if (
            any(
                value > as_of
                for name, value in dates.items()
                if name != "forecast_origin"
            )
            or dates["forecast_origin"] != as_of
        ):
            issues.add("no_lookahead_invalid")
        if row.get("influence_source_stage") != "m3_asset_attribution":
            issues.add("m3_dependency_invalid")


def verify_current_mapping(
    product: object,
    *,
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
    influence: pd.DataFrame,
) -> CurrentMappingVerificationReport:
    """Independently verify the product and derive its release status."""

    issues: set[str] = set()
    try:
        frame = _product_frame(product)
    except (TypeError, ValueError):
        return _blocked_report_from_inputs(
            distribution,
            issue_code="product_type_invalid",
        )
    _verify_arrow_surface(frame, issues)
    if {"asset_id", "horizon_months"}.issubset(frame.columns):
        if frame.duplicated(["asset_id", "horizon_months"]).any():
            issues.add("product_dimensions_duplicate")
        for _, asset_rows in frame.groupby("asset_id", sort=False):
            if set(asset_rows["horizon_months"]) != {3, 6, 12}:
                issues.add("product_horizon_coverage_invalid")
    else:
        issues.add("product_dimensions_missing")
    if tuple(frame.columns) == ASSET_MAPPING_CURRENT_COLUMNS:
        for _, row in frame.iterrows():
            _verify_probability_quantile_risk(row, issues)
            _verify_influence(row, issues)
        _verify_freshness_weight_and_status(
            frame,
            snapshot=snapshot,
            weight_ranges=weight_ranges,
            issues=issues,
        )
        _verify_no_lookahead_and_provenance(frame, issues)
    try:
        validate_asset_mapping_current(
            product,
            snapshot=snapshot,
            distribution=distribution,
            transferability=transferability,
            weight_ranges=weight_ranges,
            influence=influence,
        )
    except (TypeError, ValueError):
        issues.add("governed_product_validation_failed")
    return _report_from_frame(frame, issues=issues)


def _write_failure_report(
    report: CurrentMappingVerificationReport,
) -> CurrentMappingVerificationReport:
    return CurrentMappingVerificationReport(
        release_status=ReleaseStatus.BLOCKED,
        total_row_count=report.total_row_count,
        live_row_count=0,
        partial_row_count=report.total_row_count,
        total_asset_count=report.total_asset_count,
        live_asset_count=0,
        affected_asset_count=report.total_asset_count,
        issue_codes=tuple(set(report.issue_codes) | {"write_failed"}),
    )


def publish_current_mapping(
    run_dir: Path,
    *,
    snapshot: CurrentFeatureSnapshot,
    distribution: CurrentDistributionResult,
    transferability: TransferabilityResult,
    weight_ranges: WeightRangeResult,
    influence: pd.DataFrame,
) -> CurrentMappingPublicationResult:
    """Build, verify, then write only LIVE or PARTIAL current mappings."""

    try:
        product = build_asset_mapping_current(
            snapshot,
            distribution,
            transferability,
            weight_ranges,
            influence,
        )
    except Exception:
        return CurrentMappingPublicationResult(
            report=_blocked_report_from_inputs(
                distribution,
                issue_code="build_failed",
            ),
            written_path=None,
        )
    report = verify_current_mapping(
        product,
        snapshot=snapshot,
        distribution=distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        influence=influence,
    )
    if report.release_status is ReleaseStatus.BLOCKED:
        return CurrentMappingPublicationResult(report=report, written_path=None)
    try:
        written_path = write_asset_mapping_current(run_dir, product)
    except Exception:
        return CurrentMappingPublicationResult(
            report=_write_failure_report(report),
            written_path=None,
        )
    return CurrentMappingPublicationResult(
        report=report,
        written_path=written_path,
    )


run_current_mapping = publish_current_mapping


__all__ = [
    "CurrentMappingPublicationResult",
    "CurrentMappingVerificationReport",
    "publish_current_mapping",
    "run_current_mapping",
    "verify_current_mapping",
]
