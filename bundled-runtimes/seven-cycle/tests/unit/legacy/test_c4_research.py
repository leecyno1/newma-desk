import json
from pathlib import Path
import runpy

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform import cli


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "inputs"
    output = root / "output"
    output.mkdir(parents=True)
    dates = pd.date_range("2000-01-31", periods=219, freq="ME")
    level = np.sin(np.arange(219) * 2 * np.pi / 42)
    timeline = [{
        "date": day.strftime("%Y-%m"), "observed": float(value),
        "rt_level": float(value), "retro_factor": float(2 * value + 0.1),
        "rt_phase": "recovery", "confirmed_phase": "recovery",
    } for day, value in zip(dates[:216], level[:216], strict=True)]
    realtime = {"meta": {"identity": "synthetic-test-only"}, "timeline": timeline,
                "latest": {"date": timeline[-1]["date"]}}
    historical = {"C4": {"cycle": [{
        "date": row["date"], "factor": row["retro_factor"],
        "phase_angle": (index % 42) / 42 * 360,
    } for index, row in enumerate(timeline[:204])]}}
    for filename, data in [
        ("c4_pseudo_realtime_prototype_2026-07-19.json", realtime),
        ("c4_c5_phase_display_prototype_2026-07-19.json", historical),
    ]:
        (output / filename).write_text(json.dumps(data), encoding="utf-8")
    returns = pd.DataFrame({("商品", "测试资产"): level * 0.01 + 0.001}, index=dates)
    returns.to_parquet(output / "monthly_returns_20y.parquet")
    features = pd.DataFrame({"level": level, "lag1": np.roll(level, 1),
                             "slope3": level - np.roll(level, 3)}, index=dates)
    feature_path = tmp_path / "features.parquet"
    features.to_parquet(feature_path)
    return root, feature_path


def command(root, features, destination):
    return ["build-c4-research", "--project-root", str(root),
            "--features", str(features), "--through", "2018-03-31",
            "--destination", str(destination)]


def test_offline_c4_interface_pairs_validated_bridge_and_statistics(inputs, tmp_path, monkeypatch):
    root, features = inputs
    destination = tmp_path / "prepared"
    monkeypatch.chdir(tmp_path)
    assert cli.main(command(root, features, destination)) == 0
    from seven_cycle_platform.legacy.c4_realtime_bridge import build_bridge
    from seven_cycle_platform.legacy.c4_asset_statistics import build_asset_statistics, build_c4_state

    output = root / "output"
    realtime = json.loads((output / "c4_pseudo_realtime_prototype_2026-07-19.json").read_text())
    historical = json.loads((output / "c4_c5_phase_display_prototype_2026-07-19.json").read_text())
    bridge = json.loads((destination / "c4_realtime_bridge_latest.json").read_text())
    statistics = json.loads((destination / "c4_asset_statistics_current.json").read_text())
    assert bridge == build_bridge(realtime, pd.read_parquet(features), through="2018-03-31")
    assert statistics == build_asset_statistics(
        pd.read_parquet(output / "monthly_returns_20y.parquet"), build_c4_state(historical, bridge))
    assert bridge["latest"]["date"] == "2018-03"
    assert bridge["bridge_validation"]["publishable_bridge"] is True
    assert bridge["latest"]["retro_publishable"] is False
    assert statistics["assets"][0]["end"] == "2018-03"
    assert "not true release vintage" in bridge["meta"]["bridge_data_identity"]
    pd.testing.assert_frame_equal(pd.read_parquet(features),
                                  pd.read_parquet(destination / "c4_bridge_features.parquet"))
    assert not (output / "c4_realtime_bridge_latest.json").exists()


@pytest.mark.parametrize("kind", ["existing", "symlink", "missing-input", "incomplete-features",
                                  "invalid-history", "before-baseline", "blocked-validation"])
