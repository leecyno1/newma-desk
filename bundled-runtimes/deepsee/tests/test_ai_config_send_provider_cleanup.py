from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import ai


def _patch_config_state(monkeypatch, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(state))

    def _save(payload: dict) -> None:
        state.clear()
        state.update(payload)

    monkeypatch.setattr(ai, "save_ai_config", _save)
    return state


def test_ai_config_accepts_wechatapi_gateway_as_primary_provider(monkeypatch):
    state = _patch_config_state(monkeypatch, {"send_provider": "wechatpad_direct"})

    ai.set_ai_config({"send_provider": "wechatapi_gateway"})

    assert state["send_provider"] == "wechatapi_gateway"
    payload = ai.get_ai_config()
    assert payload["send_provider"] == "wechatapi_gateway"


def test_ai_config_defaults_to_wechatapi_gateway_when_provider_missing_or_invalid(monkeypatch):
    monkeypatch.setattr(ai, "load_ai_config", lambda: {})
    payload = ai.get_ai_config()
    assert payload["send_provider"] == "wechatapi_gateway"

    monkeypatch.setattr(ai, "load_ai_config", lambda: {"send_provider": "invalid-provider"})
    payload = ai.get_ai_config()
    assert payload["send_provider"] == "wechatapi_gateway"


def test_ai_config_response_does_not_expose_langbot_fields(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "send_provider": "wechatapi_gateway",
            "langbot_gateway_base": "http://127.0.0.1:5311",
            "langbot_gateway_bot_uuid": "bot-uuid",
            "langbot_gateway_auth_token": "secret",
        },
    )

    payload = ai.get_ai_config()

    assert "langbot_gateway_base" not in payload
    assert "langbot_gateway_bot_uuid" not in payload
    assert "langbot_gateway_has_token" not in payload


def test_ai_config_rejects_removed_langbot_provider(monkeypatch):
    state = _patch_config_state(monkeypatch, {"send_provider": "wechatapi_gateway"})

    ai.set_ai_config({"send_provider": "langbot_gateway"})

    assert state["send_provider"] == "wechatapi_gateway"
    payload = ai.get_ai_config()
    assert payload["send_provider"] == "wechatapi_gateway"
