import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import ai


def test_onepage_image_generation_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_url": "https://api.openai.com/v1",
            "api_key": "base-key",
            "onepage_output_mode": "auto",
            "onepage_image_api_url": "https://api.openai.com/v1",
            "onepage_image_api_key": "image-key",
            "onepage_image_model": "gpt-image-2",
            "onepage_image_size": "1024x1536",
            "onepage_image_quality": "medium",
            "model": "gpt-5.5",
            "model_router": {"enabled": False},
        },
    )
    calls = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": "aGVsbG8="}]}

    def _post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Resp()

    monkeypatch.setattr(ai.requests, "post", _post)

    out = ai.generate_onepage_image({
        "period": "最近1天",
        "template_style": "executive_blue",
        "onepage": {
            "hero_title": "市场一页通",
            "key_takeaway": "科技主线延续，但需关注回撤风险。",
            "sections": [
                {"title": "市场主线", "bullets": ["半导体景气延续"], "metrics": {"热度": "高"}, "chart_hint": "思维导图"}
            ],
        },
    })

    assert out["status"] == "ok"
    assert out["b64_json"] == "aGVsbG8="
    assert calls[0]["url"] == "https://api.openai.com/v1/images/generations"
    assert calls[0]["headers"]["Authorization"] == "Bearer image-key"
    assert calls[0]["json"]["model"] == "gpt-image-2"
    assert calls[0]["json"]["size"] == "1024x1536"
    assert "思维导图" in calls[0]["json"]["prompt"]


def test_onepage_image_generation_skips_when_local_mode(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {"onepage_output_mode": "local", "model_router": {"enabled": False}},
    )

    out = ai.generate_onepage_image({"onepage": {"hero_title": "x"}})

    assert out == {"status": "skipped", "reason": "local_mode"}


def test_onepage_audio_generation_uses_mmx_wrapper(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_url": "https://app.watertimber.us/v1",
            "api_key": "base-key",
            "model": "gpt-5.5",
            "onepage_image_api_key": "",
            "model_router": {"enabled": False},
        },
    )
    monkeypatch.setattr(ai, "_build_onepage_audio_script", lambda payload, conf: "口播稿")

    calls = {}

    def _fake_speech(script, *, api_key, duration_minutes):
        calls["script"] = script
        calls["api_key"] = api_key
        calls["duration_minutes"] = duration_minutes
        return {
            "status": "ok",
            "duration_minutes": duration_minutes,
            "mime_type": "audio/mpeg",
            "b64_audio": "aGVsbG8=",
            "script": script,
            "provider": "MiniMax CLI",
        }

    monkeypatch.setattr(ai, "_run_mmx_speech", _fake_speech)

    out = ai.generate_onepage_audio({
        "duration_minutes": 10,
        "onepage": {"hero_title": "市场一页通", "key_takeaway": "科技主线延续"},
    })

    assert out["status"] == "ok"
    assert out["duration_minutes"] == 10
    assert out["b64_audio"] == "aGVsbG8="
    assert calls == {"script": "口播稿", "api_key": "", "duration_minutes": 10}
