"""Explicit M2 cycle build stages and atomic publication."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import stat
import tempfile
from types import MappingProxyType

import numpy as np
import pandas as pd

from seven_cycle_platform.cycles.discovery import DiscoveryEvidence
from seven_cycle_platform.cycles.engine import SevenCycleEngine
from seven_cycle_platform.cycles.model_version import (
    CycleModelVersion,
    ManualOverride,
)
from seven_cycle_platform.cycles.recalibration import recalibrate_cycle
from seven_cycle_platform.cycles.vintage import (
    VintageSelection,
    read_vintage,
    reconstruct_cycle_vintage,
)
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.products.cycle_phase import (
    CYCLE_PHASE_VINTAGE_FILENAME,
    build_cycle_phase_vintage,
    write_cycle_phase_vintage,
)
from seven_cycle_platform.registry.models import CycleSpec, RegistryBundle
from seven_cycle_platform.security import redact_secrets
from seven_cycle_platform.storage.manifest import (
    RunManifest,
    collect_product_checksums,
)
from seven_cycle_platform.storage.publisher import publish_run
from seven_cycle_platform.storage.run_context import (
    RunContext,
    canonical_json_bytes,
)
from seven_cycle_platform.types import ReleaseStatus, VintageKind
from seven_cycle_platform.verification.cycles import (
    CYCLE_MODEL_VERSIONS_FILENAME,
    MANDATORY_CHECKS,
    CycleAcceptanceError,
    CycleVerificationRequest,
    CycleVerifiers,
    QualityFinding,
    VerificationPlan,
    cycle_model_set_identity,
    create_verification_plan,
    default_cycle_verifiers,
    deserialize_cycle_model_version,
    m2_algorithm_fingerprint,
    registry_config_payload,
    registry_snapshot_payloads,
    serialize_cycle_model_version,
    validate_product_interpretations,
    validate_registry_bundle_contract,
    verify_published_cycle_run,
    write_quality_findings,
    write_verification_plan,
)


CYCLE_PIPELINE_INPUT_FILENAME = "cycle_pipeline_input.json"
_CYCLE_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def _nonblank(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-blank string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-blank string")
    return normalized


def _category_map(value: object, *, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    normalized: dict[str, str] = {}
    for entity_id, category in value.items():
        normalized[_nonblank(entity_id, name=f"{name} key")] = _nonblank(
            category,
            name=f"{name} value",
        )
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return dict(sorted(normalized.items()))


def _date_tuple(value: object, *, name: str) -> tuple[date, ...]:
    if not isinstance(value, tuple) or not value:
        raise TypeError(f"{name} must be a non-empty tuple")
    normalized: list[date] = []
    for item in value:
        if not isinstance(item, date) or isinstance(item, datetime):
            raise TypeError(f"{name} must contain dates without time")
        normalized.append(item)
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{name} must be unique and sorted")
    return tuple(normalized)


def _observation_key(record: Observation) -> tuple[object, ...]:
    return (
        record.entity_id,
        record.observation_date,
        record.release_date,
        record.vintage_date,
        record.revision_number,
        record.vintage_kind.value,
        record.retrieval_time,
        record.value,
    )


@dataclass(frozen=True)
class QuarterlyDiscoveryEvidence:
    """One supplied quarterly discovery record for a governed cycle."""

    cycle_id: str
    effective_date: date
    evidence: DiscoveryEvidence

    def __post_init__(self) -> None:
        cycle_id = _nonblank(self.cycle_id, name="cycle_id")
        if cycle_id not in _CYCLE_IDS:
            raise ValueError("cycle_id must be one of C1 through C7")
        if not isinstance(self.effective_date, date) or isinstance(
            self.effective_date,
            datetime,
        ):
            raise TypeError("effective_date must be a date without time")
        if (self.effective_date.month, self.effective_date.day) not in {
            (3, 31),
            (6, 30),
            (9, 30),
            (12, 31),
        }:
            raise ValueError("effective_date must be a calendar quarter end")
        if not isinstance(self.evidence, DiscoveryEvidence):
            raise TypeError("evidence must be DiscoveryEvidence")
        object.__setattr__(self, "cycle_id", cycle_id)


@dataclass(frozen=True)
class QuarterlyManualOverride:
    """One governed manual override request keyed to a cycle quarter."""

    cycle_id: str
    effective_date: date
    override: ManualOverride

    def __post_init__(self) -> None:
        cycle_id = _nonblank(self.cycle_id, name="cycle_id")
        if cycle_id not in _CYCLE_IDS:
            raise ValueError("cycle_id must be one of C1 through C7")
        if not isinstance(self.effective_date, date) or isinstance(
            self.effective_date,
            datetime,
        ):
            raise TypeError("effective_date must be a date without time")
        if (self.effective_date.month, self.effective_date.day) not in {
            (3, 31),
            (6, 30),
            (9, 30),
            (12, 31),
        }:
            raise ValueError("effective_date must be a calendar quarter end")
        if not isinstance(self.override, ManualOverride):
            raise TypeError("override must be a ManualOverride")
        object.__setattr__(self, "cycle_id", cycle_id)


@dataclass(frozen=True)
class CyclePipelineInput:
    """Immutable, injectable source contract for one M2 cycle build."""

    observations: tuple[Observation, ...]
    annual_categories: Mapping[str, str]
    monthly_categories: Mapping[str, str]
    prior_model_versions: tuple[CycleModelVersion, ...]
    discovery_evidence: tuple[QuarterlyDiscoveryEvidence, ...]
    state_dates: tuple[date, ...]
    verification_cutoffs: tuple[date, ...]
    manual_overrides: tuple[QuarterlyManualOverride, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or not self.observations:
            raise TypeError("observations must be a non-empty tuple")
        if any(not isinstance(record, Observation) for record in self.observations):
            raise TypeError("observations must contain Observation records")
        if not isinstance(self.prior_model_versions, tuple) or any(
            not isinstance(version, CycleModelVersion)
            for version in self.prior_model_versions
        ):
            raise TypeError(
                "prior_model_versions must be a tuple of CycleModelVersion records"
            )
        if not isinstance(self.discovery_evidence, tuple) or any(
            not isinstance(item, QuarterlyDiscoveryEvidence)
            for item in self.discovery_evidence
        ):
            raise TypeError(
                "discovery_evidence must contain QuarterlyDiscoveryEvidence"
            )
        if not isinstance(self.manual_overrides, tuple) or any(
            not isinstance(item, QuarterlyManualOverride)
            for item in self.manual_overrides
        ):
            raise TypeError(
                "manual_overrides must contain QuarterlyManualOverride records"
            )
        annual = _category_map(self.annual_categories, name="annual_categories")
        monthly = _category_map(
            self.monthly_categories,
            name="monthly_categories",
        )
        overlap = sorted(set(annual).intersection(monthly))
        if overlap:
            raise ValueError(
                "entities cannot be both annual and monthly: " + ", ".join(overlap)
            )
        versions = tuple(
            sorted(
                self.prior_model_versions,
                key=lambda version: (
                    version.cycle_id,
                    version.effective_date,
                    version.version_id,
                ),
            )
        )
        evidence = tuple(
            sorted(
                self.discovery_evidence,
                key=lambda item: (item.effective_date, item.cycle_id),
            )
        )
        evidence_keys = [
            (item.cycle_id, item.effective_date) for item in evidence
        ]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("discovery_evidence keys must be unique")
        manual_overrides = tuple(
            sorted(
                self.manual_overrides,
                key=lambda item: (item.effective_date, item.cycle_id),
            )
        )
        override_keys = [
            (item.cycle_id, item.effective_date) for item in manual_overrides
        ]
        if len(override_keys) != len(set(override_keys)):
            raise ValueError("manual_overrides keys must be unique")
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=_observation_key)),
        )
        object.__setattr__(self, "annual_categories", MappingProxyType(annual))
        object.__setattr__(self, "monthly_categories", MappingProxyType(monthly))
        object.__setattr__(self, "prior_model_versions", versions)
        object.__setattr__(self, "discovery_evidence", evidence)
        object.__setattr__(self, "manual_overrides", manual_overrides)
        object.__setattr__(
            self,
            "state_dates",
            _date_tuple(self.state_dates, name="state_dates"),
        )
        object.__setattr__(
            self,
            "verification_cutoffs",
            _date_tuple(
                self.verification_cutoffs,
                name="verification_cutoffs",
            ),
        )


@dataclass(frozen=True)
class LoadedCycleVintage:
    """Visible vintage views and the actual run data vintage."""

    selections: tuple[VintageSelection, ...]
    interpretations: tuple[VintageKind, ...]
    data_vintage: date


@dataclass(frozen=True)
class GovernedCycleModels:
    """Seven current model versions and center-injected engine specs."""

    model_versions: tuple[CycleModelVersion, ...]
    cycle_specs: tuple[CycleSpec, ...]
    model_version_identity: str


@dataclass(frozen=True)
class EstimatedCycleStates:
    """Raw Task 10 state views produced by governed model centers."""

    engine: SevenCycleEngine
    state_frames: tuple[pd.DataFrame, ...]


@dataclass(frozen=True)
class CycleVerificationReport:
    """Mandatory findings plus the staged cycle product candidate."""

    findings: tuple[QualityFinding, ...]
    product: pd.DataFrame | None
    product_checksum: str | None

    @property
    def passed(self) -> bool:
        return self.product is not None and self.product_checksum is not None and all(
            finding.status == "PASS" for finding in self.findings
        )


@dataclass(frozen=True)
class CycleBuildResult:
    """Outcome of a governed M2 build attempt."""

    status: ReleaseStatus
    run_id: str | None
    publication_path: Path | None
    manifest: RunManifest | None
    findings: tuple[QualityFinding, ...]
    reused: bool


class _CycleBuildBlocked(RuntimeError):
    def __init__(self, finding: QualityFinding) -> None:
        super().__init__(finding.message)
        self.finding = finding


def _governance_failure(check: str, message: str) -> QualityFinding:
    return QualityFinding(
        entity_id="seven_cycle_platform",
        check=check,
        severity="mandatory",
        status="FAIL",
        message=redact_secrets(message),
        observed_value=0.0,
        threshold=1.0,
    )


def _normalize_as_of(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("as_of must be a date without time")
    return value


def _has_causal_coverage(
    observations: tuple[Observation, ...],
    entity_ids: set[str],
) -> bool:
    dates_by_entity: dict[str, set[date]] = {}
    for observation in observations:
        if observation.entity_id in entity_ids:
            dates_by_entity.setdefault(observation.entity_id, set()).add(
                observation.observation_date
            )
    return any(len(dates) >= 3 for dates in dates_by_entity.values())


def _prepare_verification_plan(
    pipeline_input: CyclePipelineInput,
    *,
    as_of: date,
    interpretations: tuple[VintageKind, ...],
    strict_vintage: bool,
) -> VerificationPlan:
    try:
        plan = create_verification_plan(
            pipeline_input.verification_cutoffs,
            algorithm_fingerprint=m2_algorithm_fingerprint(),
            interpretations=interpretations,
            strict_vintage=strict_vintage,
        )
        if any(cutoff > as_of for cutoff in plan.verification_cutoffs):
            raise ValueError("verification cutoffs cannot follow as_of")
        annual_entities = set(pipeline_input.annual_categories)
        monthly_entities = set(pipeline_input.monthly_categories)
        covered_archives: list[tuple[Observation, ...]] = []
        latest_cutoff = plan.verification_cutoffs[-1]
        for interpretation in plan.interpretations:
            candidate_kinds = (
                {VintageKind.REALTIME, VintageKind.PSEUDO_VINTAGE}
                if interpretation is VintageKind.REALTIME
                else {interpretation}
            )
            visible = tuple(
                record
                for record in pipeline_input.observations
                if record.vintage_kind in candidate_kinds
                and record.release_date <= latest_cutoff
                and record.vintage_date <= latest_cutoff
            )
            if not (
                _has_causal_coverage(visible, annual_entities)
                or _has_causal_coverage(visible, monthly_entities)
            ):
                raise ValueError(
                    "verification plan has no causal data coverage for "
                    f"{interpretation.value}"
                )
            covered_archives.append(visible)
        covered = tuple(
            observation
            for archive in covered_archives
            for observation in archive
        )
        if not _has_causal_coverage(covered, annual_entities):
            raise ValueError("verification plan has no causal annual coverage")
        if not _has_causal_coverage(covered, monthly_entities):
            raise ValueError("verification plan has no causal monthly coverage")
        return plan
    except (TypeError, ValueError) as error:
        raise _CycleBuildBlocked(
            _governance_failure(
                "verification_plan",
                f"verification plan is not meaningful: {error}",
            )
        ) from error


def load_vintage(
    pipeline_input: CyclePipelineInput,
    *,
    as_of: date,
    strict_vintage: bool,
) -> LoadedCycleVintage:
    """Load actual point-in-time views without fabricating observations."""

    if not isinstance(pipeline_input, CyclePipelineInput):
        raise TypeError("pipeline_input must be CyclePipelineInput")
    cutoff = _normalize_as_of(as_of)
    if not isinstance(strict_vintage, bool):
        raise TypeError("strict_vintage must be a boolean")
    if any(state_date > cutoff for state_date in pipeline_input.state_dates):
        raise ValueError("state_dates cannot follow as_of")
    try:
        realtime = read_vintage(
            pipeline_input.observations,
            as_of=cutoff,
            strict=strict_vintage,
            interpretation=VintageKind.REALTIME,
        )
    except ValueError as error:
        if "pseudo_vintage" in str(error):
            raise _CycleBuildBlocked(
                _governance_failure("vintage_contract", str(error))
            ) from error
        raise
    if not realtime.observations:
        raise _CycleBuildBlocked(
            _governance_failure(
                "vintage_contract",
                "no realtime observations are visible at the requested as_of",
            )
        )
    selections = [realtime]
    interpretations = [VintageKind.REALTIME]
    has_latest = any(
        record.vintage_kind is VintageKind.LATEST_HISTORICAL
        and record.release_date <= cutoff
        and record.vintage_date <= cutoff
        for record in pipeline_input.observations
    )
    if has_latest:
        latest = read_vintage(
            pipeline_input.observations,
            as_of=cutoff,
            strict=strict_vintage,
            interpretation=VintageKind.LATEST_HISTORICAL,
        )
        selections.append(latest)
        interpretations.append(VintageKind.LATEST_HISTORICAL)
    selected_records = tuple(
        record for selection in selections for record in selection.observations
    )
    data_vintage = max(record.vintage_date for record in selected_records)
    if data_vintage > cutoff:
        raise ValueError("selected data_vintage cannot follow as_of")
    return LoadedCycleVintage(
        selections=tuple(selections),
        interpretations=tuple(interpretations),
        data_vintage=data_vintage,
    )


def _next_quarter_end(value: date) -> date:
    if (value.month, value.day) == (3, 31):
        return date(value.year, 6, 30)
    if (value.month, value.day) == (6, 30):
        return date(value.year, 9, 30)
    if (value.month, value.day) == (9, 30):
        return date(value.year, 12, 31)
    if (value.month, value.day) == (12, 31):
        return date(value.year + 1, 3, 31)
    raise ValueError("model version effective_date must be a quarter end")


def _current_versions(
    pipeline_input: CyclePipelineInput,
    as_of: date,
) -> dict[str, CycleModelVersion]:
    grouped: dict[str, list[CycleModelVersion]] = {
        cycle_id: [] for cycle_id in _CYCLE_IDS
    }
    seen: set[tuple[str, date]] = set()
    for version in pipeline_input.prior_model_versions:
        key = (version.cycle_id, version.effective_date)
        if key in seen:
            raise ValueError("only one governed model version is allowed per quarter")
        seen.add(key)
        if version.effective_date <= as_of:
            grouped[version.cycle_id].append(version)
    missing = [cycle_id for cycle_id, versions in grouped.items() if not versions]
    if missing:
        raise _CycleBuildBlocked(
            _governance_failure(
                "model_version_contract",
                "missing current governed model versions for " + ", ".join(missing),
            )
        )
    return {
        cycle_id: max(versions, key=lambda version: version.effective_date)
        for cycle_id, versions in grouped.items()
    }


def recalibrate_if_due(
    pipeline_input: CyclePipelineInput,
    *,
    registry_bundle: RegistryBundle,
    as_of: date,
) -> GovernedCycleModels:
    """Apply supplied quarterly evidence or carry current versions forward."""

    if not isinstance(pipeline_input, CyclePipelineInput):
        raise TypeError("pipeline_input must be CyclePipelineInput")
    if not isinstance(registry_bundle, RegistryBundle):
        raise TypeError("registry_bundle must be RegistryBundle")
    cutoff = _normalize_as_of(as_of)
    specs = {cycle.cycle_id: cycle for cycle in registry_bundle.cycles}
    if tuple(sorted(specs)) != _CYCLE_IDS:
        raise ValueError("registry_bundle must contain exactly C1 through C7")
    current = _current_versions(pipeline_input, cutoff)
    evidence_by_key = {
        (item.cycle_id, item.effective_date): item.evidence
        for item in pipeline_input.discovery_evidence
    }
    override_by_key = {
        (item.cycle_id, item.effective_date): item.override
        for item in pipeline_input.manual_overrides
    }
    governed: list[CycleModelVersion] = []
    for cycle_id in _CYCLE_IDS:
        version = current[cycle_id]
        due_date = _next_quarter_end(version.effective_date)
        while due_date <= cutoff:
            evidence = evidence_by_key.get((cycle_id, due_date))
            if evidence is None:
                raise _CycleBuildBlocked(
                    _governance_failure(
                        "recalibration_evidence",
                        f"required discovery evidence is absent for {cycle_id} "
                        f"at {due_date.isoformat()}",
                    )
                )
            version = recalibrate_cycle(
                specs[cycle_id],
                evidence,
                old_center=version.new_center,
                old_band=version.new_band,
                old_confidence=version.new_confidence,
                effective_date=due_date,
                manual_override=override_by_key.get((cycle_id, due_date)),
                previous_version_id=version.version_id,
            )
            due_date = _next_quarter_end(due_date)
        governed.append(version)
    versions = tuple(governed)
    injected_specs = tuple(
        specs[version.cycle_id].with_initial_center(version.new_center)
        for version in versions
    )
    return GovernedCycleModels(
        model_versions=versions,
        cycle_specs=injected_specs,
        model_version_identity=cycle_model_set_identity(versions),
    )


def estimate_states(
    pipeline_input: CyclePipelineInput,
    loaded: LoadedCycleVintage,
    governed: GovernedCycleModels,
    *,
    strict_vintage: bool,
) -> EstimatedCycleStates:
    """Estimate requested Task 10 views using governed current centers."""

    if not isinstance(loaded, LoadedCycleVintage):
        raise TypeError("loaded must be LoadedCycleVintage")
    if not isinstance(governed, GovernedCycleModels):
        raise TypeError("governed must be GovernedCycleModels")
    engine = SevenCycleEngine(governed.cycle_specs)
    frames = tuple(
        reconstruct_cycle_vintage(
            pipeline_input.observations,
            engine=engine,
            annual_categories=pipeline_input.annual_categories,
            monthly_categories=pipeline_input.monthly_categories,
            as_of=pipeline_input.state_dates,
            strict=strict_vintage,
            interpretation=interpretation,
        )
        for interpretation in loaded.interpretations
    )
    expected_centers = {
        version.cycle_id: version.new_center
        for version in governed.model_versions
    }
    for frame in frames:
        for cycle_id, center in expected_centers.items():
            values = frame.loc[
                frame["cycle_id"].eq(cycle_id),
                "center_period",
            ].to_numpy(dtype="float64")
            if not np.isclose(values, center, rtol=0.0, atol=1e-12).all():
                raise ValueError("engine did not apply the governed model center")
    return EstimatedCycleStates(engine=engine, state_frames=frames)


def _invoke_request_gate(
    gate,
    request: CycleVerificationRequest,
    check: str,
) -> QualityFinding:
    try:
        finding = gate(request)
        if not isinstance(finding, QualityFinding) or finding.check != check:
            raise TypeError(f"{check} verifier returned an invalid finding")
        return finding
    except Exception as error:
        return _governance_failure(
            check,
            f"{check} verifier failed: {redact_secrets(str(error))}",
        )


def _invoke_schema_gate(
    gate,
    staged_dir: Path,
    manifest: RunManifest,
) -> QualityFinding:
    try:
        finding = gate(staged_dir, manifest)
        if (
            not isinstance(finding, QualityFinding)
            or finding.check != "schema_contract"
        ):
            raise TypeError("schema_contract verifier returned an invalid finding")
        return finding
    except Exception as error:
        return _governance_failure(
            "schema_contract",
            "schema_contract verifier failed: " + redact_secrets(str(error)),
        )


def _combine_veto_findings(
    default_finding: QualityFinding,
    injected_finding: QualityFinding | None,
) -> QualityFinding:
    if default_finding.status == "FAIL":
        return default_finding
    if injected_finding is not None and injected_finding.status == "FAIL":
        return injected_finding
    return default_finding


def _schema_failure(message: str) -> QualityFinding:
    return _governance_failure(
        "schema_contract",
        f"schema contract failed: {redact_secrets(message)}",
    )


def verify(
    pipeline_input: CyclePipelineInput,
    estimated: EstimatedCycleStates,
    *,
    context: RunContext,
    product_root: Path,
    verification_plan: VerificationPlan,
    verifiers: CycleVerifiers | None = None,
) -> CycleVerificationReport:
    """Run cutoff, schema, and no-lookahead gates before publication."""

    default_verifiers = default_cycle_verifiers()
    if verifiers is not None and not isinstance(verifiers, CycleVerifiers):
        raise TypeError("verifiers must be CycleVerifiers")
    request = CycleVerificationRequest(
        observations=pipeline_input.observations,
        engine=estimated.engine,
        annual_categories=pipeline_input.annual_categories,
        monthly_categories=pipeline_input.monthly_categories,
        interpretations=verification_plan.interpretations,
        verification_cutoffs=verification_plan.verification_cutoffs,
        numeric_tolerance=verification_plan.numeric_tolerance,
        strict_vintage=verification_plan.strict_vintage,
    )
    default_cutoff = _invoke_request_gate(
        default_verifiers.cutoff_reconstruction,
        request,
        "cutoff_reconstruction",
    )
    injected_cutoff = (
        None
        if verifiers is None
        else _invoke_request_gate(
            verifiers.cutoff_reconstruction,
            request,
            "cutoff_reconstruction",
        )
    )
    cutoff_finding = _combine_veto_findings(
        default_cutoff,
        injected_cutoff,
    )
    default_no_lookahead = _invoke_request_gate(
        default_verifiers.no_lookahead,
        request,
        "no_lookahead",
    )
    injected_no_lookahead = (
        None
        if verifiers is None
        else _invoke_request_gate(
            verifiers.no_lookahead,
            request,
            "no_lookahead",
        )
    )
    no_lookahead_finding = _combine_veto_findings(
        default_no_lookahead,
        injected_no_lookahead,
    )
    product_checksum = None
    try:
        product = build_cycle_phase_vintage(
            estimated.state_frames,
            context=context,
        )
        validate_product_interpretations(product, verification_plan)
        root = Path(product_root)
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".m2-verify-",
            dir=root,
        ) as temporary:
            staged_dir = Path(temporary) / context.run_id
            staged_dir.mkdir()
            write_cycle_phase_vintage(staged_dir, product, context=context)
            product_checksums = collect_product_checksums(staged_dir)
            product_checksum = product_checksums[CYCLE_PHASE_VINTAGE_FILENAME]
            provisional_context = context.with_product_checksums(product_checksums)
            provisional_manifest = RunManifest.from_context(provisional_context)
            default_schema = _invoke_schema_gate(
                default_verifiers.schema_contract,
                staged_dir,
                provisional_manifest,
            )
            injected_schema = (
                None
                if verifiers is None
                else _invoke_schema_gate(
                    verifiers.schema_contract,
                    staged_dir,
                    provisional_manifest,
                )
            )
            schema_finding = _combine_veto_findings(
                default_schema,
                injected_schema,
            )
    except Exception as error:
        product = None
        schema_finding = _schema_failure(str(error))
    findings_by_check = {
        cutoff_finding.check: cutoff_finding,
        schema_finding.check: schema_finding,
        no_lookahead_finding.check: no_lookahead_finding,
    }
    findings = tuple(findings_by_check[check] for check in MANDATORY_CHECKS)
    return CycleVerificationReport(
        findings=findings,
        product=product,
        product_checksum=product_checksum,
    )


def _observation_payload(record: Observation) -> dict[str, object]:
    return record.model_dump(mode="json")


def _evidence_payload(item: QuarterlyDiscoveryEvidence) -> dict[str, object]:
    evidence = item.evidence
    return {
        "cycle_id": item.cycle_id,
        "effective_date": item.effective_date.isoformat(),
        "evidence": {
            "bootstrap_period_high": evidence.bootstrap_period_high,
            "bootstrap_period_low": evidence.bootstrap_period_low,
            "candidate_center": evidence.candidate_center,
            "category_balanced_score": evidence.category_balanced_score,
            "category_support": evidence.category_support,
            "macro_only_score": evidence.macro_only_score,
            "method_agreement": evidence.method_agreement,
            "method_peak_periods": dict(evidence.method_peak_periods),
            "random_seed": evidence.random_seed,
            "red_noise_score": evidence.red_noise_score,
            "series_count": evidence.series_count,
            "supporting_categories": list(evidence.supporting_categories),
            "total_categories": evidence.total_categories,
        },
    }


def _manual_override_payload(
    item: QuarterlyManualOverride,
) -> dict[str, object]:
    return {
        "cycle_id": item.cycle_id,
        "effective_date": item.effective_date.isoformat(),
        "override": {
            "authorized_by": item.override.authorized_by,
            "reason": item.override.reason,
            "requested_center": item.override.requested_center,
        },
    }


def _input_payload(pipeline_input: CyclePipelineInput) -> dict[str, object]:
    return {
        "annual_categories": dict(pipeline_input.annual_categories),
        "discovery_evidence": [
            _evidence_payload(item) for item in pipeline_input.discovery_evidence
        ],
        "manual_overrides": [
            _manual_override_payload(item)
            for item in pipeline_input.manual_overrides
        ],
        "monthly_categories": dict(pipeline_input.monthly_categories),
        "observations": [
            _observation_payload(record) for record in pipeline_input.observations
        ],
        "prior_model_versions": [
            serialize_cycle_model_version(version)
            for version in pipeline_input.prior_model_versions
        ],
        "schema_version": 2,
        "state_dates": [value.isoformat() for value in pipeline_input.state_dates],
        "verification_cutoffs": [
            value.isoformat() for value in pipeline_input.verification_cutoffs
        ],
    }


def _input_checksums(
    pipeline_input: CyclePipelineInput,
    *,
    strict_vintage: bool,
) -> dict[str, str]:
    payload = _input_payload(pipeline_input)
    components = {
        "annual_categories.json": payload["annual_categories"],
        "discovery_evidence.json": payload["discovery_evidence"],
        "manual_overrides.json": payload["manual_overrides"],
        "monthly_categories.json": payload["monthly_categories"],
        "observations.json": payload["observations"],
        "pipeline_options.json": {"strict_vintage": strict_vintage},
        "prior_model_versions.json": payload["prior_model_versions"],
        "state_dates.json": payload["state_dates"],
        "verification_cutoffs.json": payload["verification_cutoffs"],
    }
    return {
        name: sha256(canonical_json_bytes(value)).hexdigest()
        for name, value in sorted(components.items())
    }


def write_cycle_pipeline_input(
    input_dir: Path,
    pipeline_input: CyclePipelineInput,
) -> Path:
    """Write the deterministic offline CLI input bundle exclusively."""

    if not isinstance(pipeline_input, CyclePipelineInput):
        raise TypeError("pipeline_input must be CyclePipelineInput")
    directory = Path(input_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CYCLE_PIPELINE_INPUT_FILENAME
    try:
        output = path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(f"refuse accidental overwrite of {path}") from error
    with output:
        output.write(canonical_json_bytes(_input_payload(pipeline_input)) + b"\n")
    return path


def _parse_evidence(payload: object) -> QuarterlyDiscoveryEvidence:
    if not isinstance(payload, Mapping):
        raise TypeError("discovery evidence entry must be a mapping")
    evidence = payload["evidence"]
    if not isinstance(evidence, Mapping):
        raise TypeError("discovery evidence payload must be a mapping")
    return QuarterlyDiscoveryEvidence(
        cycle_id=payload["cycle_id"],
        effective_date=date.fromisoformat(str(payload["effective_date"])),
        evidence=DiscoveryEvidence(
            candidate_center=evidence["candidate_center"],
            bootstrap_period_low=evidence["bootstrap_period_low"],
            bootstrap_period_high=evidence["bootstrap_period_high"],
            red_noise_score=evidence["red_noise_score"],
            category_support=evidence["category_support"],
            macro_only_score=evidence["macro_only_score"],
            category_balanced_score=evidence["category_balanced_score"],
            method_agreement=evidence["method_agreement"],
            method_peak_periods=evidence["method_peak_periods"],
            supporting_categories=tuple(evidence["supporting_categories"]),
            total_categories=evidence["total_categories"],
            series_count=evidence["series_count"],
            random_seed=evidence["random_seed"],
        ),
    )


def _parse_manual_override(payload: object) -> QuarterlyManualOverride:
    if not isinstance(payload, Mapping) or set(payload) != {
        "cycle_id",
        "effective_date",
        "override",
    }:
        raise TypeError("manual override entry must be a canonical mapping")
    override = payload["override"]
    if not isinstance(override, Mapping) or set(override) != {
        "authorized_by",
        "reason",
        "requested_center",
    }:
        raise TypeError("manual override payload must be a canonical mapping")
    return QuarterlyManualOverride(
        cycle_id=payload["cycle_id"],
        effective_date=date.fromisoformat(str(payload["effective_date"])),
        override=ManualOverride(
            requested_center=override["requested_center"],
            authorized_by=override["authorized_by"],
            reason=override["reason"],
        ),
    )


def load_cycle_pipeline_input(input_dir: Path) -> CyclePipelineInput:
    """Load one deterministic offline bundle without network dependencies."""

    path = Path(input_dir) / CYCLE_PIPELINE_INPUT_FILENAME
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise FileNotFoundError(
            f"cycle pipeline input bundle does not exist: {path}"
        ) from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise ValueError("cycle pipeline input bundle must be a regular file")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("cycle pipeline input bundle is invalid JSON") from error
    if raw != canonical_json_bytes(payload) + b"\n":
        raise ValueError("cycle pipeline input bundle must be canonical JSON")
    base_keys = {
        "annual_categories",
        "discovery_evidence",
        "monthly_categories",
        "observations",
        "prior_model_versions",
        "schema_version",
        "state_dates",
        "verification_cutoffs",
    }
    if not isinstance(payload, Mapping):
        raise ValueError("cycle pipeline input bundle has invalid keys")
    schema_version = payload.get("schema_version")
    if schema_version == 1:
        expected_keys = base_keys
        manual_override_payloads: object = ()
    elif schema_version == 2:
        expected_keys = {*base_keys, "manual_overrides"}
        manual_override_payloads = payload.get("manual_overrides")
    else:
        raise ValueError("unsupported cycle pipeline input schema_version")
    if set(payload) != expected_keys:
        raise ValueError("cycle pipeline input bundle has invalid keys")
    try:
        manual_overrides = tuple(
            _parse_manual_override(item) for item in manual_override_payloads
        )
        return CyclePipelineInput(
            observations=tuple(
                Observation.model_validate(item) for item in payload["observations"]
            ),
            annual_categories=payload["annual_categories"],
            monthly_categories=payload["monthly_categories"],
            prior_model_versions=tuple(
                deserialize_cycle_model_version(item)
                for item in payload["prior_model_versions"]
            ),
            discovery_evidence=tuple(
                _parse_evidence(item) for item in payload["discovery_evidence"]
            ),
            state_dates=tuple(
                date.fromisoformat(str(value)) for value in payload["state_dates"]
            ),
            verification_cutoffs=tuple(
                date.fromisoformat(str(value))
                for value in payload["verification_cutoffs"]
            ),
            manual_overrides=manual_overrides,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("cycle pipeline input bundle failed validation") from error


def _write_json_product(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(f"refuse accidental overwrite of {path}") from error
    with output:
        output.write(canonical_json_bytes(payload) + b"\n")


def _version_product(
    versions: tuple[CycleModelVersion, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "versions": [serialize_cycle_model_version(version) for version in versions],
    }


def _require_secret_free(payload: object, *, label: str) -> None:
    rendered = canonical_json_bytes(payload).decode("utf-8")
    if redact_secrets(rendered) != rendered:
        raise _CycleBuildBlocked(
            _governance_failure(
                "secret_contract",
                f"{label} contains sensitive values and cannot be published",
            )
        )


def _existing_result(
    run_dir: Path,
    *,
    candidate_product: pd.DataFrame,
) -> CycleBuildResult | None:
    try:
        run_dir.lstat()
    except FileNotFoundError:
        return None
    try:
        acceptance = verify_published_cycle_run(run_dir)
    except CycleAcceptanceError as error:
        finding = _governance_failure(
            "schema_contract",
            f"existing immutable run failed M2 acceptance: {error}",
        )
        return CycleBuildResult(
            status=ReleaseStatus.BLOCKED,
            run_id=run_dir.name,
            publication_path=None,
            manifest=None,
            findings=(finding,),
            reused=False,
        )
    try:
        normalized_candidate = candidate_product.copy(deep=True)
        normalized_candidate["created_at"] = acceptance.manifest.created_at
        with tempfile.TemporaryDirectory(prefix=".m2-reuse-") as temporary:
            candidate_dir = Path(temporary) / acceptance.manifest.run_id
            candidate_dir.mkdir()
            write_cycle_phase_vintage(
                candidate_dir,
                normalized_candidate,
                context=acceptance.manifest,
            )
            candidate_product_checksum = collect_product_checksums(candidate_dir)[
                CYCLE_PHASE_VINTAGE_FILENAME
            ]
    except Exception as error:
        finding = _schema_failure(
            "current candidate cycle product checksum failed: " + str(error)
        )
        return CycleBuildResult(
            status=ReleaseStatus.BLOCKED,
            run_id=run_dir.name,
            publication_path=None,
            manifest=None,
            findings=(finding,),
            reused=False,
        )
    published_checksum = acceptance.manifest.product_checksums.get(
        CYCLE_PHASE_VINTAGE_FILENAME
    )
    if published_checksum != candidate_product_checksum:
        finding = _schema_failure(
            "current candidate cycle product checksum differs from the existing "
            "immutable run"
        )
        return CycleBuildResult(
            status=ReleaseStatus.BLOCKED,
            run_id=run_dir.name,
            publication_path=None,
            manifest=None,
            findings=(finding,),
            reused=False,
        )
    return CycleBuildResult(
        status=ReleaseStatus.LIVE,
        run_id=acceptance.manifest.run_id,
        publication_path=run_dir,
        manifest=acceptance.manifest,
        findings=acceptance.findings,
        reused=True,
    )


def _publication_blocked_result(
    *,
    context: RunContext,
    report: CycleVerificationReport,
    error: Exception,
) -> CycleBuildResult:
    replacement = _schema_failure(str(error))
    findings_by_check = {
        finding.check: finding for finding in report.findings
    }
    findings_by_check[replacement.check] = replacement
    findings = tuple(findings_by_check[check] for check in MANDATORY_CHECKS)
    return CycleBuildResult(
        status=ReleaseStatus.BLOCKED,
        run_id=context.run_id,
        publication_path=None,
        manifest=None,
        findings=findings,
        reused=False,
    )


def publish(
    *,
    product_root: Path,
    context: RunContext,
    registry_bundle: RegistryBundle,
    governed: GovernedCycleModels,
    report: CycleVerificationReport,
    verification_plan: VerificationPlan,
) -> CycleBuildResult:
    """Publish a passing M2 run only through the atomic publisher."""

    if not report.passed:
        return CycleBuildResult(
            status=ReleaseStatus.BLOCKED,
            run_id=context.run_id,
            publication_path=None,
            manifest=None,
            findings=report.findings,
            reused=False,
        )
    try:
        snapshots = registry_snapshot_payloads(registry_bundle)

        def write_staging(staging_dir: Path) -> None:
            for filename, payload in snapshots.items():
                _write_json_product(staging_dir / filename, payload)
            _write_json_product(
                staging_dir / CYCLE_MODEL_VERSIONS_FILENAME,
                _version_product(governed.model_versions),
            )
            if report.product is None:
                raise ValueError("verified cycle product is unavailable")
            write_cycle_phase_vintage(
                staging_dir,
                report.product,
                context=context,
            )
            write_quality_findings(staging_dir, report.findings)
            write_verification_plan(staging_dir, verification_plan)

        def validate_staging(
            staging_dir: Path,
            manifest: RunManifest,
        ) -> None:
            acceptance = verify_published_cycle_run(staging_dir)
            if acceptance.manifest != manifest:
                raise ValueError("staged M2 acceptance manifest mismatch")

        manifest = publish_run(
            Path(product_root),
            context,
            write_staging=write_staging,
            validate_staging=validate_staging,
        )
    except FileExistsError:
        if report.product_checksum is None:
            return _publication_blocked_result(
                context=context,
                report=report,
                error=ValueError("verified cycle product checksum is unavailable"),
            )
        existing = _existing_result(
            Path(product_root) / "runs" / context.run_id,
            candidate_product=report.product,
        )
        if existing is not None:
            return existing
        return _publication_blocked_result(
            context=context,
            report=report,
            error=FileExistsError("immutable run destination already exists"),
        )
    except Exception as error:
        return _publication_blocked_result(
            context=context,
            report=report,
            error=error,
        )
    run_dir = Path(product_root) / "runs" / manifest.run_id
    return CycleBuildResult(
        status=ReleaseStatus.LIVE,
        run_id=manifest.run_id,
        publication_path=run_dir,
        manifest=manifest,
        findings=report.findings,
        reused=False,
    )


def _created_at(value: datetime | None) -> datetime:
    timestamp = datetime.now(timezone.utc) if value is None else value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


def build_cycles(
    pipeline_input: CyclePipelineInput,
    *,
    registry_bundle: RegistryBundle,
    product_root: Path,
    as_of: date,
    strict_vintage: bool,
    created_at: datetime | None = None,
    verifiers: CycleVerifiers | None = None,
) -> CycleBuildResult:
    """Run load → recalibrate → estimate → verify → publish."""

    try:
        normalized_as_of = _normalize_as_of(as_of)
        try:
            validate_registry_bundle_contract(registry_bundle)
        except (TypeError, ValueError) as error:
            raise _CycleBuildBlocked(
                _governance_failure(
                    "registry_contract",
                    f"registry cross-contract validation failed: {error}",
                )
            ) from error
        loaded = load_vintage(
            pipeline_input,
            as_of=normalized_as_of,
            strict_vintage=strict_vintage,
        )
        verification_plan = _prepare_verification_plan(
            pipeline_input,
            as_of=normalized_as_of,
            interpretations=loaded.interpretations,
            strict_vintage=strict_vintage,
        )
        governed = recalibrate_if_due(
            pipeline_input,
            registry_bundle=registry_bundle,
            as_of=normalized_as_of,
        )
        snapshots = registry_snapshot_payloads(registry_bundle)
        _require_secret_free(snapshots, label="registry snapshots")
        _require_secret_free(
            _version_product(governed.model_versions),
            label="cycle model versions",
        )
        estimated = estimate_states(
            pipeline_input,
            loaded,
            governed,
            strict_vintage=strict_vintage,
        )
    except _CycleBuildBlocked as error:
        return CycleBuildResult(
            status=ReleaseStatus.BLOCKED,
            run_id=None,
            publication_path=None,
            manifest=None,
            findings=(error.finding,),
            reused=False,
        )

    context = RunContext.create(
        as_of=normalized_as_of,
        data_vintage=loaded.data_vintage,
        model_version=governed.model_version_identity,
        config=registry_config_payload(
            snapshots,
            verification_plan=verification_plan,
        ),
        input_checksums=_input_checksums(
            pipeline_input,
            strict_vintage=strict_vintage,
        ),
        quality_summary={
            "failed": 0,
            "mandatory": len(MANDATORY_CHECKS),
            "passed": len(MANDATORY_CHECKS),
            "total": len(MANDATORY_CHECKS),
        },
        created_at=_created_at(created_at),
    )
    report = verify(
        pipeline_input,
        estimated,
        context=context,
        product_root=Path(product_root),
        verification_plan=verification_plan,
        verifiers=verifiers,
    )
    if report.passed:
        run_dir = Path(product_root) / "runs" / context.run_id
        existing = _existing_result(
            run_dir,
            candidate_product=report.product,
        )
        if existing is not None:
            return existing
    return publish(
        product_root=Path(product_root),
        context=context,
        registry_bundle=registry_bundle,
        governed=governed,
        report=report,
        verification_plan=verification_plan,
    )


__all__ = [
    "CYCLE_PIPELINE_INPUT_FILENAME",
    "CycleBuildResult",
    "CyclePipelineInput",
    "CycleVerificationReport",
    "CycleVerifiers",
    "EstimatedCycleStates",
    "GovernedCycleModels",
    "LoadedCycleVintage",
    "QuarterlyDiscoveryEvidence",
    "QuarterlyManualOverride",
    "VerificationPlan",
    "build_cycles",
    "estimate_states",
    "load_cycle_pipeline_input",
    "load_vintage",
    "publish",
    "recalibrate_if_due",
    "verify",
    "write_cycle_pipeline_input",
]
