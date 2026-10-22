from pathlib import Path
import runpy

import pandas as pd
import pytest

from seven_cycle_platform import cli


def write_raw_panels(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir()
    annual = pd.DataFrame({
        "WB_GDP": range(110), "WB_GDP_EXT_WB": range(110),
        "UK_CPI_YOY_PCT": range(110), "UK_CPI_RET": range(110),
        "SHORT": [1.0] * 5 + [None] * 105,
    }, index=range(1900, 2010))
    annual.to_parquet(root / "data/indicator_panel_annual_very_long_history_year.parquet")
    dates = pd.date_range("2000-01-31", periods=96, freq="ME")
    monthly = pd.DataFrame({
        "CN_GDP_YOY": range(96), "CN_GDP_LEVEL": range(96),
        "CN_CPI_YOY": [None] + list(range(95)), "CN_GDP_ACCU": range(96),
    }, index=dates)
    monthly.to_parquet(root / "data/indicator_panel_monthly.parquet")
    pd.DataFrame([{
        "id": name, "name": name, "freq": "M",
        "universe_category": category, "primary_source": "synthetic-test",
        "backend": "test", "base_freq": "M", "value_type": value_type,
        "panel_main_column": name,
    } for name, value_type, category in [
        ("CN_GDP_YOY", "rate_yoy", "宏观增长类（Macro Growth）"),
        ("CN_GDP_LEVEL", "level", "宏观增长类（Macro Growth）"),
        ("CN_CPI_YOY", "rate_yoy", "通胀与价格类（Inflation & Prices）"),
        ("CN_GDP_ACCU", "level", "宏观增长类（Macro Growth）"),
    ]]).to_csv(root / "output/cycle_bandpower_scores_monthly.csv", index=False)


def command(root: Path, destination: Path) -> list[str]:
    return ["build-research-panels", "--project-root", str(root),
            "--destination", str(destination), "--annual-start", "1900", "--annual-end", "1999",
            "--monthly-start", "2000-01-31", "--monthly-end", "2005-12-31"]


def test_installed_interface_separates_input_output_and_preserves_selection(tmp_path, monkeypatch):
    source, destination = tmp_path / "raw", tmp_path / "prepared"
    write_raw_panels(source)
    monkeypatch.chdir(tmp_path)
    assert cli.main(command(source, destination)) == 0
    annual = pd.read_parquet(destination / "data/research_input_annual_long.parquet")
    monthly = pd.read_parquet(destination / "data/research_input_monthly_macro.parquet")
    assert set(annual.columns) == {"WB_GDP_EXT_WB", "UK_CPI_YOY_PCT"}
    assert annual.index.min() == 1900 and annual.index.max() == 1999
    assert set(monthly.columns) == {"CN_GDP_YOY", "CN_CPI_YOY"}
    assert monthly.index.max() == pd.Timestamp("2005-12-31")
    assert pd.isna(monthly.iloc[0]["CN_CPI_YOY"])
    selections = pd.read_csv(destination / "output/research_input_monthly_macro_selection.csv")
    assert selections.set_index("panel_main_column").loc["CN_GDP_LEVEL", "status"] == "excluded"
    assert len(list(destination.rglob("*selection.md"))) == 2
    assert not (source / "data/research_input_annual_long.parquet").exists()


def test_existing_destination_is_never_overwritten(tmp_path):
    source, destination = tmp_path / "raw", tmp_path / "existing"
    write_raw_panels(source)
    destination.mkdir()
    (destination / "sentinel.txt").write_text("keep", encoding="utf-8")
    assert cli.main(command(source, destination)) == 1
    assert (destination / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert list(destination.iterdir()) == [destination / "sentinel.txt"]


def test_missing_input_does_not_publish_partial_panels(tmp_path):
    source, destination = tmp_path / "raw", tmp_path / "prepared"
    write_raw_panels(source)
    (source / "data/indicator_panel_monthly.parquet").unlink()
    assert cli.main(command(source, destination)) == 1
    assert not destination.exists()


def test_broken_destination_link_is_not_followed(tmp_path):
    source, destination, target = tmp_path / "raw", tmp_path / "linked", tmp_path / "not-created"
    write_raw_panels(source)
    destination.symlink_to(target, target_is_directory=True)
    assert cli.main(command(source, destination)) == 1
    assert destination.is_symlink()
    assert not target.exists()


@pytest.mark.parametrize("option,value", [("--annual-end", "1800"), ("--monthly-end", "1999-01-31")])
def test_invalid_windows_do_not_publish_outputs(tmp_path, option, value):
    source, destination = tmp_path / "raw", tmp_path / "prepared"
    write_raw_panels(source)
    arguments = command(source, destination)
    arguments[arguments.index(option) + 1] = value
    assert cli.main(arguments) == 1
    assert not destination.exists()


def test_invalid_monthly_metadata_does_not_publish_the_already_built_annual_panel(tmp_path):
    source, destination = tmp_path / "raw", tmp_path / "prepared"
    write_raw_panels(source)
    pd.DataFrame({"wrong": ["metadata"]}).to_csv(source / "output/cycle_bandpower_scores_monthly.csv", index=False)
    assert cli.main(command(source, destination)) == 1
    assert not destination.exists()


@pytest.mark.parametrize("kind", ["annual_long", "monthly_macro"])
def test_legacy_script_calls_the_same_packaged_implementation(tmp_path, monkeypatch, kind):
    root = Path(__file__).resolve().parents[3]
    script = runpy.run_path(str(root / f"scripts/build_research_input_{kind}.py"))
    source, destination = tmp_path / "raw", tmp_path / "prepared"
    write_raw_panels(source)
    args = command(source, destination)
    args[args.index("--annual-start") + 1] = "1700"
    args[args.index("--annual-end") + 1] = "2024"
    args[args.index("--monthly-end") + 1] = "2025-12-31"
    assert cli.main(args) == 0
    monkeypatch.setitem(script["main"].__globals__, "_project_root", lambda: source)
    script["main"]()
    name = f"research_input_{kind}.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(source / "data" / name),
                                  pd.read_parquet(destination / "data" / name))
