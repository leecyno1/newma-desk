"""End-to-end atomic-release degradation contracts for the API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from conftest import PublishedRun, assert_row_provenance, publish_catalog


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_failed_post_publish_gate_preserves_live_run_and_stale_service(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    before = client.get("/v1/assets/compare?horizon=12")
    live_tree = _tree_bytes(published_run.run_dir)
    live_catalog = published_run.catalog_path.read_bytes()
    latest = published_run.product_root / "latest.json"
    candidate_catalog: Path | None = None

    def reject_candidate(run_dir: Path, manifest: object) -> None:
        nonlocal candidate_catalog
        assert run_dir.name == manifest.run_id
        candidate_catalog = published_run.catalog_root / f"{manifest.run_id}.duckdb"
        raise RuntimeError("candidate catalog validation failed")

    with pytest.raises(RuntimeError, match="candidate catalog validation failed"):
        publish_catalog(
            published_run.product_root,
            published_run.catalog_root,
            label="b",
            validate_published=reject_candidate,
        )

    assert json.loads(latest.read_text()) == {"run_id": published_run.context.run_id}
    assert _tree_bytes(published_run.run_dir) == live_tree
    assert published_run.catalog_path.read_bytes() == live_catalog
    assert candidate_catalog is not None
    assert not candidate_catalog.exists()
    assert list((published_run.product_root / "runs").glob(".failed.*"))

    after = client.get("/v1/assets/compare?horizon=12")
    assert after.status_code == 200
    assert after.json()["freshness"] == "stale"
    assert after.headers["etag"] == before.headers["etag"]
    assert after.headers["x-catalog-checksum"] == before.headers["x-catalog-checksum"]
    assert_row_provenance(after, published_run)


def test_post_catalog_failure_removes_candidate_catalog_and_keeps_live_run(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    live_catalog = published_run.catalog_path.read_bytes()
    candidate_catalog: Path | None = None

    def reject_after_catalog(candidate: PublishedRun) -> None:
        nonlocal candidate_catalog
        candidate_catalog = candidate.catalog_path
        assert candidate_catalog.is_file()
        raise RuntimeError("post-catalog gate failed")

    with pytest.raises(RuntimeError, match="post-catalog gate failed"):
        publish_catalog(
            published_run.product_root,
            published_run.catalog_root,
            label="b",
            after_catalog_before_latest=reject_after_catalog,
        )

    assert candidate_catalog is not None
    assert not candidate_catalog.exists()
    assert published_run.catalog_path.read_bytes() == live_catalog
    assert json.loads((published_run.product_root / "latest.json").read_text()) == {
        "run_id": published_run.context.run_id
    }
    after = client.get("/v1/assets/compare?horizon=12")
    assert after.status_code == 200
    assert_row_provenance(after, published_run)


def test_next_request_switches_wholly_after_successful_publish_and_catalog(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    before = client.get("/v1/assets/compare?horizon=12")
    observed: list[object] = []

    def observe_catalog_before_latest(candidate: PublishedRun) -> None:
        pre_latest = client.get("/v1/assets/compare?horizon=12")
        observed.append(pre_latest)

        assert candidate.catalog_path.is_file()
        assert pre_latest.status_code == 200
        assert_row_provenance(pre_latest, published_run)

    next_run = publish_catalog(
        published_run.product_root,
        published_run.catalog_root,
        label="b",
        after_catalog_before_latest=observe_catalog_before_latest,
    )

    after = client.get("/v1/assets/compare?horizon=12")
    assert before.status_code == 200
    assert len(observed) == 1
    assert after.status_code == 200
    assert json.loads((published_run.product_root / "latest.json").read_text()) == {
        "run_id": next_run.context.run_id
    }
    assert after.headers["etag"] != before.headers["etag"]
    assert after.headers["x-catalog-checksum"] != before.headers["x-catalog-checksum"]
    assert after.headers["x-manifest-checksum"] != before.headers["x-manifest-checksum"]
    assert_row_provenance(after, next_run)


def test_shared_catalog_rejects_same_run_without_harming_first_publisher(
    client: TestClient,
    published_run: PublishedRun,
    tmp_path: Path,
) -> None:
    original_catalog = published_run.catalog_path.read_bytes()

    with pytest.raises(FileExistsError, match="catalog"):
        publish_catalog(
            tmp_path / "second-products",
            published_run.catalog_root,
            label="a",
        )

    assert published_run.catalog_path.read_bytes() == original_catalog
    response = client.get("/v1/assets/compare?horizon=12")
    assert response.status_code == 200
    assert_row_provenance(response, published_run)


def test_catalog_cleanup_preserves_concurrent_replacement_and_gate_error(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    replacement_path: Path | None = None
    displaced_catalog: Path | None = None

    def replace_catalog_then_fail(candidate: PublishedRun) -> None:
        nonlocal displaced_catalog, replacement_path
        replacement_path = candidate.catalog_path
        displaced_catalog = replacement_path.with_name(
            f"displaced-{replacement_path.name}"
        )
        replacement_path.rename(displaced_catalog)
        replacement_path.mkdir()
        raise RuntimeError("original gate failure")

    with pytest.raises(RuntimeError, match="original gate failure"):
        publish_catalog(
            published_run.product_root,
            published_run.catalog_root,
            label="b",
            after_catalog_before_latest=replace_catalog_then_fail,
        )

    assert replacement_path is not None
    assert displaced_catalog is not None
    assert replacement_path.is_dir()
    assert displaced_catalog.is_file()
    response = client.get("/v1/assets/compare?horizon=12")
    assert response.status_code == 200
    assert_row_provenance(response, published_run)
