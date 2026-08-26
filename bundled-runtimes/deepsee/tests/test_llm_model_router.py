import os
import sys

import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app.services.llm_client as llm_client
from app.services.llm_client import (
    DASHENG_CLOUD_API_URL,
    DASHENG_CLOUD_MAIN_MODEL,
    DASHENG_CLOUD_TOOL_MODEL,
    _MODEL_ROUTER_COUNTERS,
    load_ai_config,
    resolve_chat_target,
    resolve_chat_targets,
)


def test_empty_config_uses_dasheng_cloud_preset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    conf = load_ai_config()

    assert conf["api_url"] == DASHENG_CLOUD_API_URL
    assert conf["model"] == DASHENG_CLOUD_MAIN_MODEL
    assert conf["tool_model"] == DASHENG_CLOUD_TOOL_MODEL
    router = conf["model_router"]
    assert router["enabled"] is True
    assert router["main_module_channels"]["market"] == ["dasheng-report-gpt-55", "dasheng-report-deepseek-v4-flash"]
    assert router["main_module_channels"]["meetings"] == ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"]
    assert router["mid_route_channels"]["onepage"] == ["dasheng-onepage-minimax-m3"]
    assert router["tool_route_channels"]["messages"][0] == "dasheng-tool-minimax-m3"


def test_chat_completions_url_accepts_openai_base_and_full_endpoint():
    from app.services.llm_client import _chat_completions_url

    assert _chat_completions_url("https://example.com") == "https://example.com/v1/chat/completions"
    assert _chat_completions_url("https://example.com/v1") == "https://example.com/v1/chat/completions"
    assert _chat_completions_url("https://example.com/v1/chat/completions") == "https://example.com/v1/chat/completions"
    assert _chat_completions_url("https://example.com/chat/completions") == "https://example.com/chat/completions"


def test_minimax_m3_caps_oversized_chat_context_without_mutating_input():
    from app.services.llm_client import _prepare_chat_messages

    original = [
        {"role": "system", "content": "S" * 2000},
        {"role": "user", "content": "HEAD" + ("x" * 100_000) + "TAIL"},
    ]

    prepared = _prepare_chat_messages(original, model="MiniMax-M3")

    assert prepared is not original
    assert prepared[0] == original[0]
    assert len(prepared[1]["content"]) <= 48_000
    assert prepared[1]["content"].startswith("HEAD")
    assert prepared[1]["content"].endswith("TAIL")
    assert "上下文已截断" in prepared[1]["content"]
    assert len(original[1]["content"]) > 100_000


def test_non_minimax_models_keep_full_chat_context():
    from app.services.llm_client import _prepare_chat_messages

    original = [{"role": "user", "content": "x" * 60_000}]
    prepared = _prepare_chat_messages(original, model="gpt-5.6-terra")

    assert prepared == original


def test_normalizer_uses_reasoning_block_only_when_provider_has_no_final_text():
    from app.services.llm_client import _normalize_llm_content

    assert _normalize_llm_content("<think>有效分析结论</think>") == "有效分析结论"
    assert _normalize_llm_content("<think>中间推理</think>\n最终结论") == "最终结论"


def test_minimax_m3_uses_small_model_output_budget():
    from app.services.llm_client import _effective_max_tokens

    assert _effective_max_tokens("MiniMax-M3", 4000) == 1800
    assert _effective_max_tokens("MiniMax-M3", 1200) == 1200
    assert _effective_max_tokens("gpt-5.6-terra", 4000) == 4000


def test_minimax_m3_does_not_force_reasoning_split_with_small_output_budget():
    from app.services.llm_client import _model_payload_extras

    assert _model_payload_extras("MiniMax-M3") == {}
    assert _model_payload_extras("gpt-5.6-terra") == {}


def test_reasoning_only_fallback_removes_planning_preamble_and_localizes_labels():
    from app.services.llm_client import _normalize_llm_content

    raw = (
        "<think>Let me analyze the messages.\n"
        "Let me go through them carefully.\n"
        "1. 会议安排\nTime: 08:00, Platform: 腾讯, Topic: 宏观策略</think>"
    )
    normalized = _normalize_llm_content(raw)

    assert "Let me" not in normalized
    assert "时间：" in normalized
    assert "平台：" in normalized
    assert "主题：" in normalized


