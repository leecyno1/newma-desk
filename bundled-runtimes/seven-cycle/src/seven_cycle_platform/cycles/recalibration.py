"""Quarterly evidence gates and bounded official-period recalibration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from numbers import Real

import numpy as np

from seven_cycle_platform.cycles.discovery import DiscoveryEvidence
from seven_cycle_platform.cycles.model_version import (
    CycleModelVersion,
    ManualOverride,
    RecalibrationReason,
    RecalibrationStatus,
)
from seven_cycle_platform.registry.models import CycleSpec


_QUARTER_ENDS = frozenset({(3, 31), (6, 30), (9, 30), (12, 31)})


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


def _unit_interval(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return numeric


def _band(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{name} must be a two-number tuple")
    lower = _positive_real(value[0], f"{name}[0]")
    upper = _positive_real(value[1], f"{name}[1]")
    if lower >= upper:
        raise ValueError(f"{name} lower bound must be less than upper bound")
    return lower, upper


@dataclass(frozen=True)
class RecalibrationPolicy:
    """Evidence thresholds and confidence changes for automatic decisions."""

    min_red_noise_score: float = 0.0
    max_bootstrap_width_fraction: float = 0.50
    min_category_support: float = 0.50
    min_macro_only_score: float = 0.0
    min_category_balanced_score: float = 0.0
    min_method_agreement: float = 2.0 / 3.0
    acceptance_confidence_gain: float = 0.05
    rejection_confidence_penalty: float = 0.15

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_red_noise_score",
            _finite_real(self.min_red_noise_score, "min_red_noise_score"),
        )
        width_fraction = _finite_real(
            self.max_bootstrap_width_fraction,
            "max_bootstrap_width_fraction",
        )
        if not 0.0 < width_fraction <= 1.0:
            raise ValueError(
                "max_bootstrap_width_fraction must be greater than 0 and at most 1"
            )
        object.__setattr__(
            self,
            "max_bootstrap_width_fraction",
            width_fraction,
        )
        for field_name in (
            "min_category_support",
            "min_method_agreement",
            "acceptance_confidence_gain",
            "rejection_confidence_penalty",
        ):
            object.__setattr__(
                self,
                field_name,
                _unit_interval(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "min_macro_only_score",
            _finite_real(self.min_macro_only_score, "min_macro_only_score"),
        )
        object.__setattr__(
            self,
            "min_category_balanced_score",
            _finite_real(
                self.min_category_balanced_score,
                "min_category_balanced_score",
            ),
        )


DEFAULT_RECALIBRATION_POLICY = RecalibrationPolicy()


def _evidence_failures(
    cycle_spec: CycleSpec,
    evidence: DiscoveryEvidence,
    policy: RecalibrationPolicy,
) -> tuple[RecalibrationReason, ...]:
    failures: list[RecalibrationReason] = []
    if not cycle_spec.search_min <= evidence.candidate_center <= cycle_spec.search_max:
        failures.append(RecalibrationReason.CANDIDATE_OUTSIDE_SEARCH_BAND)
    if evidence.red_noise_score <= policy.min_red_noise_score:
        failures.append(RecalibrationReason.LOW_RED_NOISE_SCORE)
    governed_width = cycle_spec.search_max - cycle_spec.search_min
    bootstrap_width = (
        evidence.bootstrap_period_high - evidence.bootstrap_period_low
    )
    if bootstrap_width / governed_width > policy.max_bootstrap_width_fraction:
        failures.append(RecalibrationReason.BOOTSTRAP_INTERVAL_TOO_WIDE)
    if evidence.category_support < policy.min_category_support:
        failures.append(RecalibrationReason.LOW_CATEGORY_SUPPORT)
    if evidence.macro_only_score <= policy.min_macro_only_score:
        failures.append(RecalibrationReason.WEAK_MACRO_ONLY_SUPPORT)
    if evidence.category_balanced_score <= policy.min_category_balanced_score:
        failures.append(RecalibrationReason.WEAK_CATEGORY_BALANCED_SUPPORT)
    if evidence.method_agreement < policy.min_method_agreement:
        failures.append(RecalibrationReason.LOW_METHOD_AGREEMENT)
    return tuple(failures)


def _evidence_metrics(
    evidence: DiscoveryEvidence,
    cycle_spec: CycleSpec,
) -> dict[str, float | int]:
    metrics = dict(evidence.metrics())
    metrics.update(
        {
            "governed_search_min": cycle_spec.search_min,
            "governed_search_max": cycle_spec.search_max,
            "max_quarterly_drift": cycle_spec.max_quarterly_drift,
        }
    )
    return metrics


def recalibrate_cycle(
    cycle_spec: CycleSpec,
    evidence: DiscoveryEvidence,
    *,
    old_center: float,
    old_band: tuple[float, float],
    old_confidence: float,
    effective_date: date,
    manual_override: ManualOverride | None = None,
    previous_version_id: str | None = None,
    policy: RecalibrationPolicy = DEFAULT_RECALIBRATION_POLICY,
) -> CycleModelVersion:
    """Create one immutable quarterly decision with bounded automatic drift."""

    if not isinstance(cycle_spec, CycleSpec):
        raise TypeError("cycle_spec must be a CycleSpec")
    if not isinstance(evidence, DiscoveryEvidence):
        raise TypeError("evidence must be DiscoveryEvidence")
    if not isinstance(policy, RecalibrationPolicy):
        raise TypeError("policy must be a RecalibrationPolicy")
    if manual_override is not None and not isinstance(
        manual_override,
        ManualOverride,
    ):
        raise TypeError("manual_override must be a ManualOverride or None")
    if not isinstance(effective_date, date) or isinstance(effective_date, datetime):
        raise TypeError("effective_date must be a date without time")
    if (effective_date.month, effective_date.day) not in _QUARTER_ENDS:
        raise ValueError("effective_date must be a calendar quarter end")
    if previous_version_id is not None:
        if not isinstance(previous_version_id, str):
            raise TypeError("previous_version_id must be a non-blank string or None")
        if not previous_version_id.strip():
            raise ValueError("previous_version_id must be a non-blank string or None")
        previous_version_id = previous_version_id.strip()

    official_center = _positive_real(old_center, "old_center")
    official_band = _band(old_band, "old_band")
    confidence = _unit_interval(old_confidence, "old_confidence")
    if not cycle_spec.search_min <= official_center <= cycle_spec.search_max:
        raise ValueError("old_center must fall inside the governed search band")
    if not official_band[0] <= official_center <= official_band[1]:
        raise ValueError("old_center must fall inside old_band")
    if (
        official_band[0] < cycle_spec.search_min
        or official_band[1] > cycle_spec.search_max
    ):
        raise ValueError("old_band must fall inside the governed search band")

    evidence_metrics = _evidence_metrics(evidence, cycle_spec)
    failures = _evidence_failures(cycle_spec, evidence, policy)
    if failures:
        reduced_confidence = max(
            0.0,
            confidence - policy.rejection_confidence_penalty,
        )
        evidence_metrics["applied_quarterly_drift"] = 0.0
        reason_codes = failures
        if manual_override is not None:
            evidence_metrics["manual_override_requested_center"] = (
                manual_override.requested_center
            )
            reason_codes = (
                *failures,
                RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED,
            )
        return CycleModelVersion(
            cycle_id=cycle_spec.cycle_id,
            effective_date=effective_date,
            old_center=official_center,
            new_center=official_center,
            old_band=official_band,
            new_band=official_band,
            old_confidence=confidence,
            new_confidence=reduced_confidence,
            candidate_center=evidence.candidate_center,
            status=RecalibrationStatus.REJECTED,
            reason_code=failures[0],
            rejection_reason=failures[0],
            reason_codes=reason_codes,
            evidence_metrics=evidence_metrics,
            manual_override=manual_override,
            previous_version_id=previous_version_id,
        )

    if manual_override is not None:
        requested_center = manual_override.requested_center
        if not cycle_spec.search_min <= requested_center <= cycle_spec.search_max:
            raise ValueError(
                "manual override requested_center must remain inside the governed "
                "search band"
            )
        new_band = (
            min(official_band[0], requested_center),
            max(official_band[1], requested_center),
        )
        evidence_metrics["applied_quarterly_drift"] = abs(
            requested_center - official_center
        )
        evidence_metrics["manual_override_requested_center"] = requested_center
        return CycleModelVersion(
            cycle_id=cycle_spec.cycle_id,
            effective_date=effective_date,
            old_center=official_center,
            new_center=requested_center,
            old_band=official_band,
            new_band=new_band,
            old_confidence=confidence,
            new_confidence=confidence,
            candidate_center=evidence.candidate_center,
            status=RecalibrationStatus.ACCEPTED,
            reason_code=RecalibrationReason.MANUAL_OVERRIDE,
            rejection_reason=None,
            reason_codes=(RecalibrationReason.MANUAL_OVERRIDE,),
            evidence_metrics=evidence_metrics,
            manual_override=manual_override,
            previous_version_id=previous_version_id,
        )

    candidate_delta = evidence.candidate_center - official_center
    bounded_delta = float(
        np.clip(
            candidate_delta,
            -cycle_spec.max_quarterly_drift,
            cycle_spec.max_quarterly_drift,
        )
    )
    new_center = official_center + bounded_delta
    interval_low = max(cycle_spec.search_min, evidence.bootstrap_period_low)
    interval_high = min(cycle_spec.search_max, evidence.bootstrap_period_high)
    new_band = (
        min(interval_low, new_center),
        max(interval_high, new_center),
    )
    if new_band[0] >= new_band[1]:
        new_band = (
            min(official_band[0], new_center),
            max(official_band[1], new_center),
        )
    drift_limited = not np.isclose(candidate_delta, bounded_delta, atol=0.0, rtol=0.0)
    reason = (
        RecalibrationReason.ACCEPTED_DRIFT_LIMITED
        if drift_limited
        else RecalibrationReason.ACCEPTED
    )
    evidence_metrics["applied_quarterly_drift"] = abs(bounded_delta)
    evidence_metrics["unbounded_candidate_drift"] = abs(candidate_delta)
    increased_confidence = min(
        1.0,
        confidence + policy.acceptance_confidence_gain,
    )
    return CycleModelVersion(
        cycle_id=cycle_spec.cycle_id,
        effective_date=effective_date,
        old_center=official_center,
        new_center=new_center,
        old_band=official_band,
        new_band=new_band,
        old_confidence=confidence,
        new_confidence=increased_confidence,
        candidate_center=evidence.candidate_center,
        status=RecalibrationStatus.ACCEPTED,
        reason_code=reason,
        rejection_reason=None,
        reason_codes=(reason,),
        evidence_metrics=evidence_metrics,
        manual_override=None,
        previous_version_id=previous_version_id,
    )


__all__ = [
    "DEFAULT_RECALIBRATION_POLICY",
    "RecalibrationPolicy",
    "recalibrate_cycle",
]
