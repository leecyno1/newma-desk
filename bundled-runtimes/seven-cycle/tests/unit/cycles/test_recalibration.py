from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime
from importlib import import_module
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.registry.models import CycleSpec


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_API = (
    "CategorySupport",
    "CycleModelVersion",
    "DiscoveryEvidence",
    "ManualOverride",
    "MethodAgreement",
    "RecalibrationPolicy",
    "RecalibrationReason",
    "RecalibrationStatus",
    "bootstrap_interval",
    "bootstrap_period_interval",
    "build_views",
    "category_support",
    "evaluate_period_candidate",
    "method_agreement",
    "recalibrate_cycle",
    "red_noise_log_excess",
)


def _api() -> ModuleType:
    module = import_module("seven_cycle_platform.cycles")
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(f"Task 9 public API is missing: {', '.join(missing)}")
    return module


@pytest.fixture()
def cycle_spec() -> CycleSpec:
    return CycleSpec(
        cycle_id="C5",
        name_zh="信用/流动性周期",
        economic_role="Test governed credit cycle.",
        frequency="M",
        search_min=15.0,
        search_max=30.0,
        initial_center=21.0,
        center_prior_months=21.0,
        period_mode="months",
        empirical_band_months=None,
        publication={
            "historical": "blocked",
            "realtime": "blocked",
            "forecast": "blocked",
            "asset_statistics": "blocked",
            "reason": "Synthetic recalibration fixture is not publishable.",
        },
        max_quarterly_drift=2.0,
        horizons=[1, 3, 6],
        default_usage="formal",
    )


@pytest.fixture()
def strong_evidence() -> object:
    api = _api()
    return api.DiscoveryEvidence(
        candidate_center=23.0,
        bootstrap_period_low=22.0,
        bootstrap_period_high=24.0,
        red_noise_score=1.25,
        category_support=0.75,
        macro_only_score=0.90,
        category_balanced_score=1.10,
        method_agreement=1.0,
        method_peak_periods={
            "canonical": 23.0,
            "canonical_hp": 23.0,
            "canonical_linear": 23.0,
        },
        supporting_categories=("credit", "growth", "prices"),
        total_categories=4,
        series_count=12,
        random_seed=20260712,
    )


@pytest.fixture()
def weak_evidence() -> object:
    api = _api()
    return api.DiscoveryEvidence(
        candidate_center=24.0,
        bootstrap_period_low=19.0,
        bootstrap_period_high=29.0,
        red_noise_score=-0.20,
        category_support=0.25,
        macro_only_score=-0.10,
        category_balanced_score=0.05,
        method_agreement=1.0 / 3.0,
        method_peak_periods={
            "canonical": 18.0,
            "canonical_hp": 24.0,
            "canonical_linear": 29.0,
        },
        supporting_categories=("credit",),
        total_categories=4,
        series_count=12,
        random_seed=20260712,
    )


def _score_fixture() -> tuple[
    np.ndarray,
    dict[str, np.ndarray],
    np.ndarray,
    np.ndarray,
]:
    periods = np.arange(18.0, 27.0, 1.0)
    categories = np.asarray(
        ["growth", "growth", "credit", "credit", "prices", "equity"],
        dtype=object,
    )
    macro_mask = categories != "equity"
    matrices: dict[str, np.ndarray] = {}
    method_shifts = {
        "canonical": -0.15,
        "canonical_hp": 0.0,
        "canonical_linear": 0.20,
    }
    row_offsets = np.asarray([0.20, 0.05, 0.15, 0.00, 0.10, -0.05])
    for method, shift in method_shifts.items():
        center = 22.0 + shift
        base = 1.40 - 0.28 * (periods - center) ** 2
        matrices[method] = np.vstack(
            [base + offset for offset in row_offsets]
        ).astype("float64")
    return periods, matrices, categories, macro_mask


