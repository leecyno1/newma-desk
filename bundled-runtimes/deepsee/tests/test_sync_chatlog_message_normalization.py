from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import db as app_db
from app.db import Base
from app.models import Chat, Contact, Message, SyncState
from app.services import sync_service
from app.services.wechat_message_normalizer import build_wechat_message_identity


APPMSG_XML = """<msg><appmsg>
  <title>Chatlog 历史研报</title>
  <des>历史幂等测试</des>
  <url>https://mp.weixin.qq.com/s/chatlog-history</url>
  <type>5</type>
</appmsg></msg>"""


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "chatlog-normalization.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(
        engine,
        tables=[
            Chat.__table__,
            Contact.__table__,
            Message.__table__,
            SyncState.__table__,
        ],
    )
    return TestingSession, engine


def _appmsg_xml(url: str) -> str:
    return f"""<msg><appmsg>
  <title>Chatlog 历史研报</title>
  <des>历史幂等测试</des>
  <url>{url}</url>
  <type>5</type>
</appmsg></msg>"""


def _appmsg_xml_with_md5(url: str, md5: str) -> str:
    return f"""<msg><appmsg>
  <title>Chatlog 历史研报</title>
  <des>历史幂等测试</des>
  <url>{url}</url>
  <md5>{md5}</md5>
  <type>5</type>
</appmsg></msg>"""


def _chatlog_message(timestamp: datetime, *, content: str = APPMSG_XML) -> dict:
    return {
        "talker": "room_chatlog@chatroom",
        "talkerName": "Chatlog 群",
        "sender": "wxid_chatlog_sender",
        "senderName": "Chatlog 发送人",
        "isChatRoom": True,
        "isSelf": False,
        "type": 49,
        "content": content,
        "time": timestamp.isoformat(),
    }


def _install_fake_chatlog(monkeypatch, messages: dict | list[dict]) -> None:
    records = [messages] if isinstance(messages, dict) else list(messages)

    class FakeChatlogClient:
        def get_sessions(self):
            return [{"talker": records[0]["talker"]}]

        @staticmethod
        def extract_talker_ids(_payload):
            return [records[0]["talker"]]

        def get_chatlog(self, time_range, talker=None, limit=None, offset=None):
            if time_range == str(records[0]["time"])[:10] and int(offset or 0) == 0:
                return records
            return []

    monkeypatch.setattr(sync_service, "ChatlogClient", FakeChatlogClient)


def _seed_history(
    db,
    timestamp: datetime,
    *,
    content_text: str,
    meta: dict | None = None,
) -> None:
    db.add(Chat(id="room_chatlog@chatroom", title="Chatlog 群", is_chatroom=True))
    db.add(Contact(id="wxid_chatlog_sender", name="Chatlog 发送人"))
    db.add(
        Message(
            chat_id="room_chatlog@chatroom",
            sender_id="wxid_chatlog_sender",
            timestamp=timestamp,
            direction="in",
            type="49",
            content_text=content_text,
            meta=meta or {},
        )
    )
    db.commit()


def test_sync_from_chatlog_matches_historical_raw_xml_content(tmp_path, monkeypatch):
    Session, _engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        message = _chatlog_message(timestamp)
        _install_fake_chatlog(monkeypatch, message)
        _seed_history(db, timestamp, content_text=APPMSG_XML)

        result = sync_service.sync_from_chatlog(db, since=timestamp - timedelta(minutes=1))

        assert result["inserted"] == 0
        assert db.query(Message).count() == 1
    finally:
        db.close()


def test_sync_full_matches_empty_historical_content_using_meta_contents(tmp_path, monkeypatch):
    Session, _engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        message = _chatlog_message(timestamp)
        _install_fake_chatlog(monkeypatch, message)
        _seed_history(
            db,
            timestamp,
            content_text="",
            meta={
                "contents": {
                    "appmsg_type": "5",
                    "title": "Chatlog 历史研报",
                    "url": "https://mp.weixin.qq.com/s/chatlog-history",
                }
            },
        )

        result = sync_service.sync_full(db, days=1)

        assert result["fetched"] == 1
        assert result["inserted"] == 0
        assert db.query(Message).count() == 1
    finally:
        db.close()


