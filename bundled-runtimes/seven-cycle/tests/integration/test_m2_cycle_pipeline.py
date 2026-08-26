from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.cycles import (
    CycleModelVersion,
    DiscoveryEvidence,
    ManualOverride,
    RecalibrationReason,
    RecalibrationStatus,
)
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import collect_product_checksums
from seven_cycle_platform.storage.run_context import canonical_json_bytes
from seven_cycle_platform.types import ReleaseStatus, VintageKind


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = PROJECT_ROOT / "config" / "seven_cycle"
AS_OF = date(2024, 5, 31)
CREATED_AT = datetime(2026, 7, 12, 12, tzinfo=timezone.utc)
RETRIEVAL_TIME = datetime(2026, 7, 12, 8, tzinfo=timezone.utc)
ANNUAL_CATEGORIES = {
    "annual_growth": "growth",
    "annual_prices": "prices",
    "annual_credit": "credit",
}
MONTHLY_CATEGORIES = {
    "monthly_growth": "growth",
    "monthly_prices": "prices",
    "monthly_credit": "credit",
}
MANDATORY_CHECKS = {
    "cutoff_reconstruction",
    "schema_contract",
    "no_lookahead",
}


def _api():
    try:
        pipeline = importlib.import_module("seven_cycle_platform.pipeline.cycles")
        verification = importlib.import_module(
            "seven_cycle_platform.verification.cycles"
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"M2 Task 11 public API is missing: {error}", pytrace=False)
    required_pipeline = (
        "CyclePipelineInput",
        "CycleVerifiers",
        "QuarterlyDiscoveryEvidence",
        "QuarterlyManualOverride",
        "build_cycles",
        "estimate_states",
        "load_vintage",
        "publish",
        "recalibrate_if_due",
        "verify",
        "write_cycle_pipeline_input",
    )
    required_verification = (
        "CycleAcceptanceError",
        "QualityFinding",
        "verify_published_cycle_run",
    )
    missing = [
        f"pipeline.{name}"
        for name in required_pipeline
        if not hasattr(pipeline, name)
    ]
    missing.extend(
        f"verification.{name}"
        for name in required_verification
        if not hasattr(verification, name)
    )
    if missing:
        pytest.fail(
            "M2 Task 11 public API is missing: " + ", ".join(missing),
            pytrace=False,
        )
    return pipeline, verification


def _observation(
    *,
    entity_id: str,
    observation_date: date,
    release_date: date,
    value: float,
    vintage_kind: VintageKind = VintageKind.REALTIME,
) -> Observation:
    return Observation(
        entity_id=entity_id,
        observation_date=observation_date,
        release_date=release_date,
        vintage_date=release_date,
        value=value,
        unit="index_points",
        source="synthetic_m2_archive",
        retrieval_time=RETRIEVAL_TIME,
        revision_number=0,
        quality_status="accepted",
        vintage_kind=vintage_kind,
    )


@pytest.fixture(scope="module")
def observations() -> tuple[Observation, ...]:
    records: list[Observation] = []
    annual_entities = tuple(ANNUAL_CATEGORIES)
    for year in range(1940, 2024):
        observation_date = date(year, 12, 31)
        release_date = observation_date + timedelta(days=90)
        elapsed = float(year - 1940)
        values = (
            np.sin(2.0 * np.pi * elapsed / 9.0)
            + 0.25 * np.sin(2.0 * np.pi * elapsed / 45.0),
            np.cos(2.0 * np.pi * elapsed / 14.0),
            np.sin(2.0 * np.pi * elapsed / 18.0 + 0.4),
        )
        records.extend(
            _observation(
                entity_id=entity_id,
                observation_date=observation_date,
                release_date=release_date,
                value=float(value),
            )
            for entity_id, value in zip(annual_entities, values, strict=True)
        )

    monthly_entities = tuple(MONTHLY_CATEGORIES)
    for position, timestamp in enumerate(
        pd.date_range("1995-01-31", "2024-04-30", freq="ME")
    ):
        observation_date = timestamp.date()
        release_date = observation_date + timedelta(days=10)
        elapsed = float(position)
        values = (
            np.sin(2.0 * np.pi * elapsed / 42.0)
            + 0.30 * np.sin(2.0 * np.pi * elapsed / 21.0),
            np.cos(2.0 * np.pi * elapsed / 30.0),
            np.sin(2.0 * np.pi * elapsed / 15.0 + 0.6),
        )
        records.extend(
            _observation(
                entity_id=entity_id,
                observation_date=observation_date,
                release_date=release_date,
                value=float(value),
            )
            for entity_id, value in zip(monthly_entities, values, strict=True)
        )
    return tuple(records)


@pytest.fixture(scope="module")
def prior_versions() -> tuple[CycleModelVersion, ...]:
    bundle = load_registry_bundle(REGISTRY_DIR)
    versions = []
    for cycle in bundle.cycles:
        center = (
            float(cycle.initial_center)
            if cycle.initial_center is not None
            else float((cycle.search_min + cycle.search_max) / 2.0)
        )
        versions.append(
            CycleModelVersion(
                cycle_id=cycle.cycle_id,
                effective_date=date(2024, 3, 31),
                old_center=center,
                new_center=center,
                old_band=(float(cycle.search_min), float(cycle.search_max)),
                new_band=(float(cycle.search_min), float(cycle.search_max)),
                old_confidence=0.80,
                new_confidence=0.80,
                candidate_center=center,
                status=RecalibrationStatus.ACCEPTED,
                reason_code=RecalibrationReason.ACCEPTED,
                rejection_reason=None,
                reason_codes=(RecalibrationReason.ACCEPTED,),
                evidence_metrics={"governed_fixture": 1},
            )
        )
    return tuple(versions)


