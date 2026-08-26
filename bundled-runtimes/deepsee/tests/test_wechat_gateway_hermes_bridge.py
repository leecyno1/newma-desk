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
from app.models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionMembership, WechatSubsessionTurn
from app.routers import wechat_gateway as wechat_gateway_router
from app.services.wechat_gateway import save_config, save_subsession_config, save_trigger_rules

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})


def setup_function():
    import app.services.hermes_bridge as hermes_bridge_service

    hermes_bridge_service._WECHAT_LOCAL_MINIMAX_ENABLED = False
    hermes_bridge_service._WECHAT_HERMES_BACKUP_ENABLED = True
    hermes_bridge_service._WECHAT_FALLBACK_ENABLED = False


def _gateway_payload(**overrides):
    payload = {
        "enabled": True,
        "outbound_enabled": True,
        "allow_chat_ids": [],
        "block_chat_ids": [],
        "keyword_blocklist": [],
        "rate_limit_per_chat_per_minute": 30,
        "outbound_random_delay_min_seconds": 0,
        "outbound_random_delay_max_seconds": 0,
    }
    payload.update(overrides)
    return payload


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "wechat-gateway-hermes-bridge.db"
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


def _private_callback(*, text: str, new_msg_id: int = 202, create_time: int = 1778036763) -> dict:
    return {
        "TypeName": "AddMsg",
        "Appid": "wx_app_test",
        "Wxid": "self_wxid",
        "Data": {
            "MsgId": 101,
            "NewMsgId": new_msg_id,
            "MsgType": 1,
            "CreateTime": create_time,
            "FromUserName": {"string": "wxid_friend"},
            "ToUserName": {"string": "self_wxid"},
            "Content": {"string": text},
        },
    }


def _force_inline_auto_reply(monkeypatch, Session):
    class _ImmediateExecutor:
        def submit(self, fn, *args, **kwargs):
            fn(*args, **kwargs)

            class _DoneFuture:
                def result(self, timeout=None):
                    return None

            return _DoneFuture()

    monkeypatch.setattr(wechat_gateway_router, "SessionLocal", Session, raising=False)
    monkeypatch.setattr(wechat_gateway_router, "_auto_reply_executor", _ImmediateExecutor(), raising=False)


def test_call_hermes_for_reply_resolves_prompt_from_subsession_and_sets_execution_metadata(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_subsession_config(
            db,
            subsession_id="wechat_gateway_default",
            payload={
                "name": "微信工作流分身",
                "system_prompt": "你是 subsession 专属助手，只能按 subsession 规则回答。",
            },
        )
    finally:
        db.close()

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "subsession auto reply"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                "model": "hermes-agent",
            }

    def _fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(hermes_bridge_service, "SessionLocal", Session)
    monkeypatch.setattr(hermes_bridge_service.requests, "post", _fake_post)

    result = hermes_bridge_service.call_hermes_for_reply(
        "ai 进入 subsession",
        subsession_id="wechat_gateway_default",
        chat_id="wxid_friend",
        sender_id="wxid_friend",
        sender_name="好友",
        talker_name="好友",
        is_group=False,
    )

    assert result["status"] == "ok"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][0]["content"] == "你是 subsession 专属助手，只能按 subsession 规则回答。"
    expected_session = "agent:bridge:wechat_gateway:subsession:wechat_gateway_default:chat:wxid_friend"
    assert captured["headers"]["X-Hermes-Session-Id"] == expected_session
    assert result["execution"]["subsession_id"] == "wechat_gateway_default"
    assert result["execution"]["hermes_session_id"] == expected_session
    assert result["execution"]["prompt_source"] == "subsession"
    assert result["execution"]["prompt_hash"]
    assert result["execution"]["fallback_used"] is False


def test_call_hermes_for_reply_uses_local_api_server_key_when_hermes_api_key_missing(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "bridge reply"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                "model": "hermes-agent",
            }

    def _fake_post(url, json, headers, timeout):
        captured["headers"] = headers
        return DummyResponse()

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    (hermes_home / ".env").write_text("API_SERVER_KEY=file-bridge-key\n", encoding="utf-8")

    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(hermes_bridge_service.requests, "post", _fake_post)

    result = hermes_bridge_service.call_hermes_for_reply(
        "ai 你好",
        subsession_id="wechat_gateway_default",
        system_prompt="你是固定 prompt。",
    )

    assert result["status"] == "ok"
    assert captured["headers"]["Authorization"] == "Bearer file-bridge-key"


