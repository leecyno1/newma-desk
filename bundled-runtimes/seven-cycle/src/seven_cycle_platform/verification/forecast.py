"""Task 28 forecast product verification and atomic publication."""

from __future__ import annotations

from dataclasses import dataclass
import json
from numbers import Integral, Real
from pathlib import Path
from collections.abc import Sequence
from typing import Iterator, cast

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from seven_cycle_platform.forecast.evaluation import (
    MAPPING_MANIFEST_METADATA_KEY,
    MAPPING_REFERENCE_FILENAME,
    MappingReference,
    PromotionResult,
)
from seven_cycle_platform.forecast.assets import AssetForecastResult
from seven_cycle_platform.forecast.cycles import CycleForecastResult
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_COLUMNS,
    ASSET_MAPPING_FUTURE_FILENAME,
    ASSET_MAPPING_FUTURE_PRODUCT,
    ASSET_MAPPING_FUTURE_SCHEMA,
    CONTRIBUTION_AGGREGATION_METHOD,
    CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS,
    CONTRIBUTION_CONSERVATION_TOLERANCE,
    AssetMappingFutureProduct,
    build_asset_mapping_future,
    compute_contribution_component_contract_hash,
    mapping_manifest_metadata,
    validate_asset_mapping_future,
    write_asset_mapping_future,
    write_mapping_reference,
)
from seven_cycle_platform.products.cycle_forecast import (
    CYCLE_FORECAST_COLUMNS,
    CYCLE_FORECAST_FILENAME,
    CYCLE_FORECAST_SCHEMA,
    CycleForecastProduct,
    build_cycle_forecast,
    validate_cycle_forecast,
    write_cycle_forecast,
)
from seven_cycle_platform.storage import RunContext, RunManifest, publish_run
from seven_cycle_platform.storage.manifest import sha256_file, verify_manifest
from seven_cycle_platform.storage.run_context import canonical_json_bytes


FORECAST_FINDING_COLUMNS = (
    "check_id",
    "product",
    "status",
    "severity",
    "reason_code",
    "detail",
)
_RESULT_FIELDS = frozenset({"findings"})
_PUBLIC_CONTRIBUTION_FIELDS = frozenset(
    {
        "aggregation_method",
        "component_id",
        "component_type",
        "contribution_kind",
        "draw_count",
        "expected_contribution",
        "interval50_lower",
        "interval50_upper",
        "interval80_lower",
        "interval80_upper",
        "median",
        "scenario_id",
    }
)
_PUBLIC_BASELINE_COMPONENT_TYPES = frozenset(
    {
        "intercept",
        "benchmark",
        "channel",
        "valuation",
        "positioning",
        "control",
        "interaction",
        "event",
        "residual",
    }
)


class ForecastVerificationError(ValueError):
    """Raised when governed Task 28 verification fails."""


def _context(value: object) -> RunContext:
    if not isinstance(value, RunContext):
        raise TypeError("context must be a RunContext")
    return value


