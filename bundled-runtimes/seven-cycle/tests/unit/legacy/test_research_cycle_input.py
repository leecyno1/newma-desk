from __future__ import annotations

from datetime import date
from dataclasses import replace
import json
from pathlib import Path
import runpy
import shutil

import pandas as pd
import pytest

from seven_cycle_platform import cli
from seven_cycle_platform.legacy.research_cycle_input import (
    ResearchCycleInputRequest,
    build_research_cycle_pipeline_input,
)
from seven_cycle_platform.types import VintageKind
from seven_cycle_platform.pipeline.cycles import load_cycle_pipeline_input


REGISTRY_DIR = Path(__file__).resolve().parents[3] / "config/seven_cycle"


def _write_inputs(root: Path) -> ResearchCycleInputRequest:
    annual = pd.DataFrame(
        {
            "GDP_SERIES": [1.0, 2.0, 3.0, 4.0],
            "CPI_SERIES": [2.0, 2.5, 3.0, 3.5],
        },
        index=pd.Index([2020, 2021, 2022, 2023], name="year"),
    )
    monthly = pd.DataFrame(
        {
            "PMI_SERIES": [49.0, 50.0, 51.0],
            "EQUITY_SERIES": [100.0, 101.0, 102.0],
        },
        index=pd.DatetimeIndex(
            ["2023-01-31", "2023-02-27", "2023-02-28"]
        ),
    )
    annual_path = root / "annual.parquet"
    monthly_path = root / "monthly.parquet"
    annual.to_parquet(annual_path)
    monthly.to_parquet(monthly_path)
    annual_selection = pd.DataFrame(
        [
            {
                "column": "GDP_SERIES",
                "coverage_pct": 100.0,
                "status": "selected",
                "source": "historical",
                "value_type": "level",
            },
            {
                "column": "CPI_SERIES",
                "coverage_pct": 100.0,
                "status": "selected",
                "source": "historical",
                "value_type": "rate_yoy",
            },
        ]
    )
    monthly_selection = pd.DataFrame(
        [
            {
                "panel_main_column": "PMI_SERIES",
                "coverage_pct": 100.0,
                "status": "selected",
                "primary_source": "official",
                "value_type": "rate_level",
                "universe_category": "宏观增长类（Macro Growth）",
            },
            {
                "panel_main_column": "EQUITY_SERIES",
                "coverage_pct": 100.0,
                "status": "selected",
                "primary_source": "exchange",
                "value_type": "level",
                "universe_category": "股票市场与估值（Equity Market & Valuation）",
            },
        ]
    )
    annual_selection_path = root / "annual_selection.csv"
    monthly_selection_path = root / "monthly_selection.csv"
    annual_selection.to_csv(annual_selection_path, index=False)
    monthly_selection.to_csv(monthly_selection_path, index=False)
    return ResearchCycleInputRequest(
        annual_panel_path=annual_path,
        annual_selection_path=annual_selection_path,
        monthly_panel_path=monthly_path,
        monthly_selection_path=monthly_selection_path,
        as_of=date(2024, 3, 31),
        state_start=date(2023, 1, 31),
        state_end=date(2023, 2, 28),
        verification_cutoffs=(date(2023, 1, 31), date(2023, 2, 28)),
        max_members_per_category=2,
    )


def test_build_research_input_normalizes_months_and_marks_pseudo_vintage(
    tmp_path: Path,
) -> None:
    pipeline_input = build_research_cycle_pipeline_input(_write_inputs(tmp_path))

    assert pipeline_input.state_dates == (
        date(2023, 1, 31),
        date(2023, 2, 28),
    )
    monthly_records = [
        row
        for row in pipeline_input.observations
        if row.entity_id in pipeline_input.monthly_categories
    ]
    assert {(row.entity_id, row.observation_date) for row in monthly_records} == {
        ("EQUITY_SERIES", date(2023, 1, 31)),
        ("EQUITY_SERIES", date(2023, 2, 28)),
        ("PMI_SERIES", date(2023, 1, 31)),
        ("PMI_SERIES", date(2023, 2, 28)),
    }
    assert all(row.vintage_kind is VintageKind.PSEUDO_VINTAGE for row in monthly_records)
    assert pipeline_input.monthly_categories == {
        "EQUITY_SERIES": "market",
        "PMI_SERIES": "growth",
    }


def test_build_research_input_creates_current_governed_versions(
    tmp_path: Path,
) -> None:
    pipeline_input = build_research_cycle_pipeline_input(_write_inputs(tmp_path))

    assert [version.cycle_id for version in pipeline_input.prior_model_versions] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert {version.effective_date for version in pipeline_input.prior_model_versions} == {
        date(2024, 3, 31)
    }
    assert pipeline_input.annual_categories == {
        "CPI_SERIES": "prices",
        "GDP_SERIES": "growth",
    }


