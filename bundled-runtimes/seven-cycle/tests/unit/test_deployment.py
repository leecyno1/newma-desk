from __future__ import annotations

from datetime import date
import os
from pathlib import Path

import pytest

import seven_cycle_platform.deployment as deployment
from seven_cycle_platform.deployment import (
    DeploymentError,
    install_catalog_repair_transaction,
    recover_pending_catalog_repair,
    verify_deployment_for_catalog_repair,
    write_deployment_manifest,
)
from seven_cycle_platform.storage.run_context import canonical_json_bytes


RUN_ID = "2026-07-24-7180d6f1dc9e-61d62230f1a7"


def _latest(product_root: Path, run_id: str = RUN_ID) -> tuple[Path, bytes, tuple[int, int]]:
    path = product_root / "latest.json"
    content = canonical_json_bytes({"run_id": run_id}) + b"\n"
    path.write_bytes(content)
    path_stat = path.stat()
    return path, content, (path_stat.st_dev, path_stat.st_ino)


def test_catalog_repair_transaction_rolls_back_all_three_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    web_root = tmp_path / "web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    previous_checksum = "1" * 64
    replacement_checksum = "2" * 64
    write_deployment_manifest(
        product_root=product_root,
        catalog_checksum=previous_checksum,
        run_id=RUN_ID,
        deployment_as_of=date(2026, 7, 24),
        web_root=web_root,
    )
    snapshot = verify_deployment_for_catalog_repair(
        product_root=product_root,
        web_root=web_root,
        run_id=RUN_ID,
        catalog_checksum=previous_checksum,
    )
    catalog_path = tmp_path / "catalog.duckdb"
    candidate_path = tmp_path / "candidate.duckdb"
    catalog_path.write_bytes(b"previous-catalog")
    candidate_path.write_bytes(b"candidate-catalog")
    catalog_identity = catalog_path.stat().st_dev, catalog_path.stat().st_ino
    latest_path, latest_content, latest_identity = _latest(product_root)
    product_before = snapshot.product_path.read_bytes()
    web_before = snapshot.web_path.read_bytes()
    real_replace = os.replace
    injected = False

    def fail_web_commit(source: object, target: object) -> None:
        nonlocal injected
        if Path(target) == snapshot.web_path and not injected:
            injected = True
            raise OSError("injected web deployment replace failure")
        real_replace(source, target)

    monkeypatch.setattr(deployment.os, "replace", fail_web_commit)

    with pytest.raises(OSError, match="injected web deployment"):
        install_catalog_repair_transaction(
            snapshot=snapshot,
            catalog_path=catalog_path,
            catalog_identity=catalog_identity,
            candidate_catalog_path=candidate_path,
            latest_content=latest_content,
            latest_identity=latest_identity,
            latest_path=latest_path,
            replacement_catalog_checksum=replacement_checksum,
        )

    assert catalog_path.read_bytes() == b"previous-catalog"
    assert snapshot.product_path.read_bytes() == product_before
    assert snapshot.web_path.read_bytes() == web_before
    assert not candidate_path.exists()


@pytest.mark.parametrize("committed_targets", [1, 2, 3])
def test_pending_journal_recovers_each_partial_commit_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committed_targets: int,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    web_root = tmp_path / "web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    previous_checksum = "1" * 64
    replacement_checksum = "2" * 64
    write_deployment_manifest(
        product_root=product_root,
        catalog_checksum=previous_checksum,
        run_id=RUN_ID,
        deployment_as_of=date(2026, 7, 24),
        web_root=web_root,
    )
    snapshot = verify_deployment_for_catalog_repair(
        product_root=product_root,
        web_root=web_root,
        run_id=RUN_ID,
        catalog_checksum=previous_checksum,
    )
    catalog_root = tmp_path / "catalogs"
    catalog_root.mkdir()
    catalog_path = catalog_root / f"{RUN_ID}.duckdb"
    candidate_path = catalog_root / "candidate.duckdb"
    catalog_path.write_bytes(b"previous-catalog")
    candidate_path.write_bytes(b"candidate-catalog")
    catalog_identity = catalog_path.stat().st_dev, catalog_path.stat().st_ino
    latest_path, latest_content, latest_identity = _latest(product_root)
    real_forward = deployment._forward_repair

    def interrupt_after_partial_commit(records, *, latest_guard) -> None:
        for record in records[:committed_targets]:
            os.replace(Path(record["staged"]), Path(record["target"]))
        raise RuntimeError("simulated process interruption")

    with monkeypatch.context() as context:
        context.setattr(deployment, "_forward_repair", interrupt_after_partial_commit)
        context.setattr(deployment, "_rollback_repair", lambda records: False)
        with pytest.raises(DeploymentError, match="recovery is pending"):
            install_catalog_repair_transaction(
                snapshot=snapshot,
                catalog_path=catalog_path,
                catalog_identity=catalog_identity,
                candidate_catalog_path=candidate_path,
                latest_content=latest_content,
                latest_identity=latest_identity,
                latest_path=latest_path,
                replacement_catalog_checksum=replacement_checksum,
            )

    assert deployment._forward_repair is real_forward
    recovered = recover_pending_catalog_repair(
        product_root=product_root,
        catalog_root=catalog_root,
        web_root=web_root,
    )
    assert recovered["action"] == "completed_pending_repair"
    assert catalog_path.read_bytes() == b"candidate-catalog"
    assert snapshot.product_path.read_bytes() == snapshot.web_path.read_bytes()
    assert replacement_checksum.encode() in snapshot.product_path.read_bytes()
    assert not (product_root / deployment.REPAIR_JOURNAL_FILENAME).exists()