def _finding(
    check_id: str,
    product: str,
    status: str,
    severity: str,
    reason_code: str,
    detail: str,
) -> dict[str, str]:
    return {
        "check_id": check_id,
        "product": product,
        "status": status,
        "severity": severity,
        "reason_code": reason_code,
        "detail": detail,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _public_contribution_entries(
    value: object,
    *,
    name: str,
    scenario_id: str,
    contribution_kind: str,
    draw_count: int,
) -> list[dict[str, object]]:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be canonical JSON")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must be valid JSON") from error
    if value != _canonical_json(parsed) or not isinstance(parsed, list):
        raise ValueError(f"{name} must be a canonical JSON array")
    entries: list[dict[str, object]] = []
    keys: list[tuple[str, str]] = []
    for entry in parsed:
        if not isinstance(entry, dict) or set(entry) != _PUBLIC_CONTRIBUTION_FIELDS:
            raise ValueError(f"{name} entries do not match the public contract")
        component_type = entry["component_type"]
        component_id = entry["component_id"]
        if not isinstance(component_type, str) or not component_type:
            raise ValueError(f"{name} component_type is invalid")
        if not isinstance(component_id, str) or not component_id:
            raise ValueError(f"{name} component_id is invalid")
        if entry["contribution_kind"] != contribution_kind:
            raise ValueError(f"{name} contribution_kind is invalid")
        if entry["scenario_id"] != scenario_id:
            raise ValueError(f"{name} scenario provenance is invalid")
        if entry["aggregation_method"] != CONTRIBUTION_AGGREGATION_METHOD:
            raise ValueError(f"{name} aggregation method is invalid")
        entry_draw_count = entry["draw_count"]
        if (
            isinstance(entry_draw_count, bool)
            or not isinstance(entry_draw_count, Integral)
            or int(entry_draw_count) != draw_count
        ):
            raise ValueError(f"{name} draw_count is inconsistent")
        if contribution_kind == "baseline_component":
            if component_type not in _PUBLIC_BASELINE_COMPONENT_TYPES:
                raise ValueError(f"{name} baseline component_type is invalid")
        elif component_type != "scenario_shock":
            raise ValueError(f"{name} scenario shock type is invalid")
        ordered_values: list[float] = []
        for column in (
            "interval80_lower",
            "interval50_lower",
            "median",
            "interval50_upper",
            "interval80_upper",
        ):
            numeric = entry[column]
            if isinstance(numeric, bool) or not isinstance(numeric, Real):
                raise ValueError(f"{name} {column} is invalid")
            normalized = float(numeric)
            if not np.isfinite(normalized):
                raise ValueError(f"{name} {column} is invalid")
            ordered_values.append(normalized)
        if ordered_values != sorted(ordered_values):
            raise ValueError(f"{name} intervals are unordered")
        expected = entry["expected_contribution"]
        if (
            isinstance(expected, bool)
            or not isinstance(expected, Real)
            or not np.isfinite(float(expected))
        ):
            raise ValueError(f"{name} expected contribution is invalid")
        keys.append((component_type, component_id))
        entries.append(dict(entry))
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name} contains duplicate components")
    if keys != sorted(keys):
        raise ValueError(f"{name} component ordering is unstable")
    return entries


