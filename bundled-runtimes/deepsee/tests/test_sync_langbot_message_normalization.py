from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import AdapterMessage, Chat, Contact, ExtAdapter, Message, SyncState
from app.services.sync_service import sync_from_langbot_adapters


APPMSG_XML = """<msg><appmsg>
  <title>LangBot 研报</title>
  <des>同步幂等测试</des>
  <url>https://mp.weixin.qq.com/s/langbot-dedupe</url>
  <type>5</type>
</appmsg></msg>"""


def _appmsg_xml(url: str, *, title: str = "相同标题的 LangBot 链接") -> str:
    return f"""<msg><appmsg>
  <title>{title}</title>
  <des>canonical identity 集成测试</des>
  <url>{url}</url>
  <type>5</type>
</appmsg></msg>"""


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "langbot-normalization.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(
        engine,
        tables=[
            Chat.__table__,
            Contact.__table__,
            Message.__table__,
            SyncState.__table__,
            ExtAdapter.__table__,
            AdapterMessage.__table__,
        ],
    )
    return TestingSession


def _seed_adapter_message(db, timestamp: datetime) -> None:
    db.add(
        ExtAdapter(
            key="langbot",
            name="LangBot",
            enabled=True,
            source_type="langbot",
            config={},
        )
    )
    db.add(
        AdapterMessage(
            adapter_key="langbot",
            external_id="langbot-appmsg-1",
            chat_id="room_langbot@chatroom",
            sender="wxid_langbot_sender",
            timestamp=timestamp,
            direction="in",
            content_text=APPMSG_XML,
            meta={"type": 49, "sender_name": "LangBot 发送人", "talker_name": "LangBot 群"},
        )
    )
    db.commit()


def test_sync_from_langbot_adapters_is_idempotent_after_content_normalization(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
        _seed_adapter_message(db, timestamp)
        since = timestamp - timedelta(minutes=1)

        first = sync_from_langbot_adapters(
            db,
            since=since,
            adapter_keys=["langbot"],
            ingest=False,
            force=True,
        )
        second = sync_from_langbot_adapters(
            db,
            since=since,
            adapter_keys=["langbot"],
            ingest=False,
            force=True,
        )

        assert first["inserted"] == 1
        assert second["inserted"] == 0
        rows = db.query(Message).all()
        assert len(rows) == 1
        assert rows[0].content_text == "LangBot 研报"
        assert rows[0].type == "link"
    finally:
        db.close()


def test_sync_from_langbot_adapters_matches_historical_raw_content_rows(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
        _seed_adapter_message(db, timestamp)
        db.add(Chat(id="room_langbot@chatroom", title="LangBot 群", is_chatroom=True))
        db.add(
            Message(
                chat_id="room_langbot@chatroom",
                sender_id="wxid_langbot_sender",
                timestamp=timestamp,
                direction="in",
                type="49",
                content_text=APPMSG_XML,
                meta={"source": "langbot"},
            )
        )
        db.commit()

        result = sync_from_langbot_adapters(
            db,
            since=timestamp - timedelta(minutes=1),
            adapter_keys=["langbot"],
            ingest=False,
            force=True,
        )

        assert result["inserted"] == 0
        assert db.query(Message).count() == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    ("external_id_a", "external_id_b"),
    [
        ("langbot-link-a", "langbot-link-b"),
        (None, None),
    ],
)
def test_sync_from_langbot_adapters_keeps_same_title_links_with_distinct_urls(
    tmp_path,
    external_id_a,
    external_id_b,
):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
        since = timestamp - timedelta(minutes=1)
        db.add(
            ExtAdapter(
                key="langbot",
                name="LangBot",
                enabled=True,
                source_type="langbot",
                config={},
            )
        )
        db.add(
            AdapterMessage(
                adapter_key="langbot",
                external_id=external_id_a,
                chat_id="room_langbot@chatroom",
                sender="wxid_langbot_sender",
                timestamp=timestamp,
                direction="in",
                content_text=_appmsg_xml("https://mp.weixin.qq.com/s/langbot-link-a"),
                meta={"type": 49, "sender_name": "LangBot 发送人", "talker_name": "LangBot 群"},
            )
        )
        db.commit()

        first = sync_from_langbot_adapters(
            db,
            since=since,
            adapter_keys=["langbot"],
            ingest=False,
        )

        db.add(
            AdapterMessage(
                adapter_key="langbot",
                external_id=external_id_b,
                chat_id="room_langbot@chatroom",
                sender="wxid_langbot_sender",
                timestamp=timestamp,
                direction="in",
                content_text=_appmsg_xml("https://mp.weixin.qq.com/s/langbot-link-b"),
                meta={"type": 49, "sender_name": "LangBot 发送人", "talker_name": "LangBot 群"},
            )
        )
        db.commit()

        second = sync_from_langbot_adapters(
            db,
            since=since,
            adapter_keys=["langbot"],
            ingest=False,
        )

        assert first["scanned"] == 1
        assert first["inserted"] == 1
        assert second["scanned"] == 1
        assert second["inserted"] == 1
        assert second["details"][0]["cursor"] == 2

        rows = db.query(Message).order_by(Message.id.asc()).all()
        assert len(rows) == 2
        assert [row.content_text for row in rows] == [
            "相同标题的 LangBot 链接",
            "相同标题的 LangBot 链接",
        ]
        assert [(row.meta or {}).get("contents", {}).get("url") for row in rows] == [
            "https://mp.weixin.qq.com/s/langbot-link-a",
            "https://mp.weixin.qq.com/s/langbot-link-b",
        ]
        if external_id_a is not None:
            assert [(row.meta or {}).get("external_id") for row in rows] == [
                external_id_a,
                external_id_b,
            ]
    finally:
        db.close()


def test_sync_from_langbot_adapters_dedupes_same_external_id_with_changed_content(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
        db.add(
            ExtAdapter(
                key="langbot",
                name="LangBot",
                enabled=True,
                source_type="langbot",
                config={},
            )
        )
        for url, title in (
            ("https://mp.weixin.qq.com/s/langbot-same-id-a", "原始标题"),
            ("https://mp.weixin.qq.com/s/langbot-same-id-b", "更新后的标题"),
        ):
            db.add(
                AdapterMessage(
                    adapter_key="langbot",
                    external_id="langbot-stable-id",
                    chat_id="room_langbot@chatroom",
                    sender="wxid_langbot_sender",
                    timestamp=timestamp,
                    direction="in",
                    content_text=_appmsg_xml(url, title=title),
                    meta={"type": 49, "sender_name": "LangBot 发送人", "talker_name": "LangBot 群"},
                )
            )
        db.commit()

        result = sync_from_langbot_adapters(
            db,
            since=timestamp - timedelta(minutes=1),
            adapter_keys=["langbot"],
            ingest=False,
            force=True,
        )

        assert result["scanned"] == 2
        assert result["inserted"] == 1
        rows = db.query(Message).all()
        assert len(rows) == 1
        assert (rows[0].meta or {}).get("external_id") == "langbot-stable-id"
    finally:
        db.close()