def _far_strong_evidence() -> object:
    api = _api()
    return api.DiscoveryEvidence(
        candidate_center=28.0,
        bootstrap_period_low=27.0,
        bootstrap_period_high=29.0,
        red_noise_score=1.50,
        category_support=1.0,
        macro_only_score=1.20,
        category_balanced_score=1.30,
        method_agreement=1.0,
        method_peak_periods={"a": 28.0, "b": 28.0, "c": 28.0},
        supporting_categories=("credit", "growth", "prices"),
        total_categories=3,
        series_count=9,
        random_seed=20260712,
    )


def _out_of_band_evidence() -> object:
    api = _api()
    return api.DiscoveryEvidence(
        candidate_center=31.0,
        bootstrap_period_low=29.0,
        bootstrap_period_high=33.0,
        red_noise_score=2.0,
        category_support=1.0,
        macro_only_score=1.0,
        category_balanced_score=1.0,
        method_agreement=1.0,
        method_peak_periods={"a": 31.0, "b": 31.0},
        supporting_categories=("credit", "growth"),
        total_categories=2,
        series_count=6,
        random_seed=9,
    )


def _model_version_payload(version: object) -> dict[str, object]:
    return {
        field.name: getattr(version, field.name)
        for field in fields(type(version))
        if field.init
    }


def _governed_model_versions(
    api: ModuleType,
    cycle_spec: CycleSpec,
    strong_evidence: object,
    weak_evidence: object,
) -> dict[str, object]:
    common = {
        "old_center": 21.0,
        "old_band": (18.0, 24.0),
        "old_confidence": 0.70,
        "effective_date": date(2026, 6, 30),
    }
    rejected_override = api.ManualOverride(
        requested_center=28.0,
        authorized_by="model_governance_committee",
        reason="Audit-only rejected override request.",
    )
    return {
        "accepted": api.recalibrate_cycle(
            cycle_spec,
            strong_evidence,
            **common,
        ),
        "rejected": api.recalibrate_cycle(
            cycle_spec,
            weak_evidence,
            **common,
        ),
        "rejected_override": api.recalibrate_cycle(
            cycle_spec,
            weak_evidence,
            manual_override=rejected_override,
            **common,
        ),
    }


def test_ar1_red_noise_score_identifies_embedded_period() -> None:
    api = _api()
    generator = np.random.default_rng(20260712)
    count = 512
    noise = np.empty(count, dtype="float64")
    noise[0] = generator.normal()
    for position in range(1, count):
        noise[position] = 0.72 * noise[position - 1] + generator.normal(scale=0.55)
    positions = np.arange(count, dtype="float64")
    values = pd.Series(
        2.40 * np.sin(2.0 * np.pi * positions / 24.0) + noise,
        name="synthetic_cycle",
    )
    periods = np.arange(12.0, 61.0, 1.0)

    scores = api.red_noise_log_excess(values, periods)

    peak_period = float(periods[int(np.nanargmax(scores))])
    period_24_score = float(scores[np.flatnonzero(periods == 24.0)[0]])
    period_12_score = float(scores[np.flatnonzero(periods == 12.0)[0]])
    assert 22.0 <= peak_period <= 25.0
    assert period_24_score > 0.0
    assert period_24_score > period_12_score
    assert scores.shape == periods.shape
    assert not scores.flags.writeable


def test_bootstrap_score_interval_is_deterministic_and_read_only() -> None:
    api = _api()
    matrix = np.asarray(
        [
            [0.0, 0.8, 1.6, 0.4],
            [0.1, 1.0, 1.8, 0.3],
            [-0.1, 0.9, 1.7, 0.5],
            [0.2, 1.1, 1.9, 0.2],
            [0.0, 0.7, 1.5, 0.6],
        ],
        dtype="float64",
    )
    before = matrix.copy()

    first_lower, first_upper = api.bootstrap_interval(
        matrix,
        random_seed=17,
        draws=250,
    )
    second_lower, second_upper = api.bootstrap_interval(
        matrix,
        random_seed=17,
        draws=250,
    )

    np.testing.assert_array_equal(first_lower, second_lower)
    np.testing.assert_array_equal(first_upper, second_upper)
    assert bool((first_lower <= first_upper).all())
    assert not first_lower.flags.writeable
    assert not first_upper.flags.writeable
    np.testing.assert_array_equal(matrix, before)


