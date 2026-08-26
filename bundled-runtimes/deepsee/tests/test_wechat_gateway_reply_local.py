from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.db import Base
from app.main import create_app
from app.models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionTurn
from app.routers import ai as ai_router
from app.routers import wechat_gateway as wechat_gateway_router
import app.services.reply_generation as reply_generation_service

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "wechat-gateway-reply-local.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(
        engine,
        tables=[
            Chat.__table__,
            Contact.__table__,
            Message.__table__,
            SyncState.__table__,
            WechatSubsession.__table__,
            WechatSubsessionTurn.__table__,
        ],
    )
    return TestingSession


def _client(tmp_path: Path) -> TestClient:
    Session = _session_factory(tmp_path)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    app.dependency_overrides[ai_router.get_db] = override_get_db
    return TestClient(app)


def test_reply_local_is_blocked_when_wechat_trigger_rules_fail(tmp_path):
    client = _client(tmp_path)
    save_resp = client.post(
        "/api/wechat-gateway/trigger-rules",
        headers=API_HEADERS,
        json={
            "enabled": True,
            "smart_reply_enabled": True,
            "group_enabled": True,
            "private_enabled": False,
            "prefixes": ["!"],
            "regexp_patterns": [],
            "at_mention_enabled": False,
            "random_rate": 0,
            "min_text_length": 3,
            "whitelist_chat_ids": ["room_1@chatroom"],
        },
    )
    assert save_resp.status_code == 200

    blocked = client.post(
        "/api/ai/reply-local",
        headers=API_HEADERS,
        json={
            "message_text": "你好",
            "talker_name": "room_1@chatroom",
            "sender_name": "wxid_sender",
            "chat_id": "room_1@chatroom",
            "sender_id": "wxid_sender",
            "is_group": True,
        },
    )
    assert blocked.status_code == 200
    data = blocked.json()
    assert data["status"] == "blocked"
    assert data["reason"] == "prefix_miss"


def test_reply_local_can_pass_wechat_trigger_rules_before_generation(tmp_path, monkeypatch):
    client = _client(tmp_path)
    save_resp = client.post(
        "/api/wechat-gateway/trigger-rules",
        headers=API_HEADERS,
        json={
            "enabled": True,
            "smart_reply_enabled": True,
            "group_enabled": True,
            "private_enabled": True,
            "prefixes": ["!"],
            "regexp_patterns": [],
            "at_mention_enabled": False,
            "random_rate": 0,
            "min_text_length": 2,
        },
    )
    assert save_resp.status_code == 200

    monkeypatch.setattr(reply_generation_service, "load_ai_config", lambda: {"api_key": "***", "tool_model": "fake-model", "tool_prompts": {}})
    monkeypatch.setattr(reply_generation_service, "siliconflow_chat", lambda *args, **kwargs: "已生成回复")

    ok = client.post(
        "/api/ai/reply-local",
        headers=API_HEADERS,
        json={
            "message_text": "!你好",
            "talker_name": "room_1@chatroom",
            "sender_name": "wxid_sender",
            "chat_id": "room_1@chatroom",
            "sender_id": "wxid_sender",
            "is_group": True,
        },
    )
    assert ok.status_code == 200
    data = ok.json()
    assert data["status"] == "ok"
    assert data["reply"] == "已生成回复"


# ── Subsession history injection tests ──

def _seed_subsession_and_turns(session, *, subsession_id="ws_test", chat_id="wxid_abc", sender_id="wxid_sender"):
    """Create a subsession row and some turn history rows."""
    from datetime import datetime
    subsession = WechatSubsession(
        id=subsession_id,
        channel="wechat_gateway",
        name="测试分身",
        enabled=True,
        mode="fixed",
        system_prompt="你是测试分身",
        model_route_kind="tool",
        model_route_key="reply",
        history_max_messages=20,
        history_max_tokens=2000,
        allow_cross_chat_context=True,
        allow_cross_sender_context=True,
    )
    session.add(subsession)
    now = datetime.utcnow()
    turns_data = [
        (chat_id, sender_id, "in", "用户: 你好"),
        (chat_id, sender_id, "out", "助手: 你好！有什么可以帮你的？"),
        (chat_id, sender_id, "in", "用户: 今天天气如何"),
        (chat_id, sender_id, "out", "助手: 抱歉，我暂时无法获取天气信息"),
    ]
    for i, (c, s, d, content) in enumerate(turns_data):
        session.add(WechatSubsessionTurn(
            subsession_id=subsession_id,
            message_id=None,
            chat_id=c,
            sender_id=s,
            direction=d,
            timestamp=now,
            content_text_snapshot=content,
        ))
    session.commit()