def test_call_hermes_for_reply_prefers_explicit_hermes_api_key_over_api_server_key(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "bridge reply"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                "model": "hermes-agent",
            }

    def _fake_post(url, json, headers, timeout):
        captured["headers"] = headers
        return DummyResponse()

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    (hermes_home / ".env").write_text("API_SERVER_KEY=file-bridge-key\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_API_KEY", "explicit-client-key")
    monkeypatch.setenv("API_SERVER_KEY", "process-api-server-key")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(hermes_bridge_service.requests, "post", _fake_post)

    result = hermes_bridge_service.call_hermes_for_reply(
        "ai 你好",
        subsession_id="wechat_gateway_default",
        system_prompt="你是固定 prompt。",
    )

    assert result["status"] == "ok"
    assert captured["headers"]["Authorization"] == "Bearer explicit-client-key"


def test_call_hermes_for_reply_appends_brief_followup_and_no_long_paraphrase_constraints(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "bridge reply"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                "model": "hermes-agent",
            }

    def _fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(hermes_bridge_service.requests, "post", _fake_post)

    result = hermes_bridge_service.call_hermes_for_reply(
        "对方刚回复了进展",
        subsession_id="wechat_gateway_default",
        system_prompt="你是固定 prompt。",
    )

    assert result["status"] == "ok"
    user_content = captured["json"]["messages"][-1]["content"]
    assert "优先顺着对方最新一句继续交流" in user_content
    assert "若对方已经回答了上一轮问题，默认不要继续追问" in user_content
    assert "更适合简短确认或致谢时，直接回复“收到/好的/明白/谢谢”" in user_content
    assert "不要大段复述对方原话" in user_content
    assert "如需总结，只允许用1-2句话提炼" in user_content


def test_call_hermes_for_reply_fail_closed_without_silent_fallback(monkeypatch):
    import requests
    import app.services.hermes_bridge as hermes_bridge_service

    def _boom(*args, **kwargs):
        raise requests.HTTPError("provider timeout")

    monkeypatch.setattr(hermes_bridge_service, "_call_hermes_api", _boom)
    monkeypatch.setattr(hermes_bridge_service, "_WECHAT_LOCAL_MINIMAX_ENABLED", False)
    monkeypatch.setattr(hermes_bridge_service, "_FALLBACK_ENABLED", False)
    monkeypatch.setattr(hermes_bridge_service, "_session_freshness_suffix", lambda chat_id: "")

    result = hermes_bridge_service.call_hermes_for_reply(
        "ai 你好",
        subsession_id="wechat_gateway_default",
        chat_id="wxid_friend",
        sender_id="wxid_friend",
        system_prompt="你是固定 prompt。",
    )

    assert result["status"] == "error"
    assert result["error"] == "provider timeout"
    assert result["execution"]["route_key"] == "wechat_gateway"
    assert result["execution"]["subsession_id"] == "wechat_gateway_default"
    assert result["execution"]["hermes_session_id"] == "agent:bridge:wechat_gateway:subsession:wechat_gateway_default:chat:wxid_friend"
    assert result["execution"]["prompt_source"] == "explicit"
    assert result["execution"]["prompt_hash"]
    assert result["execution"]["fallback_used"] is False


