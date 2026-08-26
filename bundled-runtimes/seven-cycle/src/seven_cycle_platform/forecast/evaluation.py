"""Auditable paired out-of-sample Challenger promotion governance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import hashlib
import json
from numbers import Integral, Real
from pathlib import Path, PurePosixPath
import stat
from typing import Sequence

import numpy as np
import pandas as pd

from seven_cycle_platform.forecast.protocol import (
    GOVERNED_LEAKAGE_CHECKS,
    FeatureAudit,
    ModelCard,
)
from seven_cycle_platform.storage.manifest import (
    MANIFEST_FILENAME,
    ManifestVerificationError,
    RunManifest,
    sha256_file,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import canonical_json_bytes


PHASES = ("expansion", "downturn", "contraction", "recovery")
MAPPING_REFERENCE_SCHEMA_VERSION = 1
MAPPING_REFERENCE_FILENAME = "mapping_reference.json"
MAPPING_MANIFEST_METADATA_KEY = "mapping_reference"
PHASE_PROBABILITY_COLUMNS = tuple(f"{phase}_probability" for phase in PHASES)
PROMOTION_METRICS = (
    "brier_score",
    "log_loss",
    "interval_coverage_error",
    "downstream_asset_oos_loss",
)
MANDATORY_PROMOTION_GATES = (
    "model_card",
    "feature_audit",
    "nested_walk_forward",
    "no_lookahead",
    "determinism",
    "paired_coverage",
    "minimum_folds",
    "minimum_samples",
    "brier_score",
    "log_loss",
    "interval_coverage",
    "downstream_asset_oos_loss",
)
OOS_FOLD_ARTIFACT_COLUMNS = (
    "outer_fold_id",
    "sample_id",
    "train_start",
    "train_end",
    "inner_tuning_start",
    "inner_tuning_end",
    "validation_origin",
    "embargo_cutoff",
    "evaluation_cutoff",
    "target_date",
    "target_visible_date",
    "target_revision_window_end",
    "model_id",
    "model_role",
    "model_version",
    "seed",
    "prediction_scope",
    "prediction_id",
    "horizon_months",
    *PHASE_PROBABILITY_COLUMNS,
    "realized_phase",
    "interval_lower",
    "interval_upper",
    "interval_nominal_coverage",
    "realized_target",
    "downstream_asset_id",
    "downstream_asset_prediction",
    "downstream_asset_actual",
    "downstream_asset_loss",
    "downstream_loss",
    "mapping_product",
    "mapping_id",
    "mapping_version",
    "mapping_run_id",
    "mapping_config_hash",
    "mapping_artifact_hash",
    "mapping_manifest_hash",
    "mapping_reference_hash",
    "mapping_reference_filename",
    "mapping_artifact_filename",
    "mapping_as_of",
    "data_vintage",
    "feature_max_visible_date",
    "feature_max_generated_date",
    "feature_max_vintage_date",
    "status",
    "reason",
)
FOLD_ARTIFACT_COLUMNS = OOS_FOLD_ARTIFACT_COLUMNS
FOLD_METRIC_COLUMNS = (
    "outer_fold_id",
    "metric",
    "champion_sample_count",
    "challenger_sample_count",
    "paired_sample_count",
    "champion_value",
    "challenger_value",
    "improvement",
    "champion_coverage_rate",
    "challenger_coverage_rate",
    "nominal_coverage",
)
AGGREGATE_METRIC_COLUMNS = (
    "metric",
    "champion_sample_count",
    "challenger_sample_count",
    "paired_sample_count",
    "fold_count",
    "champion_value",
    "challenger_value",
    "improvement",
    "champion_coverage_rate",
    "challenger_coverage_rate",
    "nominal_coverage",
)
GATE_RESULT_COLUMNS = (
    "gate",
    "mandatory",
    "passed",
    "reason_codes",
    "detail",
)

_DATE_COLUMNS = (
    "train_start",
    "train_end",
    "inner_tuning_start",
    "inner_tuning_end",
    "validation_origin",
    "embargo_cutoff",
    "evaluation_cutoff",
    "target_date",
    "target_visible_date",
    "target_revision_window_end",
    "mapping_as_of",
    "data_vintage",
    "feature_max_visible_date",
    "feature_max_generated_date",
    "feature_max_vintage_date",
)
_FOLD_METADATA_COLUMNS = (
    "train_start",
    "train_end",
    "inner_tuning_start",
    "inner_tuning_end",
    "validation_origin",
    "embargo_cutoff",
    "evaluation_cutoff",
    "mapping_product",
    "mapping_id",
    "mapping_version",
    "mapping_run_id",
    "mapping_config_hash",
    "mapping_artifact_hash",
    "mapping_manifest_hash",
    "mapping_reference_hash",
    "mapping_reference_filename",
    "mapping_artifact_filename",
    "mapping_as_of",
)
_RESULT_FRAME_FIELDS = frozenset(
    {
        "fold_metrics",
        "aggregate_metrics",
        "gate_results",
        "champion_artifacts",
        "challenger_artifacts",
        "champion_replay_artifacts",
        "challenger_replay_artifacts",
    }
)
_LOSS_DEFINITIONS = frozenset({"squared_error", "absolute_error"})
_MAPPING_ARTIFACT_COLUMNS = (
    "mapping_product",
    "mapping_id",
    "mapping_version",
    "mapping_run_id",
    "mapping_config_hash",
    "mapping_artifact_hash",
    "mapping_manifest_hash",
    "mapping_reference_hash",
    "mapping_reference_filename",
    "mapping_artifact_filename",
    "mapping_as_of",
)


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return numeric


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _nonnegative_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _bounded_fraction(value: object, *, name: str, allow_zero: bool = True) -> float:
    numeric = _finite_real(value, name=name)
    lower_valid = numeric >= 0.0 if allow_zero else numeric > 0.0
    if not lower_valid or numeric > 1.0:
        qualifier = "between 0 and 1" if allow_zero else "greater than 0 and at most 1"
        raise ValueError(f"{name} must be {qualifier}")
    return numeric


def _normalize_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


def _normalize_hash(value: object, *, name: str) -> str:
    normalized = _normalize_text(value, name=name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _is_missing(value: object) -> bool:
    missing = pd.isna(value)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _normalize_optional_text(value: object, *, name: str) -> str | None:
    if value is None or _is_missing(value):
        return None
    return _normalize_text(value, name=name)


def _normalize_date(value: object, *, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    if not isinstance(value, (str, date, datetime, np.datetime64, pd.Timestamp)):
        raise TypeError(f"{name} must be date-like")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be missing")
    if timestamp.tzinfo is not None:
        raise ValueError(f"{name} must be timezone-naive")
    return timestamp.normalize()


def _normalize_dates(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_date(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _required_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    if tuple(values.columns) != columns:
        raise ValueError(f"{name} columns do not match the governed contract")
    return values.copy(deep=True)


class MappingReferenceVerificationError(ValueError):
    """Raised when a Mapping reference is not backed by a trusted published run."""


_MAPPING_MANIFEST_METADATA_FIELDS = frozenset(
    {
        "schema_version",
        "mapping_product",
        "mapping_id",
        "artifact_filename",
    }
)
_MAPPING_REFERENCE_CATALOG_FIELDS = frozenset(
    {
        *_MAPPING_MANIFEST_METADATA_FIELDS,
        "version",
        "run_id",
        "config_hash",
        "artifact_hash",
        "as_of",
    }
)


def _path_identity(
    path: Path,
    *,
    label: str,
    directory: bool,
) -> tuple[int, int]:
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise MappingReferenceVerificationError(
            f"{label} is missing or invalid"
        ) from error
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_kind(path_stat.st_mode):
        raise MappingReferenceVerificationError(
            f"{label} must be a real {'directory' if directory else 'file'}"
        )
    return path_stat.st_dev, path_stat.st_ino


def _published_run_dir(
    run_dir: Path,
    *,
    expected_manifest: RunManifest,
) -> Path:
    try:
        normalized = Path(run_dir).absolute()
    except TypeError as error:
        raise TypeError("run_dir must be path-like") from error
    if normalized.parent.name != "runs":
        raise MappingReferenceVerificationError(
            "Mapping run must be inside a published runs directory"
        )
    product_root = normalized.parent.parent
    _path_identity(product_root, label="Mapping product root", directory=True)
    _path_identity(normalized.parent, label="Mapping runs directory", directory=True)
    _path_identity(normalized, label="Mapping run directory", directory=True)
    if normalized.name != expected_manifest.run_id:
        raise MappingReferenceVerificationError(
            "Mapping run directory does not match the trusted expected manifest"
        )
    return normalized


def _relative_product_filename(value: object, *, name: str) -> str:
    normalized = _normalize_text(value, name=name)
    pure_path = PurePosixPath(normalized)
    if (
        pure_path.is_absolute()
        or pure_path.as_posix() != normalized
        or any(part in {"", ".", ".."} for part in pure_path.parts)
        or "\\" in normalized
    ):
        raise MappingReferenceVerificationError(
            f"{name} must be a canonical relative product filename"
        )
    if normalized in {MANIFEST_FILENAME, MAPPING_REFERENCE_FILENAME}:
        raise MappingReferenceVerificationError(
            f"{name} must identify the Mapping artifact"
        )
    return normalized


def _manifest_mapping_metadata(
    manifest: RunManifest,
) -> tuple[str, str, str]:
    metadata = manifest.quality_summary.get(MAPPING_MANIFEST_METADATA_KEY)
    if not isinstance(metadata, Mapping):
        raise MappingReferenceVerificationError(
            "trusted manifest is missing governed Mapping metadata"
        )
    if set(metadata) != _MAPPING_MANIFEST_METADATA_FIELDS:
        raise MappingReferenceVerificationError(
            "trusted manifest Mapping metadata does not match the governed contract"
        )
    schema_version = metadata["schema_version"]
    if (
        isinstance(schema_version, bool)
        or schema_version != MAPPING_REFERENCE_SCHEMA_VERSION
    ):
        raise MappingReferenceVerificationError(
            "trusted manifest Mapping metadata schema_version is unsupported"
        )
    mapping_product = _normalize_text(
        metadata["mapping_product"],
        name="manifest mapping_product",
    )
    mapping_id = _normalize_text(
        metadata["mapping_id"],
        name="manifest mapping_id",
    )
    artifact_filename = _relative_product_filename(
        metadata["artifact_filename"],
        name="manifest artifact_filename",
    )
    return mapping_product, mapping_id, artifact_filename


def _load_mapping_reference_catalog(reference_path: Path) -> dict[str, object]:
    try:
        raw_reference = reference_path.read_bytes()
        payload = json.loads(raw_reference)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MappingReferenceVerificationError(
            "Mapping reference catalog is missing or invalid"
        ) from error
    if not isinstance(payload, dict):
        raise MappingReferenceVerificationError(
            "Mapping reference catalog must be a JSON object"
        )
    try:
        canonical_reference = canonical_json_bytes(payload) + b"\n"
    except (TypeError, ValueError) as error:
        raise MappingReferenceVerificationError(
            "Mapping reference catalog is not canonical JSON"
        ) from error
    if raw_reference != canonical_reference:
        raise MappingReferenceVerificationError(
            "Mapping reference catalog JSON is not canonical"
        )
    if set(payload) != _MAPPING_REFERENCE_CATALOG_FIELDS:
        raise MappingReferenceVerificationError(
            "Mapping reference catalog does not match the governed contract"
        )
    schema_version = payload["schema_version"]
    if (
        isinstance(schema_version, bool)
        or schema_version != MAPPING_REFERENCE_SCHEMA_VERSION
    ):
        raise MappingReferenceVerificationError(
            "Mapping reference catalog schema_version is unsupported"
        )
    return payload


def _published_mapping_file_identities(
    run_dir: Path,
    *,
    artifact_filename: str,
) -> tuple[tuple[str, int, int], ...]:
    paths = (
        ("product_root", run_dir.parent.parent, True),
        ("runs_root", run_dir.parent, True),
        ("run_dir", run_dir, True),
        ("manifest", run_dir / MANIFEST_FILENAME, False),
        ("reference", run_dir / MAPPING_REFERENCE_FILENAME, False),
        ("artifact", run_dir / artifact_filename, False),
    )
    return tuple(
        (label, *(_path_identity(path, label=label, directory=directory)))
        for label, path, directory in paths
    )


@dataclass(frozen=True, slots=True, init=False)
class MappingReference:
    """Verified identity for one immutable, published downstream Mapping run."""

    mapping_product: str
    mapping_id: str
    version: str
    run_id: str
    config_hash: str
    artifact_hash: str
    manifest_hash: str
    reference_hash: str
    as_of: date
    run_dir: Path
    reference_filename: str
    artifact_filename: str
    _trusted_manifest_json: bytes = field(repr=False)
    _file_identities: tuple[tuple[str, int, int], ...] = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("MappingReference must be created with from_published_run()")

    @classmethod
    def from_published_run(
        cls,
        run_dir: Path,
        *,
        expected_manifest: RunManifest,
    ) -> MappingReference:
        """Build a reference only after trusted manifest and product verification."""

        if not isinstance(expected_manifest, RunManifest):
            raise TypeError("expected_manifest must be a trusted RunManifest")
        normalized_run_dir = _published_run_dir(
            run_dir,
            expected_manifest=expected_manifest,
        )
        try:
            verified_manifest = verify_manifest(
                normalized_run_dir,
                expected=expected_manifest,
            )
        except ManifestVerificationError as error:
            raise MappingReferenceVerificationError(str(error)) from error

        mapping_product, mapping_id, artifact_filename = _manifest_mapping_metadata(
            verified_manifest
        )
        if normalized_run_dir.parent.parent.name != mapping_product:
            raise MappingReferenceVerificationError(
                "Mapping product does not match the published product root"
            )
        reference_path = normalized_run_dir / MAPPING_REFERENCE_FILENAME
        catalog = _load_mapping_reference_catalog(reference_path)
        catalog_mapping_product = _normalize_text(
            catalog["mapping_product"],
            name="catalog mapping_product",
        )
        catalog_mapping_id = _normalize_text(
            catalog["mapping_id"],
            name="catalog mapping_id",
        )
        catalog_artifact_filename = _relative_product_filename(
            catalog["artifact_filename"],
            name="catalog artifact_filename",
        )
        if (
            catalog_mapping_product != mapping_product
            or catalog_mapping_id != mapping_id
            or catalog_artifact_filename != artifact_filename
        ):
            raise MappingReferenceVerificationError(
                "Mapping reference catalog does not match trusted manifest metadata"
            )

        version = _normalize_text(catalog["version"], name="mapping version")
        run_id = _normalize_text(catalog["run_id"], name="mapping run_id")
        config_hash = _normalize_hash(
            catalog["config_hash"],
            name="mapping config_hash",
        )
        artifact_hash = _normalize_hash(
            catalog["artifact_hash"],
            name="mapping artifact_hash",
        )
        mapping_as_of = _normalize_date(
            catalog["as_of"],
            name="mapping as_of",
        ).date()
        if version != verified_manifest.model_version:
            raise MappingReferenceVerificationError(
                "Mapping version does not match the trusted manifest"
            )
        if run_id != verified_manifest.run_id:
            raise MappingReferenceVerificationError(
                "Mapping run_id does not match the trusted manifest"
            )
        if config_hash != verified_manifest.config_hash:
            raise MappingReferenceVerificationError(
                "Mapping config_hash does not match the trusted manifest"
            )
        if mapping_as_of != verified_manifest.as_of:
            raise MappingReferenceVerificationError(
                "Mapping as_of does not match the trusted manifest"
            )

        reference_hash = verified_manifest.product_checksums.get(
            MAPPING_REFERENCE_FILENAME
        )
        manifest_artifact_hash = verified_manifest.product_checksums.get(
            artifact_filename
        )
        if reference_hash is None or manifest_artifact_hash is None:
            raise MappingReferenceVerificationError(
                "trusted manifest is missing Mapping reference products"
            )
        if artifact_hash != manifest_artifact_hash:
            raise MappingReferenceVerificationError(
                "Mapping artifact_hash does not match the trusted manifest"
            )
        artifact_path = normalized_run_dir / artifact_filename
        if sha256_file(reference_path) != reference_hash:
            raise MappingReferenceVerificationError(
                "Mapping reference checksum does not match the trusted manifest"
            )
        if sha256_file(artifact_path) != artifact_hash:
            raise MappingReferenceVerificationError(
                "Mapping artifact checksum does not match the trusted manifest"
            )

        identities_before = _published_mapping_file_identities(
            normalized_run_dir,
            artifact_filename=artifact_filename,
        )
        try:
            verify_manifest(normalized_run_dir, expected=expected_manifest)
        except ManifestVerificationError as error:
            raise MappingReferenceVerificationError(str(error)) from error
        identities_after = _published_mapping_file_identities(
            normalized_run_dir,
            artifact_filename=artifact_filename,
        )
        if identities_before != identities_after:
            raise MappingReferenceVerificationError(
                "published Mapping run identity changed during verification"
            )

        trusted_manifest_json = expected_manifest.to_json_bytes()
        manifest_hash = sha256_file(normalized_run_dir / MANIFEST_FILENAME)
        trusted_manifest_hash = hashlib.sha256(trusted_manifest_json).hexdigest()
        if manifest_hash != trusted_manifest_hash:
            raise MappingReferenceVerificationError(
                "Mapping manifest checksum does not match the trusted manifest"
            )

        reference = object.__new__(cls)
        values: dict[str, object] = {
            "mapping_product": mapping_product,
            "mapping_id": mapping_id,
            "version": version,
            "run_id": run_id,
            "config_hash": config_hash,
            "artifact_hash": artifact_hash,
            "manifest_hash": manifest_hash,
            "reference_hash": reference_hash,
            "as_of": mapping_as_of,
            "run_dir": normalized_run_dir,
            "reference_filename": MAPPING_REFERENCE_FILENAME,
            "artifact_filename": artifact_filename,
            "_trusted_manifest_json": trusted_manifest_json,
            "_file_identities": identities_after,
        }
        for name, value in values.items():
            object.__setattr__(reference, name, value)
        return reference

    def _governed_identity(self) -> tuple[object, ...]:
        return (
            self.mapping_product,
            self.mapping_id,
            self.version,
            self.run_id,
            self.config_hash,
            self.artifact_hash,
            self.manifest_hash,
            self.reference_hash,
            self.as_of,
            self.run_dir,
            self.reference_filename,
            self.artifact_filename,
        )

    def revalidate(self) -> MappingReference:
        """Re-verify the retained published run and reject later replacement."""

        try:
            trusted_manifest = RunManifest.model_validate_json(
                self._trusted_manifest_json
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise MappingReferenceVerificationError(
                "MappingReference was not created from a trusted published run"
            ) from error
        verified = type(self).from_published_run(
            self.run_dir,
            expected_manifest=trusted_manifest,
        )
        if self._governed_identity() != verified._governed_identity():
            raise MappingReferenceVerificationError(
                "MappingReference does not match the published Mapping run"
            )
        if (
            self._trusted_manifest_json != verified._trusted_manifest_json
            or self._file_identities != verified._file_identities
        ):
            raise MappingReferenceVerificationError(
                "published Mapping run identity changed after verification"
            )
        return verified


@dataclass(frozen=True, slots=True)
class PromotionEvidenceContext:
    """Authoritative cutoff and Mapping evidence for one promotion decision."""

    evaluation_cutoff: date
    mapping_reference: MappingReference

    def __post_init__(self) -> None:
        evaluation_cutoff = _normalize_date(
            self.evaluation_cutoff,
            name="evaluation_cutoff",
        ).date()
        if not isinstance(self.mapping_reference, MappingReference):
            raise TypeError("mapping_reference must be a MappingReference")
        mapping_reference = self.mapping_reference.revalidate()
        if mapping_reference.as_of > evaluation_cutoff:
            raise ValueError("mapping as_of cannot follow evaluation_cutoff")
        object.__setattr__(self, "evaluation_cutoff", evaluation_cutoff)
        object.__setattr__(self, "mapping_reference", mapping_reference)


@dataclass(frozen=True)
class PromotionConfig:
    """Immutable thresholds and mandatory Challenger promotion gates."""

    minimum_folds: int = 3
    minimum_samples: int = 30
    min_brier_improvement: float = 0.0
    min_log_loss_improvement: float = 0.0
    min_interval_coverage_improvement: float = 0.0
    min_downstream_asset_loss_improvement: float = 0.0
    coverage_tolerance: float = 0.05
    probability_epsilon: float = 1e-15
    embargo_days: int = 0
    seed_policy: str = "matched"
    downstream_loss: str = "squared_error"
    require_deterministic_replay: bool = False
    mandatory_gates: Sequence[str] = MANDATORY_PROMOTION_GATES

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_folds",
            _positive_integer(self.minimum_folds, name="minimum_folds"),
        )
        object.__setattr__(
            self,
            "minimum_samples",
            _positive_integer(self.minimum_samples, name="minimum_samples"),
        )
        for field_name in (
            "min_brier_improvement",
            "min_log_loss_improvement",
            "min_interval_coverage_improvement",
            "min_downstream_asset_loss_improvement",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_real(getattr(self, field_name), name=field_name),
            )
        object.__setattr__(
            self,
            "coverage_tolerance",
            _bounded_fraction(self.coverage_tolerance, name="coverage_tolerance"),
        )
        epsilon = _bounded_fraction(
            self.probability_epsilon,
            name="probability_epsilon",
            allow_zero=False,
        )
        if epsilon >= 0.25:
            raise ValueError("probability_epsilon must be smaller than 0.25")
        object.__setattr__(self, "probability_epsilon", epsilon)
        object.__setattr__(
            self,
            "embargo_days",
            _nonnegative_integer(self.embargo_days, name="embargo_days"),
        )
        seed_policy = _normalize_text(self.seed_policy, name="seed_policy")
        if seed_policy not in {"matched", "model_specific"}:
            raise ValueError("seed_policy must be matched or model_specific")
        object.__setattr__(self, "seed_policy", seed_policy)
        downstream_loss = _normalize_text(
            self.downstream_loss,
            name="downstream_loss",
        )
        if downstream_loss not in _LOSS_DEFINITIONS:
            raise ValueError("downstream_loss must be squared_error or absolute_error")
        object.__setattr__(self, "downstream_loss", downstream_loss)
        if not isinstance(self.require_deterministic_replay, (bool, np.bool_)):
            raise TypeError("require_deterministic_replay must be boolean")
        object.__setattr__(
            self,
            "require_deterministic_replay",
            bool(self.require_deterministic_replay),
        )
        if isinstance(self.mandatory_gates, (str, bytes, bytearray)):
            raise TypeError("mandatory_gates must be a sequence of gate names")
        try:
            supplied_gates = tuple(self.mandatory_gates)
        except TypeError as error:
            raise TypeError(
                "mandatory_gates must be a sequence of gate names"
            ) from error
        normalized_gates = tuple(
            _normalize_text(gate, name="mandatory gate") for gate in supplied_gates
        )
        if len(normalized_gates) != len(set(normalized_gates)):
            raise ValueError("mandatory_gates cannot contain duplicates")
        unknown = set(normalized_gates) - set(MANDATORY_PROMOTION_GATES)
        missing = set(MANDATORY_PROMOTION_GATES) - set(normalized_gates)
        if unknown or missing:
            raise ValueError("all governed mandatory promotion gates are required")
        object.__setattr__(self, "mandatory_gates", MANDATORY_PROMOTION_GATES)

    @property
    def min_folds(self) -> int:
        return self.minimum_folds

    @property
    def min_samples(self) -> int:
        return self.minimum_samples


def _rebuild_config(value: object) -> PromotionConfig:
    if not isinstance(value, PromotionConfig):
        raise TypeError("config must be a PromotionConfig")
    return PromotionConfig(**asdict(value))


def _rebuild_model_card(value: object, *, name: str) -> ModelCard:
    if not isinstance(value, ModelCard):
        raise TypeError(f"{name} must be a ModelCard")
    return ModelCard(**asdict(value))


def _rebuild_feature_audit(value: object, *, name: str) -> FeatureAudit:
    if not isinstance(value, FeatureAudit):
        raise TypeError(f"{name} must be a FeatureAudit")
    return FeatureAudit(**asdict(value))


def _rebuild_mapping_reference(value: object, *, name: str) -> MappingReference:
    if not isinstance(value, MappingReference):
        raise TypeError(f"{name} must be a MappingReference")
    return value.revalidate()


def _rebuild_evidence_context(
    value: object,
    *,
    name: str = "evidence_context",
) -> PromotionEvidenceContext:
    if not isinstance(value, PromotionEvidenceContext):
        raise TypeError(f"{name} must be a PromotionEvidenceContext")
    return PromotionEvidenceContext(
        evaluation_cutoff=value.evaluation_cutoff,
        mapping_reference=_rebuild_mapping_reference(
            value.mapping_reference,
            name=f"{name}.mapping_reference",
        ),
    )


def _normalize_artifacts(values: object, *, name: str) -> pd.DataFrame:
    artifacts = _required_frame(
        values,
        name=name,
        columns=OOS_FOLD_ARTIFACT_COLUMNS,
    )
    if artifacts.empty:
        return artifacts.reset_index(drop=True)
    for column in _DATE_COLUMNS:
        artifacts[column] = _normalize_dates(
            artifacts[column],
            name=f"{name} {column}",
        )

    text_columns = (
        "outer_fold_id",
        "sample_id",
        "model_id",
        "model_role",
        "model_version",
        "prediction_scope",
        "prediction_id",
        "realized_phase",
        "downstream_asset_id",
        "downstream_loss",
        "mapping_product",
        "mapping_id",
        "mapping_version",
        "mapping_run_id",
        "mapping_reference_filename",
        "mapping_artifact_filename",
        "status",
    )
    for column in text_columns:
        artifacts[column] = pd.Series(
            [
                _normalize_text(value, name=f"{name} {column}")
                for value in artifacts[column].tolist()
            ],
            index=artifacts.index,
            dtype="object",
        )
    for column in (
        "mapping_config_hash",
        "mapping_artifact_hash",
        "mapping_manifest_hash",
        "mapping_reference_hash",
    ):
        artifacts[column] = pd.Series(
            [
                _normalize_hash(value, name=f"{name} {column}")
                for value in artifacts[column].tolist()
            ],
            index=artifacts.index,
            dtype="object",
        )
    artifacts["reason"] = pd.Series(
        [
            _normalize_optional_text(value, name=f"{name} reason")
            for value in artifacts["reason"].tolist()
        ],
        index=artifacts.index,
        dtype="object",
    )

    if not set(artifacts["model_role"]).issubset({"champion", "challenger"}):
        raise ValueError(f"{name} model_role must be champion or challenger")
    if not set(artifacts["prediction_scope"]).issubset({"cycle", "channel"}):
        raise ValueError(f"{name} prediction_scope must be cycle or channel")
    if not set(artifacts["realized_phase"]).issubset(set(PHASES)):
        raise ValueError(f"{name} realized_phase is not governed")
    if not set(artifacts["status"]).issubset({"complete", "failed", "unavailable"}):
        raise ValueError(f"{name} status must be complete, failed, or unavailable")
    if not set(artifacts["downstream_loss"]).issubset(_LOSS_DEFINITIONS):
        raise ValueError(
            f"{name} downstream_loss must be squared_error or absolute_error"
        )
    complete = artifacts["status"].eq("complete")
    if artifacts.loc[complete, "reason"].notna().any():
        raise ValueError(f"{name} complete rows cannot define a reason")
    if artifacts.loc[~complete, "reason"].isna().any():
        raise ValueError(f"{name} incomplete rows require a reason")

    artifacts["seed"] = pd.Series(
        [
            _nonnegative_integer(value, name=f"{name} seed")
            for value in artifacts["seed"].tolist()
        ],
        index=artifacts.index,
        dtype="int64",
    )
    artifacts["horizon_months"] = pd.Series(
        [
            _positive_integer(value, name=f"{name} horizon_months")
            for value in artifacts["horizon_months"].tolist()
        ],
        index=artifacts.index,
        dtype="int64",
    )

    probability_values = np.asarray(
        [
            [
                _finite_real(value, name=f"{name} {column}")
                for value in artifacts.loc[complete, column].tolist()
            ]
            for column in PHASE_PROBABILITY_COLUMNS
        ],
        dtype="float64",
    ).T
    if bool(((probability_values < 0.0) | (probability_values > 1.0)).any()):
        raise ValueError(f"{name} phase probabilities must be between 0 and 1")
    if len(probability_values) and not np.allclose(
        probability_values.sum(axis=1),
        1.0,
        atol=1e-10,
        rtol=1e-10,
    ):
        raise ValueError(f"{name} phase probabilities must sum to one")
    for position, column in enumerate(PHASE_PROBABILITY_COLUMNS):
        normalized = pd.to_numeric(artifacts[column], errors="coerce").astype("float64")
        if len(probability_values):
            normalized.loc[complete] = probability_values[:, position]
        artifacts[column] = normalized

    numeric_columns = (
        "interval_lower",
        "interval_upper",
        "interval_nominal_coverage",
        "realized_target",
        "downstream_asset_prediction",
        "downstream_asset_actual",
        "downstream_asset_loss",
    )
    for column in numeric_columns:
        normalized = pd.to_numeric(artifacts[column], errors="coerce").astype("float64")
        normalized.loc[complete] = [
            _finite_real(value, name=f"{name} {column}")
            for value in artifacts.loc[complete, column].tolist()
        ]
        artifacts[column] = normalized
    if bool(
        artifacts.loc[complete, "interval_lower"]
        .gt(artifacts.loc[complete, "interval_upper"])
        .any()
    ):
        raise ValueError(f"{name} interval lower cannot exceed interval upper")
    nominal = artifacts.loc[complete, "interval_nominal_coverage"]
    if bool(((nominal <= 0.0) | (nominal > 1.0)).any()):
        raise ValueError(
            f"{name} interval_nominal_coverage must be greater than 0 and at most 1"
        )
    if bool(artifacts.loc[complete, "downstream_asset_loss"].lt(0.0).any()):
        raise ValueError(f"{name} downstream asset loss must be nonnegative")

    complete_rows = artifacts.loc[complete]
    residual = (
        complete_rows["downstream_asset_prediction"]
        - complete_rows["downstream_asset_actual"]
    ).to_numpy(dtype="float64")
    expected_losses = np.where(
        complete_rows["downstream_loss"].eq("squared_error").to_numpy(),
        residual**2,
        np.abs(residual),
    )
    if len(expected_losses) and not np.allclose(
        complete_rows["downstream_asset_loss"].to_numpy(dtype="float64"),
        expected_losses,
        atol=1e-12,
        rtol=1e-12,
    ):
        raise ValueError(f"{name} downstream asset loss is inconsistent")

    if artifacts.duplicated(["outer_fold_id", "sample_id"]).any():
        raise ValueError(f"{name} contains duplicate fold samples")
    if artifacts["sample_id"].duplicated().any():
        raise ValueError(f"{name} sample_id values must be globally unique")
    for fold_id, group in artifacts.groupby("outer_fold_id", sort=False):
        for column in _FOLD_METADATA_COLUMNS:
            if group[column].nunique(dropna=False) != 1:
                raise ValueError(
                    f"{name} fold {fold_id} has inconsistent {column} metadata"
                )
    return artifacts.sort_values(
        ["validation_origin", "outer_fold_id", "sample_id"],
        kind="stable",
    ).reset_index(drop=True)


@dataclass(frozen=True)
class _ArtifactAudit:
    nested_codes: tuple[str, ...]
    lookahead_codes: tuple[str, ...]
    invalid_fold_ids: frozenset[str]


def _artifact_audit(
    artifacts: pd.DataFrame,
    *,
    config: PromotionConfig,
    evidence_context: PromotionEvidenceContext,
) -> _ArtifactAudit:
    nested_codes: list[str] = []
    lookahead_codes: list[str] = []
    invalid_folds: set[str] = set()
    authoritative_cutoff = pd.Timestamp(evidence_context.evaluation_cutoff)

    def flag(collection: list[str], code: str, fold_id: str) -> None:
        if code not in collection:
            collection.append(code)
        invalid_folds.add(fold_id)

    fold_rows: list[pd.Series] = []
    for fold_id, group in artifacts.groupby("outer_fold_id", sort=False):
        row = group.iloc[0].copy()
        row["_fold_target_end"] = group["target_date"].max()
        fold_rows.append(row)
        if not bool(group["evaluation_cutoff"].eq(authoritative_cutoff).all()):
            flag(lookahead_codes, "EVALUATION_CUTOFF_MISMATCH", str(fold_id))
        for column, code in (
            (
                "validation_origin",
                "VALIDATION_ORIGIN_AFTER_EVALUATION_CUTOFF",
            ),
            ("target_date", "TARGET_DATE_AFTER_EVALUATION_CUTOFF"),
            (
                "target_visible_date",
                "TARGET_VISIBLE_DATE_AFTER_EVALUATION_CUTOFF",
            ),
            (
                "target_revision_window_end",
                "TARGET_REVISION_AFTER_EVALUATION_CUTOFF",
            ),
            ("mapping_as_of", "MAPPING_AS_OF_AFTER_EVALUATION_CUTOFF"),
        ):
            if bool(group[column].gt(authoritative_cutoff).any()):
                flag(lookahead_codes, code, str(fold_id))
        if row["train_start"] > row["train_end"]:
            flag(nested_codes, "TRAIN_WINDOW_INVALID", str(fold_id))
        if row["inner_tuning_start"] > row["inner_tuning_end"] or (
            row["inner_tuning_start"] < row["train_start"]
            or row["inner_tuning_end"] > row["train_end"]
        ):
            flag(
                nested_codes,
                "INNER_TUNING_WINDOW_OUTSIDE_TRAIN",
                str(fold_id),
            )
        expected_embargo = row["validation_origin"] - pd.Timedelta(
            days=config.embargo_days
        )
        if row["embargo_cutoff"] != expected_embargo:
            flag(lookahead_codes, "EMBARGO_CUTOFF_MISMATCH", str(fold_id))
        if row["train_end"] >= row["embargo_cutoff"]:
            flag(
                lookahead_codes,
                "TRAIN_END_NOT_BEFORE_EMBARGO",
                str(fold_id),
            )
        if row["inner_tuning_end"] >= row["embargo_cutoff"]:
            flag(
                lookahead_codes,
                "INNER_TUNING_END_NOT_BEFORE_EMBARGO",
                str(fold_id),
            )
        if row["validation_origin"] >= authoritative_cutoff:
            flag(lookahead_codes, "CURRENT_OR_FUTURE_FOLD", str(fold_id))

        if bool((group["target_date"] <= group["validation_origin"]).any()):
            flag(
                lookahead_codes,
                "TARGET_NOT_AFTER_VALIDATION_ORIGIN",
                str(fold_id),
            )
        target_not_mature = (
            (group["target_date"] >= authoritative_cutoff)
            | (group["target_visible_date"] >= authoritative_cutoff)
            | (group["target_revision_window_end"] >= authoritative_cutoff)
            | (group["target_visible_date"] < group["target_date"])
            | (group["target_revision_window_end"] < group["target_visible_date"])
        )
        if bool(target_not_mature.any()):
            flag(
                lookahead_codes,
                "TARGET_NOT_MATURE_AT_EVALUATION_CUTOFF",
                str(fold_id),
            )
        for column, code in (
            ("data_vintage", "DATA_VINTAGE_NOT_BEFORE_ORIGIN"),
            ("feature_max_visible_date", "FEATURE_VISIBLE_NOT_BEFORE_ORIGIN"),
            (
                "feature_max_generated_date",
                "FEATURE_GENERATED_NOT_BEFORE_ORIGIN",
            ),
            ("feature_max_vintage_date", "FEATURE_VINTAGE_NOT_BEFORE_ORIGIN"),
        ):
            if bool((group[column] >= group["validation_origin"]).any()):
                flag(lookahead_codes, code, str(fold_id))

    if fold_rows:
        folds = pd.DataFrame(fold_rows).sort_values(
            ["validation_origin", "outer_fold_id"],
            kind="stable",
        )
        duplicated_origins = folds["validation_origin"].duplicated(keep=False)
        if bool(duplicated_origins.any()):
            if "NON_INCREASING_OUTER_FOLDS" not in nested_codes:
                nested_codes.append("NON_INCREASING_OUTER_FOLDS")
            invalid_folds.update(
                folds.loc[duplicated_origins, "outer_fold_id"].astype(str)
            )
        previous_target_end = folds["_fold_target_end"].shift(1)
        overlapping = folds["validation_origin"].le(previous_target_end)
        if bool(overlapping.fillna(False).any()):
            if "OVERLAPPING_OUTER_FOLDS" not in nested_codes:
                nested_codes.append("OVERLAPPING_OUTER_FOLDS")
            overlapping_positions = np.flatnonzero(
                overlapping.fillna(False).to_numpy(dtype="bool")
            )
            for position in overlapping_positions:
                invalid_folds.add(str(folds.iloc[position]["outer_fold_id"]))
                invalid_folds.add(str(folds.iloc[position - 1]["outer_fold_id"]))
        train_end_diff = folds["train_end"].diff().dropna()
        if bool(train_end_diff.le(pd.Timedelta(0)).any()):
            if "NON_INCREASING_TRAINING_WINDOWS" not in nested_codes:
                nested_codes.append("NON_INCREASING_TRAINING_WINDOWS")
            invalid_folds.update(folds["outer_fold_id"].astype(str))

    return _ArtifactAudit(
        nested_codes=tuple(nested_codes),
        lookahead_codes=tuple(lookahead_codes),
        invalid_fold_ids=frozenset(invalid_folds),
    )


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def _model_card_codes(
    champion_artifacts: pd.DataFrame,
    challenger_artifacts: pd.DataFrame,
    champion_card: ModelCard,
    challenger_card: ModelCard,
) -> tuple[str, ...]:
    codes: list[str] = []
    if champion_card.role != "champion":
        _append_unique(codes, "CHAMPION_MODEL_CARD_ROLE_INVALID")
    if challenger_card.role != "challenger":
        _append_unique(codes, "CHALLENGER_MODEL_CARD_ROLE_INVALID")
    if champion_card.model_id == challenger_card.model_id:
        _append_unique(codes, "MODEL_IDS_MUST_BE_DISTINCT")
    if champion_card.scope != challenger_card.scope:
        _append_unique(codes, "MODEL_CARD_SCOPE_MISMATCH")

    for artifacts, card in (
        (champion_artifacts, champion_card),
        (challenger_artifacts, challenger_card),
    ):
        expected = {
            "model_id": card.model_id,
            "model_role": card.role,
            "model_version": card.version,
            "prediction_scope": card.scope,
        }
        for column, value in expected.items():
            if set(artifacts[column]) != ({value} if not artifacts.empty else set()):
                _append_unique(codes, "ARTIFACT_MODEL_CARD_MISMATCH")
        if card.training_cutoff > card.data_vintage:
            _append_unique(codes, "MODEL_CARD_VINTAGE_BEFORE_TRAINING_CUTOFF")
        if card.direct_asset_weights_allowed:
            _append_unique(codes, "DIRECT_ASSET_ALLOCATION_PROHIBITED")
        if card.direct_asset_prediction_bypass_allowed:
            _append_unique(codes, "DIRECT_ASSET_PREDICTION_BYPASS_PROHIBITED")
        if card.historical_contribution_weights_allowed:
            _append_unique(
                codes,
                "HISTORICAL_CONTRIBUTION_WEIGHTS_PROHIBITED",
            )
    return tuple(codes)


def _feature_audit_codes(
    champion_card: ModelCard,
    challenger_card: ModelCard,
    champion_audit: FeatureAudit,
    challenger_audit: FeatureAudit,
) -> tuple[str, ...]:
    codes: list[str] = []
    for card, audit in (
        (champion_card, champion_audit),
        (challenger_card, challenger_audit),
    ):
        identity_matches = (
            audit.model_id == card.model_id
            and audit.version == card.version
            and audit.role == card.role
            and audit.scope == card.scope
            and audit.data_vintage == card.data_vintage
            and audit.train_end == card.training_cutoff
            and audit.code_hash == card.code_hash
            and audit.config_hash == card.config_hash
        )
        if not identity_matches:
            _append_unique(codes, "FEATURE_AUDIT_IDENTITY_MISMATCH")
        if audit.feature_ids != card.feature_ids:
            _append_unique(codes, "FEATURE_AUDIT_FEATURE_SET_MISMATCH")
        if any(
            value > audit.as_of
            for value in (
                audit.max_visible_date,
                audit.max_generated_date,
                audit.max_vintage_date,
            )
        ):
            _append_unique(codes, "FEATURE_AUDIT_FUTURE_DATA")
        governed_checks = set(GOVERNED_LEAKAGE_CHECKS)
        reported_checks = set(audit.leakage_checks)
        if reported_checks - governed_checks:
            _append_unique(codes, "FEATURE_AUDIT_UNKNOWN_LEAKAGE_CHECKS")
        if governed_checks - reported_checks:
            _append_unique(codes, "FEATURE_AUDIT_MISSING_LEAKAGE_CHECKS")
        if audit.status == "failed":
            _append_unique(codes, "FEATURE_AUDIT_STATUS_FAILED")
            for reason in audit.reasons:
                _append_unique(codes, reason)
        if audit.forbidden_features:
            _append_unique(codes, "PROHIBITED_FEATURES_PRESENT")
    return tuple(codes)


def _replay_codes(
    champion_artifacts: pd.DataFrame,
    challenger_artifacts: pd.DataFrame,
    champion_replay: pd.DataFrame | None,
    challenger_replay: pd.DataFrame | None,
    champion_card: ModelCard,
    challenger_card: ModelCard,
    champion_audit: FeatureAudit,
    challenger_audit: FeatureAudit,
    config: PromotionConfig,
) -> tuple[str, ...]:
    codes: list[str] = []
    for artifacts, card in (
        (champion_artifacts, champion_card),
        (challenger_artifacts, challenger_card),
    ):
        if not artifacts.empty and set(artifacts["seed"]) != {card.seed}:
            _append_unique(codes, "ARTIFACT_SEED_MISMATCH")
    if config.seed_policy == "matched" and champion_card.seed != challenger_card.seed:
        _append_unique(codes, "SEED_POLICY_VIOLATION")
    if config.require_deterministic_replay and (
        champion_replay is None or challenger_replay is None
    ):
        _append_unique(codes, "DETERMINISTIC_REPLAY_REQUIRED")
    for artifacts, replay in (
        (champion_artifacts, champion_replay),
        (challenger_artifacts, challenger_replay),
    ):
        if replay is None:
            continue
        try:
            pd.testing.assert_frame_equal(
                artifacts,
                replay,
                check_dtype=True,
                check_exact=True,
            )
        except AssertionError:
            _append_unique(codes, "NON_DETERMINISTIC_REPLAY")
    return tuple(codes)


@dataclass(frozen=True)
class _PairAudit:
    codes: tuple[str, ...]
    paired_keys: tuple[tuple[str, str], ...]
    paired_sample_count: int
    paired_fold_count: int
    paired_counts_by_fold: dict[str, int]


def _series_equal(left: pd.Series, right: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
        return pd.Series(
            np.isclose(
                left.to_numpy(dtype="float64"),
                right.to_numpy(dtype="float64"),
                atol=1e-12,
                rtol=1e-12,
                equal_nan=True,
            ),
            index=left.index,
        )
    return left.eq(right)


def _mapping_reference_artifact_values(
    mapping_reference: MappingReference,
) -> dict[str, object]:
    return {
        "mapping_product": mapping_reference.mapping_product,
        "mapping_id": mapping_reference.mapping_id,
        "mapping_version": mapping_reference.version,
        "mapping_run_id": mapping_reference.run_id,
        "mapping_config_hash": mapping_reference.config_hash,
        "mapping_artifact_hash": mapping_reference.artifact_hash,
        "mapping_manifest_hash": mapping_reference.manifest_hash,
        "mapping_reference_hash": mapping_reference.reference_hash,
        "mapping_reference_filename": mapping_reference.reference_filename,
        "mapping_artifact_filename": mapping_reference.artifact_filename,
        "mapping_as_of": pd.Timestamp(mapping_reference.as_of),
    }


def _pair_audit(
    champion_artifacts: pd.DataFrame,
    challenger_artifacts: pd.DataFrame,
    *,
    champion_invalid_folds: frozenset[str],
    challenger_invalid_folds: frozenset[str],
    evidence_context: PromotionEvidenceContext,
    config: PromotionConfig,
) -> _PairAudit:
    codes: list[str] = []
    key_columns = ["outer_fold_id", "sample_id"]
    champion_keys = set(
        champion_artifacts[key_columns].itertuples(index=False, name=None)
    )
    challenger_keys = set(
        challenger_artifacts[key_columns].itertuples(index=False, name=None)
    )
    if champion_keys != challenger_keys:
        _append_unique(codes, "PAIRED_SAMPLE_SET_MISMATCH")

    merged = champion_artifacts.merge(
        challenger_artifacts,
        on=key_columns,
        how="inner",
        suffixes=("_champion", "_challenger"),
        validate="one_to_one",
    )
    valid_pair = pd.Series(True, index=merged.index, dtype="bool")
    dimension_columns = (
        "validation_origin",
        "evaluation_cutoff",
        "target_date",
        "target_visible_date",
        "target_revision_window_end",
        "prediction_scope",
        "prediction_id",
        "horizon_months",
        "interval_nominal_coverage",
        "downstream_asset_id",
        "downstream_loss",
    )
    for column in dimension_columns:
        equal = _series_equal(
            merged[f"{column}_champion"],
            merged[f"{column}_challenger"],
        )
        if not bool(equal.all()):
            _append_unique(codes, "PAIRED_DIMENSION_MISMATCH")
            valid_pair &= equal
    target_columns = (
        "realized_phase",
        "realized_target",
        "downstream_asset_actual",
    )
    for column in target_columns:
        equal = _series_equal(
            merged[f"{column}_champion"],
            merged[f"{column}_challenger"],
        )
        if not bool(equal.all()):
            _append_unique(codes, "PAIRED_TARGET_MISMATCH")
            valid_pair &= equal
    mapping_equal = pd.Series(True, index=merged.index, dtype="bool")
    for column in _MAPPING_ARTIFACT_COLUMNS:
        mapping_equal &= _series_equal(
            merged[f"{column}_champion"],
            merged[f"{column}_challenger"],
        )
    if not bool(mapping_equal.all()):
        _append_unique(codes, "PAIRED_MAPPING_MISMATCH")
        valid_pair &= mapping_equal
    governed_mapping = pd.Series(True, index=merged.index, dtype="bool")
    for column, expected in _mapping_reference_artifact_values(
        evidence_context.mapping_reference
    ).items():
        governed_mapping &= merged[f"{column}_champion"].eq(expected)
        governed_mapping &= merged[f"{column}_challenger"].eq(expected)
    if not bool(governed_mapping.all()):
        _append_unique(codes, "GOVERNED_MAPPING_REFERENCE_MISMATCH")
        valid_pair &= governed_mapping

    complete = merged["status_champion"].eq("complete") & merged[
        "status_challenger"
    ].eq("complete")
    if not bool(complete.all()):
        _append_unique(codes, "INCOMPLETE_PAIRED_COVERAGE")
    valid_pair &= complete
    configured_loss = merged["downstream_loss_champion"].eq(
        config.downstream_loss
    ) & merged["downstream_loss_challenger"].eq(config.downstream_loss)
    if not bool(configured_loss.all()):
        _append_unique(codes, "DOWNSTREAM_LOSS_DEFINITION_MISMATCH")
        valid_pair &= configured_loss
    invalid_folds = champion_invalid_folds | challenger_invalid_folds
    if invalid_folds:
        valid_pair &= ~merged["outer_fold_id"].isin(invalid_folds)

    paired = merged.loc[valid_pair]
    paired_keys = tuple(
        sorted(
            (str(fold_id), str(sample_id))
            for fold_id, sample_id in paired[key_columns].itertuples(
                index=False,
                name=None,
            )
        )
    )
    counts = {
        str(fold_id): int(len(group))
        for fold_id, group in paired.groupby("outer_fold_id", sort=False)
    }
    return _PairAudit(
        codes=tuple(codes),
        paired_keys=paired_keys,
        paired_sample_count=int(len(paired)),
        paired_fold_count=len(counts),
        paired_counts_by_fold=counts,
    )


def _score_artifacts(
    artifacts: pd.DataFrame,
    *,
    paired_keys: tuple[tuple[str, str], ...],
    probability_epsilon: float,
) -> pd.DataFrame:
    if paired_keys:
        artifact_keys = pd.MultiIndex.from_frame(
            artifacts.loc[:, ["outer_fold_id", "sample_id"]]
        )
        paired_index = pd.MultiIndex.from_tuples(
            paired_keys,
            names=("outer_fold_id", "sample_id"),
        )
        scored = artifacts.loc[artifact_keys.isin(paired_index)].copy(deep=True)
    else:
        scored = artifacts.iloc[0:0].copy(deep=True)
    if scored.empty:
        for metric in PROMOTION_METRICS:
            scored[metric] = pd.Series(dtype="float64")
        scored["interval_covered"] = pd.Series(dtype="float64")
        return scored

    probabilities = scored.loc[:, PHASE_PROBABILITY_COLUMNS].to_numpy(dtype="float64")
    labels = np.asarray(
        [
            [float(phase == realized) for phase in PHASES]
            for realized in scored["realized_phase"]
        ],
        dtype="float64",
    )
    scored["brier_score"] = np.square(probabilities - labels).sum(axis=1)
    phase_positions = {phase: position for position, phase in enumerate(PHASES)}
    true_probabilities = np.asarray(
        [
            probabilities[index, phase_positions[str(realized)]]
            for index, realized in enumerate(scored["realized_phase"])
        ],
        dtype="float64",
    )
    scored["log_loss"] = -np.log(np.maximum(true_probabilities, probability_epsilon))
    scored["interval_covered"] = (
        scored["realized_target"].ge(scored["interval_lower"])
        & scored["realized_target"].le(scored["interval_upper"])
    ).astype("float64")
    scored["downstream_asset_oos_loss"] = scored["downstream_asset_loss"].astype(
        "float64"
    )
    return scored


@dataclass(frozen=True)
class _MetricSummary:
    sample_count: int
    value: float
    coverage_rate: float
    nominal_coverage: float


def _metric_summary(frame: pd.DataFrame, metric: str) -> _MetricSummary:
    if frame.empty:
        return _MetricSummary(0, float("nan"), float("nan"), float("nan"))
    if metric == "interval_coverage_error":
        coverage_rate = float(frame["interval_covered"].mean())
        nominal = float(frame["interval_nominal_coverage"].mean())
        return _MetricSummary(
            sample_count=len(frame),
            value=abs(coverage_rate - nominal),
            coverage_rate=coverage_rate,
            nominal_coverage=nominal,
        )
    return _MetricSummary(
        sample_count=len(frame),
        value=float(frame[metric].mean()),
        coverage_rate=float("nan"),
        nominal_coverage=float("nan"),
    )


def _improvement(champion_value: float, challenger_value: float) -> float:
    if not np.isfinite(champion_value) or not np.isfinite(challenger_value):
        return float("nan")
    return champion_value - challenger_value


def _common_nominal(
    champion: _MetricSummary,
    challenger: _MetricSummary,
) -> float:
    if not np.isfinite(champion.nominal_coverage):
        return challenger.nominal_coverage
    if not np.isfinite(challenger.nominal_coverage):
        return champion.nominal_coverage
    if np.isclose(
        champion.nominal_coverage,
        challenger.nominal_coverage,
        atol=1e-12,
        rtol=1e-12,
    ):
        return champion.nominal_coverage
    return float("nan")


def _metric_frames(
    champion_scored: pd.DataFrame,
    challenger_scored: pd.DataFrame,
    *,
    pair_audit: _PairAudit,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fold_ids = sorted(
        set(champion_scored["outer_fold_id"]) | set(challenger_scored["outer_fold_id"])
    )
    fold_records: list[dict[str, object]] = []
    for fold_id in fold_ids:
        champion_fold = champion_scored.loc[
            champion_scored["outer_fold_id"].eq(fold_id)
        ]
        challenger_fold = challenger_scored.loc[
            challenger_scored["outer_fold_id"].eq(fold_id)
        ]
        for metric in PROMOTION_METRICS:
            champion = _metric_summary(champion_fold, metric)
            challenger = _metric_summary(challenger_fold, metric)
            fold_records.append(
                {
                    "outer_fold_id": fold_id,
                    "metric": metric,
                    "champion_sample_count": champion.sample_count,
                    "challenger_sample_count": challenger.sample_count,
                    "paired_sample_count": pair_audit.paired_counts_by_fold.get(
                        str(fold_id),
                        0,
                    ),
                    "champion_value": champion.value,
                    "challenger_value": challenger.value,
                    "improvement": _improvement(
                        champion.value,
                        challenger.value,
                    ),
                    "champion_coverage_rate": champion.coverage_rate,
                    "challenger_coverage_rate": challenger.coverage_rate,
                    "nominal_coverage": _common_nominal(champion, challenger),
                }
            )
    fold_metrics = pd.DataFrame(fold_records, columns=FOLD_METRIC_COLUMNS)

    aggregate_records: list[dict[str, object]] = []
    for metric in PROMOTION_METRICS:
        champion = _metric_summary(champion_scored, metric)
        challenger = _metric_summary(challenger_scored, metric)
        aggregate_records.append(
            {
                "metric": metric,
                "champion_sample_count": champion.sample_count,
                "challenger_sample_count": challenger.sample_count,
                "paired_sample_count": pair_audit.paired_sample_count,
                "fold_count": pair_audit.paired_fold_count,
                "champion_value": champion.value,
                "challenger_value": challenger.value,
                "improvement": _improvement(
                    champion.value,
                    challenger.value,
                ),
                "champion_coverage_rate": champion.coverage_rate,
                "challenger_coverage_rate": challenger.coverage_rate,
                "nominal_coverage": _common_nominal(champion, challenger),
            }
        )
    aggregate_metrics = pd.DataFrame(
        aggregate_records,
        columns=AGGREGATE_METRIC_COLUMNS,
    )
    return fold_metrics, aggregate_metrics


def _aggregate_row(aggregate_metrics: pd.DataFrame, metric: str) -> pd.Series:
    return aggregate_metrics.loc[aggregate_metrics["metric"].eq(metric)].iloc[0]


def _metric_gate(
    aggregate_metrics: pd.DataFrame,
    *,
    metric: str,
    threshold: float,
    reason_code: str,
    coverage_tolerance: float | None = None,
) -> tuple[bool, tuple[str, ...], str]:
    row = _aggregate_row(aggregate_metrics, metric)
    improvement = float(row["improvement"])
    codes: list[str] = []
    if not np.isfinite(improvement) or not improvement > threshold:
        codes.append(reason_code)
    if coverage_tolerance is not None:
        challenger_value = float(row["challenger_value"])
        if not np.isfinite(challenger_value) or challenger_value > coverage_tolerance:
            codes.append("INTERVAL_COVERAGE_OUTSIDE_TOLERANCE")
    detail = f"improvement={improvement!r}; threshold={threshold!r}" + (
        f"; tolerance={coverage_tolerance!r}" if coverage_tolerance is not None else ""
    )
    return not codes, tuple(codes), detail


def _gate_results(
    *,
    model_card_codes: tuple[str, ...],
    feature_audit_codes: tuple[str, ...],
    nested_codes: tuple[str, ...],
    lookahead_codes: tuple[str, ...],
    determinism_codes: tuple[str, ...],
    pair_audit: _PairAudit,
    aggregate_metrics: pd.DataFrame,
    config: PromotionConfig,
) -> pd.DataFrame:
    gate_values: dict[str, tuple[bool, tuple[str, ...], str]] = {
        "model_card": (
            not model_card_codes,
            model_card_codes,
            f"violations={len(model_card_codes)}",
        ),
        "feature_audit": (
            not feature_audit_codes,
            feature_audit_codes,
            f"violations={len(feature_audit_codes)}",
        ),
        "nested_walk_forward": (
            not nested_codes,
            nested_codes,
            f"violations={len(nested_codes)}",
        ),
        "no_lookahead": (
            not lookahead_codes,
            lookahead_codes,
            f"violations={len(lookahead_codes)}",
        ),
        "determinism": (
            not determinism_codes,
            determinism_codes,
            f"violations={len(determinism_codes)}",
        ),
        "paired_coverage": (
            not pair_audit.codes,
            pair_audit.codes,
            f"paired_samples={pair_audit.paired_sample_count}",
        ),
        "minimum_folds": (
            pair_audit.paired_fold_count >= config.minimum_folds,
            (
                ()
                if pair_audit.paired_fold_count >= config.minimum_folds
                else ("INSUFFICIENT_FOLDS",)
            ),
            (
                f"paired_folds={pair_audit.paired_fold_count}; "
                f"minimum={config.minimum_folds}"
            ),
        ),
        "minimum_samples": (
            pair_audit.paired_sample_count >= config.minimum_samples,
            (
                ()
                if pair_audit.paired_sample_count >= config.minimum_samples
                else ("INSUFFICIENT_SAMPLES",)
            ),
            (
                f"paired_samples={pair_audit.paired_sample_count}; "
                f"minimum={config.minimum_samples}"
            ),
        ),
        "brier_score": _metric_gate(
            aggregate_metrics,
            metric="brier_score",
            threshold=config.min_brier_improvement,
            reason_code="BRIER_NOT_IMPROVED",
        ),
        "log_loss": _metric_gate(
            aggregate_metrics,
            metric="log_loss",
            threshold=config.min_log_loss_improvement,
            reason_code="LOG_LOSS_NOT_IMPROVED",
        ),
        "interval_coverage": _metric_gate(
            aggregate_metrics,
            metric="interval_coverage_error",
            threshold=config.min_interval_coverage_improvement,
            reason_code="INTERVAL_COVERAGE_NOT_IMPROVED",
            coverage_tolerance=config.coverage_tolerance,
        ),
        "downstream_asset_oos_loss": _metric_gate(
            aggregate_metrics,
            metric="downstream_asset_oos_loss",
            threshold=config.min_downstream_asset_loss_improvement,
            reason_code="DOWNSTREAM_ASSET_LOSS_NOT_IMPROVED",
        ),
    }
    records = [
        {
            "gate": gate,
            "mandatory": True,
            "passed": gate_values[gate][0],
            "reason_codes": gate_values[gate][1],
            "detail": gate_values[gate][2],
        }
        for gate in MANDATORY_PROMOTION_GATES
    ]
    return pd.DataFrame(records, columns=GATE_RESULT_COLUMNS)


@dataclass(frozen=True)
class _ComputedDecision:
    fold_metrics: pd.DataFrame
    aggregate_metrics: pd.DataFrame
    gate_results: pd.DataFrame
    promotion_decision: str
    live_model: str
    live_model_role: str
    challenger_status: str
    failure_reason_codes: tuple[str, ...]


def _compute_decision(
    champion_artifacts: pd.DataFrame,
    challenger_artifacts: pd.DataFrame,
    *,
    champion_model_card: ModelCard,
    challenger_model_card: ModelCard,
    champion_feature_audit: FeatureAudit,
    challenger_feature_audit: FeatureAudit,
    evidence_context: PromotionEvidenceContext,
    config: PromotionConfig,
    champion_replay_artifacts: pd.DataFrame | None,
    challenger_replay_artifacts: pd.DataFrame | None,
) -> _ComputedDecision:
    champion_pit = _artifact_audit(
        champion_artifacts,
        config=config,
        evidence_context=evidence_context,
    )
    challenger_pit = _artifact_audit(
        challenger_artifacts,
        config=config,
        evidence_context=evidence_context,
    )
    pair_audit = _pair_audit(
        champion_artifacts,
        challenger_artifacts,
        champion_invalid_folds=champion_pit.invalid_fold_ids,
        challenger_invalid_folds=challenger_pit.invalid_fold_ids,
        evidence_context=evidence_context,
        config=config,
    )
    champion_scored = _score_artifacts(
        champion_artifacts,
        paired_keys=pair_audit.paired_keys,
        probability_epsilon=config.probability_epsilon,
    )
    challenger_scored = _score_artifacts(
        challenger_artifacts,
        paired_keys=pair_audit.paired_keys,
        probability_epsilon=config.probability_epsilon,
    )
    fold_metrics, aggregate_metrics = _metric_frames(
        champion_scored,
        challenger_scored,
        pair_audit=pair_audit,
    )
    gate_results = _gate_results(
        model_card_codes=_model_card_codes(
            champion_artifacts,
            challenger_artifacts,
            champion_model_card,
            challenger_model_card,
        ),
        feature_audit_codes=_feature_audit_codes(
            champion_model_card,
            challenger_model_card,
            champion_feature_audit,
            challenger_feature_audit,
        ),
        nested_codes=tuple(
            dict.fromkeys(champion_pit.nested_codes + challenger_pit.nested_codes)
        ),
        lookahead_codes=tuple(
            dict.fromkeys(champion_pit.lookahead_codes + challenger_pit.lookahead_codes)
        ),
        determinism_codes=_replay_codes(
            champion_artifacts,
            challenger_artifacts,
            champion_replay_artifacts,
            challenger_replay_artifacts,
            champion_model_card,
            challenger_model_card,
            champion_feature_audit,
            challenger_feature_audit,
            config,
        ),
        pair_audit=pair_audit,
        aggregate_metrics=aggregate_metrics,
        config=config,
    )
    promoted = bool(gate_results["passed"].all())
    failures: list[str] = []
    for codes in gate_results.loc[~gate_results["passed"], "reason_codes"]:
        for code in codes:
            _append_unique(failures, str(code))
    return _ComputedDecision(
        fold_metrics=fold_metrics,
        aggregate_metrics=aggregate_metrics,
        gate_results=gate_results,
        promotion_decision="promoted" if promoted else "rejected",
        live_model=(
            challenger_model_card.model_id if promoted else champion_model_card.model_id
        ),
        live_model_role="challenger" if promoted else "champion",
        challenger_status="live" if promoted else "experimental",
        failure_reason_codes=tuple(failures),
    )


def _canonical_output_frame(values: object, *, name: str) -> pd.DataFrame:
    columns = {
        "fold_metrics": FOLD_METRIC_COLUMNS,
        "aggregate_metrics": AGGREGATE_METRIC_COLUMNS,
        "gate_results": GATE_RESULT_COLUMNS,
    }[name]
    frame = _required_frame(values, name=name, columns=columns)
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty and np.isinf(numeric.to_numpy(dtype="float64")).any():
        raise ValueError(f"{name} numeric values cannot be infinite")
    if name == "fold_metrics":
        if frame.duplicated(["outer_fold_id", "metric"]).any():
            raise ValueError("fold_metrics contains duplicate fold metrics")
        metric_order = {metric: index for index, metric in enumerate(PROMOTION_METRICS)}
        if not set(frame["metric"]).issubset(metric_order):
            raise ValueError("fold_metrics contains an unknown metric")
        frame["_metric_order"] = frame["metric"].map(metric_order)
        return (
            frame.sort_values(
                ["outer_fold_id", "_metric_order"],
                kind="stable",
            )
            .drop(columns="_metric_order")
            .reset_index(drop=True)
        )
    if name == "aggregate_metrics":
        if frame.duplicated(["metric"]).any():
            raise ValueError("aggregate_metrics contains duplicate metrics")
        if set(frame["metric"]) != set(PROMOTION_METRICS):
            raise ValueError("aggregate_metrics must contain all promotion metrics")
        metric_order = {metric: index for index, metric in enumerate(PROMOTION_METRICS)}
        frame["_metric_order"] = frame["metric"].map(metric_order)
        return (
            frame.sort_values("_metric_order", kind="stable")
            .drop(columns="_metric_order")
            .reset_index(drop=True)
        )

    if frame.duplicated(["gate"]).any():
        raise ValueError("gate_results contains duplicate gates")
    if set(frame["gate"]) != set(MANDATORY_PROMOTION_GATES):
        raise ValueError("gate_results must contain all mandatory gates")
    normalized_codes: list[tuple[str, ...]] = []
    for value in frame["reason_codes"]:
        if isinstance(value, (str, bytes, bytearray)):
            raise TypeError("gate reason_codes must be a sequence")
        try:
            normalized_codes.append(tuple(str(code) for code in value))
        except TypeError as error:
            raise TypeError("gate reason_codes must be a sequence") from error
    frame["reason_codes"] = pd.Series(normalized_codes, dtype="object")
    frame["mandatory"] = frame["mandatory"].astype("bool")
    frame["passed"] = frame["passed"].astype("bool")
    gate_order = {gate: index for index, gate in enumerate(MANDATORY_PROMOTION_GATES)}
    frame["_gate_order"] = frame["gate"].map(gate_order)
    return (
        frame.sort_values("_gate_order", kind="stable")
        .drop(columns="_gate_order")
        .reset_index(drop=True)
    )


def _assert_frame_matches(
    supplied: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    name: str,
) -> None:
    try:
        pd.testing.assert_frame_equal(
            supplied,
            expected,
            check_dtype=True,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(f"{name} is inconsistent with retained artifacts") from error


@dataclass(frozen=True)
class PromotionResult:
    """Immutable decision rebuilt from retained evidence, folds, and governance."""

    fold_metrics: pd.DataFrame
    aggregate_metrics: pd.DataFrame
    gate_results: pd.DataFrame
    champion_artifacts: pd.DataFrame
    challenger_artifacts: pd.DataFrame
    champion_model_card: ModelCard
    challenger_model_card: ModelCard
    champion_feature_audit: FeatureAudit
    challenger_feature_audit: FeatureAudit
    evidence_context: PromotionEvidenceContext
    config: PromotionConfig
    promotion_decision: str
    live_model: str
    live_model_role: str
    challenger_status: str
    failure_reason_codes: Sequence[str]
    champion_replay_artifacts: pd.DataFrame | None = None
    challenger_replay_artifacts: pd.DataFrame | None = None

    def __post_init__(self) -> None:
        config = _rebuild_config(self.config)
        evidence_context = _rebuild_evidence_context(self.evidence_context)
        champion_card = _rebuild_model_card(
            self.champion_model_card,
            name="champion_model_card",
        )
        challenger_card = _rebuild_model_card(
            self.challenger_model_card,
            name="challenger_model_card",
        )
        champion_audit = _rebuild_feature_audit(
            self.champion_feature_audit,
            name="champion_feature_audit",
        )
        challenger_audit = _rebuild_feature_audit(
            self.challenger_feature_audit,
            name="challenger_feature_audit",
        )
        champion_artifacts = _normalize_artifacts(
            object.__getattribute__(self, "champion_artifacts"),
            name="champion_artifacts",
        )
        challenger_artifacts = _normalize_artifacts(
            object.__getattribute__(self, "challenger_artifacts"),
            name="challenger_artifacts",
        )
        raw_champion_replay = object.__getattribute__(
            self,
            "champion_replay_artifacts",
        )
        raw_challenger_replay = object.__getattribute__(
            self,
            "challenger_replay_artifacts",
        )
        champion_replay = (
            None
            if raw_champion_replay is None
            else _normalize_artifacts(
                raw_champion_replay,
                name="champion_replay_artifacts",
            )
        )
        challenger_replay = (
            None
            if raw_challenger_replay is None
            else _normalize_artifacts(
                raw_challenger_replay,
                name="challenger_replay_artifacts",
            )
        )
        computed = _compute_decision(
            champion_artifacts,
            challenger_artifacts,
            champion_model_card=champion_card,
            challenger_model_card=challenger_card,
            champion_feature_audit=champion_audit,
            challenger_feature_audit=challenger_audit,
            evidence_context=evidence_context,
            config=config,
            champion_replay_artifacts=champion_replay,
            challenger_replay_artifacts=challenger_replay,
        )
        for name, expected_values in (
            ("fold_metrics", computed.fold_metrics),
            ("aggregate_metrics", computed.aggregate_metrics),
            ("gate_results", computed.gate_results),
        ):
            supplied = _canonical_output_frame(
                object.__getattribute__(self, name),
                name=name,
            )
            expected = _canonical_output_frame(expected_values, name=name)
            _assert_frame_matches(supplied, expected, name=name)
            object.__setattr__(self, name, expected.copy(deep=True))

        supplied_failures = tuple(
            _normalize_text(code, name="failure reason code")
            for code in self.failure_reason_codes
        )
        scalar_values = {
            "promotion_decision": (
                self.promotion_decision,
                computed.promotion_decision,
            ),
            "live_model": (self.live_model, computed.live_model),
            "live_model_role": (self.live_model_role, computed.live_model_role),
            "challenger_status": (
                self.challenger_status,
                computed.challenger_status,
            ),
            "failure_reason_codes": (
                supplied_failures,
                computed.failure_reason_codes,
            ),
        }
        for name, (supplied, expected) in scalar_values.items():
            if supplied != expected:
                raise ValueError(f"{name} is inconsistent with retained artifacts")

        object.__setattr__(
            self, "champion_artifacts", champion_artifacts.copy(deep=True)
        )
        object.__setattr__(
            self,
            "challenger_artifacts",
            challenger_artifacts.copy(deep=True),
        )
        object.__setattr__(
            self,
            "champion_replay_artifacts",
            None if champion_replay is None else champion_replay.copy(deep=True),
        )
        object.__setattr__(
            self,
            "challenger_replay_artifacts",
            None if challenger_replay is None else challenger_replay.copy(deep=True),
        )
        object.__setattr__(self, "champion_model_card", champion_card)
        object.__setattr__(self, "challenger_model_card", challenger_card)
        object.__setattr__(self, "champion_feature_audit", champion_audit)
        object.__setattr__(self, "challenger_feature_audit", challenger_audit)
        object.__setattr__(self, "evidence_context", evidence_context)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "promotion_decision", computed.promotion_decision)
        object.__setattr__(self, "live_model", computed.live_model)
        object.__setattr__(self, "live_model_role", computed.live_model_role)
        object.__setattr__(self, "challenger_status", computed.challenger_status)
        object.__setattr__(
            self,
            "failure_reason_codes",
            computed.failure_reason_codes,
        )

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    @property
    def promoted(self) -> bool:
        return self.promotion_decision == "promoted"

    @property
    def decision(self) -> str:
        return self.promotion_decision

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        return tuple(self.failure_reason_codes)

    @property
    def frame(self) -> pd.DataFrame:
        return self.aggregate_metrics


def evaluate_challenger_promotion(
    champion_artifacts: pd.DataFrame,
    challenger_artifacts: pd.DataFrame,
    *,
    champion_model_card: ModelCard,
    challenger_model_card: ModelCard,
    champion_feature_audit: FeatureAudit,
    challenger_feature_audit: FeatureAudit,
    evidence_context: PromotionEvidenceContext,
    config: PromotionConfig | None = None,
    champion_replay_artifacts: pd.DataFrame | None = None,
    challenger_replay_artifacts: pd.DataFrame | None = None,
) -> PromotionResult:
    """Evaluate a Challenger only on strict paired, mature, PIT OOS folds."""

    normalized_config = _rebuild_config(config or PromotionConfig())
    normalized_evidence_context = _rebuild_evidence_context(evidence_context)
    champion_card = _rebuild_model_card(
        champion_model_card,
        name="champion_model_card",
    )
    challenger_card = _rebuild_model_card(
        challenger_model_card,
        name="challenger_model_card",
    )
    champion_audit = _rebuild_feature_audit(
        champion_feature_audit,
        name="champion_feature_audit",
    )
    challenger_audit = _rebuild_feature_audit(
        challenger_feature_audit,
        name="challenger_feature_audit",
    )
    normalized_champion = _normalize_artifacts(
        champion_artifacts,
        name="champion_artifacts",
    )
    normalized_challenger = _normalize_artifacts(
        challenger_artifacts,
        name="challenger_artifacts",
    )
    normalized_champion_replay = (
        None
        if champion_replay_artifacts is None
        else _normalize_artifacts(
            champion_replay_artifacts,
            name="champion_replay_artifacts",
        )
    )
    normalized_challenger_replay = (
        None
        if challenger_replay_artifacts is None
        else _normalize_artifacts(
            challenger_replay_artifacts,
            name="challenger_replay_artifacts",
        )
    )
    computed = _compute_decision(
        normalized_champion,
        normalized_challenger,
        champion_model_card=champion_card,
        challenger_model_card=challenger_card,
        champion_feature_audit=champion_audit,
        challenger_feature_audit=challenger_audit,
        evidence_context=normalized_evidence_context,
        config=normalized_config,
        champion_replay_artifacts=normalized_champion_replay,
        challenger_replay_artifacts=normalized_challenger_replay,
    )
    return PromotionResult(
        fold_metrics=computed.fold_metrics,
        aggregate_metrics=computed.aggregate_metrics,
        gate_results=computed.gate_results,
        champion_artifacts=normalized_champion,
        challenger_artifacts=normalized_challenger,
        champion_model_card=champion_card,
        challenger_model_card=challenger_card,
        champion_feature_audit=champion_audit,
        challenger_feature_audit=challenger_audit,
        evidence_context=normalized_evidence_context,
        config=normalized_config,
        promotion_decision=computed.promotion_decision,
        live_model=computed.live_model,
        live_model_role=computed.live_model_role,
        challenger_status=computed.challenger_status,
        failure_reason_codes=computed.failure_reason_codes,
        champion_replay_artifacts=normalized_champion_replay,
        challenger_replay_artifacts=normalized_challenger_replay,
    )


evaluate_promotion = evaluate_challenger_promotion
promote_challenger = evaluate_challenger_promotion


__all__ = [
    "AGGREGATE_METRIC_COLUMNS",
    "FOLD_ARTIFACT_COLUMNS",
    "FOLD_METRIC_COLUMNS",
    "GATE_RESULT_COLUMNS",
    "MANDATORY_PROMOTION_GATES",
    "MAPPING_MANIFEST_METADATA_KEY",
    "MAPPING_REFERENCE_FILENAME",
    "MAPPING_REFERENCE_SCHEMA_VERSION",
    "MappingReference",
    "MappingReferenceVerificationError",
    "OOS_FOLD_ARTIFACT_COLUMNS",
    "PHASE_PROBABILITY_COLUMNS",
    "PHASES",
    "PROMOTION_METRICS",
    "PromotionConfig",
    "PromotionEvidenceContext",
    "PromotionResult",
    "evaluate_challenger_promotion",
    "evaluate_promotion",
    "promote_challenger",
]