def test_build_subsession_history_returns_turns(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        _seed_subsession_and_turns(session, subsession_id="ws_h1", chat_id="wxid_abc", sender_id="wxid_s")

        history = reply_generation_service._build_subsession_history(
            session,
            subsession_id="ws_h1",
            chat_id="wxid_abc",
            sender_id="wxid_s",
            history_max_messages=20,
            history_max_tokens=0,
            allow_cross_chat=True,
            allow_cross_sender=True,
        )
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "用户: 你好"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[3]["role"] == "assistant"
    finally:
        session.close()


def test_build_subsession_history_respects_max_messages(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        _seed_subsession_and_turns(session, subsession_id="ws_h2", chat_id="wxid_abc", sender_id="wxid_s")

        history = reply_generation_service._build_subsession_history(
            session,
            subsession_id="ws_h2",
            chat_id="wxid_abc",
            sender_id="wxid_s",
            history_max_messages=2,
            history_max_tokens=0,
            allow_cross_chat=True,
            allow_cross_sender=True,
        )
        assert len(history) == 2
        assert history[-1]["content"] == "助手: 抱歉，我暂时无法获取天气信息"
    finally:
        session.close()


def test_build_subsession_history_respects_token_budget(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        _seed_subsession_and_turns(session, subsession_id="ws_h3", chat_id="wxid_abc", sender_id="wxid_s")

        history = reply_generation_service._build_subsession_history(
            session,
            subsession_id="ws_h3",
            chat_id="wxid_abc",
            sender_id="wxid_s",
            history_max_messages=20,
            history_max_tokens=5,  # very tight budget
            allow_cross_chat=True,
            allow_cross_sender=True,
        )
        assert len(history) <= 2  # only last entries fit
        if history:
            assert any("抱歉" in t["content"] or "天气" in t["content"] for t in history)
    finally:
        session.close()


def test_build_subsession_history_cross_context_isolation(tmp_path):
    """Turns from other chats are excluded when cross_chat=False."""
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        _seed_subsession_and_turns(session, subsession_id="ws_h4", chat_id="wxid_abc", sender_id="wxid_s")
        # Add a turn from a different chat
        session.add(WechatSubsessionTurn(
            subsession_id="ws_h4", chat_id="wxid_xyz", sender_id="wxid_s",
            direction="in", content_text_snapshot="另一群的用户: 其他消息",
            timestamp=__import__("datetime").datetime.utcnow(),
        ))
        session.commit()

        history = reply_generation_service._build_subsession_history(
            session,
            subsession_id="ws_h4",
            chat_id="wxid_abc",
            sender_id="wxid_s",
            history_max_messages=20,
            history_max_tokens=0,
            allow_cross_chat=False,  # only turns from wxid_abc
            allow_cross_sender=True,
        )
        for t in history:
            assert "另一群" not in t["content"]
    finally:
        session.close()


def test_generate_local_reply_injects_history(tmp_path, monkeypatch):
    """Full integration: reply includes history and execution records history_turns."""
    from datetime import datetime
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        # Seed subsession + turns
        subsession = WechatSubsession(
            id="wechat_gateway_default",
            channel="wechat_gateway",
            name="测试分身",
            enabled=True,
            mode="fixed",
            system_prompt="你是测试分身",
            model_route_kind="tool",
            model_route_key="reply",
            history_max_messages=10,
            history_max_tokens=5000,
            allow_cross_chat_context=True,
            allow_cross_sender_context=True,
        )
        session.add(subsession)
        now = datetime.utcnow()
        session.add(WechatSubsessionTurn(subsession_id="wechat_gateway_default", chat_id="wxid_test", sender_id="wxid_test", direction="in", content_text_snapshot="用户: 之前的问题", timestamp=now))
        session.add(WechatSubsessionTurn(subsession_id="wechat_gateway_default", chat_id="wxid_test", sender_id="wxid_test", direction="out", content_text_snapshot="助手: 之前的回答", timestamp=now))
        # seed trigger rules
        session.add(SyncState(key="wechat_gateway_trigger_rules", value='{"enabled":true,"smart_reply_enabled":true,"group_enabled":true,"private_enabled":true,"prefixes":["ai"],"regexp_patterns":[],"at_mention_enabled":false,"random_rate":0,"min_text_length":2,"human_reply_suppression_seconds":0}'))
        session.commit()

        # Mock LLM call to capture messages
        captured_messages = []
        def fake_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return {"text": "测试回复", "execution": {"final_model": "test-model", "provider": "test", "channel_id": "ch-test", "latency_ms": 100}}

        monkeypatch.setattr(reply_generation_service, "load_ai_config", lambda: {"api_key": "***", "tool_model": "test-model", "tool_prompts": {}})
        monkeypatch.setattr(reply_generation_service, "siliconflow_chat", fake_chat)

        result = reply_generation_service.generate_local_reply(session, {
            "message_text": "ai 新问题",
            "chat_id": "wxid_test",
            "sender_id": "wxid_test",
            "sender_name": "测试",
            "talker_name": "测试",
            "is_group": False,
            "message_time": "2026-05-09T20:00:00",
            "subsession_id": "wechat_gateway_default",
        })

        assert result["status"] == "ok"
        assert result["reply"] == "测试回复"
        assert result["execution"]["history_turns"] == 2
        assert len([m for m in captured_messages if m["role"] == "user"]) >= 2  # history + current
        assert len([m for m in captured_messages if m["role"] == "assistant"]) >= 1
    finally:
        session.close()


def test_generate_local_reply_no_history_when_max_messages_zero(tmp_path, monkeypatch):
    """When history_max_messages=0, no history turns are injected."""
    Session = _session_factory(tmp_path)
    session = Session()
    try:
        subsession = WechatSubsession(
            id="wechat_gateway_default",
            channel="wechat_gateway",
            name="测试分身",
            enabled=True,
            mode="fixed",
            system_prompt="你是测试分身",
            model_route_kind="tool",
            model_route_key="reply",
            history_max_messages=0,
            history_max_tokens=5000,
            allow_cross_chat_context=True,
            allow_cross_sender_context=True,
        )
        session.add(subsession)
        session.add(SyncState(key="wechat_gateway_trigger_rules", value='{"enabled":true,"smart_reply_enabled":true,"group_enabled":true,"private_enabled":true,"prefixes":["ai"],"regexp_patterns":[],"at_mention_enabled":false,"random_rate":0,"min_text_length":2,"human_reply_suppression_seconds":0}'))
        session.commit()

        captured_messages = []
        def fake_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return {"text": "回复", "execution": {}}
        monkeypatch.setattr(reply_generation_service, "load_ai_config", lambda: {"api_key": "***", "tool_model": "test-model", "tool_prompts": {}})
        monkeypatch.setattr(reply_generation_service, "siliconflow_chat", fake_chat)

        result = reply_generation_service.generate_local_reply(session, {
            "message_text": "ai 你好",
            "chat_id": "wxid_test",
            "sender_id": "wxid_test",
            "sender_name": "测试",
            "talker_name": "测试",
            "is_group": False,
            "message_time": "2026-05-09T20:00:00",
            "subsession_id": "wechat_gateway_default",
        })
        assert result["status"] == "ok"
        assert result["execution"]["history_turns"] == 0
        assert len(captured_messages) == 2  # system + user only
    finally:
        session.close()
