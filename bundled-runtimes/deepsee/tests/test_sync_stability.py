import os
import sys
import json
import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class _Row:
    def __init__(self, value):
        self.value = value


class _DB:
    def __init__(self, rows=None):
        self._rows = rows or {}

    def get(self, _model, key):
        v = self._rows.get(key)
        if v is None:
            return None
        return _Row(v)

    def execute(self, *_args, **_kwargs):
        class _Result:
            def scalar(self):
                return None

        return _Result()


def test_classify_sync_error_timeout_retryable():
    import app.services.sync_runtime as sync_runtime

    code, retryable = sync_runtime.classify_sync_error(requests.Timeout("timeout"))
    assert code == "SYNC-CHATLOG-TIMEOUT-001"
    assert retryable is True


def test_classify_sync_error_unreachable_retryable():
    import app.services.sync_runtime as sync_runtime

    code, retryable = sync_runtime.classify_sync_error(requests.ConnectionError("conn down"))
    assert code == "SYNC-CHATLOG-UNAVAILABLE-001"
    assert retryable is True


def test_run_with_retry_eventual_success():
    import app.services.sync_runtime as sync_runtime

    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("temporary")
        return {"status": "ok"}

    result, attempts, err = sync_runtime.run_with_retry(_fn, max_attempts=3, sleep_seconds=0)
    assert err is None
    assert attempts == 3
    assert result == {"status": "ok"}


def test_build_sync_state_payload_with_last_run_json():
    import app.services.sync_runtime as sync_runtime

    run = {
        "run_id": "run-1",
        "status": "ok",
        "attempts": 1,
        "error_code": None,
        "fetched": 10,
        "inserted": 3,
        "duration_ms": 120,
    }
    db = _DB(
        {
            "chatlog_last_sync": "2026-03-07T11:30:00",
            "chatlog_sync_last_run": json.dumps(run, ensure_ascii=False),
        }
    )
    out = sync_runtime.build_sync_state_payload(db, _model_cls=object)
    assert out["last_sync"] == "2026-03-07T11:30:00"
    assert out["last_run"]["run_id"] == "run-1"
    assert out["last_run"]["fetched"] == 10


def test_build_sync_state_payload_handles_bad_json():
    import app.services.sync_runtime as sync_runtime

    db = _DB(
        {
            "chatlog_last_sync": "2026-03-07T11:30:00",
            "chatlog_sync_last_run": "{bad-json",
        }
    )
    out = sync_runtime.build_sync_state_payload(db, _model_cls=object)
    assert out["last_sync"] == "2026-03-07T11:30:00"
    assert out["last_run"] is None


def test_normalize_chatlog_sync_policy_defaults():
    import app.services.sync_runtime as sync_runtime

    p = sync_runtime.normalize_chatlog_sync_policy(None)
    assert p["max_attempts"] == 2
    assert p["sleep_seconds"] == 0.6


def test_normalize_chatlog_sync_policy_bounds():
    import app.services.sync_runtime as sync_runtime

    p = sync_runtime.normalize_chatlog_sync_policy({"max_attempts": 99, "sleep_seconds": -5})
    assert p["max_attempts"] == 5
    assert p["sleep_seconds"] == 0.0


def test_wechat_dual_track_policy_defaults_and_bounds():
    import app.routers.sync as sync_router

    db = _DB()
    policy = sync_router._dual_track_policy(db)
    assert policy["mode"] == "custom"
    assert policy["enabled_tracks"] == ["wechatapi", "chatlog", "wx_cli"]
    assert policy["track_order"] == ["wechatapi", "chatlog", "wx_cli"]
    assert policy["use_multiple_tracks"] is False
    assert policy["chatlog_window_days"] == 1

    db = _DB(
        {
            "wechat_dual_track_policy": json.dumps(
                {
                    "mode": "custom",
                    "enabled_tracks": ["chatlog", "bad"],
                    "track_order": ["wx_cli", "chatlog", "wechatapi"],
                    "use_multiple_tracks": True,
                    "chatlog_window_days": 999,
                },
                ensure_ascii=False,
            )
        }
    )
    policy = sync_router._dual_track_policy(db)
    assert policy["mode"] == "custom"
    assert policy["enabled_tracks"] == ["chatlog"]
    assert policy["track_order"] == ["wx_cli", "chatlog", "wechatapi"]
    assert policy["use_multiple_tracks"] is True
    assert policy["chatlog_window_days"] == 90


