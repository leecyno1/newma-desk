from __future__ import annotations

from datetime import datetime
import json
import os
import sys
import threading

import pytest
import requests
from sqlalchemy import Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session as OrmSession, mapped_column, sessionmaker


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class _FakeDb:
    def __init__(self, events: list[str] | None = None):
        self.events = events if events is not None else []
        self.closed = False

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.closed = True


def _chatlog_adapters(sync_runtime, events: list[str], sync_fn):
    persisted: list[dict] = []

    def populate_fallback(_db, _since):
        events.append("fallback")
        return {"message_ids": [1, 2]}

    def run_tool_overlay(_db, _fallback_result, mode):
        events.append(f"overlay:{mode}")

    def refresh_snapshots(_db):
        events.append("snapshot")

    def persist_run(_db, payload):
        events.append("persist")
        persisted.append(dict(payload))

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=sync_fn,
        load_policy=lambda _db: {"max_attempts": 2, "sleep_seconds": 0},
        populate_fallback=populate_fallback,
        run_tool_overlay=run_tool_overlay,
        refresh_snapshots=refresh_snapshots,
        persist_run=persist_run,
    )
    return adapters, persisted


def test_chatlog_run_success_has_stable_orchestration_order():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)

    def sync_from_chatlog(_db, since):
        events.append("sync")
        assert since == datetime(2026, 7, 10, 9, 30)
        return {
            "status": "ok",
            "fetched": 7,
            "inserted": 3,
            "since": since.isoformat(),
            "until": "2026-07-10T10:00:00",
        }

    adapters, persisted = _chatlog_adapters(sync_runtime, events, sync_from_chatlog)

    result = sync_runtime.execute_chatlog_sync_run(
        db,
        since=datetime(2026, 7, 10, 9, 30),
        adapters=adapters,
    )

    assert events == ["sync", "fallback", "overlay:async", "snapshot", "persist", "commit"]
    assert result["status"] == "ok"
    assert result["run_id"].startswith("chatlog-")
    assert result["attempts"] == 1
    assert len(persisted) == 1
    assert persisted[0]["status"] == "ok"
    assert persisted[0]["attempts"] == 1
    assert persisted[0]["fetched"] == 7
    assert persisted[0]["inserted"] == 3


def test_chatlog_run_refreshes_contact_predictions_incrementally_after_commit():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)

    def sync_from_chatlog(_db, since):
        events.append("sync")
        return {
            "status": "ok",
            "fetched": 5,
            "inserted": 2,
            "since": "2026-07-12T08:00:00",
            "until": "2026-07-12T09:00:00",
        }

    adapters, _persisted = _chatlog_adapters(sync_runtime, events, sync_from_chatlog)
    adapters.refresh_contact_predictions = lambda _db, result: (
        events.append(f"predictions:{result['since']}:{result['until']}"),
        {"status": "ok", "inserted": 3, "updated": 0},
    )[1]

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert events == [
        "sync",
        "fallback",
        "overlay:async",
        "snapshot",
        "persist",
        "commit",
        "predictions:2026-07-12T08:00:00:2026-07-12T09:00:00",
    ]
    assert result["contact_prediction_refresh"] == {
        "status": "ok",
        "inserted": 3,
        "updated": 0,
    }


def test_chatlog_run_retries_after_rollback_and_persists_only_success():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)
    calls = {"count": 0}

    def sync_from_chatlog(_db, _since):
        calls["count"] += 1
        events.append(f"sync:{calls['count']}")
        if calls["count"] == 1:
            raise requests.ConnectionError("temporary unavailable")
        return {"status": "ok", "fetched": 2, "inserted": 1}

    adapters, persisted = _chatlog_adapters(sync_runtime, events, sync_from_chatlog)

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert result["status"] == "ok"
    assert result["attempts"] == 2
    assert [item["status"] for item in persisted] == ["ok"]
    assert events[:3] == ["sync:1", "rollback", "sync:2"]
    assert events[-2:] == ["persist", "commit"]


