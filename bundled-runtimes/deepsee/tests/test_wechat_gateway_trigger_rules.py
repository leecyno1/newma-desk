from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Chat, Contact, Message, SyncState
from app.services.wechat_gateway import (
    evaluate_auto_reply_rules,
    evaluate_inbound_message,
    evaluate_outbound_message,
    ingest_callback_event,
    load_config,
    load_trigger_rules,
    save_config,
    save_trigger_rules,
)


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "wechat-gateway-rules-test.db"
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


def _sample_callback(*, chat_id: str = "room_1@chatroom", text: str = "!你好，网关", sender: str = "wxid_sender") -> dict:
    return {
        "TypeName": "AddMsg",
        "Appid": "wx_app_test",
        "Wxid": "self_wxid",
        "Data": {
            "MsgId": 101,
            "NewMsgId": 202,
            "MsgType": 1,
            "CreateTime": 1778036763,
            "PushContent": "群消息预览",
            "FromUserName": {"string": chat_id},
            "ToUserName": {"string": "self_wxid"},
            "Content": {"string": f"{sender}:\n{text}" if chat_id.endswith("@chatroom") else text},
            "MsgSource": "<msgsource><membercount>3</membercount></msgsource>",
        },
    }


def test_trigger_rules_roundtrip(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        saved = save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": False,
                "prefixes": ["!", "!", "问"],
                "regexp_patterns": [r"^你好", r"^你好"],
                "at_mention_enabled": True,
                "random_rate": 35,
                "whitelist_chat_ids_enabled": True,
                "whitelist_chat_ids": ["room_1@chatroom"],
                "blacklist_sender_ids_enabled": True,
                "blacklist_sender_ids": ["wxid_bad"],
                "min_text_length": 3,
                "human_reply_suppression_seconds": 180,
            },
        )
        loaded = load_trigger_rules(db)
        assert saved["enabled"] is True
        assert loaded["smart_reply_enabled"] is True
        assert loaded["private_enabled"] is False
        assert loaded["prefixes"] == ["!", "问"]
        assert loaded["regexp_patterns"] == [r"^你好"]
        assert loaded["at_mention_enabled"] is True
        assert loaded["random_rate"] == 35
        assert loaded["whitelist_chat_ids_enabled"] is True
        assert loaded["whitelist_chat_ids"] == ["room_1@chatroom"]
        assert loaded["blacklist_sender_ids_enabled"] is True
        assert loaded["blacklist_sender_ids"] == ["wxid_bad"]
        assert loaded["min_text_length"] == 3
        assert loaded["human_reply_suppression_seconds"] == 180
    finally:
        db.close()


def test_default_trigger_rules_enable_smart_reply_and_ai_prefix(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        loaded = load_trigger_rules(db)
        assert loaded["enabled"] is True
        assert loaded["smart_reply_enabled"] is True
        assert loaded["private_enabled"] is True
        assert loaded["prefixes"] == ["ai"]
    finally:
        db.close()


def test_gateway_config_roundtrip_dedupes_lists(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        saved = save_config(
            db,
            {
                "enabled": True,
                "outbound_enabled": True,
                "allow_chat_ids_enabled": True,
                "allow_chat_ids": ["wxid_a", "wxid_a", "room_1@chatroom"],
                "block_chat_ids_enabled": True,
                "block_chat_ids": ["wxid_b", "wxid_b"],
                "keyword_blocklist": ["广告", "广告", "拉群"],
            },
        )
        loaded = load_config(db)
        assert saved["allow_chat_ids_enabled"] is True
        assert saved["block_chat_ids_enabled"] is True
        assert saved["allow_chat_ids"] == ["wxid_a", "room_1@chatroom"]
        assert saved["block_chat_ids"] == ["wxid_b"]
        assert saved["keyword_blocklist"] == ["广告", "拉群"]
        assert loaded["allow_chat_ids_enabled"] is True
        assert loaded["block_chat_ids_enabled"] is True
        assert loaded["allow_chat_ids"] == ["wxid_a", "room_1@chatroom"]
        assert loaded["block_chat_ids"] == ["wxid_b"]
        assert loaded["keyword_blocklist"] == ["广告", "拉群"]
    finally:
        db.close()


def test_auto_reply_rules_block_short_text_and_prefix_miss(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["!"],
                "min_text_length": 3,
            },
        )
        short = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="!hi",
            is_group=True,
        )
        assert short["allowed"] is False
        assert short["reason"] == "text_too_short"

        no_prefix = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="你好 world",
            is_group=True,
        )
        assert no_prefix["allowed"] is False
        assert no_prefix["reason"] == "prefix_miss"
    finally:
        db.close()