def test_failed_c4_build_does_not_publish_or_overwrite(inputs, tmp_path, kind):
    root, features = inputs
    destination = tmp_path / "prepared"
    arguments = command(root, features, destination)
    if kind == "existing":
        destination.mkdir()
        (destination / "keep.txt").write_text("keep")
    elif kind == "symlink":
        destination.symlink_to(tmp_path / "missing", target_is_directory=True)
    elif kind == "missing-input":
        features.unlink()
    elif kind == "incomplete-features":
        pd.read_parquet(features).iloc[:-1].to_parquet(features)
    elif kind == "invalid-history":
        (root / "output/c4_c5_phase_display_prototype_2026-07-19.json").write_text("{}")
    elif kind == "before-baseline":
        arguments[arguments.index("--through") + 1] = "2017-01-31"
    elif kind == "blocked-validation":
        path = root / "output/c4_pseudo_realtime_prototype_2026-07-19.json"
        payload = json.loads(path.read_text())
        payload["timeline"] = payload["timeline"][:24]
        path.write_text(json.dumps(payload))
    assert cli.main(arguments) == 1
    if kind == "existing":
        assert [path.name for path in destination.iterdir()] == ["keep.txt"]
        assert (destination / "keep.txt").read_text() == "keep"
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob(".c4-research-*"))


def test_c4_network_fetch_is_explicit_and_retains_features(inputs, tmp_path, monkeypatch):
    from seven_cycle_platform.legacy import c4_realtime_bridge

    root, features = inputs
    calls = []
    monkeypatch.setattr(c4_realtime_bridge, "fetch_c4_features",
                        lambda: (calls.append(True), pd.read_parquet(features))[1])
    arguments = command(root, features, tmp_path / "prepared")
    feature_index = arguments.index("--features")
    del arguments[feature_index:feature_index + 2]
    assert cli.main(arguments) == 2
    assert calls == []
    assert cli.main([*arguments, "--fetch-features"]) == 0
    assert calls == [True]


@pytest.mark.parametrize("kind", ["statistics", "bridge"])
def test_legacy_c4_exports_reuse_packaged_algorithms(kind):
    root = Path(__file__).resolve().parents[3]
    if kind == "statistics":
        from seven_cycle_platform.legacy import c4_asset_statistics as implementation
        filename, names = "refresh_c4_asset_statistics.py", (
            "build_asset_statistics", "build_c4_state", "_regression_statistics", "_confidence")
    else:
        from seven_cycle_platform.legacy import c4_realtime_bridge as implementation
        filename, names = "update_c4_realtime_bridge.py", ("build_bridge", "fetch_c4_features")
    adapter = runpy.run_path(str(root / "scripts" / filename))
    for name in names:
        exported = adapter[name] if name in adapter else adapter["__getattr__"](name)
        assert exported is getattr(implementation, name)


@pytest.mark.parametrize("kind", ["bridge", "statistics"])
def test_legacy_c4_commands_keep_original_arguments_and_outputs(inputs, tmp_path, monkeypatch, kind):
    from seven_cycle_platform.legacy import c4_realtime_bridge

    root, features = inputs
    destination = tmp_path / "prepared"
    assert cli.main(command(root, features, destination)) == 0
    filename = "update_c4_realtime_bridge.py" if kind == "bridge" else "refresh_c4_asset_statistics.py"
    script_root = Path(__file__).resolve().parents[3]
    adapter = runpy.run_path(str(script_root / "scripts" / filename))
    target = tmp_path / "legacy-result.json"
    for name, path in {
        "DEFAULT_INPUT": root / "output/c4_pseudo_realtime_prototype_2026-07-19.json",
        "DEFAULT_OUTPUT": target, "OUTPUT_PATH": target,
        "RETURNS_PATH": root / "output/monthly_returns_20y.parquet",
        "HISTORICAL_PATH": root / "output/c4_c5_phase_display_prototype_2026-07-19.json",
        "REALTIME_PATH": destination / "c4_realtime_bridge_latest.json",
    }.items():
        monkeypatch.setitem(adapter["main"].__globals__, name, path)
    monkeypatch.setattr(c4_realtime_bridge, "fetch_c4_features", lambda: pd.read_parquet(features))
    monkeypatch.setattr("sys.argv", [filename, "--through", "2018-03"] if kind == "bridge" else [filename])
    adapter["main"]()
    expected = "c4_realtime_bridge_latest.json" if kind == "bridge" else "c4_asset_statistics_current.json"
    assert json.loads(target.read_text()) == json.loads((destination / expected).read_text())
