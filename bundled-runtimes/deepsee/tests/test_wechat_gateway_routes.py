from __future__ import annotations

import inspect
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.main import create_app
from app.config import settings
from app.db import Base
from app.models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionMembership, WechatSubsessionTurn
from app.routers import wechat_gateway as wechat_gateway_router
from app.routers import messages as messages_router
from app.services.wechat_gateway import save_config, save_subsession_config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})


def test_create_app_includes_wechat_gateway_routes():
    app = create_app()
    paths = {getattr(route, 'path', '') for route in app.routes}
    assert '/api/wechat-gateway/config' in paths
    assert '/api/wechat-gateway/trigger-rules' in paths
    assert '/api/wechat-gateway/callback' in paths


def test_wechat_gateway_callback_uses_async_serial_ingest_worker():
    assert inspect.iscoroutinefunction(wechat_gateway_router.receive_wechat_gateway_callback)
    assert wechat_gateway_router._callback_ingest_executor._max_workers == 1


def test_create_app_includes_wechat_gateway_bind_callback_route():
    app = create_app()
    paths = {getattr(route, 'path', '') for route in app.routes}
    assert '/api/wechat-gateway/bind-callback' in paths


def test_bind_callback_route_calls_wechatapi_client(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-bind.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "token": "***",
            "app_id": "wx_app_test",
            "callback_public_url": "https://customer.example/api/wechat-gateway/callback",
        })
    finally:
        db.close()

    calls = []

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def set_callback(self, callback_url: str):
            calls.append(callback_url)
            return {"ret": "200", "msg": "ok"}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/api/wechat-gateway/bind-callback", headers=API_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["callback_url"] == "https://customer.example/api/wechat-gateway/callback"
    assert calls == ["https://customer.example/api/wechat-gateway/callback"]


def test_bind_callback_route_appends_default_callback_path_when_public_url_is_origin_only(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-bind-origin.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "token": "***",
            "app_id": "wx_app_test",
            "callback_public_url": "https://customer.example",
        })
    finally:
        db.close()

    calls = []

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def set_callback(self, callback_url: str):
            calls.append(callback_url)
            return {"ret": "200", "msg": "ok"}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/api/wechat-gateway/bind-callback", headers=API_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["callback_url"] == "https://customer.example/api/wechat-gateway/callback"
    assert calls == ["https://customer.example/api/wechat-gateway/callback"]


def test_agent_event_route_merges_into_messages_api(tmp_path):
    db_path = tmp_path / "wechat-gateway-agent-route.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    app.dependency_overrides[messages_router.get_db] = override_get_db
    client = TestClient(app)

    event = {
        "channel": "wechat",
        "source": "openclaw",
        "message_id": "route-agent-msg-1",
        "chat_id": "room_route@chatroom",
        "sender_id": "wxid_route_sender",
        "sender_name": "路由测试",
        "text": "从 agent websocket/HTTP 进入微信聚合",
        "is_group": True,
    }

    ingested = client.post("/api/wechat-gateway/agent-event", json=event, headers=API_HEADERS)
    assert ingested.status_code == 200
    assert ingested.json()["stored"] is True

    listed = client.get("/api/messages", params={"chat_id": "room_route@chatroom", "fast": "true"}, headers=API_HEADERS)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["content_text"] == "从 agent websocket/HTTP 进入微信聚合"
    assert item["meta"]["source"] == "wechat_gateway"
    assert item["meta"]["agent_source"] == "openclaw"