def test_bootstrap_period_interval_is_deterministic_for_fixed_seed() -> None:
    api = _api()
    periods = np.arange(18.0, 25.0, 1.0)
    row_peaks = (20.0, 20.0, 21.0, 21.0, 22.0, 22.0)
    matrix = np.vstack(
        [1.0 - 0.35 * (periods - peak) ** 2 for peak in row_peaks]
    )

    first = api.bootstrap_period_interval(
        matrix,
        periods,
        random_seed=101,
        draws=300,
    )
    second = api.bootstrap_period_interval(
        matrix,
        periods,
        random_seed=101,
        draws=300,
    )

    assert first == second
    assert first[0] <= 21.0 <= first[1]
    assert periods.min() <= first[0] <= first[1] <= periods.max()


def test_category_support_reports_labels_scores_and_ratio() -> None:
    api = _api()
    matrix = np.asarray(
        [
            [-0.2, 1.0, -0.1],
            [-0.1, 1.4, 0.0],
            [-0.4, 0.3, -0.2],
            [-0.3, 0.1, -0.1],
            [0.0, -0.6, 0.1],
            [0.1, -0.4, 0.2],
        ],
        dtype="float64",
    )
    categories = np.asarray(
        ["growth", "growth", "credit", "credit", "prices", "prices"],
        dtype=object,
    )

    result = api.category_support(matrix, categories, period_index=1)

    assert isinstance(result, api.CategorySupport)
    assert result.supported_categories == ("credit", "growth")
    assert result.total_categories == 3
    assert result.support_ratio == pytest.approx(2.0 / 3.0)
    assert result.category_scores["growth"] == pytest.approx(1.2)
    with pytest.raises(TypeError):
        result.category_scores["growth"] = 99.0


def test_method_agreement_identifies_consensus_and_outlier() -> None:
    api = _api()
    method_periods = {
        "canonical": 20.0,
        "canonical_hp": 20.5,
        "canonical_linear": 21.0,
        "wavelet": 30.0,
    }

    result = api.method_agreement(method_periods, tolerance=1.0)

    assert isinstance(result, api.MethodAgreement)
    assert result.center == pytest.approx(20.75)
    assert result.supporting_methods == (
        "canonical",
        "canonical_hp",
        "canonical_linear",
    )
    assert result.outlier_methods == ("wavelet",)
    assert result.agreement_ratio == pytest.approx(0.75)
    method_periods["canonical"] = 99.0
    assert result.method_periods["canonical"] == 20.0


def test_candidate_evaluation_combines_all_approved_evidence_views() -> None:
    api = _api()
    periods, matrices, categories, macro_mask = _score_fixture()
    before = {method: matrix.copy() for method, matrix in matrices.items()}

    evidence = api.evaluate_period_candidate(
        periods=periods,
        method_score_matrices=matrices,
        categories=categories,
        macro_mask=macro_mask,
        random_seed=303,
        bootstrap_draws=240,
    )

    assert isinstance(evidence, api.DiscoveryEvidence)
    assert evidence.candidate_center == pytest.approx(22.0)
    assert evidence.bootstrap_period_low <= evidence.candidate_center
    assert evidence.bootstrap_period_high >= evidence.candidate_center
    assert evidence.red_noise_score > 0.0
    assert evidence.category_support == 1.0
    assert evidence.macro_only_score > 0.0
    assert evidence.category_balanced_score > 0.0
    assert evidence.method_agreement == 1.0
    assert evidence.random_seed == 303
    assert evidence.series_count == len(categories)
    for method, matrix in matrices.items():
        np.testing.assert_array_equal(matrix, before[method])