@pytest.fixture()
def pipeline_input(
    observations: tuple[Observation, ...],
    prior_versions: tuple[CycleModelVersion, ...],
):
    pipeline, _ = _api()
    return pipeline.CyclePipelineInput(
        observations=observations,
        annual_categories=ANNUAL_CATEGORIES,
        monthly_categories=MONTHLY_CATEGORIES,
        prior_model_versions=prior_versions,
        discovery_evidence=(),
        state_dates=(date(2018, 6, 30), date(2022, 12, 31)),
        verification_cutoffs=(date(2018, 6, 30), date(2022, 12, 31)),
    )


def _publish_prior_latest(product_root: Path) -> bytes:
    payload = b'{"prior":true}\n'
    context = RunContext.create(
        as_of=date(2024, 3, 31),
        data_vintage=date(2024, 3, 31),
        model_version="prior-governed-run",
        config={"kind": "prior"},
        input_checksums={"prior.json": hashlib.sha256(payload).hexdigest()},
        quality_summary={"passed": 1},
        created_at=CREATED_AT,
    )

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "prior.json").write_bytes(payload)

    publish_run(product_root, context, write_staging=write_staging)
    return (product_root / "latest.json").read_bytes()


def _finding(verification, check: str, status: str):
    return verification.QualityFinding(
        entity_id="seven_cycle_platform",
        check=check,
        severity="mandatory",
        status=status,
        message=f"forced {status.lower()} for {check}",
        observed_value=1.0 if status == "PASS" else 0.0,
        threshold=1.0,
    )


def _forced_verifiers(pipeline, verification, failing_check: str):
    def request_gate(check: str):
        return lambda request: _finding(
            verification,
            check,
            "FAIL" if check == failing_check else "PASS",
        )

    def schema_gate(staged_dir: Path, manifest):
        return _finding(
            verification,
            "schema_contract",
            "FAIL" if failing_check == "schema_contract" else "PASS",
        )

    return pipeline.CycleVerifiers(
        cutoff_reconstruction=request_gate("cutoff_reconstruction"),
        schema_contract=schema_gate,
        no_lookahead=request_gate("no_lookahead"),
    )


def _dual_interpretation_input(pipeline_input):
    latest_historical = tuple(
        observation.model_copy(
            update={"vintage_kind": VintageKind.LATEST_HISTORICAL}
        )
        for observation in pipeline_input.observations
    )
    revision_base = next(
        observation
        for observation in pipeline_input.observations
        if observation.entity_id == "monthly_growth"
        and observation.observation_date == date(2017, 1, 31)
    )
    revised_latest = revision_base.model_copy(
        update={
            "value": float(revision_base.value + 25.0),
            "vintage_date": date(2018, 1, 15),
            "revision_number": 1,
            "vintage_kind": VintageKind.LATEST_HISTORICAL,
        }
    )
    return replace(
        pipeline_input,
        observations=(
            *pipeline_input.observations,
            *latest_historical,
            revised_latest,
        ),
    )


def _quarterly_evidence(
    pipeline,
    pipeline_input,
    *,
    weak_cycle_id: str | None = None,
):
    evidence = []
    for version in pipeline_input.prior_model_versions:
        center = version.new_center
        weak = version.cycle_id == weak_cycle_id
        evidence.append(
            pipeline.QuarterlyDiscoveryEvidence(
                cycle_id=version.cycle_id,
                effective_date=date(2024, 6, 30),
                evidence=DiscoveryEvidence(
                    candidate_center=center,
                    bootstrap_period_low=center - 0.25,
                    bootstrap_period_high=center + 0.25,
                    red_noise_score=0.0 if weak else 1.0,
                    category_support=1.0,
                    macro_only_score=1.0,
                    category_balanced_score=1.0,
                    method_agreement=1.0,
                    method_peak_periods={
                        "canonical": center,
                        "canonical_hp": center,
                        "canonical_linear": center,
                    },
                    supporting_categories=("credit", "growth", "prices"),
                    total_categories=3,
                    series_count=6,
                    random_seed=20260712,
                ),
            )
        )
    return tuple(evidence)


def _mixed_pseudo_realtime_input(pipeline_input):
    realtime_available_from = date(2019, 1, 31)
    pseudo = tuple(
        observation.model_copy(
            update={"vintage_kind": VintageKind.PSEUDO_VINTAGE}
        )
        for observation in pipeline_input.observations
    )
    realtime = tuple(
        observation.model_copy(
            update={
                "release_date": max(
                    observation.release_date,
                    realtime_available_from,
                ),
                "vintage_date": max(
                    observation.vintage_date,
                    realtime_available_from,
                ),
                "vintage_kind": VintageKind.REALTIME,
            }
        )
        for observation in pipeline_input.observations
    )
    return replace(pipeline_input, observations=(*pseudo, *realtime))


