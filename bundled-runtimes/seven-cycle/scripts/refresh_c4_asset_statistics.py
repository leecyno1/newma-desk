"""Compatibility entry point for the packaged C4 research implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
HISTORICAL_PATH = (
    PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
)
REALTIME_PATH = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c4_asset_statistics_current.json"


def __getattr__(name: str):
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import c4_asset_statistics

    return getattr(c4_asset_statistics, name)


def main() -> None:
    build_asset_statistics = __getattr__("build_asset_statistics")
    build_c4_state = __getattr__("build_c4_state")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    historical = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))
    realtime = json.loads(REALTIME_PATH.read_text(encoding="utf-8"))
    payload = build_asset_statistics(returns, build_c4_state(historical, realtime))
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
