"""Compatibility entry point for the packaged research implementation."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
STATE_PATHS = {
    "C5": PROJECT_ROOT / "output" / "c5_liquidity_state_research.json",
    "C7": PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json",
}
OUTPUT_PATH = PROJECT_ROOT / "output" / "c5_c7_asset_association.json"

def _implementation():
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import state_asset_association

    return state_asset_association


def __getattr__(name: str):
    return getattr(_implementation(), name)


def build_payload():
    return _implementation().build_payload(returns_path=RETURNS_PATH, state_paths=STATE_PATHS)


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                cycle_id: mapping["summary"]
                for cycle_id, mapping in payload["cycles"].items()
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