def test_auto_reply_rules_support_group_private_and_black_white_lists(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": False,
                "prefixes": ["!"],
                "whitelist_chat_ids_enabled": True,
                "whitelist_chat_ids": ["room_1@chatroom"],
                "blacklist_sender_ids_enabled": True,
                "blacklist_sender_ids": ["wxid_bad"],
                "min_text_length": 2,
            },
        )
        group_ok = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="!你好",
            is_group=True,
        )
        assert group_ok["allowed"] is True

        private_blocked = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="!你好",
            is_group=False,
        )
        assert private_blocked["allowed"] is False
        assert private_blocked["reason"] == "private_disabled"

        sender_blocked = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_bad",
            text="!你好",
            is_group=True,
        )
        assert sender_blocked["allowed"] is False
        assert sender_blocked["reason"] == "sender_blacklisted"

        chat_blocked = evaluate_auto_reply_rules(
            db,
            chat_id="room_2@chatroom",
            sender_id="wxid_sender",
            text="!你好",
            is_group=True,
        )
        assert chat_blocked["allowed"] is False
        assert chat_blocked["reason"] == "chat_not_whitelisted"
    finally:
        db.close()


def test_auto_reply_rules_keep_lists_when_switches_disabled(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["!"],
                "whitelist_chat_ids_enabled": False,
                "whitelist_chat_ids": ["room_locked@chatroom"],
                "blacklist_sender_ids_enabled": False,
                "blacklist_sender_ids": ["wxid_blocked"],
                "min_text_length": 2,
            },
        )
        allowed = evaluate_auto_reply_rules(
            db,
            chat_id="room_other@chatroom",
            sender_id="wxid_blocked",
            text="!你好",
            is_group=True,
        )
        assert allowed["allowed"] is True
        assert allowed["reason"] == "passed"
    finally:
        db.close()


def test_gateway_allow_block_lists_require_explicit_switches(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        conf = save_config(
            db,
            {
                "enabled": True,
                "outbound_enabled": True,
                "allow_chat_ids_enabled": False,
                "allow_chat_ids": ["wxid_only"],
                "block_chat_ids_enabled": False,
                "block_chat_ids": ["wxid_blocked"],
            },
        )
        inbound_allowed = evaluate_inbound_message(conf, chat_id="wxid_other", sender_id="wxid_sender", text="hello")
        outbound_allowed = evaluate_outbound_message(conf, target="wxid_blocked", text="hello")
        assert inbound_allowed["action"] == "allow"
        assert outbound_allowed["allowed"] is True

        conf = save_config(
            db,
            {
                "allow_chat_ids_enabled": True,
                "block_chat_ids_enabled": True,
            },
        )
        inbound_blocked = evaluate_inbound_message(conf, chat_id="wxid_other", sender_id="wxid_sender", text="hello")
        outbound_allow_gate = evaluate_outbound_message(conf, target="wxid_other", text="hello")
        assert inbound_blocked["reason"] == "chat_not_whitelisted"
        assert outbound_allow_gate["reason"] == "chat_not_whitelisted"

        conf = save_config(
            db,
            {
                "allow_chat_ids_enabled": False,
                "block_chat_ids_enabled": True,
            },
        )
        inbound_blacklisted = evaluate_inbound_message(conf, chat_id="wxid_blocked", sender_id="wxid_sender", text="hello")
        outbound_blocked = evaluate_outbound_message(conf, target="wxid_blocked", text="hello")
        assert inbound_blacklisted["reason"] == "chat_blocked"
        assert outbound_blocked["reason"] == "chat_blocked"
    finally:
        db.close()


def test_auto_reply_rules_human_reply_suppression(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["!"],
                "min_text_length": 2,
                "human_reply_suppression_seconds": 3600,
            },
        )
        save_config(db, {"enabled": True, "outbound_enabled": True})
        ingest_callback_event(db, _sample_callback(text="!上一条"))
        db.add(
            Message(
                chat_id="room_1@chatroom",
                sender_id="self_wxid",
                sender_name="self_wxid",
                talker_name="room_1@chatroom",
                timestamp=datetime.utcnow(),
                direction="out",
                type="text",
                content_text="人工已回复",
                meta={"source": "manual_test", "human_manual": True},
            )
        )
        db.commit()

        blocked = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="!继续问",
            is_group=True,
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "human_reply_suppressed"
    finally:
        db.close()


