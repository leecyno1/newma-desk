"""Create a canonical pseudo-vintage M2 input bundle from real research panels."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=_parse_date, default=date(2025, 12, 31))
    parser.add_argument("--state-start", type=_parse_date, default=date(2020, 11, 30))
    parser.add_argument("--state-end", type=_parse_date, default=date(2025, 10, 31))
    parser.add_argument(
        "--verification-cutoff",
        type=_parse_date,
        action="append",
        dest="verification_cutoffs",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("inputs/seven_cycle"))
    parser.add_argument("--max-members-per-category", type=int, default=5)
    parser.add_argument("--minimum-coverage-pct", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    root = _project_root()
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy.research_cycle_input import (
        ResearchCycleInputRequest,
        build_research_cycle_pipeline_input,
    )
    from seven_cycle_platform.pipeline.cycles import write_cycle_pipeline_input

    arguments = _parser().parse_args(argv)
    cutoffs = tuple(
        sorted(
            set(
                arguments.verification_cutoffs
                or [date(2021, 12, 31), date(2023, 12, 31), arguments.state_end]
            )
        )
    )
    request = ResearchCycleInputRequest(
        annual_panel_path=root / "data/research_input_annual_long.parquet",
        annual_selection_path=root / "output/research_input_annual_long_selection.csv",
        monthly_panel_path=root / "data/research_input_monthly_macro.parquet",
        monthly_selection_path=root / "output/research_input_monthly_macro_selection.csv",
        config_dir=root / "config/seven_cycle",
        as_of=arguments.as_of,
        state_start=arguments.state_start,
        state_end=arguments.state_end,
        verification_cutoffs=cutoffs,
        max_members_per_category=arguments.max_members_per_category,
        minimum_coverage_pct=arguments.minimum_coverage_pct,
    )
    pipeline_input = build_research_cycle_pipeline_input(request)
    output_dir = arguments.output_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    path = write_cycle_pipeline_input(output_dir, pipeline_input)
    print(
        json.dumps(
            {
                "annual_members": len(pipeline_input.annual_categories),
                "monthly_members": len(pipeline_input.monthly_categories),
                "observations": len(pipeline_input.observations),
                "path": str(path),
                "state_dates": len(pipeline_input.state_dates),
                "vintage": "pseudo_vintage",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
