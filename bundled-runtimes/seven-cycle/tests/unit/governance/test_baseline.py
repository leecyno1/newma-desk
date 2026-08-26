from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError
import pytest
import yaml

from seven_cycle_platform.governance.baseline import load_evidence_baseline


BASELINE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "seven_cycle"
    / "evidence_baseline.yaml"
)


def _write_payload(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "evidence_baseline.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _baseline_payload() -> dict[str, object]:
    return yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))


def test_baseline_contains_exactly_c1_through_c7() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)
    assert [record.cycle_id for record in baseline.cycles] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]


def test_baseline_preserves_current_research_metadata() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)

    assert baseline.generated.isoformat() == "2026-08-12"
    assert baseline.source_document == (
        "docs/research/seven-cycle-evidence-baseline-2026-08-12.md"
    )


def test_c1_is_explanatory_only() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)
    record = baseline.cycles[0]

    assert record.evidence_status == "explanatory_only"
    assert record.empirical_band_months is None
    assert "modern_technology_bridge_rejected" in record.reason_codes


def test_c4_is_supported_and_c5_is_blocked() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)
    records = {record.cycle_id: record for record in baseline.cycles}

    assert records["C4"].evidence_status == "supported"
    assert records["C4"].empirical_band_months == (40.0, 42.2)
    assert records["C5"].evidence_status == "unidentified"
    assert "red_noise_not_significant" in records["C5"].reason_codes


def test_loaded_baseline_and_records_are_immutable() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)

    with pytest.raises(ValidationError, match="frozen"):
        baseline.source_document = "changed.md"
    with pytest.raises(ValidationError, match="frozen"):
        baseline.cycles[0].evidence_status = "supported"


def test_supported_evidence_requires_a_band(tmp_path: Path) -> None:
    payload = deepcopy(_baseline_payload())
    payload["cycles"][3]["empirical_band_months"] = None

    with pytest.raises(ValidationError, match="requires empirical_band_months"):
        load_evidence_baseline(_write_payload(tmp_path, payload))


def test_unidentified_evidence_cannot_publish_a_band(tmp_path: Path) -> None:
    payload = deepcopy(_baseline_payload())
    payload["cycles"][4]["empirical_band_months"] = [18, 22]

    with pytest.raises(ValidationError, match="cannot publish an empirical band"):
        load_evidence_baseline(_write_payload(tmp_path, payload))


def test_duplicate_or_missing_cycles_are_rejected_clearly(tmp_path: Path) -> None:
    payload = deepcopy(_baseline_payload())
    payload["cycles"][-1] = deepcopy(payload["cycles"][0])

    with pytest.raises(ValueError, match="must contain C1 through C7 in order"):
        load_evidence_baseline(_write_payload(tmp_path, payload))


def test_unknown_or_missing_fields_are_rejected(tmp_path: Path) -> None:
    unknown_payload = deepcopy(_baseline_payload())
    unknown_payload["cycles"][0]["confidence"] = "high"
    missing_payload = deepcopy(_baseline_payload())
    del missing_payload["cycles"][0]["reason_codes"]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_evidence_baseline(_write_payload(tmp_path, unknown_payload))
    with pytest.raises(ValidationError, match="Field required"):
        load_evidence_baseline(_write_payload(tmp_path, missing_payload))


def test_approved_values_are_strictly_typed(tmp_path: Path) -> None:
    payload = deepcopy(_baseline_payload())
    payload["cycles"][0]["center_prior_months"] = "600"

    with pytest.raises(ValidationError, match="valid number"):
        load_evidence_baseline(_write_payload(tmp_path, payload))


def test_unknown_evidence_status_is_rejected(tmp_path: Path) -> None:
    payload = deepcopy(_baseline_payload())
    payload["cycles"][0]["evidence_status"] = "probable"

    with pytest.raises(ValidationError, match="Input should be") as error:
        load_evidence_baseline(_write_payload(tmp_path, payload))
    assert "too_short" not in str(error.value)


def test_malformed_yaml_is_rejected_clearly(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    path.write_text("generated: [2026-07-19\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid evidence baseline YAML"):
        load_evidence_baseline(path)


def test_duplicate_key_inside_cycle_is_rejected(tmp_path: Path) -> None:
    contents = BASELINE_PATH.read_text(encoding="utf-8").replace(
        "    evidence_status: supported\n",
        "    evidence_status: supported\n    evidence_status: unidentified\n",
        1,
    )
    path = tmp_path / "duplicate-key.yaml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate key 'evidence_status'"):
        load_evidence_baseline(path)


def test_missing_path_preserves_file_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        load_evidence_baseline(path)
