from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_FILENAME,
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME,
    DATA_IDENTITY_SCHEMA,
    PROVENANCE_FIELDS,
    PUBLICATION_GATE_FILENAME,
    PUBLICATION_GATE_SCHEMA,
    write_records,
)
from seven_cycle_platform.storage import RunContext


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2026, 7, 19),
        data_vintage=date(2025, 12, 31),
        model_version="research-foundation-v1",
        config={"kind": "research_foundation"},
        input_checksums={"evidence": "0" * 64},
        quality_summary={"passed": 1},
        created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )


def _cycle_evidence_record() -> dict[str, object]:
    return {
        "cycle_id": "C4",
        "evidence_status": "supported",
        "center_prior_months": 42.0,
        "empirical_min_months": 40.0,
        "empirical_max_months": 42.2,
        "family_centers_json": "[40.0,41.55,42.05,42.2]",
        "reason_codes_json": '["cross_family_consensus"]',
        "summary": "C4 supported.",
    }


def _data_identity_record() -> dict[str, object]:
    return {
        "entity_id": "c4_macro_panel",
        "source": "approved_prototype",
        "frequency": "M",
        "unit": "standardized_factor",
        "transform": "family_balanced_composite",
        "observation_start": date(2005, 1, 31),
        "source_data_as_of": date(2025, 12, 31),
        "release_date": date(2026, 7, 19),
        "retrieval_time": datetime(2026, 7, 19, tzinfo=timezone.utc),
        "vintage_kind": "pseudo_vintage",
        "stale_months": 7,
        "stale_after_months": 2,
        "freshness_status": "stale",
        "proxy_for": None,
        "caveat": "Original release vintages unavailable.",
    }


def _run_dir(root: Path, context: RunContext) -> Path:
    run_dir = root / context.run_id
    run_dir.mkdir(parents=True)
    return run_dir


def test_governance_schemas_use_exact_provenance_suffix() -> None:
    expected_suffix = pa.schema(PROVENANCE_FIELDS)

    for schema in (
        CYCLE_EVIDENCE_SCHEMA,
        DATA_IDENTITY_SCHEMA,
        PUBLICATION_GATE_SCHEMA,
        CALIBRATION_LOG_SCHEMA,
    ):
        suffix = pa.schema(list(schema)[-len(PROVENANCE_FIELDS) :])
        assert suffix.equals(expected_suffix)


def test_governance_schemas_only_allow_domain_optional_nulls() -> None:
    assert {field.name for field in CYCLE_EVIDENCE_SCHEMA if field.nullable} == {
        "empirical_min_months",
        "empirical_max_months",
    }
    assert {field.name for field in DATA_IDENTITY_SCHEMA if field.nullable} == {
        "proxy_for"
    }
    assert not any(field.nullable for field in PUBLICATION_GATE_SCHEMA)
    assert not any(field.nullable for field in CALIBRATION_LOG_SCHEMA)
    assert not any(field.nullable for field in PROVENANCE_FIELDS)


def test_writer_injects_manifest_provenance(tmp_path) -> None:
    context = _context()
    run_dir = _run_dir(tmp_path, context)

    path = write_records(
        run_dir,
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=[_cycle_evidence_record()],
        context=context,
    )
    table = pq.read_table(path)

    assert table.column("run_id").to_pylist() == [context.run_id]
    assert table.column("as_of").to_pylist() == [context.as_of]
    assert table.column("data_vintage").to_pylist() == [context.data_vintage]
    assert table.column("model_version").to_pylist() == [context.model_version]
    assert table.column("config_hash").to_pylist() == [context.config_hash]
    assert table.column("created_at").to_pylist() == [context.created_at]
    assert table.schema.equals(CYCLE_EVIDENCE_SCHEMA, check_metadata=False)


@pytest.mark.parametrize(
    ("filename", "schema"),
    [
        (CYCLE_EVIDENCE_FILENAME, CYCLE_EVIDENCE_SCHEMA),
        (DATA_IDENTITY_FILENAME, DATA_IDENTITY_SCHEMA),
        (PUBLICATION_GATE_FILENAME, PUBLICATION_GATE_SCHEMA),
        (CALIBRATION_LOG_FILENAME, CALIBRATION_LOG_SCHEMA),
    ],
)
def test_writer_persists_each_governed_schema(
    tmp_path,
    filename: str,
    schema: pa.Schema,
) -> None:
    context = _context()
    path = write_records(
        _run_dir(tmp_path, context),
        filename=filename,
        schema=schema,
        records=[],
        context=context,
    )

    assert pq.read_schema(path).equals(schema, check_metadata=False)


