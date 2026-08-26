import os
import sys

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import agent_api


def _set_agent_tokens(monkeypatch, single=None, many=None):
    monkeypatch.setattr(agent_api.settings, "AGENT_API_TOKEN", single, raising=False)
    monkeypatch.setattr(agent_api.settings, "AGENT_API_TOKENS", many, raising=False)


def test_configured_agent_tokens_empty(monkeypatch):
    _set_agent_tokens(monkeypatch, single=None, many=None)
    assert agent_api._configured_agent_tokens() == set()


def test_configured_agent_tokens_parse_multiple(monkeypatch):
    _set_agent_tokens(monkeypatch, single="tok-1", many="tok-2, tok-3, tok-2, ,")
    assert agent_api._configured_agent_tokens() == {"tok-1", "tok-2", "tok-3"}


def test_require_agent_token_skips_when_unconfigured(monkeypatch):
    _set_agent_tokens(monkeypatch, single=None, many=None)
    agent_api.require_agent_token(authorization=None, x_agent_token=None)


def test_require_agent_token_rejects_missing_when_configured(monkeypatch):
    _set_agent_tokens(monkeypatch, single="tok-1", many=None)
    with pytest.raises(HTTPException) as exc:
        agent_api.require_agent_token(authorization=None, x_agent_token=None)
    assert exc.value.status_code == 401


def test_require_agent_token_accepts_bearer(monkeypatch):
    _set_agent_tokens(monkeypatch, single="tok-1", many=None)
    agent_api.require_agent_token(authorization="Bearer tok-1", x_agent_token=None)


def test_require_agent_token_accepts_x_agent_token(monkeypatch):
    _set_agent_tokens(monkeypatch, single="tok-1", many=None)
    agent_api.require_agent_token(authorization=None, x_agent_token="tok-1")


def test_require_agent_token_rejects_wrong_token(monkeypatch):
    _set_agent_tokens(monkeypatch, single="tok-1", many="tok-2")
    with pytest.raises(HTTPException) as exc:
        agent_api.require_agent_token(authorization="Bearer nope", x_agent_token="bad")
    assert exc.value.status_code == 401


def test_all_agent_routes_attach_auth_dependency():
    for route in agent_api.router.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = [dep.call for dep in route.dependant.dependencies]
        assert agent_api.require_agent_token in calls
