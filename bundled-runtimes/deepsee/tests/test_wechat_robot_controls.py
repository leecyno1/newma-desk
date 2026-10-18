from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionTurn, WechatSubsessionMembership
from app.routers import wechat_gateway as routes
from app.services.wechat_gateway import evaluate_auto_reply_rules, load_trigger_rules, save_trigger_rules, save_config
from app.services.wechat_auto_reply_transaction import AutoReplyAdapters, execute_wechat_auto_reply_transaction


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'robot.db'}")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in (
        Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionTurn, WechatSubsessionMembership)])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        save_config(db, {"enabled": True, "outbound_enabled": True})
        db.add(Chat(id="friend", title="测试好友"))
        db.add(Message(id=1, chat_id="friend", sender_id="friend", direction="in", type="text",
                       content_text="ai hello", timestamp=datetime.now(), meta={}))
        db.commit()
    yield factory
    engine.dispose()


def evaluate(db, **kwargs):
    return evaluate_auto_reply_rules(db, chat_id="friend", sender_id="friend", text="ai hello", is_group=False, **kwargs)


@pytest.mark.parametrize("hour,allowed", [(13, False), (14, True), (17, True), (18, False), (23, False)])
def test_overnight_beijing_schedule(sessions, hour, allowed):
    with sessions() as db:
        save_trigger_rules(db, {"schedule_enabled": True, "schedule_start": "22:00", "schedule_end": "02:00"})
        result = evaluate(db, now=datetime(2026, 10, 16, hour, tzinfo=timezone.utc))
        assert result["allowed"] is allowed


def test_blocked_keyword_and_strict_mention(sessions):
    with sessions() as db:
        save_trigger_rules(db, {"blocked_keywords": ["HELLO"]})
        assert evaluate(db)["reason"] == "input_keyword_blocked"
        save_trigger_rules(db, {"blocked_keywords": [], "group_require_mention": True})
        assert evaluate(db)["allowed"]
        result = evaluate_auto_reply_rules(db, chat_id="room@chatroom", sender_id="friend", text="ai hi", is_group=True)
        assert result["reason"] == "group_mention_required"


def test_invalid_fixed_reply_and_time_rejected(sessions):
    with sessions() as db:
        with pytest.raises(ValueError):
            save_trigger_rules(db, {"reply_mode": "fixed", "fixed_reply_text": " "})
        with pytest.raises(ValueError):
            save_trigger_rules(db, {"schedule_enabled": True, "schedule_start": "25:00"})
        assert load_trigger_rules(db)["reply_mode"] == "ai"


def unexpected(*args, **kwargs):
    raise AssertionError("must not invoke real generation or sending")


def test_fixed_preview_never_creates_client_or_calls_ai(sessions):
    with sessions() as db:
        save_trigger_rules(db, {"reply_mode": "fixed", "fixed_reply_text": "收到 https://example.com", "delivery_mode": "preview"})
        save_config(db, {"outbound_enabled": False})
    result = execute_wechat_auto_reply_transaction(1, session_factory=sessions,
        adapters=AutoReplyAdapters(generate_reply=unexpected, client_factory=unexpected))
    assert result.status == "preview"
    assert result.execution["reply_preview"] == "收到 https://example.com"
    with sessions() as db:
        assert db.query(Message).count() == 1


def test_long_fixed_reply_is_blocked_not_truncated(sessions):
    with sessions() as db:
        save_trigger_rules(db, {"reply_mode": "fixed", "fixed_reply_text": "https://example.com", "max_reply_chars": 5})
    result = execute_wechat_auto_reply_transaction(1, session_factory=sessions,
        adapters=AutoReplyAdapters(generate_reply=unexpected, client_factory=unexpected))
    assert result.reason == "reply_too_long"


def test_ai_preview_passes_custom_instructions_without_sending(sessions):
    with sessions() as db:
        save_trigger_rules(db, {"delivery_mode": "preview", "reply_system_prompt": "只回答可核实的信息"})
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "reply": "这是模拟的 AI 回复"}
    result = execute_wechat_auto_reply_transaction(1, session_factory=sessions,
        adapters=AutoReplyAdapters(generate_reply=generate, client_factory=unexpected))
    assert result.status == "preview"
    assert calls[0]["system_prompt"] == "只回答可核实的信息"
    assert result.execution["reply_preview"] == "这是模拟的 AI 回复"


