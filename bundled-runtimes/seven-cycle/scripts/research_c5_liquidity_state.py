"""Compatibility entry point for the packaged research implementation."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"


def _implementation():
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import c5_liquidity_state

    return c5_liquidity_state


def __getattr__(name: str):
    return getattr(_implementation(), name)


def _monthly_panel():
    return _implementation()._monthly_panel(PANEL_PATH)


def validate_asset_direction(families, state):
    return _implementation().validate_asset_direction(families, state, returns_path=RETURNS_PATH)


def build_payload():
    return _implementation().build_payload(panel_path=PANEL_PATH, returns_path=RETURNS_PATH)


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")
    print("status=", payload["status"], "current=", payload["current"])
    for horizon, validation in payload["validation"].items():
        print(
            horizon,
            "accuracy=",
            validation["accuracy"],
            "auc=",
            validation["auc"],
            "qualified=",
            validation["qualified"],
        )
    print("asset=", payload["assetValidation"]["status"])


if __name__ == "__main__":
    main()