def test_chatlog_run_terminal_error_has_stable_failure_payload_and_record():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)

    def sync_from_chatlog(_db, _since):
        events.append("sync")
        raise ValueError("invalid upstream payload")

    adapters, persisted = _chatlog_adapters(sync_runtime, events, sync_from_chatlog)
    adapters.load_policy = lambda _db: {"max_attempts": 4, "sleep_seconds": 0}

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert result["status"] == "error"
    assert result["error_code"] == "SYNC-CHATLOG-UNKNOWN-001"
    assert result["attempts"] == 1
    assert result["fetched"] == 0
    assert result["inserted"] == 0
    assert persisted[0]["status"] == "error"
    assert persisted[0]["error_code"] == "SYNC-CHATLOG-UNKNOWN-001"
    assert persisted[0]["attempts"] == 1
    assert events == ["sync", "rollback", "persist", "commit"]


def test_chatlog_run_keeps_success_when_one_postprocess_stage_fails():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)
    persisted: list[dict] = []

    def populate_fallback(_db, _since):
        events.append("fallback")
        raise RuntimeError("fallback failed")

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=lambda _db, _since: events.append("sync")
        or {"status": "ok", "fetched": 1, "inserted": 1},
        load_policy=lambda _db: {"max_attempts": 1, "sleep_seconds": 0},
        populate_fallback=populate_fallback,
        run_tool_overlay=lambda _db, _fallback, mode: events.append(f"overlay:{mode}"),
        refresh_snapshots=lambda _db: events.append("snapshot"),
        persist_run=lambda _db, payload: (events.append("persist"), persisted.append(dict(payload))),
    )

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert result["status"] == "ok"
    assert result["postprocess_errors"] == [
        {"stage": "fallback_summary", "error": "fallback failed"}
    ]
    assert persisted[0]["status"] == "ok"
    assert persisted[0]["postprocess_errors"] == result["postprocess_errors"]
    assert events == ["sync", "fallback", "overlay:async", "snapshot", "persist", "commit"]


def test_chatlog_run_isolates_real_sqlite_postprocess_flush_failure():
    import app.services.sync_runtime as sync_runtime

    class _Base(DeclarativeBase):
        pass

    class _MainRecord(_Base):
        __tablename__ = "sync_run_main_records"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(64), unique=True)

    class _StageRecord(_Base):
        __tablename__ = "sync_run_stage_records"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(64), unique=True)

    class _RunState(_Base):
        __tablename__ = "sync_run_states"

        key: Mapped[str] = mapped_column(String(128), primary_key=True)
        value: Mapped[str] = mapped_column(Text)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    _Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()

    def sync_from_chatlog(run_db, _since):
        run_db.add(_MainRecord(name="main-sync-ok"))
        return {"status": "ok", "fetched": 1, "inserted": 1}

    def broken_fallback(run_db, _since):
        run_db.add_all(
            [
                _StageRecord(name="duplicate"),
                _StageRecord(name="duplicate"),
            ]
        )
        run_db.flush()

    def healthy_overlay(run_db, _fallback_result, _mode):
        run_db.add(_StageRecord(name="overlay-ok"))

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=sync_from_chatlog,
        load_policy=lambda _db: {"max_attempts": 1, "sleep_seconds": 0},
        populate_fallback=broken_fallback,
        run_tool_overlay=healthy_overlay,
        refresh_snapshots=lambda _db: None,
        persist_run=lambda run_db, payload: sync_runtime.persist_sync_run(
            run_db,
            _RunState,
            payload,
        ),
    )

    result = sync_runtime.execute_chatlog_sync_run(
        db,
        adapters=adapters,
        model_cls=_RunState,
    )
    db.close()

    assert result["status"] == "ok"
    assert result["postprocess_errors"][0]["stage"] == "fallback_summary"
    with session_factory() as verify_db:
        assert verify_db.scalar(select(_MainRecord.name)) == "main-sync-ok"
        assert verify_db.scalars(select(_StageRecord.name)).all() == ["overlay-ok"]
        stored = verify_db.get(_RunState, sync_runtime.CHATLOG_LAST_RUN_KEY)
        assert stored is not None
        run_payload = json.loads(stored.value)
        assert run_payload["status"] == "ok"
        assert run_payload["postprocess_errors"][0]["stage"] == "fallback_summary"