@pytest.mark.parametrize("change", ["pause", "preview", "gateway"])
def test_setting_changed_during_delay_cancels_delivery(sessions, change):
    with sessions() as db:
        save_trigger_rules(db, {"reply_mode": "fixed", "fixed_reply_text": "收到"})

    class Client:
        def configured(self):
            return True
        send_text = unexpected

    def delay(config):
        with sessions() as other:
            if change == "gateway":
                save_config(other, {"enabled": False})
            else:
                save_trigger_rules(other, {"smart_reply_enabled": False} if change == "pause" else {"delivery_mode": "preview"})
        return 0

    result = execute_wechat_auto_reply_transaction(1, session_factory=sessions,
        adapters=AutoReplyAdapters(generate_reply=unexpected, apply_delay=delay, client_factory=lambda **kw: Client()))
    assert result.reason == "policy_changed_before_send"
    assert result.status == "blocked"


def test_simulator_does_not_save_rules_or_call_external_services(sessions, monkeypatch):
    monkeypatch.setattr(routes, "WechatApiClient", unexpected)
    app = FastAPI()
    app.include_router(routes.router)
    def get_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[routes.get_db] = get_db
    client = TestClient(app)
    response = client.post("/api/wechat-gateway/robot-simulate", json={"text": "ai hello",
        "rules": {"reply_mode": "fixed", "fixed_reply_text": "收到"}})
    assert response.status_code == 200
    assert response.json()["reply_preview"] == "收到"
    assert response.json()["sends_message"] is False
    with sessions() as db:
        assert load_trigger_rules(db)["reply_mode"] == "ai"
        assert db.query(Message).count() == 1


def test_preview_is_visible_in_activity(sessions, monkeypatch):
    with sessions() as db:
        save_trigger_rules(db, {"reply_mode": "fixed", "fixed_reply_text": "收到", "delivery_mode": "preview"})
    monkeypatch.setattr(routes, "WechatApiClient", unexpected)
    routes._run_auto_reply_for_message(1, sessions)
    with sessions() as db:
        item = routes.get_robot_activity(db)["items"][0]
        assert item["status"] == "preview"
        assert item["reply_preview"] == "收到"


@pytest.mark.parametrize("draft", [
    {"regexp_patterns": ["["]},
    {"reply_mode": "fixed", "fixed_reply_text": " "},
    {"schedule_enabled": True, "schedule_end": "99:00"},
    ["invalid rules"],
])
def test_invalid_draft_is_rejected_without_persisting(sessions, draft):
    app = FastAPI()
    app.include_router(routes.router)
    def get_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[routes.get_db] = get_db
    client = TestClient(app)
    with sessions() as db:
        before = load_trigger_rules(db)
    assert client.post("/api/wechat-gateway/robot-simulate", json={"text": "ai hello", "rules": draft}).status_code == 422
    if isinstance(draft, dict):
        assert client.post("/api/wechat-gateway/trigger-rules", json=draft).status_code == 422
    with sessions() as db:
        assert load_trigger_rules(db) == before


def test_draft_simulator_checks_fixed_reply_length(sessions):
    with sessions() as db:
        result = routes.simulate_robot({"text": "ai hello", "rules": {
            "reply_mode": "fixed", "fixed_reply_text": "https://example.com", "max_reply_chars": 5,
        }}, db)
        assert result["allowed"] is False
        assert result["reason"] == "reply_too_long"
        assert result["reply_preview"] is None
        assert result["simulation_scope"] == "draft"
        assert result["sends_message"] is False
        assert load_trigger_rules(db)["reply_mode"] == "ai"


def test_emergency_pause_works_with_invalid_legacy_rules(sessions):
    import json
    from app.services.wechat_gateway import TRIGGER_RULES_KEY
    with sessions() as db:
        db.add(SyncState(key=TRIGGER_RULES_KEY, value=json.dumps({"regexp_patterns": ["["]})))
        db.commit()
        result = save_trigger_rules(db, {"smart_reply_enabled": False})
        assert result["smart_reply_enabled"] is False
        assert result["regexp_patterns"] == ["["]
