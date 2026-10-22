from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform import cli
from seven_cycle_platform.cycles import discovery


@pytest.fixture
def research_root(tmp_path: Path) -> Path:
    """Small synthetic panels exercise real discovery, not a published model."""
    root = tmp_path / "research-inputs"
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir()
    for spec in discovery.PANEL_SPECS:
        t = np.arange(180)
        period = 9 if spec.frequency == "A" else 42
        index = (
            pd.Index(range(1800, 1980), name="year")
            if spec.frequency == "A"
            else pd.date_range("2000-01-01", periods=180, freq="MS")
        )
        panel = pd.DataFrame({
            "CPI_TEST": 10 + np.sin(2 * np.pi * t / period),
            "BANK_RATE_TEST": 5 + np.cos(2 * np.pi * t / period),
        }, index=index)
        panel.to_parquet(root / "data" / spec.path.name)
        annual = spec.frequency == "A"
        pd.DataFrame({
            "status": ["selected", "selected"],
            "column" if annual else "panel_main_column": panel.columns,
            "source" if annual else "primary_source": ["synthetic", "synthetic"],
            "value_type": ["rate_level", "rate_level"],
            "family_key": ["prices", "rates"],
            "universe_category": ["prices", "money_credit"],
        }).to_csv(root / "output" / spec.metadata_path.name, index=False)
    return root


def test_cli_discovers_from_external_inputs_into_separate_output(
    research_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    output = tmp_path / "results"
    original_specs = discovery.PANEL_SPECS
    assert cli.main([
        "discover-cycles", "--project-root", str(research_root),
        "--output-dir", str(output),
    ]) == 0
    assert discovery.PANEL_SPECS == original_specs
    assert not list(unrelated.iterdir())
    assert not list((research_root / "output").glob("cycle_discovery_*"))
    profiles = pd.read_csv(output / discovery.OUT_PROFILE.name)
    assert set(profiles["panel"]) == {"annual_long", "monthly_macro"}
    priors = pd.read_csv(output / discovery.OUT_PRIORS.name)
    report = (output / discovery.OUT_REPORT.name).read_text()
    assert len(list(output.iterdir())) == 5
    assert "The 100-month prior is supported" not in report
    for row in priors.to_dict("records"):
        assert f"{row['prior']}: {row['verdict']}" in report
    assert str(discovery.ROOT) not in report
    assert f"`{discovery.OUT_PROFILE.name}`" in report


def test_cli_missing_input_does_not_create_results(tmp_path: Path, capsys) -> None:
    output = tmp_path / "results"
    assert cli.main([
        "discover-cycles", "--project-root", str(tmp_path / "missing"),
        "--output-dir", str(output),
    ]) == 1
    assert "research_input_annual_long.parquet" in capsys.readouterr().err
    assert not output.exists()


def test_cli_default_root_is_working_directory(monkeypatch, tmp_path) -> None:
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(discovery, "main", lambda **kwargs: calls.append(kwargs))
    assert cli.main(["discover-cycles"]) == 0
    assert calls == [{"project_root": tmp_path, "output_dir": None}]


def test_package_entry_defaults_to_cwd_not_install_location(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError) as error:
        discovery.main()
    assert str(tmp_path / "data" / "research_input_annual_long.parquet") in str(error.value)
    assert not (tmp_path / "output").exists()
