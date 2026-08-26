from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionMembership, WechatSubsessionTurn
from app.services.wechat_gateway import save_trigger_rules


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "reply-generation-local-fallback.db"
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
            WechatSubsessionMembership.__table__,
            WechatSubsessionTurn.__table__,
        ],
    )
    return TestingSession


def test_generate_local_reply_prefers_subsession_prompt_and_route_over_global(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
            },
        )
        db.add(
            WechatSubsession(
                id="wechat_gateway_default",
                channel="wechat_gateway",
                name="微信工作流分身",
                enabled=True,
                mode="fixed",
                system_prompt="你是 subsession 专属助手，只能按 subsession 规则回答。",
                model_route_kind="tool",
                model_route_key="reply_subsession",
                model_override="subsession-model",
            )
        )
        db.commit()
    finally:
        db.close()

    import app.services.reply_generation as reply_generation_service

    monkeypatch.setattr(
        reply_generation_service,
        "load_ai_config",
        lambda: {
            "api_key": "***",
            "tool_model": "global-model",
            "tool_prompts": {
                "reply_da": {
                    "system": "全局 system prompt",
                    "user": "全局用户模板：{{message_text}}",
                }
            },
        },
    )
    captured = {}

    def _fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "subsession reply"

    monkeypatch.setattr(reply_generation_service, "siliconflow_chat", _fake_chat)

    verify = Session()
    try:
        result = reply_generation_service.generate_local_reply(
            verify,
            {
                "message_text": "ai 请按 subsession 回复",
                "chat_id": "room_a@chatroom",
                "sender_id": "wxid_sender_a",
                "sender_name": "发送者A",
                "talker_name": "群A",
                "is_group": True,
                "subsession_id": "wechat_gateway_default",
            },
        )
        assert result["status"] == "ok"
        assert result["reply"] == "subsession reply"
        assert result["subsession_id"] == "wechat_gateway_default"
        assert result["prompt_key"] == "reply_da"
        assert captured["messages"][0]["content"] == "你是 subsession 专属助手，只能按 subsession 规则回答。"
        assert captured["messages"][1]["content"] == "全局用户模板：ai 请按 subsession 回复"
        assert captured["kwargs"]["model_override"] == "subsession-model"
        assert captured["kwargs"]["route_kind"] == "tool"
        assert captured["kwargs"]["route_key"] == "reply_subsession"
    finally:
        verify.close()


def test_generate_local_reply_returns_execution_metadata_for_subsession_route(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
            },
        )
        db.add(
            WechatSubsession(
                id="wechat_gateway_default",
                channel="wechat_gateway",
                name="微信工作流分身",
                enabled=True,
                mode="fixed",
                system_prompt="你是 subsession 专属助手，只能按 subsession 规则回答。",
                model_route_kind="tool",
                model_route_key="reply_subsession",
                model_override="subsession-model",
            )
        )
        db.commit()
    finally:
        db.close()

    import app.services.reply_generation as reply_generation_service

    monkeypatch.setattr(
        reply_generation_service,
        "load_ai_config",
        lambda: {
            "api_key": "***",
            "tool_model": "global-model",
            "tool_prompts": {
                "reply_da": {
                    "system": "全局 system prompt",
                    "user": "全局用户模板：{{message_text}}",
                }
            },
        },
    )

    def _fake_chat(messages, **kwargs):
        return {
            "text": "subsession reply",
            "execution": {
                "route_kind": kwargs.get("route_kind"),
                "route_key": kwargs.get("route_key"),
                "final_model": "resolved-subsession-model",
                "provider": "api.siliconflow.cn",
                "channel_id": "tool-reply-primary",
            },
        }

    monkeypatch.setattr(reply_generation_service, "siliconflow_chat", _fake_chat)

    verify = Session()
    try:
        result = reply_generation_service.generate_local_reply(
            verify,
            {
                "message_text": "ai 请按 subsession 回复",
                "chat_id": "room_a@chatroom",
                "sender_id": "wxid_sender_a",
                "sender_name": "发送者A",
                "talker_name": "群A",
                "is_group": True,
                "subsession_id": "wechat_gateway_default",
            },
        )
        assert result["status"] == "ok"
        assert result["reply"] == "subsession reply"
        assert result["execution"]["route_kind"] == "tool"
        assert result["execution"]["route_key"] == "reply_subsession"
        assert result["execution"]["configured_model"] == "subsession-model"
        assert result["execution"]["final_model"] == "resolved-subsession-model"
        assert result["execution"]["provider"] == "api.siliconflow.cn"
        assert result["execution"]["channel_id"] == "tool-reply-primary"
    finally:
        verify.close()
