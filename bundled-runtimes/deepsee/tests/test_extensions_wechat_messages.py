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
from app.models import Chat, Contact, Message, SyncState
from app.routers import extensions as extensions_router
from app.services.sync_service import _build_chatlog_media_url
from app.services.wechat_gateway import ingest_callback_event

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})
ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "static" / "index.html"


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "extensions-wechat-main-table.db"
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
    return TestingSession


def _client(tmp_path: Path) -> tuple[TestClient, sessionmaker]:
    Session = _session_factory(tmp_path)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[extensions_router.get_db] = override_get_db
    return TestClient(app), Session


def test_extensions_wechat_messages_main_table_exposes_chinese_names_and_image_meta(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        db.add(Contact(id="wxid_sender_ext", name="王五", alias="老王"))
        db.add(Chat(id="room_ext@chatroom", title="微信测试群", is_chatroom=True))
        db.commit()

        result = ingest_callback_event(
            db,
            {
                "TypeName": "AddMsg",
                "Appid": "wx_app_test_ext",
                "Wxid": "self_wxid_ext",
                "Data": {
                    "NewMsgId": "ext-1",
                    "MsgId": "msg-ext-1",
                    "FromUserName": "room_ext@chatroom",
                    "ToUserName": "self_wxid_ext",
                    "Content": (
                        '<?xml version="1.0"?><msg><fromusername>wxid_sender_ext</fromusername><img '
                        'cdnthumburl="https://mmbiz.qpic.cn/test-thumb.jpg" '
                        'md5="abc123"></img></msg>'
                    ),
                    "MsgType": 3,
                    "CreateTime": 1778299200,
                },
            },
        )
        assert result["stored"] is True
    finally:
        db.close()

    resp = client.get("/api/extensions/messages", params={"adapter_key": "wechat"}, headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["adapter_key"] == "wechat"
    assert item["external_id"] == "ext-1"
    assert item["sender"] == "老王"
    assert item["chat_id"] == "room_ext@chatroom"
    assert item["meta"]["sender_name"] == "老王"
    assert item["meta"]["talker_name"] == "微信测试群"
    assert item["meta"]["source"] == "wechat_gateway"
    assert item["meta"]["media_url"] == "https://mmbiz.qpic.cn/test-thumb.jpg"
    assert item["meta"]["contents"]["cdnthumburl"] == "https://mmbiz.qpic.cn/test-thumb.jpg"


def test_extensions_wechat_messages_uses_stored_canonical_file_contents(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        db.add(
            Message(
                chat_id="room_file_ext@chatroom",
                sender_id="wxid_file_ext",
                sender_name="文件发送人",
                talker_name="文件群",
                direction="in",
                type="file",
                content_text="扩展报告.pdf",
                media_url="https://files.example.com/extension-report.pdf",
                meta={
                    "source": "wechat_gateway",
                    "external_new_msg_id": "ext-file-1",
                    "contents": {
                        "appmsg_type": "6",
                        "title": "扩展报告.pdf",
                        "url": "https://files.example.com/extension-report.pdf",
                        "attachid": "extension-attach-1",
                        "cdnattachurl": "extension-cdn-1",
                        "aeskey": "extension-key-1",
                        "fileext": "pdf",
                        "totallen": "1024",
                    },
                },
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/extensions/messages", params={"adapter_key": "wechat"}, headers=API_HEADERS)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["external_id"] == "ext-file-1"
    assert item["meta"]["media_url"] == "https://files.example.com/extension-report.pdf"
    assert item["meta"]["contents"]["appmsg_type"] == "6"
    assert item["meta"]["contents"]["attachid"] == "extension-attach-1"
    assert item["meta"]["contents"]["cdnattachurl"] == "extension-cdn-1"
    assert item["meta"]["contents"]["aeskey"] == "extension-key-1"


def test_build_chatlog_media_url_supports_cdnthumburl_image_preview():
    url = _build_chatlog_media_url(
        3,
        {
            "cdnthumburl": "https://mmbiz.qpic.cn/test-thumb.jpg",
        },
    )
    assert url == "https://mmbiz.qpic.cn/test-thumb.jpg"


def test_wechat_adapter_page_keeps_media_card_rendering_for_main_table_rows():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert 'buildMediaCell({' in source
    assert 'resolverUrl || pickUrl(\'image\')' in source
    assert 'const talker = String(it?.meta?.talker_name || it.chat_id || \'\').trim();' in source
