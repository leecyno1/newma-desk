from __future__ import annotations

from app.routers import ai


def test_ai_config_accepts_wechatapi_gateway_provider(monkeypatch):
    state = {"send_provider": "wechatpad_direct"}
    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(state))

    def _save(payload):
        state.clear()
        state.update(payload)
        return dict(state)

    monkeypatch.setattr(ai, "save_ai_config", _save)
    ai.set_ai_config({"send_provider": "wechatapi_gateway"})
    payload = ai.get_ai_config()
    assert payload["send_provider"] == "wechatapi_gateway"