def test_chatlog_run_persists_failure_when_policy_loading_raises():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    persisted: list[dict] = []
    db = _FakeDb(events)

    def load_policy(_db):
        raise RuntimeError("policy storage unavailable")

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=lambda *_args: pytest.fail("sync must not run"),
        load_policy=load_policy,
        populate_fallback=lambda *_args: None,
        run_tool_overlay=lambda *_args: None,
        refresh_snapshots=lambda *_args: None,
        persist_run=lambda _db, payload: (events.append("persist"), persisted.append(dict(payload))),
    )

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert result["status"] == "error"
    assert result["attempts"] == 0
    assert result["error_code"] == "SYNC-CHATLOG-UNKNOWN-001"
    assert result["fetched"] == 0
    assert result["inserted"] == 0
    assert persisted[0]["status"] == "error"
    assert persisted[0]["attempts"] == 0
    assert persisted[0]["error_code"] == "SYNC-CHATLOG-UNKNOWN-001"
    assert events == ["rollback", "persist", "commit"]


def test_default_chatlog_postprocessors_disable_internal_commits(monkeypatch):
    import app.services.sync_runtime as sync_runtime

    class _Message:
        id = 7
        content_text = "这是一条长度超过二十个字并等待工具摘要处理的微信消息。"
        derived = None
        meta = None

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [_Message()]

    class _Db:
        def execute(self, _query):
            return _Result()

        def get(self, _model, _key):
            return None

    captured = {}

    def fake_fallback(_db, rows, *, force, commit):
        captured["fallback"] = {"rows": rows, "force": force, "commit": commit}
        return 1

    def fake_overlay(
        _db,
        rows,
        *,
        force,
        concurrency,
        batch_size,
        temperature,
        commit,
    ):
        captured["overlay"] = {
            "rows": rows,
            "force": force,
            "concurrency": concurrency,
            "batch_size": batch_size,
            "temperature": temperature,
            "commit": commit,
        }
        return {"updated": 1}

    monkeypatch.setattr("app.services.ai_tools.populate_fallback_derived", fake_fallback)
    monkeypatch.setattr("app.services.ai_tools.ensure_message_features", fake_overlay)
    db = _Db()

    fallback_result = sync_runtime._default_populate_fallback(db, None)
    sync_runtime._run_inline_tool_overlay(db, fallback_result)

    assert captured["fallback"]["commit"] is False
    assert captured["overlay"]["commit"] is False


def test_async_overlay_worker_starts_after_commit_and_sees_fallback(tmp_path, monkeypatch):
    from app.db import Base
    from app.models import Message, SyncState
    import app.services.sync_runtime as sync_runtime

    database_path = tmp_path / "sync-overlay.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    committed = threading.Event()
    worker_done = threading.Event()
    observed: dict = {}

    class _TrackingSession(OrmSession):
        def commit(self):
            super().commit()
            committed.set()

    session_factory = sessionmaker(
        bind=engine,
        class_=_TrackingSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.db.SessionLocal", session_factory)

    real_thread_class = threading.Thread
    threads = []
    start_commit_states: list[bool] = []

    class _TrackingThread(real_thread_class):
        def start(self):
            start_commit_states.append(committed.is_set())
            threads.append(self)
            return super().start()

    monkeypatch.setattr(sync_runtime.threading, "Thread", _TrackingThread)

    def fake_ensure(_db, rows, **_kwargs):
        observed["rows"] = [
            {
                "id": row.id,
                "content_text": row.content_text,
                "derived": dict(row.derived or {}),
            }
            for row in rows
        ]
        worker_done.set()
        return {"updated": 0}

    monkeypatch.setattr("app.services.ai_tools.ensure_message_features", fake_ensure)
    db = session_factory()

    def sync_from_chatlog(run_db, _since):
        run_db.add(
            Message(
                timestamp=datetime.utcnow(),
                type="text",
                content_text="这是一条超过二十个字并且需要异步摘要处理的新微信消息。",
                derived=None,
            )
        )
        return {"status": "ok", "fetched": 1, "inserted": 1}

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=sync_from_chatlog,
        load_policy=lambda _db: {"max_attempts": 1, "sleep_seconds": 0},
        refresh_snapshots=lambda _db: None,
        persist_run=lambda run_db, payload: sync_runtime.persist_sync_run(
            run_db,
            SyncState,
            payload,
        ),
    )

    result = sync_runtime.execute_chatlog_sync_run(
        db,
        adapters=adapters,
        model_cls=SyncState,
        overlay_mode="async",
    )

    assert worker_done.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert thread.is_alive() is False
    db.close()
    engine.dispose()

    assert result["status"] == "ok"
    assert start_commit_states == [True]
    assert len(observed["rows"]) == 1
    assert observed["rows"][0]["derived"]["summary_origin"] == "fallback"
    assert observed["rows"][0]["content_text"].startswith("这是一条超过二十个字")


