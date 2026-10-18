from datetime import datetime, timezone, timedelta
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Chat, Contact, Message, SyncState
from app.services.chatlog_client import ChatlogClient
from app.services.chatlog_backfill import import_page, backfill, STATE_KEY


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def page(*, server="123", local=88, stamp=1776268837, type_num=1, content="历史消息", media=None):
    return ChatlogClient._normalize_history({"username": "friend", "chat": "备注名称",
        "messages": [{"message_id": local, "server_id": server, "timestamp": stamp,
                      "time": "2026-04-15 23:59", "sender_id": "friend", "sender": "备注名称",
                      "type": "share", "type_num": type_num, "content": content,
                      "media_url": media, "contents": {"host": "127.0.0.1:5031"}}]}, talker="friend")["messages"]


def test_preserves_seconds_types_and_resolved_media():
    rows = page(type_num=3, media="http://127.0.0.1:5031/image/safe-path")
    assert datetime.fromisoformat(rows[0]["time"]).timestamp() == 1776268837
    assert rows[0]["type"] == 3
    from app.services.sync_service import _normalize_chatlog_message
    normalized = _normalize_chatlog_message(rows[0])
    assert normalized.message_type == "image"
    assert normalized.media_url == "http://127.0.0.1:5031/image/safe-path"


def test_sessions_paginate_beyond_500_and_detect_old_server(monkeypatch):
    client = ChatlogClient()
    calls = []
    def get_sessions(offset=0):
        calls.append(offset)
        rows = [{"username": f"friend{i}"} for i in range(offset, min(offset + 500, 502))]
        return {"sessions": rows, "has_more": offset == 0}
    monkeypatch.setattr(client, "get_sessions", get_sessions)
    assert len(client.get_all_sessions()) == 502
    assert calls == [0, 500]
    monkeypatch.setattr(client, "get_sessions", lambda offset=0: {"sessions": [{"username": str(i)} for i in range(500)]})
    with pytest.raises(ValueError, match="repeated"):
        client.get_all_sessions()


def test_idempotent_history_and_websocket_dedup_markers(factory):
    rows = page() + page(server="124", local=89)
    with factory() as db:
        first = import_page(db, rows, account_id="owner")
        db.commit()
        second = import_page(db, rows, account_id="owner")
        db.commit()
        assert first["inserted"] == 2  # same content/second, distinct server IDs are distinct messages
        assert second["inserted"] == 0 and second["existing"] == 2
        assert len(list(db.scalars(select(Message)))) == 2
        marker = db.get(SyncState, "wechat_gateway_dedup:owner:123")
        assert db.get(Message, int(marker.value)) is not None


def test_existing_websocket_record_is_enriched_not_duplicated(factory):
    rows = page(type_num=3, media="http://127.0.0.1:5031/image/photo")
    timestamp = datetime.fromisoformat(rows[0]["time"]).replace(tzinfo=None)
    with factory() as db:
        db.add(Chat(id="friend"))
        db.add(Contact(id="friend", alias="原备注"))
        message = Message(chat_id="friend", sender_id="friend", timestamp=timestamp + timedelta(seconds=5),
                       type="image", content_text="[图片]", meta={"source": "wechat_gateway",
                       "external_new_msg_id": "123", "raw": {"keep": True}})
        db.add(message)
        db.flush()
        db.add(SyncState(key="wechat_gateway_dedup:owner:123", value=str(message.id)))
        db.commit()
        stats = import_page(db, rows, account_id="owner")
        db.commit()
        assert stats["existing"] == 1 and stats["inserted"] == 0
        row = db.scalar(select(Message))
        assert row.media_url.endswith("/image/photo")
        assert row.meta["raw"] == {"keep": True}
        assert row.meta["source"] == "wechat_gateway"
        assert db.get(Contact, "friend").alias == "原备注"