def test_auto_reply_rules_ignore_auto_reply_and_system_echo_for_human_reply_suppression(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": False,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
                "human_reply_suppression_seconds": 10,
            },
        )

        now = datetime.utcnow()
        db.add(
            Message(
                chat_id="wxid_friend",
                sender_id=None,
                sender_name=None,
                talker_name="wxid_friend",
                timestamp=now - timedelta(seconds=2),
                direction="out",
                type="text",
                content_text="这是自动回复",
                meta={
                    "source": "wechat_gateway",
                    "external_new_msg_id": "9001",
                    "auto_reply": {"trigger_message_id": 1},
                },
            )
        )
        db.add(
            Message(
                chat_id="wxid_friend",
                sender_id="self_wxid",
                sender_name="self_wxid",
                talker_name="wxid_friend",
                timestamp=now - timedelta(seconds=1),
                direction="out",
                type="other",
                content_text='<msg><op id="1"><name>lastMessage</name><arg>{"messageSvrId":"9001"}</arg></op></msg>',
                meta={
                    "source": "wechat_gateway",
                    "event_type": "AddMsg",
                    "msg_type": 51,
                    "manual": True,
                    "human_manual": True,
                },
            )
        )
        db.commit()

        allowed = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="ai 继续问",
            is_group=False,
        )
        assert allowed["allowed"] is True
        assert allowed["reason"] == "passed"

        db.add(
            Message(
                chat_id="wxid_friend",
                sender_id="self_wxid",
                sender_name="self_wxid",
                talker_name="wxid_friend",
                timestamp=datetime.utcnow(),
                direction="out",
                type="text",
                content_text="这是人工回复",
                meta={
                    "source": "wechat_gateway",
                    "manual": True,
                },
            )
        )
        db.commit()

        blocked = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="ai 再问一次",
            is_group=False,
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "human_reply_suppressed"
    finally:
        db.close()

def test_auto_reply_rules_unknown_type_51_manual_callback_still_suppresses(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": False,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
                "human_reply_suppression_seconds": 10,
            },
        )
        db.add(
            Message(
                chat_id="wxid_friend",
                sender_id="self_wxid",
                sender_name="self_wxid",
                talker_name="wxid_friend",
                timestamp=datetime.utcnow(),
                direction="out",
                type="other",
                content_text='<msg><op id="1"><name>lastMessage</name><arg>{"messageSvrId":"not_bot"}</arg></op></msg>',
                meta={
                    "source": "wechat_gateway",
                    "event_type": "AddMsg",
                    "msg_type": 51,
                    "manual": True,
                    "human_manual": True,
                },
            )
        )
        db.commit()

        blocked = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="ai 再问一次",
            is_group=False,
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "human_reply_suppressed"
    finally:
        db.close()


