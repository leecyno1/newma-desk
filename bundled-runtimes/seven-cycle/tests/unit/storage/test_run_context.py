from datetime import date, datetime, timedelta, timezone
import hashlib
from typing import cast
import warnings

from pydantic import ValidationError
import pytest


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _create_context(
    *,
    as_of: date = date(2026, 6, 30),
    data_vintage: date = date(2026, 6, 30),
    model_version: str = "seven-cycle-v1",
    config: dict[str, object] | None = None,
    input_checksums: dict[str, str] | None = None,
    quality_summary: dict[str, object] | None = None,
    product_checksums: dict[str, str] | None = None,
    created_at: datetime | None = None,
):
    from seven_cycle_platform.storage.run_context import RunContext

    return RunContext.create(
        as_of=as_of,
        data_vintage=data_vintage,
        model_version=model_version,
        config=config
        or {
            "features": ["cpi", "gdp"],
            "model": {"enabled": True, "window": 12},
        },
        input_checksums=input_checksums
        or {
            "inputs/cpi.parquet": _checksum("cpi"),
            "inputs/gdp.parquet": _checksum("gdp"),
        },
        quality_summary=quality_summary
        or {"findings": {"failed": 0, "passed": 8}},
        product_checksums=product_checksums or {},
        created_at=created_at
        or datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    )


def test_config_hash_and_run_id_are_canonical_and_idempotent() -> None:
    from seven_cycle_platform.storage.run_context import compute_config_hash

    first_config = {
        "features": ["cpi", "gdp"],
        "model": {"enabled": True, "window": 12},
    }
    reordered_config = {
        "model": {"window": 12, "enabled": True},
        "features": ["cpi", "gdp"],
    }
    first = _create_context(config=first_config)
    second = _create_context(
        config=reordered_config,
        input_checksums={
            "inputs/gdp.parquet": _checksum("gdp"),
            "inputs/cpi.parquet": _checksum("cpi"),
        },
    )
    expected_hash = hashlib.sha256(
        b'{"features":["cpi","gdp"],'
        b'"model":{"enabled":true,"window":12}}'
    ).hexdigest()

    assert compute_config_hash(first_config) == expected_hash
    assert first.config_hash == second.config_hash == expected_hash
    assert first.run_id == second.run_id
    assert first.run_id.startswith(
        f"2026-06-30-{expected_hash[:12]}-"
    )


def test_run_id_changes_when_run_identity_changes() -> None:
    baseline = _create_context()
    changed_as_of = _create_context(as_of=date(2026, 7, 1))
    changed_input = _create_context(
        input_checksums={
            "inputs/cpi.parquet": _checksum("revised-cpi"),
            "inputs/gdp.parquet": _checksum("gdp"),
        }
    )
    changed_model = _create_context(model_version="seven-cycle-v2")

    assert len(
        {
            baseline.run_id,
            changed_as_of.run_id,
            changed_input.run_id,
            changed_model.run_id,
        }
    ) == 4


def test_run_id_pattern_is_public_and_exported() -> None:
    from seven_cycle_platform.storage import RUN_ID_PATTERN as exported_pattern
    from seven_cycle_platform.storage.run_context import RUN_ID_PATTERN

    context = _create_context()

    assert exported_pattern is RUN_ID_PATTERN
    assert RUN_ID_PATTERN.fullmatch(context.run_id)
    assert not RUN_ID_PATTERN.fullmatch("../" + context.run_id)


