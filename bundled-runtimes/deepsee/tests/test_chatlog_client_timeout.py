import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_chatlog_client_uses_configured_timeouts(monkeypatch):
    from app.services.chatlog_client import ChatlogClient
    from app.config import settings

    monkeypatch.setattr(settings, "CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS", 3, raising=False)
    monkeypatch.setattr(settings, "CHATLOG_HTTP_TIMEOUT_SECONDS", 7, raising=False)

    calls = []

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return []

        @property
        def text(self):
            return ""

    def _fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return _Resp()

    monkeypatch.setattr("app.services.chatlog_client.requests.get", _fake_get)

    c = ChatlogClient(base="http://127.0.0.1:5030")
    c.get_sessions()
    c.get_chatlog("2026-03-07", talker="wxid_1", limit=10, offset=0)

    assert calls[0]["timeout"] == 3
    assert calls[1]["timeout"] == 7