def test_fixed_seed_and_inputs_produce_identical_quarterly_evidence() -> None:
    api = _api()
    periods, matrices, categories, macro_mask = _score_fixture()
    arguments = {
        "periods": periods,
        "method_score_matrices": matrices,
        "categories": categories,
        "macro_mask": macro_mask,
        "random_seed": 404,
        "bootstrap_draws": 180,
    }

    first = api.evaluate_period_candidate(**arguments)
    second = api.evaluate_period_candidate(**arguments)

    assert first == second
    assert dict(first.method_peak_periods) == dict(second.method_peak_periods)


def test_point_bootstrap_interval_retains_a_valid_official_band(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()
    periods, matrices, categories, macro_mask = _score_fixture()
    evidence = api.evaluate_period_candidate(
        periods=periods,
        method_score_matrices=matrices,
        categories=categories,
        macro_mask=macro_mask,
        random_seed=505,
        bootstrap_draws=180,
    )
    assert evidence.bootstrap_period_low == evidence.bootstrap_period_high

    version = api.recalibrate_cycle(
        cycle_spec,
        evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 6, 30),
    )

    assert version.status is api.RecalibrationStatus.ACCEPTED
    assert version.new_band[0] < version.new_band[1]
    assert version.new_band[0] <= version.new_center <= version.new_band[1]


def test_strong_candidate_inside_search_band_is_accepted(
    cycle_spec: CycleSpec,
    strong_evidence: object,
) -> None:
    api = _api()

    version = api.recalibrate_cycle(
        cycle_spec,
        strong_evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 6, 30),
    )

    assert isinstance(version, api.CycleModelVersion)
    assert version.status is api.RecalibrationStatus.ACCEPTED
    assert version.reason_code is api.RecalibrationReason.ACCEPTED
    assert version.rejection_reason is None
    assert version.old_center == 21.0
    assert version.new_center == 23.0
    assert version.old_band == (18.0, 24.0)
    assert version.new_band == (22.0, 24.0)
    assert version.new_confidence > version.old_confidence
    assert version.effective_quarter == "2026Q2"
    assert version.version_id.startswith("C5-2026Q2-")
    assert version.evidence_metrics["red_noise_score"] == 1.25
    assert version.manual_override is None


def test_weak_candidate_retains_official_identity_and_lowers_confidence(
    cycle_spec: CycleSpec,
    weak_evidence: object,
) -> None:
    api = _api()

    version = api.recalibrate_cycle(
        cycle_spec,
        weak_evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 6, 30),
    )

    assert version.status is api.RecalibrationStatus.REJECTED
    assert version.reason_code is api.RecalibrationReason.LOW_RED_NOISE_SCORE
    assert version.rejection_reason is api.RecalibrationReason.LOW_RED_NOISE_SCORE
    assert api.RecalibrationReason.LOW_CATEGORY_SUPPORT in version.reason_codes
    assert api.RecalibrationReason.LOW_METHOD_AGREEMENT in version.reason_codes
    assert version.new_center == version.old_center == 21.0
    assert version.new_band == version.old_band == (18.0, 24.0)
    assert version.new_confidence < version.old_confidence
    assert version.manual_override is None


def test_automatic_recalibration_caps_quarterly_drift(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()

    version = api.recalibrate_cycle(
        cycle_spec,
        _far_strong_evidence(),
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 9, 30),
    )

    assert version.status is api.RecalibrationStatus.ACCEPTED
    assert version.reason_code is api.RecalibrationReason.ACCEPTED_DRIFT_LIMITED
    assert abs(version.new_center - version.old_center) <= cycle_spec.max_quarterly_drift
    assert version.new_center == 23.0
    assert version.manual_override is None


