from __future__ import annotations

import asyncio
import json
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Message
from app.routers import wechat_gateway as gateway_router
from app.services import hermes_bridge, wechat_device_ws
from app.services.wechat_gateway import save_config, save_trigger_rules
from app.services.wechatapi_client import WechatApiClient


def _client():
    return WechatApiClient(base_url="http://device.test:7091", token="test-device-key",
                           header_name="key", app_id="")


class _Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_device_auth_status_and_send_use_documented_interfaces(monkeypatch):
    client = _client()
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        data = {"loginState": 1} if method == "GET" else {
            "baseResponse": {"ret": 0}, "newMsgId": 9123, "msgId": 456,
        }
        return _Response({"Code": 200, "Success": False, "Data": data})

    monkeypatch.setattr(client._session, "request", request)
    assert client.configured()
    assert client.check_online()["data"] is True
    assert calls[0][1].endswith("/login/GetLoginStatus")
    assert client.send_text("friend", "hello")["data"]["newMsgId"] == 9123
    method, url, kwargs = calls[-1]
    assert method == "POST" and url.endswith("/message/SendTextMessage")
    assert kwargs["params"] == {"key": "test-device-key"}
    assert kwargs["json"]["MsgItem"] == [{
        "ToUserName": "friend", "TextContent": "hello", "MsgType": 1, "AtWxIDList": [],
    }]
    assert "appId" not in kwargs["json"]
    assert client.device_ws_url() == "ws://device.test:7091/ws/GetSyncMsg?key=test-device-key"
    monkeypatch.setattr(client._session, "request", lambda *a, **k: _Response({
        "Code": 200, "Data": {"baseResponse": {"ret": -1, "errMsg": "not sent"}},
    }))
    with pytest.raises(RuntimeError, match="not sent"):
        client.send_text("friend", "hello")


def _frame(msg_id, sender="friend", text="ai 你好", age=0):
    return {"key": "test-device-key", "data": {
        "newMsgId": msg_id, "msgId": msg_id, "msgType": 1,
        "fromUserName": {"str": sender}, "toUserName": {"str": "self" if sender != "self" else "friend"},
        "content": {"str": text}, "createTime": int(time.time()) - age,
    }}


@pytest.mark.parametrize("as_list", [False, True])
def test_device_real_send_receipt_and_nested_failures(monkeypatch, as_list):
    client = _client()
    receipt = {"isSendSuccess": True, "resp": {
        "base_response": {"ret": 0},
        "chat_send_ret_list": [{"ret": 0, "msgId": 0, "newMsgId": 9123}],
    }}
    monkeypatch.setattr(client._session, "request", lambda *a, **k: _Response({
        "Code": 200, "Success": False, "Data": [receipt] if as_list else receipt,
    }))
    assert client.send_text("filehelper", "test")["data"]["newMsgId"] == 9123
    receipt["resp"]["chat_send_ret_list"][0]["ret"] = -1
    with pytest.raises(RuntimeError):
        client.send_text("filehelper", "test")
    receipt["resp"]["chat_send_ret_list"][0]["ret"] = 0
    receipt["resp"]["base_response"]["ret"] = -2
    with pytest.raises(RuntimeError):
        client.send_text("filehelper", "test")
    receipt["resp"]["base_response"]["ret"] = 0
    receipt["isSendSuccess"] = False
    with pytest.raises(RuntimeError):
        client.send_text("filehelper", "test")


def test_ws_pipeline_replies_once_and_ignores_echo_and_old_messages(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'device.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        save_config(db, {"enabled": True, "outbound_enabled": True, "ws_enabled": True,
                         "base_url": "http://device.test:7091", "header_name": "key", "token": "test-device-key"})
        save_trigger_rules(db, {"prefixes": ["ai"], "random_rate": 0})
    sent = []

    class InlineExecutor:
        def submit(self, fn, *args):
            return fn(*args)

    def send(_session, method, url, **kwargs):
        sent.append(kwargs["json"])
        return _Response({"Code": 200, "Success": False, "Data": {
            "baseResponse": {"ret": 0}, "List": [{"newMsgId": 300, "msgId": 300}],
        }})

    monkeypatch.setattr(wechat_device_ws, "SessionLocal", Session)
    monkeypatch.setattr(gateway_router, "_auto_reply_executor", InlineExecutor())
    monkeypatch.setattr(gateway_router, "_queue_contact_prediction_refresh", lambda *a: None)
    monkeypatch.setattr(hermes_bridge, "call_hermes_for_reply", lambda **k: {"status": "ok", "reply": "测试回复"})
    monkeypatch.setattr("requests.Session.request", send)
    frame = _frame(100)
    assert asyncio.run(wechat_device_ws.ingest_device_frame(json.dumps(frame), "self")) == 1
    assert asyncio.run(wechat_device_ws.ingest_device_frame(frame, "self")) == 0
    assert len(sent) == 1
    assert sent[0]["MsgItem"][0]["ToUserName"] == "friend"
    asyncio.run(wechat_device_ws.ingest_device_frame(_frame(300, sender="self", text="测试回复"), "self"))
    asyncio.run(wechat_device_ws.ingest_device_frame(_frame(400, age=600), "self"))
    assert len(sent) == 1
    with Session() as db:
        messages = db.query(Message).all()
        assert len(messages) == 3
        outbound = next(m for m in messages if m.direction == "out")
        assert outbound.meta["auto_reply"]["trigger_message_id"]
        assert all("test-device-key" not in json.dumps(m.meta) for m in messages)
    engine.dispose()


def test_device_group_and_callback_shapes_are_normalized():
    message = _frame(1)["data"]
    message["fromUserName"] = {"str": "room@chatroom"}
    message["content"] = {"str": "friend:\nai 群消息"}
    events = wechat_device_ws.normalize_device_events({"Data": {"addMsgs": [message]}}, "self")
    assert events[0]["Data"]["FromUserName"]["string"] == "room@chatroom"
    assert events[0]["Data"]["Content"]["string"] == "friend:\nai 群消息"
    envelope = {"key": "test-device-key", "type": "AddMsg", "message": json.dumps(message)}
    assert wechat_device_ws.normalize_device_events(envelope, "self") == events
    snake_message = {
        "new_msg_id": 1, "msg_id": 1, "msg_type": 1,
        "from_user_name": {"str": "room@chatroom"}, "to_user_name": {"str": "self"},
        "content": {"str": "friend:\nai 群消息"}, "create_time": message["createTime"],
    }
    cache = {"Data": {"AddMsgs": [snake_message], "Key": {"buffer": "private-key"}}}
    assert wechat_device_ws.normalize_device_events(cache, "self") == events
    assert wechat_device_ws.normalize_device_events({"type": "heartbeat"}, "self") == []