def test_run_context_is_strict_immutable_and_normalizes_created_at() -> None:
    from seven_cycle_platform.storage.run_context import RunContext

    context = _create_context(
        created_at=datetime(
            2026,
            7,
            12,
            17,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
    )

    assert context.created_at == datetime(
        2026,
        7,
        12,
        9,
        30,
        tzinfo=timezone.utc,
    )
    assert context.created_at.tzinfo is timezone.utc

    with pytest.raises(ValidationError, match="frozen_instance"):
        context.model_version = "changed"

    payload = context.model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RunContext.model_validate(payload)


def test_run_context_rejects_naive_datetimes_and_invalid_identity() -> None:
    from seven_cycle_platform.storage.run_context import RunContext

    with pytest.raises(ValidationError, match="timezone-aware"):
        _create_context(created_at=datetime(2026, 7, 12, 9, 30))

    with pytest.raises(ValidationError, match="SHA-256"):
        _create_context(input_checksums={"inputs/cpi.parquet": "not-a-hash"})

    context = _create_context()
    payload = context.model_dump(mode="python")
    payload["run_id"] = f"2026-06-30-{'0' * 12}-{'1' * 12}"
    with pytest.raises(ValidationError, match="does not match"):
        RunContext.model_validate(payload)


def test_run_context_json_is_deterministic_for_nested_mappings() -> None:
    first = _create_context(
        quality_summary={
            "checks": {"warnings": 1, "errors": 0},
            "status": "passed",
        },
        product_checksums={
            "tables/cycles.parquet": _checksum("cycles"),
            "catalog.duckdb": _checksum("catalog"),
        },
    )
    second = _create_context(
        quality_summary={
            "status": "passed",
            "checks": {"errors": 0, "warnings": 1},
        },
        product_checksums={
            "catalog.duckdb": _checksum("catalog"),
            "tables/cycles.parquet": _checksum("cycles"),
        },
    )

    assert first.model_dump(mode="python") == second.model_dump(mode="python")
    assert first.to_json_bytes() == second.to_json_bytes()


def test_input_checksum_map_rejects_in_place_mutation() -> None:
    context = _create_context()

    with pytest.raises(TypeError, match="immutable"):
        context.input_checksums["inputs/new.parquet"] = _checksum("new")


def test_product_checksum_map_rejects_in_place_mutation() -> None:
    context = _create_context(
        product_checksums={"cycles.parquet": _checksum("cycles")}
    )

    with pytest.raises(TypeError, match="immutable"):
        context.product_checksums["catalog.duckdb"] = _checksum("catalog")


def test_nested_quality_mapping_rejects_in_place_mutation() -> None:
    context = _create_context(
        quality_summary={"findings": {"failed": 0, "passed": 8}}
    )
    findings = cast(dict[str, object], context.quality_summary["findings"])

    with pytest.raises(TypeError, match="immutable"):
        findings["failed"] = 1


def test_quality_sequence_rejects_in_place_mutation() -> None:
    context = _create_context(
        quality_summary={"checks": ["schema", "checksums"]}
    )
    checks = cast(list[object], context.quality_summary["checks"])

    with pytest.raises(TypeError):
        checks[0] = "changed"


def test_run_manifest_inherits_deep_immutability() -> None:
    from seven_cycle_platform.storage.manifest import RunManifest

    context = _create_context(
        quality_summary={"checks": [{"status": "passed"}]},
        product_checksums={"cycles.parquet": _checksum("cycles")},
    )
    manifest = RunManifest.from_context(context)
    check = cast(
        dict[str, object],
        cast(list[object], manifest.quality_summary["checks"])[0],
    )

    with pytest.raises(TypeError, match="immutable"):
        manifest.product_checksums["new.parquet"] = _checksum("new")
    with pytest.raises(TypeError, match="immutable"):
        check["status"] = "failed"


def test_immutable_context_round_trips_as_plain_json_without_warnings() -> None:
    from seven_cycle_platform.storage.run_context import RunContext

    context = _create_context(
        quality_summary={
            "checks": [{"name": "schema", "status": "passed"}],
            "counts": {"failed": 0, "passed": 1},
        },
        product_checksums={"cycles.parquet": _checksum("cycles")},
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        json_payload = context.model_dump(mode="json")
        serialized = context.to_json_bytes()

    assert json_payload["input_checksums"] == dict(context.input_checksums)
    assert json_payload["product_checksums"] == dict(
        context.product_checksums
    )
    assert json_payload["quality_summary"] == {
        "checks": [{"name": "schema", "status": "passed"}],
        "counts": {"failed": 0, "passed": 1},
    }
    assert RunContext.model_validate_json(serialized) == context


def test_quality_summary_redacts_nested_errors_before_manifest_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest

    secret = "dummy-secret-value"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    first = _create_context(
        quality_summary={
            "checks": [
                {
                    "details": {
                        "error": f"upstream echoed {secret}",
                        "url": (
                            "https://example.test/data?api_key="
                            f"{secret}&count=2"
                        ),
                    },
                    "status": "failed",
                }
            ],
            "status": "failed",
        }
    )
    second = _create_context(
        quality_summary={
            "status": "failed",
            "checks": [
                {
                    "status": "failed",
                    "details": {
                        "url": (
                            "https://example.test/data?api_key="
                            f"{secret}&count=2"
                        ),
                        "error": f"upstream echoed {secret}",
                    },
                }
            ],
        }
    )

    manifest = RunManifest.from_context(first)
    serialized = manifest.to_json_bytes()
    checks = cast(list[object], first.quality_summary["checks"])
    first_check = cast(dict[str, object], checks[0])
    details = cast(dict[str, object], first_check["details"])

    assert secret.encode() not in serialized
    assert serialized.count(b"[REDACTED]") == 2
    assert first.to_json_bytes() == second.to_json_bytes()
    assert details["error"] == "upstream echoed [REDACTED]"
    assert details["url"] == (
        "https://example.test/data?api_key=[REDACTED]&count=2"
    )
    with pytest.raises(TypeError, match="immutable"):
        details["error"] = "changed"