def test_explicit_manual_override_may_exceed_drift_inside_search_band(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()
    override = api.ManualOverride(
        requested_center=28.0,
        authorized_by="model_governance_committee",
        reason="Approved structural-break review.",
    )

    version = api.recalibrate_cycle(
        cycle_spec,
        _far_strong_evidence(),
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 9, 30),
        manual_override=override,
    )

    assert version.status is api.RecalibrationStatus.ACCEPTED
    assert version.reason_code is api.RecalibrationReason.MANUAL_OVERRIDE
    assert version.rejection_reason is None
    assert version.new_center == 28.0
    assert abs(version.new_center - version.old_center) > cycle_spec.max_quarterly_drift
    assert cycle_spec.search_min <= version.new_center <= cycle_spec.search_max
    assert version.new_band[0] <= version.new_center <= version.new_band[1]
    assert version.manual_override == override
    assert version.manual_override.authorized_by == "model_governance_committee"


def test_weak_evidence_rejects_override_and_preserves_request_provenance(
    cycle_spec: CycleSpec,
    weak_evidence: object,
) -> None:
    api = _api()
    override = api.ManualOverride(
        requested_center=28.0,
        authorized_by="model_governance_committee",
        reason="Requested drift exception despite weak evidence.",
    )

    version = api.recalibrate_cycle(
        cycle_spec,
        weak_evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 9, 30),
        manual_override=override,
    )

    assert version.status is api.RecalibrationStatus.REJECTED
    assert version.reason_code is api.RecalibrationReason.LOW_RED_NOISE_SCORE
    assert version.new_center == version.old_center == 21.0
    assert version.new_band == version.old_band == (18.0, 24.0)
    assert version.new_confidence < version.old_confidence
    assert version.manual_override == override
    assert "manual_override_not_applied" in {
        reason.value for reason in version.reason_codes
    }


def test_out_of_band_candidate_rejects_override_and_preserves_request_provenance(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()
    override = api.ManualOverride(
        requested_center=28.0,
        authorized_by="model_governance_committee",
        reason="Requested drift exception for an invalid candidate.",
    )

    version = api.recalibrate_cycle(
        cycle_spec,
        _out_of_band_evidence(),
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 12, 31),
        manual_override=override,
    )

    assert version.status is api.RecalibrationStatus.REJECTED
    assert version.reason_code is api.RecalibrationReason.CANDIDATE_OUTSIDE_SEARCH_BAND
    assert version.new_center == version.old_center == 21.0
    assert version.new_band == version.old_band == (18.0, 24.0)
    assert version.new_confidence < version.old_confidence
    assert version.manual_override == override
    assert "manual_override_not_applied" in {
        reason.value for reason in version.reason_codes
    }


def test_manual_override_outside_governed_search_band_is_rejected(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()
    override = api.ManualOverride(
        requested_center=31.0,
        authorized_by="model_governance_committee",
        reason="Invalid test request.",
    )

    with pytest.raises(ValueError, match="governed search band"):
        api.recalibrate_cycle(
            cycle_spec,
            _far_strong_evidence(),
            old_center=21.0,
            old_band=(18.0, 24.0),
            old_confidence=0.70,
            effective_date=date(2026, 9, 30),
            manual_override=override,
        )


def test_candidate_outside_search_band_creates_rejected_model_vintage(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()

    version = api.recalibrate_cycle(
        cycle_spec,
        _out_of_band_evidence(),
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 12, 31),
    )

    assert version.status is api.RecalibrationStatus.REJECTED
    assert version.reason_code is api.RecalibrationReason.CANDIDATE_OUTSIDE_SEARCH_BAND
    assert version.new_center == version.old_center
    assert version.new_band == version.old_band


@pytest.mark.parametrize(
    "quarter_end",
    [
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 9, 30),
        date(2026, 12, 31),
    ],
)
def test_calendar_quarter_ends_are_valid_effective_dates(
    cycle_spec: CycleSpec,
    strong_evidence: object,
    quarter_end: date,
) -> None:
    api = _api()

    version = api.recalibrate_cycle(
        cycle_spec,
        strong_evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=quarter_end,
    )
    direct_version = replace(version, effective_date=quarter_end)

    assert version.effective_date == quarter_end
    assert direct_version.effective_date == quarter_end


