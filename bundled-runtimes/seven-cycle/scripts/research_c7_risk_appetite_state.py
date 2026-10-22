"""Compatibility entry point for the packaged research implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
PUBLIC_SIGNAL_DIR = PROJECT_ROOT / "data" / "raw" / "web_public"

def _implementation():
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import c7_risk_appetite_state

    return c7_risk_appetite_state


def __getattr__(name: str):
    return getattr(_implementation(), name)


def _monthly_panel():
    return _implementation()._monthly_panel(PANEL_PATH)


def _refresh_public_signals():
    return _implementation()._refresh_public_signals(PUBLIC_SIGNAL_DIR)


def _fred_monthly(series_id, *, aggregation="mean"):
    return _implementation()._fred_monthly(series_id, public_signal_dir=PUBLIC_SIGNAL_DIR, aggregation=aggregation)


def build_risk_appetite_state(panel):
    return _implementation().build_risk_appetite_state(panel, public_signal_dir=PUBLIC_SIGNAL_DIR)


def _validate_broad_asset_direction(families):
    return _implementation()._validate_broad_asset_direction(families, returns_path=RETURNS_PATH)


def validate_asset_direction(families):
    return _implementation().validate_asset_direction(families, returns_path=RETURNS_PATH)


def build_payload():
    return _implementation().build_payload(
        panel_path=PANEL_PATH, returns_path=RETURNS_PATH, public_signal_dir=PUBLIC_SIGNAL_DIR,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-public", action="store_true")
    args = parser.parse_args()
    if args.refresh_public:
        _refresh_public_signals()
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