def test_resume_after_failed_page_keeps_committed_checkpoint(factory):
    start = datetime(2026, 4, 15, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, tzinfo=timezone.utc)
    class Client:
        fail = True
        def get_database_talkers(self):
            return []
        def get_all_sessions(self):
            return [{"username": "friend", "timestamp": int(end.timestamp())}]
        def get_history_page(self, talker, since, until, offset=0):
            if offset == 1 and self.fail:
                raise RuntimeError("temporary failure")
            return {"messages": page(server=str(123 + offset), local=88 + offset), "total_count": 2}
    client = Client()
    with pytest.raises(RuntimeError):
        backfill(start=start, end=end, account_id="owner", client=client,
                 session_factory=factory, progress=lambda _: None)
    with factory() as db:
        state = json.loads(db.get(SyncState, STATE_KEY).value)
        assert state["offset"] == 1 and state["inserted"] == 1
        assert state["status"] == "interrupted"
    client.fail = False
    result = backfill(start=start, end=end, account_id="owner", client=client,
                      session_factory=factory, progress=lambda _: None)
    assert result["status"] == "complete" and result["inserted"] == 2


def test_failed_transaction_does_not_advance_checkpoint(factory, monkeypatch):
    import app.services.chatlog_backfill as module
    class Client:
        def get_database_talkers(self):
            return []
        def get_all_sessions(self):
            return [{"username": "friend", "timestamp": 1792079552}]
        def get_history_page(self, *args, **kwargs):
            return {"messages": page(), "total_count": 1}
    original = module._save_state
    def fail_on_page(db, state):
        if state["inserted"] > 0:
            raise RuntimeError("page checkpoint write failed")
        original(db, state)
    monkeypatch.setattr(module, "_save_state", fail_on_page)
    with pytest.raises(RuntimeError):
        backfill(start=datetime(2026, 4, 15, tzinfo=timezone.utc),
                 end=datetime(2026, 10, 15, tzinfo=timezone.utc), account_id="owner",
                 client=Client(), session_factory=factory, progress=lambda _: None)
    with factory() as db:
        state = json.loads(db.get(SyncState, STATE_KEY).value)
        assert state["offset"] == 0 and state["inserted"] == 0
        assert db.scalar(select(Message)) is None


def test_history_search_uses_database_substrings_remarks_and_stable_paging(factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import messages
    app = FastAPI()
    app.include_router(messages.router)
    def get_db():
        with factory() as db:
            yield db
    app.dependency_overrides[messages.get_db] = get_db
    with factory() as db:
        db.add(Chat(id="friend", title="历史会话"))
        db.add(Contact(id="friend", alias="研究员备注"))
        for mid, content in [(1, "中文增长20%报告"), (2, "中文增长20个点"), (3, "另外一条")]:
            db.add(Message(id=mid, chat_id="friend", sender_id="friend", type="text",
                           content_text=content, timestamp=datetime(2026, 4, 20), direction="out"))
        db.commit()
    client = TestClient(app)
    params = {"search_mode": "contains", "q": "增长20%", "time_to": "2026-04-30", "direction": "out"}
    response = client.get("/api/messages", params=params)
    assert response.status_code == 200
    assert [x["id"] for x in response.json()["items"]] == [1]
    params.update(q="研究员备注", size=1)
    first = client.get("/api/messages", params=params).json()
    second = client.get("/api/messages", params={**params, "page": 2}).json()
    assert first["total"] == 3
    assert first["items"][0]["id"] == 3 and second["items"][0]["id"] == 2


def test_file_resolver_uses_persisted_chatlog_url(factory, monkeypatch):
    from app.routers import messages
    from starlette.responses import Response
    with factory() as db:
        message = Message(type="file", content_text="report.pdf", media_url="http://127.0.0.1:5031/file/saved")
        db.add(message); db.commit()
        seen = []
        def serve(url, *args, **kwargs):
            seen.append(url)
            return Response(b"pdf", media_type="application/pdf")
        monkeypatch.setattr(messages, "_serve_or_cache_small_file", serve)
        result = messages.resolve_file_media(message_id=message.id, md5=None, path=None, host=None, url=None, name=None, db=db)
        assert result.status_code == 200
        assert seen[0] == message.media_url
