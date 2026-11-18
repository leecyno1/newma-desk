import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from vibe_visualization_api.global_intel.state import initialize_state, inspect_state
from vibe_visualization_api.global_topics.store import GlobalTopicStore


def test_state_inspection_never_creates_missing_database(tmp_path):
    path = tmp_path / "missing" / "topics.db"
    assert inspect_state(path) == {"status": "missing", "dedicated": None, "counts": {}}
    assert not path.parent.exists()


def test_inspector_distinguishes_dedicated_and_shared_without_adopting_records(tmp_path):
    path = tmp_path / "topics.db"
    store = GlobalTopicStore(path)
    store.save_forecast("hormuz", "original", {}, {}, scope=("private-user", "private-workspace"))
    first = inspect_state(path)
    assert first["status"] == "ready" and first["dedicated"] is True
    assert first["counts"] == {"global_topic_forecasts": 0, "global_topic_scoped_forecasts": 1}
    assert "private" not in str(first)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE desk_private_data (id TEXT)")
    second = inspect_state(path)
    assert second["status"] == "ready" and second["dedicated"] is False
    assert second["counts"] == first["counts"]
    assert store.latest_forecast("hormuz", scope=("private-user", "private-workspace"))["createdAt"] == "original"


def test_incomplete_or_non_sqlite_state_is_not_ready(tmp_path):
    path = tmp_path / "foreign.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE global_topic_forecasts (id INTEGER)")
    report = inspect_state(path)
    assert report["status"] == "incomplete"
    assert len(report["missingTables"]) == 2
    assert report["counts"] == {}
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA table_info(global_topic_forecasts)").fetchall() == [(0, "id", "INTEGER", 0, None, 0)]


def test_initialize_empty_domain_schema_and_keep_legacy_unassigned(tmp_path):
    legacy = tmp_path / "legacy.db"
    old = GlobalTopicStore(legacy)
    old.save_forecast("hormuz", "original", {"oil": 1}, {"risk": "high"})
    target = tmp_path / "new.db"
    initialize_state(target)
    report = inspect_state(target)
    assert report["status"] == "ready" and report["dedicated"] is True
    assert report["counts"] == {"global_topic_forecasts": 0, "global_topic_scoped_forecasts": 0}
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        for table in ("global_topic_events", "global_topic_observations"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    assert target.stat().st_mode & 0o777 == 0o600
    assert old.latest_forecast("hormuz")["createdAt"] == "original"
    assert old.latest_forecast("hormuz", scope=("user", "workspace")) is None
    with pytest.raises(FileExistsError):
        initialize_state(legacy)
    assert old.latest_forecast("hormuz")["result"] == {"risk": "high"}
    assert not list(tmp_path.glob(".global-init-*"))


def test_initialize_requires_absolute_path_existing_parent_and_rejects_symlink(tmp_path):
    with pytest.raises(ValueError):
        initialize_state(Path("relative.db"))
    target = tmp_path / "missing" / "new.db"
    with pytest.raises(FileNotFoundError):
        initialize_state(target)
    assert not target.parent.exists()
    link = tmp_path / "link.db"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        initialize_state(link)
    assert link.is_symlink() and not target.exists()


def test_failed_schema_does_not_publish_partial_database(tmp_path, monkeypatch):
    import vibe_visualization_api.global_topics.store as store
    monkeypatch.setattr(store, "SCHEMA", "CREATE TABLE partial (id INTEGER); INVALID SQL;")
    with pytest.raises(sqlite3.Error):
        initialize_state(tmp_path / "new.db")
    assert list(tmp_path.iterdir()) == []


def test_competing_initializer_never_overwrites_target(tmp_path, monkeypatch):
    import vibe_visualization_api.global_intel.state as state
    original_link = state.os.link
    target = tmp_path / "new.db"

    def competing_link(source, destination):
        GlobalTopicStore(target).save_forecast("hormuz", "other-process", {}, {})
        original_link(source, destination)

    monkeypatch.setattr(state.os, "link", competing_link)
    with pytest.raises(FileExistsError):
        initialize_state(target)
    assert GlobalTopicStore(target).latest_forecast("hormuz")["createdAt"] == "other-process"
    assert not list(tmp_path.glob(".global-init-*"))


@pytest.mark.parametrize("flags", [
    ["--initialize-state"], ["--check-state"], ["--require-existing-state"],
    ["--initialize-state", "--require-existing-state"],
])
def test_state_cli_requires_explicit_path_and_exclusive_mode(tmp_path, monkeypatch, flags):
    from vibe_visualization_api.global_intel import app
    from vibe_visualization_api.global_intel.runtime import Settings
    monkeypatch.setattr(app, "Settings", lambda: Settings(_env_file=None, _env_prefix="TEST_UNUSED_"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["newma-global", *flags])
    with pytest.raises(SystemExit) as error:
        app.main()
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_state_cli_initializes_once_checks_and_preserves_records(tmp_path, monkeypatch, capsys):
    from vibe_visualization_api.global_intel import app
    from vibe_visualization_api.global_intel.runtime import Settings
    target = tmp_path / "new.db"
    monkeypatch.setattr(app, "Settings", lambda: Settings(database_path=target, _env_prefix="TEST_UNUSED_"))
    monkeypatch.setattr(sys, "argv", ["newma-global", "--initialize-state"])
    with pytest.raises(SystemExit) as error:
        app.main()
    assert error.value.code == 0
    assert json.loads(capsys.readouterr().out)["counts"]["global_topic_scoped_forecasts"] == 0
    GlobalTopicStore(target).save_forecast("hormuz", "saved", {}, {}, scope=("user", "workspace"))
    with pytest.raises(SystemExit) as error:
        app.main()
    assert error.value.code == 2
    assert "目标已存在" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["newma-global", "--check-state"])
    with pytest.raises(SystemExit) as error:
        app.main()
    assert error.value.code == 0
    assert json.loads(capsys.readouterr().out)["counts"]["global_topic_scoped_forecasts"] == 1
