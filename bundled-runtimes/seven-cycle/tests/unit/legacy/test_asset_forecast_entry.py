import json
from pathlib import Path
import runpy

import pandas as pd
import pytest

from seven_cycle_platform import cli


@pytest.fixture
def inputs(tmp_path):
    output = tmp_path / "raw/output"
    output.mkdir(parents=True)
    dates = pd.date_range("2023-01-31", periods=6, freq="ME")
    pd.DataFrame({("商品", "测试资产"): [0.01] * 6}, index=dates).to_parquet(
        output / "monthly_returns_20y.parquet")
    for cycle, filename in (("C4", "c4_realtime_bridge_latest.json"),
                            ("C5", "c5_liquidity_state_research.json"),
                            ("C7", "c7_risk_appetite_state_research.json")):
        timeline = [{"date": day.strftime("%Y-%m"),
                     "rt_level": index, "state": index, "slope3": index / 3}
                    for index, day in enumerate(dates)]
        (output / filename).write_text(json.dumps({"timeline": timeline}), encoding="utf-8")
    return output.parent


def command(root, destination):
    return ["build-asset-forecast", "--project-root", str(root),
            "--destination", str(destination), "--workers", "1"]


def test_forecast_features_use_explicit_input_states(inputs, tmp_path, monkeypatch):
    from seven_cycle_platform.legacy import asset_cycle_state_forecast as forecast

    monkeypatch.chdir(tmp_path)
    states = {cycle: inputs / "output" / filename for cycle, filename in (
        ("C4", "c4_realtime_bridge_latest.json"),
        ("C5", "c5_liquidity_state_research.json"),
        ("C7", "c7_risk_appetite_state_research.json"))}
    asynchronous = forecast.build_feature_frame(forecast.ASYNCHRONOUS_CLOCK, state_paths=states)
    synchronous = forecast.build_feature_frame(forecast.SYNCHRONOUS_CLOCK, state_paths=states)
    assert asynchronous.index[-1].strftime("%Y-%m") == "2023-06"
    assert asynchronous.iloc[-1]["c4_level"] == 4
    assert asynchronous.iloc[-1]["c7_state"] == 5
    assert synchronous.iloc[-1]["c4_level"] == 5


def test_forecast_cli_publishes_paired_output_without_changing_inputs(inputs, tmp_path, monkeypatch, capsys):
    from seven_cycle_platform.legacy import asset_cycle_state_forecast as forecast

    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        kwargs["synchronous_reference_path"].write_text('{"assets": []}', encoding="utf-8")
        return {"meta": {"asOf": "2023-06"}, "summary": {"assets": 1},
                "governance": {"publicationStatus": "limited"}, "assets": []}
    monkeypatch.setattr(forecast, "build_payload", build)
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "prepared"
    assert cli.main(command(inputs, destination)) == 0
    assert calls[0]["returns_path"] == inputs / "output/monthly_returns_20y.parquet"
    assert set(calls[0]["state_paths"]) == {"C4", "C5", "C7"}
    assert calls[0]["workers"] == 1
    assert not (inputs / "output/asset_cycle_state_forecast.json").exists()
    result = json.loads((destination / "asset_cycle_state_forecast.json").read_text())
    assert result["governance"]["publicationStatus"] == "limited"
    assert (destination / "asset_cycle_state_forecast_synchronous_reference.json").is_file()
    assert json.loads(capsys.readouterr().out)["status"] == "prepared"
    assert cli.main(command(inputs, destination)) == 1
    assert len(calls) == 1


def test_forecast_failure_does_not_publish_half_a_pair(inputs, tmp_path, monkeypatch):
    from seven_cycle_platform.legacy import asset_cycle_state_forecast as forecast

    def fail(**kwargs):
        kwargs["synchronous_reference_path"].write_text("partial", encoding="utf-8")
        raise ValueError("invalid state input")
    monkeypatch.setattr(forecast, "build_payload", fail)
    destination = tmp_path / "prepared"
    assert cli.main(command(inputs, destination)) == 1
    assert not destination.exists()
    assert not list(tmp_path.glob(".asset-forecast-*"))


def test_forecast_missing_inputs_or_invalid_workers_fail_before_calculation(inputs, tmp_path, monkeypatch):
    from seven_cycle_platform.legacy import asset_cycle_state_forecast as forecast

    monkeypatch.setattr(forecast, "build_payload", lambda **_: pytest.fail("must not calculate"))
    destination = tmp_path / "prepared"
    assert cli.main(command(inputs, destination)[:-1] + ["0"]) == 1
    (inputs / "output/c7_risk_appetite_state_research.json").unlink()
    assert cli.main(command(inputs, destination)) == 1
    assert not destination.exists()


def test_old_forecast_script_preserves_source_paths(inputs, monkeypatch):
    from seven_cycle_platform.legacy import asset_cycle_state_forecast as forecast

    script = Path(__file__).resolve().parents[3] / "scripts/research_asset_cycle_state_forecast.py"
    adapter = runpy.run_path(str(script))
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return {"meta": {"synchronousReference": {"path": "reference.json"}}}
    monkeypatch.setattr(forecast, "build_payload", build)
    result = adapter["build_payload"](workers=2)
    assert calls[0]["workers"] == 2
    assert calls[0]["returns_path"] == script.parent.parent / "output/monthly_returns_20y.parquet"
    assert calls[0]["state_paths"]["C4"] == script.parent.parent / "output/c4_realtime_bridge_latest.json"
    assert result["meta"]["synchronousReference"]["path"] == (
        "output/asset_cycle_state_forecast_synchronous_reference.json")