def _audit_public_contribution_surface(
    mapping_frame: pd.DataFrame,
) -> tuple[bool, str]:
    required = {
        "scenario_id",
        "asset_id",
        "horizon_months",
        "status",
        "absolute_expected_return",
        "contribution_draw_count",
        "contribution_component_contract_hash",
        "baseline_component_contribution_json",
        "channel_contribution_json",
        "scenario_contribution_json",
        "contribution_aggregation_method",
        "contribution_conservation_max_abs_error",
        "contribution_conservation_passed",
        *CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS,
    }
    missing = sorted(required - set(mapping_frame.columns))
    if missing:
        return False, f"public contribution columns are missing: {missing}"
    available_rows = 0
    for row in mapping_frame.itertuples(index=False):
        identity = f"{row.scenario_id}/{row.asset_id}/{int(row.horizon_months)}M"
        try:
            draw_count_value = row.contribution_draw_count
            if isinstance(draw_count_value, (bool, np.bool_)) or not isinstance(
                draw_count_value, (Integral, np.integer)
            ):
                raise ValueError("contribution_draw_count is invalid")
            draw_count = int(draw_count_value)
            baseline_entries = _public_contribution_entries(
                row.baseline_component_contribution_json,
                name="baseline_component_contribution_json",
                scenario_id=row.scenario_id,
                contribution_kind="baseline_component",
                draw_count=draw_count,
            )
            channel_entries = _public_contribution_entries(
                row.channel_contribution_json,
                name="channel_contribution_json",
                scenario_id=row.scenario_id,
                contribution_kind="baseline_component",
                draw_count=draw_count,
            )
            scenario_entries = _public_contribution_entries(
                row.scenario_contribution_json,
                name="scenario_contribution_json",
                scenario_id=row.scenario_id,
                contribution_kind="scenario_shock",
                draw_count=draw_count,
            )
            if row.contribution_aggregation_method != CONTRIBUTION_AGGREGATION_METHOD:
                raise ValueError("row aggregation method is invalid")
            expected_channels = [
                entry
                for entry in baseline_entries
                if entry["component_type"] == "channel"
            ]
            if channel_entries != expected_channels:
                raise ValueError(
                    "channel JSON is not the exact baseline channel subset"
                )
            if row.scenario_id == "baseline" and scenario_entries:
                raise ValueError("baseline scenario contains scenario shocks")
            expected_component_contract_hash = (
                compute_contribution_component_contract_hash(
                    asset_id=row.asset_id,
                    scenario_id=row.scenario_id,
                    horizon_months=row.horizon_months,
                    baseline_keys=tuple(
                        (
                            str(entry["component_type"]),
                            str(entry["component_id"]),
                        )
                        for entry in baseline_entries
                    ),
                    scenario_keys=tuple(
                        (
                            str(entry["component_type"]),
                            str(entry["component_id"]),
                        )
                        for entry in scenario_entries
                    ),
                    source_identity={
                        column: getattr(row, column)
                        for column in CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
                    },
                )
            )
            if (
                row.contribution_component_contract_hash
                != expected_component_contract_hash
            ):
                raise ValueError(
                    "component contract fingerprint does not match public JSON keys"
                )
            passed_value = row.contribution_conservation_passed
            if not isinstance(passed_value, (bool, np.bool_)):
                raise ValueError("contribution conservation flag is invalid")
            if row.status == "unavailable":
                if (
                    baseline_entries
                    or channel_entries
                    or scenario_entries
                    or draw_count != 0
                    or bool(passed_value)
                    or not pd.isna(row.contribution_conservation_max_abs_error)
                ):
                    raise ValueError(
                        "unavailable row exposes contributions or a forged pass signal"
                    )
                continue
            if row.status != "available":
                raise ValueError("forecast status is invalid")
            available_rows += 1
            if not baseline_entries or draw_count < 1 or not bool(passed_value):
                raise ValueError("available row lacks contributions or a pass signal")
            expected_return = row.absolute_expected_return
            reported_error = row.contribution_conservation_max_abs_error
            if (
                isinstance(expected_return, (bool, np.bool_))
                or not isinstance(expected_return, (Real, np.integer, np.floating))
                or not np.isfinite(float(expected_return))
                or isinstance(reported_error, (bool, np.bool_))
                or not isinstance(reported_error, (Real, np.integer, np.floating))
                or not np.isfinite(float(reported_error))
            ):
                raise ValueError("conservation numeric metadata is invalid")
            public_expected_sum = sum(
                float(entry["expected_contribution"])
                for entry in baseline_entries + scenario_entries
            )
            expected_error = abs(public_expected_sum - float(expected_return))
            normalized_error = float(reported_error)
            if (
                normalized_error < 0.0
                or normalized_error > CONTRIBUTION_CONSERVATION_TOLERANCE
                or expected_error > CONTRIBUTION_CONSERVATION_TOLERANCE
                or normalized_error + CONTRIBUTION_CONSERVATION_TOLERANCE
                < expected_error
            ):
                raise ValueError(
                    "public expected contributions do not conserve absolute return"
                )
        except (AttributeError, TypeError, ValueError) as error:
            return False, f"{identity}: {error}"
    return (
        True,
        "independently audited full baseline components, channel subset, "
        "scenario shocks, expected-return conservation, and component contract "
        f"fingerprint verified for {available_rows} available rows",
    )


