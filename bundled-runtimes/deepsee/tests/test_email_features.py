import re
import types
import os
import sys

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Prevent accidental real LLM calls in tests by patching the client layer."""
    from app.services import ai_tools

    def _fake_tool_chat(*args, **kwargs):  # pragma: no cover - safety net
        raise RuntimeError("siliconflow_tool_chat should not be called in unit tests")

    monkeypatch.setattr("app.services.llm_client.siliconflow_tool_chat", _fake_tool_chat)
    yield


def test_build_email_features_uses_tool_summary_when_available(monkeypatch):
    from app.services import email_features

    captured_messages = {}

    def fake_extract_message_features(messages, batch_size=8, concurrency=3, temperature=0.1, **kwargs):
        # Capture the content passed into the tool to ensure it does not include the subject line
        assert isinstance(messages, list) and messages, "expected non-empty messages list"
        m0 = messages[0]
        content = m0.get("content") or ""
        # Ensure subject is not embedded (should be strictly based on body)
        assert "主题:" not in content
        assert "正文:" in content
        captured_messages["content"] = content
        return {
            "1": {
                # Simulate a good tool summary based on body text
                "summary": "ai: 正文中的核心观点：中兴通讯会议更新；会议号491436856",
                "meeting_number": "491436856",
                "tone": "neutral",
                "confidence": 0.9,
            }
        }

    # Patch the symbol that email_features.py imported at module load time
    monkeypatch.setattr("app.services.email_features.extract_message_features", fake_extract_message_features)

    items = [
        {
            "id": 1,
            "from_addr": "report@hysec.com",
            "subject": "更新: 华源电子&南方 | 中兴通讯汇报(华源证券)(S37396) | 腾讯:491436856 | 10/27 16:40",
            "body_text": "观点：中兴通讯交换机订单改善，AI 交换机出货提速；建议跟踪 Q4 海外交付。会议号：491436856",
            "snippet": "检测当前小模型的生成规则（标题重复问题演示）",
        }
    ]

    out = email_features.build_email_features(items)
    assert "1" in out
    feat = out["1"]
    # summary: must use tool summary (ai: 前缀) rather than any subject-derived text
    assert feat.get("summary", "").startswith("ai: ")
    assert "正文中的核心观点" in feat["summary"], "summary should be based on body"
    # key_info should reflect tool/body content (not the subject)
    key_info = feat.get("key_info", "")
    assert key_info and len(key_info) <= 30
    assert "华源电子&南方" not in key_info
    # meeting number propagated
    assert feat.get("meeting_number") == "491436856"
    # origin marks tool
    assert feat.get("summary_origin") == "tool"


def test_build_email_features_fallback_avoids_title_monkeypatch(monkeypatch):
    from app.services import email_features

    # Tool returns nothing -> trigger fallback path only
    def fake_extract_message_features(messages, batch_size=8, concurrency=3, temperature=0.1, **kwargs):
        return {}

    monkeypatch.setattr("app.services.email_features.extract_message_features", fake_extract_message_features)

    items = [
        {
            "id": 2,
            "from_addr": "report@hysec.com",
            "subject": "更新: 华源电子&南方 | 中兴通讯汇报",
            "body_text": "观点：重点关注中兴通讯政企业务拐点；预计 Q4 回暖。",
            "snippet": "标题不应出现在摘要中",
        }
    ]

    out = email_features.build_email_features(items)
    f = out["2"]
    # Fallback summary_full should be derived from body text
    assert "summary_full" in f
    assert "政企业务拐点" in f["summary_full"]
    # Fallback short summary shouldn't be a raw title echo (we don't assert exact string, just that title not forced)
    assert "华源电子&南方" not in (f.get("key_info") or "")


def test_build_email_features_skips_short_content(monkeypatch):
    from app.services import email_features

    def fake_extract_message_features(messages, **kwargs):
        raise AssertionError("short email content must not be sent to the tool model")

    monkeypatch.setattr("app.services.email_features.extract_message_features", fake_extract_message_features)

    out = email_features.build_email_features([
        {
            "id": 3,
            "from_addr": "a@example.com",
            "subject": "",
            "body_text": "短邮件不摘要",
            "snippet": "",
        }
    ])

    assert out == {}


def test_build_email_fallback_features_skips_short_content():
    from app.services import email_features

    out = email_features.build_email_fallback_features([
        {
            "id": 4,
            "subject": "",
            "body_text": "短邮件不摘要",
            "snippet": "",
        }
    ])

    assert out == {}
