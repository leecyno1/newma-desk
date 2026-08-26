from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import (
    Chat,
    Contact,
    Message,
    SyncState,
    WechatSubsession,
    WechatSubsessionMembership,
    WechatSubsessionTurn,
)
from app.services.wechat_auto_reply_transaction import (
    AutoReplyAdapters,
    execute_wechat_auto_reply_transaction,
)
from app.services.wechat_gateway import ingest_callback_event, save_config


class _TrackingSession:
    def __init__(self, message: Message | None, contact: Contact | None = None):
        self.message = message
        self.contact = contact
        self.added: list[Any] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def get(self, model, key):
        if model is Message:
            if self.message is not None and self.message.id == key:
                return self.message
            return None
        if model is Contact:
            if self.contact is not None and self.contact.id == key:
                return self.contact
            return None
        raise AssertionError(f"unexpected model lookup: {model!r}")

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


def _message(*, direction: str = "in", message_type: str = "text") -> Message:
    return Message(
        id=17,
        chat_id="room_1@chatroom",
        sender_id="wxid_sender",
        sender_name="发送者",
        talker_name="测试群",
        timestamp=datetime(2026, 7, 11, 12, 30, 45),
        direction=direction,
        type=message_type,
        content_text="ai 请回复",
        meta={"subsession": {"id": "wechat_sales"}},
    )


def _adapters(
    events: list[str],
    *,
    precheck: dict[str, Any] | None = None,
    recheck: dict[str, Any] | None = None,
    generated: dict[str, Any] | None = None,
    outbound_rule: dict[str, Any] | None = None,
    configured: bool = True,
    claimed: bool = True,
    delay_error: Exception | None = None,
    send_error: Exception | None = None,
) -> AutoReplyAdapters:
    precheck_result = precheck or {"allowed": True, "reason": "passed"}
    recheck_result = recheck or {"allowed": True, "reason": "passed"}
    generated_result = generated or {
        "status": "ok",
        "reply": "自动回复内容",
        "prompt_key": "reply_da",
        "execution": {
            "route_kind": "hermes_api_server",
            "route_key": "wechat_gateway",
            "subsession_id": "wechat_sales",
            "fallback_used": False,
        },
    }
    outbound_result = outbound_rule or {"allowed": True, "reason": "passed"}

    def evaluate_rules(db, **kwargs):
        if kwargs["wait_for_human_reply_suppression"]:
            events.append("precheck")
            return precheck_result
        events.append("recheck")
        return recheck_result

    def generate_reply(**kwargs):
        events.append("generate")
        assert kwargs == {
            "message_text": "ai 请回复",
            "subsession_id": "wechat_sales",
            "chat_id": "room_1@chatroom",
            "sender_id": "wxid_sender",
            "sender_name": "发送者",
            "sender_remark": "销售备注",
            "talker_name": "测试群",
            "is_group": True,
        }
        return generated_result

    def load_config(db):
        return {
            "base_url": "http://wechat.example",
            "token": "secret-token",
            "header_name": "VideosApi-token",
            "app_id": "wx_app_test",
        }

    def evaluate_outbound(config, *, target, text):
        events.append("outbound_rule")
        assert target == "room_1@chatroom"
        assert text == str(generated_result.get("reply") or "")
        return outbound_result

    def apply_delay(config):
        events.append("delay")
        if delay_error is not None:
            raise delay_error
        return 1.25

    def claim_attempt(db, *, message_id, target):
        events.append("claim")
        return {
            "claimed": claimed,
            "attempt": {
                "state": "claimed" if claimed else "recorded",
                "trigger_message_id": message_id,
                "target": target,
            },
        }

    def update_attempt(db, *, message_id, state, delivery=None, error=None, commit=True):
        events.append(f"attempt:{state}")
        return {
            "state": state,
            "trigger_message_id": message_id,
            "delivery": delivery,
            "error": error,
        }

    class _Client:
        def configured(self):
            return configured

        def send_text(self, *, to_wxid, text):
            events.append("send")
            if send_error is not None:
                raise send_error
            return {
                "ret": 200,
                "msg": "操作成功",
                "data": {
                    "toWxid": to_wxid,
                    "msgId": 101,
                    "newMsgId": 202,
                    "type": 1,
                },
            }

    def client_factory(**kwargs):
        assert kwargs == {
            "base_url": "http://wechat.example",
            "token": "secret-token",
            "header_name": "VideosApi-token",
            "app_id": "wx_app_test",
        }
        return _Client()

    def record_outbound(db, *, target, text, provider_result):
        events.append("record")
        assert target == "room_1@chatroom"
        assert text == "自动回复内容"
        assert provider_result["source"] == "wechat_gateway_auto_reply"
        assert provider_result["auto_reply"] == {"trigger_message_id": 17}
        assert provider_result["data"]["newMsgId"] == 202
        return Message(id=81, chat_id=target, direction="out", type="text", content_text=text, meta={})

    return AutoReplyAdapters(
        evaluate_rules=evaluate_rules,
        generate_reply=generate_reply,
        load_config=load_config,
        evaluate_outbound=evaluate_outbound,
        apply_delay=apply_delay,
        client_factory=client_factory,
        record_outbound=record_outbound,
        claim_attempt=claim_attempt,
        update_attempt=update_attempt,
    )


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        (None, "message_not_found"),
        (_message(direction="out"), "message_not_inbound"),
        (_message(message_type="image"), "message_not_text"),
    ],
)
def test_ineligible_message_is_skipped_without_calling_adapters(message, reason):
    session = _TrackingSession(message)

    def unexpected(*args, **kwargs):
        raise AssertionError("adapter must not be called")

    adapters = AutoReplyAdapters(
        evaluate_rules=unexpected,
        generate_reply=unexpected,
        load_config=unexpected,
        evaluate_outbound=unexpected,
        apply_delay=unexpected,
        client_factory=unexpected,
        record_outbound=unexpected,
    )

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert result.status == "skipped"
    assert result.reason == reason
    assert result.message_id == 17
    assert result.outbound_message_id is None
    assert result.execution is None
    assert session.closed is True