def test_compare_with_chatlog_fix_canonicalizes_historical_db_rows(tmp_path, monkeypatch):
    Session, engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        message = _chatlog_message(timestamp)
        _install_fake_chatlog(monkeypatch, message)
        monkeypatch.setattr(app_db, "engine", engine)
        _seed_history(db, timestamp, content_text=APPMSG_XML)

        result = sync_service.compare_with_chatlog(
            db,
            date=timestamp.date().isoformat(),
            fix=True,
        )

        assert result["totals"]["missing_in_db"] == 0
        assert result["totals"]["extra_in_db"] == 0
        assert result["days"][0]["repaired"] == 0
        assert db.query(Message).count() == 1
    finally:
        db.close()


def test_sync_from_chatlog_keeps_same_title_messages_with_different_urls(tmp_path, monkeypatch):
    Session, _engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        content_a = _appmsg_xml("https://mp.weixin.qq.com/s/article-a")
        content_b = _appmsg_xml("https://mp.weixin.qq.com/s/article-b")
        message_a = _chatlog_message(timestamp, content=content_a)
        message_b = _chatlog_message(timestamp, content=content_b)
        _install_fake_chatlog(monkeypatch, [message_a, message_b])
        _seed_history(db, timestamp, content_text=content_a)

        result = sync_service.sync_from_chatlog(db, since=timestamp - timedelta(minutes=1))

        assert result["fetched"] == 2
        assert result["inserted"] == 1
        assert db.query(Message).count() == 2
    finally:
        db.close()


def test_compare_with_chatlog_counts_same_title_different_url_messages_separately(tmp_path, monkeypatch):
    Session, engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        content_a = _appmsg_xml("https://mp.weixin.qq.com/s/article-a")
        content_b = _appmsg_xml("https://mp.weixin.qq.com/s/article-b")
        message_a = _chatlog_message(timestamp, content=content_a)
        message_b = _chatlog_message(timestamp, content=content_b)
        _install_fake_chatlog(monkeypatch, [message_a, message_b])
        monkeypatch.setattr(app_db, "engine", engine)
        _seed_history(db, timestamp, content_text=content_a)
        db.add(
            Message(
                chat_id="room_chatlog@chatroom",
                sender_id="wxid_chatlog_sender",
                timestamp=timestamp,
                direction="in",
                type="49",
                content_text=content_b,
                meta={},
            )
        )
        db.commit()

        result = sync_service.compare_with_chatlog(
            db,
            date=timestamp.date().isoformat(),
            fix=True,
        )

        assert result["days"][0]["chatlog"] == 2
        assert result["days"][0]["db"] == 2
        assert result["totals"]["missing_in_db"] == 0
        assert result["totals"]["extra_in_db"] == 0
        assert result["days"][0]["repaired"] == 0
        assert db.query(Message).count() == 2
    finally:
        db.close()


def test_maximum_identity_matching_handles_cross_subset_without_input_order_dependency():
    url_identity = build_wechat_message_identity(
        msg_type=49,
        content="Chatlog 历史研报",
        contents={"url": "https://mp.weixin.qq.com/s/cross-subset"},
    )
    md5_identity = build_wechat_message_identity(
        msg_type=49,
        content="Chatlog 历史研报",
        contents={"md5": "cross-subset-md5"},
    )
    rich_identity = build_wechat_message_identity(
        msg_type=49,
        content="Chatlog 历史研报",
        contents={
            "url": "https://mp.weixin.qq.com/s/cross-subset",
            "md5": "cross-subset-md5",
        },
    )

    forward = sync_service._maximum_identity_matching(
        [rich_identity, url_identity],
        [url_identity, md5_identity],
    )
    reversed_order = sync_service._maximum_identity_matching(
        [url_identity, rich_identity],
        [md5_identity, url_identity],
    )

    assert forward == {0: 1, 1: 0}
    assert reversed_order == {0: 1, 1: 0}


def test_sync_from_chatlog_consumes_each_historical_row_at_most_once(tmp_path, monkeypatch):
    Session, _engine = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.combine(datetime.now().date(), time(12, 0))
        url = "https://mp.weixin.qq.com/s/cross-subset"
        rich_message = _chatlog_message(
            timestamp,
            content=_appmsg_xml_with_md5(url, "cross-subset-md5"),
        )
        url_message = _chatlog_message(timestamp, content=_appmsg_xml(url))
        _install_fake_chatlog(monkeypatch, [rich_message, url_message])
        _seed_history(
            db,
            timestamp,
            content_text="",
            meta={
                "contents": {
                    "appmsg_type": "5",
                    "title": "Chatlog 历史研报",
                    "url": url,
                }
            },
        )

        result = sync_service.sync_from_chatlog(db, since=timestamp - timedelta(minutes=1))

        assert result["fetched"] == 2
        assert result["inserted"] == 1
        assert db.query(Message).count() == 2
    finally:
        db.close()
