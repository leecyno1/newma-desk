"""Immutable model-version records for governed cycle recalibration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from numbers import Integral, Real
from types import MappingProxyType

import numpy as np


_CYCLE_IDS = frozenset({"C1", "C2", "C3", "C4", "C5", "C6", "C7"})
_QUARTER_ENDS = frozenset({(3, 31), (6, 30), (9, 30), (12, 31)})


class RecalibrationStatus(StrEnum):
    """Outcome of a governed quarterly recalibration decision."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RecalibrationReason(StrEnum):
    """Explicit reason codes retained with every model version."""

    ACCEPTED = "accepted"
    ACCEPTED_DRIFT_LIMITED = "accepted_drift_limited"
    MANUAL_OVERRIDE = "manual_override"
    MANUAL_OVERRIDE_NOT_APPLIED = "manual_override_not_applied"
    CANDIDATE_OUTSIDE_SEARCH_BAND = "candidate_outside_search_band"
    LOW_RED_NOISE_SCORE = "low_red_noise_score"
    BOOTSTRAP_INTERVAL_TOO_WIDE = "bootstrap_interval_too_wide"
    LOW_CATEGORY_SUPPORT = "low_category_support"
    WEAK_MACRO_ONLY_SUPPORT = "weak_macro_only_support"
    WEAK_CATEGORY_BALANCED_SUPPORT = "weak_category_balanced_support"
    LOW_METHOD_AGREEMENT = "low_method_agreement"