def test_precheck_block_stops_before_generation():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, precheck={"allowed": False, "reason": "prefix_miss"})

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck"]
    assert result.status == "blocked"
    assert result.reason == "prefix_miss"
    assert result.outbound_message_id is None
    assert session.closed is True


def test_success_path_runs_in_strict_order_and_records_execution_metadata():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events)

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == [
        "precheck",
        "generate",
        "recheck",
        "outbound_rule",
        "claim",
        "delay",
        "send",
        "attempt:sent_pending_record",
        "record",
        "attempt:recorded",
    ]
    assert result.status == "sent"
    assert result.reason == "sent"
    assert result.message_id == 17
    assert result.outbound_message_id == 81
    assert result.delivery == {
        "target": "room_1@chatroom",
        "provider_message_id": 101,
        "provider_new_message_id": 202,
        "provider_status": 200,
        "provider_message": "操作成功",
    }
    assert result.execution == {
        "route_kind": "hermes_api_server",
        "route_key": "wechat_gateway",
        "subsession_id": "wechat_sales",
        "fallback_used": False,
        "delivery": result.delivery,
    }
    outbound = session.added[-1]
    assert outbound.meta["auto_reply"] == {
        "trigger_message_id": 17,
        "rule": {"allowed": True, "reason": "passed"},
        "prompt_key": "reply_da",
        "execution": result.execution,
        "outbound_rule": {"allowed": True, "reason": "passed"},
        "outbound_delay_seconds": 1.25,
    }
    assert session.commit_count == 1
    assert session.closed is True


def test_human_takeover_after_generation_stops_at_recheck():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, recheck={"allowed": False, "reason": "human_reply_suppressed"})

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck", "generate", "recheck"]
    assert result.status == "blocked"
    assert result.reason == "human_reply_suppressed"
    assert result.execution == {
        "route_kind": "hermes_api_server",
        "route_key": "wechat_gateway",
        "subsession_id": "wechat_sales",
        "fallback_used": False,
    }
    assert session.commit_count == 0
    assert session.closed is True


def test_generation_failure_returns_stable_result_and_does_not_send():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(
        events,
        generated={
            "status": "error",
            "error": "provider timeout",
            "execution": {"route_key": "wechat_gateway", "error": "provider timeout"},
        },
    )

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck", "generate"]
    assert result.status == "failed"
    assert result.reason == "provider timeout"
    assert result.execution == {"route_key": "wechat_gateway", "error": "provider timeout"}
    assert session.commit_count == 0
    assert session.closed is True


