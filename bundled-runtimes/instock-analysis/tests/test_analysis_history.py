from instock.core.analysis_history import AnalysisHistoryRegistry


def payload(snapshot_id="snapshot:one", value=1):
    return {
        "engine": {"name": "fixture"},
        "as_of": "2026-08-13",
        "value": value,
        "snapshot": {
            "snapshot_id": snapshot_id,
            "generated_at": "2026-08-13T10:00:00+08:00",
            "parameters": {"symbol": "300502", "bars": 240},
            "data_window": {"end_date": "2026-08-13"},
        },
    }


def test_refresh_appends_versions_even_when_snapshot_id_is_the_same():
    registry = AnalysisHistoryRegistry(max_entries=10, ttl_seconds=60)

    first = registry.register(module_id="czsc", title="300502 · 缠论", payload=payload(value=1))
    second = registry.register(module_id="czsc", title="300502 · 缠论", payload=payload(value=2))

    records = registry.list("czsc")
    assert [item["history_id"] for item in records] == [
        second["history_id"], first["history_id"],
    ]
    assert records[0]["snapshot_id"] == records[1]["snapshot_id"]
    assert registry.get(first["history_id"])["payload"]["value"] == 1


def test_history_is_module_scoped_and_copy_isolated():
    registry = AnalysisHistoryRegistry(max_entries=10, ttl_seconds=60)
    record = registry.register(module_id="czsc", title="CZSC", payload=payload())
    registry.register(module_id="rotation", title="轮动", payload=payload("snapshot:two"))

    restored = registry.get(record["history_id"])
    restored["payload"]["value"] = 99
    listed = registry.list("czsc")
    listed[0]["title"] = "changed"

    assert len(registry.list("czsc")) == 1
    assert len(registry.list("rotation")) == 1
    assert registry.get(record["history_id"])["payload"]["value"] == 1
    assert registry.list("czsc")[0]["title"] == "CZSC"


def test_history_evicts_by_capacity_and_ttl():
    now = [0.0]
    registry = AnalysisHistoryRegistry(
        max_entries=2, ttl_seconds=10, clock=lambda: now[0]
    )
    first = registry.register(module_id="czsc", title="1", payload=payload("s:1"))
    registry.register(module_id="czsc", title="2", payload=payload("s:2"))
    registry.register(module_id="czsc", title="3", payload=payload("s:3"))

    assert registry.get(first["history_id"]) is None
    assert registry.stats()["entries"] == 2

    now[0] = 10.0
    assert registry.list("czsc") == []
    assert registry.stats()["entries"] == 0


def test_sqlite_history_survives_registry_recreation(tmp_path):
    database = tmp_path / "history.sqlite3"
    first_registry = AnalysisHistoryRegistry(
        max_entries=10, ttl_seconds=60, db_path=str(database)
    )
    record = first_registry.register(
        module_id="czsc", title="CZSC", payload=payload(value=7)
    )

    restarted_registry = AnalysisHistoryRegistry(
        max_entries=10, ttl_seconds=60, db_path=str(database)
    )

    assert restarted_registry.list("czsc")[0]["history_id"] == record["history_id"]
    assert restarted_registry.get(record["history_id"])["payload"]["value"] == 7
    assert restarted_registry.stats() == {
        "storage": "sqlite",
        "volatile": False,
        "cleared_on_restart": False,
        "entries": 1,
        "max_entries": 10,
        "ttl_seconds": 60.0,
        "modules": {"czsc": 1},
    }


def test_sqlite_history_still_respects_ttl_and_capacity(tmp_path):
    now = [100.0]
    registry = AnalysisHistoryRegistry(
        max_entries=2,
        ttl_seconds=10,
        db_path=str(tmp_path / "history.sqlite3"),
        wall_clock=lambda: now[0],
    )
    first = registry.register(module_id="czsc", title="1", payload=payload("s:1"))
    registry.register(module_id="czsc", title="2", payload=payload("s:2"))
    registry.register(module_id="czsc", title="3", payload=payload("s:3"))

    assert registry.get(first["history_id"]) is None
    assert registry.stats()["entries"] == 2

    now[0] = 110.0
    assert registry.list("czsc") == []
