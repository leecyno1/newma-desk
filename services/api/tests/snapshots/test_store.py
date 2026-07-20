import json
import sqlite3
from pathlib import Path

import pytest

from vibe_visualization_api.snapshots.store import (
    SnapshotNotFoundError,
    SnapshotStore,
)


def test_failed_refresh_does_not_replace_last_success(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    first = store.write_success(
        "market-daily",
        {"asOf": "2026-07-18", "breadth": {"up": 3000}},
    )

    store.write_failure("market-daily", "upstream timeout")

    latest = store.latest_success("market-daily")
    assert latest.id == first.id
    assert latest.data["asOf"] == "2026-07-18"


def test_success_write_uses_an_immutable_file_and_atomic_latest_pointer(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path)

    snapshot = store.write_success("market-daily", {"asOf": "2026-07-18"})

    module_dir = tmp_path / "snapshots" / "market-daily"
    pointer = json.loads((module_dir / "latest.json").read_text())
    immutable_path = module_dir / pointer["snapshotFile"]
    assert immutable_path.is_file()
    assert immutable_path.name.endswith(f"-{snapshot.id}.json")
    assert not list(module_dir.glob("*.tmp"))
    assert json.loads(immutable_path.read_text())["data"]["asOf"] == "2026-07-18"


def test_success_history_is_newest_first(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    first = store.write_success("market-daily", {"sequence": 1})
    second = store.write_success("market-daily", {"sequence": 2})

    history = store.list_success("market-daily")

    assert [snapshot.id for snapshot in history] == [second.id, first.id]
    assert store.get_success("market-daily", first.id).data == {"sequence": 1}


def test_missing_or_unsafe_snapshot_is_not_resolved(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)

    with pytest.raises(SnapshotNotFoundError):
        store.latest_success("market-daily")
    with pytest.raises(SnapshotNotFoundError):
        store.get_success("market-daily", "../latest")


def test_refresh_outcomes_are_recorded_in_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    store = SnapshotStore(tmp_path, database_path)

    success = store.write_success("market-daily", {"asOf": "2026-07-18"})
    store.write_failure("market-daily", "upstream timeout")

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT status, snapshot_id, error
            FROM snapshot_refresh_events
            WHERE module_id = ?
            ORDER BY id
            """,
            ("market-daily",),
        ).fetchall()

    assert rows == [
        ("success", success.id, None),
        ("failed", None, "upstream timeout"),
    ]