def test_outbound_rule_block_returns_stable_result_before_delay():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, outbound_rule={"allowed": False, "reason": "keyword_blocked"})

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck", "generate", "recheck", "outbound_rule"]
    assert result.status == "blocked"
    assert result.reason == "keyword_blocked"
    assert result.outbound_message_id is None
    assert session.closed is True


def test_unconfigured_gateway_skips_before_delay_and_send():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, configured=False)

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck", "generate", "recheck", "outbound_rule"]
    assert result.status == "skipped"
    assert result.reason == "gateway_not_configured"
    assert result.outbound_message_id is None
    assert session.closed is True


def test_adapter_exception_returns_stable_error_rolls_back_and_closes_session():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, send_error=RuntimeError("gateway unavailable"))

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == [
        "precheck",
        "generate",
        "recheck",
        "outbound_rule",
        "claim",
        "delay",
        "send",
        "attempt:delivery_unknown",
    ]
    assert result.status == "delivery_unknown"
    assert result.reason == "send_failed_delivery_unknown"
    assert result.outbound_message_id is None
    assert result.execution == {
        "route_kind": "hermes_api_server",
        "route_key": "wechat_gateway",
        "subsession_id": "wechat_sales",
        "fallback_used": False,
        "transaction_stage": "send",
        "transaction_error": "gateway unavailable",
        "delivery": {"target": "room_1@chatroom", "send_error": "gateway unavailable"},
    }
    assert result.delivery == {"target": "room_1@chatroom", "send_error": "gateway unavailable"}
    assert session.rollback_count == 1
    assert session.closed is True


def test_delay_failure_marks_attempt_failed_before_send_and_does_not_send():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, delay_error=RuntimeError("delay scheduler failed"))

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == [
        "precheck",
        "generate",
        "recheck",
        "outbound_rule",
        "claim",
        "delay",
        "attempt:failed_before_send",
    ]
    assert result.status == "error"
    assert result.reason == "failed_before_send"
    assert result.delivery is None
    assert session.rollback_count == 1
    assert session.closed is True


def test_already_claimed_attempt_skips_before_delay_and_send():
    events: list[str] = []
    session = _TrackingSession(_message(), Contact(id="wxid_sender", alias="销售备注"))
    adapters = _adapters(events, claimed=False)

    result = execute_wechat_auto_reply_transaction(
        17,
        session_factory=lambda: session,
        adapters=adapters,
    )

    assert events == ["precheck", "generate", "recheck", "outbound_rule", "claim"]
    assert result.status == "skipped"
    assert result.reason == "already_claimed"
    assert result.outbound_message_id is None
    assert session.closed is True


def test_default_gateway_adapters_resolve_service_functions_at_call_time(monkeypatch):
    import app.services.wechat_gateway as gateway_service

    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        gateway_service,
        "evaluate_auto_reply_rules",
        lambda db, **kwargs: calls.append(("rules", kwargs)) or {"allowed": True},
    )
    monkeypatch.setattr(
        gateway_service,
        "load_config",
        lambda db: calls.append(("config", db)) or {"token": "patched"},
    )
    monkeypatch.setattr(
        gateway_service,
        "evaluate_outbound_message",
        lambda config, **kwargs: calls.append(("outbound", kwargs)) or {"allowed": True},
    )
    monkeypatch.setattr(
        gateway_service,
        "apply_outbound_random_delay",
        lambda config: calls.append(("delay", config)) or 2.5,
    )
    monkeypatch.setattr(
        gateway_service,
        "record_outbound_message",
        lambda db, **kwargs: calls.append(("record", kwargs)) or "patched-outbound",
    )
    monkeypatch.setattr(
        gateway_service,
        "claim_auto_reply_attempt",
        lambda db, **kwargs: calls.append(("claim", kwargs)) or {"claimed": True},
        raising=False,
    )
    monkeypatch.setattr(
        gateway_service,
        "update_auto_reply_attempt",
        lambda db, **kwargs: calls.append(("update", kwargs)) or {"state": kwargs["state"]},
        raising=False,
    )

    adapters = AutoReplyAdapters()

    assert adapters.evaluate_rules("db", marker="rules") == {"allowed": True}
    assert adapters.load_config("db") == {"token": "patched"}
    assert adapters.evaluate_outbound({}, marker="outbound") == {"allowed": True}
    assert adapters.apply_delay({"delay": True}) == 2.5
    assert adapters.record_outbound("db", marker="record") == "patched-outbound"
    assert adapters.claim_attempt("db", marker="claim") == {"claimed": True}
    assert adapters.update_attempt("db", state="recorded") == {"state": "recorded"}
    assert [name for name, _ in calls] == ["rules", "config", "outbound", "delay", "record", "claim", "update"]
    assert calls[-3][1]["commit"] is False