def test_mid_quarter_effective_date_is_rejected_by_all_construction_paths(
    cycle_spec: CycleSpec,
    strong_evidence: object,
) -> None:
    api = _api()

    with pytest.raises(ValueError, match="quarter end"):
        api.recalibrate_cycle(
            cycle_spec,
            strong_evidence,
            old_center=21.0,
            old_band=(18.0, 24.0),
            old_confidence=0.70,
            effective_date=date(2026, 7, 1),
        )

    valid_version = api.recalibrate_cycle(
        cycle_spec,
        strong_evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 6, 30),
    )
    with pytest.raises(ValueError, match="quarter end"):
        replace(valid_version, effective_date=date(2026, 7, 1))


@pytest.mark.parametrize(
    ("base_kind", "primary", "rejection", "reason_codes"),
    [
        (
            "accepted",
            "LOW_RED_NOISE_SCORE",
            None,
            ("LOW_RED_NOISE_SCORE",),
        ),
        (
            "rejected",
            "ACCEPTED",
            "ACCEPTED",
            ("ACCEPTED",),
        ),
        (
            "rejected_override",
            "MANUAL_OVERRIDE_NOT_APPLIED",
            "MANUAL_OVERRIDE_NOT_APPLIED",
            ("MANUAL_OVERRIDE_NOT_APPLIED",),
        ),
    ],
)
def test_direct_model_version_constructor_rejects_impossible_status_reasons(
    cycle_spec: CycleSpec,
    strong_evidence: object,
    weak_evidence: object,
    base_kind: str,
    primary: str,
    rejection: str | None,
    reason_codes: tuple[str, ...],
) -> None:
    api = _api()
    versions = _governed_model_versions(
        api,
        cycle_spec,
        strong_evidence,
        weak_evidence,
    )
    payload = _model_version_payload(versions[base_kind])
    payload["reason_code"] = getattr(api.RecalibrationReason, primary)
    payload["rejection_reason"] = (
        None if rejection is None else getattr(api.RecalibrationReason, rejection)
    )
    payload["reason_codes"] = tuple(
        getattr(api.RecalibrationReason, name) for name in reason_codes
    )

    with pytest.raises(ValueError, match="reason"):
        api.CycleModelVersion(**payload)


@pytest.mark.parametrize(
    ("base_kind", "reason_codes"),
    [
        ("accepted", ("ACCEPTED_DRIFT_LIMITED", "ACCEPTED")),
        ("accepted", ("ACCEPTED", "ACCEPTED")),
        ("accepted", ("ACCEPTED", "LOW_METHOD_AGREEMENT")),
        ("rejected", ("LOW_CATEGORY_SUPPORT", "LOW_RED_NOISE_SCORE")),
        ("rejected", ("LOW_RED_NOISE_SCORE", "LOW_RED_NOISE_SCORE")),
        ("rejected", ("LOW_RED_NOISE_SCORE", "ACCEPTED")),
    ],
)
def test_dataclasses_replace_rejects_noncanonical_reason_code_sequences(
    cycle_spec: CycleSpec,
    strong_evidence: object,
    weak_evidence: object,
    base_kind: str,
    reason_codes: tuple[str, ...],
) -> None:
    api = _api()
    versions = _governed_model_versions(
        api,
        cycle_spec,
        strong_evidence,
        weak_evidence,
    )
    version = versions[base_kind]
    normalized_codes = tuple(
        getattr(api.RecalibrationReason, name) for name in reason_codes
    )

    with pytest.raises(ValueError, match="reason"):
        replace(version, reason_codes=normalized_codes)