def test_minimax_plain_content_removes_task_restatement_and_planning_lines():
    from app.services.llm_client import _normalize_model_content

    raw = (
        "The user wants me to extract meeting information.\n"
        "Let me analyze the messages carefully.\n\n"
        "1. 会议安排\nTime: 08:00, Platform: 腾讯, Topic: 宏观策略"
    )
    normalized = _normalize_model_content(raw, model="MiniMax-M3")

    assert "The user wants me" not in normalized
    assert "Let me" not in normalized
    assert normalized.startswith("1. 会议安排")
    assert "时间：" in normalized


def test_router_disabled_falls_back_to_default_model():
    conf = {
        "api_url": "https://example.com/v1",
        "api_key": "k-default",
        "model": "main-default",
        "tool_model": "tool-default",
        "model_router": {"enabled": False},
    }
    target = resolve_chat_target(conf, route_kind="main", route_key="market", model_override=None)
    assert target["model"] == "main-default"
    assert target["channel_id"] is None
    assert target["api_url"] == "https://example.com/v1"
    assert target["api_key"] == "k-default"


def test_router_prefers_mapped_channel_when_enabled():
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "main-default",
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "main_channels": [
                {"id": "main-a", "model": "model-a", "weight": 1, "enabled": True},
                {"id": "main-b", "model": "model-b", "weight": 1, "enabled": True, "api_url": "https://b.example/v1", "api_key": "b-key"},
            ],
            "main_module_channels": {"market": ["main-b"], "default": ["main-a"]},
        },
    }
    target = resolve_chat_target(conf, route_kind="main", route_key="market", model_override="manual-model")
    assert target["channel_id"] == "main-b"
    assert target["model"] == "model-b"
    assert target["api_url"] == "https://b.example/v1"
    assert target["api_key"] == "b-key"


def test_router_honors_manual_override_when_prefer_router_disabled():
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "main-default",
        "model_router": {
            "enabled": True,
            "prefer_router": False,
            "main_channels": [{"id": "main-a", "model": "model-a", "weight": 1, "enabled": True}],
            "main_module_channels": {"default": ["main-a"]},
        },
    }
    target = resolve_chat_target(conf, route_kind="main", route_key="market", model_override="manual-model")
    assert target["channel_id"] is None
    assert target["model"] == "manual-model"
    assert target["api_url"] == "https://base.example/v1"


def test_tool_default_route_keeps_weighted_round_robin_sequence():
    _MODEL_ROUTER_COUNTERS.clear()
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "tool_model": "tool-default",
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "tool_channels": [
                {"id": "tool-a", "model": "tool-model-a", "weight": 1, "enabled": True},
                {"id": "tool-b", "model": "tool-model-b", "weight": 2, "enabled": True},
            ],
            "tool_route_channels": {"reply": ["tool-a", "tool-b"], "default": ["tool-a"]},
        },
    }

    seq = []
    for _ in range(6):
        target = resolve_chat_target(conf, route_kind="tool", route_key="reply", model_override=None)
        seq.append(target["channel_id"])
    assert seq == ["tool-a", "tool-b", "tool-b", "tool-a", "tool-b", "tool-b"]


def test_router_returns_ordered_fallback_targets():
    _MODEL_ROUTER_COUNTERS.clear()
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "main-default",
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "main_channels": [
                {"id": "main-a", "model": "model-a", "weight": 2, "enabled": True, "api_url": "https://a.example/v1", "api_key": "ka"},
                {"id": "main-b", "model": "model-b", "weight": 1, "enabled": True, "api_url": "https://b.example/v1", "api_key": "kb"},
            ],
            "main_module_channels": {"market": ["main-a", "main-b"], "default": ["main-a"]},
        },
    }
    targets = resolve_chat_targets(conf, route_kind="main", route_key="market", model_override=None)
    assert len(targets) >= 2
    assert targets[0]["channel_id"] in {"main-a", "main-b"}
    # all mapped channels should be included for fallback
    got_ids = [t.get("channel_id") for t in targets if t.get("channel_id")]
    assert set(got_ids) == {"main-a", "main-b"}
    # base default should be included as final fallback
    assert targets[-1]["channel_id"] is None
    assert targets[-1]["model"] == "main-default"