def _patch_default_verifiers(
    monkeypatch: pytest.MonkeyPatch,
    verification,
    *,
    failing_check: str = "none",
) -> None:
    def request_finding(check: str, request):
        count = float(len(request.verification_cutoffs))
        return verification.QualityFinding(
            entity_id="seven_cycle_platform",
            check=check,
            severity="mandatory",
            status="FAIL" if check == failing_check else "PASS",
            message=f"default {check}",
            observed_value=0.0 if check == failing_check else count,
            threshold=count,
        )

    monkeypatch.setattr(
        verification,
        "verify_cutoff_reconstruction",
        lambda request: request_finding("cutoff_reconstruction", request),
    )
    monkeypatch.setattr(
        verification,
        "verify_no_lookahead",
        lambda request: request_finding("no_lookahead", request),
    )
    monkeypatch.setattr(
        verification,
        "verify_schema_contract",
        lambda staged_dir, manifest: verification.QualityFinding(
            entity_id="seven_cycle_platform",
            check="schema_contract",
            severity="mandatory",
            status=("FAIL" if failing_check == "schema_contract" else "PASS"),
            message="default schema_contract",
            observed_value=(0.0 if failing_check == "schema_contract" else 1.0),
            threshold=1.0,
        ),
    )


def _assert_blocked_preserves_prior(
    result,
    *,
    product_root: Path,
    latest_before: bytes,
    prior_runs: list[str],
    failed_check: str,
) -> None:
    assert result.status is ReleaseStatus.BLOCKED
    assert result.manifest is None
    assert result.publication_path is None
    assert any(
        finding.check == failed_check and finding.status == "FAIL"
        for finding in result.findings
    )
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert sorted(path.name for path in (product_root / "runs").iterdir()) == (
        prior_runs
    )
    staging_root = product_root / "staging"
    assert not staging_root.exists() or not any(staging_root.iterdir())


def test_verification_plan_public_contract_is_exposed() -> None:
    _, verification = _api()

    assert hasattr(verification, "CYCLE_VERIFIER_PROFILE")
    assert hasattr(verification, "m2_algorithm_fingerprint")
    assert hasattr(verification, "VERIFICATION_PLAN_FILENAME")
    assert hasattr(verification, "VerificationPlan")


@pytest.mark.integration
def test_m2_build_publishes_governed_products_and_reuses_exact_run(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    product_root = tmp_path / "products" / "seven_cycle"

    first = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert first.status is ReleaseStatus.LIVE
    assert first.reused is False
    assert first.run_id is not None
    assert first.manifest is not None
    run_dir = product_root / "runs" / first.run_id
    expected_files = {
        "registries/assets.json",
        "registries/channels.json",
        "registries/cycles.json",
        "registries/indicators.json",
        "cycle_model_versions.json",
        "cycle_phase_vintage.parquet",
        "quality_findings.parquet",
        "verification_plan.json",
        "manifest.json",
    }
    actual_files = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert (product_root / "latest.json").read_bytes() == (
        json.dumps(
            {"run_id": first.run_id},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    version_payload = json.loads(
        (run_dir / "cycle_model_versions.json").read_text(encoding="utf-8")
    )
    assert version_payload["schema_version"] == 1
    versions = version_payload["versions"]
    assert [version["cycle_id"] for version in versions] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert [version["version_id"] for version in versions] == [
        version.version_id for version in pipeline_input.prior_model_versions
    ]

    cycle_table = pq.read_table(run_dir / "cycle_phase_vintage.parquet")
    from seven_cycle_platform.contracts.arrow import (
        CYCLE_PHASE_VINTAGE_SCHEMA,
        QUALITY_FINDING_SCHEMA,
    )

    assert cycle_table.schema == CYCLE_PHASE_VINTAGE_SCHEMA
    cycle_product = cycle_table.to_pandas()
    assert set(cycle_product["vintage"]) == {VintageKind.REALTIME.value}
    assert cycle_product.groupby(["date", "vintage"]).size().eq(7).all()
    expected_centers = {
        version.cycle_id: version.new_center
        for version in pipeline_input.prior_model_versions
    }
    assert cycle_product.groupby("cycle_id")["center_period"].first().to_dict() == (
        expected_centers
    )

    finding_table = pq.read_table(run_dir / "quality_findings.parquet")
    assert finding_table.schema == QUALITY_FINDING_SCHEMA
    findings = finding_table.to_pandas()
    assert set(findings["check"]) == MANDATORY_CHECKS
    assert findings["status"].eq("PASS").all()
    assert findings["severity"].eq("mandatory").all()
    finding_by_check = findings.set_index("check")
    assert finding_by_check.loc["cutoff_reconstruction", "observed_value"] == 2.0
    assert finding_by_check.loc["cutoff_reconstruction", "threshold"] == 2.0
    assert finding_by_check.loc["no_lookahead", "observed_value"] == 2.0
    assert finding_by_check.loc["no_lookahead", "threshold"] == 2.0

    plan_path = run_dir / "verification_plan.json"
    plan_bytes = plan_path.read_bytes()
    plan_payload = json.loads(plan_bytes)
    assert plan_bytes == canonical_json_bytes(plan_payload) + b"\n"
    assert plan_payload == {
        "algorithm_fingerprint": verification.m2_algorithm_fingerprint(),
        "interpretations": ["realtime"],
        "mandatory_checks": [
            "cutoff_reconstruction",
            "schema_contract",
            "no_lookahead",
        ],
        "numeric_tolerance": 1e-10,
        "schema_version": verification.VERIFICATION_PLAN_SCHEMA_VERSION,
        "strict_vintage": True,
        "verification_cutoffs": ["2018-06-30", "2022-12-31"],
        "verifier_profile": verification.CYCLE_VERIFIER_PROFILE,
    }

    acceptance = verification.verify_published_cycle_run(run_dir)
    assert acceptance.manifest == first.manifest
    assert acceptance.checks_verified == 3
    assert acceptance.files_verified == 8

    original_bytes = {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    latest_before = (product_root / "latest.json").read_bytes()
    second = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT + timedelta(hours=1),
    )

    assert second.status is ReleaseStatus.LIVE
    assert second.reused is True
    assert second.run_id == first.run_id
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    } == original_bytes
    assert [path.name for path in (product_root / "runs").iterdir()] == [
        first.run_id
    ]

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_seven_cycle_platform.py"),
            "--run-id",
            first.run_id,
            "--product-root",
            str(product_root),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    assert '"verification":"m2_acceptance"' in completed.stdout
    assert "Traceback" not in completed.stderr

    tampered = cycle_product.copy(deep=True)
    tampered["run_id"] = "caller-controlled-provenance"
    pq.write_table(
        cycle_table.from_pandas(tampered, schema=CYCLE_PHASE_VINTAGE_SCHEMA),
        run_dir / "cycle_phase_vintage.parquet",
    )
    updated_manifest = first.manifest.with_product_checksums(
        collect_product_checksums(run_dir)
    )
    (run_dir / "manifest.json").write_bytes(updated_manifest.to_json_bytes())
    with pytest.raises(
        verification.CycleAcceptanceError,
        match="RunContext|provenance|run_id",
    ):
        verification.verify_published_cycle_run(run_dir)


@pytest.mark.integration
def test_exact_run_reuse_still_honors_current_injected_veto(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    product_root = tmp_path / "products" / "seven_cycle"
    first = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )
    assert first.status is ReleaseStatus.LIVE
    assert first.run_id is not None
    run_dir = product_root / "runs" / first.run_id
    latest_before = (product_root / "latest.json").read_bytes()
    run_bytes_before = {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    second = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT + timedelta(hours=1),
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="cutoff_reconstruction",
        ),
    )

    assert second.status is ReleaseStatus.BLOCKED
    assert second.reused is False
    assert second.manifest is None
    assert any(
        finding.check == "cutoff_reconstruction"
        and finding.status == "FAIL"
        for finding in second.findings
    )
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    } == run_bytes_before
    assert [path.name for path in (product_root / "runs").iterdir()] == [
        first.run_id
    ]
    staging_root = product_root / "staging"
    assert not staging_root.exists() or not any(staging_root.iterdir())


