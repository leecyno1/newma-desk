from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil

import pyarrow.parquet as pq
import pytest

import seven_cycle_platform.pipeline.research_foundation as research_foundation
from seven_cycle_platform.pipeline.research_foundation import (
    FoundationSources,
    build_research_foundation,
)
from seven_cycle_platform.products.research_governance import (
    PUBLICATION_GATE_FILENAME,
)
from seven_cycle_platform.storage.manifest import load_manifest, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PRODUCTS = {
    "calibration_log.parquet",
    "cycle_evidence.parquet",
    "cycle_phase_vintage.parquet",
    "data_identity.parquet",
    "publication_gate.parquet",
}


def _sources() -> FoundationSources:
    approved_config = (
        PROJECT_ROOT / "config" / "seven_cycle" / "approved" / "2026-07-19"
    )
    return FoundationSources(
        config_dir=approved_config,
        evidence_path=approved_config / "evidence_baseline.yaml",
        historical_path=(
            PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
        ),
        realtime_path=(
            PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
        ),
        forecast_path=(
            PROJECT_ROOT / "output" / "c4_forecast_prototype_2026-07-19.json"
        ),
        asset_path=(
            PROJECT_ROOT / "output" / "c4_asset_statistics_prototype_2026-07-19.json"
        ),
    )


def _replace_snapshot_content(
    monkeypatch: pytest.MonkeyPatch,
    *,
    role: str,
    content: bytes,
) -> None:
    original_snapshot = research_foundation._snapshot_approved_sources

    def altered_snapshot(sources):
        snapshots = original_snapshot(sources)
        snapshots[role] = replace(snapshots[role], content=content)
        return snapshots

    monkeypatch.setattr(
        research_foundation,
        "_snapshot_approved_sources",
        altered_snapshot,
    )


