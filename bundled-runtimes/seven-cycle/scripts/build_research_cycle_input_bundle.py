"""Create a canonical pseudo-vintage M2 input bundle from real research panels."""

from __future__ import annotations

import argparse
from datetime import date
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
    from seven_cycle_platform.cli import main as cli_main

    arguments = _parser().parse_args(argv)
    cutoffs = tuple(
        sorted(
            set(
                arguments.verification_cutoffs
                or [date(2021, 12, 31), date(2023, 12, 31), arguments.state_end]
            )
        )
    )
    output_dir = arguments.output_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    command = [
        "build-cycle-inputs", "--project-root", str(root),
        "--output-dir", str(output_dir),
        "--as-of", arguments.as_of.isoformat(),
        "--state-start", arguments.state_start.isoformat(),
        "--state-end", arguments.state_end.isoformat(),
        "--max-members-per-category", str(arguments.max_members_per_category),
        "--minimum-coverage-pct", str(arguments.minimum_coverage_pct),
    ]
    for cutoff in cutoffs:
        command.extend(("--verification-cutoff", cutoff.isoformat()))
    return cli_main(command)


if __name__ == "__main__":
    raise SystemExit(main())
