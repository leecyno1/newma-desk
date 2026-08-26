import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import ai


def test_set_ai_config_preserves_existing_unified_key_when_masked(monkeypatch):
    state = {
        "api_url": "https://app.watertimber.us/v1",
        "api_key": "existing-key",
        "model": "gpt-5.5",
        "tool_model": "MiniMax-M3",
        "message_filters": {},
        "module_prompts": {},
        "tool_prompts": {},
        "derive_defaults": {},
        "model_router": {"enabled": True, "main_channels": [], "tool_channels": []},
    }

    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(state))

    saved = {}

    def _save(conf):
        saved.update(conf)

    monkeypatch.setattr(ai, "save_ai_config", _save)

    ai.set_ai_config({"api_key": "", "has_key": True, "api_url": "https://app.watertimber.us/v1"})

    assert saved["api_key"] == "existing-key"


def test_ai_provider_mode_is_saved_and_returned(monkeypatch):
    state = {
        "api_url": "https://app.watertimber.us/v1",
        "api_key": "existing-key",
        "model": "gpt-5.5",
        "tool_model": "MiniMax-M3",
        "message_filters": {},
        "module_prompts": {},
        "tool_prompts": {},
        "derive_defaults": {},
        "model_router": {"enabled": True, "main_channels": [], "tool_channels": []},
    }
    saved = {}

    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(state))
    monkeypatch.setattr(ai, "save_ai_config", lambda conf: saved.update(conf))

    ai.set_ai_config({"ai_provider_mode": "dasheng"})

    assert saved["ai_provider_mode"] == "dasheng"

    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(saved))
    payload = ai.get_ai_config()
    assert payload["ai_provider_mode"] == "dasheng"


def test_onepage_image_config_masks_key_and_saves_masked(monkeypatch):
    state = {
        "api_url": "https://app.watertimber.us/v1",
        "api_key": "base-key",
        "onepage_image_api_url": "https://api.openai.com/v1",
        "onepage_image_api_key": "image-key",
        "onepage_image_model": "gpt-image-2",
        "onepage_output_mode": "auto",
        "model": "gpt-5.5",
        "tool_model": "MiniMax-M3",
        "message_filters": {},
        "module_prompts": {},
        "tool_prompts": {},
        "derive_defaults": {},
        "model_router": {"enabled": True, "main_channels": [], "tool_channels": []},
    }
    saved = {}

    monkeypatch.setattr(ai, "load_ai_config", lambda: dict(state))
    monkeypatch.setattr(ai, "save_ai_config", lambda conf: saved.update(conf))

    payload = ai.get_ai_config()
    assert "onepage_image_api_key" not in payload
    assert payload["onepage_image_has_key"] is True

    ai.set_ai_config({"onepage_image_api_key": "", "onepage_image_has_key": True})
    assert saved["onepage_image_api_key"] == "image-key"


def test_get_ai_config_masks_quan2go_provider_key(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_url": "https://api.siliconflow.cn/v1",
            "api_key": "base-key",
            "model": "gpt-5.4",
            "tool_model": "THUDM/GLM-4-9B-0414",
            "tool_model_messages": "Qwen/Qwen3-8B",
            "tool_model_emails": "THUDM/GLM-4-9B-0414",
            "message_filters": {},
            "module_prompts": {},
            "tool_prompts": {},
            "derive_defaults": {},
            "model_router": {
                "enabled": True,
                "main_channels": [
                    {
                        "id": "main-quan2go-gpt55",
                        "name": "候选 Quan2Go GPT-5.5",
                        "model": "gpt-5.5",
                        "enabled": False,
                        "weight": 1,
                        "api_url": "https://capi.quan2go.com/openai",
                        "api_key": "secret-key",
                        "max_inflight": 4,
                    }
                ],
                "mid_channels": [],
                "tool_channels": [],
                "main_module_channels": {"default": ["main-quan2go-gpt55"]},
                "mid_route_channels": {},
                "tool_route_channels": {},
            },
        },
    )

    payload = ai.get_ai_config()
    main_channel = payload["model_router"]["main_channels"][0]
    assert main_channel["id"] == "main-quan2go-gpt55"
    assert main_channel["model"] == "gpt-5.5"
    assert main_channel["api_url"] == "https://capi.quan2go.com/openai"
    assert main_channel["api_key"] == ""
    assert main_channel["has_api_key"] is True
