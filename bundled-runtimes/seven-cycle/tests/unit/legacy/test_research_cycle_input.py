from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from seven_cycle_platform.legacy.research_cycle_input import (
    ResearchCycleInputRequest,
    build_research_cycle_pipeline_input,
)
from seven_cycle_platform.types import VintageKind


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