def _cli_input_root(root: Path) -> Path:
    root.mkdir()
    request = _write_inputs(root)
    (root / "data").mkdir()
    (root / "output").mkdir()
    for source, target in (
        (request.annual_panel_path, "data/research_input_annual_long.parquet"),
        (request.monthly_panel_path, "data/research_input_monthly_macro.parquet"),
        (request.annual_selection_path, "output/research_input_annual_long_selection.csv"),
        (request.monthly_selection_path, "output/research_input_monthly_macro_selection.csv"),
    ):
        source.rename(root / target)
    return root


def _input_cli_args(root: Path, output: Path) -> list[str]:
    return [
        "build-cycle-inputs", "--project-root", str(root),
        "--output-dir", str(output), "--as-of", "2024-03-31",
        "--state-start", "2023-01-31", "--state-end", "2023-02-28",
        "--verification-cutoff", "2023-02-28",
        "--verification-cutoff", "2023-01-31",
        "--verification-cutoff", "2023-02-28",
    ]


def test_cli_builds_from_separate_inputs_and_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    root = _cli_input_root(tmp_path / "research-inputs")
    config = tmp_path / "registry"
    shutil.copytree(REGISTRY_DIR, config)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    args = _input_cli_args(root, Path("result")) + ["--config-dir", str(config)]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    output = unrelated / "result"
    assert Path(result["path"]).parent == output
    assert result["vintage"] == "pseudo_vintage"
    actual = load_cycle_pipeline_input(output)
    assert len(actual.observations) == result["observations"] == 12
    assert actual.state_dates == (date(2023, 1, 31), date(2023, 2, 28))
    assert actual.verification_cutoffs == actual.state_dates
    assert all(row.vintage_kind is VintageKind.PSEUDO_VINTAGE for row in actual.observations)
    assert actual.monthly_categories == {"EQUITY_SERIES": "market", "PMI_SERIES": "growth"}
    assert len(list((root / "output").iterdir())) == 2
    original = Path(result["path"]).read_bytes()
    assert cli.main(args) == 1
    assert "refuse accidental overwrite" in capsys.readouterr().err
    assert Path(result["path"]).read_bytes() == original


def test_input_cli_defaults_root_to_cwd_and_config_to_input_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _cli_input_root(tmp_path / "inputs")
    shutil.copytree(REGISTRY_DIR, root / "config/seven_cycle")
    monkeypatch.chdir(root)
    args = _input_cli_args(root, tmp_path / "results")
    del args[1:3]
    assert cli.main(args) == 0
    assert len(load_cycle_pipeline_input(tmp_path / "results").prior_model_versions) == 7


def test_input_cli_missing_panels_and_invalid_dates_do_not_write(
    tmp_path: Path, capsys,
) -> None:
    output = tmp_path / "results"
    args = _input_cli_args(tmp_path / "missing", output)
    assert cli.main(args) == 1
    assert "research_input_annual_long.parquet" in capsys.readouterr().err
    assert not output.exists()
    args[args.index("--state-end") + 1] = "2025-02-28"
    assert cli.main(args) == 1
    assert "state_end cannot follow as_of" in capsys.readouterr().err
    assert not output.exists()


def test_input_prior_in_first_quarter_uses_previous_year_end(tmp_path: Path) -> None:
    request = replace(_write_inputs(tmp_path), as_of=date(2024, 1, 15))
    result = build_research_cycle_pipeline_input(request)
    assert {version.effective_date for version in result.prior_model_versions} == {
        date(2023, 12, 31)
    }


def test_legacy_script_keeps_default_dates_and_root_relative_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    root = _cli_input_root(tmp_path / "legacy-source")
    shutil.copytree(REGISTRY_DIR, root / "config/seven_cycle")
    script = REGISTRY_DIR.parents[1] / "scripts/build_research_cycle_input_bundle.py"
    legacy_main = runpy.run_path(str(script))["main"]
    monkeypatch.setitem(legacy_main.__globals__, "_project_root", lambda: root)
    monkeypatch.chdir(tmp_path)
    assert legacy_main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["path"]).parent == root / "inputs/seven_cycle"
    actual = load_cycle_pipeline_input(root / "inputs/seven_cycle")
    assert actual.state_dates[0] == date(2020, 11, 30)
    assert actual.state_dates[-1] == date(2025, 10, 31)
    assert actual.verification_cutoffs == (
        date(2021, 12, 31), date(2023, 12, 31), date(2025, 10, 31),
    )
    assert {version.effective_date for version in actual.prior_model_versions} == {
        date(2025, 12, 31)
    }