def test_auto_reply_rules_human_reply_suppression_uses_incoming_message_timestamp(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": False,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
                "human_reply_suppression_seconds": 10,
            },
        )

        manual_reply_at = datetime.utcnow() - timedelta(seconds=20)
        inbound_message_at = manual_reply_at + timedelta(seconds=8)
        db.add(
            Message(
                chat_id="wxid_friend",
                sender_id="self_wxid",
                sender_name="self_wxid",
                talker_name="wxid_friend",
                timestamp=manual_reply_at,
                direction="out",
                type="text",
                content_text="这是人工回复",
                meta={
                    "source": "wechat_gateway",
                    "manual": True,
                },
            )
        )
        db.commit()

        blocked = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="ai 再问一次",
            is_group=False,
            message_time=inbound_message_at,
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "human_reply_suppressed"
    finally:
        db.close()


def test_auto_reply_rules_human_reply_suppression_uses_real_wechat_outbound_callback(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": False,
                "private_enabled": True,
                "prefixes": ["ai"],
                "min_text_length": 2,
                "human_reply_suppression_seconds": 20,
            },
        )
        ingest_callback_event(
            db,
            {
                "TypeName": "AddMsg",
                "Appid": "wx_app_test",
                "Wxid": "self_wxid",
                "Data": {
                    "MsgId": 201,
                    "NewMsgId": 301,
                    "MsgType": 1,
                    "CreateTime": 1778036763,
                    "FromUserName": {"string": "self_wxid"},
                    "ToUserName": {"string": "wxid_friend"},
                    "Content": {"string": "这是人工回复"},
                    "MsgSource": "<msgsource></msgsource>",
                },
            },
        )

        blocked = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="ai 继续问",
            is_group=False,
            message_time=datetime.fromtimestamp(1778036763).isoformat(),
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "human_reply_suppressed"
    finally:
        db.close()


def test_auto_reply_rules_require_smart_reply_switch(tmp_path):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": False,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": ["!"],
                "min_text_length": 2,
            },
        )
        result = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="!你好",
            is_group=True,
        )
        assert result["allowed"] is False
        assert result["reason"] == "smart_reply_disabled"
    finally:
        db.close()


def test_auto_reply_rules_support_regexp_random_and_at_mention(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    db = Session()
    try:
        save_trigger_rules(
            db,
            {
                "enabled": True,
                "smart_reply_enabled": True,
                "group_enabled": True,
                "private_enabled": True,
                "prefixes": [],
                "regexp_patterns": [r"^你好"],
                "random_rate": 0,
                "min_text_length": 2,
            },
        )

        regex_ok = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="你好，请回复",
            is_group=False,
        )
        assert regex_ok["allowed"] is True
        assert regex_ok["matched_by"] == "regexp"

        regex_miss = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="hello",
            is_group=False,
        )
        assert regex_miss["allowed"] is False
        assert regex_miss["reason"] == "regexp_miss"

        save_trigger_rules(
            db,
            {
                "regexp_patterns": [],
                "random_rate": 100,
            },
        )
        monkeypatch.setattr("app.services.wechat_gateway.random.random", lambda: 0.01)
        random_ok = evaluate_auto_reply_rules(
            db,
            chat_id="wxid_friend",
            sender_id="wxid_friend",
            text="随便来一句",
            is_group=False,
        )
        assert random_ok["allowed"] is True
        assert random_ok["matched_by"] == "random"

        save_trigger_rules(
            db,
            {
                "random_rate": 0,
                "at_mention_enabled": True,
            },
        )
        mention_ok = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="你好机器人",
            is_group=True,
            message_meta={
                "raw": {
                    "Wxid": "self_wxid",
                    "Data": {
                        "MsgSource": "<msgsource><atuserlist><![CDATA[,self_wxid]]></atuserlist></msgsource>",
                    },
                }
            },
        )
        assert mention_ok["allowed"] is True
        assert mention_ok["matched_by"] == "at_mention"

        mention_miss = evaluate_auto_reply_rules(
            db,
            chat_id="room_1@chatroom",
            sender_id="wxid_sender",
            text="你好机器人",
            is_group=True,
            message_meta={
                "raw": {
                    "Wxid": "self_wxid",
                    "Data": {"MsgSource": "<msgsource></msgsource>"},
                }
            },
        )
        assert mention_miss["allowed"] is False
        assert mention_miss["reason"] == "at_mention_required"
    finally:
        db.close()
