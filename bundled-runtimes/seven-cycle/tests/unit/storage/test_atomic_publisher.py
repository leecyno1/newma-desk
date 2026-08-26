from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest


def _checksum_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context():
    from seven_cycle_platform.storage.run_context import RunContext

    return RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="seven-cycle-v1",
        config={"model": {"window": 12}, "cycles": ["C1", "C2"]},
        input_checksums={
            "inputs/observations.parquet": _checksum_bytes(b"observations")
        },
        quality_summary={"failed": 0, "passed": 4},
        created_at=datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    )


def _product_root(tmp_path: Path) -> Path:
    return tmp_path / "products" / "seven_cycle"


def test_publish_promotes_complete_run_and_atomically_updates_latest(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    cycle_bytes = b"cycle-product"
    report_bytes = b'{"status":"passed"}\n'
    validation_calls: list[str] = []

    def write_staging(staging_dir: Path) -> None:
        tables_dir = staging_dir / "tables"
        tables_dir.mkdir()
        (tables_dir / "cycles.parquet").write_bytes(cycle_bytes)
        (staging_dir / "quality.json").write_bytes(report_bytes)

    def validate_staging(staging_dir: Path, manifest: RunManifest) -> None:
        validation_calls.append(manifest.run_id)
        assert not (product_root / "latest.json").exists()
        assert not (product_root / "runs" / manifest.run_id).exists()
        assert (staging_dir / "manifest.json").is_file()
        assert manifest.product_checksums == {
            "quality.json": _checksum_bytes(report_bytes),
            "tables/cycles.parquet": _checksum_bytes(cycle_bytes),
        }

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
        validate_staging=validate_staging,
    )

    run_dir = product_root / "runs" / context.run_id
    stored_manifest = RunManifest.model_validate_json(
        (run_dir / "manifest.json").read_bytes()
    )

    assert validation_calls == [context.run_id]
    assert manifest == stored_manifest
    assert stored_manifest.product_checksums == {
        "quality.json": _checksum_bytes(report_bytes),
        "tables/cycles.parquet": _checksum_bytes(cycle_bytes),
    }
    assert not (product_root / "staging" / context.run_id).exists()
    assert (run_dir / "quality.json").read_bytes() == report_bytes
    assert json.loads((product_root / "latest.json").read_bytes()) == {
        "run_id": context.run_id
    }
    assert list(product_root.glob(".latest.*.tmp")) == []