def test_foundation_run_publishes_auditable_products(tmp_path: Path) -> None:
    sources = _sources()
    product_root = tmp_path / "products"

    result = build_research_foundation(
        sources=sources,
        product_root=product_root,
        as_of=date(2026, 7, 19),
    )

    manifest = load_manifest(result.run_dir)
    assert result.run_id == manifest.run_id == result.run_dir.name
    assert set(manifest.product_checksums) == EXPECTED_PRODUCTS
    assert manifest.as_of == date(2026, 7, 19)
    assert manifest.data_vintage == date(2025, 12, 31)
    assert manifest.model_version == "research-foundation-v1"
    assert manifest.created_at == datetime(2026, 7, 19, tzinfo=timezone.utc)
    assert dict(manifest.quality_summary) == {
        "cycle_evidence_records": 7,
        "formal_historical_cycles": 1,
        "pseudo_realtime": 1,
        "stale_sources": 2,
    }

    expected_inputs = {
        path.name: sha256_file(path)
        for path in (
            sources.config_dir / "assets.yaml",
            sources.config_dir / "channels.yaml",
            sources.config_dir / "cycles.yaml",
            sources.config_dir / "indicators.yaml",
            sources.evidence_path,
            sources.historical_path,
            sources.realtime_path,
            sources.forecast_path,
            sources.asset_path,
        )
    }
    assert dict(manifest.input_checksums) == expected_inputs
    for filename, checksum in manifest.product_checksums.items():
        assert sha256_file(result.run_dir / filename) == checksum
    assert json.loads((product_root / "latest.json").read_bytes()) == {
        "run_id": result.run_id
    }

    phase_rows = pq.read_table(
        result.run_dir / "cycle_phase_vintage.parquet"
    ).to_pylist()
    assert len(phase_rows) == 252
    assert {row["cycle_id"] for row in phase_rows} == {"C4"}
    assert {row["vintage"] for row in phase_rows} == {"latest_historical"}
    assert phase_rows[0]["date"] == date(2005, 1, 31)
    assert phase_rows[-1]["date"] == date(2025, 12, 31)
    assert phase_rows[0]["slope"] == 0.0
    assert phase_rows[0]["phase"] == "recovery"
    assert {row["vintage_caveat"] for row in phase_rows} == {
        "Two-sided Gaussian and Butterworth historical estimate; "
        "endpoint is not a realtime signal."
    }

    evidence_rows = pq.read_table(result.run_dir / "cycle_evidence.parquet").to_pylist()
    assert [row["cycle_id"] for row in evidence_rows] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert all(
        row["reason_codes_json"]
        == json.dumps(
            json.loads(row["reason_codes_json"]),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for row in evidence_rows
    )

    identities = pq.read_table(result.run_dir / "data_identity.parquet").to_pylist()
    assert [row["entity_id"] for row in identities] == [
        "c4_asset_return_panel",
        "c4_historical_panel",
        "c4_realtime_panel",
    ]
    identity_lookup = {row["entity_id"]: row for row in identities}
    assert identity_lookup["c4_historical_panel"]["freshness_status"] == "fresh"
    assert identity_lookup["c4_realtime_panel"]["freshness_status"] == "stale"
    asset_identity = identity_lookup["c4_asset_return_panel"]
    assert asset_identity["source"] == (
        "output/c4_asset_statistics_prototype_2026-07-19.json"
    )
    assert asset_identity["observation_start"] == date(2005, 12, 31)
    assert asset_identity["source_data_as_of"] == date(2024, 10, 31)
    assert asset_identity["vintage_kind"] == "latest_historical"
    assert asset_identity["freshness_status"] == "stale"
    assert asset_identity["stale_months"] == 21
    assert asset_identity["caveat"] == (
        "Gold, copper and crude oil direct sources are unavailable."
    )
    assert {row["retrieval_time"] for row in identities} == {
        datetime(2026, 7, 19, tzinfo=timezone.utc)
    }

    gates = pq.read_table(result.run_dir / "publication_gate.parquet").to_pylist()
    assert len(gates) == 28
    lookup = {(row["cycle_id"], row["layer"]): row for row in gates}
    assert lookup[("C4", "historical")]["status"] == "formal"
    assert lookup[("C4", "realtime")]["status"] == "limited"
    assert lookup[("C4", "forecast")]["status"] == "limited"
    assert lookup[("C4", "asset_statistics")]["status"] == "formal"
    assert lookup[("C6", "historical")]["status"] == "calendar_only"
    assert lookup[("C6", "forecast")]["status"] == "calendar_only"
    assert lookup[("C5", "asset_statistics")]["status"] == "blocked"
    assert {
        lookup[(cycle_id, layer)]["status"]
        for cycle_id in ("C2", "C3", "C5", "C7")
        for layer in ("historical", "realtime", "forecast", "asset_statistics")
    } == {"blocked"}
    assert lookup[("C4", "realtime")]["reason_codes_json"] == '["pseudo_vintage"]'
    assert lookup[("C4", "forecast")]["reason_codes_json"] == '["stale_input"]'
    assert lookup[("C6", "historical")]["reason_codes_json"] == (
        '["configured_policy"]'
    )
    assert lookup[("C6", "forecast")]["reason_codes_json"] == ('["configured_policy"]')

    calibration_rows = pq.read_table(
        result.run_dir / "calibration_log.parquet"
    ).to_pylist()
    assert [
        (row["subject_id"], row["version"], row["status"]) for row in calibration_rows
    ] == [
        ("C1", "v3", "scenario_only"),
        ("C2/C3", "v2", "blocked"),
        ("C4", "v4", "formal"),
        ("C4-forecast", "v1", "limited"),
        ("C4-realtime", "v1", "limited"),
        ("C5/C7", "v2", "blocked"),
    ]


def test_foundation_run_is_immutable(tmp_path: Path) -> None:
    product_root = tmp_path / "products"
    result = build_research_foundation(
        sources=_sources(),
        product_root=product_root,
        as_of=date(2026, 7, 19),
    )
    manifest_bytes = (result.run_dir / "manifest.json").read_bytes()
    latest_bytes = (product_root / "latest.json").read_bytes()

    with pytest.raises(FileExistsError, match="immutable"):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert (result.run_dir / "manifest.json").read_bytes() == manifest_bytes
    assert (product_root / "latest.json").read_bytes() == latest_bytes
    assert list((product_root / "staging").iterdir()) == []


def test_foundation_failure_cleans_staging_and_preserves_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_root = tmp_path / "products"
    product_root.mkdir()
    latest_path = product_root / "latest.json"
    prior_latest = b'{"run_id":"prior-foundation-run"}\n'
    latest_path.write_bytes(prior_latest)
    original_write_records = research_foundation.write_records

    def fail_during_governance_write(*args: object, **kwargs: object) -> Path:
        if kwargs.get("filename") == PUBLICATION_GATE_FILENAME:
            raise RuntimeError("publication gate write failed")
        return original_write_records(*args, **kwargs)

    monkeypatch.setattr(
        research_foundation,
        "write_records",
        fail_during_governance_write,
    )

    with pytest.raises(RuntimeError, match="publication gate write failed"):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert latest_path.read_bytes() == prior_latest
    assert list((product_root / "staging").iterdir()) == []
    assert list((product_root / "runs").iterdir()) == []


@pytest.mark.parametrize(
    "source_field",
    ["historical_path", "realtime_path", "forecast_path", "asset_path"],
)
def test_foundation_rejects_same_date_substitute_prototypes_before_staging(
    tmp_path: Path,
    source_field: str,
) -> None:
    sources = _sources()
    approved_path = getattr(sources, source_field)
    substitute_path = tmp_path / approved_path.name
    substitute_path.write_text(
        json.dumps({"meta": {"generated": "2026-07-19"}}),
        encoding="utf-8",
    )
    product_root = tmp_path / "products"

    with pytest.raises(ValueError, match="exact approved path"):
        build_research_foundation(
            sources=replace(sources, **{source_field: substitute_path}),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


@pytest.mark.parametrize(
    "config_filename",
    [
        "assets.yaml",
        "channels.yaml",
        "cycles.yaml",
        "indicators.yaml",
        "evidence_baseline.yaml",
    ],
)
def test_foundation_rejects_substitute_config_sources_before_staging(
    tmp_path: Path,
    config_filename: str,
) -> None:
    substituted_config = tmp_path / "2026-07-19"
    shutil.copytree(
        PROJECT_ROOT / "config" / "seven_cycle" / "approved" / "2026-07-19",
        substituted_config,
    )
    substituted_path = substituted_config / config_filename
    substituted_path.write_text(
        substituted_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    sources = replace(
        _sources(),
        config_dir=substituted_config,
        evidence_path=substituted_config / "evidence_baseline.yaml",
    )
    product_root = tmp_path / "products"

    with pytest.raises(ValueError, match="exact approved path"):
        build_research_foundation(
            sources=sources,
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_rejects_approved_bytes_under_the_wrong_role_filename(
    tmp_path: Path,
) -> None:
    sources = _sources()
    wrong_name = tmp_path / "same-date-history.json"
    shutil.copyfile(sources.historical_path, wrong_name)
    product_root = tmp_path / "products"

    with pytest.raises(ValueError, match="approved filename"):
        build_research_foundation(
            sources=replace(sources, historical_path=wrong_name),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_rejects_identical_bytes_from_an_arbitrary_copy(
    tmp_path: Path,
) -> None:
    sources = _sources()
    copied_path = tmp_path / sources.historical_path.name
    shutil.copyfile(sources.historical_path, copied_path)
    product_root = tmp_path / "products"

    with pytest.raises(ValueError, match="exact approved path"):
        build_research_foundation(
            sources=replace(sources, historical_path=copied_path),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_rejects_source_file_symlinks(tmp_path: Path) -> None:
    sources = _sources()
    symlink_path = tmp_path / sources.historical_path.name
    symlink_path.symlink_to(sources.historical_path)
    product_root = tmp_path / "products"

    with pytest.raises(ValueError, match="must not be a symlink"):
        build_research_foundation(
            sources=replace(sources, historical_path=symlink_path),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_gate_inputs_keep_layer_identities_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []
    original_evaluate_gate = research_foundation.evaluate_gate

    def capture_gate(request):
        captured.append(request)
        return original_evaluate_gate(request)

    monkeypatch.setattr(research_foundation, "evaluate_gate", capture_gate)
    build_research_foundation(
        sources=_sources(),
        product_root=tmp_path / "products",
        as_of=date(2026, 7, 19),
    )

    layer_identities = {
        layer: {
            (request.vintage_kind.value, request.freshness.value)
            for request in captured
            if request.layer == layer
        }
        for layer in (
            "historical",
            "realtime",
            "forecast",
            "asset_statistics",
        )
    }
    assert layer_identities == {
        "historical": {("latest_historical", "fresh")},
        "realtime": {("pseudo_vintage", "stale")},
        "forecast": {("pseudo_vintage", "stale")},
        "asset_statistics": {("latest_historical", "stale")},
    }
    model_qualification = {
        (request.cycle_id, request.layer): request.model_qualified
        for request in captured
    }
    assert model_qualification[("C4", "forecast")] is True
    assert model_qualification[("C6", "forecast")] is None
    assert all(
        qualified is None
        for (cycle_id, layer), qualified in model_qualification.items()
        if layer != "forecast"
    )


def test_foundation_reads_each_actual_approved_source_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = _sources()
    approved_paths = {
        path.resolve()
        for path in (
            sources.config_dir / "assets.yaml",
            sources.config_dir / "channels.yaml",
            sources.config_dir / "cycles.yaml",
            sources.config_dir / "indicators.yaml",
            sources.evidence_path,
            sources.historical_path,
            sources.realtime_path,
            sources.forecast_path,
            sources.asset_path,
        )
    }
    read_counts = {path: 0 for path in approved_paths}
    original_read_bytes = Path.read_bytes

    def count_source_reads(path: Path) -> bytes:
        resolved = path.resolve()
        if resolved in read_counts:
            read_counts[resolved] += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", count_source_reads)
    build_research_foundation(
        sources=sources,
        product_root=tmp_path / "products",
        as_of=date(2026, 7, 19),
    )

    assert set(read_counts.values()) == {1}


def test_foundation_wraps_malformed_evidence_snapshot_with_source_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _replace_snapshot_content(
        monkeypatch,
        role="evidence_baseline",
        content=(
            b"generated: 2026-07-19\n"
            b"source_document: malformed-review-input\n"
            b"cycles: []\n"
        ),
    )
    product_root = tmp_path / "products"

    with pytest.raises(
        ValueError,
        match=r"evidence_baseline \(evidence_baseline.yaml\).*validation failed",
    ):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_wraps_malformed_registry_snapshot_with_source_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _replace_snapshot_content(
        monkeypatch,
        role="cycle_registry",
        content=b"cycles: []\n",
    )
    product_root = tmp_path / "products"

    with pytest.raises(
        ValueError,
        match=r"cycle_registry \(cycles.yaml\).*validation failed",
    ):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_wraps_missing_historical_fields_with_source_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _replace_snapshot_content(
        monkeypatch,
        role="historical_prototype",
        content=json.dumps(
            {
                "meta": {"generated": "2026-07-19"},
                "C4": {"cycle": [{"date": "2005-01"}]},
            }
        ).encode("utf-8"),
    )
    product_root = tmp_path / "products"

    with pytest.raises(
        ValueError,
        match=(
            r"historical_prototype "
            r"\(c4_c5_phase_display_prototype_2026-07-19.json\).*factor"
        ),
    ):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()


def test_foundation_rejects_empty_direct_asset_rows_with_source_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable_assets = [
        {
            "asset_id": asset_id,
            "data_identity": "configured_source_unavailable",
            "start": None,
            "end": None,
        }
        for asset_id in ("商品||黄金", "商品||铜", "商品||原油")
    ]
    _replace_snapshot_content(
        monkeypatch,
        role="asset_prototype",
        content=json.dumps(
            {
                "meta": {
                    "generated": "2026-07-19",
                    "cycle": "C4 inventory cycle",
                    "return_source": "malformed-review-input",
                    "missing_rule": "no synthetic return history",
                },
                "summary": {
                    "total_rows": 3,
                    "observed_assets": 0,
                    "unavailable_assets": 3,
                },
                "assets": unavailable_assets,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    product_root = tmp_path / "products"

    with pytest.raises(
        ValueError,
        match=(
            r"asset_prototype "
            r"\(c4_asset_statistics_prototype_2026-07-19.json\).*no direct asset"
        ),
    ):
        build_research_foundation(
            sources=_sources(),
            product_root=product_root,
            as_of=date(2026, 7, 19),
        )

    assert not product_root.exists()
