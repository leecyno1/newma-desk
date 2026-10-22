import json
from pathlib import Path
import runpy

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform import cli
from seven_cycle_platform.legacy import c5_liquidity_state, c7_risk_appetite_state


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir()
    public = tmp_path / "fred"
    public.mkdir()
    dates = pd.date_range("2000-01-31", periods=120, freq="ME")
    pd.DataFrame({"fixture": range(120)}, index=dates).to_parquet(root / "data/indicator_panel_monthly.parquet")
    pd.DataFrame({("商品", "测试资产"): np.sin(np.arange(120)) * 0.01}, index=dates).to_parquet(
        root / "output/monthly_returns_20y.parquet")
    for series in c7_risk_appetite_state.FRED_SIGNAL_IDS:
        pd.DataFrame({"observation_date": dates, series: np.arange(120) * 0.1}).to_csv(
            public / f"fred_{series}.csv", index=False)
    calls = []

    def build(cycle, **kwargs):
        calls.append((cycle, kwargs))
        if cycle == "C7":
            for series in c7_risk_appetite_state.FRED_SIGNAL_IDS:
                c7_risk_appetite_state._fred_monthly(series, public_signal_dir=kwargs["public_signal_dir"])
        state = np.sin(np.arange(120) / 7)
        return {
            "current": {"date": "2009-12", "level": float(state[-1])},
            "status": "research_only", "publicationStatus": "limited",
            "governance": {"formalCycleStatus": "blocked", "assetForecastStatus": "blocked"},
            "assetValidation": {"status": "blocked"},
            "validation": {"3m": {"qualified": False}},
            "pathValidation": {"1m": {"qualified": False}},
            "timeline": [{"date": day.strftime("%Y-%m"), "state": float(value),
                          "slope3": float(np.cos(index / 7))}
                         for index, (day, value) in enumerate(zip(dates, state, strict=True))],
        }

    monkeypatch.setattr(c5_liquidity_state, "build_payload", lambda **kwargs: build("C5", **kwargs))
    monkeypatch.setattr(c7_risk_appetite_state, "build_payload", lambda **kwargs: build("C7", **kwargs))
    return root, public, calls


def command(root, public, destination):
    return ["build-state-research", "--project-root", str(root),
            "--public-signal-dir", str(public), "--destination", str(destination)]


def test_installed_state_interface_keeps_inputs_outputs_and_gates_separate(inputs, tmp_path, monkeypatch):
    root, public, calls = inputs
    destination = tmp_path / "prepared"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(c7_risk_appetite_state, "_refresh_public_signals",
                        lambda *_: pytest.fail("offline build must not fetch"))
    assert cli.main(command(root, public, destination)) == 0
    assert [cycle for cycle, _ in calls] == ["C5", "C7"]
    assert calls[0][1] == {"panel_path": root / "data/indicator_panel_monthly.parquet",
                           "returns_path": root / "output/monthly_returns_20y.parquet"}
    for series in c7_risk_appetite_state.FRED_SIGNAL_IDS:
        assert (destination / "public-signals" / f"fred_{series}.csv").read_bytes() == (
            public / f"fred_{series}.csv").read_bytes()
    assert not str(calls[1][1]["public_signal_dir"]).startswith(str(public))
    mapping = json.loads((destination / "c5_c7_asset_association.json").read_text())
    assert mapping["meta"]["notAssetForecast"] is True
    for cycle in ("C5", "C7"):
        payload = json.loads((destination / f"{cycle.lower()}_{'liquidity' if cycle == 'C5' else 'risk_appetite'}_state_research.json").read_text())
        assert payload["governance"]["formalCycleStatus"] == "blocked"
        assert mapping["cycles"][cycle]["currentState"]["assetForecastStatus"] == "blocked"
        assert len(mapping["cycles"][cycle]["assets"]) == 1
    assert list((root / "output").iterdir()) == [root / "output/monthly_returns_20y.parquet"]


@pytest.mark.parametrize("failure", ["existing", "symlink", "missing-panel", "missing-fred", "bad-fred", "model"])
def test_state_failure_never_publishes_half_a_pair(inputs, tmp_path, monkeypatch, failure):
    root, public, calls = inputs
    destination = tmp_path / "prepared"
    if failure == "existing":
        destination.mkdir()
        (destination / "keep.txt").write_text("keep")
    elif failure == "symlink":
        destination.symlink_to(tmp_path / "missing", target_is_directory=True)
    elif failure == "missing-panel":
        (root / "data/indicator_panel_monthly.parquet").unlink()
    elif failure == "missing-fred":
        (public / "fred_NFCI.csv").unlink()
    elif failure == "bad-fred":
        (public / "fred_NFCI.csv").write_text("wrong\n1\n")
    else:
        def failed_model(**_):
            raise RuntimeError("C7 computation failed")
        monkeypatch.setattr(c7_risk_appetite_state, "build_payload", failed_model)
    assert cli.main(command(root, public, destination)) == 1
    if failure == "existing":
        assert [path.name for path in destination.iterdir()] == ["keep.txt"]
        assert (destination / "keep.txt").read_text() == "keep"
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob(".state-research-*"))
    if failure in {"existing", "symlink", "missing-panel", "missing-fred"}:
        assert not calls


def test_state_public_refresh_is_explicit_and_uses_only_staging(inputs, tmp_path, monkeypatch):
    root, public, _ = inputs
    fetched = []

    def fetch(destination):
        fetched.append(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for path in public.iterdir():
            (destination / path.name).write_bytes(path.read_bytes())

    monkeypatch.setattr(c7_risk_appetite_state, "_refresh_public_signals", fetch)
    destination = tmp_path / "prepared"
    assert cli.main(["build-state-research", "--project-root", str(root),
                     "--refresh-public", "--destination", str(destination)]) == 0
    assert len(fetched) == 1
    assert fetched[0].name == "public-signals"
    assert not (root / "data/raw").exists()


@pytest.mark.parametrize("kind", ["c5", "c7", "association"])
def test_legacy_state_builders_pass_original_paths_to_packaged_models(tmp_path, monkeypatch, kind):
    from seven_cycle_platform.legacy import state_asset_association

    filename, implementation = {
        "c5": ("research_c5_liquidity_state.py", c5_liquidity_state),
        "c7": ("research_c7_risk_appetite_state.py", c7_risk_appetite_state),
        "association": ("research_c5_c7_asset_association.py", state_asset_association),
    }[kind]
    script = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts" / filename))
    captured = []
    monkeypatch.setattr(implementation, "build_payload", lambda **kwargs: (captured.append(kwargs), {"ok": True})[1])
    for name in ("PANEL_PATH", "RETURNS_PATH", "PUBLIC_SIGNAL_DIR", "STATE_PATHS"):
        if name in script:
            value = {"C5": tmp_path / "c5.json", "C7": tmp_path / "c7.json"} if name == "STATE_PATHS" else tmp_path / name
            monkeypatch.setitem(script["build_payload"].__globals__, name, value)
    assert script["build_payload"]() == {"ok": True}
    expected_keys = {"returns_path", "state_paths"} if kind == "association" else {"panel_path", "returns_path"}
    if kind == "c7":
        expected_keys.add("public_signal_dir")
    assert set(captured[0]) == expected_keys
    assert all(str(value).startswith(str(tmp_path)) for key, value in captured[0].items() if key != "state_paths")
