"""Retained research references survive restarts without extending their life."""

import sqlite3

import pytest

from instock.core.analysis_history import AnalysisHistoryRegistry
from instock.core.analysis_snapshot import AnalysisSnapshotRegistry
from test_analysis_scope import workspace


def snapshot(value="saved conclusion"):
    return {"schema_version": "1.0", "snapshot_id": "dossier:original",
            "generated_at": "2026-08-11T10:00:00+08:00",
            "data_window": {"end_date": "2026-08-11", "coverage": "partial"},
            "freshness": {"state": "historical"}, "result": {"summary": {"conclusion": value}}}


@pytest.mark.parametrize("persistent", [False, True])
def test_recovery_keeps_original_result_and_scope_without_renewal(tmp_path, persistent):
    now = [100.0]
    options = dict(ttl_seconds=20, clock=lambda: now[0], wall_clock=lambda: now[0],
                   db_path=str(tmp_path / "history.db") if persistent else None)
    history = AnalysisHistoryRegistry(**options)
    original = snapshot()
    with workspace("alice", "a"):
        record = history.register(module_id="stock-research", title="original", payload={"snapshot": original})
    if persistent:
        history = AnalysisHistoryRegistry(**options)  # Reopen the saved database.
    registry = AnalysisSnapshotRegistry(history_lookup=history.get_snapshot)
    for user, name in [("alice", "b"), ("bob", "a")]:
        with workspace(user, name):
            assert registry.get(original["snapshot_id"]) is None
    assert registry.get(original["snapshot_id"]) is None  # Standalone cannot claim it.
    with workspace("alice", "a"):
        now[0] = 119.0
        recovered = registry.get(original["snapshot_id"])
        assert recovered == original
        recovered["result"]["summary"]["conclusion"] = "edited"
        assert registry.get(original["snapshot_id"]) == original
        assert history.get(record["history_id"])["payload"]["snapshot"] == original
        assert len(history.list("stock-research")) == 1
        assert registry.stats()["entries"] == 0  # No fresh memory TTL after recovery.
        now[0] = 120.0
        assert registry.get(original["snapshot_id"]) is None


def test_recovery_never_claims_ownerless_rows_or_nested_references(tmp_path):
    history = AnalysisHistoryRegistry(db_path=str(tmp_path / "history.db"))
    with workspace("alice", "a"):
        old = history.register(module_id="stock-research", title="legacy", payload={"snapshot": snapshot()})
        with sqlite3.connect(history.db_path) as db:
            db.execute("UPDATE analysis_history SET scope = NULL WHERE history_id = ?", (old["history_id"],))
        history.register(module_id="research-book", title="reference only", payload={"references": [snapshot()]})
        assert history.get_snapshot("dossier:original") is None
    assert history.get_snapshot("dossier:original") is None
    with sqlite3.connect(history.db_path) as db:
        assert db.execute("SELECT count(*) FROM analysis_history WHERE scope IS NULL").fetchone()[0] == 1


def test_capacity_eviction_and_invalid_snapshot_do_not_restore(tmp_path):
    history = AnalysisHistoryRegistry(db_path=str(tmp_path / "history.db"), max_entries=1)
    registry = AnalysisSnapshotRegistry(history_lookup=history.get_snapshot)
    history.register(module_id="stock-research", title="original", payload={"snapshot": snapshot()})
    assert registry.get("dossier:original") == snapshot()
    history.register(module_id="stock-research", title="next", payload={"snapshot": {**snapshot(), "snapshot_id": "next", "schema_version": "unsupported"}})
    assert registry.get("dossier:original") is None
    assert registry.get("next") is None


def test_memory_expiry_falls_back_to_history_not_to_recalculation():
    now = [0.0]
    history = AnalysisHistoryRegistry(clock=lambda: now[0], ttl_seconds=20)
    registry = AnalysisSnapshotRegistry(clock=lambda: now[0], ttl_seconds=5, history_lookup=history.get_snapshot)
    history.register(module_id="stock-research", title="saved", payload={"snapshot": snapshot()})
    registry.register(snapshot())
    now[0] = 5.0
    assert registry.get("dossier:original") == snapshot()
    assert registry.stats()["entries"] == 0
    now[0] = 20.0
    assert registry.get("dossier:original") is None