@pytest.mark.parametrize("failure_stage", ["persist", "commit"])
def test_async_overlay_does_not_start_when_finalization_fails(
    failure_stage,
    monkeypatch,
):
    import app.services.sync_runtime as sync_runtime

    starts: list[str] = []

    class _Thread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            starts.append("start")

    class _FailingDb(_FakeDb):
        def commit(self):
            self.events.append("commit")
            if failure_stage == "commit":
                raise RuntimeError("commit failed")

    monkeypatch.setattr(sync_runtime.threading, "Thread", _Thread)
    db = _FailingDb()

    def persist_run(_db, _payload):
        if failure_stage == "persist":
            raise RuntimeError("persist failed")

    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=lambda _db, _since: {"status": "ok", "fetched": 1, "inserted": 1},
        load_policy=lambda _db: {"max_attempts": 1, "sleep_seconds": 0},
        populate_fallback=lambda _db, _since: {"message_ids": [1]},
        refresh_snapshots=lambda _db: None,
        persist_run=persist_run,
    )

    result = sync_runtime.execute_chatlog_sync_run(db, adapters=adapters)

    assert result["status"] == "error"
    assert starts == []


def test_async_overlay_start_failure_is_observable_after_successful_commit(monkeypatch):
    import app.services.sync_runtime as sync_runtime

    class _Thread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(sync_runtime.threading, "Thread", _Thread)
    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=lambda _db, _since: {"status": "ok", "fetched": 1, "inserted": 1},
        load_policy=lambda _db: {"max_attempts": 1, "sleep_seconds": 0},
        populate_fallback=lambda _db, _since: {"message_ids": [1]},
        refresh_snapshots=lambda _db: None,
        persist_run=lambda _db, _payload: None,
    )

    result = sync_runtime.execute_chatlog_sync_run(_FakeDb(), adapters=adapters)

    assert result["status"] == "ok"
    assert result["post_commit_errors"] == [
        {"stage": "tool_overlay", "error": "thread start failed"}
    ]


def test_inline_overlay_restores_conservative_pending_filter_and_limit(monkeypatch):
    import app.services.sync_runtime as sync_runtime

    class _State:
        value = json.dumps(
            {
                "enable_msg_tool_overlay": True,
                "default_concurrency": 9,
            }
        )

    class _Message:
        def __init__(self, message_id, text, derived=None):
            self.id = message_id
            self.timestamp = datetime.utcnow()
            self.type = "text"
            self.content_text = text
            self.meta = None
            self.derived = derived

    class _Db:
        def get(self, _model, key):
            return _State() if key == "ai_runtime" else None

    short = _Message(1, "短文本")
    existing_tool = _Message(
        2,
        "这是一条已经拥有工具摘要且长度超过二十字的微信消息。",
        {"summary_origin": "tool", "summary": "ai: 已处理"},
    )
    pending = [
        _Message(
            message_id,
            f"这是第{message_id}条长度超过二十个字并等待工具摘要处理的微信消息。",
        )
        for message_id in range(3, 68)
    ]
    captured = {}

    def fake_ensure(_db, rows, **kwargs):
        captured["ids"] = [row.id for row in rows]
        captured["kwargs"] = kwargs
        return {"updated": len(rows)}

    monkeypatch.setattr("app.services.ai_tools.ensure_message_features", fake_ensure)

    sync_runtime._run_inline_tool_overlay(
        _Db(),
        {"message_ids": [row.id for row in [short, existing_tool, *pending]], "messages": [short, existing_tool, *pending]},
    )

    assert captured["ids"] == list(range(3, 63))
    assert captured["kwargs"] == {
        "force": False,
        "concurrency": 1,
        "batch_size": 1,
        "temperature": 0.1,
        "commit": False,
    }