def _retained_component_keys(
    result: AssetForecastResult,
    *,
    asset_id: str,
    horizon_months: int,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    components = result.components
    components = components.loc[
        components["asset_id"].eq(asset_id)
        & components["month_number"].le(horizon_months)
    ]
    baseline_keys = tuple(
        sorted(
            {
                (str(row.source_type), str(row.component_id))
                for row in components.itertuples(index=False)
            }
        )
    )
    scenario_keys = tuple(
        ("scenario_shock", component_id)
        for component_id in sorted(
            components.loc[
                components["scenario_contribution"].ne(0.0),
                "component_id",
            ]
            .drop_duplicates()
            .astype(str)
            .tolist()
        )
    )
    return baseline_keys, scenario_keys


def _retained_component_contract_finding(
    mapping_product: AssetMappingFutureProduct,
) -> dict[str, str]:
    forecasts = object.__getattribute__(mapping_product, "_forecasts")
    if not forecasts:
        return _finding(
            "contribution_component_contract",
            "asset_mapping_future",
            "failed",
            "error",
            "RETAINED_COMPONENT_CONTRACT_MISSING",
            "retained Task 26 forecasts are missing for component contract verification",
        )
    by_scenario = {result.forecast_input.scenario_id: result for result in forecasts}
    checked_rows = 0
    try:
        for row in mapping_product.mapping.itertuples(index=False):
            identity = f"{row.scenario_id}/{row.asset_id}/{row.horizon_months}M"
            result = by_scenario.get(row.scenario_id)
            if result is None:
                raise ValueError(f"{identity}: retained scenario forecast is missing")
            summary_rows = result.summary.loc[
                result.summary["asset_id"].eq(row.asset_id)
                & result.summary["horizon_months"].eq(row.horizon_months)
                & result.summary["return_basis"].eq("absolute")
            ]
            if len(summary_rows) != 1:
                raise ValueError(f"{identity}: retained absolute summary is missing")
            source_row = summary_rows.iloc[0]
            if row.status != source_row["status"]:
                raise ValueError(f"{identity}: retained forecast status changed")
            source_identity = {
                column: source_row[column]
                for column in CONTRIBUTION_COMPONENT_IDENTITY_COLUMNS
            }
            for column, expected_value in source_identity.items():
                if getattr(row, column) != expected_value:
                    raise ValueError(f"{identity}: retained source identity changed")
            expected_baseline_keys, expected_scenario_keys = _retained_component_keys(
                result,
                asset_id=str(row.asset_id),
                horizon_months=int(row.horizon_months),
            )
            if row.status == "unavailable" and (
                expected_baseline_keys or expected_scenario_keys
            ):
                raise ValueError(
                    f"{identity}: unavailable retained forecast has component keys"
                )
            baseline_entries = _public_contribution_entries(
                row.baseline_component_contribution_json,
                name="baseline_component_contribution_json",
                scenario_id=row.scenario_id,
                contribution_kind="baseline_component",
                draw_count=int(row.contribution_draw_count),
            )
            scenario_entries = _public_contribution_entries(
                row.scenario_contribution_json,
                name="scenario_contribution_json",
                scenario_id=row.scenario_id,
                contribution_kind="scenario_shock",
                draw_count=int(row.contribution_draw_count),
            )
            actual_baseline_keys = tuple(
                (
                    str(entry["component_type"]),
                    str(entry["component_id"]),
                )
                for entry in baseline_entries
            )
            actual_scenario_keys = tuple(
                (
                    str(entry["component_type"]),
                    str(entry["component_id"]),
                )
                for entry in scenario_entries
            )
            if actual_baseline_keys != expected_baseline_keys:
                raise ValueError(
                    f"{identity}: baseline component keys differ from retained Task 26"
                )
            if actual_scenario_keys != expected_scenario_keys:
                raise ValueError(
                    f"{identity}: scenario component keys differ from retained Task 26"
                )
            expected_hash = compute_contribution_component_contract_hash(
                asset_id=row.asset_id,
                scenario_id=row.scenario_id,
                horizon_months=row.horizon_months,
                baseline_keys=expected_baseline_keys,
                scenario_keys=expected_scenario_keys,
                source_identity=source_identity,
            )
            if row.contribution_component_contract_hash != expected_hash:
                raise ValueError(
                    f"{identity}: component contract fingerprint differs from retained Task 26"
                )
            checked_rows += 1
    except (AttributeError, TypeError, ValueError) as error:
        return _finding(
            "contribution_component_contract",
            "asset_mapping_future",
            "failed",
            "error",
            "RETAINED_COMPONENT_CONTRACT_MISMATCH",
            str(error),
        )
    return _finding(
        "contribution_component_contract",
        "asset_mapping_future",
        "passed",
        "info",
        "RETAINED_COMPONENT_CONTRACT_VERIFIED",
        "component contract fingerprint and key sets verified against retained "
        f"Task 26 forecasts for {checked_rows} rows",
    )


def _normalize_findings(values: object) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError("findings must be a pandas DataFrame")
    if tuple(values.columns) != FORECAST_FINDING_COLUMNS:
        raise ValueError("findings columns do not match the stable contract")
    frame = values.copy(deep=True)
    if frame.empty:
        raise ValueError("verification findings cannot be empty")
    if frame["check_id"].duplicated().any():
        raise ValueError("verification findings contain duplicate checks")
    if not set(frame["status"]).issubset({"passed", "warning", "failed"}):
        raise ValueError("verification finding status is invalid")
    if not set(frame["severity"]).issubset({"info", "warning", "error"}):
        raise ValueError("verification finding severity is invalid")
    for column in FORECAST_FINDING_COLUMNS:
        if (
            frame[column].isna().any()
            or frame[column].astype(str).str.len().eq(0).any()
        ):
            raise ValueError(f"verification finding {column} cannot be blank")
    return frame.reset_index(drop=True)


@dataclass(frozen=True)
class ForecastVerificationReport:
    """Immutable verification findings for both forecast products."""

    passed: bool
    findings: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.passed, (bool, np.bool_)):
            raise TypeError("passed must be boolean")
        findings = _normalize_findings(self.findings)
        expected = not findings["status"].eq("failed").any()
        if bool(self.passed) != bool(expected):
            raise ValueError("passed is inconsistent with verification findings")
        object.__setattr__(self, "passed", bool(expected))
        object.__setattr__(self, "findings", findings.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    def __iter__(self) -> Iterator[pd.DataFrame]:
        yield self.findings


@dataclass(frozen=True)
class ForecastPublicationResult:
    """Published manifest, verified Mapping reference, and quality report."""

    manifest: RunManifest
    mapping_reference: MappingReference
    verification: ForecastVerificationReport

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, RunManifest):
            raise TypeError("manifest must be a RunManifest")
        if not isinstance(self.mapping_reference, MappingReference):
            raise TypeError("mapping_reference must be a MappingReference")
        if not isinstance(self.verification, ForecastVerificationReport):
            raise TypeError("verification must be a ForecastVerificationReport")
        if not self.verification.passed:
            raise ValueError("published forecast verification must pass")
        if self.mapping_reference.run_id != self.manifest.run_id:
            raise ValueError("Mapping reference and manifest run_id must match")