@pytest.mark.integration
def test_exact_run_reuse_blocks_when_current_candidate_product_differs(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, _ = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    product_root = tmp_path / "products" / "seven_cycle"
    first = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )
    assert first.status is ReleaseStatus.LIVE
    assert first.run_id is not None
    run_dir = product_root / "runs" / first.run_id
    latest_before = (product_root / "latest.json").read_bytes()
    run_bytes_before = {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    original_builder = pipeline.build_cycle_phase_vintage

    def changed_candidate(states, *, context):
        product = original_builder(states, context=context).copy(deep=True)
        index = product.index[product["confidence"].lt(0.999)][0]
        product.loc[index, "confidence"] += 0.001
        return product

    monkeypatch.setattr(
        pipeline,
        "build_cycle_phase_vintage",
        changed_candidate,
    )

    second = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT + timedelta(hours=1),
    )

    assert second.status is ReleaseStatus.BLOCKED
    assert second.reused is False
    assert second.manifest is None
    assert any(
        finding.check == "schema_contract"
        and finding.status == "FAIL"
        and "checksum" in finding.message
        for finding in second.findings
    )
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    } == run_bytes_before
    assert [path.name for path in (product_root / "runs").iterdir()] == [
        first.run_id
    ]
    staging_root = product_root / "staging"
    assert not staging_root.exists() or not any(staging_root.iterdir())


@pytest.mark.integration
def test_algorithm_fingerprint_changes_run_identity_without_invalidating_archive(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    product_root = tmp_path / "products" / "seven_cycle"
    first = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )
    assert first.status is ReleaseStatus.LIVE
    first_dir = product_root / "runs" / first.run_id
    first_plan = json.loads((first_dir / "verification_plan.json").read_bytes())
    changed_fingerprint = "f" * 64
    assert first_plan["algorithm_fingerprint"] != changed_fingerprint
    monkeypatch.setattr(
        pipeline,
        "m2_algorithm_fingerprint",
        lambda: changed_fingerprint,
    )

    second = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT + timedelta(hours=1),
    )

    assert second.status is ReleaseStatus.LIVE
    assert second.reused is False
    assert second.run_id != first.run_id
    second_dir = product_root / "runs" / second.run_id
    second_plan = json.loads((second_dir / "verification_plan.json").read_bytes())
    assert second_plan["algorithm_fingerprint"] == changed_fingerprint
    assert first.manifest.config_hash != second.manifest.config_hash
    assert verification.verify_published_cycle_run(first_dir).manifest == first.manifest