def test_default_client_adapter_resolves_client_class_at_call_time(monkeypatch):
    import app.services.wechatapi_client as client_service

    monkeypatch.setattr(
        client_service,
        "WechatApiClient",
        lambda **kwargs: {"client": "patched", "kwargs": kwargs},
    )

    client = AutoReplyAdapters().client_factory(token="patched-token")

    assert client == {"client": "patched", "kwargs": {"token": "patched-token"}}


def test_auto_reply_attempt_insert_compiles_for_sqlite_and_postgresql():
    import app.services.wechat_gateway as gateway_service

    statement = gateway_service._build_auto_reply_attempt_insert(
        key="wechat_auto_reply_attempt:17",
        value='{"state":"claimed"}',
    )

    sqlite_sql = str(statement.compile(dialect=sqlite.dialect()))
    postgres_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO sync_state" in sqlite_sql
    assert "INSERT INTO sync_state" in postgres_sql
    assert "ON CONFLICT" not in sqlite_sql.upper()
    assert "ON CONFLICT" not in postgres_sql.upper()


def test_final_commit_failure_rolls_back_default_recorded_outbound_and_turn(tmp_path: Path):
    db_path = tmp_path / "wechat-auto-reply-atomicity.db"
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
    NormalSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    seed = NormalSession()
    try:
        save_config(
            seed,
            {
                "enabled": True,
                "outbound_enabled": True,
                "sessionized_reply_enabled": True,
                "fixed_subsession_enabled": True,
                "fixed_subsession_id": "wechat_gateway_default",
                "fixed_subsession_name": "微信工作流分身",
                "auto_learn_subsession_members": True,
            },
        )
        seed.add(Chat(id="wxid_friend", title="好友", type="single", is_chatroom=False))
        inbound = Message(
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            sender_name="好友",
            talker_name="好友",
            timestamp=datetime(2026, 7, 11, 15, 0, 0),
            direction="in",
            type="text",
            content_text="ai 你好",
            meta={"subsession": {"id": "wechat_gateway_default"}},
        )
        seed.add(inbound)
        seed.commit()
        inbound_id = int(inbound.id)
    finally:
        seed.close()

    class _FailCompleteAutoReplyCommitSession(OrmSession):
        def commit(self):
            changed = list(self.new) + list(self.dirty)
            for value in changed:
                if not isinstance(value, Message) or value.direction != "out":
                    continue
                auto_reply = (value.meta or {}).get("auto_reply")
                if isinstance(auto_reply, dict) and auto_reply.get("outbound_rule"):
                    raise RuntimeError("final commit failed")
            return super().commit()

    FailingSession = sessionmaker(
        bind=engine,
        class_=_FailCompleteAutoReplyCommitSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    send_calls: list[tuple[str, str]] = []

    class _ConfiguredClient:
        def configured(self):
            return True

        def send_text(self, *, to_wxid, text):
            send_calls.append((to_wxid, text))
            return {
                "ret": 200,
                "msg": "操作成功",
                "data": {"toWxid": to_wxid, "msgId": 301, "newMsgId": 302, "type": 1},
            }

    def evaluate_rules(db, **kwargs):
        return {"allowed": True, "reason": "passed"}

    adapters = AutoReplyAdapters(
        evaluate_rules=evaluate_rules,
        generate_reply=lambda **kwargs: {
            "status": "ok",
            "reply": "事务内自动回复",
            "prompt_key": "reply_da",
            "execution": {"route_key": "wechat_gateway", "fallback_used": False},
        },
        load_config=lambda db: {
            "base_url": "http://wechat.example",
            "token": "secret-token",
            "header_name": "VideosApi-token",
            "app_id": "wx_app_test",
        },
        evaluate_outbound=lambda config, **kwargs: {"allowed": True, "reason": "passed"},
        apply_delay=lambda config: 0.0,
        client_factory=lambda **kwargs: _ConfiguredClient(),
    )

    result = execute_wechat_auto_reply_transaction(
        inbound_id,
        session_factory=FailingSession,
        adapters=adapters,
    )

    assert result.status == "delivery_unknown"
    assert result.reason == "persistence_failed_after_send"
    assert result.execution["transaction_stage"] == "commit"
    assert result.execution["transaction_error"] == "final commit failed"
    assert result.delivery == {
        "target": "wxid_friend",
        "provider_message_id": 301,
        "provider_new_message_id": 302,
        "provider_status": 200,
        "provider_message": "操作成功",
    }
    assert result.execution["delivery"] == result.delivery
    assert send_calls == [("wxid_friend", "事务内自动回复")]

    verify = NormalSession()
    try:
        messages = verify.query(Message).order_by(Message.id.asc()).all()
        assert [(row.id, row.direction, row.content_text) for row in messages] == [
            (inbound_id, "in", "ai 你好")
        ]
        assert verify.query(WechatSubsessionTurn).filter(WechatSubsessionTurn.direction == "out").count() == 0
        attempt_row = verify.get(SyncState, f"wechat_auto_reply_attempt:{inbound_id}")
        assert attempt_row is not None
        attempt = json.loads(attempt_row.value)
        assert attempt["state"] == "sent_pending_record"
        assert attempt["trigger_message_id"] == inbound_id
        assert attempt["target"] == "wxid_friend"
        assert attempt["delivery"] == result.delivery
    finally:
        verify.close()


def test_concurrent_transactions_claim_once_and_send_once(tmp_path: Path):
    db_path = tmp_path / "wechat-auto-reply-idempotency.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(
        engine,
        tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__],
    )
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    seed = Session()
    try:
        seed.add(Chat(id="wxid_friend", title="好友", type="single", is_chatroom=False))
        inbound = Message(
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            sender_name="好友",
            talker_name="好友",
            timestamp=datetime(2026, 7, 11, 16, 0, 0),
            direction="in",
            type="text",
            content_text="ai 并发测试",
            meta={},
        )
        seed.add(inbound)
        seed.commit()
        inbound_id = int(inbound.id)
    finally:
        seed.close()

    before_claim = threading.Barrier(2)
    send_lock = threading.Lock()
    send_count = 0

    class _CountingClient:
        def configured(self):
            return True

        def send_text(self, *, to_wxid, text):
            nonlocal send_count
            with send_lock:
                send_count += 1
            return {
                "ret": 200,
                "msg": "操作成功",
                "data": {"toWxid": to_wxid, "msgId": 401, "newMsgId": 402, "type": 1},
            }

    def evaluate_outbound(config, **kwargs):
        before_claim.wait(timeout=5)
        return {"allowed": True, "reason": "passed"}

    adapters = AutoReplyAdapters(
        evaluate_rules=lambda db, **kwargs: {"allowed": True, "reason": "passed"},
        generate_reply=lambda **kwargs: {
            "status": "ok",
            "reply": "并发自动回复",
            "execution": {"route_key": "wechat_gateway", "fallback_used": False},
        },
        load_config=lambda db: {
            "base_url": "http://wechat.example",
            "token": "secret-token",
            "header_name": "VideosApi-token",
            "app_id": "wx_app_test",
        },
        evaluate_outbound=evaluate_outbound,
        apply_delay=lambda config: 0.0,
        client_factory=lambda **kwargs: _CountingClient(),
    )

    def execute_once():
        return execute_wechat_auto_reply_transaction(
            inbound_id,
            session_factory=Session,
            adapters=adapters,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=10) for future in [pool.submit(execute_once), pool.submit(execute_once)]]

    assert send_count == 1
    assert sorted(result.status for result in results) == ["sent", "skipped"]
    skipped = next(result for result in results if result.status == "skipped")
    assert skipped.reason == "already_claimed"

    verify = Session()
    try:
        assert verify.query(Message).filter(Message.direction == "out").count() == 1
        attempt_row = verify.get(SyncState, f"wechat_auto_reply_attempt:{inbound_id}")
        assert attempt_row is not None
        assert json.loads(attempt_row.value)["state"] == "recorded"
    finally:
        verify.close()


