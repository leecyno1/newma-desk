from datetime import datetime


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, messages, emails):
        self._results = [_ScalarResult(messages), _ScalarResult(emails)]

    def execute(self, _query):
        return self._results.pop(0)


class _FakeMessage:
    def __init__(self, msg_id, text, derived=None):
        self.id = msg_id
        self.timestamp = datetime.utcnow()
        self.content_text = text
        self.meta = None
        self.derived = derived


class _FakeEmail:
    def __init__(self, email_id, derived=None):
        self.id = email_id
        self.sent_at = datetime.utcnow()
        self.derived = derived


def test_summary_overlay_once_updates_wechat_and_email_incrementally(monkeypatch):
    from app import background

    long_message = _FakeMessage(1, "这是一条超过二十字的微信消息，需要每小时进入增量摘要。")
    short_message = _FakeMessage(2, "短消息")
    email = _FakeEmail(10)
    db = _FakeDb([long_message, short_message], [email])
    captured = {}

    def fake_populate(_db, rows, force=False):
        captured["message_fallback_rows"] = rows
        captured["message_fallback_force"] = force
        return 1

    def fake_ensure(_db, rows, **kwargs):
        captured["message_tool_rows"] = rows
        captured["message_tool_force"] = kwargs.get("force")
        return {"updated": len(rows)}

    def fake_email_fallback(_db, rows, force=False, commit=False):
        captured["email_fallback_rows"] = rows
        captured["email_fallback_force"] = force
        captured["email_fallback_commit"] = commit
        return {"10": {}}

    def fake_email_features(_db, rows, force=False, commit=False):
        captured["email_tool_rows"] = rows
        captured["email_tool_force"] = force
        captured["email_tool_commit"] = commit
        return {"10": {}}

    monkeypatch.setattr("app.services.ai_tools.populate_fallback_derived", fake_populate)
    monkeypatch.setattr("app.services.ai_tools.ensure_message_features", fake_ensure)
    monkeypatch.setattr("app.services.email_features.persist_email_fallback", fake_email_fallback)
    monkeypatch.setattr("app.services.email_features.persist_email_features", fake_email_features)

    stats = background.run_summary_overlay_once(
        db,
        cfg={
            "enable_msg_tool_overlay": True,
            "msg_tool_overlay_limit": 20,
            "enable_email_tool_overlay": True,
            "email_overlay_window": 20,
            "email_overlay_cap": 20,
        },
    )

    assert captured["message_fallback_rows"] == [long_message, short_message]
    assert captured["message_fallback_force"] is False
    assert captured["message_tool_rows"] == [long_message]
    assert captured["message_tool_force"] is False
    assert captured["email_fallback_rows"] == [email]
    assert captured["email_fallback_commit"] is False
    assert captured["email_tool_rows"] == [email]
    assert captured["email_tool_commit"] is False
    assert stats == {"wechat_fallback": 1, "wechat_tool": 1, "email_fallback": 1, "email_tool": 1}