def test_call_hermes_for_reply_handles_identity_questions_without_model_call(monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    def _unexpected_model(*args, **kwargs):
        raise AssertionError("Identity replies must not call a model")

    monkeypatch.setattr(hermes_bridge_service, "_call_local_minimax_route", _unexpected_model)

    result = hermes_bridge_service.call_hermes_for_reply("你是人工还是AI在回复？")

    assert result["status"] == "ok"
    assert result["reply"] == "程胤团队这边回的"
    assert result["execution"]["route_kind"] == "wechat_deterministic"
    assert result["execution"]["final_model"] == "none"


def test_call_hermes_for_reply_does_not_fallback_to_hermes_when_minimax_route_fails(monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    def _minimax_error(*args, **kwargs):
        return {
            "status": "error",
            "error": "m3 exhausted",
            "execution": {"channel_id": "tool-minimax-m3"},
        }

    def _unexpected_hermes(*args, **kwargs):
        raise AssertionError("Hermes API should not be used for WeChat when M3 is enabled")

    monkeypatch.setattr(hermes_bridge_service, "_call_local_minimax_route", _minimax_error)
    monkeypatch.setattr(hermes_bridge_service, "_call_hermes_api", _unexpected_hermes)
    monkeypatch.setattr(hermes_bridge_service, "_WECHAT_LOCAL_MINIMAX_ENABLED", True)
    monkeypatch.setattr(hermes_bridge_service, "_WECHAT_HERMES_BACKUP_ENABLED", False)
    monkeypatch.setattr(hermes_bridge_service, "_WECHAT_FALLBACK_ENABLED", False)

    result = hermes_bridge_service.call_hermes_for_reply(
        "ai 你好",
        subsession_id="wechat_gateway_default",
        chat_id="wxid_friend",
        sender_id="wxid_friend",
        system_prompt="你是固定 prompt。",
    )

    assert result["status"] == "error"
    assert result["error"] == "m3 exhausted"
    assert result["execution"]["route_kind"] == "wechat_minimax_m3"
    assert result["execution"]["route_key"] == "reply"
    assert result["execution"]["channel_id"] == "tool-minimax-m3"
    assert result["execution"]["configured_model"] == "MiniMax-M3"
    assert result["execution"]["fallback_used"] is False
    assert result["execution"]["hermes_backup_enabled"] is False


def test_call_hermes_for_reply_does_not_escalate_to_hermes_when_m3_route_fails(monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    called = False

    def _m3_failure(*args, **kwargs):
        return {"status": "error", "error": "MiniMax-M3 unavailable", "execution": {}}

    def _hermes_call(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Hermes must not run after an M3 route failure")

    monkeypatch.setattr(hermes_bridge_service, "_WECHAT_LOCAL_MINIMAX_ENABLED", True)
    monkeypatch.setattr(hermes_bridge_service, "_call_local_minimax_route", _m3_failure)
    monkeypatch.setattr(hermes_bridge_service, "_call_hermes_api", _hermes_call)

    result = hermes_bridge_service.call_hermes_for_reply("ai 你好")

    assert result["status"] == "error"
    assert result["error"] == "MiniMax-M3 unavailable"
    assert called is False


def test_call_hermes_for_reply_scopes_session_to_subsession_not_contact(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_subsession_config(
            db,
            subsession_id="wechat_gateway_default",
            payload={
                "name": "微信工作流分身",
                "system_prompt": "你是 subsession 专属助手，只能按 subsession 规则回答。",
            },
        )
    finally:
        db.close()

    session_ids = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "subsession auto reply"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                "model": "hermes-agent",
            }

    def _fake_post(url, json, headers, timeout):
        session_ids.append(headers["X-Hermes-Session-Id"])
        return DummyResponse()

    monkeypatch.setattr(hermes_bridge_service, "SessionLocal", Session)
    monkeypatch.setattr(hermes_bridge_service.requests, "post", _fake_post)

    first = hermes_bridge_service.call_hermes_for_reply(
        "ai 第一位联系人",
        subsession_id="wechat_gateway_default",
        chat_id="wxid_friend_a",
        sender_id="wxid_friend_a",
        sender_name="好友A",
        talker_name="好友A",
        is_group=False,
    )
    second = hermes_bridge_service.call_hermes_for_reply(
        "ai 第二位联系人",
        subsession_id="wechat_gateway_default",
        chat_id="wxid_friend_b",
        sender_id="wxid_friend_b",
        sender_name="好友B",
        talker_name="好友B",
        is_group=False,
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    # 每个联系人拥有独立 session，避免跨联系人上下文污染
    assert session_ids == [
        "agent:bridge:wechat_gateway:subsession:wechat_gateway_default:chat:wxid_friend_a",
        "agent:bridge:wechat_gateway:subsession:wechat_gateway_default:chat:wxid_friend_b",
    ]


def test_callback_auto_reply_uses_only_subsession_id_for_hermes_bridge_and_persists_execution(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_config(
            db,
            _gateway_payload(
                token="***",
                app_id="wx_app_test",
                sessionized_reply_enabled=True,
                fixed_subsession_enabled=True,
                fixed_subsession_id="wechat_gateway_default",
                fixed_subsession_name="微信工作流分身",
                auto_learn_subsession_members=True,
            ),
        )
        save_subsession_config(
            db,
            subsession_id="wechat_gateway_default",
            payload={
                "name": "微信工作流分身",
                "system_prompt": "你是 subsession 专属助手，只能按 subsession 规则回答。",
            },
        )
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "at_mention_enabled": False,
                "prefixes": ["ai"],
                "min_text_length": 2,
            },
        )
    finally:
        db.close()

    captured = {}

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def send_text(self, to_wxid: str, text: str):
            return {"ret": 200, "msg": "操作成功", "data": {"toWxid": to_wxid, "msgId": 11, "newMsgId": 22, "type": 1}}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def _capture_hermes_reply(message_text: str, **kwargs):
        captured["message_text"] = message_text
        captured.update(kwargs)
        return {
            "status": "ok",
            "reply": "subsession auto reply",
            "execution": {
                "route_kind": "hermes_api_server",
                "route_key": "wechat_gateway",
                "subsession_id": kwargs.get("subsession_id"),
                "hermes_session_id": "agent:bridge:wechat_gateway:subsession:wechat_gateway_default",
                "prompt_hash": "abc123def456",
                "fallback_used": False,
            },
        }

    monkeypatch.setattr(hermes_bridge_service, "call_hermes_for_reply", _capture_hermes_reply)
    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    _force_inline_auto_reply(monkeypatch, Session)

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/api/wechat-gateway/callback", json=_private_callback(text="ai 进入 subsession", new_msg_id=1303), headers=API_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["stored"] is True
    assert data["auto_reply"]["status"] == "queued"
    assert data["auto_reply"]["message_id"] > 0
    assert data["subsession_id"] == "wechat_gateway_default"
    assert captured["subsession_id"] == "wechat_gateway_default"
    assert captured.get("system_prompt") is None

    verify = Session()
    try:
        rows = verify.query(Message).order_by(Message.id.asc()).all()
        assert len(rows) == 2
        outbound = rows[1]
        execution = ((outbound.meta or {}).get("auto_reply") or {}).get("execution") or {}
        assert execution["subsession_id"] == "wechat_gateway_default"
        assert execution["hermes_session_id"] == "agent:bridge:wechat_gateway:subsession:wechat_gateway_default"
        assert execution["prompt_hash"] == "abc123def456"
        assert execution["fallback_used"] is False
    finally:
        verify.close()


def test_callback_auto_reply_fail_closed_returns_error_and_sends_nothing(tmp_path, monkeypatch):
    import app.services.hermes_bridge as hermes_bridge_service

    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_config(
            db,
            _gateway_payload(token="***", app_id="wx_app_test"),
        )
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "at_mention_enabled": False,
                "prefixes": ["ai"],
                "min_text_length": 2,
            },
        )
    finally:
        db.close()

    send_calls = []

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def send_text(self, to_wxid: str, text: str):
            send_calls.append((to_wxid, text))
            return {"ret": 200, "msg": "操作成功", "data": {"toWxid": to_wxid, "msgId": 11, "newMsgId": 22, "type": 1}}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(
        hermes_bridge_service,
        "call_hermes_for_reply",
        lambda message_text, **kwargs: {
            "status": "error",
            "error": "provider timeout",
            "execution": {
                "route_kind": "hermes_api_server",
                "route_key": "wechat_gateway",
                "subsession_id": kwargs.get("subsession_id"),
                "hermes_session_id": "agent:bridge:wechat_gateway:subsession:wechat_gateway_default",
                "prompt_hash": "deadbeefcafe",
                "fallback_used": False,
                "error": "provider timeout",
            },
        },
    )
    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    _force_inline_auto_reply(monkeypatch, Session)

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/api/wechat-gateway/callback", json=_private_callback(text="ai 你好", new_msg_id=1404), headers=API_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["stored"] is True
    assert data["auto_reply"]["status"] == "queued"
    assert data["auto_reply"]["message_id"] > 0
    assert send_calls == []

    verify = Session()
    try:
        rows = verify.query(Message).order_by(Message.id.asc()).all()
        assert len(rows) == 1
        assert rows[0].direction == "in"
    finally:
        verify.close()