def test_tool_messages_route_includes_explicit_key_channels_before_base():
    _MODEL_ROUTER_COUNTERS.clear()
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "tool_model": "tool-default",
        "tool_model_messages": "msg-stable-model",
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "tool_channels": [
                {"id": "tool-a", "model": "tool-model-a", "weight": 1, "enabled": True, "api_url": "https://a.example/v1", "api_key": "ka"},
                {"id": "tool-b", "model": "tool-model-b", "weight": 1, "enabled": True, "api_url": "https://b.example/v1", "api_key": "kb"},
            ],
            "tool_route_channels": {"messages": ["tool-a", "tool-b"], "default": ["tool-a"]},
        },
    }
    targets = resolve_chat_targets(conf, route_kind="tool", route_key="messages", model_override="msg-stable-model")
    assert [t["channel_id"] for t in targets] == ["tool-a", "tool-b", None]
    assert targets[0]["model"] == "tool-model-a"
    assert targets[1]["model"] == "tool-model-b"
    assert targets[-1]["model"] == "msg-stable-model"
    assert targets[-1]["api_url"] == "https://base.example/v1"


def test_tool_messages_route_uses_stable_channel_pool_before_base():
    _MODEL_ROUTER_COUNTERS.clear()
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "tool_model": "tool-default",
        "tool_model_messages": "msg-stable-model",
        "tool_messages_stable_only": True,
        "tool_messages_stable_channels": ["tool-sf-qwen8b", "tool-sf-glm9b"],
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "tool_channels": [
                {"id": "tool-sf-qwen8b", "model": "Qwen/Qwen3-8B", "weight": 5, "enabled": True, "api_url": "https://sf.example/v1", "api_key": "ksf"},
                {"id": "tool-sf-glm9b", "model": "THUDM/GLM-4-9B-0414", "weight": 3, "enabled": True, "api_url": "https://sf.example/v1", "api_key": "ksf"},
                {"id": "tool-bad", "model": "bad-model", "weight": 9, "enabled": True, "api_url": "https://bad.example/v1", "api_key": "kbad"},
            ],
            "tool_route_channels": {"messages": ["tool-bad", "tool-sf-qwen8b", "tool-sf-glm9b"]},
        },
    }
    targets = resolve_chat_targets(conf, route_kind="tool", route_key="messages", model_override="msg-stable-model")
    assert [t["channel_id"] for t in targets] == ["tool-sf-qwen8b", "tool-sf-glm9b", "tool-bad", None]
    assert targets[0]["model"] == "Qwen/Qwen3-8B"
    assert targets[1]["model"] == "THUDM/GLM-4-9B-0414"


class _FakeResponse:
    def __init__(self, content: str, status_code: int = 200):
        self._content = content
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_siliconflow_chat_falls_back_to_next_channel(monkeypatch):
    _MODEL_ROUTER_COUNTERS.clear()
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "base-model",
        "max_tokens": 1024,
        "model_temperature": 0.3,
        "http_timeout": 5,
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "main_channels": [
                {"id": "m1", "model": "model-1", "weight": 1, "enabled": True, "api_url": "https://m1.example/v1", "api_key": "k1"},
                {"id": "m2", "model": "model-2", "weight": 1, "enabled": True, "api_url": "https://m2.example/v1", "api_key": "k2"},
            ],
            "main_module_channels": {"market": ["m1", "m2"], "default": ["m1"]},
        },
    }
    monkeypatch.setattr(llm_client, "load_ai_config", lambda: conf)
    calls: list[str] = []

    def _fake_post(url, headers, payload, timeout=180, attempts=5, backoff=0.6):  # noqa: ARG001
        calls.append(url)
        if len(calls) == 1:
            raise requests.RequestException("first route failed")
        return _FakeResponse("ok-from-fallback")

    monkeypatch.setattr(llm_client, "_post_with_backoff", _fake_post)
    out = llm_client.siliconflow_chat(
        [{"role": "user", "content": "ping"}],
        route_kind="main",
        route_key="market",
    )
    assert out == "ok-from-fallback"
    assert len(calls) >= 2
    assert calls[0].startswith("https://m1.example/v1")
    assert calls[1].startswith("https://m2.example/v1")


