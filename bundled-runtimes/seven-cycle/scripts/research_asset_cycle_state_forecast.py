"""Compatibility entry point for the installed asset forecast implementation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
C4_PATH = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
C5_PATH = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"
C7_PATH = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "asset_cycle_state_forecast.json"
SYNCHRONOUS_REFERENCE_PATH = (
    PROJECT_ROOT / "output" / "asset_cycle_state_forecast_synchronous_reference.json"
)


def _implementation():
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import asset_cycle_state_forecast

    return asset_cycle_state_forecast


def __getattr__(name: str):
    return getattr(_implementation(), name)


def _state_paths():
    return {"C4": C4_PATH, "C5": C5_PATH, "C7": C7_PATH}


def build_feature_frame(clock=None):
    implementation = _implementation()
    return implementation.build_feature_frame(
        implementation.ASYNCHRONOUS_CLOCK if clock is None else clock,
        state_paths=_state_paths(),
    )


def build_payload(*, workers: int = 1):
    payload = _implementation().build_payload(
        returns_path=RETURNS_PATH, state_paths=_state_paths(),
        synchronous_reference_path=SYNCHRONOUS_REFERENCE_PATH, workers=workers,
        refresh_reference=os.environ.get("CIRCLE_REFRESH_SYNC_REFERENCE") == "1",
    )
    if "synchronousReference" in payload.get("meta", {}):
        payload["meta"]["synchronousReference"]["path"] = str(
            SYNCHRONOUS_REFERENCE_PATH.relative_to(PROJECT_ROOT)
        )
    return payload


def main() -> None:
    configured_workers = os.environ.get("CIRCLE_FORECAST_WORKERS")
    workers = (
        _implementation().DEFAULT_FORECAST_WORKERS
        if configured_workers is None else max(1, int(configured_workers))
    )
    payload = build_payload(workers=workers)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({"output": str(OUTPUT_PATH), "asOf": payload["meta"]["asOf"],
                      "summary": payload["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