def test_latest_advance_is_refused_immediately_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    web_root = tmp_path / "web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    write_deployment_manifest(
        product_root=product_root,
        catalog_checksum="1" * 64,
        run_id=RUN_ID,
        deployment_as_of=date(2026, 7, 24),
        web_root=web_root,
    )
    snapshot = verify_deployment_for_catalog_repair(
        product_root=product_root,
        web_root=web_root,
        run_id=RUN_ID,
        catalog_checksum="1" * 64,
    )
    catalog_path = tmp_path / f"{RUN_ID}.duckdb"
    candidate_path = tmp_path / "candidate.duckdb"
    catalog_path.write_bytes(b"old")
    candidate_path.write_bytes(b"new")
    catalog_identity = catalog_path.stat().st_dev, catalog_path.stat().st_ino
    latest_path, latest_content, latest_identity = _latest(product_root)
    real_write_journal = deployment._write_repair_journal

    def advance_after_journal(path: Path, payload: dict[str, object]) -> None:
        real_write_journal(path, payload)
        latest_path.write_bytes(
            canonical_json_bytes(
                {"run_id": "2026-07-25-aaaaaaaaaaaa-bbbbbbbbbbbb"}
            )
            + b"\n"
        )

    monkeypatch.setattr(deployment, "_write_repair_journal", advance_after_journal)
    with pytest.raises(DeploymentError, match="latest run changed"):
        install_catalog_repair_transaction(
            snapshot=snapshot,
            catalog_path=catalog_path,
            catalog_identity=catalog_identity,
            candidate_catalog_path=candidate_path,
            latest_content=latest_content,
            latest_identity=latest_identity,
            latest_path=latest_path,
            replacement_catalog_checksum="2" * 64,
        )
    assert catalog_path.read_bytes() == b"old"
    assert snapshot.product_path.read_bytes() == snapshot.content
    assert snapshot.web_path.read_bytes() == snapshot.content


def test_latest_advance_after_final_replace_rolls_back_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    web_root = tmp_path / "web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    write_deployment_manifest(
        product_root=product_root,
        catalog_checksum="1" * 64,
        run_id=RUN_ID,
        deployment_as_of=date(2026, 7, 24),
        web_root=web_root,
    )
    snapshot = verify_deployment_for_catalog_repair(
        product_root=product_root,
        web_root=web_root,
        run_id=RUN_ID,
        catalog_checksum="1" * 64,
    )
    catalog_path = tmp_path / f"{RUN_ID}.duckdb"
    candidate_path = tmp_path / "candidate.duckdb"
    catalog_path.write_bytes(b"old")
    candidate_path.write_bytes(b"new")
    catalog_identity = catalog_path.stat().st_dev, catalog_path.stat().st_ino
    latest_path, latest_content, latest_identity = _latest(product_root)
    real_replace = os.replace
    advanced = False

    def advance_after_final_replace(source: object, target: object) -> None:
        nonlocal advanced
        real_replace(source, target)
        if Path(target) == snapshot.web_path and not advanced:
            advanced = True
            latest_path.write_bytes(
                canonical_json_bytes(
                    {"run_id": "2026-07-25-aaaaaaaaaaaa-bbbbbbbbbbbb"}
                )
                + b"\n"
            )

    monkeypatch.setattr(deployment.os, "replace", advance_after_final_replace)
    with pytest.raises(DeploymentError, match="latest run changed"):
        install_catalog_repair_transaction(
            snapshot=snapshot,
            catalog_path=catalog_path,
            catalog_identity=catalog_identity,
            candidate_catalog_path=candidate_path,
            latest_content=latest_content,
            latest_identity=latest_identity,
            latest_path=latest_path,
            replacement_catalog_checksum="2" * 64,
        )
    assert catalog_path.read_bytes() == b"old"
    assert snapshot.product_path.read_bytes() == snapshot.content
    assert snapshot.web_path.read_bytes() == snapshot.content
    assert not (product_root / deployment.REPAIR_JOURNAL_FILENAME).exists()


def test_staged_files_are_cleaned_when_deployment_lock_is_busy(
    tmp_path: Path,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    web_root = tmp_path / "web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    (product_root / ".deployment-update.lock").write_text(
        "active\n",
        encoding="utf-8",
    )

    with pytest.raises(DeploymentError, match="concurrently"):
        write_deployment_manifest(
            product_root=product_root,
            catalog_checksum="1" * 64,
            run_id=RUN_ID,
            deployment_as_of=date(2026, 7, 24),
            web_root=web_root,
        )

    assert list(product_root.glob(".deployment.json.*.tmp")) == []
    assert list((web_root / "data").glob(".deployment.json.*.tmp")) == []
