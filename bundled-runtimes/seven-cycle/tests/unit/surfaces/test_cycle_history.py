from __future__ import annotations

import pandas as pd

from seven_cycle_platform.surfaces.history import (
    select_current_cycle_snapshot,
    select_preferred_cycle_vintage,
)


def test_preferred_cycle_history_is_order_independent_and_prefers_realtime() -> None:
    rows = pd.DataFrame(
        [
            {"date": "2025-01-31", "cycle_id": "C1", "vintage": "latest_historical", "angle": 210.0},
            {"date": "2025-01-31", "cycle_id": "C1", "vintage": "realtime", "angle": 30.0},
            {"date": "2025-01-31", "cycle_id": "C2", "vintage": "pseudo_vintage", "angle": 240.0},
            {"date": "2025-01-31", "cycle_id": "C2", "vintage": "latest_historical", "angle": 60.0},
        ]
    ).sample(frac=1.0, random_state=7)

    selected = select_preferred_cycle_vintage(rows)

    assert selected[["cycle_id", "vintage", "angle"]].to_dict("records") == [
        {"cycle_id": "C1", "vintage": "realtime", "angle": 30.0},
        {"cycle_id": "C2", "vintage": "latest_historical", "angle": 60.0},
    ]


def test_current_cycle_snapshot_uses_latest_date_then_vintage_priority() -> None:
    rows = pd.DataFrame(
        [
            {"date": "2025-01-31", "cycle_id": "C1", "vintage": "realtime", "angle": 30.0},
            {"date": "2025-02-28", "cycle_id": "C1", "vintage": "latest_historical", "angle": 45.0},
            {"date": "2025-02-28", "cycle_id": "C1", "vintage": "realtime", "angle": 50.0},
            {"date": "2025-02-28", "cycle_id": "C2", "vintage": "pseudo_vintage", "angle": 80.0},
        ]
    )

    current = select_current_cycle_snapshot(rows)

    assert current[["cycle_id", "vintage", "angle"]].to_dict("records") == [
        {"cycle_id": "C1", "vintage": "realtime", "angle": 50.0},
        {"cycle_id": "C2", "vintage": "pseudo_vintage", "angle": 80.0},
    ]
