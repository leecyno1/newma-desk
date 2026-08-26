"""Attach historical stability diagnostics to published cycle contributions."""

from __future__ import annotations

import json

import pandas as pd

from research_asset_cycle_state_forecast import (
    ASYNCHRONOUS_CLOCK,
    OUTPUT_PATH,
    RETURNS_PATH,
    attach_cycle_attribution_stability,
    build_feature_frame,
)


def main() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    summary = attach_cycle_attribution_stability(
        payload["assets"],
        features=build_feature_frame(ASYNCHRONOUS_CLOCK),
        returns=returns,
    )
    payload["meta"]["attributionStability"] = summary
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
