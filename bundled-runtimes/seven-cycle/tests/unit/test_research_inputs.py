import json
from types import SimpleNamespace

import pytest

from seven_cycle_platform import cli
from seven_cycle_platform.pipeline.circle_deployment import RESEARCH_DATA_FILENAMES
from seven_cycle_platform.research_inputs import (
    SNAPSHOT_FILENAME, export_research_inputs, load_research_inputs,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    data = root / "web/public/data"
    output = root / "output"
    forecast = {"meta": {"generated": "2026-08-15", "asOf": "2026-07"},
                "assets": [{"id": "oil", "return": 0.05}], "governance": {"publicationStatus": "limited"}}
    statistics = {"meta": {"generated": "2026-07-22"}, "assets": [{"asset_id": "oil", "value": 0}]}
    c4 = {"meta": {"data_as_of": "2026-06"}, "forecast": [{"value": 1}],
          "history": [], "model_summary": {}, "qualified_models": [],
          "phase_windows": [], "eligibility": {"status": "limited"}}
    for name in RESEARCH_DATA_FILENAMES:
        write_json(data / name, {"meta": {"generated": "2026-08-22", "asOf": "2026-07"}})
    write_json(data / "asset-statistics.json", {
        **statistics, "currentCycleForecast": {
            **forecast, "meta": {**forecast["meta"], "layer": "joint_state_forecast",
                                 "includedCycles": ["C4", "C5", "C7"], "separateFromSingleCycleMapping": True},
        },
    })
    write_json(data / "forecast-extension.json", {
        "meta": {**c4["meta"], "build_as_of": "2026-08", "stale_months_at_build": 2},
        **{web: c4[raw] for web, raw in (
            ("forecast", "forecast"), ("history", "history"),
            ("modelSummary", "model_summary"), ("qualifiedModels", "qualified_models"),
            ("phaseWindows", "phase_windows"), ("eligibility", "eligibility"),
        )},
    })
    write_json(output / "asset_cycle_state_forecast.json", forecast)
    write_json(output / "c4_asset_statistics_current.json", statistics)
    write_json(output / "c4_forecast_reproducible_latest.json", c4)
    write_json(output / "private-not-in-snapshot.json", {"private": True})
    return root


def export(source, destination):
    return export_research_inputs(
        web_data_dir=source / "web/public/data", research_output_dir=source / "output",
        c4_forecast_path=source / "output/c4_forecast_reproducible_latest.json",
        destination=destination,
    )


def test_export_relocates_derived_inputs_without_rewriting_dates(source, tmp_path):
    snapshot = export(source, tmp_path / "snapshot")
    moved = tmp_path / "elsewhere" / "snapshot"
    moved.parent.mkdir()
    snapshot.root.rename(moved)
    source.rename(tmp_path / "source-not-available")
    loaded = load_research_inputs(moved)
    web_root = tmp_path / "dist"
    loaded.install_web_data(web_root)
    assert len(list(moved.rglob("*.json"))) == 9
    assert not list(moved.rglob("private*"))
    assert json.loads(loaded.asset_forecast_path.read_text())["meta"]["asOf"] == "2026-07"
    assert (web_root / "data/asset-statistics.json").read_bytes() == (moved / "web-data/asset-statistics.json").read_bytes()
    manifest = json.loads((moved / SNAPSHOT_FILENAME).read_text())
    assert manifest["sourceDates"]["c4_forecast.json"]["data_as_of"] == "2026-06"
    with pytest.raises(FileExistsError):
        export(tmp_path / "source-not-available", moved)


@pytest.mark.parametrize("name,field", [
    ("asset_cycle_state_forecast.json", "assets"),
    ("c4_asset_statistics_current.json", "assets"),
    ("c4_forecast_reproducible_latest.json", "forecast"),
])
def test_export_rejects_same_date_different_results(source, tmp_path, name, field):
    path = source / "output" / name
    value = json.loads(path.read_text())
    value[field] = [{"value": 999}]
    write_json(path, value)
    with pytest.raises(ValueError, match="match"):
        export(source, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_export_missing_inputs_and_load_modified_pair_fail(source, tmp_path):
    snapshot = export(source, tmp_path / "snapshot")
    snapshot.c4_forecast_path.unlink()
    with pytest.raises(FileNotFoundError):
        load_research_inputs(snapshot.root)
    (source / "web/public/data/cycle-research.json").unlink()
    with pytest.raises(FileNotFoundError):
        export(source, tmp_path / "incomplete")
    assert not (tmp_path / "incomplete").exists()


def test_build_rejects_invalid_snapshot_before_publishing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_registry_bundle", lambda _: None)
    def forbidden(**kwargs):
        pytest.fail("invalid snapshot must fail before publishing a foundation")
    monkeypatch.setattr(cli, "_publish_foundation_release", forbidden)
    assert cli.main(["build", "--as-of", "2026-08-22", "--research-bundle-dir", str(tmp_path / "missing")]) == 1
    assert "research input snapshot is invalid" in capsys.readouterr().err
    assert cli.main(["build", "--as-of", "2026-08-22", "--research-bundle-dir", "a", "--research-output-dir", "b"]) == 2


def test_cli_export_and_build_use_the_same_snapshot(source, tmp_path, monkeypatch, capsys):
    import seven_cycle_platform.catalog as catalog
    import seven_cycle_platform.pipeline.circle_deployment as deployment
    destination = tmp_path / "snapshot"
    assert cli.main(["export-research-inputs", "--project-root", str(source), "--destination", str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "exported"
    # Compilation leaves old web data; build must replace it with the snapshot.
    web_root = tmp_path / "dist"
    web_root.mkdir()
    (web_root / "index.html").write_text("<title>test</title>")
    write_json(web_root / "data/asset-statistics.json", {"old": True})
    monkeypatch.setattr(cli, "load_registry_bundle", lambda _: None)
    run = SimpleNamespace(run_id="test-run", run_dir=tmp_path / "run", reused=False)
    monkeypatch.setattr(cli, "_publish_foundation_release", lambda **_: (run, None, False))
    monkeypatch.setattr(cli, "_build_web_distribution", lambda _: web_root)
    def build(**kwargs):
        assert kwargs["asset_forecast_path"] == destination / "research/asset_cycle_state_forecast.json"
        assert kwargs["asset_statistics_path"] == destination / "research/c4_asset_statistics_current.json"
        assert kwargs["c4_forecast_path"] == destination / "research/c4_forecast.json"
        assert (kwargs["web_data_dir"] / "asset-statistics.json").read_bytes() == (destination / "web-data/asset-statistics.json").read_bytes()
        return run
    monkeypatch.setattr(deployment, "build_circle_deployment", build)
    monkeypatch.setattr(cli, "load_manifest", lambda _: None)
    monkeypatch.setattr(catalog, "build_catalog", lambda *a, **kw: SimpleNamespace(path=tmp_path / "catalog", catalog_checksum="test"))
    monkeypatch.setattr(cli, "_write_deployment_manifest", lambda **_: (tmp_path / "deployment", "test"))
    assert cli.main(["build", "--as-of", "2026-08-22", "--research-bundle-dir", str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