@dataclass(frozen=True)
class ForecastBuildResult:
    """Built Task 28 products plus their in-memory verification report."""

    cycle_product: CycleForecastProduct
    mapping_product: AssetMappingFutureProduct
    verification: ForecastVerificationReport

    def __post_init__(self) -> None:
        if not isinstance(self.cycle_product, CycleForecastProduct):
            raise TypeError("cycle_product must be a CycleForecastProduct")
        if not isinstance(self.mapping_product, AssetMappingFutureProduct):
            raise TypeError("mapping_product must be an AssetMappingFutureProduct")
        if not isinstance(self.verification, ForecastVerificationReport):
            raise TypeError("verification must be a ForecastVerificationReport")
        if not self.verification.passed:
            raise ValueError("built forecast products must pass verification")


def _frame_contract_findings(
    cycle_frame: pd.DataFrame,
    mapping_frame: pd.DataFrame,
    *,
    context: RunContext,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        validate_cycle_forecast(cycle_frame, context=context)
    except (TypeError, ValueError) as error:
        findings.append(
            _finding(
                "cycle_product_contract",
                "cycle_forecast",
                "failed",
                "error",
                "CYCLE_PRODUCT_CONTRACT_FAILED",
                str(error),
            )
        )
    else:
        findings.append(
            _finding(
                "cycle_product_contract",
                "cycle_forecast",
                "passed",
                "info",
                "CYCLE_PRODUCT_CONTRACT_PASSED",
                f"validated {len(cycle_frame)} governed cycle/horizon rows",
            )
        )
    try:
        validate_asset_mapping_future(mapping_frame, context=context)
    except (TypeError, ValueError) as error:
        findings.append(
            _finding(
                "future_mapping_contract",
                "asset_mapping_future",
                "failed",
                "error",
                "FUTURE_MAPPING_CONTRACT_FAILED",
                str(error),
            )
        )
    else:
        findings.append(
            _finding(
                "future_mapping_contract",
                "asset_mapping_future",
                "passed",
                "info",
                "FUTURE_MAPPING_CONTRACT_PASSED",
                f"validated {len(mapping_frame)} scenario/date/asset rows",
            )
        )

    forbidden = {
        column
        for column in mapping_frame.columns
        if "weight" in column
        or "contribution_share" in column
        or "historical_attribution" in column
    }
    findings.append(
        _finding(
            "future_mapping_weight_prohibition",
            "asset_mapping_future",
            "failed" if forbidden else "passed",
            "error" if forbidden else "info",
            (
                "FORBIDDEN_FUTURE_WEIGHT_SURFACE"
                if forbidden
                else "FUTURE_WEIGHT_SURFACE_PROHIBITED"
            ),
            (
                f"forbidden columns: {sorted(forbidden)}"
                if forbidden
                else "no historical contribution share or future weight field is exposed"
            ),
        )
    )
    scenarios = set(mapping_frame.get("scenario_id", pd.Series(dtype="object")))
    findings.append(
        _finding(
            "scenario_separation",
            "asset_mapping_future",
            "passed" if len(scenarios) == 6 else "failed",
            "info" if len(scenarios) == 6 else "error",
            (
                "STANDARD_SCENARIOS_ISOLATED"
                if len(scenarios) == 6
                else "STANDARD_SCENARIO_COVERAGE_FAILED"
            ),
            f"retained isolated scenarios: {sorted(scenarios)}",
        )
    )
    conservation_passed, conservation_detail = _audit_public_contribution_surface(
        mapping_frame
    )
    findings.append(
        _finding(
            "contribution_conservation",
            "asset_mapping_future",
            "passed" if conservation_passed else "failed",
            "info" if conservation_passed else "error",
            (
                "CONTRIBUTION_PATHS_CONSERVE"
                if conservation_passed
                else "CONTRIBUTION_PATHS_DO_NOT_CONSERVE"
            ),
            conservation_detail,
        )
    )
    baseline_failures = mapping_frame.loc[~mapping_frame["baseline_gate_passed"]]
    downgraded = (
        baseline_failures["mapping_status"]
        .isin({"retrospective_only", "unavailable"})
        .all()
    )
    findings.append(
        _finding(
            "future_mapping_baseline_gate",
            "asset_mapping_future",
            "passed" if downgraded else "failed",
            "info" if downgraded else "error",
            (
                "BASELINE_FAILURES_DOWNGRADED"
                if downgraded
                else "BASELINE_FAILURE_PUBLISHED_LIVE"
            ),
            f"baseline-failed rows={len(baseline_failures)}",
        )
    )
    return findings


def _channel_baseline_finding(
    mapping_product: AssetMappingFutureProduct,
) -> dict[str, str]:
    forecasts = object.__getattribute__(mapping_product, "_forecasts")
    if not forecasts:
        return _finding(
            "channel_simple_baseline_comparison",
            "asset_mapping_future",
            "failed",
            "error",
            "CHANNEL_BASELINE_EVIDENCE_MISSING",
            "retained Task 25 source forecasts are missing",
        )
    channel_result = forecasts[0].forecast_input.channel_forecast
    summary = channel_result.summary
    numeric = summary.loc[
        :,
        [
            "champion_oos_loss",
            "historical_mean_oos_loss",
            "persistence_oos_loss",
        ],
    ].apply(pd.to_numeric, errors="coerce")
    eligible = numeric.notna().all(axis=1)
    if not eligible.any():
        return _finding(
            "channel_simple_baseline_comparison",
            "asset_mapping_future",
            "warning",
            "warning",
            "CHANNEL_BASELINE_EVIDENCE_UNAVAILABLE",
            "Task 25 retained no finite paired simple-baseline comparisons",
        )
    comparison = numeric.loc[eligible]
    wins = comparison["champion_oos_loss"].le(
        comparison[["historical_mean_oos_loss", "persistence_oos_loss"]].min(axis=1)
    )
    if wins.all():
        return _finding(
            "channel_simple_baseline_comparison",
            "asset_mapping_future",
            "passed",
            "info",
            "CHANNEL_CHAMPION_BEATS_SIMPLE_BASELINES",
            f"Champion won {int(wins.sum())}/{len(wins)} paired channel horizons",
        )
    return _finding(
        "channel_simple_baseline_comparison",
        "asset_mapping_future",
        "warning",
        "warning",
        "CHANNEL_CHAMPION_NOT_STABLY_ABOVE_BASELINES",
        f"Champion won {int(wins.sum())}/{len(wins)} paired channel horizons; "
        "asset-level Mapping gates remain authoritative",
    )


def _report(findings: list[dict[str, str]]) -> ForecastVerificationReport:
    frame = pd.DataFrame(findings, columns=FORECAST_FINDING_COLUMNS)
    return ForecastVerificationReport(
        passed=not frame["status"].eq("failed").any(),
        findings=frame,
    )


def verify_forecast_products(
    cycle_product: CycleForecastProduct,
    mapping_product: AssetMappingFutureProduct,
    *,
    context: RunContext,
) -> ForecastVerificationReport:
    """Verify both in-memory Task 28 products and governed source gates."""

    run_context = _context(context)
    if not isinstance(cycle_product, CycleForecastProduct):
        raise TypeError("cycle_product must be build_cycle_forecast output")
    if not isinstance(mapping_product, AssetMappingFutureProduct):
        raise TypeError("mapping_product must be build_asset_mapping_future output")
    findings = _frame_contract_findings(
        cycle_product.forecast,
        mapping_product.mapping,
        context=run_context,
    )
    findings.append(_retained_component_contract_finding(mapping_product))
    promotion = object.__getattribute__(cycle_product, "_promotion_result")
    governed = bool(
        promotion is not None
        and promotion.promotion_decision == "rejected"
        and promotion.live_model_role == "champion"
        and promotion.challenger_status == "experimental"
        and promotion.failure_reason_codes
    )
    findings.append(
        _finding(
            "champion_challenger_governance",
            "cycle_forecast",
            "passed" if governed else "failed",
            "info" if governed else "error",
            (
                "REJECTED_CHALLENGER_RETAINED_EXPERIMENTAL"
                if governed
                else "FORECAST_MODEL_LABEL_GOVERNANCE_FAILED"
            ),
            "forecast values remain Champion/live and Challenger remains experimental",
        )
    )
    findings.append(_channel_baseline_finding(mapping_product))
    return _report(findings)


def _reference_catalog_check(
    run_dir: Path,
    *,
    manifest: RunManifest,
) -> None:
    metadata = manifest.quality_summary.get(MAPPING_MANIFEST_METADATA_KEY)
    if not isinstance(metadata, dict) and not hasattr(metadata, "items"):
        raise ForecastVerificationError("manifest Mapping metadata is missing")
    expected_metadata = dict(metadata.items())
    reference_path = run_dir / MAPPING_REFERENCE_FILENAME
    try:
        raw = reference_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ForecastVerificationError("Mapping reference JSON is invalid") from error
    if raw != canonical_json_bytes(payload) + b"\n":
        raise ForecastVerificationError("Mapping reference JSON is not canonical")
    expected = {
        **expected_metadata,
        "version": manifest.model_version,
        "run_id": manifest.run_id,
        "config_hash": manifest.config_hash,
        "artifact_hash": sha256_file(run_dir / ASSET_MAPPING_FUTURE_FILENAME),
        "as_of": manifest.as_of.isoformat(),
    }
    if payload != expected:
        raise ForecastVerificationError(
            "Mapping reference JSON does not match manifest and artifact"
        )


def _verify_staged_run(
    run_dir: Path,
    *,
    manifest: RunManifest,
) -> ForecastVerificationReport:
    cycle_path = run_dir / CYCLE_FORECAST_FILENAME
    mapping_path = run_dir / ASSET_MAPPING_FUTURE_FILENAME
    if pq.read_schema(cycle_path) != CYCLE_FORECAST_SCHEMA:
        raise ForecastVerificationError(
            "persisted cycle_forecast Arrow schema mismatch"
        )
    if pq.read_schema(mapping_path) != ASSET_MAPPING_FUTURE_SCHEMA:
        raise ForecastVerificationError(
            "persisted asset_mapping_future Arrow schema mismatch"
        )
    cycle_frame = pd.read_parquet(cycle_path)
    mapping_frame = pd.read_parquet(mapping_path)
    if tuple(cycle_frame.columns) != CYCLE_FORECAST_COLUMNS:
        raise ForecastVerificationError("persisted cycle_forecast columns changed")
    if tuple(mapping_frame.columns) != ASSET_MAPPING_FUTURE_COLUMNS:
        raise ForecastVerificationError("persisted future Mapping columns changed")
    validate_cycle_forecast(cycle_frame, context=manifest)
    validate_asset_mapping_future(mapping_frame, context=manifest)
    _reference_catalog_check(run_dir, manifest=manifest)
    findings = _frame_contract_findings(
        cycle_frame,
        mapping_frame,
        context=manifest,
    )
    findings.append(
        _finding(
            "mapping_reference_catalog",
            "asset_mapping_future",
            "passed",
            "info",
            "MAPPING_REFERENCE_CATALOG_VERIFIED",
            "canonical Mapping reference matches manifest and artifact checksum",
        )
    )
    return _report(findings)


def verify_published_forecast_run(
    run_dir: Path,
    *,
    expected_manifest: RunManifest,
) -> ForecastVerificationReport:
    """Reload and verify a published Task 28 run and Mapping reference."""

    if not isinstance(expected_manifest, RunManifest):
        raise TypeError("expected_manifest must be a trusted RunManifest")
    directory = Path(run_dir).absolute()
    verified = verify_manifest(directory, expected=expected_manifest)
    report = _verify_staged_run(directory, manifest=verified)
    MappingReference.from_published_run(
        directory,
        expected_manifest=verified,
    )
    return report


def build_forecast_products(
    cycle_forecast: CycleForecastResult,
    asset_forecasts: Sequence[AssetForecastResult],
    current_mapping: object,
    promotion_result: PromotionResult,
    *,
    context: RunContext,
) -> ForecastBuildResult:
    """Build and verify both Task 28 products from governed retained results."""

    run_context = _context(context)
    cycle_product = build_cycle_forecast(
        cycle_forecast,
        promotion_result,
        context=run_context,
    )
    mapping_product = build_asset_mapping_future(
        asset_forecasts,
        current_mapping,
        context=run_context,
    )
    report = verify_forecast_products(
        cycle_product,
        mapping_product,
        context=run_context,
    )
    if not report.passed:
        failed = report.findings.loc[report.findings["status"].eq("failed")]
        raise ForecastVerificationError(
            "; ".join(failed["detail"].astype(str).tolist())
        )
    return ForecastBuildResult(
        cycle_product=cycle_product,
        mapping_product=mapping_product,
        verification=report,
    )


def publish_forecast_products(
    product_root: Path,
    cycle_product: CycleForecastProduct,
    mapping_product: AssetMappingFutureProduct,
    *,
    context: RunContext,
    mapping_id: str,
) -> ForecastPublicationResult:
    """Atomically publish both Parquet products and canonical reference JSON."""

    run_context = _context(context)
    root = Path(product_root)
    if root.name != ASSET_MAPPING_FUTURE_PRODUCT:
        raise ValueError(
            "product_root name must match Task 27 mapping_product asset_mapping_future"
        )
    expected_metadata = mapping_manifest_metadata(mapping_id)
    metadata = run_context.quality_summary.get(MAPPING_MANIFEST_METADATA_KEY)
    if not hasattr(metadata, "items") or dict(metadata.items()) != expected_metadata:
        raise ValueError("RunContext quality_summary Mapping metadata is invalid")
    report = verify_forecast_products(
        cycle_product,
        mapping_product,
        context=run_context,
    )
    if not report.passed:
        failed = report.findings.loc[report.findings["status"].eq("failed")]
        raise ForecastVerificationError(
            "; ".join(failed["detail"].astype(str).tolist())
        )

    def write_staging(staging_dir: Path) -> None:
        write_cycle_forecast(staging_dir, cycle_product, context=run_context)
        write_asset_mapping_future(staging_dir, mapping_product, context=run_context)
        write_mapping_reference(
            staging_dir,
            context=run_context,
            mapping_id=mapping_id,
        )

    def validate_staging(staging_dir: Path, manifest: RunManifest) -> None:
        staged_report = _verify_staged_run(staging_dir, manifest=manifest)
        if not staged_report.passed:
            raise ForecastVerificationError("staged Task 28 verification failed")

    published_report: ForecastVerificationReport | None = None
    published_reference: MappingReference | None = None

    def validate_published(run_dir: Path, manifest: RunManifest) -> None:
        nonlocal published_report, published_reference
        published_report = verify_published_forecast_run(
            run_dir,
            expected_manifest=manifest,
        )
        published_reference = MappingReference.from_published_run(
            run_dir,
            expected_manifest=manifest,
        )

    manifest = publish_run(
        root,
        run_context,
        write_staging=write_staging,
        validate_staging=validate_staging,
        validate_published=validate_published,
    )
    return ForecastPublicationResult(
        manifest=manifest,
        mapping_reference=cast(MappingReference, published_reference),
        verification=cast(ForecastVerificationReport, published_report),
    )


def build_verify_publish_forecasts(
    product_root: Path,
    cycle_forecast: CycleForecastResult,
    asset_forecasts: Sequence[AssetForecastResult],
    current_mapping: object,
    promotion_result: PromotionResult,
    *,
    context: RunContext,
    mapping_id: str,
) -> ForecastPublicationResult:
    """Run the complete Task 28 build, verify, and atomic publish sequence."""

    built = build_forecast_products(
        cycle_forecast,
        asset_forecasts,
        current_mapping,
        promotion_result,
        context=context,
    )
    return publish_forecast_products(
        product_root,
        built.cycle_product,
        built.mapping_product,
        context=context,
        mapping_id=mapping_id,
    )


run_forecast_pipeline = build_verify_publish_forecasts


__all__ = [
    "FORECAST_FINDING_COLUMNS",
    "ForecastBuildResult",
    "ForecastPublicationResult",
    "ForecastVerificationError",
    "ForecastVerificationReport",
    "build_forecast_products",
    "build_verify_publish_forecasts",
    "publish_forecast_products",
    "run_forecast_pipeline",
    "verify_forecast_products",
    "verify_published_forecast_run",
]