def _dual_track_adapters(sync_runtime, events: list[str], *, fail_chatlog: bool = False):
    persisted: list[dict] = []

    def sync_full(_db, days):
        events.append(f"chatlog:{days}")
        if fail_chatlog:
            raise RuntimeError("chatlog track failed")
        return {"fetched": 4, "inserted": 2, "from": "2026-07-10", "to": "2026-07-11"}

    adapters = sync_runtime.DualTrackSyncAdapters(
        load_policy=lambda _db: {},
        get_wechatapi_state=lambda _db: {"healthy": True, "message": "wechatapi ok"},
        get_chatlog_state=lambda _db: {"healthy": True, "message": "chatlog ok"},
        get_wx_cli_state=lambda _db: {"healthy": True, "message": "wx-cli ok"},
        sync_full=sync_full,
        sync_from_wx_cli=lambda _db, days: events.append(f"wx_cli:{days}")
        or {"fetched": 3, "inserted": 1, "from": "2026-07-10", "to": "2026-07-11"},
        refresh_snapshots=lambda _db: events.append("snapshot"),
        persist_run=lambda _db, payload: (events.append("persist"), persisted.append(dict(payload))),
    )
    return adapters, persisted


def test_dual_track_run_uses_only_first_enabled_track_by_default():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)
    adapters, persisted = _dual_track_adapters(sync_runtime, events)
    adapters.load_policy = lambda _db: {
        "mode": "custom",
        "enabled_tracks": ["chatlog", "wx_cli"],
        "track_order": ["wx_cli", "chatlog", "wechatapi"],
        "use_multiple_tracks": False,
        "chatlog_window_days": 2,
    }

    result = sync_runtime.execute_dual_track_sync_run(db, adapters=adapters)

    assert result["enabled_order"] == ["wx_cli", "chatlog"]
    assert result["execution_order"] == ["wx_cli"]
    assert [item["track"] for item in result["actions"]] == ["wx_cli"]
    assert "chatlog:2" not in events
    assert events == ["wx_cli:2", "snapshot", "commit", "persist", "commit"]
    assert persisted[0]["status"] == "ok"


def test_dual_track_run_continues_after_track_failure_when_multi_track_enabled():
    import app.services.sync_runtime as sync_runtime

    events: list[str] = []
    db = _FakeDb(events)
    adapters, persisted = _dual_track_adapters(sync_runtime, events, fail_chatlog=True)
    adapters.load_policy = lambda _db: {
        "mode": "custom",
        "enabled_tracks": ["chatlog", "wx_cli"],
        "track_order": ["chatlog", "wx_cli", "wechatapi"],
        "use_multiple_tracks": True,
        "chatlog_window_days": 3,
    }

    result = sync_runtime.execute_dual_track_sync_run(db, days=5, adapters=adapters)

    assert result["execution_order"] == ["chatlog", "wx_cli"]
    assert [item["status"] for item in result["actions"]] == ["error", "ok"]
    assert events == [
        "chatlog:5",
        "rollback",
        "wx_cli:5",
        "snapshot",
        "commit",
        "persist",
        "commit",
    ]
    assert result["status"] == "ok"
    assert persisted[0]["status"] == "ok"


