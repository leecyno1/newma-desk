"""Immutable point-in-time feature snapshots for the mapping layer."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
from numbers import Integral, Real
import re
from types import MappingProxyType
from typing import Self, TypeVar

import numpy as np

from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


_EXPECTED_CYCLE_IDS = tuple(f"C{position}" for position in range(1, 8))
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_KEY = TypeVar("_KEY")
_VALUE = TypeVar("_VALUE")


class FeatureKind(StrEnum):
    """Governed feature categories in a current mapping snapshot."""

    CYCLE = "cycle"
    CHANNEL = "channel"
    VALUATION = "valuation"
    EARNINGS = "earnings"
    POSITIONING = "positioning"
    LIQUIDITY = "liquidity"
    EVENT = "event"
    HISTORICAL_POSTERIOR = "historical_posterior"


class FreshnessStatus(StrEnum):
    """Per-feature freshness classification at the requested cutoff."""

    FRESH = "fresh"
    STALE = "stale"


class _FrozenMapping(Mapping[_KEY, _VALUE]):
    __slots__ = ("_values",)

    def __init__(self, values: Mapping[_KEY, _VALUE]) -> None:
        object.__setattr__(
            self,
            "_values",
            MappingProxyType(dict(values)),
        )

    def __getitem__(self, key: _KEY) -> _VALUE:
        return self._values[key]

    def __iter__(self) -> Iterator[_KEY]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return repr(dict(self._values))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self


def _strict_date(value: object, *, name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")
    return value


def _nonempty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def _optional_identifier(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _nonempty_string(value, name=name)


def _nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return normalized


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    return normalized


def _mapping_items(
    values: Mapping[object, object],
    *,
    name: str,
) -> list[tuple[str, object]]:
    keys = list(values)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name} keys must be unique")
    normalized: list[tuple[str, object]] = []
    for key in keys:
        normalized_key = _nonempty_string(key, name=f"{name} key")
        normalized.append((normalized_key, values[key]))
    return sorted(normalized, key=lambda item: item[0])


def _freeze_payload_value(value: object, *, path: str) -> object:
    if value is None:
        raise ValueError(f"payload values cannot be missing at {path}")
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, datetime):
        raise TypeError(f"payload value at {path} must not be a datetime")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"payload strings cannot be blank at {path}")
        return value
    if isinstance(value, (Integral, np.integer)):
        return int(value)
    if isinstance(value, (Real, np.floating)):
        normalized = float(value)
        if not math.isfinite(normalized):
            raise ValueError(f"payload numeric values must be finite at {path}")
        return normalized
    if isinstance(value, Mapping):
        items = _mapping_items(value, name=f"payload mapping at {path}")
        if not items:
            raise ValueError(f"payload mappings cannot be empty at {path}")
        return _FrozenMapping(
            {
                key: _freeze_payload_value(
                    nested,
                    path=f"{path}.{key}",
                )
                for key, nested in items
            }
        )
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"payload sequences cannot be empty at {path}")
        return tuple(
            _freeze_payload_value(item, path=f"{path}[{position}]")
            for position, item in enumerate(value)
        )
    raise TypeError(
        "payload values must be JSON-like finite scalars, dates, mappings, "
        f"or sequences; invalid value at {path}"
    )


def _canonical_payload_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            "type": "mapping",
            "items": [
                {
                    "key": {"type": "string", "value": str(key)},
                    "value": _canonical_payload_value(value[key]),
                }
                for key in sorted(value)
            ],
        }
    if isinstance(value, tuple):
        return {
            "type": "sequence",
            "items": [_canonical_payload_value(item) for item in value],
        }
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value.hex()}
    if isinstance(value, str):
        return {"type": "string", "value": str(value)}
    raise TypeError("unsupported frozen payload value")


def _feature_key_sort_key(key: FeatureKey) -> tuple[str, str, str]:
    return (key.kind.value, key.entity_id or "", key.feature_id)


@dataclass(frozen=True)
class FeatureKey:
    """Stable identity for one governed feature."""

    kind: FeatureKind
    feature_id: str
    entity_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FeatureKind):
            raise TypeError("kind must be a FeatureKind")
        object.__setattr__(
            self,
            "feature_id",
            _nonempty_string(self.feature_id, name="feature_id"),
        )
        object.__setattr__(
            self,
            "entity_id",
            _optional_identifier(self.entity_id, name="entity_id"),
        )

    def __str__(self) -> str:
        scope = f"{self.entity_id}:" if self.entity_id is not None else ""
        return f"{self.kind.value}:{scope}{self.feature_id}"


@dataclass(frozen=True)
class FeaturePayload:
    """Immutable feature identity and arbitrary governed value payload."""

    kind: FeatureKind
    feature_id: str
    values: Mapping[str, object]
    entity_id: str | None = None
    _payload_digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = FeatureKey(
            kind=self.kind,
            feature_id=self.feature_id,
            entity_id=self.entity_id,
        )
        if not isinstance(self.values, Mapping):
            raise TypeError("values must be a mapping")
        items = _mapping_items(self.values, name="payload")
        if not items:
            raise ValueError("payload must contain at least one value")
        frozen_values = _FrozenMapping(
            {
                field_name: _freeze_payload_value(
                    value,
                    path=field_name,
                )
                for field_name, value in items
            }
        )
        object.__setattr__(self, "kind", key.kind)
        object.__setattr__(self, "feature_id", key.feature_id)
        object.__setattr__(self, "entity_id", key.entity_id)
        object.__setattr__(self, "values", frozen_values)
        canonical = {
            "entity_id": key.entity_id,
            "feature_id": key.feature_id,
            "kind": key.kind.value,
            "values": _canonical_payload_value(frozen_values),
        }
        encoded = json.dumps(
            canonical,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        object.__setattr__(
            self,
            "_payload_digest",
            hashlib.sha256(encoded).hexdigest(),
        )

    @property
    def key(self) -> FeatureKey:
        return FeatureKey(
            kind=self.kind,
            feature_id=self.feature_id,
            entity_id=self.entity_id,
        )

    @property
    def payload_digest(self) -> str:
        return self._payload_digest


@dataclass(frozen=True)
class FeatureProvenance:
    """Complete point-in-time lineage for one feature payload."""

    kind: FeatureKind
    feature_id: str
    observation_date: date
    release_date: date
    vintage_date: date
    source: str
    unit: str
    retrieval_time: datetime
    revision_number: int
    quality_status: str
    vintage_kind: VintageKind
    methodology: str
    payload_digest: str
    entity_id: str | None = None
    vintage_caveat: str | None = None

    def __post_init__(self) -> None:
        key = FeatureKey(
            kind=self.kind,
            feature_id=self.feature_id,
            entity_id=self.entity_id,
        )
        observation_date = _strict_date(
            self.observation_date,
            name="observation_date",
        )
        release_date = _strict_date(self.release_date, name="release_date")
        vintage_date = _strict_date(self.vintage_date, name="vintage_date")
        if release_date < observation_date:
            raise ValueError("release_date cannot precede observation_date")
        if vintage_date < release_date:
            raise ValueError("vintage_date cannot precede release_date")
        if not isinstance(self.retrieval_time, datetime):
            raise TypeError("retrieval_time must be a datetime")
        if (
            self.retrieval_time.tzinfo is None
            or self.retrieval_time.utcoffset() is None
        ):
            raise ValueError("retrieval_time must be timezone-aware")
        retrieval_time = self.retrieval_time.astimezone(timezone.utc)
        if retrieval_time.date() < vintage_date:
            raise ValueError("retrieval_time UTC date cannot precede vintage_date")
        revision_number = _nonnegative_integer(
            self.revision_number,
            name="revision_number",
        )
        if not isinstance(self.vintage_kind, VintageKind):
            raise TypeError("vintage_kind must be a VintageKind")
        source = _nonempty_string(self.source, name="source")
        unit = _nonempty_string(self.unit, name="unit")
        quality_status = _nonempty_string(
            self.quality_status,
            name="quality_status",
        )
        methodology = _nonempty_string(
            self.methodology,
            name="methodology",
        )
        if not isinstance(self.payload_digest, str) or not _SHA256_PATTERN.fullmatch(
            self.payload_digest
        ):
            raise ValueError("payload_digest must be a lowercase SHA-256 digest")
        caveat = _optional_identifier(
            self.vintage_caveat,
            name="vintage_caveat",
        )
        if self.vintage_kind is VintageKind.PSEUDO_VINTAGE and caveat is None:
            raise ValueError("pseudo_vintage provenance requires a caveat")
        if self.vintage_kind is not VintageKind.PSEUDO_VINTAGE and caveat is not None:
            raise ValueError(
                "only pseudo_vintage provenance may define a vintage_caveat"
            )
        object.__setattr__(self, "kind", key.kind)
        object.__setattr__(self, "feature_id", key.feature_id)
        object.__setattr__(self, "entity_id", key.entity_id)
        object.__setattr__(self, "observation_date", observation_date)
        object.__setattr__(self, "release_date", release_date)
        object.__setattr__(self, "vintage_date", vintage_date)
        object.__setattr__(self, "retrieval_time", retrieval_time)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "quality_status", quality_status)
        object.__setattr__(self, "methodology", methodology)
        object.__setattr__(self, "vintage_caveat", caveat)

    @classmethod
    def from_payload(
        cls,
        payload: FeaturePayload,
        *,
        observation_date: date,
        release_date: date,
        vintage_date: date,
        source: str,
        unit: str,
        retrieval_time: datetime,
        revision_number: int,
        quality_status: str,
        vintage_kind: VintageKind,
        methodology: str,
        vintage_caveat: str | None = None,
    ) -> Self:
        if not isinstance(payload, FeaturePayload):
            raise TypeError("payload must be a FeaturePayload")
        return cls(
            kind=payload.kind,
            feature_id=payload.feature_id,
            entity_id=payload.entity_id,
            observation_date=observation_date,
            release_date=release_date,
            vintage_date=vintage_date,
            source=source,
            unit=unit,
            retrieval_time=retrieval_time,
            revision_number=revision_number,
            quality_status=quality_status,
            vintage_kind=vintage_kind,
            methodology=methodology,
            payload_digest=payload.payload_digest,
            vintage_caveat=vintage_caveat,
        )

    @property
    def key(self) -> FeatureKey:
        return FeatureKey(
            kind=self.kind,
            feature_id=self.feature_id,
            entity_id=self.entity_id,
        )

    @property
    def visible_date(self) -> date:
        return max(self.release_date, self.vintage_date)


@dataclass(frozen=True)
class FreshnessPolicy:
    """Maximum acceptable ages for observation and visibility dates."""

    max_observation_age_days: int
    max_visible_age_days: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_observation_age_days",
            _nonnegative_integer(
                self.max_observation_age_days,
                name="max_observation_age_days",
            ),
        )
        object.__setattr__(
            self,
            "max_visible_age_days",
            _nonnegative_integer(
                self.max_visible_age_days,
                name="max_visible_age_days",
            ),
        )


@dataclass(frozen=True)
class StructuralDriftFlag:
    """Explicit and auditable structural-drift evaluation for one feature."""

    detected: bool
    score: float
    threshold: float
    method: str
    baseline_id: str
    evaluated_at: date
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.detected, bool):
            raise TypeError("detected must be a boolean")
        score = _finite_real(self.score, name="score")
        threshold = _finite_real(self.threshold, name="threshold")
        if threshold < 0.0:
            raise ValueError("threshold must be nonnegative")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(
            self,
            "method",
            _nonempty_string(self.method, name="method"),
        )
        object.__setattr__(
            self,
            "baseline_id",
            _nonempty_string(self.baseline_id, name="baseline_id"),
        )
        object.__setattr__(
            self,
            "evaluated_at",
            _strict_date(self.evaluated_at, name="evaluated_at"),
        )
        object.__setattr__(
            self,
            "reason",
            _nonempty_string(self.reason, name="reason"),
        )


@dataclass(frozen=True)
class FeatureInput:
    """One validated feature input before an ``as_of`` cutoff is applied."""

    payload: FeaturePayload
    provenance: FeatureProvenance
    freshness_policy: FreshnessPolicy
    structural_drift: StructuralDriftFlag

    def __post_init__(self) -> None:
        if not isinstance(self.payload, FeaturePayload):
            raise TypeError("payload must be a FeaturePayload")
        if not isinstance(self.provenance, FeatureProvenance):
            raise TypeError("provenance must be a FeatureProvenance")
        if not isinstance(self.freshness_policy, FreshnessPolicy):
            raise TypeError("freshness_policy must be a FreshnessPolicy")
        if not isinstance(self.structural_drift, StructuralDriftFlag):
            raise TypeError("structural_drift must be a StructuralDriftFlag")
        if self.payload.key != self.provenance.key:
            raise ValueError("payload identity does not match provenance")
        if self.payload.payload_digest != self.provenance.payload_digest:
            raise ValueError("payload digest does not match provenance")

    @property
    def key(self) -> FeatureKey:
        return self.payload.key


@dataclass(frozen=True)
class FreshnessFlag:
    """Computed point-in-time freshness evidence for one feature."""

    as_of: date
    observation_date: date
    visible_date: date
    observation_age_days: int
    visible_age_days: int
    max_observation_age_days: int
    max_visible_age_days: int
    status: FreshnessStatus
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        as_of = _strict_date(self.as_of, name="as_of")
        observation_date = _strict_date(
            self.observation_date,
            name="observation_date",
        )
        visible_date = _strict_date(self.visible_date, name="visible_date")
        if observation_date > as_of:
            raise ValueError("observation_date cannot follow as_of")
        if visible_date > as_of:
            raise ValueError("visible_date cannot follow as_of")
        observation_age = _nonnegative_integer(
            self.observation_age_days,
            name="observation_age_days",
        )
        visible_age = _nonnegative_integer(
            self.visible_age_days,
            name="visible_age_days",
        )
        max_observation_age = _nonnegative_integer(
            self.max_observation_age_days,
            name="max_observation_age_days",
        )
        max_visible_age = _nonnegative_integer(
            self.max_visible_age_days,
            name="max_visible_age_days",
        )
        if observation_age != (as_of - observation_date).days:
            raise ValueError("observation_age_days is inconsistent with dates")
        if visible_age != (as_of - visible_date).days:
            raise ValueError("visible_age_days is inconsistent with dates")
        if not isinstance(self.status, FreshnessStatus):
            raise TypeError("status must be a FreshnessStatus")
        if isinstance(self.reasons, str):
            raise TypeError("reasons must be an iterable of strings")
        reasons = tuple(self.reasons)
        if any(not isinstance(reason, str) or not reason for reason in reasons):
            raise ValueError("reasons must contain non-empty strings")
        expected_reasons: list[str] = []
        if observation_age > max_observation_age:
            expected_reasons.append("observation_age_exceeded")
        if visible_age > max_visible_age:
            expected_reasons.append("visible_age_exceeded")
        expected_status = (
            FreshnessStatus.STALE if expected_reasons else FreshnessStatus.FRESH
        )
        if self.status is not expected_status or reasons != tuple(expected_reasons):
            raise ValueError("freshness status or reasons are inconsistent")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "observation_date", observation_date)
        object.__setattr__(self, "visible_date", visible_date)
        object.__setattr__(self, "observation_age_days", observation_age)
        object.__setattr__(self, "visible_age_days", visible_age)
        object.__setattr__(
            self,
            "max_observation_age_days",
            max_observation_age,
        )
        object.__setattr__(self, "max_visible_age_days", max_visible_age)
        object.__setattr__(self, "reasons", reasons)

    @classmethod
    def evaluate(
        cls,
        *,
        as_of: date,
        provenance: FeatureProvenance,
        policy: FreshnessPolicy,
    ) -> Self:
        if not isinstance(provenance, FeatureProvenance):
            raise TypeError("provenance must be a FeatureProvenance")
        if not isinstance(policy, FreshnessPolicy):
            raise TypeError("policy must be a FreshnessPolicy")
        cutoff = _strict_date(as_of, name="as_of")
        observation_age = (cutoff - provenance.observation_date).days
        visible_age = (cutoff - provenance.visible_date).days
        reasons: list[str] = []
        if observation_age > policy.max_observation_age_days:
            reasons.append("observation_age_exceeded")
        if visible_age > policy.max_visible_age_days:
            reasons.append("visible_age_exceeded")
        return cls(
            as_of=cutoff,
            observation_date=provenance.observation_date,
            visible_date=provenance.visible_date,
            observation_age_days=observation_age,
            visible_age_days=visible_age,
            max_observation_age_days=policy.max_observation_age_days,
            max_visible_age_days=policy.max_visible_age_days,
            status=(FreshnessStatus.STALE if reasons else FreshnessStatus.FRESH),
            reasons=tuple(reasons),
        )

    @property
    def is_fresh(self) -> bool:
        return self.status is FreshnessStatus.FRESH


@dataclass(frozen=True)
class FeatureFlags:
    """All per-feature operational flags retained by the snapshot."""

    freshness: FreshnessFlag
    structural_drift: StructuralDriftFlag
    vintage_kind: VintageKind
    is_pseudo_vintage: bool

    def __post_init__(self) -> None:
        if not isinstance(self.freshness, FreshnessFlag):
            raise TypeError("freshness must be a FreshnessFlag")
        if not isinstance(self.structural_drift, StructuralDriftFlag):
            raise TypeError("structural_drift must be a StructuralDriftFlag")
        if not isinstance(self.vintage_kind, VintageKind):
            raise TypeError("vintage_kind must be a VintageKind")
        if not isinstance(self.is_pseudo_vintage, bool):
            raise TypeError("is_pseudo_vintage must be a boolean")
        expected = self.vintage_kind is VintageKind.PSEUDO_VINTAGE
        if self.is_pseudo_vintage is not expected:
            raise ValueError("is_pseudo_vintage is inconsistent with vintage_kind")


@dataclass(frozen=True)
class CurrentFeature:
    """One feature made current at the snapshot cutoff."""

    payload: FeaturePayload
    provenance: FeatureProvenance
    flags: FeatureFlags

    def __post_init__(self) -> None:
        if not isinstance(self.payload, FeaturePayload):
            raise TypeError("payload must be a FeaturePayload")
        if not isinstance(self.provenance, FeatureProvenance):
            raise TypeError("provenance must be a FeatureProvenance")
        if not isinstance(self.flags, FeatureFlags):
            raise TypeError("flags must be FeatureFlags")
        if self.payload.key != self.provenance.key:
            raise ValueError("payload identity does not match provenance")
        if self.payload.payload_digest != self.provenance.payload_digest:
            raise ValueError("payload digest does not match provenance")
        if self.flags.vintage_kind is not self.provenance.vintage_kind:
            raise ValueError("feature flags do not match provenance vintage_kind")

    @property
    def key(self) -> FeatureKey:
        return self.payload.key

    @property
    def kind(self) -> FeatureKind:
        return self.payload.kind

    @property
    def feature_id(self) -> str:
        return self.payload.feature_id

    @property
    def entity_id(self) -> str | None:
        return self.payload.entity_id

    @property
    def values(self) -> Mapping[str, object]:
        return self.payload.values

    @property
    def freshness(self) -> FreshnessFlag:
        return self.flags.freshness

    @property
    def structural_drift(self) -> StructuralDriftFlag:
        return self.flags.structural_drift

    @property
    def is_pseudo_vintage(self) -> bool:
        return self.flags.is_pseudo_vintage


@dataclass(frozen=True)
class SnapshotProvenance:
    """Run-level and feature-level provenance for one complete snapshot."""

    run_context: RunContext
    features: Mapping[FeatureKey, FeatureProvenance]
    vintage_kinds: tuple[VintageKind, ...]
    pseudo_vintage_features: tuple[FeatureKey, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_context, RunContext):
            raise TypeError("run_context must be a RunContext")
        if not isinstance(self.features, Mapping):
            raise TypeError("features must be a mapping")
        feature_keys = list(self.features)
        if len(feature_keys) != len(set(feature_keys)):
            raise ValueError("feature provenance keys must be unique")
        normalized_features: dict[FeatureKey, FeatureProvenance] = {}
        for key in sorted(feature_keys, key=_feature_key_sort_key):
            provenance = self.features[key]
            if not isinstance(key, FeatureKey):
                raise TypeError("feature provenance keys must be FeatureKey values")
            if not isinstance(provenance, FeatureProvenance):
                raise TypeError(
                    "feature provenance values must be FeatureProvenance values"
                )
            if key != provenance.key:
                raise ValueError("feature provenance key does not match its value")
            normalized_features[key] = provenance
        kinds = tuple(self.vintage_kinds)
        if any(not isinstance(kind, VintageKind) for kind in kinds):
            raise TypeError("vintage_kinds must contain VintageKind values")
        if len(kinds) != len(set(kinds)):
            raise ValueError("vintage_kinds must be unique")
        expected_kinds = tuple(
            sorted(
                {value.vintage_kind for value in normalized_features.values()},
                key=lambda kind: kind.value,
            )
        )
        if kinds != expected_kinds:
            raise ValueError("vintage_kinds do not match feature provenance")
        pseudo_keys = tuple(self.pseudo_vintage_features)
        if len(pseudo_keys) != len(set(pseudo_keys)):
            raise ValueError("pseudo_vintage_features must be unique")
        if any(not isinstance(key, FeatureKey) for key in pseudo_keys):
            raise TypeError("pseudo_vintage_features must contain FeatureKey values")
        expected_pseudo = tuple(
            sorted(
                (
                    key
                    for key, value in normalized_features.items()
                    if value.vintage_kind is VintageKind.PSEUDO_VINTAGE
                ),
                key=_feature_key_sort_key,
            )
        )
        if pseudo_keys != expected_pseudo:
            raise ValueError("pseudo_vintage_features do not match feature provenance")
        object.__setattr__(
            self,
            "features",
            _FrozenMapping(normalized_features),
        )
        object.__setattr__(self, "vintage_kinds", kinds)
        object.__setattr__(self, "pseudo_vintage_features", pseudo_keys)

    @property
    def run_id(self) -> str:
        return self.run_context.run_id

    @property
    def as_of(self) -> date:
        return self.run_context.as_of

    @property
    def data_vintage(self) -> date:
        return self.run_context.data_vintage

    @property
    def model_version(self) -> str:
        return self.run_context.model_version

    @property
    def config_hash(self) -> str:
        return self.run_context.config_hash

    @property
    def created_at(self) -> datetime:
        return self.run_context.created_at

    @property
    def input_checksums(self) -> Mapping[str, str]:
        return self.run_context.input_checksums

    @property
    def quality_summary(self) -> Mapping[str, object]:
        return self.run_context.quality_summary

    @property
    def product_checksums(self) -> Mapping[str, str]:
        return self.run_context.product_checksums


def _feature_inputs(values: object, *, name: str) -> tuple[FeatureInput, ...]:
    if isinstance(values, (str, bytes, bytearray, Mapping)) or isinstance(
        values,
        (bool, np.bool_),
    ):
        raise TypeError(f"{name} must be an iterable of FeatureInput values")
    try:
        normalized = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of FeatureInput values") from error
    if not normalized:
        raise ValueError(f"{name} must contain at least one feature")
    if any(not isinstance(value, FeatureInput) for value in normalized):
        raise TypeError(f"{name} must contain only FeatureInput values")
    return normalized


def _current_feature(feature: FeatureInput, *, as_of: date) -> CurrentFeature:
    provenance = feature.provenance
    for field_name in ("observation_date", "release_date", "vintage_date"):
        visible_date = getattr(provenance, field_name)
        if visible_date > as_of:
            raise ValueError(
                f"{feature.key} {field_name} {visible_date} exceeds as_of {as_of}"
            )
    if feature.structural_drift.evaluated_at > as_of:
        raise ValueError(
            f"{feature.key} structural drift evaluated_at "
            f"{feature.structural_drift.evaluated_at} exceeds as_of {as_of}"
        )
    freshness = FreshnessFlag.evaluate(
        as_of=as_of,
        provenance=provenance,
        policy=feature.freshness_policy,
    )
    return CurrentFeature(
        payload=feature.payload,
        provenance=provenance,
        flags=FeatureFlags(
            freshness=freshness,
            structural_drift=feature.structural_drift,
            vintage_kind=provenance.vintage_kind,
            is_pseudo_vintage=(provenance.vintage_kind is VintageKind.PSEUDO_VINTAGE),
        ),
    )


def _normalize_group(
    values: object,
    *,
    name: str,
    expected_kind: FeatureKind,
    as_of: date,
    require_entity_id: bool = False,
) -> tuple[CurrentFeature, ...]:
    inputs = _feature_inputs(values, name=name)
    current: list[CurrentFeature] = []
    seen: set[FeatureKey] = set()
    for feature in inputs:
        if feature.payload.kind is not expected_kind:
            raise ValueError(f"{name} must contain only {expected_kind.name} features")
        if require_entity_id and feature.payload.entity_id is None:
            raise ValueError(f"{name} features require entity_id")
        normalized = _current_feature(feature, as_of=as_of)
        if normalized.key in seen:
            raise ValueError(f"duplicate feature in {name}: {normalized.feature_id}")
        seen.add(normalized.key)
        current.append(normalized)
    return tuple(
        sorted(current, key=lambda feature: _feature_key_sort_key(feature.key))
    )


@dataclass(frozen=True, init=False)
class CurrentFeatureSnapshot:
    """Complete immutable current feature surface at one requested cutoff."""

    as_of: date
    cycle_states: tuple[CurrentFeature, ...]
    channel_states: tuple[CurrentFeature, ...]
    valuation_controls: tuple[CurrentFeature, ...]
    earnings_controls: tuple[CurrentFeature, ...]
    positioning_controls: tuple[CurrentFeature, ...]
    liquidity_controls: tuple[CurrentFeature, ...]
    event_scenarios: tuple[CurrentFeature, ...]
    historical_posterior: tuple[CurrentFeature, ...]
    run_context: RunContext
    provenance: SnapshotProvenance
    _features: tuple[CurrentFeature, ...] = field(repr=False)
    _asset_controls: Mapping[FeatureKind, tuple[CurrentFeature, ...]] = field(
        repr=False
    )
    _freshness: Mapping[FeatureKey, FreshnessFlag] = field(repr=False)
    _structural_drift: Mapping[FeatureKey, StructuralDriftFlag] = field(repr=False)

    def __init__(
        self,
        *,
        as_of: date,
        cycle_states: object,
        channel_states: object,
        valuation_controls: object,
        earnings_controls: object,
        positioning_controls: object,
        liquidity_controls: object,
        event_scenarios: object,
        historical_posterior: object,
        run_context: RunContext,
    ) -> None:
        cutoff = _strict_date(as_of, name="as_of")
        if not isinstance(run_context, RunContext):
            raise TypeError("run_context must be a RunContext")
        if run_context.as_of != cutoff:
            raise ValueError(
                "run_context as_of must match snapshot as_of: "
                f"{run_context.as_of} != {cutoff}"
            )
        if run_context.data_vintage > cutoff:
            raise ValueError("run_context data_vintage cannot follow as_of")

        normalized_cycles = _normalize_group(
            cycle_states,
            name="cycle_states",
            expected_kind=FeatureKind.CYCLE,
            as_of=cutoff,
        )
        cycle_ids = [feature.feature_id for feature in normalized_cycles]
        cycle_id_set = set(cycle_ids)
        expected_cycle_ids = set(_EXPECTED_CYCLE_IDS)
        if len(normalized_cycles) != len(_EXPECTED_CYCLE_IDS) or (
            cycle_id_set != expected_cycle_ids
        ):
            details: list[str] = []
            missing = sorted(expected_cycle_ids - cycle_id_set)
            unexpected = sorted(cycle_id_set - expected_cycle_ids)
            duplicates = sorted(
                cycle_id for cycle_id in cycle_id_set if cycle_ids.count(cycle_id) > 1
            )
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected {', '.join(unexpected)}")
            if duplicates:
                details.append(f"duplicate {', '.join(duplicates)}")
            raise ValueError(
                "cycle_states must contain exactly C1-C7; " + "; ".join(details)
            )
        normalized_channels = _normalize_group(
            channel_states,
            name="channel_states",
            expected_kind=FeatureKind.CHANNEL,
            as_of=cutoff,
        )
        normalized_valuation = _normalize_group(
            valuation_controls,
            name="valuation_controls",
            expected_kind=FeatureKind.VALUATION,
            as_of=cutoff,
            require_entity_id=True,
        )
        normalized_earnings = _normalize_group(
            earnings_controls,
            name="earnings_controls",
            expected_kind=FeatureKind.EARNINGS,
            as_of=cutoff,
            require_entity_id=True,
        )
        normalized_positioning = _normalize_group(
            positioning_controls,
            name="positioning_controls",
            expected_kind=FeatureKind.POSITIONING,
            as_of=cutoff,
            require_entity_id=True,
        )
        normalized_liquidity = _normalize_group(
            liquidity_controls,
            name="liquidity_controls",
            expected_kind=FeatureKind.LIQUIDITY,
            as_of=cutoff,
            require_entity_id=True,
        )
        normalized_events = _normalize_group(
            event_scenarios,
            name="event_scenarios",
            expected_kind=FeatureKind.EVENT,
            as_of=cutoff,
        )
        normalized_posterior = _normalize_group(
            historical_posterior,
            name="historical_posterior",
            expected_kind=FeatureKind.HISTORICAL_POSTERIOR,
            as_of=cutoff,
        )
        all_features = (
            normalized_cycles
            + normalized_channels
            + normalized_valuation
            + normalized_earnings
            + normalized_positioning
            + normalized_liquidity
            + normalized_events
            + normalized_posterior
        )
        for feature in all_features:
            if feature.provenance.vintage_date > run_context.data_vintage:
                raise ValueError(
                    f"{feature.key} vintage_date "
                    f"{feature.provenance.vintage_date} exceeds run_context "
                    f"data_vintage {run_context.data_vintage}"
                )
        keys = [feature.key for feature in all_features]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate features are not supported")
        feature_provenance = {
            feature.key: feature.provenance for feature in all_features
        }
        vintage_kinds = tuple(
            sorted(
                {feature.provenance.vintage_kind for feature in all_features},
                key=lambda kind: kind.value,
            )
        )
        pseudo_features = tuple(
            sorted(
                (feature.key for feature in all_features if feature.is_pseudo_vintage),
                key=_feature_key_sort_key,
            )
        )
        provenance = SnapshotProvenance(
            run_context=run_context,
            features=feature_provenance,
            vintage_kinds=vintage_kinds,
            pseudo_vintage_features=pseudo_features,
        )
        asset_controls = _FrozenMapping(
            {
                FeatureKind.VALUATION: normalized_valuation,
                FeatureKind.EARNINGS: normalized_earnings,
                FeatureKind.POSITIONING: normalized_positioning,
                FeatureKind.LIQUIDITY: normalized_liquidity,
            }
        )
        freshness = _FrozenMapping(
            {feature.key: feature.freshness for feature in all_features}
        )
        structural_drift = _FrozenMapping(
            {feature.key: feature.structural_drift for feature in all_features}
        )

        object.__setattr__(self, "as_of", cutoff)
        object.__setattr__(self, "cycle_states", normalized_cycles)
        object.__setattr__(self, "channel_states", normalized_channels)
        object.__setattr__(self, "valuation_controls", normalized_valuation)
        object.__setattr__(self, "earnings_controls", normalized_earnings)
        object.__setattr__(self, "positioning_controls", normalized_positioning)
        object.__setattr__(self, "liquidity_controls", normalized_liquidity)
        object.__setattr__(self, "event_scenarios", normalized_events)
        object.__setattr__(self, "historical_posterior", normalized_posterior)
        object.__setattr__(self, "run_context", run_context)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "_features", all_features)
        object.__setattr__(self, "_asset_controls", asset_controls)
        object.__setattr__(self, "_freshness", freshness)
        object.__setattr__(self, "_structural_drift", structural_drift)

    @property
    def features(self) -> tuple[CurrentFeature, ...]:
        return self._features

    @property
    def asset_controls(
        self,
    ) -> Mapping[FeatureKind, tuple[CurrentFeature, ...]]:
        return self._asset_controls

    @property
    def freshness(self) -> Mapping[FeatureKey, FreshnessFlag]:
        return self._freshness

    @property
    def structural_drift(
        self,
    ) -> Mapping[FeatureKey, StructuralDriftFlag]:
        return self._structural_drift

    @property
    def contains_pseudo_vintage(self) -> bool:
        return bool(self.provenance.pseudo_vintage_features)


__all__ = [
    "CurrentFeature",
    "CurrentFeatureSnapshot",
    "FeatureFlags",
    "FeatureInput",
    "FeatureKey",
    "FeatureKind",
    "FeaturePayload",
    "FeatureProvenance",
    "FreshnessFlag",
    "FreshnessPolicy",
    "FreshnessStatus",
    "SnapshotProvenance",
    "StructuralDriftFlag",
]