def test_wechatapi_callback_queues_incremental_contact_prediction_refresh(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-contact-scoring.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    queued: list[tuple[object, tuple[object, ...]]] = []

    class CapturingExecutor:
        def submit(self, fn, *args, **kwargs):
            queued.append((fn, args))
            return None

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "_contact_scoring_executor", CapturingExecutor(), raising=False)
    monkeypatch.setattr(wechat_gateway_router, "_auto_reply_executor", CapturingExecutor())
    monkeypatch.setattr(wechat_gateway_router, "SessionLocal", Session, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "TypeName": "AddMsg",
        "Appid": "wx_app_test",
        "Wxid": "self_wxid",
        "Data": {
            "MsgId": 901,
            "NewMsgId": 902,
            "MsgType": 1,
            "CreateTime": 1783951200,
            "FromUserName": {"string": "wxid_stock_sender"},
            "ToUserName": {"string": "self_wxid"},
            "Content": {"string": "继续看好宁德时代，未来一个月有望上涨。"},
            "MsgSource": "<msgsource></msgsource>",
        },
    }

    response = client.post("/api/wechat-gateway/callback", json=payload, headers=API_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["stored"] is True
    assert data["contact_scoring"] == {"status": "queued", "message_id": data["message_id"]}
    scoring_jobs = [item for item in queued if getattr(item[0], "__name__", "") == "_refresh_contact_prediction_for_message"]
    assert len(scoring_jobs) == 1
    assert scoring_jobs[0][0] is wechat_gateway_router._refresh_contact_prediction_for_message
    assert scoring_jobs[0][1][0] == data["message_id"]
    assert callable(scoring_jobs[0][1][1])


def test_agent_send_text_route_sends_through_wechatapi_gateway(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-agent-send.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "enabled": True,
            "outbound_enabled": True,
            "token": "token-x",
            "app_id": "wx_app_test",
            "outbound_random_delay_min_seconds": 0,
            "outbound_random_delay_max_seconds": 0,
        })
    finally:
        db.close()

    calls = []

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def send_text(self, to_wxid: str, text: str):
            calls.append((to_wxid, text))
            return {"ret": "200", "msg": "ok", "data": {"msgId": 10, "newMsgId": 20, "toWxid": to_wxid}}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post(
        "/api/wechat-gateway/agent-send-text",
        json={"channel": "wechat", "source": "hermes", "target": "wxid_friend", "text": "受控发送"},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["sent"] is True
    assert data["provider"] == "wechatapi_gateway"
    assert calls == [("wxid_friend", "受控发送")]

    verify = Session()
    try:
        rows = verify.query(Message).all()
        assert len(rows) == 1
        assert rows[0].direction == "out"
        assert rows[0].chat_id == "wxid_friend"
        assert rows[0].content_text == "受控发送"
        assert rows[0].meta["source"] == "wechat_gateway"
        assert rows[0].meta["agent_source"] == "hermes"
    finally:
        verify.close()


def test_agent_send_text_route_ignores_non_wechat_channel(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-agent-send-ignore.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    calls = []

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def send_text(self, to_wxid: str, text: str):
            calls.append((to_wxid, text))
            return {"ret": "200"}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post(
        "/api/wechat-gateway/agent-send-text",
        json={"channel": "main", "source": "hermes", "target": "terminal", "text": "不要发微信"},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "non_wechat_channel"
    assert response.json()["sent"] is False
    assert calls == []


def test_wechat_gateway_config_roundtrip_includes_subsession_fields(tmp_path):
    db_path = tmp_path / "wechat-gateway-subsession-config.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
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
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "enabled": True,
        "outbound_enabled": True,
        "sessionized_reply_enabled": True,
        "fixed_subsession_enabled": True,
        "fixed_subsession_id": "wechat_gateway_default",
        "fixed_subsession_name": "微信工作流分身",
        "auto_learn_subsession_members": True,
    }

    saved = client.post("/api/wechat-gateway/config", json=payload, headers=API_HEADERS)
    assert saved.status_code == 200
    body = saved.json()["config"]
    assert body["sessionized_reply_enabled"] is True
    assert body["fixed_subsession_enabled"] is True
    assert body["fixed_subsession_id"] == "wechat_gateway_default"
    assert body["fixed_subsession_name"] == "微信工作流分身"
    assert body["auto_learn_subsession_members"] is True

    loaded = client.get("/api/wechat-gateway/config", headers=API_HEADERS)
    assert loaded.status_code == 200
    data = loaded.json()
    assert data["sessionized_reply_enabled"] is True
    assert data["fixed_subsession_enabled"] is True
    assert data["fixed_subsession_id"] == "wechat_gateway_default"
    assert data["fixed_subsession_name"] == "微信工作流分身"
    assert data["auto_learn_subsession_members"] is True


def test_callback_ingest_persists_fixed_subsession_memberships_and_turn(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-fixed-subsesson.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
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
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "enabled": True,
            "outbound_enabled": True,
            "sessionized_reply_enabled": True,
            "fixed_subsession_enabled": True,
            "fixed_subsession_id": "wechat_gateway_default",
            "fixed_subsession_name": "固定工作流分身",
            "auto_learn_subsession_members": True,
        })
    finally:
        db.close()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "SessionLocal", Session, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "TypeName": "AddMsg",
        "Appid": "wx_app_test",
        "Data": {
            "NewMsgId": "subsession-msg-1",
            "FromUserName": {"string": "room_alpha@chatroom"},
            "ToUserName": {"string": "wxid_self"},
            "Content": {"string": "wxid_sender_a:\nai固定子session测试"},
            "MsgType": 1,
            "CreateTime": 1710000000,
            "MsgSource": "",
        },
    }

    response = client.post("/api/wechat-gateway/callback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["stored"] is True
    assert data["duplicate"] is False

    verify = Session()
    try:
        message = verify.query(Message).order_by(Message.id.desc()).first()
        assert message is not None
        assert (message.meta or {}).get("subsession", {}).get("id") == "wechat_gateway_default"

        subsession = verify.get(WechatSubsession, "wechat_gateway_default")
        assert subsession is not None
        assert subsession.name == "固定工作流分身"
        assert subsession.channel == "wechat_gateway"

        memberships = verify.query(WechatSubsessionMembership).filter(WechatSubsessionMembership.subsession_id == "wechat_gateway_default").all()
        member_types = {(row.member_type, row.chat_id, row.sender_id) for row in memberships}
        assert ("chat", "room_alpha@chatroom", None) in member_types
        assert ("sender", None, "wxid_sender_a") in member_types

        turn = verify.query(WechatSubsessionTurn).filter(WechatSubsessionTurn.subsession_id == "wechat_gateway_default").one()
        assert turn.chat_id == "room_alpha@chatroom"
        assert turn.sender_id == "wxid_sender_a"
        assert turn.direction == "in"
        assert turn.message_id == message.id
    finally:
        verify.close()


def test_agent_send_text_uses_fixed_subsession_for_outbound_message(tmp_path, monkeypatch):
    db_path = tmp_path / "wechat-gateway-agent-send-subsession.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
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
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "enabled": True,
            "outbound_enabled": True,
            "sessionized_reply_enabled": True,
            "fixed_subsession_enabled": True,
            "fixed_subsession_id": "wechat_gateway_default",
            "fixed_subsession_name": "固定工作流分身",
            "auto_learn_subsession_members": True,
            "token": "***",
            "app_id": "wx_app_test",
            "outbound_random_delay_min_seconds": 0,
            "outbound_random_delay_max_seconds": 0,
        })
    finally:
        db.close()

    class DummyWechatApiClient:
        def __init__(self, *args, **kwargs):
            pass

        def configured(self):
            return True

        def send_text(self, to_wxid: str, text: str):
            return {"ret": "200", "msg": "ok", "data": {"toWxid": to_wxid}}

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(wechat_gateway_router, "WechatApiClient", DummyWechatApiClient, raising=False)
    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    response = client.post(
        "/api/wechat-gateway/agent-send-text",
        json={"channel": "wechat", "source": "hermes", "target": "wxid_friend", "text": "受控发送"},
        headers=API_HEADERS,
    )
    assert response.status_code == 200

    verify = Session()
    try:
        row = verify.query(Message).one()
        assert (row.meta or {}).get("subsession", {}).get("id") == "wechat_gateway_default"
        turn = verify.query(WechatSubsessionTurn).filter(WechatSubsessionTurn.message_id == row.id).one()
        assert turn.direction == "out"
        assert turn.subsession_id == "wechat_gateway_default"
    finally:
        verify.close()