def test_validation_failure_preserves_latest_and_hides_failed_run(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{ "run_id": "prior-run", "keep": "exact bytes" }\n'
    latest_path.write_bytes(prior_pointer)

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.parquet").write_bytes(b"candidate")

    def reject_staging(staging_dir: Path, manifest: RunManifest) -> None:
        assert latest_path.read_bytes() == prior_pointer
        assert (staging_dir / "manifest.json").is_file()
        assert not (product_root / "runs" / manifest.run_id).exists()
        raise RuntimeError("contract validation blocked publication")

    with pytest.raises(RuntimeError, match="contract validation blocked"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_staging=reject_staging,
        )

    assert latest_path.read_bytes() == prior_pointer
    assert not (product_root / "runs" / context.run_id).exists()
    assert not (product_root / "staging" / context.run_id).exists()


def test_published_validator_runs_after_rename_and_before_latest(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest, verify_manifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    calls: list[str] = []

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.parquet").write_bytes(b"published")

    def validate_published(run_dir: Path, manifest: RunManifest) -> None:
        calls.append(manifest.run_id)
        assert run_dir == product_root / "runs" / manifest.run_id
        assert run_dir.is_dir()
        assert not (product_root / "staging" / manifest.run_id).exists()
        assert not (product_root / "latest.json").exists()
        verify_manifest(run_dir, expected=manifest)

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
        validate_published=validate_published,
    )

    assert calls == [manifest.run_id]
    assert json.loads((product_root / "latest.json").read_bytes()) == {
        "run_id": manifest.run_id
    }


@pytest.mark.parametrize("existing_latest", [False, True])
def test_published_validation_failure_preserves_latest_and_isolates_run(
    tmp_path: Path,
    existing_latest: bool,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    if existing_latest:
        latest_path.write_bytes(prior_pointer)

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.parquet").write_bytes(b"candidate")

    def reject_published(run_dir: Path, manifest: RunManifest) -> None:
        assert run_dir == product_root / "runs" / manifest.run_id
        assert (run_dir / "manifest.json").is_file()
        if existing_latest:
            assert latest_path.read_bytes() == prior_pointer
        else:
            assert not latest_path.exists()
        raise RuntimeError("published reload blocked publication")

    with pytest.raises(RuntimeError, match="published reload blocked"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_published=reject_published,
        )

    if existing_latest:
        assert latest_path.read_bytes() == prior_pointer
    else:
        assert not latest_path.exists()
    assert not (product_root / "runs" / context.run_id).exists()
    isolated = list((product_root / "runs").glob(f".failed.{context.run_id}.*"))
    assert len(isolated) == 1
    assert (isolated[0] / "cycles.parquet").read_bytes() == b"candidate"
    assert not (product_root / "staging" / context.run_id).exists()


def test_published_failure_never_deletes_concurrent_destination_replacement(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    latest_path.write_bytes(prior_pointer)
    displaced_original = tmp_path / "displaced-original-run"

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.parquet").write_bytes(b"candidate")

    def replace_destination(run_dir: Path, manifest: RunManifest) -> None:
        assert run_dir.name == manifest.run_id
        os.rename(run_dir, displaced_original)
        run_dir.mkdir()
        (run_dir / "concurrent-sentinel.txt").write_bytes(b"do-not-delete")
        raise RuntimeError("concurrent replacement after rename")

    with pytest.raises(RuntimeError, match="concurrent replacement"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_published=replace_destination,
        )

    destination = product_root / "runs" / context.run_id
    assert latest_path.read_bytes() == prior_pointer
    assert (destination / "concurrent-sentinel.txt").read_bytes() == b"do-not-delete"
    assert (displaced_original / "cycles.parquet").read_bytes() == b"candidate"


def test_existing_published_destination_is_never_overwritten(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    destination = product_root / "runs" / context.run_id
    destination.mkdir(parents=True)
    sentinel = destination / "sentinel.txt"
    sentinel.write_bytes(b"immutable")
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    latest_path.write_bytes(prior_pointer)
    writer_called = False

    def write_staging(staging_dir: Path) -> None:
        nonlocal writer_called
        writer_called = True
        (staging_dir / "replacement.txt").write_text("replacement")

    with pytest.raises(FileExistsError, match="immutable"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
        )

    assert writer_called is False
    assert sentinel.read_bytes() == b"immutable"
    assert latest_path.read_bytes() == prior_pointer
    assert not (product_root / "staging" / context.run_id).exists()


def test_post_validation_checksum_mismatch_blocks_promotion(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import (
        ManifestVerificationError,
        RunManifest,
    )
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    latest_path.write_bytes(prior_pointer)

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.parquet").write_bytes(b"validated")

    def mutate_after_validation(
        staging_dir: Path,
        manifest: RunManifest,
    ) -> None:
        assert manifest.product_checksums["cycles.parquet"] == _checksum_bytes(
            b"validated"
        )
        (staging_dir / "cycles.parquet").write_bytes(b"changed")

    with pytest.raises(ManifestVerificationError, match="checksums"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_staging=mutate_after_validation,
        )

    assert latest_path.read_bytes() == prior_pointer
    assert not (product_root / "runs" / context.run_id).exists()
    assert not (product_root / "staging" / context.run_id).exists()


def test_staging_directory_symlink_substitution_is_rejected_safely(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run","keep":"exact"}\n'
    latest_path.write_bytes(prior_pointer)
    external_dir = tmp_path / "external-products"
    external_dir.mkdir()
    external_file = external_dir / "do-not-delete.txt"
    external_file.write_bytes(b"external-content")
    staging_dir = product_root / "staging" / context.run_id
    destination = product_root / "runs" / context.run_id

    def substitute_staging(staging_path: Path) -> None:
        staging_path.rmdir()
        staging_path.symlink_to(external_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="staging directory.*real directory"):
        publish_run(
            product_root,
            context,
            write_staging=substitute_staging,
        )

    assert latest_path.read_bytes() == prior_pointer
    assert not os.path.lexists(destination)
    assert not os.path.lexists(staging_dir)
    assert external_file.read_bytes() == b"external-content"
    assert not (external_dir / "manifest.json").exists()


def test_staging_directory_file_substitution_is_rejected_and_cleaned(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    latest_path.write_bytes(prior_pointer)
    staging_dir = product_root / "staging" / context.run_id
    destination = product_root / "runs" / context.run_id

    def substitute_staging(staging_path: Path) -> None:
        staging_path.rmdir()
        staging_path.write_bytes(b"not-a-directory")

    with pytest.raises(ValueError, match="staging directory.*real directory"):
        publish_run(
            product_root,
            context,
            write_staging=substitute_staging,
        )

    assert latest_path.read_bytes() == prior_pointer
    assert not os.path.lexists(destination)
    assert not os.path.lexists(staging_dir)


def test_post_validation_staging_symlink_substitution_is_rejected_safely(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import RunManifest
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    product_root.mkdir(parents=True)
    latest_path = product_root / "latest.json"
    prior_pointer = b'{"run_id":"prior-run"}\n'
    latest_path.write_bytes(prior_pointer)
    external_dir = tmp_path / "validated-external-products"
    external_dir.mkdir()
    external_file = external_dir / "do-not-delete.txt"
    external_file.write_bytes(b"external-content")
    staging_dir = product_root / "staging" / context.run_id
    destination = product_root / "runs" / context.run_id

    def write_staging(staging_path: Path) -> None:
        (staging_path / "cycles.parquet").write_bytes(b"validated")

    def substitute_after_validation(
        staging_path: Path,
        manifest: RunManifest,
    ) -> None:
        assert manifest.run_id == context.run_id
        shutil.copytree(staging_path, external_dir, dirs_exist_ok=True)
        shutil.rmtree(staging_path)
        staging_path.symlink_to(external_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="staging directory.*real directory"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_staging=substitute_after_validation,
        )

    assert latest_path.read_bytes() == prior_pointer
    assert not os.path.lexists(destination)
    assert not os.path.lexists(staging_dir)
    assert external_file.read_bytes() == b"external-content"
    assert (external_dir / "cycles.parquet").read_bytes() == b"validated"


@pytest.mark.parametrize(
    "root_name",
    ["product_root", "staging_root", "runs_root"],
)
def test_publish_rejects_symlinked_product_layout_roots(
    tmp_path: Path,
    root_name: str,
) -> None:
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    external_dir = tmp_path / f"external-{root_name}"
    external_dir.mkdir()
    external_file = external_dir / "do-not-delete.txt"
    external_file.write_bytes(b"external-content")
    prior_pointer = b'{"run_id":"prior-run"}\n'

    if root_name == "product_root":
        product_root.parent.mkdir(parents=True)
        product_root.symlink_to(external_dir, target_is_directory=True)
        latest_path = external_dir / "latest.json"
    else:
        product_root.mkdir(parents=True)
        latest_path = product_root / "latest.json"
        (product_root / root_name.removesuffix("_root")).symlink_to(
            external_dir,
            target_is_directory=True,
        )
    latest_path.write_bytes(prior_pointer)
    writer_called = False

    def write_staging(staging_path: Path) -> None:
        nonlocal writer_called
        writer_called = True
        (staging_path / "cycles.parquet").write_bytes(b"candidate")

    with pytest.raises(ValueError, match="must be a real directory"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
        )

    assert writer_called is False
    assert latest_path.read_bytes() == prior_pointer
    assert external_file.read_bytes() == b"external-content"
    assert not os.path.lexists(product_root / "runs" / context.run_id)


@pytest.mark.parametrize(
    "root_name",
    ["product_root", "staging_root", "runs_root"],
)
def test_publish_rejects_regular_files_as_product_layout_roots(
    tmp_path: Path,
    root_name: str,
) -> None:
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)
    protected_bytes = b"not-a-directory"
    latest_path: Path | None = None

    if root_name == "product_root":
        product_root.parent.mkdir(parents=True)
        protected_path = product_root
    else:
        product_root.mkdir(parents=True)
        protected_path = product_root / root_name.removesuffix("_root")
        latest_path = product_root / "latest.json"
        latest_path.write_bytes(b'{"run_id":"prior-run"}\n')
    protected_path.write_bytes(protected_bytes)
    writer_called = False

    def write_staging(staging_path: Path) -> None:
        nonlocal writer_called
        writer_called = True

    with pytest.raises(ValueError, match="must be a real directory"):
        publish_run(
            product_root,
            context,
            write_staging=write_staging,
        )

    assert writer_called is False
    assert protected_path.read_bytes() == protected_bytes
    if latest_path is not None:
        assert latest_path.read_bytes() == b'{"run_id":"prior-run"}\n'


@pytest.mark.parametrize("root_kind", ["symlink", "file"])
def test_manifest_operations_reject_non_directory_run_roots(
    tmp_path: Path,
    root_kind: str,
) -> None:
    from seven_cycle_platform.storage.manifest import (
        ManifestVerificationError,
        collect_product_checksums,
        load_manifest,
        verify_manifest,
    )
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)

    def write_staging(staging_path: Path) -> None:
        (staging_path / "cycles.parquet").write_bytes(b"published")

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )
    published_dir = product_root / "runs" / context.run_id
    alias_dir = tmp_path / "alias" / context.run_id
    alias_dir.parent.mkdir()
    if root_kind == "symlink":
        alias_dir.symlink_to(published_dir, target_is_directory=True)
    else:
        alias_dir.write_bytes(b"not-a-directory")

    with pytest.raises(ManifestVerificationError, match="real directory"):
        collect_product_checksums(alias_dir)
    with pytest.raises(ManifestVerificationError, match="real directory"):
        load_manifest(alias_dir)
    with pytest.raises(ManifestVerificationError, match="real directory"):
        verify_manifest(alias_dir, expected=manifest)


def test_trusted_verification_rejects_canonical_manifest_metadata_edit(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.storage.manifest import (
        ManifestVerificationError,
        RunManifest,
        load_manifest,
        verify_manifest,
    )
    from seven_cycle_platform.storage.publisher import publish_run

    context = _context()
    product_root = _product_root(tmp_path)

    def write_staging(staging_path: Path) -> None:
        (staging_path / "cycles.parquet").write_bytes(b"published")

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )
    run_dir = product_root / "runs" / context.run_id
    tampered_payload = manifest.model_dump(mode="python")
    tampered_payload["created_at"] = datetime(
        2026,
        7,
        13,
        9,
        30,
        tzinfo=timezone.utc,
    )
    tampered_manifest = RunManifest.model_validate(tampered_payload)
    (run_dir / "manifest.json").write_bytes(tampered_manifest.to_json_bytes())

    assert load_manifest(run_dir) == tampered_manifest
    with pytest.raises(TypeError, match="expected"):
        verify_manifest(run_dir)
    with pytest.raises(
        ManifestVerificationError,
        match="trusted expected manifest",
    ):
        verify_manifest(run_dir, expected=manifest)