def test_dual_track_policy_save_normalizes_and_persists_selection():
    import app.services.sync_runtime as sync_runtime

    class _PolicyModel:
        def __init__(self, *, key, value):
            self.key = key
            self.value = value

    class _PolicyDb:
        def __init__(self):
            self.rows = {}

        def get(self, _model, key):
            return self.rows.get(key)

        def add(self, row):
            self.rows[row.key] = row

    db = _PolicyDb()

    policy = sync_runtime.save_dual_track_policy(
        db,
        model_cls=_PolicyModel,
        payload={
            "enabled_tracks": [],
            "track_order": ["wx_cli", "chatlog", "invalid"],
            "use_multiple_tracks": True,
            "chatlog_window_days": 999,
        },
    )

    assert policy == {
        "mode": "custom",
        "enabled_tracks": ["wx_cli"],
        "track_order": ["wx_cli", "chatlog", "wechatapi"],
        "use_multiple_tracks": True,
        "chatlog_window_days": 90,
    }
    stored = json.loads(db.rows[sync_runtime.WECHAT_DUAL_TRACK_POLICY_KEY].value)
    assert stored == policy


def test_sync_chatlog_router_delegates_to_runtime_with_router_globals(monkeypatch):
    import app.routers.sync as sync_router

    captured = {}
    sentinel = {"status": "ok", "run_id": "chatlog-test", "attempts": 1}

    def fake_execute(db, *, since, adapters, model_cls):
        captured.update({"db": db, "since": since, "adapters": adapters, "model_cls": model_cls})
        return sentinel

    monkeypatch.setattr(sync_router.sync_runtime, "execute_chatlog_sync_run", fake_execute)
    db = _FakeDb()

    result = sync_router.sync_chatlog("2026-07-11T08:30:00Z", db=db)

    assert result is sentinel
    assert captured["db"] is db
    assert captured["since"] == datetime(2026, 7, 11, 16, 30)
    assert captured["model_cls"] is sync_router.SyncState
    assert captured["adapters"].sync_from_chatlog is not None
    assert captured["adapters"].load_policy is not None


def test_sync_dual_track_router_delegates_to_runtime_with_router_globals(monkeypatch):
    import app.routers.sync as sync_router

    captured = {}
    sentinel = {"status": "ok", "run_id": "wechat-dual-test"}

    def fake_execute(db, *, days, adapters, model_cls):
        captured.update({"db": db, "days": days, "adapters": adapters, "model_cls": model_cls})
        return sentinel

    monkeypatch.setattr(sync_router.sync_runtime, "execute_dual_track_sync_run", fake_execute)
    db = _FakeDb()

    result = sync_router.sync_wechat_dual_track(days=7, db=db)

    assert result is sentinel
    assert captured["db"] is db
    assert captured["days"] == 7
    assert captured["model_cls"] is sync_router.SyncState
    assert captured["adapters"].sync_full is not None
    assert captured["adapters"].sync_from_wx_cli is not None


def test_background_chatlog_job_uses_shared_sync_run_with_inline_overlay(monkeypatch):
    from app import background

    db = _FakeDb()
    captured = {}

    def fake_execute(run_db, *, adapters, overlay_mode, model_cls):
        captured.update(
            {
                "db": run_db,
                "adapters": adapters,
                "overlay_mode": overlay_mode,
                "model_cls": model_cls,
            }
        )
        return {"status": "ok"}

    monkeypatch.setattr(background, "SessionLocal", lambda: db)
    monkeypatch.setattr(background.sync_runtime, "execute_chatlog_sync_run", fake_execute)

    background._run_chatlog_sync_job()

    assert captured["db"] is db
    assert captured["overlay_mode"] == "inline"
    assert captured["model_cls"] is background.SyncState
    assert captured["adapters"].sync_from_chatlog is not None
    assert db.events == []
    assert db.closed is True


def test_background_chatlog_job_preserves_loop_failure_signal(monkeypatch):
    from app import background

    db = _FakeDb()
    monkeypatch.setattr(background, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        background.sync_runtime,
        "execute_chatlog_sync_run",
        lambda *_args, **_kwargs: {
            "status": "error",
            "error_code": "SYNC-CHATLOG-TIMEOUT-001",
            "error": "upstream timed out",
        },
    )

    with pytest.raises(RuntimeError, match="SYNC-CHATLOG-TIMEOUT-001"):
        background._run_chatlog_sync_job()

    assert db.closed is True