def test_callback_before_outbound_record_reconciles_one_auto_reply_message(tmp_path: Path):
    db_path = tmp_path / "wechat-auto-reply-callback-race.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(
        engine,
        tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__],
    )
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    seed = Session()
    try:
        seed.add(Chat(id="wxid_friend", title="好友", type="single", is_chatroom=False))
        inbound = Message(
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            sender_name="好友",
            talker_name="好友",
            timestamp=datetime(2026, 7, 11, 17, 0, 0),
            direction="in",
            type="text",
            content_text="ai callback 竞态测试",
            meta={},
        )
        seed.add(inbound)
        seed.commit()
        inbound_id = int(inbound.id)
    finally:
        seed.close()

    provider_result = {
        "ret": 200,
        "msg": "操作成功",
        "data": {"toWxid": "wxid_friend", "msgId": 501, "newMsgId": 502, "type": 1},
    }
    callback_payload = {
        "TypeName": "AddMsg",
        "Appid": "wx_app_test",
        "Wxid": "self_wxid",
        "Data": {
            "MsgId": 501,
            "NewMsgId": 502,
            "MsgType": 1,
            "CreateTime": 1783760410,
            "FromUserName": {"string": "self_wxid"},
            "ToUserName": {"string": "wxid_friend"},
            "Content": {"string": "callback 竞态自动回复"},
        },
    }
    attempt_committed = threading.Event()
    callback_completed = threading.Event()

    import app.services.wechat_gateway as gateway_service

    def update_attempt(db, **kwargs):
        updated = gateway_service.update_auto_reply_attempt(db, **kwargs)
        if kwargs["state"] == "sent_pending_record" and kwargs.get("commit", True):
            attempt_committed.set()
        return updated

    def record_outbound(db, **kwargs):
        assert callback_completed.wait(timeout=5)
        return gateway_service.record_outbound_message(db, commit=False, **kwargs)

    class _ConfiguredClient:
        def configured(self):
            return True

        def send_text(self, *, to_wxid, text):
            assert (to_wxid, text) == ("wxid_friend", "callback 竞态自动回复")
            return provider_result

    adapters = AutoReplyAdapters(
        evaluate_rules=lambda db, **kwargs: {"allowed": True, "reason": "passed"},
        generate_reply=lambda **kwargs: {
            "status": "ok",
            "reply": "callback 竞态自动回复",
            "prompt_key": "reply_da",
            "execution": {"route_key": "wechat_gateway", "fallback_used": False},
        },
        load_config=lambda db: {
            "base_url": "http://wechat.example",
            "token": "secret-token",
            "header_name": "VideosApi-token",
            "app_id": "wx_app_test",
        },
        evaluate_outbound=lambda config, **kwargs: {"allowed": True, "reason": "passed"},
        apply_delay=lambda config: 0.0,
        client_factory=lambda **kwargs: _ConfiguredClient(),
        record_outbound=record_outbound,
        update_attempt=update_attempt,
    )

    def receive_callback():
        assert attempt_committed.wait(timeout=5)
        callback_db = Session()
        try:
            callback_result = ingest_callback_event(callback_db, callback_payload)
            callback_message = callback_db.get(Message, int(callback_result["message_id"]))
            return callback_result, dict(callback_message.meta or {})
        finally:
            callback_db.close()
            callback_completed.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        callback_future = pool.submit(receive_callback)
        result = execute_wechat_auto_reply_transaction(
            inbound_id,
            session_factory=Session,
            adapters=adapters,
        )
        callback_result, callback_meta = callback_future.result(timeout=10)

    assert result.status == "sent"
    assert callback_result["stored"] is True
    assert callback_meta["auto_reply"] == {
        "trigger_message_id": inbound_id,
        "reconciled_from_attempt": True,
    }
    assert "manual" not in callback_meta
    assert "human_manual" not in callback_meta

    verify = Session()
    try:
        outbound_rows = verify.query(Message).filter(Message.direction == "out").all()
        assert len(outbound_rows) == 1
        outbound = outbound_rows[0]
        assert outbound.id == result.outbound_message_id == int(callback_result["message_id"])
        assert (outbound.meta or {})["external_new_msg_id"] == 502
        assert (outbound.meta or {})["auto_reply"]["trigger_message_id"] == inbound_id
        assert "manual" not in (outbound.meta or {})
        assert "human_manual" not in (outbound.meta or {})

        dedupe = verify.get(SyncState, "wechat_gateway_dedup:wx_app_test:502")
        assert dedupe is not None
        assert int(dedupe.value) == outbound.id
        attempt_row = verify.get(SyncState, f"wechat_auto_reply_attempt:{inbound_id}")
        assert attempt_row is not None
        assert json.loads(attempt_row.value)["state"] == "recorded"
    finally:
        verify.close()
