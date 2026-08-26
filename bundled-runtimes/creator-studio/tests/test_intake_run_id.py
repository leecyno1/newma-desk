from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_stage1_intake import parse_args  # noqa: E402


def test_intake_accepts_canonical_run_id() -> None:
    args = parse_args(["--run-id", "2026-08-03_194542_intake"])
    assert args.run_id == "2026-08-03_194542_intake"


def test_intake_rejects_path_like_run_id() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--run-id", "../outside"])
