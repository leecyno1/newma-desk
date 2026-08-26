import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import agent_api


def test_check_agent_path_allowed_blocklist_first(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "_effective_agent_policy",
        lambda: {"allowlist": ["/api/messages"], "blocklist": ["/api/messages"]},
    )
    ok, reason = agent_api._check_agent_path_allowed("/api/messages")
    assert ok is False
    assert "blocklist" in str(reason)


def test_check_agent_path_allowed_requires_allowlist_hit(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "_effective_agent_policy",
        lambda: {"allowlist": ["/api/messages"], "blocklist": []},
    )
    ok, reason = agent_api._check_agent_path_allowed("/api/email/messages")
    assert ok is False
    assert "allowlist" in str(reason)


def test_check_agent_path_allowed_when_allowlist_empty(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "_effective_agent_policy",
        lambda: {"allowlist": [], "blocklist": []},
    )
    ok, reason = agent_api._check_agent_path_allowed("/api/messages")
    assert ok is True
    assert reason is None


def test_invoke_single_returns_403_when_blocked(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "_effective_agent_policy",
        lambda: {"allowlist": [], "blocklist": ["/api/messages"]},
    )
    payload = agent_api.AgentInvokeIn(method="GET", path="/api/messages")
    status, out = agent_api._invoke_single(payload=payload, request=object())
    assert status == 403
    assert out["ok"] is False