def test_model_version_and_nested_evidence_are_deeply_immutable(
    cycle_spec: CycleSpec,
) -> None:
    api = _api()
    method_peaks = {"canonical": 23.0, "canonical_hp": 23.0}
    evidence = api.DiscoveryEvidence(
        candidate_center=23.0,
        bootstrap_period_low=22.0,
        bootstrap_period_high=24.0,
        red_noise_score=1.0,
        category_support=1.0,
        macro_only_score=1.0,
        category_balanced_score=1.0,
        method_agreement=1.0,
        method_peak_periods=method_peaks,
        supporting_categories=("credit",),
        total_categories=1,
        series_count=4,
        random_seed=11,
    )
    version = api.recalibrate_cycle(
        cycle_spec,
        evidence,
        old_center=21.0,
        old_band=(18.0, 24.0),
        old_confidence=0.70,
        effective_date=date(2026, 6, 30),
    )
    expected_id = version.version_id

    method_peaks["canonical"] = 99.0

    assert evidence.method_peak_periods["canonical"] == 23.0
    assert version.version_id == expected_id
    with pytest.raises(TypeError):
        evidence.method_peak_periods["canonical"] = 99.0
    with pytest.raises(TypeError):
        version.evidence_metrics["red_noise_score"] = 99.0
    with pytest.raises(FrozenInstanceError):
        version.new_center = 99.0


def test_identical_quarterly_decision_inputs_have_deterministic_version_id(
    cycle_spec: CycleSpec,
    strong_evidence: object,
) -> None:
    api = _api()
    arguments = {
        "old_center": 21.0,
        "old_band": (18.0, 24.0),
        "old_confidence": 0.70,
        "effective_date": date(2026, 6, 30),
    }

    first = api.recalibrate_cycle(cycle_spec, strong_evidence, **arguments)
    second = api.recalibrate_cycle(cycle_spec, strong_evidence, **arguments)

    assert first == second
    assert first.version_id == second.version_id


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("random_seed", True),
        ("draws", True),
        ("random_seed", -1),
        ("draws", 0),
    ],
)
def test_bootstrap_rejects_invalid_integer_parameters(
    parameter: str,
    value: object,
) -> None:
    api = _api()
    arguments: dict[str, object] = {
        "matrix": np.ones((3, 4), dtype="float64"),
        "random_seed": 1,
        "draws": 10,
    }
    arguments[parameter] = value

    expected_error = TypeError if isinstance(value, bool) else ValueError
    with pytest.raises(expected_error, match=parameter):
        api.bootstrap_interval(**arguments)


def test_discovery_rejects_malformed_or_unaligned_inputs() -> None:
    api = _api()
    periods = np.asarray([20.0, 21.0, 22.0])

    with pytest.raises(ValueError, match="two-dimensional"):
        api.bootstrap_interval(np.ones(3, dtype="float64"))
    with pytest.raises(TypeError, match="periods"):
        api.red_noise_log_excess(pd.Series(np.arange(80.0)), np.asarray([True, False]))
    with pytest.raises(ValueError, match="align"):
        api.build_views(
            np.ones((2, 3), dtype="float64"),
            np.asarray(["growth"], dtype=object),
            panel_name="monthly_macro",
        )
    with pytest.raises(ValueError, match="blank category"):
        api.build_views(
            np.ones((2, 3), dtype="float64"),
            np.asarray(["growth", "  "], dtype=object),
            panel_name="monthly_macro",
        )
    with pytest.raises(ValueError, match="same shape"):
        api.evaluate_period_candidate(
            periods=periods,
            method_score_matrices={
                "first": np.ones((2, 3), dtype="float64"),
                "second": np.ones((3, 3), dtype="float64"),
            },
            categories=np.asarray(["growth", "credit"], dtype=object),
            macro_mask=np.asarray([True, True]),
        )
    with pytest.raises(ValueError, match="macro_mask.*align"):
        api.evaluate_period_candidate(
            periods=periods,
            method_score_matrices={
                "first": np.ones((2, 3), dtype="float64"),
            },
            categories=np.asarray(["growth", "credit"], dtype=object),
            macro_mask=np.asarray([True]),
        )
    with pytest.raises(ValueError, match="macro_mask.*boolean"):
        api.evaluate_period_candidate(
            periods=periods,
            method_score_matrices={
                "first": np.ones((2, 3), dtype="float64"),
            },
            categories=np.asarray(["growth", "credit"], dtype=object),
            macro_mask=np.asarray([1, 0]),
        )