def test_siliconflow_chat_sets_openrouter_headers(monkeypatch):
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "base-model",
        "max_tokens": 1024,
        "model_temperature": 0.3,
        "http_timeout": 5,
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "main_channels": [
                {
                    "id": "openrouter-1",
                    "model": "stepfun/step-3.5-flash:free",
                    "weight": 1,
                    "enabled": True,
                    "api_url": "https://openrouter.ai/api/v1",
                    "api_key": "k-openrouter",
                }
            ],
            "main_module_channels": {"market": ["openrouter-1"], "default": ["openrouter-1"]},
        },
    }
    monkeypatch.setattr(llm_client, "load_ai_config", lambda: conf)
    captured_headers = {}

    def _fake_post(url, headers, payload, timeout=180, attempts=5, backoff=0.6):  # noqa: ARG001
        captured_headers.update(headers)
        return _FakeResponse("ok-openrouter")

    monkeypatch.setattr(llm_client, "_post_with_backoff", _fake_post)
    out = llm_client.siliconflow_chat(
        [{"role": "user", "content": "ping"}],
        route_kind="main",
        route_key="market",
    )
    assert out == "ok-openrouter"
    assert captured_headers.get("HTTP-Referer") == "https://localhost"
    assert captured_headers.get("X-Title") == "Dr.Lemon Information Aggregation AI"


def test_router_runtime_stats_has_remaining_cooldown(monkeypatch):
    llm_client.reset_router_runtime_stats()
    st = llm_client._get_channel_runtime("x-1")
    st["calls"] = 3
    st["success"] = 2
    st["failure"] = 1
    st["cooldown_until"] = llm_client._now_ts() + 30

    out = llm_client.get_router_runtime_stats()
    assert "x-1" in out
    assert out["x-1"]["calls"] == 3
    assert out["x-1"]["cooldown_remaining_sec"] > 0


def test_router_runtime_stats_reset_clears_all():
    st = llm_client._get_channel_runtime("x-2")
    st["calls"] = 9
    assert "x-2" in llm_client.get_router_runtime_stats()
    llm_client.reset_router_runtime_stats()
    assert llm_client.get_router_runtime_stats() == {}


def test_dynamic_weighting_demotes_failing_high_weight_channel():
    llm_client.reset_router_runtime_stats()
    _MODEL_ROUTER_COUNTERS.clear()
    bad = llm_client._get_channel_runtime("bad-heavy")
    bad["calls"] = 8
    bad["success"] = 0
    bad["failure"] = 8
    bad["consecutive_failures"] = 4
    bad["ema_latency_ms"] = 9000
    good = llm_client._get_channel_runtime("good-light")
    good["calls"] = 8
    good["success"] = 8
    good["failure"] = 0
    good["consecutive_failures"] = 0
    good["ema_latency_ms"] = 800
    conf = {
        "api_url": "https://base.example/v1",
        "api_key": "base-key",
        "model": "main-default",
        "model_router": {
            "enabled": True,
            "prefer_router": True,
            "dynamic_weighting": True,
            "latency_ref_ms": 3000,
            "main_channels": [
                {"id": "bad-heavy", "model": "bad-model", "weight": 32, "enabled": True, "api_url": "https://bad.example/v1", "api_key": "kb"},
                {"id": "good-light", "model": "good-model", "weight": 1, "enabled": True, "api_url": "https://good.example/v1", "api_key": "kg"},
            ],
            "main_module_channels": {"market": ["bad-heavy", "good-light"]},
        },
    }
    targets = resolve_chat_targets(conf, route_kind="main", route_key="market", model_override=None)
    assert targets[0]["channel_id"] == "good-light"
