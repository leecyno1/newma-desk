"""M2 cycle quality gates and acceptance verification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from numbers import Real
from pathlib import Path
import stat
import sys
from types import MappingProxyType

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError

from seven_cycle_platform.contracts.arrow import (
    CYCLE_PHASE_VINTAGE_SCHEMA,
    QUALITY_FINDING_SCHEMA,
)
from seven_cycle_platform.cycles.engine import SevenCycleEngine
from seven_cycle_platform.cycles.model_version import (
    CycleModelVersion,
    ManualOverride,
    RecalibrationReason,
    RecalibrationStatus,
)
from seven_cycle_platform.cycles.vintage import (
    CYCLE_VINTAGE_COLUMNS,
    reconstruct_cycle_vintage,
)
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.products.cycle_phase import (
    CYCLE_PHASE_VINTAGE_FILENAME,
    validate_cycle_phase_vintage,
)
from seven_cycle_platform.registry.models import (
    AssetRegistry,
    ChannelRegistry,
    CycleRegistry,
    IndicatorRegistry,
    RegistryBundle,
)
from seven_cycle_platform.registry.loader import (
    _validate_assets,
    _validate_channels,
    _validate_cycles,
    _validate_indicators,
)
from seven_cycle_platform.security import redact_secrets
from seven_cycle_platform.storage.manifest import (
    RunManifest,
    load_manifest,
    sha256_file,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import (
    canonical_json_bytes,
    compute_config_hash,
)
from seven_cycle_platform.types import VintageKind


QUALITY_FINDINGS_FILENAME = "quality_findings.parquet"
CYCLE_MODEL_VERSIONS_FILENAME = "cycle_model_versions.json"
VERIFICATION_PLAN_FILENAME = "verification_plan.json"
VERIFICATION_PLAN_SCHEMA_VERSION = 2
CYCLE_VERIFIER_PROFILE = "m2-cycle-verifier-v1"
NUMERIC_TOLERANCE = 1e-10
MANDATORY_CHECKS = (
    "cutoff_reconstruction",
    "schema_contract",
    "no_lookahead",
)
_CYCLE_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
_INTERPRETATION_ORDER = (
    VintageKind.REALTIME,
    VintageKind.LATEST_HISTORICAL,
)
_ALGORITHM_FINGERPRINT_LENGTH = 64
_ALGORITHM_RUNTIME_DISTRIBUTIONS = (
    "numpy",
    "pandas",
    "pyarrow",
    "pydantic",
    "scipy",
    "statsmodels",
)
_NUMERIC_RECONSTRUCTION_COLUMNS = (
    "angle",
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "innovation",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
    "effective_cycles",
    "observed_observations",
    "member_breadth",
    "category_breadth",
    "total_members",
    "total_categories",
)
_EXACT_RECONSTRUCTION_COLUMNS = tuple(
    column
    for column in CYCLE_VINTAGE_COLUMNS
    if column not in _NUMERIC_RECONSTRUCTION_COLUMNS
)
_REGISTRY_FILES = {
    "registries/assets.json": ("assets", AssetRegistry),
    "registries/channels.json": ("channels", ChannelRegistry),
    "registries/cycles.json": ("cycles", CycleRegistry),
    "registries/indicators.json": ("indicators", IndicatorRegistry),
}


class CycleAcceptanceError(ValueError):
    """Raised when a self-consistent run fails an M2 product contract."""


def _nonblank(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-blank string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-blank string")
    return normalized


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


@dataclass(frozen=True)
class QualityFinding:
    """One deterministic row in the stable quality finding product."""

    entity_id: str
    check: str
    severity: str
    status: str
    message: str
    observed_value: float
    threshold: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entity_id",
            _nonblank(self.entity_id, name="entity_id"),
        )
        object.__setattr__(self, "check", _nonblank(self.check, name="check"))
        severity = _nonblank(self.severity, name="severity").lower()
        if severity != "mandatory":
            raise ValueError("M2 release findings must be mandatory")
        object.__setattr__(self, "severity", severity)
        status = _nonblank(self.status, name="status").upper()
        if status not in {"PASS", "FAIL"}:
            raise ValueError("status must be PASS or FAIL")
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "message",
            redact_secrets(_nonblank(self.message, name="message")),
        )
        object.__setattr__(
            self,
            "observed_value",
            _finite(self.observed_value, name="observed_value"),
        )
        object.__setattr__(
            self,
            "threshold",
            _finite(self.threshold, name="threshold"),
        )

    def to_record(self) -> dict[str, object]:
        """Return the exact Arrow row representation."""

        return {
            "entity_id": self.entity_id,
            "check": self.check,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "observed_value": self.observed_value,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class VerificationPlan:
    """Canonical auditable plan for mandatory M2 verification."""

    schema_version: int
    verifier_profile: str
    algorithm_fingerprint: str
    interpretations: tuple[VintageKind, ...]
    mandatory_checks: tuple[str, ...]
    verification_cutoffs: tuple[date, ...]
    numeric_tolerance: float
    strict_vintage: bool

    def __post_init__(self) -> None:
        if self.schema_version != VERIFICATION_PLAN_SCHEMA_VERSION:
            raise ValueError("unsupported verification plan schema_version")
        if self.verifier_profile != CYCLE_VERIFIER_PROFILE:
            raise ValueError("verification plan verifier profile mismatch")
        if (
            not isinstance(self.algorithm_fingerprint, str)
            or len(self.algorithm_fingerprint) != _ALGORITHM_FINGERPRINT_LENGTH
            or any(
                character not in "0123456789abcdef"
                for character in self.algorithm_fingerprint
            )
        ):
            raise ValueError(
                "verification plan algorithm_fingerprint must be a lowercase SHA-256"
            )
        if not isinstance(self.interpretations, tuple) or not self.interpretations:
            raise TypeError("verification plan interpretations must be a tuple")
        if any(
            not isinstance(interpretation, VintageKind)
            for interpretation in self.interpretations
        ):
            raise TypeError(
                "verification plan interpretations must contain VintageKind values"
            )
        expected_interpretations = tuple(
            interpretation
            for interpretation in _INTERPRETATION_ORDER
            if interpretation in self.interpretations
        )
        if self.interpretations != expected_interpretations:
            raise ValueError(
                "verification plan interpretations must be unique and ordered"
            )
        if VintageKind.REALTIME not in self.interpretations:
            raise ValueError("verification plan must include realtime interpretation")
        if self.mandatory_checks != MANDATORY_CHECKS:
            raise ValueError("verification plan mandatory checks mismatch")
        cutoffs = _dates(
            self.verification_cutoffs,
            name="verification_cutoffs",
        )
        if not any(
            cutoff.month == 12 and cutoff.day == 31 for cutoff in cutoffs
        ):
            raise ValueError(
                "verification plan requires a calendar year-end cutoff"
            )
        if not any(
            pd.Timestamp(cutoff).is_month_end
            and not (cutoff.month == 12 and cutoff.day == 31)
            for cutoff in cutoffs
        ):
            raise ValueError(
                "verification plan requires a non-year-end month-end cutoff"
            )
        tolerance = _finite(
            self.numeric_tolerance,
            name="numeric_tolerance",
        )
        if tolerance != NUMERIC_TOLERANCE:
            raise ValueError("verification plan numeric tolerance mismatch")
        if not isinstance(self.strict_vintage, bool):
            raise TypeError("strict_vintage must be a boolean")
        object.__setattr__(self, "verification_cutoffs", cutoffs)
        object.__setattr__(self, "numeric_tolerance", tolerance)

    def to_payload(self) -> dict[str, object]:
        """Return the exact canonical JSON product payload."""

        return {
            "algorithm_fingerprint": self.algorithm_fingerprint,
            "interpretations": [
                interpretation.value for interpretation in self.interpretations
            ],
            "mandatory_checks": list(self.mandatory_checks),
            "numeric_tolerance": self.numeric_tolerance,
            "schema_version": self.schema_version,
            "strict_vintage": self.strict_vintage,
            "verification_cutoffs": [
                cutoff.isoformat() for cutoff in self.verification_cutoffs
            ],
            "verifier_profile": self.verifier_profile,
        }


def create_verification_plan(
    verification_cutoffs: tuple[date, ...],
    *,
    algorithm_fingerprint: str,
    interpretations: tuple[VintageKind, ...],
    strict_vintage: bool,
) -> VerificationPlan:
    """Create the fixed-profile plan used by build and acceptance."""

    return VerificationPlan(
        schema_version=VERIFICATION_PLAN_SCHEMA_VERSION,
        verifier_profile=CYCLE_VERIFIER_PROFILE,
        algorithm_fingerprint=algorithm_fingerprint,
        interpretations=interpretations,
        mandatory_checks=MANDATORY_CHECKS,
        verification_cutoffs=verification_cutoffs,
        numeric_tolerance=NUMERIC_TOLERANCE,
        strict_vintage=strict_vintage,
    )


def m2_algorithm_fingerprint() -> str:
    """Hash the complete local M2 algorithm surface without absolute paths."""

    package_root = Path(__file__).resolve().parents[1]
    component_paths = {
        *(package_root / "cycles").rglob("*.py"),
        *(package_root / "data").rglob("*.py"),
        *(package_root / "registry").rglob("*.py"),
        package_root / "contracts" / "arrow.py",
        package_root / "pipeline" / "cycles.py",
        package_root / "products" / "cycle_phase.py",
        package_root / "types.py",
        package_root / "verification" / "cycles.py",
    }
    digest = sha256()
    try:
        for path in sorted(
            component_paths,
            key=lambda value: value.relative_to(package_root).as_posix(),
        ):
            relative_name = path.relative_to(package_root).as_posix()
            source = path.read_bytes().replace(b"\r\n", b"\n")
            digest.update(relative_name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(source)
            digest.update(b"\0")
    except OSError as error:
        raise ValueError("M2 algorithm fingerprint sources are unavailable") from error
    try:
        runtime_versions = {
            "python": ".".join(str(value) for value in sys.version_info[:3]),
            **{
                distribution: version(distribution)
                for distribution in _ALGORITHM_RUNTIME_DISTRIBUTIONS
            },
        }
    except PackageNotFoundError as error:
        raise ValueError("M2 algorithm runtime fingerprint is unavailable") from error
    digest.update(b"runtime_versions\0")
    digest.update(canonical_json_bytes(runtime_versions))
    return digest.hexdigest()


@dataclass(frozen=True)
class CycleVerificationRequest:
    """Immutable inputs shared by causal M2 verification gates."""

    observations: tuple[Observation, ...]
    engine: SevenCycleEngine
    annual_categories: Mapping[str, str]
    monthly_categories: Mapping[str, str]
    interpretations: tuple[VintageKind, ...]
    verification_cutoffs: tuple[date, ...]
    numeric_tolerance: float
    strict_vintage: bool

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or any(
            not isinstance(record, Observation) for record in self.observations
        ):
            raise TypeError("observations must be a tuple of Observation records")
        if not isinstance(self.engine, SevenCycleEngine):
            raise TypeError("engine must be a SevenCycleEngine")
        if not isinstance(self.strict_vintage, bool):
            raise TypeError("strict_vintage must be a boolean")
        annual = _category_map(self.annual_categories, name="annual_categories")
        monthly = _category_map(
            self.monthly_categories,
            name="monthly_categories",
        )
        if not isinstance(self.interpretations, tuple) or not self.interpretations:
            raise TypeError("interpretations must be a non-empty tuple")
        if any(
            interpretation not in _INTERPRETATION_ORDER
            for interpretation in self.interpretations
        ):
            raise ValueError("unsupported verification interpretation")
        if len(self.interpretations) != len(set(self.interpretations)):
            raise ValueError("verification interpretations must be unique")
        cutoffs = _dates(self.verification_cutoffs, name="verification_cutoffs")
        tolerance = _finite(
            self.numeric_tolerance,
            name="numeric_tolerance",
        )
        if tolerance != NUMERIC_TOLERANCE:
            raise ValueError("numeric_tolerance must match the verifier profile")
        object.__setattr__(self, "annual_categories", MappingProxyType(annual))
        object.__setattr__(self, "monthly_categories", MappingProxyType(monthly))
        object.__setattr__(
            self,
            "interpretations",
            tuple(self.interpretations),
        )
        object.__setattr__(self, "verification_cutoffs", cutoffs)
        object.__setattr__(self, "numeric_tolerance", tolerance)


RequestGate = Callable[[CycleVerificationRequest], QualityFinding]
SchemaGate = Callable[[Path, RunManifest], QualityFinding]


@dataclass(frozen=True)
class CycleVerifiers:
    """Injectable mandatory gate implementations."""

    cutoff_reconstruction: RequestGate
    schema_contract: SchemaGate
    no_lookahead: RequestGate

    def __post_init__(self) -> None:
        for name in MANDATORY_CHECKS:
            attribute = getattr(self, name)
            if not callable(attribute):
                raise TypeError(f"{name} verifier must be callable")


@dataclass(frozen=True)
class CycleAcceptanceReport:
    """Validated published M2 run metadata and quality findings."""

    manifest: RunManifest
    findings: tuple[QualityFinding, ...]
    files_verified: int
    checks_verified: int


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


def _dates(value: object, *, name: str) -> tuple[date, ...]:
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


def _finding(
    check: str,
    *,
    passed: bool,
    message: str,
    observed_value: float,
    threshold: float,
) -> QualityFinding:
    return QualityFinding(
        entity_id="seven_cycle_platform",
        check=check,
        severity="mandatory",
        status="PASS" if passed else "FAIL",
        message=message,
        observed_value=observed_value,
        threshold=threshold,
    )


def serialize_cycle_model_version(
    version: CycleModelVersion,
) -> dict[str, object]:
    """Serialize one governed version without losing audit fields."""

    if not isinstance(version, CycleModelVersion):
        raise TypeError("version must be a CycleModelVersion")
    manual_override = None
    if version.manual_override is not None:
        manual_override = {
            "authorized_by": version.manual_override.authorized_by,
            "reason": version.manual_override.reason,
            "requested_center": version.manual_override.requested_center,
        }
    return {
        "candidate_center": version.candidate_center,
        "cycle_id": version.cycle_id,
        "effective_date": version.effective_date.isoformat(),
        "effective_quarter": version.effective_quarter,
        "evidence_metrics": dict(version.evidence_metrics),
        "manual_override": manual_override,
        "new_band": list(version.new_band),
        "new_center": version.new_center,
        "new_confidence": version.new_confidence,
        "old_band": list(version.old_band),
        "old_center": version.old_center,
        "old_confidence": version.old_confidence,
        "previous_version_id": version.previous_version_id,
        "reason_code": version.reason_code.value,
        "reason_codes": [reason.value for reason in version.reason_codes],
        "rejection_reason": (
            None
            if version.rejection_reason is None
            else version.rejection_reason.value
        ),
        "status": version.status.value,
        "version_id": version.version_id,
    }


def deserialize_cycle_model_version(payload: object) -> CycleModelVersion:
    """Parse and revalidate one serialized governed version."""

    if not isinstance(payload, Mapping):
        raise TypeError("cycle model version must be a mapping")
    manual_payload = payload.get("manual_override")
    manual_override = None
    if manual_payload is not None:
        if not isinstance(manual_payload, Mapping):
            raise TypeError("manual_override must be a mapping or null")
        manual_override = ManualOverride(
            requested_center=manual_payload["requested_center"],
            authorized_by=manual_payload["authorized_by"],
            reason=manual_payload["reason"],
        )
    rejection_value = payload.get("rejection_reason")
    version = CycleModelVersion(
        cycle_id=payload["cycle_id"],
        effective_date=date.fromisoformat(str(payload["effective_date"])),
        old_center=payload["old_center"],
        new_center=payload["new_center"],
        old_band=tuple(payload["old_band"]),
        new_band=tuple(payload["new_band"]),
        old_confidence=payload["old_confidence"],
        new_confidence=payload["new_confidence"],
        candidate_center=payload["candidate_center"],
        status=RecalibrationStatus(payload["status"]),
        reason_code=RecalibrationReason(payload["reason_code"]),
        rejection_reason=(
            None
            if rejection_value is None
            else RecalibrationReason(rejection_value)
        ),
        reason_codes=tuple(
            RecalibrationReason(reason) for reason in payload["reason_codes"]
        ),
        evidence_metrics=payload["evidence_metrics"],
        manual_override=manual_override,
        previous_version_id=payload.get("previous_version_id"),
    )
    if payload.get("effective_quarter") != version.effective_quarter:
        raise ValueError("effective_quarter does not match the governed version")
    if payload.get("version_id") != version.version_id:
        raise ValueError("version_id does not match the governed version")
    return version


def cycle_model_set_identity(
    versions: tuple[CycleModelVersion, ...],
) -> str:
    """Derive the run model identity from all seven current versions."""

    ordered = tuple(sorted(versions, key=lambda version: version.cycle_id))
    if tuple(version.cycle_id for version in ordered) != _CYCLE_IDS:
        raise ValueError("model identity requires exactly one version for C1-C7")
    digest = sha256(
        canonical_json_bytes(
            {"version_ids": [version.version_id for version in ordered]}
        )
    ).hexdigest()
    return f"m2-cycle-model-set-{digest[:20]}"


def registry_snapshot_payloads(
    bundle: RegistryBundle,
) -> dict[str, dict[str, object]]:
    """Return deterministic JSON payloads for all governed registries."""

    if not isinstance(bundle, RegistryBundle):
        raise TypeError("bundle must be a RegistryBundle")
    definitions = (
        ("registries/assets.json", "assets", "asset_id", bundle.assets),
        ("registries/channels.json", "channels", "channel_id", bundle.channels),
        ("registries/cycles.json", "cycles", "cycle_id", bundle.cycles),
        (
            "registries/indicators.json",
            "indicators",
            "indicator_id",
            bundle.indicators,
        ),
    )
    snapshots: dict[str, dict[str, object]] = {}
    for filename, key, identifier, records in definitions:
        snapshots[filename] = {
            "schema_version": 1,
            key: [
                record.model_dump(mode="json")
                for record in sorted(
                    records,
                    key=lambda record: str(getattr(record, identifier)),
                )
            ],
        }
    return snapshots


def validate_registry_bundle_contract(bundle: RegistryBundle) -> None:
    """Apply the same cross-registry governance used by YAML loading."""

    if not isinstance(bundle, RegistryBundle):
        raise TypeError("bundle must be a RegistryBundle")
    _validate_cycles(bundle.cycles)
    cycle_ids = {cycle.cycle_id for cycle in bundle.cycles}
    _validate_indicators(bundle.indicators, cycle_ids)
    _validate_channels(bundle.channels, bundle.indicators)
    _validate_assets(bundle.assets)


def registry_config_payload(
    snapshots: Mapping[str, Mapping[str, object]],
    *,
    verification_plan: VerificationPlan,
) -> dict[str, object]:
    """Build the exact unhashed registry configuration payload."""

    if not isinstance(verification_plan, VerificationPlan):
        raise TypeError("verification_plan must be VerificationPlan")
    return {
        "registry_snapshots": {
            filename: dict(snapshots[filename]) for filename in sorted(snapshots)
        },
        "verification_plan": verification_plan.to_payload(),
    }


def _canonical_file_payload(path: Path) -> object:
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise CycleAcceptanceError(f"required M2 file is missing: {path.name}") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise CycleAcceptanceError(f"required M2 file is not regular: {path.name}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CycleAcceptanceError(f"invalid canonical JSON: {path.name}") from error
    if raw != canonical_json_bytes(payload) + b"\n":
        raise CycleAcceptanceError(f"JSON is not canonical: {path.name}")
    return payload


def _quality_table(findings: tuple[QualityFinding, ...]) -> pa.Table:
    records = [finding.to_record() for finding in findings]
    arrays = [
        pa.array(
            [record[field.name] for record in records],
            type=field.type,
            from_pandas=True,
        )
        for field in QUALITY_FINDING_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=QUALITY_FINDING_SCHEMA)


def write_quality_findings(
    run_dir: Path,
    findings: tuple[QualityFinding, ...],
) -> Path:
    """Write canonical mandatory findings without overwriting a product."""

    if not isinstance(findings, tuple) or not findings:
        raise TypeError("findings must be a non-empty tuple")
    if any(not isinstance(finding, QualityFinding) for finding in findings):
        raise TypeError("findings must contain QualityFinding records")
    ordered = tuple(
        sorted(
            findings,
            key=lambda finding: (
                MANDATORY_CHECKS.index(finding.check)
                if finding.check in MANDATORY_CHECKS
                else len(MANDATORY_CHECKS),
                finding.check,
            ),
        )
    )
    path = Path(run_dir) / QUALITY_FINDINGS_FILENAME
    try:
        output = path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(f"refuse accidental overwrite of {path}") from error
    try:
        with output:
            pq.write_table(
                _quality_table(ordered),
                output,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
        if pq.read_schema(path) != QUALITY_FINDING_SCHEMA:
            raise ValueError("persisted quality finding schema mismatch")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def read_quality_findings(path: Path) -> tuple[QualityFinding, ...]:
    """Read and validate the stable quality finding product."""

    try:
        table = pq.read_table(path)
    except Exception as error:
        raise CycleAcceptanceError(
            "quality finding product is unreadable"
        ) from error
    if table.schema != QUALITY_FINDING_SCHEMA:
        raise CycleAcceptanceError("quality finding Arrow schema mismatch")
    try:
        findings = tuple(QualityFinding(**record) for record in table.to_pylist())
    except (TypeError, ValueError) as error:
        raise CycleAcceptanceError("invalid quality finding rows") from error
    return findings


def write_verification_plan(
    run_dir: Path,
    plan: VerificationPlan,
) -> Path:
    """Write the canonical verification plan exclusively."""

    if not isinstance(plan, VerificationPlan):
        raise TypeError("plan must be VerificationPlan")
    path = Path(run_dir) / VERIFICATION_PLAN_FILENAME
    try:
        output = path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(f"refuse accidental overwrite of {path}") from error
    with output:
        output.write(canonical_json_bytes(plan.to_payload()) + b"\n")
    return path


def load_verification_plan(run_dir: Path) -> VerificationPlan:
    """Load and validate one canonical published verification plan."""

    payload = _canonical_file_payload(Path(run_dir) / VERIFICATION_PLAN_FILENAME)
    required_keys = {
        "algorithm_fingerprint",
        "interpretations",
        "mandatory_checks",
        "numeric_tolerance",
        "schema_version",
        "strict_vintage",
        "verification_cutoffs",
        "verifier_profile",
    }
    if not isinstance(payload, Mapping) or set(payload) != required_keys:
        raise CycleAcceptanceError("invalid verification plan product")
    try:
        return VerificationPlan(
            schema_version=payload["schema_version"],
            verifier_profile=payload["verifier_profile"],
            algorithm_fingerprint=payload["algorithm_fingerprint"],
            interpretations=tuple(
                VintageKind(value) for value in payload["interpretations"]
            ),
            mandatory_checks=tuple(payload["mandatory_checks"]),
            verification_cutoffs=tuple(
                date.fromisoformat(str(value))
                for value in payload["verification_cutoffs"]
            ),
            numeric_tolerance=payload["numeric_tolerance"],
            strict_vintage=payload["strict_vintage"],
        )
    except (TypeError, ValueError) as error:
        raise CycleAcceptanceError("verification plan contract failed") from error


def _sort_reconstruction(values: pd.DataFrame) -> pd.DataFrame:
    return values.sort_values(
        ["date", "cycle_id", "vintage"],
        kind="stable",
    ).reset_index(drop=True)


def _compare_reconstruction(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    numeric_tolerance: float,
) -> None:
    if tuple(actual.columns) != CYCLE_VINTAGE_COLUMNS:
        raise AssertionError("full reconstruction does not use the 24-column contract")
    if tuple(expected.columns) != CYCLE_VINTAGE_COLUMNS:
        raise AssertionError(
            "comparison reconstruction does not use the 24-column contract"
        )
    left = _sort_reconstruction(actual)
    right = _sort_reconstruction(expected)
    pd.testing.assert_frame_equal(
        left.loc[:, _EXACT_RECONSTRUCTION_COLUMNS],
        right.loc[:, _EXACT_RECONSTRUCTION_COLUMNS],
        check_exact=True,
    )
    for column in _NUMERIC_RECONSTRUCTION_COLUMNS:
        left_values = left[column].to_numpy(dtype="float64")
        right_values = right[column].to_numpy(dtype="float64")
        if np.isnan(left_values).tolist() != np.isnan(right_values).tolist():
            raise AssertionError(f"{column} missingness differs")
        np.testing.assert_allclose(
            left_values,
            right_values,
            rtol=0.0,
            atol=numeric_tolerance,
            equal_nan=True,
        )


def _reconstruct(
    request: CycleVerificationRequest,
    observations: tuple[Observation, ...],
    dates: tuple[date, ...],
    interpretation: VintageKind,
) -> pd.DataFrame:
    return reconstruct_cycle_vintage(
        observations,
        engine=request.engine,
        annual_categories=request.annual_categories,
        monthly_categories=request.monthly_categories,
        as_of=dates,
        strict=request.strict_vintage,
        interpretation=interpretation,
    )


def verify_cutoff_reconstruction(
    request: CycleVerificationRequest,
) -> QualityFinding:
    """Compare full and physically truncated archives at every cutoff."""

    try:
        for interpretation in request.interpretations:
            for cutoff in request.verification_cutoffs:
                dates = tuple(
                    date_value
                    for date_value in request.verification_cutoffs
                    if date_value <= cutoff
                )
                truncated = tuple(
                    record
                    for record in request.observations
                    if record.release_date <= cutoff
                    and record.vintage_date <= cutoff
                )
                _compare_reconstruction(
                    _reconstruct(
                        request,
                        request.observations,
                        dates,
                        interpretation,
                    ),
                    _reconstruct(
                        request,
                        truncated,
                        dates,
                        interpretation,
                    ),
                    numeric_tolerance=request.numeric_tolerance,
                )
    except Exception as error:
        total_cases = len(request.verification_cutoffs) * len(
            request.interpretations
        )
        return _finding(
            "cutoff_reconstruction",
            passed=False,
            message=f"cutoff reconstruction failed: {redact_secrets(str(error))}",
            observed_value=0.0,
            threshold=float(total_cases),
        )
    count = len(request.verification_cutoffs) * len(request.interpretations)
    return _finding(
        "cutoff_reconstruction",
        passed=True,
        message=f"full and truncated archives match across {count} cases",
        observed_value=float(count),
        threshold=float(count),
    )


def _next_annual_date(
    request: CycleVerificationRequest,
    entity_id: str,
    cutoff: date,
) -> date:
    years = [
        record.observation_date.year
        for record in request.observations
        if record.entity_id == entity_id
    ]
    return date(max(max(years, default=cutoff.year), cutoff.year) + 1, 12, 31)


def _next_monthly_date(
    request: CycleVerificationRequest,
    entity_id: str,
    cutoff: date,
) -> date:
    timestamps = [
        pd.Timestamp(record.observation_date)
        for record in request.observations
        if record.entity_id == entity_id
    ]
    latest = max(timestamps, default=pd.Timestamp(cutoff))
    return (latest + pd.offsets.MonthEnd(1)).date()


def _probe_observation(
    request: CycleVerificationRequest,
    *,
    entity_id: str,
    observation_date: date,
    lag_days: int,
    vintage_kind: VintageKind,
) -> Observation:
    candidates = [
        record
        for record in request.observations
        if record.entity_id == entity_id
    ]
    if not candidates:
        raise ValueError(f"cannot build a no-lookahead probe for {entity_id}")
    template = candidates[-1]
    release_date = observation_date + timedelta(days=lag_days)
    retrieval_time = datetime(
        release_date.year,
        release_date.month,
        release_date.day,
        tzinfo=timezone.utc,
    )
    return Observation(
        entity_id=entity_id,
        observation_date=observation_date,
        release_date=release_date,
        vintage_date=release_date,
        value=float(template.value + 1_000_000.0),
        unit=template.unit,
        source=template.source,
        retrieval_time=retrieval_time,
        revision_number=0,
        quality_status=template.quality_status,
        vintage_kind=vintage_kind,
    )


def _perturbed_future_archive(
    request: CycleVerificationRequest,
    cutoff: date,
    interpretation: VintageKind,
) -> tuple[Observation, ...]:
    perturbed = tuple(
        record.model_copy(
            update={"value": float(record.value + 100_000.0 + position)}
        )
        if record.release_date > cutoff or record.vintage_date > cutoff
        else record
        for position, record in enumerate(request.observations, start=1)
    )
    annual_entity = sorted(request.annual_categories)[0]
    monthly_entity = sorted(request.monthly_categories)[0]
    probes = (
        _probe_observation(
            request,
            entity_id=annual_entity,
            observation_date=_next_annual_date(request, annual_entity, cutoff),
            lag_days=90,
            vintage_kind=interpretation,
        ),
        _probe_observation(
            request,
            entity_id=monthly_entity,
            observation_date=_next_monthly_date(request, monthly_entity, cutoff),
            lag_days=10,
            vintage_kind=interpretation,
        ),
    )
    return (*perturbed, *probes)


def verify_no_lookahead(request: CycleVerificationRequest) -> QualityFinding:
    """Perturb and append future rows, then require historical invariance."""

    try:
        for interpretation in request.interpretations:
            for cutoff in request.verification_cutoffs:
                dates = tuple(
                    date_value
                    for date_value in request.verification_cutoffs
                    if date_value <= cutoff
                )
                baseline = _reconstruct(
                    request,
                    request.observations,
                    dates,
                    interpretation,
                )
                perturbed = _reconstruct(
                    request,
                    _perturbed_future_archive(
                        request,
                        cutoff,
                        interpretation,
                    ),
                    dates,
                    interpretation,
                )
                _compare_reconstruction(
                    baseline,
                    perturbed,
                    numeric_tolerance=request.numeric_tolerance,
                )
    except Exception as error:
        total_cases = len(request.verification_cutoffs) * len(
            request.interpretations
        )
        return _finding(
            "no_lookahead",
            passed=False,
            message=f"future perturbation changed history: {redact_secrets(str(error))}",
            observed_value=0.0,
            threshold=float(total_cases),
        )
    count = len(request.verification_cutoffs) * len(request.interpretations)
    return _finding(
        "no_lookahead",
        passed=True,
        message=f"future perturbations preserve history across {count} cases",
        observed_value=float(count),
        threshold=float(count),
    )


def verify_schema_contract(
    staged_dir: Path,
    manifest: RunManifest,
) -> QualityFinding:
    """Validate staged Arrow schema, provenance, dimensions, and checksum."""

    try:
        if not isinstance(manifest, RunManifest):
            raise TypeError("manifest must be a RunManifest")
        product_path = Path(staged_dir) / CYCLE_PHASE_VINTAGE_FILENAME
        if sha256_file(product_path) != manifest.product_checksums.get(
            CYCLE_PHASE_VINTAGE_FILENAME
        ):
            raise ValueError("manifest checksum does not match cycle product")
        table = pq.read_table(product_path)
        if table.schema != CYCLE_PHASE_VINTAGE_SCHEMA:
            raise ValueError("cycle product Arrow schema mismatch")
        product = table.to_pandas()
        validate_cycle_phase_vintage(product, context=manifest)
        row_dates = pd.to_datetime(product["date"]).dt.date
        if any(row_date > manifest.as_of for row_date in row_dates):
            raise ValueError("cycle product contains dates after manifest as_of")
        if manifest.data_vintage > manifest.as_of:
            raise ValueError("manifest data_vintage cannot follow as_of")
    except Exception as error:
        return _finding(
            "schema_contract",
            passed=False,
            message=f"schema contract failed: {redact_secrets(str(error))}",
            observed_value=0.0,
            threshold=1.0,
        )
    return _finding(
        "schema_contract",
        passed=True,
        message="staged cycle product matches Arrow, provenance, and checksum contracts",
        observed_value=1.0,
        threshold=1.0,
    )


def default_cycle_verifiers() -> CycleVerifiers:
    """Return fresh defaults so tests can inject individual gates."""

    return CycleVerifiers(
        cutoff_reconstruction=verify_cutoff_reconstruction,
        schema_contract=verify_schema_contract,
        no_lookahead=verify_no_lookahead,
    )


def _load_registry_snapshots(run_dir: Path) -> RegistryBundle:
    payloads: dict[str, Mapping[str, object]] = {}
    parsed: dict[str, object] = {}
    for filename, (key, model_type) in _REGISTRY_FILES.items():
        payload = _canonical_file_payload(run_dir / filename)
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise CycleAcceptanceError(f"invalid registry snapshot: {filename}")
        if set(payload) != {"schema_version", key}:
            raise CycleAcceptanceError(f"invalid registry snapshot keys: {filename}")
        try:
            registry = model_type.model_validate({key: payload[key]})
        except ValidationError as error:
            raise CycleAcceptanceError(
                f"registry snapshot contract failed: {filename}"
            ) from error
        payloads[filename] = payload
        parsed[key] = getattr(registry, key)
    bundle = RegistryBundle(
        cycles=parsed["cycles"],
        indicators=parsed["indicators"],
        channels=parsed["channels"],
        assets=parsed["assets"],
    )
    try:
        validate_registry_bundle_contract(bundle)
    except (TypeError, ValueError) as error:
        raise CycleAcceptanceError("registry cross-contract validation failed") from error
    expected_payloads = registry_snapshot_payloads(bundle)
    if dict(payloads) != expected_payloads:
        raise CycleAcceptanceError("registry snapshots are not deterministically ordered")
    return bundle


def _load_versions(run_dir: Path) -> tuple[CycleModelVersion, ...]:
    payload = _canonical_file_payload(run_dir / CYCLE_MODEL_VERSIONS_FILENAME)
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "versions",
    }:
        raise CycleAcceptanceError("invalid cycle model version product")
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("versions"),
        list,
    ):
        raise CycleAcceptanceError("invalid cycle model version product")
    try:
        versions = tuple(
            deserialize_cycle_model_version(item) for item in payload["versions"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CycleAcceptanceError("invalid governed cycle model version") from error
    ordered = tuple(sorted(versions, key=lambda version: version.cycle_id))
    if tuple(version.cycle_id for version in ordered) != _CYCLE_IDS:
        raise CycleAcceptanceError("model version product requires exactly C1-C7")
    if versions != ordered:
        raise CycleAcceptanceError("model versions are not deterministically ordered")
    return versions


def _validate_centers(
    product: pd.DataFrame,
    versions: tuple[CycleModelVersion, ...],
    bundle: RegistryBundle,
    manifest: RunManifest,
) -> None:
    version_by_cycle = {version.cycle_id: version for version in versions}
    spec_by_cycle = {cycle.cycle_id: cycle for cycle in bundle.cycles}
    for cycle_id in _CYCLE_IDS:
        version = version_by_cycle[cycle_id]
        spec = spec_by_cycle[cycle_id]
        if version.effective_date > manifest.as_of:
            raise CycleAcceptanceError("model version effective_date follows as_of")
        if not spec.search_min <= version.new_center <= spec.search_max:
            raise CycleAcceptanceError("model version center is outside registry band")
        centers = product.loc[
            product["cycle_id"].eq(cycle_id),
            "center_period",
        ].to_numpy(dtype="float64")
        if not np.isclose(
            centers,
            version.new_center,
            rtol=0.0,
            atol=1e-12,
        ).all():
            raise CycleAcceptanceError(
                "cycle product center does not match governed model version"
            )


def validate_product_interpretations(
    product: pd.DataFrame,
    plan: VerificationPlan,
) -> None:
    """Require the product vintage views to match the audited interpretations."""

    if not isinstance(product, pd.DataFrame):
        raise TypeError("product must be a pandas DataFrame")
    if not isinstance(plan, VerificationPlan):
        raise TypeError("plan must be VerificationPlan")
    planned_others = set(plan.interpretations).difference(
        {VintageKind.REALTIME}
    )
    logical_realtime = {VintageKind.REALTIME, VintageKind.PSEUDO_VINTAGE}
    try:
        grouped = tuple(product.groupby("date", sort=False))
    except KeyError as error:
        raise CycleAcceptanceError("cycle product has invalid vintage labels") from error
    if not grouped:
        raise CycleAcceptanceError("cycle product is empty")
    for _, rows in grouped:
        try:
            actual = {
                VintageKind(value) for value in rows["vintage"].unique()
            }
        except (KeyError, ValueError) as error:
            raise CycleAcceptanceError(
                "cycle product has invalid vintage labels"
            ) from error
        realtime_views = actual.intersection(logical_realtime)
        if len(realtime_views) != 1:
            raise CycleAcceptanceError(
                "every product date must contain exactly one logical realtime view"
            )
        if plan.strict_vintage and VintageKind.PSEUDO_VINTAGE in realtime_views:
            raise CycleAcceptanceError(
                "strict verification plan cannot publish pseudo_vintage rows"
            )
        expected = {*planned_others, *realtime_views}
        if actual != expected:
            raise CycleAcceptanceError(
                "every product date must contain all and only planned interpretations"
            )


def verify_published_cycle_run(run_dir: Path) -> CycleAcceptanceReport:
    """Re-check a published M2 run using only its own validated manifest."""

    directory = Path(run_dir)
    try:
        manifest = load_manifest(directory)
        manifest = verify_manifest(directory, expected=manifest)
    except (OSError, ValueError) as error:
        raise CycleAcceptanceError(
            f"manifest self-consistency failed: {redact_secrets(str(error))}"
        ) from error

    required_files = {
        *list(_REGISTRY_FILES),
        CYCLE_MODEL_VERSIONS_FILENAME,
        CYCLE_PHASE_VINTAGE_FILENAME,
        QUALITY_FINDINGS_FILENAME,
        VERIFICATION_PLAN_FILENAME,
    }
    missing = sorted(required_files.difference(manifest.product_checksums))
    if missing:
        raise CycleAcceptanceError(
            "manifest is missing required M2 products: " + ", ".join(missing)
        )

    bundle = _load_registry_snapshots(directory)
    snapshots = registry_snapshot_payloads(bundle)
    plan = load_verification_plan(directory)
    if any(cutoff > manifest.as_of for cutoff in plan.verification_cutoffs):
        raise CycleAcceptanceError(
            "verification plan cutoff cannot follow manifest as_of"
        )
    if compute_config_hash(
        registry_config_payload(
            snapshots,
            verification_plan=plan,
        )
    ) != manifest.config_hash:
        raise CycleAcceptanceError("manifest config_hash does not match registries")

    versions = _load_versions(directory)
    if cycle_model_set_identity(versions) != manifest.model_version:
        raise CycleAcceptanceError(
            "manifest model_version does not match governed version identities"
        )

    schema_finding = verify_schema_contract(directory, manifest)
    if schema_finding.status != "PASS":
        raise CycleAcceptanceError(schema_finding.message)
    product = pq.read_table(
        directory / CYCLE_PHASE_VINTAGE_FILENAME
    ).to_pandas()
    validate_product_interpretations(product, plan)
    _validate_centers(product, versions, bundle, manifest)

    findings = read_quality_findings(directory / QUALITY_FINDINGS_FILENAME)
    if tuple(finding.check for finding in findings) != MANDATORY_CHECKS:
        raise CycleAcceptanceError(
            "quality findings must contain the three mandatory checks"
        )
    if any(finding.status != "PASS" for finding in findings):
        raise CycleAcceptanceError("published M2 runs may contain only PASS findings")
    finding_by_check = {finding.check: finding for finding in findings}
    cutoff_count = float(
        len(plan.verification_cutoffs) * len(plan.interpretations)
    )
    expected_counts = {
        "cutoff_reconstruction": cutoff_count,
        "schema_contract": 1.0,
        "no_lookahead": cutoff_count,
    }
    for check, expected_count in expected_counts.items():
        finding = finding_by_check[check]
        if finding.observed_value != expected_count:
            raise CycleAcceptanceError(
                f"{check} observed_value does not match verification plan"
            )
        if finding.threshold != expected_count:
            raise CycleAcceptanceError(
                f"{check} threshold does not match verification plan"
            )
    expected_summary = {
        "failed": 0,
        "mandatory": len(MANDATORY_CHECKS),
        "passed": len(MANDATORY_CHECKS),
        "total": len(MANDATORY_CHECKS),
    }
    if manifest.quality_summary != expected_summary:
        raise CycleAcceptanceError(
            "manifest quality_summary does not match mandatory findings"
        )
    return CycleAcceptanceReport(
        manifest=manifest,
        findings=findings,
        files_verified=len(manifest.product_checksums),
        checks_verified=len(findings),
    )


__all__ = [
    "CYCLE_VERIFIER_PROFILE",
    "CYCLE_MODEL_VERSIONS_FILENAME",
    "CycleAcceptanceError",
    "CycleAcceptanceReport",
    "CycleVerificationRequest",
    "CycleVerifiers",
    "MANDATORY_CHECKS",
    "NUMERIC_TOLERANCE",
    "QUALITY_FINDINGS_FILENAME",
    "QualityFinding",
    "VERIFICATION_PLAN_FILENAME",
    "VERIFICATION_PLAN_SCHEMA_VERSION",
    "VerificationPlan",
    "cycle_model_set_identity",
    "create_verification_plan",
    "default_cycle_verifiers",
    "deserialize_cycle_model_version",
    "load_verification_plan",
    "m2_algorithm_fingerprint",
    "read_quality_findings",
    "registry_config_payload",
    "registry_snapshot_payloads",
    "serialize_cycle_model_version",
    "validate_product_interpretations",
    "validate_registry_bundle_contract",
    "verify_cutoff_reconstruction",
    "verify_no_lookahead",
    "verify_published_cycle_run",
    "verify_schema_contract",
    "write_quality_findings",
    "write_verification_plan",
]
