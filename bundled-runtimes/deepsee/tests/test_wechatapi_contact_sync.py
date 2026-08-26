from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Chat, Contact, SyncState
from app.routers import contacts as contacts_router
from app.services.wechat_contact_sync import sync_contacts_from_wechatapi
from app.services.wechatapi_client import WechatApiClient


def _db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'contacts.db'}", future=True)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine, tables=[Contact.__table__, Chat.__table__, SyncState.__table__])
    return Session()


def test_fetch_contacts_list_uses_long_request_timeout():
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ret": 200, "msg": "ok", "data": {"friends": [], "chatrooms": [], "ghs": []}}

    class _Session:
        trust_env = False

        def post(self, url, json, headers, timeout):
            captured.update(url=url, payload=json, timeout=timeout)
            return _Response()

    client = WechatApiClient(base_url="http://api.example", token="token", app_id="app")
    client._session = _Session()

    client.fetch_contacts_list()

    assert captured["url"].endswith("/contacts/fetchContactsList")
    assert captured["timeout"] >= 120


def test_sync_contacts_uses_wechatapi_roster_details_and_labels(tmp_path):
    class _Client:
        def configured(self):
            return True

        def fetch_contacts_list(self):
            return {
                "ret": 200,
                "data": {
                    "friends": ["wxid_a", "room_from_friends@chatroom", "gh_from_friends"],
                    "chatrooms": ["room_a@chatroom"],
                    "ghs": ["gh_a"],
                },
            }

        def fetch_contacts_list_cache(self):
            raise AssertionError("fresh roster succeeded; cache should not be used")

        def list_labels(self):
            return {
                "ret": 200,
                "data": {
                    "labelList": [
                        {"labelId": 36, "labelName": "发观点"},
                        {"labelId": 37, "labelName": "险资"},
                    ]
                },
            }

        def get_brief_info(self, *, wxids):
            assert len(wxids) <= 20
            rows = {
                "wxid_a": {
                    "userName": "wxid_a",
                    "nickName": "昵称A",
                    "remark": "侯先生",
                    "alias": "hou-a",
                    "labelList": "36,37",
                },
                "room_a@chatroom": {
                    "userName": "room_a@chatroom",
                    "nickName": "群A",
                    "remark": "",
                    "labelList": "",
                },
                "room_from_friends@chatroom": {
                    "userName": "room_from_friends@chatroom",
                    "nickName": "误归类群",
                    "remark": "",
                    "labelList": "",
                },
                "gh_a": {"userName": "gh_a", "nickName": "公众号A", "remark": "", "labelList": ""},
                "gh_from_friends": {
                    "userName": "gh_from_friends",
                    "nickName": "误归类公众号",
                    "remark": "",
                    "labelList": "",
                },
            }
            return {"ret": 200, "data": [rows[wxid] for wxid in wxids]}

    db = _db(tmp_path)
    try:
        db.add(Contact(id="wxid_a", name="旧昵称", alias=None, rating=88, stats={"manual_rating": 88}))
        db.commit()

        stats = sync_contacts_from_wechatapi(db, client=_Client(), detail_workers=1)

        contact = db.get(Contact, "wxid_a")
        assert contact is not None
        assert contact.name == "昵称A"
        assert contact.alias == "侯先生"
        assert contact.rating == 88
        assert contact.stats == {"manual_rating": 88}
        assert contact.labels == {
            "tags": ["发观点", "险资"],
            "label_ids": ["36", "37"],
            "source": "wechatapi_gateway",
        }

        room = db.get(Chat, "room_a@chatroom")
        moved_room = db.get(Chat, "room_from_friends@chatroom")
        official = db.get(Chat, "gh_a")
        assert room is not None and room.title == "群A" and room.is_chatroom is True
        assert moved_room is not None and moved_room.is_chatroom is True
        assert official is not None and official.type == "official"

        assert stats["source"] == "wechatapi_gateway"
        assert stats["friends"] == 1
        assert stats["chatrooms"] == 2
        assert stats["official_accounts"] == 2
        assert stats["labels"] == 2
        assert db.get(SyncState, "wechatapi_contacts_cache_v1") is not None

        db.add(
            Contact(
                id="legacy_only",
                name="历史联系人",
                alias=None,
                rating=50,
                labels={"tags": ["旧标签"], "source": "chatlog_contact_db"},
                stats={},
            )
        )
        db.commit()
        api_only = contacts_router.list_contacts(
            include_labels=True,
            wechatapi_only=True,
            db=db,
        )
        assert [row.id for row in api_only] == ["wxid_a"]
    finally:
        db.close()
