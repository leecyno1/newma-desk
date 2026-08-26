from datetime import datetime, timedelta

import pandas as pd

from instock.core.analysis_snapshot import AnalysisSnapshotRegistry, build_analysis_snapshot


def _frame(size=30):
    frame = pd.DataFrame([
        {
            "date": datetime(2026, 7, 1) + timedelta(days=index),
            "open": 10 + index,
            "high": 11 + index,
            "low": 9 + index,
            "close": 10.5 + index,
            "volume": 1000 + index,
            "amount": 10000 + index,
        }
        for index in range(size)
    ])
    frame.attrs.update({
        "data_endpoint": "/api/market-terminal/ohlcv",
        "adjust": "qfq",
        "as_of_mode": "client_filter",
        "upstream_limit": 800,
        "upstream_has_more": True,
        "upstream_source": "tencent",
        "upstream_as_of": "2026-08-04T08:05:59+00:00",
        "upstream_market": "CN",
        "upstream_timeframe": "1d",
        "replay_limitations": [
            "upstream_no_historical_anchor",
            "latest_800_bars_client_filter",
        ],
    })
    return frame


def test_snapshot_is_traceable_and_stable_for_same_analysis():
    frame = _frame()
    kwargs = {
        "analysis_name": "czsc",
        "analysis_version": "0.10.12",
        "parameters": {"symbol": "300502", "period": "daily", "bars": 30, "asOf": "2026-07-30"},
        "frame": frame,
        "requested_bars": 30,
        "provider_name": "newma-desk",
        "result_summary": {"trend": "up", "score": 80},
    }

    first = build_analysis_snapshot(**kwargs)
    second = build_analysis_snapshot(**kwargs)

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["input"]["digest"] == second["input"]["digest"]
    assert first["result"]["digest"] == second["result"]["digest"]
    assert first["freshness"] == {
        "state": "historical",
        "resolution": "exact",
        "calendar_lag_days": 0,
    }
    assert first["data_window"]["coverage"] == "complete"
    assert first["provenance"]["as_of_mode"] == "client_filter"
    assert first["provenance"]["adjust"] == "qfq"
    assert first["provenance"]["upstream_source"] == "tencent"
    assert first["provenance"]["upstream_as_of"] == "2026-08-04T08:05:59+00:00"
    assert first["provenance"]["market"] == "CN"
    assert first["provenance"]["timeframe"] == "1d"
    assert first["provenance"]["upstream_has_more"] is True
    assert "upstream_no_historical_anchor" in first["provenance"]["limitations"]


def test_snapshot_marks_partial_requested_window():
    snapshot = build_analysis_snapshot(
        analysis_name="czsc",
        analysis_version="0.10.12",
        parameters={"symbol": "300502", "period": "daily", "bars": 120},
        frame=_frame(30),
        requested_bars=120,
        provider_name="newma-desk",
        result_summary={"trend": "sideways"},
    )

    assert snapshot["data_window"]["coverage"] == "partial"
    assert "requested_window_not_fully_covered" in snapshot["provenance"]["limitations"]


def test_snapshot_registry_is_bounded_lru_and_copy_isolated():
    registry = AnalysisSnapshotRegistry(max_entries=2, ttl_seconds=60)
    snapshots = [
        {
            "schema_version": "1.0",
            "snapshot_id": f"czsc:{index:024x}",
            "result": {"summary": {"rank": index}},
        }
        for index in range(3)
    ]
    registry.register(snapshots[0])
    registry.register(snapshots[1])
    first = registry.get(snapshots[0]["snapshot_id"])
    first["result"]["summary"]["rank"] = 99
    registry.register(snapshots[2])

    assert registry.get(snapshots[1]["snapshot_id"]) is None
    assert registry.get(snapshots[0]["snapshot_id"])["result"]["summary"]["rank"] == 0
    assert registry.stats()["entries"] == 2


def test_snapshot_registry_expires_entries_without_wall_clock_dependency():
    now = [100.0]
    registry = AnalysisSnapshotRegistry(
        max_entries=2,
        ttl_seconds=10,
        clock=lambda: now[0],
    )
    snapshot = {
        "schema_version": "1.0",
        "snapshot_id": "czsc:000000000000000000000001",
    }
    registry.register(snapshot)
    now[0] = 109.9
    assert registry.get(snapshot["snapshot_id"]) == snapshot
    now[0] = 120.0
    assert registry.get(snapshot["snapshot_id"]) is None