def test_wechat_dual_track_sync_uses_only_first_track_by_default(monkeypatch):
    import app.routers.sync as sync_router

    calls = {"chatlog": 0, "wx_cli": 0}

    class _DBWithWrites(_DB):
        def commit(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(
        sync_router,
        "_dual_track_policy",
        lambda _db: {
            "mode": "custom",
            "enabled_tracks": ["chatlog", "wx_cli"],
            "track_order": ["chatlog", "wx_cli", "wechatapi"],
            "use_multiple_tracks": False,
            "chatlog_window_days": 1,
        },
    )
    monkeypatch.setattr(sync_router, "_wechatapi_track_state", lambda _db: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "_chatlog_track_state", lambda: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "_wx_cli_track_state", lambda: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "refresh_default_snapshots", lambda _db: None)
    monkeypatch.setattr(sync_router.sync_runtime, "persist_sync_run", lambda *_args, **_kwargs: None)

    def fake_chatlog(_db, days):
        calls["chatlog"] += 1
        return {"fetched": 2, "inserted": 1}

    def fake_wx_cli(_db, days):
        calls["wx_cli"] += 1
        return {"fetched": 99, "inserted": 99}

    monkeypatch.setattr(sync_router, "sync_full", fake_chatlog)
    monkeypatch.setattr(sync_router, "sync_from_wx_cli", fake_wx_cli)

    payload = sync_router.sync_wechat_dual_track(days=1, db=_DBWithWrites())

    assert payload["execution_order"] == ["chatlog"]
    assert calls == {"chatlog": 1, "wx_cli": 0}
    assert payload["actions"][0]["track"] == "chatlog"


def test_wechat_dual_track_sync_uses_multiple_tracks_when_enabled(monkeypatch):
    import app.routers.sync as sync_router

    calls = {"chatlog": 0, "wx_cli": 0}

    class _DBWithWrites(_DB):
        def commit(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(
        sync_router,
        "_dual_track_policy",
        lambda _db: {
            "mode": "custom",
            "enabled_tracks": ["chatlog", "wx_cli"],
            "track_order": ["chatlog", "wx_cli", "wechatapi"],
            "use_multiple_tracks": True,
            "chatlog_window_days": 1,
        },
    )
    monkeypatch.setattr(sync_router, "_wechatapi_track_state", lambda _db: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "_chatlog_track_state", lambda: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "_wx_cli_track_state", lambda: {"healthy": True, "message": "ok"})
    monkeypatch.setattr(sync_router, "refresh_default_snapshots", lambda _db: None)
    monkeypatch.setattr(sync_router.sync_runtime, "persist_sync_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sync_router, "sync_full", lambda _db, days: calls.__setitem__("chatlog", calls["chatlog"] + 1) or {"fetched": 1, "inserted": 1})
    monkeypatch.setattr(sync_router, "sync_from_wx_cli", lambda _db, days: calls.__setitem__("wx_cli", calls["wx_cli"] + 1) or {"fetched": 1, "inserted": 1})

    payload = sync_router.sync_wechat_dual_track(days=1, db=_DBWithWrites())

    assert payload["execution_order"] == ["chatlog", "wx_cli"]
    assert calls == {"chatlog": 1, "wx_cli": 1}


def test_sync_from_chatlog_fails_fast_when_session_times_out(monkeypatch):
    import app.services.sync_service as sync_service

    calls = {"chatlog": 0}

    class _Client:
        def get_sessions(self):
            raise requests.Timeout("session timeout")

        def get_chatlog(self, *args, **kwargs):
            calls["chatlog"] += 1
            return []

    monkeypatch.setattr(sync_service, "ChatlogClient", lambda: _Client())

    try:
        sync_service.sync_from_chatlog(_DB())
    except requests.Timeout:
        pass
    else:
        raise AssertionError("expected chatlog session timeout to propagate")

    assert calls["chatlog"] == 0


def test_sync_full_fails_fast_when_session_times_out(monkeypatch):
    import app.services.sync_service as sync_service

    calls = {"chatlog": 0}

    class _Client:
        def get_sessions(self):
            raise requests.Timeout("session timeout")

        def get_chatlog(self, *args, **kwargs):
            calls["chatlog"] += 1
            return []

    monkeypatch.setattr(sync_service, "ChatlogClient", lambda: _Client())

    try:
        sync_service.sync_full(_DB(), days=3)
    except requests.Timeout:
        pass
    else:
        raise AssertionError("expected chatlog session timeout to propagate")

    assert calls["chatlog"] == 0