@pytest.mark.integration
def test_realtime_and_latest_historical_are_both_causally_verified(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    dual_input = _dual_interpretation_input(pipeline_input)
    product_root = tmp_path / "products" / "seven_cycle"
    original_reconstruct = verification.reconstruct_cycle_vintage
    verified_interpretations: list[VintageKind] = []

    def record_interpretation(records, **kwargs):
        interpretation = VintageKind(kwargs["interpretation"])
        verified_interpretations.append(interpretation)
        return original_reconstruct(records, **kwargs)

    monkeypatch.setattr(
        verification,
        "reconstruct_cycle_vintage",
        record_interpretation,
    )

    result = pipeline.build_cycles(
        dual_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.LIVE
    assert result.run_id is not None
    assert set(verified_interpretations) == {
        VintageKind.REALTIME,
        VintageKind.LATEST_HISTORICAL,
    }
    run_dir = product_root / "runs" / result.run_id
    product = pq.read_table(run_dir / "cycle_phase_vintage.parquet").to_pandas()
    assert set(product["vintage"]) == {
        VintageKind.REALTIME.value,
        VintageKind.LATEST_HISTORICAL.value,
    }
    plan = json.loads((run_dir / "verification_plan.json").read_bytes())
    assert plan["interpretations"] == [
        VintageKind.REALTIME.value,
        VintageKind.LATEST_HISTORICAL.value,
    ]
    findings = pq.read_table(run_dir / "quality_findings.parquet").to_pandas()
    finding_by_check = findings.set_index("check")
    assert finding_by_check.loc["cutoff_reconstruction", "observed_value"] == 4.0
    assert finding_by_check.loc["cutoff_reconstruction", "threshold"] == 4.0
    assert finding_by_check.loc["no_lookahead", "observed_value"] == 4.0
    assert finding_by_check.loc["no_lookahead", "threshold"] == 4.0
    verification.verify_published_cycle_run(run_dir)


@pytest.mark.integration
def test_latest_historical_no_lookahead_difference_blocks_publication(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    dual_input = _dual_interpretation_input(pipeline_input)
    product_root = tmp_path / "products" / "seven_cycle"
    original_reconstruct = verification.reconstruct_cycle_vintage
    original_count = len(dual_input.observations)
    verified_interpretations: list[VintageKind] = []

    def inject_latest_future_difference(records, **kwargs):
        interpretation = VintageKind(kwargs["interpretation"])
        verified_interpretations.append(interpretation)
        output = original_reconstruct(records, **kwargs)
        if (
            interpretation is VintageKind.LATEST_HISTORICAL
            and len(tuple(records)) > original_count
        ):
            output = output.copy(deep=True)
            output["center_period"] = output["center_period"] + 0.5
        return output

    monkeypatch.setattr(
        verification,
        "reconstruct_cycle_vintage",
        inject_latest_future_difference,
    )

    result = pipeline.build_cycles(
        dual_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert any(
        finding.check == "no_lookahead" and finding.status == "FAIL"
        for finding in result.findings
    )
    assert VintageKind.LATEST_HISTORICAL in verified_interpretations
    assert not (product_root / "latest.json").exists()
    assert not (product_root / "runs").exists()
    staging_root = product_root / "staging"
    assert not staging_root.exists() or not any(staging_root.iterdir())


@pytest.mark.integration
@pytest.mark.parametrize("failing_check", sorted(MANDATORY_CHECKS))
def test_any_mandatory_gate_blocks_without_advancing_latest(
    tmp_path: Path,
    pipeline_input,
    failing_check: str,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    latest_before = _publish_prior_latest(product_root)
    prior_runs = sorted(path.name for path in (product_root / "runs").iterdir())

    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check,
        ),
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert result.manifest is None
    assert result.publication_path is None
    assert any(
        finding.check == failing_check and finding.status == "FAIL"
        for finding in result.findings
    )
    assert (product_root / "latest.json").read_bytes() == latest_before
    assert sorted(path.name for path in (product_root / "runs").iterdir()) == (
        prior_runs
    )
    staging_root = product_root / "staging"
    assert not staging_root.exists() or not any(staging_root.iterdir())


@pytest.mark.integration
def test_cycle_product_construction_exception_returns_blocked(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    latest_before = _publish_prior_latest(product_root)
    prior_runs = sorted(path.name for path in (product_root / "runs").iterdir())
    _patch_default_verifiers(monkeypatch, verification)

    def fail_product(*args, **kwargs):
        raise RuntimeError("forced cycle product construction failure")

    monkeypatch.setattr(pipeline, "build_cycle_phase_vintage", fail_product)

    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    _assert_blocked_preserves_prior(
        result,
        product_root=product_root,
        latest_before=latest_before,
        prior_runs=prior_runs,
        failed_check="schema_contract",
    )


@pytest.mark.integration
@pytest.mark.parametrize("failure_point", ["staging_write", "staged_acceptance"])
def test_publication_stage_exception_returns_blocked_and_cleans_staging(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    latest_before = _publish_prior_latest(product_root)
    prior_runs = sorted(path.name for path in (product_root / "runs").iterdir())
    _patch_default_verifiers(monkeypatch, verification)

    if failure_point == "staging_write":
        original_write = pipeline.write_cycle_phase_vintage

        def fail_staging_write(run_dir: Path, product, *, context):
            if Path(run_dir).parent.name == "staging":
                raise RuntimeError("forced staging product write failure")
            return original_write(run_dir, product, context=context)

        monkeypatch.setattr(
            pipeline,
            "write_cycle_phase_vintage",
            fail_staging_write,
        )
    else:
        original_acceptance = pipeline.verify_published_cycle_run

        def fail_staged_acceptance(run_dir: Path):
            if Path(run_dir).parent.name == "staging":
                raise RuntimeError("forced staged acceptance failure")
            return original_acceptance(run_dir)

        monkeypatch.setattr(
            pipeline,
            "verify_published_cycle_run",
            fail_staged_acceptance,
        )

    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    _assert_blocked_preserves_prior(
        result,
        product_root=product_root,
        latest_before=latest_before,
        prior_runs=prior_runs,
        failed_check="schema_contract",
    )


@pytest.mark.integration
def test_custom_pass_verifiers_cannot_override_default_mandatory_failure(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    latest_before = _publish_prior_latest(product_root)
    prior_runs = sorted(path.name for path in (product_root / "runs").iterdir())
    _patch_default_verifiers(
        monkeypatch,
        verification,
        failing_check="cutoff_reconstruction",
    )

    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    _assert_blocked_preserves_prior(
        result,
        product_root=product_root,
        latest_before=latest_before,
        prior_runs=prior_runs,
        failed_check="cutoff_reconstruction",
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "verification_cutoffs",
    [
        (date(2022, 12, 31),),
        (date(1930, 6, 30), date(1930, 12, 31)),
    ],
)
def test_insufficient_or_no_data_verification_cutoffs_block_before_build(
    tmp_path: Path,
    pipeline_input,
    verification_cutoffs: tuple[date, ...],
) -> None:
    pipeline, _ = _api()
    invalid_input = replace(
        pipeline_input,
        verification_cutoffs=verification_cutoffs,
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        invalid_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert {finding.check for finding in result.findings} == {
        "verification_plan"
    }
    assert not (product_root / "latest.json").exists()
    assert not (product_root / "runs").exists()


@pytest.mark.integration
def test_sparse_cutoff_publishes_governed_unavailable_rows(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    first_cutoff = pipeline_input.verification_cutoffs[0]
    sparse_input = replace(
        pipeline_input,
        observations=tuple(
            observation
            for observation in pipeline_input.observations
            if observation.entity_id in ANNUAL_CATEGORIES
            or observation.release_date > first_cutoff
        ),
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        sparse_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.LIVE
    run_dir = product_root / "runs" / result.run_id
    product = pq.read_table(run_dir / "cycle_phase_vintage.parquet").to_pandas()
    first_rows = product.loc[
        pd.to_datetime(product["date"]).dt.date.eq(first_cutoff)
    ]
    unavailable = first_rows.loc[first_rows["cycle_id"].isin({"C4", "C5", "C6", "C7"})]
    assert len(unavailable) == 4
    assert unavailable[
        ["angle", "phase", "level", "slope", "amplitude", "uncertainty"]
    ].isna().all().all()
    assert unavailable["confidence"].eq(0.0).all()
    verification.verify_published_cycle_run(run_dir)


@pytest.mark.integration
def test_recalibration_due_without_evidence_blocks_instead_of_inventing(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    due_input = replace(
        pipeline_input,
        state_dates=(date(2024, 6, 30),),
    )

    result = pipeline.build_cycles(
        due_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=tmp_path / "products" / "seven_cycle",
        as_of=date(2024, 6, 30),
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert {finding.check for finding in result.findings} == {
        "recalibration_evidence"
    }
    assert "absent" in result.findings[0].message.lower()
    assert not (tmp_path / "products" / "seven_cycle" / "latest.json").exists()


def test_due_recalibration_uses_supplied_quarterly_evidence(
    pipeline_input,
) -> None:
    pipeline, _ = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    evidence = []
    for version in pipeline_input.prior_model_versions:
        center = version.new_center
        candidate_center = center + 1.0 if version.cycle_id == "C5" else center
        evidence.append(
            pipeline.QuarterlyDiscoveryEvidence(
                cycle_id=version.cycle_id,
                effective_date=date(2024, 6, 30),
                evidence=DiscoveryEvidence(
                    candidate_center=candidate_center,
                    bootstrap_period_low=candidate_center - 0.25,
                    bootstrap_period_high=candidate_center + 0.25,
                    red_noise_score=1.0,
                    category_support=1.0,
                    macro_only_score=1.0,
                    category_balanced_score=1.0,
                    method_agreement=1.0,
                    method_peak_periods={
                        "canonical": candidate_center,
                        "canonical_hp": candidate_center,
                        "canonical_linear": candidate_center,
                    },
                    supporting_categories=("credit", "growth", "prices"),
                    total_categories=3,
                    series_count=6,
                    random_seed=20260712,
                ),
            )
        )
    due_input = replace(
        pipeline_input,
        discovery_evidence=tuple(evidence),
        state_dates=(date(2024, 6, 30),),
    )

    governed = pipeline.recalibrate_if_due(
        due_input,
        registry_bundle=bundle,
        as_of=date(2024, 6, 30),
    )

    assert len(governed.model_versions) == 7
    assert {version.effective_date for version in governed.model_versions} == {
        date(2024, 6, 30)
    }
    assert [version.previous_version_id for version in governed.model_versions] == [
        version.version_id for version in pipeline_input.prior_model_versions
    ]
    assert {
        cycle.cycle_id: cycle.initial_center for cycle in governed.cycle_specs
    } == {
        version.cycle_id: version.new_center
        for version in governed.model_versions
    }
    for cycle in governed.cycle_specs:
        expected_prior_months = (
            float(cycle.initial_center) * 12.0
            if cycle.frequency == "A"
            else float(cycle.initial_center)
        )
        assert cycle.center_prior_months == pytest.approx(
            expected_prior_months,
            abs=1e-4,
        )


@pytest.mark.integration
def test_manual_override_flows_through_pipeline_and_published_model_version(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, _ = _api()
    override = pipeline.QuarterlyManualOverride(
        cycle_id="C1",
        effective_date=date(2024, 6, 30),
        override=ManualOverride(
            requested_center=50.0,
            authorized_by="model_governance_committee",
            reason="Approved structural-break drift exception.",
        ),
    )
    due_input = replace(
        pipeline_input,
        discovery_evidence=_quarterly_evidence(pipeline, pipeline_input),
        manual_overrides=(override,),
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        due_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=date(2024, 6, 30),
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.LIVE
    versions = json.loads(
        (
            product_root
            / "runs"
            / result.run_id
            / "cycle_model_versions.json"
        ).read_bytes()
    )["versions"]
    c1 = next(version for version in versions if version["cycle_id"] == "C1")
    assert c1["status"] == RecalibrationStatus.ACCEPTED.value
    assert c1["reason_code"] == RecalibrationReason.MANUAL_OVERRIDE.value
    assert c1["new_center"] == 50.0
    assert c1["manual_override"] == {
        "authorized_by": "model_governance_committee",
        "reason": "Approved structural-break drift exception.",
        "requested_center": 50.0,
    }


@pytest.mark.integration
def test_weak_evidence_rejects_pipeline_override_with_audit_provenance(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, _ = _api()
    override = pipeline.QuarterlyManualOverride(
        cycle_id="C1",
        effective_date=date(2024, 6, 30),
        override=ManualOverride(
            requested_center=50.0,
            authorized_by="model_governance_committee",
            reason="Requested exception pending evidence gate.",
        ),
    )
    due_input = replace(
        pipeline_input,
        discovery_evidence=_quarterly_evidence(
            pipeline,
            pipeline_input,
            weak_cycle_id="C1",
        ),
        manual_overrides=(override,),
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        due_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=date(2024, 6, 30),
        strict_vintage=True,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.LIVE
    versions = json.loads(
        (
            product_root
            / "runs"
            / result.run_id
            / "cycle_model_versions.json"
        ).read_bytes()
    )["versions"]
    c1 = next(version for version in versions if version["cycle_id"] == "C1")
    assert c1["status"] == RecalibrationStatus.REJECTED.value
    assert c1["reason_code"] == RecalibrationReason.LOW_RED_NOISE_SCORE.value
    assert RecalibrationReason.MANUAL_OVERRIDE_NOT_APPLIED.value in c1["reason_codes"]
    assert c1["new_center"] == c1["old_center"]
    assert c1["manual_override"] == {
        "authorized_by": "model_governance_committee",
        "reason": "Requested exception pending evidence gate.",
        "requested_center": 50.0,
    }


def test_manual_override_contract_round_trips_and_rejects_duplicate_keys(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, _ = _api()
    override = pipeline.QuarterlyManualOverride(
        cycle_id="C1",
        effective_date=date(2024, 6, 30),
        override=ManualOverride(
            requested_center=50.0,
            authorized_by="model_governance_committee",
            reason="Approved offline bundle request.",
        ),
    )
    override_input = replace(pipeline_input, manual_overrides=(override,))
    input_dir = tmp_path / "inputs"

    pipeline.write_cycle_pipeline_input(input_dir, override_input)
    loaded = pipeline.load_cycle_pipeline_input(input_dir)

    assert loaded == override_input
    with pytest.raises(ValueError, match="manual_overrides.*unique"):
        replace(pipeline_input, manual_overrides=(override, override))


@pytest.mark.integration
def test_non_strict_mixed_pseudo_to_realtime_product_passes_acceptance(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    mixed_input = _mixed_pseudo_realtime_input(pipeline_input)
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        mixed_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=False,
        created_at=CREATED_AT,
    )

    assert result.status is ReleaseStatus.LIVE
    run_dir = product_root / "runs" / result.run_id
    product = pq.read_table(run_dir / "cycle_phase_vintage.parquet").to_pandas()
    vintage_by_date = {
        row_date: set(rows["vintage"])
        for row_date, rows in product.groupby("date")
    }
    assert vintage_by_date == {
        date(2018, 6, 30): {VintageKind.PSEUDO_VINTAGE.value},
        date(2022, 12, 31): {VintageKind.REALTIME.value},
    }
    verification.verify_published_cycle_run(run_dir)


@pytest.mark.integration
def test_strict_pipeline_rejects_selected_pseudo_vintage(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    pseudo_input = replace(
        pipeline_input,
        observations=tuple(
            observation.model_copy(
                update={"vintage_kind": VintageKind.PSEUDO_VINTAGE}
            )
            for observation in pipeline_input.observations
        ),
    )

    result = pipeline.build_cycles(
        pseudo_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=tmp_path / "products" / "seven_cycle",
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert {finding.check for finding in result.findings} == {
        "vintage_contract"
    }
    assert "pseudo_vintage" in result.findings[0].message
    assert not (tmp_path / "products" / "seven_cycle" / "latest.json").exists()


def test_cli_input_bundle_round_trips_the_immutable_contract(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, _ = _api()
    input_dir = tmp_path / "inputs"

    path = pipeline.write_cycle_pipeline_input(input_dir, pipeline_input)
    loaded = pipeline.load_cycle_pipeline_input(input_dir)

    assert path == input_dir / pipeline.CYCLE_PIPELINE_INPUT_FILENAME
    assert loaded == pipeline_input
    with pytest.raises(TypeError):
        loaded.annual_categories["new"] = "category"


@pytest.mark.integration
def test_secret_bearing_model_audit_text_is_blocked_before_publication(
    tmp_path: Path,
    pipeline_input,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, verification = _api()
    secret = "m2-secret-audit-value"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    base = pipeline_input.prior_model_versions[0]
    secret_version = CycleModelVersion(
        cycle_id=base.cycle_id,
        effective_date=base.effective_date,
        old_center=base.old_center,
        new_center=base.new_center,
        old_band=base.old_band,
        new_band=base.new_band,
        old_confidence=base.old_confidence,
        new_confidence=base.new_confidence,
        candidate_center=base.candidate_center,
        status=RecalibrationStatus.ACCEPTED,
        reason_code=RecalibrationReason.MANUAL_OVERRIDE,
        rejection_reason=None,
        reason_codes=(RecalibrationReason.MANUAL_OVERRIDE,),
        evidence_metrics=base.evidence_metrics,
        manual_override=ManualOverride(
            requested_center=base.new_center,
            authorized_by=secret,
            reason="approved governance override",
        ),
    )
    secret_input = replace(
        pipeline_input,
        prior_model_versions=(
            secret_version,
            *pipeline_input.prior_model_versions[1:],
        ),
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        secret_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert {finding.check for finding in result.findings} == {"secret_contract"}
    assert secret not in result.findings[0].message
    assert not (product_root / "latest.json").exists()
    assert not (product_root / "runs").exists()


@pytest.mark.integration
def test_acceptance_wrapper_reports_corrupt_quality_product_without_traceback(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )
    assert result.status is ReleaseStatus.LIVE
    assert result.manifest is not None
    run_dir = product_root / "runs" / result.run_id
    (run_dir / "quality_findings.parquet").write_bytes(b"not parquet")
    updated_manifest = result.manifest.with_product_checksums(
        collect_product_checksums(run_dir)
    )
    (run_dir / "manifest.json").write_bytes(updated_manifest.to_json_bytes())

    with pytest.raises(verification.CycleAcceptanceError):
        verification.verify_published_cycle_run(run_dir)

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_seven_cycle_platform.py"),
            "--run-id",
            result.run_id,
            "--product-root",
            str(product_root),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 1
    assert "M2 acceptance verification failed" in completed.stderr
    assert "Traceback" not in completed.stderr


@pytest.mark.integration
def test_acceptance_rejects_removed_and_tampered_verification_plan(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    product_root = tmp_path / "products" / "seven_cycle"
    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=load_registry_bundle(REGISTRY_DIR),
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
    )
    assert result.status is ReleaseStatus.LIVE
    assert result.manifest is not None
    run_dir = product_root / "runs" / result.run_id
    plan_path = run_dir / "verification_plan.json"
    original_plan = plan_path.read_bytes()
    original_manifest = (run_dir / "manifest.json").read_bytes()

    plan_path.unlink()
    removed_manifest = result.manifest.with_product_checksums(
        collect_product_checksums(run_dir)
    )
    (run_dir / "manifest.json").write_bytes(removed_manifest.to_json_bytes())
    with pytest.raises(
        verification.CycleAcceptanceError,
        match="verification plan|required M2 products",
    ):
        verification.verify_published_cycle_run(run_dir)

    plan_path.write_bytes(original_plan)
    (run_dir / "manifest.json").write_bytes(original_manifest)
    tampered_payload = json.loads(original_plan)
    tampered_payload["verifier_profile"] = "tampered-profile"
    plan_path.write_bytes(canonical_json_bytes(tampered_payload) + b"\n")
    tampered_manifest = result.manifest.with_product_checksums(
        collect_product_checksums(run_dir)
    )
    (run_dir / "manifest.json").write_bytes(tampered_manifest.to_json_bytes())
    with pytest.raises(
        verification.CycleAcceptanceError,
        match="verification plan|verifier profile|config_hash",
    ):
        verification.verify_published_cycle_run(run_dir)


@pytest.mark.integration
def test_in_memory_registry_cross_contract_failure_blocks_publication(
    tmp_path: Path,
    pipeline_input,
) -> None:
    pipeline, verification = _api()
    bundle = load_registry_bundle(REGISTRY_DIR)
    invalid_channel = bundle.channels[0].model_copy(
        deep=True,
        update={"eligible_indicator_concepts": ["unknown_concept"]},
    )
    invalid_bundle = bundle.model_copy(
        deep=True,
        update={"channels": [invalid_channel, *bundle.channels[1:]]},
    )
    product_root = tmp_path / "products" / "seven_cycle"

    result = pipeline.build_cycles(
        pipeline_input,
        registry_bundle=invalid_bundle,
        product_root=product_root,
        as_of=AS_OF,
        strict_vintage=True,
        created_at=CREATED_AT,
        verifiers=_forced_verifiers(
            pipeline,
            verification,
            failing_check="none",
        ),
    )

    assert result.status is ReleaseStatus.BLOCKED
    assert {finding.check for finding in result.findings} == {
        "registry_contract"
    }
    assert not (product_root / "latest.json").exists()
