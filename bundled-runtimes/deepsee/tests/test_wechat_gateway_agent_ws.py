from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Chat, Contact, Message, SyncState
from app.services.wechat_gateway import ingest_agent_wechat_event


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-ws.db'}", future=True)
    Base.metadata.create_all(engine, tables=[Chat.__table__, Contact.__table__, Message.__table__, SyncState.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return Session()


def test_agent_wechat_ws_event_is_deduped_and_merged_into_message_aggregation(tmp_path):
    db = _session(tmp_path)
    try:
        payload = {
            "channel": "wechat",
            "source": "hermes",
            "message_id": "agent-msg-1",
            "chat_id": "room_1@chatroom",
            "sender_id": "wxid_sender",
            "sender_name": "张三",
            "text": "来自 hermes 的微信消息",
            "timestamp": "2026-05-06T12:00:00",
            "is_group": True,
        }
        first = ingest_agent_wechat_event(db, payload)
        second = ingest_agent_wechat_event(db, payload)
        rows = list(db.execute(select(Message)).scalars().all())
        assert first["stored"] is True
        assert second["duplicate"] is True
        assert len(rows) == 1
        msg = rows[0]
        assert msg.chat_id == "room_1@chatroom"
        assert msg.sender_id == "wxid_sender"
        assert msg.content_text == "来自 hermes 的微信消息"
        assert msg.meta["source"] == "wechat_gateway"
        assert msg.meta["agent_source"] == "hermes"
        assert msg.meta["agent_channel"] == "wechat"
    finally:
        db.close()


def test_agent_gateway_ignores_non_wechat_channels(tmp_path):
    db = _session(tmp_path)
    try:
        result = ingest_agent_wechat_event(
            db,
            {
                "channel": "main",
                "source": "hermes",
                "message_id": "main-msg-1",
                "chat_id": "terminal",
                "sender_id": "user",
                "text": "不要进入微信聚合",
            },
        )
        assert result["stored"] is False
        assert result["reason"] == "non_wechat_channel"
        assert db.execute(select(Message)).scalars().all() == []
    finally:
        db.close()


def test_wechat_gateway_config_normalizes_outbound_random_delay(tmp_path):
    from app.services.wechat_gateway import load_config, save_config

    db = _session(tmp_path)
    try:
        cfg = save_config(db, {"outbound_random_delay_min_seconds": 5, "outbound_random_delay_max_seconds": 3})
        assert cfg["outbound_random_delay_min_seconds"] == 3
        assert cfg["outbound_random_delay_max_seconds"] == 5
        loaded = load_config(db)
        assert loaded["outbound_random_delay_min_seconds"] == 3
        assert loaded["outbound_random_delay_max_seconds"] == 5
    finally:
        db.close()
