from __future__ import annotations

import os
import sys
from datetime import datetime
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
from app.routers import messages as messages_router
from app.services.wechat_gateway import ingest_agent_wechat_event

API_HEADERS = ({"X-API-Token": str(settings.API_TOKEN).strip()} if str(getattr(settings, "API_TOKEN", "") or "").strip() else {})
ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "static" / "index.html"


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "message-list-wechat-media.db"
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
    app.dependency_overrides[messages_router.get_db] = override_get_db
    return TestClient(app), Session


def test_message_list_api_normalizes_wechat_gateway_image_meta_and_names(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        db.add(Contact(id="wxid_sender_1", name="王五", alias="老王"))
        db.add(Chat(id="room_1@chatroom", title="测试群", is_chatroom=True))
        db.add(
            Message(
                chat_id="room_1@chatroom",
                sender_id="wxid_sender_1",
                sender_name="wxid_sender_1",
                talker_name="room_1@chatroom",
                direction="in",
                type="image",
                content_text='<?xml version="1.0"?><msg><img cdnthumburl="https://mmbiz.qpic.cn/test-thumb.jpg" md5="abc123"></img></msg>',
                media_url=None,
                meta={"source": "wechat_gateway", "raw": {"Data": {"Content": '<?xml version="1.0"?><msg><img cdnthumburl="https://mmbiz.qpic.cn/test-thumb.jpg" md5="abc123"></img></msg>'}}},
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get('/api/messages', headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 1
    item = data['items'][0]
    assert item['sender_name'] == '老王'
    assert item['talker_name'] == '测试群'
    assert item['type'] == 'image'
    assert item['media_url'] == 'https://mmbiz.qpic.cn/test-thumb.jpg'
    assert item['meta']['contents']['cdnthumburl'] == 'https://mmbiz.qpic.cn/test-thumb.jpg'


def test_message_list_api_normalizes_wechat_gateway_names_from_meta_when_top_level_is_missing(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        db.add(
            Message(
                chat_id="room_2@chatroom",
                sender_id="wxid_sender_2",
                sender_name="",
                talker_name="",
                direction="in",
                type="image",
                content_text='<?xml version="1.0"?><msg><img cdnthumburl="https://mmbiz.qpic.cn/second-thumb.jpg"></img></msg>',
                media_url=None,
                meta={
                    "source": "wechat_gateway",
                    "sender_name": "张三",
                    "talker_name": "项目群",
                    "raw": {"Data": {"Content": '<?xml version="1.0"?><msg><img cdnthumburl="https://mmbiz.qpic.cn/second-thumb.jpg"></img></msg>'}},
                },
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get('/api/messages', headers=API_HEADERS)
    assert resp.status_code == 200
    item = resp.json()['items'][0]
    assert item['sender_name'] == '张三'
    assert item['talker_name'] == '项目群'


def test_message_list_api_repairs_historical_wechat_gateway_id_names_and_numeric_type(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        db.add(Contact(id="wxid_sender_3", name="赵六", alias="老赵"))
        db.add(Chat(id="room_3@chatroom", title="投研群", is_chatroom=True))
        db.add(
            Message(
                chat_id="room_3@chatroom",
                sender_id="wxid_sender_3",
                sender_name="wxid_sender_3",
                talker_name="room_3@chatroom",
                direction="in",
                type="49",
                content_text="旧消息",
                media_url=None,
                meta={"source": "wechat_gateway"},
                timestamp=datetime(2026, 5, 9, 10, 11, 12),
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get('/api/messages', headers=API_HEADERS)
    assert resp.status_code == 200
    item = resp.json()['items'][0]
    assert item['sender_name'] == '老赵'
    assert item['talker_name'] == '投研群'
    assert item['type'] == 'link'


def test_message_list_api_preserves_explicit_appmsg_contents_and_fills_missing_xml_fields(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        appmsg_xml = """<msg><appmsg>
          <title>XML 标题</title>
          <des>XML 补全描述</des>
          <url>https://mp.weixin.qq.com/s/xml</url>
          <type>5</type>
          <sourceusername>gh_xml</sourceusername>
          <sourcedisplayname>XML 来源</sourcedisplayname>
        </appmsg></msg>"""
        db.add(
            Message(
                chat_id="room_appmsg@chatroom",
                sender_id="wxid_appmsg_sender",
                direction="in",
                type="49",
                content_text=appmsg_xml,
                media_url=None,
                meta={
                    "source": "wechat_gateway",
                    "contents": {
                        "title": "显式标题",
                        "url": "https://mp.weixin.qq.com/s/explicit",
                        "sourceusername": "gh_explicit",
                    },
                },
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get('/api/messages', headers=API_HEADERS)
    assert resp.status_code == 200
    item = resp.json()['items'][0]
    assert item['type'] == 'link'
    assert item['content_text'] == '显式标题'
    assert item['media_url'] == 'https://mp.weixin.qq.com/s/explicit'
    assert item['meta']['contents']['title'] == '显式标题'
    assert item['meta']['contents']['url'] == 'https://mp.weixin.qq.com/s/explicit'
    assert item['meta']['contents']['sourceusername'] == 'gh_explicit'
    assert item['meta']['contents']['desc'] == 'XML 补全描述'
    assert item['meta']['contents']['sourcedisplayname'] == 'XML 来源'


def test_message_list_api_normalizes_historical_record_appmsg_as_file(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        record_xml = """<msg><appmsg>
          <title>聊天记录</title><type>24</type>
          <recorditem><![CDATA[
            <recordinfo><datalist><dataitem>
              <cdn_dataurl>record-file-id</cdn_dataurl>
              <cdn_datakey>record-file-key</cdn_datakey>
              <datatitle>历史研报.pdf</datatitle>
              <datafmt>pdf</datafmt>
              <datasize>4096</datasize>
            </dataitem></datalist></recordinfo>
          ]]></recorditem>
        </appmsg></msg>"""
        db.add(
            Message(
                chat_id="room_record@chatroom",
                sender_id="wxid_record",
                direction="in",
                type="49",
                content_text=record_xml,
                media_url=None,
                meta={"source": "wechat_gateway"},
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get('/api/messages', headers=API_HEADERS)
    assert resp.status_code == 200
    item = resp.json()['items'][0]
    assert item['type'] == 'file'
    assert item['content_text'] == '聊天记录'
    assert item['meta']['contents']['cdn_dataurl'] == 'record-file-id'
    assert item['meta']['contents']['cdndatakey'] == 'record-file-key'
    assert item['meta']['contents']['datatitle'] == '历史研报.pdf'
    assert item['meta']['contents']['datafmt'] == 'pdf'


def test_ingest_agent_wechat_event_backfills_sender_and_talker_names_from_meta(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        payload = {
            'channel': 'wechat_gateway',
            'source': 'agent',
            'message_id': 'agent-msg-1',
            'chat_id': 'room_meta@chatroom',
            'sender_id': 'wxid_meta_sender',
            'text': 'hello',
            'timestamp': '2026-05-09T10:11:12+08:00',
            'meta': {
                'sender_name': '李四',
                'talker_name': '策略讨论群',
            },
        }
        result = ingest_agent_wechat_event(db, payload)
        assert result['stored'] is True
        msg = db.get(Message, result['message_id'])
        assert msg is not None
        assert msg.sender_name == '李四'
        assert msg.talker_name == '策略讨论群'
    finally:
        db.close()


def test_ingest_agent_wechat_event_keeps_local_wall_clock_for_offset_timestamp(tmp_path):
    client, Session = _client(tmp_path)
    db = Session()
    try:
        payload = {
            'channel': 'wechat_gateway',
            'source': 'agent',
            'message_id': 'agent-msg-2',
            'chat_id': 'room_time@chatroom',
            'sender_id': 'wxid_time_sender',
            'text': 'time-check',
            'timestamp': '2026-05-09T10:11:12+08:00',
        }
        result = ingest_agent_wechat_event(db, payload)
        assert result['stored'] is True
        msg = db.get(Message, result['message_id'])
        assert msg is not None
        assert msg.timestamp == datetime(2026, 5, 9, 10, 11, 12)
    finally:
        db.close()


def test_main_message_list_frontend_recognizes_wechat_gateway_xml_image_as_image_card():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert 'normalizeWechatGatewayMedia' in source
    assert 'const normalizedMedia = normalizeWechatGatewayMedia(m);' in source
    assert "const messageType = normalizedMedia.type || mapMsgTypeCode(m.type);" in source
    assert 'media_url: normalizedMedia.media_url || m.media_url || \'' in source
    assert 'contents: normalizedMedia.contents || ((m.meta && m.meta.contents) || {})' in source


def test_main_message_list_frontend_image_card_uses_real_url_not_hash_fallback():
    source = INDEX_HTML.read_text(encoding='utf-8')
    image_block = source.split("if (typeLabel === '图片') {", 1)[1].split("const fileLikeLink", 1)[0]
    assert "a.href = url || '#';" not in image_block
    assert "a.href = url || 'javascript:void(0)';" in image_block
    assert "a.addEventListener('click', (e)=> { if (!url) e.preventDefault(); e.stopPropagation(); });" in image_block


def test_main_message_list_frontend_blacklist_reapplies_and_matches_ids_and_names():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert 'function _rowListKeys(row)' in source
    assert 'row.dataset.senderId' in source
    assert 'row.dataset.talkerName' in source
    assert "if (!_passesListFilter(listKeys)) return false;" in source
    assert "const isBlacklisted = _isBlacklisted(_rowListKeys(tr));" in source
    load_block = source.split('async function loadFiltersFromBackend()', 1)[1].split('function renderFilterLists', 1)[0]
    assert "if (typeof applyDerivedToRows === 'function') applyDerivedToRows();" in load_block
    assert "if (typeof applyFilters === 'function') applyFilters();" in load_block


def test_summary_list_content_uses_regular_font_weight():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert '.summary-text.ai { color: var(--title-accent); font-weight: 400; }' in source
    assert '.summary-col .summary-text,' in source
    assert '.summary-content .agg-summary-table .agg-summary-copy,' in source
    assert 'font-weight: 400 !important;' in source


def test_local_wechat_mp_articles_have_summary_and_detail_support():
    source = Path('app/routers/mp_rss.py').read_text(encoding='utf-8')
    assert 'def _clean_local_summary' in source
    assert 'derived.get("key_info")' in source
    assert '"heat": heat_score' in source
    assert 'if article_id.startswith("local-gh-"):' in source
    assert '"source": "wechat_gateway_local"' in source