def test_subsession_config_api_roundtrip_updates_execution_fields(tmp_path):
    db_path = tmp_path / "wechat-gateway-subsession-config-api.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
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
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        save_config(db, {
            "sessionized_reply_enabled": True,
            "fixed_subsession_enabled": True,
            "fixed_subsession_id": "wechat_gateway_default",
            "fixed_subsession_name": "微信工作流分身",
        })
        save_subsession_config(
            db,
            subsession_id="wechat_gateway_default",
            payload={
                "name": "微信工作流分身",
                "system_prompt": "旧 prompt",
                "model_route_kind": "tool",
                "model_route_key": "reply_old",
                "model_override": "old-model",
            },
        )
    finally:
        db.close()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[wechat_gateway_router.get_db] = override_get_db
    client = TestClient(app)

    get_resp = client.get("/api/wechat-gateway/subsession-config/wechat_gateway_default", headers=API_HEADERS)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["status"] == "ok"
    assert get_data["subsession"]["id"] == "wechat_gateway_default"
    assert get_data["subsession"]["model_route_key"] == "reply_old"

    post_resp = client.post(
        "/api/wechat-gateway/subsession-config/wechat_gateway_default",
        headers=API_HEADERS,
        json={
            "system_prompt": "新的 subsession prompt",
            "model_route_kind": "tool",
            "model_route_key": "reply_subsession",
            "model_override": "subsession-model",
        },
    )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["status"] == "ok"
    assert post_data["subsession"]["system_prompt"] == "新的 subsession prompt"
    assert post_data["subsession"]["model_route_key"] == "reply_subsession"
    assert post_data["subsession"]["model_override"] == "subsession-model"