@pytest.mark.parametrize(
    ("parameter", "value", "error_type"),
    [
        ("old_center", True, TypeError),
        ("old_confidence", True, TypeError),
        ("old_confidence", 1.1, ValueError),
        ("effective_date", datetime(2026, 6, 30), TypeError),
    ],
)
def test_recalibration_rejects_invalid_public_inputs(
    cycle_spec: CycleSpec,
    strong_evidence: object,
    parameter: str,
    value: object,
    error_type: type[Exception],
) -> None:
    api = _api()
    arguments: dict[str, object] = {
        "old_center": 21.0,
        "old_band": (18.0, 24.0),
        "old_confidence": 0.70,
        "effective_date": date(2026, 6, 30),
    }
    arguments[parameter] = value

    with pytest.raises(error_type, match=parameter):
        api.recalibrate_cycle(cycle_spec, strong_evidence, **arguments)


def test_discovery_evidence_rejects_boolean_real_values() -> None:
    api = _api()

    with pytest.raises(TypeError, match="candidate_center"):
        api.DiscoveryEvidence(
            candidate_center=True,
            bootstrap_period_low=22.0,
            bootstrap_period_high=24.0,
            red_noise_score=1.0,
            category_support=1.0,
            macro_only_score=1.0,
            category_balanced_score=1.0,
            method_agreement=1.0,
            method_peak_periods={"a": 23.0},
            supporting_categories=("credit",),
            total_categories=1,
            series_count=3,
            random_seed=1,
        )


def test_legacy_discovery_modules_are_checkout_safe_thin_wrappers() -> None:
    scripts_directory = PROJECT_ROOT / "scripts"
    source_directory = PROJECT_ROOT / "src"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    code = f"""
import importlib.abc
from pathlib import Path
import sys

source_directory = {str(source_directory)!r}
source_path = Path(source_directory).resolve()
sys.path[:] = [
    entry
    for entry in sys.path
    if Path(entry or '.').resolve() != source_path
]

class RequireRepoSource(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'seven_cycle_platform' and source_directory not in sys.path:
            raise ModuleNotFoundError('repo src was not bootstrapped')
        return None

sys.meta_path.insert(0, RequireRepoSource())
sys.path.insert(0, {str(scripts_directory)!r})
import cycle_robustness_core
import discover_cycle_periods_robust

assert cycle_robustness_core.ROOT == Path({str(PROJECT_ROOT)!r})
assert cycle_robustness_core.red_noise_log_excess.__module__ == 'seven_cycle_platform.cycles.discovery'
assert discover_cycle_periods_robust.bootstrap_interval.__module__ == 'seven_cycle_platform.cycles.discovery'
assert discover_cycle_periods_robust.main.__module__ == 'seven_cycle_platform.cycles.discovery'
print(cycle_robustness_core.ROOT)
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(PROJECT_ROOT)


def test_importing_cycles_does_not_mutate_process_warning_filters() -> None:
    code = """
import warnings

import numpy
import pandas
from scipy import ndimage, signal
from scipy.sparse import SparseEfficiencyWarning
import statsmodels.api
import seven_cycle_platform.registry.models

before = tuple(warnings.filters)
import seven_cycle_platform.cycles
after = tuple(warnings.filters)

if after != before:
    raise SystemExit(f"warnings.filters changed: before={before!r} after={after!r}")
print(len(after), SparseEfficiencyWarning.__name__)
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