def test_writer_rejects_missing_extra_and_caller_provenance(tmp_path) -> None:
    context = _context()
    run_dir = _run_dir(tmp_path, context)
    missing = _cycle_evidence_record()
    del missing["summary"]
    with pytest.raises(ValueError, match="missing fields: summary"):
        write_records(
            run_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[missing],
            context=context,
        )

    extra = {**_cycle_evidence_record(), "unexpected": "value"}
    with pytest.raises(ValueError, match="unexpected fields: unexpected"):
        write_records(
            run_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[extra],
            context=context,
        )

    caller_provenance = {**_cycle_evidence_record(), "run_id": "caller-value"}
    with pytest.raises(ValueError, match="provenance.*RunContext"):
        write_records(
            run_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[caller_provenance],
            context=context,
        )


def test_writer_rejects_silent_field_coercion(tmp_path) -> None:
    context = _context()
    record = {**_cycle_evidence_record(), "center_prior_months": "42.0"}

    with pytest.raises(TypeError, match="center_prior_months must be float64"):
        write_records(
            _run_dir(tmp_path, context),
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[record],
            context=context,
        )


def test_writer_rejects_none_for_required_fields(tmp_path) -> None:
    context = _context()
    record = {**_cycle_evidence_record(), "cycle_id": None}

    with pytest.raises(ValueError, match=r"records\[0\]\.cycle_id cannot be null"):
        write_records(
            _run_dir(tmp_path, context),
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[record],
            context=context,
        )


def test_writer_round_trips_optional_nulls(tmp_path) -> None:
    context = _context()
    run_dir = _run_dir(tmp_path, context)
    evidence = {
        **_cycle_evidence_record(),
        "evidence_status": "unidentified",
        "empirical_min_months": None,
        "empirical_max_months": None,
    }

    evidence_path = write_records(
        run_dir,
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=[evidence],
        context=context,
    )
    identity_path = write_records(
        run_dir,
        filename=DATA_IDENTITY_FILENAME,
        schema=DATA_IDENTITY_SCHEMA,
        records=[_data_identity_record()],
        context=context,
    )

    evidence_row = pq.read_table(evidence_path).to_pylist()[0]
    identity_row = pq.read_table(identity_path).to_pylist()[0]
    assert evidence_row["empirical_min_months"] is None
    assert evidence_row["empirical_max_months"] is None
    assert identity_row["proxy_for"] is None


def test_writer_rejects_non_utc_record_timestamps(tmp_path) -> None:
    context = _context()
    record = {
        **_data_identity_record(),
        "retrieval_time": datetime(
            2026,
            7,
            19,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    }

    with pytest.raises(ValueError, match="retrieval_time must use UTC"):
        write_records(
            _run_dir(tmp_path, context),
            filename=DATA_IDENTITY_FILENAME,
            schema=DATA_IDENTITY_SCHEMA,
            records=[record],
            context=context,
        )


def test_writer_rejects_run_directory_mismatch(tmp_path) -> None:
    context = _context()
    wrong_run_dir = tmp_path / "wrong-run-id"
    wrong_run_dir.mkdir()

    with pytest.raises(
        ValueError,
        match="run_dir name must match RunContext run_id",
    ):
        write_records(
            wrong_run_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[_cycle_evidence_record()],
            context=context,
        )


def test_writer_canonicalizes_row_order_and_file_bytes(tmp_path) -> None:
    context = _context()
    c4_record = _cycle_evidence_record()
    c1_record = {
        **_cycle_evidence_record(),
        "cycle_id": "C1",
        "center_prior_months": 600.0,
        "summary": "C1 scenario supported.",
    }
    forward_records = [c1_record, c4_record]
    reversed_records = [dict(c4_record), dict(c1_record)]
    forward_snapshot = [dict(record) for record in forward_records]
    reversed_snapshot = [dict(record) for record in reversed_records]

    forward_path = write_records(
        _run_dir(tmp_path / "forward", context),
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=forward_records,
        context=context,
    )
    reversed_path = write_records(
        _run_dir(tmp_path / "reversed", context),
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=reversed_records,
        context=context,
    )

    assert pq.read_table(forward_path).column("cycle_id").to_pylist() == ["C1", "C4"]
    assert pq.read_table(reversed_path).column("cycle_id").to_pylist() == ["C1", "C4"]
    assert (
        hashlib.sha256(forward_path.read_bytes()).digest()
        == hashlib.sha256(reversed_path.read_bytes()).digest()
    )
    assert forward_records == forward_snapshot
    assert reversed_records == reversed_snapshot


def test_writer_refuses_overwrite_without_changing_existing_product(tmp_path) -> None:
    context = _context()
    run_dir = _run_dir(tmp_path, context)
    path = write_records(
        run_dir,
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=[_cycle_evidence_record()],
        context=context,
    )
    original = path.read_bytes()

    with pytest.raises(FileExistsError, match="refuse accidental overwrite"):
        write_records(
            run_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=[_cycle_evidence_record()],
            context=context,
        )

    assert path.read_bytes() == original
    assert not list(run_dir.glob(f".{CYCLE_EVIDENCE_FILENAME}.*.tmp"))