_ACCEPTED_REASONS = frozenset(
    {
        RecalibrationReason.ACCEPTED,
        RecalibrationReason.ACCEPTED_DRIFT_LIMITED,
        RecalibrationReason.MANUAL_OVERRIDE,
    }
)
_EVIDENCE_FAILURE_REASONS = frozenset(
    {
        RecalibrationReason.CANDIDATE_OUTSIDE_SEARCH_BAND,
        RecalibrationReason.LOW_RED_NOISE_SCORE,
        RecalibrationReason.BOOTSTRAP_INTERVAL_TOO_WIDE,
        RecalibrationReason.LOW_CATEGORY_SUPPORT,
        RecalibrationReason.WEAK_MACRO_ONLY_SUPPORT,
        RecalibrationReason.WEAK_CATEGORY_BALANCED_SUPPORT,
        RecalibrationReason.LOW_METHOD_AGREEMENT,
    }
)


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _positive_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _confidence(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return numeric


def _nonblank_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-blank string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-blank string")
    return normalized


def _band(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{name} must be a two-number tuple")
    lower = _positive_real(value[0], f"{name}[0]")
    upper = _positive_real(value[1], f"{name}[1]")
    if lower >= upper:
        raise ValueError(f"{name} lower bound must be less than upper bound")
    return lower, upper


def _quarter_key(effective_date: date) -> str:
    quarter = (effective_date.month - 1) // 3 + 1
    return f"{effective_date.year}Q{quarter}"


def _quarter_end_date(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("effective_date must be a date without time")
    if (value.month, value.day) not in _QUARTER_ENDS:
        raise ValueError("effective_date must be a calendar quarter end")
    return value


@dataclass(frozen=True)
class ManualOverride:
    """Explicit provenance for a governance-approved center override."""

    requested_center: float
    authorized_by: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_center",
            _positive_real(self.requested_center, "requested_center"),
        )
        object.__setattr__(
            self,
            "authorized_by",
            _nonblank_text(self.authorized_by, "authorized_by"),
        )
        object.__setattr__(self, "reason", _nonblank_text(self.reason, "reason"))


@dataclass(frozen=True)
class CycleModelVersion:
    """Immutable official record of one quarterly recalibration decision."""

    cycle_id: str
    effective_date: date
    old_center: float
    new_center: float
    old_band: tuple[float, float]
    new_band: tuple[float, float]
    old_confidence: float
    new_confidence: float
    candidate_center: float
    status: RecalibrationStatus
    reason_code: RecalibrationReason
    rejection_reason: RecalibrationReason | None
    reason_codes: tuple[RecalibrationReason, ...]
    evidence_metrics: Mapping[str, float | int]
    manual_override: ManualOverride | None = None
    previous_version_id: str | None = None
    effective_quarter: str = field(init=False)
    version_id: str = field(init=False)

    def __post_init__(self) -> None:
        cycle_id = _nonblank_text(self.cycle_id, "cycle_id")
        if cycle_id not in _CYCLE_IDS:
            raise ValueError("cycle_id must be one of C1 through C7")
        effective_date = _quarter_end_date(self.effective_date)

        old_center = _positive_real(self.old_center, "old_center")
        new_center = _positive_real(self.new_center, "new_center")
        candidate_center = _positive_real(self.candidate_center, "candidate_center")
        old_band = _band(self.old_band, "old_band")
        new_band = _band(self.new_band, "new_band")
        if not old_band[0] <= old_center <= old_band[1]:
            raise ValueError("old_center must fall inside old_band")
        if not new_band[0] <= new_center <= new_band[1]:
            raise ValueError("new_center must fall inside new_band")

        old_confidence = _confidence(self.old_confidence, "old_confidence")
        new_confidence = _confidence(self.new_confidence, "new_confidence")
        if not isinstance(self.status, RecalibrationStatus):
            raise TypeError("status must be a RecalibrationStatus")
        if not isinstance(self.reason_code, RecalibrationReason):
            raise TypeError("reason_code must be a RecalibrationReason")
        if self.rejection_reason is not None and not isinstance(
            self.rejection_reason,
            RecalibrationReason,
        ):
            raise TypeError("rejection_reason must be a RecalibrationReason or None")

        if not isinstance(self.reason_codes, tuple) or not self.reason_codes:
            raise TypeError("reason_codes must be a non-empty tuple")
        if any(
            not isinstance(reason, RecalibrationReason)
            for reason in self.reason_codes
        ):
            raise TypeError("reason_codes must contain RecalibrationReason values")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes cannot contain duplicates")
        if self.reason_codes[0] is not self.reason_code:
            raise ValueError("reason_codes[0] must equal reason_code")

        if not isinstance(self.evidence_metrics, Mapping):
            raise TypeError("evidence_metrics must be a mapping")
        normalized_metrics: dict[str, float | int] = {}
        for key, value in self.evidence_metrics.items():
            normalized_key = _nonblank_text(key, "evidence metric name")
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value,
                (Real, Integral, np.integer, np.floating),
            ):
                raise TypeError(
                    f"evidence metric {normalized_key} must be a finite number"
                )
            numeric = float(value)
            if not np.isfinite(numeric):
                raise ValueError(
                    f"evidence metric {normalized_key} must be a finite number"
                )
            if isinstance(value, (Integral, np.integer)):
                normalized_metrics[normalized_key] = int(value)
            else:
                normalized_metrics[normalized_key] = numeric

        if self.manual_override is not None and not isinstance(
            self.manual_override,
            ManualOverride,
        ):
            raise TypeError("manual_override must be a ManualOverride or None")
        previous_version_id = self.previous_version_id
        if previous_version_id is not None:
            previous_version_id = _nonblank_text(
                previous_version_id,
                "previous_version_id",
            )

        if self.status is RecalibrationStatus.REJECTED:
            if self.rejection_reason is None:
                raise ValueError("rejected versions require rejection_reason")
            if self.reason_code is not self.rejection_reason:
                raise ValueError("reason_code must equal rejection_reason when rejected")
            if self.reason_code not in _EVIDENCE_FAILURE_REASONS:
                raise ValueError(
                    "rejected primary reason must be an evidence-failure reason"
                )
            allowed_rejected_reasons = {
                *_EVIDENCE_FAILURE_REASONS,
                RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED,
            }
            if any(
                reason not in allowed_rejected_reasons
                for reason in self.reason_codes
            ):
                raise ValueError(
                    "rejected reason_codes may contain only evidence failures and "
                    "manual_override_not_applied"
                )
            if new_center != old_center or new_band != old_band:
                raise ValueError("rejected versions must retain the old center and band")
            if new_confidence > old_confidence:
                raise ValueError("rejected versions cannot increase confidence")
            if self.manual_override is not None:
                if (
                    RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED
                    not in self.reason_codes
                ):
                    raise ValueError(
                        "rejected override requests require manual_override_not_applied"
                    )
                if RecalibrationReason.MANUAL_OVERRIDE in self.reason_codes:
                    raise ValueError(
                        "rejected override requests cannot use manual_override reason"
                    )
            elif (
                RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED
                in self.reason_codes
            ):
                raise ValueError(
                    "manual_override_not_applied requires override provenance"
                )
        else:
            if self.rejection_reason is not None:
                raise ValueError("accepted versions cannot define rejection_reason")
            if self.reason_code not in _ACCEPTED_REASONS:
                raise ValueError(
                    "accepted primary reason must be an accepted-family reason"
                )
            if self.reason_codes != (self.reason_code,):
                raise ValueError(
                    "accepted reason_codes must equal the primary reason exactly"
                )
            if self.manual_override is not None:
                if self.reason_code is not RecalibrationReason.MANUAL_OVERRIDE:
                    raise ValueError(
                        "manual override versions require manual_override reason"
                    )
                if new_center != self.manual_override.requested_center:
                    raise ValueError(
                        "manual override requested_center must equal new_center"
                    )
            elif self.reason_code is RecalibrationReason.MANUAL_OVERRIDE:
                raise ValueError("manual_override reason requires override provenance")
            if (
                RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED
                in self.reason_codes
            ):
                raise ValueError(
                    "accepted versions cannot use manual_override_not_applied"
                )

        effective_quarter = _quarter_key(effective_date)
        object.__setattr__(self, "cycle_id", cycle_id)
        object.__setattr__(self, "effective_date", effective_date)
        object.__setattr__(self, "old_center", old_center)
        object.__setattr__(self, "new_center", new_center)
        object.__setattr__(self, "candidate_center", candidate_center)
        object.__setattr__(self, "old_band", old_band)
        object.__setattr__(self, "new_band", new_band)
        object.__setattr__(self, "old_confidence", old_confidence)
        object.__setattr__(self, "new_confidence", new_confidence)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(
            self,
            "evidence_metrics",
            MappingProxyType(dict(sorted(normalized_metrics.items()))),
        )
        object.__setattr__(self, "previous_version_id", previous_version_id)
        object.__setattr__(self, "effective_quarter", effective_quarter)
        object.__setattr__(self, "version_id", self._deterministic_version_id())

    def _deterministic_version_id(self) -> str:
        override_payload = None
        if self.manual_override is not None:
            override_payload = {
                "requested_center": self.manual_override.requested_center,
                "authorized_by": self.manual_override.authorized_by,
                "reason": self.manual_override.reason,
            }
        payload = {
            "cycle_id": self.cycle_id,
            "effective_date": self.effective_date.isoformat(),
            "old_center": self.old_center,
            "new_center": self.new_center,
            "old_band": self.old_band,
            "new_band": self.new_band,
            "old_confidence": self.old_confidence,
            "new_confidence": self.new_confidence,
            "candidate_center": self.candidate_center,
            "status": self.status.value,
            "reason_code": self.reason_code.value,
            "rejection_reason": (
                None
                if self.rejection_reason is None
                else self.rejection_reason.value
            ),
            "reason_codes": [reason.value for reason in self.reason_codes],
            "evidence_metrics": dict(self.evidence_metrics),
            "manual_override": override_payload,
            "previous_version_id": self.previous_version_id,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        digest = sha256(encoded).hexdigest()[:16]
        return f"{self.cycle_id}-{self.effective_quarter}-{digest}"


__all__ = [
    "CycleModelVersion",
    "ManualOverride",
    "RecalibrationReason",
    "RecalibrationStatus",
]
