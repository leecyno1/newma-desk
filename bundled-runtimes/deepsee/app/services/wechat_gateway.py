from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..models import Chat, Contact, Message, SyncState, WechatSubsession, WechatSubsessionMembership, WechatSubsessionTurn
from .wechat_message_normalizer import (
    extract_app_message_fields,
    normalize_message_type,
    normalize_wechat_message,
)

CONFIG_KEY = "wechat_gateway_config"
TRIGGER_RULES_KEY = "wechat_gateway_trigger_rules"
DEDUP_PREFIX = "wechat_gateway_dedup"
AUTO_REPLY_ATTEMPT_PREFIX = "wechat_auto_reply_attempt"
AUTO_REPLY_DELIVERY_PREFIX = "wechat_auto_reply_delivery"
_RULE_SCOPE = "wechat_gateway"
_GROUP_TEXT_PREFIX_RE = re.compile(r"^(?P<sender>[^:\n]{1,128}):\n(?P<body>.*)$", re.DOTALL)

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "outbound_enabled": False,
    "sessionized_reply_enabled": False,
    "fixed_subsession_enabled": False,
    "fixed_subsession_id": "",
    "fixed_subsession_name": "",
    "auto_learn_subsession_members": True,
    "base_url": "http://api.wechatapi.net/finder/v2/api",
    "header_name": "VideosApi-token",
    "token": "",
    "app_id": "",
    "callback_path": "/api/wechat-gateway/callback",
    "callback_public_url": "",
    "device_type": "ipad",
    "region_id": "11000",
    "allow_chat_ids_enabled": False,
    "allow_chat_ids": [],
    "block_chat_ids_enabled": False,
    "block_chat_ids": [],
    "keyword_blocklist": [],
    "rate_limit_per_chat_per_minute": 30,
    "outbound_random_delay_min_seconds": 0,
    "outbound_random_delay_max_seconds": 0,
}

DEFAULT_TRIGGER_RULES: dict[str, Any] = {
    "enabled": True,
    "smart_reply_enabled": True,
    "group_enabled": True,
    "private_enabled": True,
    "prefixes": ["ai"],
    "regexp_patterns": [],
    "at_mention_enabled": True,
    "random_rate": 0,
    "whitelist_chat_ids_enabled": False,
    "whitelist_chat_ids": [],
    "blacklist_chat_ids_enabled": False,
    "blacklist_chat_ids": [],
    "whitelist_sender_ids_enabled": False,
    "whitelist_sender_ids": [],
    "blacklist_sender_ids_enabled": False,
    "blacklist_sender_ids": [],
    "private_wakeup_window_seconds": 180,
    "private_wakeup_whitelist_enabled": False,
    "private_wakeup_whitelist_chat_ids": [],
    "private_wakeup_exit_commands": [],
    "min_text_length": 1,
    "human_reply_suppression_seconds": 0,
}


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _dedupe_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(low, min(high, parsed))


def _normalize_callback_public_url(value: Any, callback_path: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = str(callback_path or DEFAULT_CONFIG["callback_path"]).strip() or DEFAULT_CONFIG["callback_path"]
    if not path.startswith("/"):
        path = f"/{path}"
    stripped = text.rstrip("/")
    lowered = stripped.lower()
    if lowered.endswith(path.lower()):
        return stripped
    scheme_idx = stripped.find("://")
    path_start = stripped.find("/", scheme_idx + 3) if scheme_idx >= 0 else stripped.find("/")
    if path_start == -1:
        return f"{stripped}{path}"
    existing_path = stripped[path_start:]
    if existing_path in {"", "/"}:
        return f"{stripped[:path_start]}{path}"
    return stripped


def _load_state_dict(db: Session, key: str) -> dict[str, Any]:
    row = db.get(SyncState, key)
    return _json_load(row.value if row else None)


def _save_state_dict(db: Session, key: str, payload: dict[str, Any]) -> None:
    row = db.get(SyncState, key)
    serialized = json.dumps(payload, ensure_ascii=False)
    if not row:
        row = SyncState(key=key, value=serialized)
    else:
        row.value = serialized
    db.add(row)
    db.commit()
    db.refresh(row)


def _normalize_trigger_rules(payload: dict[str, Any] | None) -> dict[str, Any]:
    conf = dict(DEFAULT_TRIGGER_RULES)
    conf.update({k: v for k, v in (payload or {}).items() if v is not None})
    for key in (
        "prefixes",
        "regexp_patterns",
        "whitelist_chat_ids",
        "blacklist_chat_ids",
        "whitelist_sender_ids",
        "blacklist_sender_ids",
        "private_wakeup_whitelist_chat_ids",
        "private_wakeup_exit_commands",
    ):
        conf[key] = _dedupe_list(conf.get(key))
    conf["enabled"] = bool(conf.get("enabled"))
    conf["smart_reply_enabled"] = bool(conf.get("smart_reply_enabled"))
    conf["group_enabled"] = bool(conf.get("group_enabled"))
    conf["private_enabled"] = bool(conf.get("private_enabled"))
    conf["at_mention_enabled"] = bool(conf.get("at_mention_enabled"))
    conf["whitelist_chat_ids_enabled"] = bool(conf.get("whitelist_chat_ids_enabled"))
    conf["blacklist_chat_ids_enabled"] = bool(conf.get("blacklist_chat_ids_enabled"))
    conf["whitelist_sender_ids_enabled"] = bool(conf.get("whitelist_sender_ids_enabled"))
    conf["blacklist_sender_ids_enabled"] = bool(conf.get("blacklist_sender_ids_enabled"))
    conf["private_wakeup_whitelist_enabled"] = bool(conf.get("private_wakeup_whitelist_enabled"))
    conf["min_text_length"] = _clamp_int(conf.get("min_text_length"), 1, 0, 10000)
    conf["random_rate"] = _clamp_int(conf.get("random_rate"), 0, 0, 100)
    conf["human_reply_suppression_seconds"] = _clamp_int(conf.get("human_reply_suppression_seconds"), 0, 0, 864000)
    conf["private_wakeup_window_seconds"] = _clamp_int(conf.get("private_wakeup_window_seconds"), 180, 0, 864000)
    return conf


def load_trigger_rules(db: Session) -> dict[str, Any]:
    return _normalize_trigger_rules(_load_state_dict(db, TRIGGER_RULES_KEY))


def save_trigger_rules(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = load_trigger_rules(db)
    merged = {**current, **(payload or {})}
    normalized = _normalize_trigger_rules(merged)
    _save_state_dict(db, TRIGGER_RULES_KEY, normalized)
    return normalized


def load_config(db: Session) -> dict[str, Any]:
    row = db.get(SyncState, CONFIG_KEY)
    raw = _json_load(row.value if row else None)
    conf = dict(DEFAULT_CONFIG)
    conf.update({k: v for k, v in raw.items() if v is not None})
    conf.pop("allow_sender_ids", None)
    conf.pop("block_sender_ids", None)
    for key in ("allow_chat_ids", "block_chat_ids", "keyword_blocklist"):
        conf[key] = _dedupe_list(conf.get(key))
    conf["enabled"] = bool(conf.get("enabled"))
    conf["outbound_enabled"] = bool(conf.get("outbound_enabled"))
    conf["sessionized_reply_enabled"] = bool(conf.get("sessionized_reply_enabled"))
    conf["fixed_subsession_enabled"] = bool(conf.get("fixed_subsession_enabled"))
    conf["auto_learn_subsession_members"] = bool(conf.get("auto_learn_subsession_members", True))
    conf["allow_chat_ids_enabled"] = bool(conf.get("allow_chat_ids_enabled"))
    conf["block_chat_ids_enabled"] = bool(conf.get("block_chat_ids_enabled"))
    conf["rate_limit_per_chat_per_minute"] = _clamp_int(conf.get("rate_limit_per_chat_per_minute"), 30, 1, 5000)
    min_delay = _clamp_int(conf.get("outbound_random_delay_min_seconds"), 0, 0, 3600)
    max_delay = _clamp_int(conf.get("outbound_random_delay_max_seconds"), 0, 0, 3600)
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    conf["outbound_random_delay_min_seconds"] = min_delay
    conf["outbound_random_delay_max_seconds"] = max_delay
    conf["base_url"] = str(conf.get("base_url") or DEFAULT_CONFIG["base_url"]).strip().rstrip("/")
    conf["header_name"] = str(conf.get("header_name") or DEFAULT_CONFIG["header_name"]).strip() or DEFAULT_CONFIG["header_name"]
    conf["callback_path"] = str(conf.get("callback_path") or DEFAULT_CONFIG["callback_path"]).strip() or DEFAULT_CONFIG["callback_path"]
    conf["device_type"] = str(conf.get("device_type") or DEFAULT_CONFIG["device_type"]).strip() or DEFAULT_CONFIG["device_type"]
    conf["region_id"] = str(conf.get("region_id") or DEFAULT_CONFIG["region_id"]).strip() or DEFAULT_CONFIG["region_id"]
    conf["token"] = str(conf.get("token") or "").strip()
    conf["app_id"] = str(conf.get("app_id") or "").strip()
    conf["fixed_subsession_id"] = str(conf.get("fixed_subsession_id") or "").strip()
    conf["fixed_subsession_name"] = str(conf.get("fixed_subsession_name") or "").strip()
    conf["callback_public_url"] = _normalize_callback_public_url(conf.get("callback_public_url"), conf["callback_path"])
    return conf


def save_config(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = load_config(db)
    merged = {**current, **(payload or {})}
    normalized = load_config_from_payload(merged)
    row = db.get(SyncState, CONFIG_KEY)
    serialized = json.dumps(normalized, ensure_ascii=False)
    if not row:
        row = SyncState(key=CONFIG_KEY, value=serialized)
    else:
        row.value = serialized
    db.add(row)
    db.commit()
    db.refresh(row)
    return normalized


def load_subsession_config(db: Session, subsession_id: str) -> dict[str, Any] | None:
    sid = _normalize_subsession_id(subsession_id)
    if not sid:
        return None
    row = db.get(WechatSubsession, sid)
    if not row:
        return None
    return {
        "id": row.id,
        "channel": row.channel,
        "name": row.name,
        "enabled": bool(row.enabled),
        "mode": row.mode,
        "system_prompt": row.system_prompt,
        "workflow_guardrails": row.workflow_guardrails,
        "model_route_kind": row.model_route_kind,
        "model_route_key": row.model_route_key,
        "model_override": row.model_override,
        "history_max_messages": row.history_max_messages,
        "history_max_tokens": row.history_max_tokens,
        "rolling_summary": row.rolling_summary,
        "pinned_memory": row.pinned_memory,
        "allow_cross_chat_context": bool(row.allow_cross_chat_context),
        "allow_cross_sender_context": bool(row.allow_cross_sender_context),
    }


def save_subsession_config(db: Session, *, subsession_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sid = _normalize_subsession_id(subsession_id)
    if not sid:
        raise ValueError("invalid subsession_id")
    row = db.get(WechatSubsession, sid)
    now = datetime.now()
    if not row:
        row = WechatSubsession(
            id=sid,
            channel="wechat_gateway",
            name=sid,
            enabled=True,
            mode="fixed",
            last_active_at=now,
        )
        db.add(row)
        db.flush()
    if "name" in payload and payload.get("name") is not None:
        row.name = str(payload.get("name") or "").strip() or row.name
    if "enabled" in payload and payload.get("enabled") is not None:
        row.enabled = bool(payload.get("enabled"))
    if "mode" in payload and payload.get("mode") is not None:
        row.mode = str(payload.get("mode") or "").strip() or row.mode or "fixed"
    if "system_prompt" in payload:
        row.system_prompt = str(payload.get("system_prompt") or "").strip() or None
    if "workflow_guardrails" in payload:
        row.workflow_guardrails = payload.get("workflow_guardrails") if isinstance(payload.get("workflow_guardrails"), dict) else None
    if "model_route_kind" in payload:
        row.model_route_kind = str(payload.get("model_route_kind") or "").strip() or None
    if "model_route_key" in payload:
        row.model_route_key = str(payload.get("model_route_key") or "").strip() or None
    if "model_override" in payload:
        row.model_override = str(payload.get("model_override") or "").strip() or None
    if "history_max_messages" in payload and payload.get("history_max_messages") is not None:
        row.history_max_messages = _clamp_int(payload.get("history_max_messages"), row.history_max_messages or 30, 1, 500)
    if "history_max_tokens" in payload and payload.get("history_max_tokens") is not None:
        row.history_max_tokens = _clamp_int(payload.get("history_max_tokens"), row.history_max_tokens or 4000, 256, 64000)
    if "rolling_summary" in payload:
        row.rolling_summary = str(payload.get("rolling_summary") or "").strip() or None
    if "pinned_memory" in payload:
        row.pinned_memory = payload.get("pinned_memory") if isinstance(payload.get("pinned_memory"), dict) else None
    if "allow_cross_chat_context" in payload and payload.get("allow_cross_chat_context") is not None:
        row.allow_cross_chat_context = bool(payload.get("allow_cross_chat_context"))
    if "allow_cross_sender_context" in payload and payload.get("allow_cross_sender_context") is not None:
        row.allow_cross_sender_context = bool(payload.get("allow_cross_sender_context"))
    row.channel = "wechat_gateway"
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    loaded = load_subsession_config(db, sid)
    if loaded is None:
        raise RuntimeError("failed to load saved subsession config")
    return loaded


def load_config_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    conf = dict(DEFAULT_CONFIG)
    conf.update({k: v for k, v in (payload or {}).items() if v is not None})
    conf.pop("allow_sender_ids", None)
    conf.pop("block_sender_ids", None)
    for key in ("allow_chat_ids", "block_chat_ids", "keyword_blocklist"):
        conf[key] = _dedupe_list(conf.get(key))
    conf["enabled"] = bool(conf.get("enabled"))
    conf["outbound_enabled"] = bool(conf.get("outbound_enabled"))
    conf["sessionized_reply_enabled"] = bool(conf.get("sessionized_reply_enabled"))
    conf["fixed_subsession_enabled"] = bool(conf.get("fixed_subsession_enabled"))
    conf["auto_learn_subsession_members"] = bool(conf.get("auto_learn_subsession_members", True))
    conf["allow_chat_ids_enabled"] = bool(conf.get("allow_chat_ids_enabled"))
    conf["block_chat_ids_enabled"] = bool(conf.get("block_chat_ids_enabled"))
    conf["rate_limit_per_chat_per_minute"] = _clamp_int(conf.get("rate_limit_per_chat_per_minute"), 30, 1, 5000)
    min_delay = _clamp_int(conf.get("outbound_random_delay_min_seconds"), 0, 0, 3600)
    max_delay = _clamp_int(conf.get("outbound_random_delay_max_seconds"), 0, 0, 3600)
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    conf["outbound_random_delay_min_seconds"] = min_delay
    conf["outbound_random_delay_max_seconds"] = max_delay
    conf["base_url"] = str(conf.get("base_url") or DEFAULT_CONFIG["base_url"]).strip().rstrip("/")
    conf["header_name"] = str(conf.get("header_name") or DEFAULT_CONFIG["header_name"]).strip() or DEFAULT_CONFIG["header_name"]
    conf["callback_path"] = str(conf.get("callback_path") or DEFAULT_CONFIG["callback_path"]).strip() or DEFAULT_CONFIG["callback_path"]
    conf["device_type"] = str(conf.get("device_type") or DEFAULT_CONFIG["device_type"]).strip() or DEFAULT_CONFIG["device_type"]
    conf["region_id"] = str(conf.get("region_id") or DEFAULT_CONFIG["region_id"]).strip() or DEFAULT_CONFIG["region_id"]
    conf["token"] = str(conf.get("token") or "").strip()
    conf["app_id"] = str(conf.get("app_id") or "").strip()
    conf["fixed_subsession_id"] = str(conf.get("fixed_subsession_id") or "").strip()
    conf["fixed_subsession_name"] = str(conf.get("fixed_subsession_name") or "").strip()
    conf["callback_public_url"] = _normalize_callback_public_url(conf.get("callback_public_url"), conf["callback_path"])
    return conf


def _dedupe_key(app_id: str, new_msg_id: str) -> str:
    return f"{DEDUP_PREFIX}:{app_id}:{new_msg_id}"


def _string_field(value: Any) -> str:
    if isinstance(value, dict):
        if isinstance(value.get("string"), str):
            return value.get("string").strip()
    return str(value or "").strip()


def _extract_appmsg_fields(content: Any) -> dict[str, str]:
    """Compatibility wrapper for legacy callers."""
    return extract_app_message_fields(content)


def _normalize_message_type(msg_type: Any) -> str:
    """Compatibility wrapper preserving the gateway's unknown-type fallback."""
    normalized = normalize_message_type(msg_type)
    if normalized in {"text", "image", "voice", "video", "emoji", "location", "link", "file", "system"}:
        return normalized
    return "other"


def _split_group_sender(chat_id: str, content: str) -> tuple[str | None, str]:
    text = str(content or "")
    if not str(chat_id or "").endswith("@chatroom"):
        return None, text
    match = _GROUP_TEXT_PREFIX_RE.match(text)
    if match:
        sender = str(match.group("sender") or "").strip() or None
        body = str(match.group("body") or "")
        return sender, body
    if text.lstrip().startswith("<"):
        try:
            root = ET.fromstring(text)
            sender = (
                root.findtext("fromusername")
                or root.findtext("fromUserName")
                or root.findtext("senderusername")
                or root.findtext("sender")
                or ""
            ).strip()
            if sender:
                return sender, text
        except Exception:
            pass
    return None, text


def _ensure_chat(db: Session, chat_id: str, title: str | None = None, timestamp: datetime | None = None) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat:
        chat = Chat(id=chat_id, title=title or chat_id, is_chatroom=chat_id.endswith("@chatroom"))
        db.add(chat)
    elif title and not chat.title:
        chat.title = title
    if timestamp and (chat.last_message_at is None or timestamp >= chat.last_message_at):
        chat.last_message_at = timestamp
    return chat


def _ensure_contact(db: Session, contact_id: str | None, name: str | None = None) -> Contact | None:
    if not contact_id:
        return None
    contact = db.get(Contact, contact_id)
    if not contact:
        contact = Contact(id=contact_id, name=name or contact_id)
        db.add(contact)
    elif name and not contact.name:
        contact.name = name
    return contact


def _normalize_subsession_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"[^a-zA-Z0-9:_\-./]+", "_", text)
    return normalized[:128].strip("_")


def resolve_gateway_subsession(db: Session, *, conf: dict[str, Any], chat_id: str | None, sender_id: str | None) -> WechatSubsession | None:
    if not conf.get("sessionized_reply_enabled"):
        return None
    if not conf.get("fixed_subsession_enabled"):
        return None
    subsession_id = _normalize_subsession_id(conf.get("fixed_subsession_id"))
    if not subsession_id:
        return None
    name = str(conf.get("fixed_subsession_name") or "").strip() or subsession_id
    now = datetime.now()

    db.execute(
        sqlite_insert(WechatSubsession)
        .values(
            id=subsession_id,
            channel="wechat_gateway",
            name=name,
            enabled=True,
            mode="fixed",
            last_active_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[WechatSubsession.id],
            set_={
                "channel": "wechat_gateway",
                "name": name,
                "enabled": True,
                "mode": "fixed",
                "last_active_at": now,
                "updated_at": now,
            },
        )
    )
    subsession = db.get(WechatSubsession, subsession_id)
    if not subsession:
        db.flush()
        subsession = db.get(WechatSubsession, subsession_id)
    if not subsession:
        return None
    if conf.get("auto_learn_subsession_members", True):
        ensure_subsession_memberships(db, subsession_id=subsession.id, chat_id=chat_id, sender_id=sender_id)
    return subsession


def ensure_subsession_memberships(db: Session, *, subsession_id: str, chat_id: str | None, sender_id: str | None) -> None:
    now = datetime.now()
    members: list[tuple[str, str, str | None, str | None]] = []
    if chat_id:
        members.append(("chat", str(chat_id).strip(), str(chat_id).strip(), None))
    if sender_id:
        members.append(("sender", str(sender_id).strip(), None, str(sender_id).strip()))
    for member_type, member_key, member_chat_id, member_sender_id in members:
        if not member_key:
            continue
        values = {
            "subsession_id": subsession_id,
            "member_type": member_type,
            "member_key": member_key,
            "chat_id": member_chat_id,
            "sender_id": member_sender_id,
            "source": "wechat_gateway",
            "first_seen_at": now,
            "last_seen_at": now,
            "meta": {"channel": "wechat_gateway"},
        }
        update_values: dict[str, Any] = {
            "last_seen_at": now,
            "source": "wechat_gateway",
            "meta": {"channel": "wechat_gateway"},
        }
        if member_chat_id:
            update_values["chat_id"] = member_chat_id
        if member_sender_id:
            update_values["sender_id"] = member_sender_id
        db.execute(
            sqlite_insert(WechatSubsessionMembership)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    WechatSubsessionMembership.subsession_id,
                    WechatSubsessionMembership.member_type,
                    WechatSubsessionMembership.member_key,
                ],
                set_=update_values,
            )
        )


def record_subsession_turn(
    db: Session,
    *,
    subsession_id: str | None,
    message_id: int | None,
    chat_id: str | None,
    sender_id: str | None,
    direction: str,
    timestamp: datetime | None,
    content_text: str | None,
    meta: dict[str, Any] | None = None,
) -> WechatSubsessionTurn | None:
    normalized_subsession_id = _normalize_subsession_id(subsession_id)
    if not normalized_subsession_id:
        return None
    turn = WechatSubsessionTurn(
        subsession_id=normalized_subsession_id,
        message_id=message_id,
        chat_id=str(chat_id or "").strip() or None,
        sender_id=str(sender_id or "").strip() or None,
        direction=str(direction or "").strip() or "in",
        timestamp=timestamp,
        content_text_snapshot=str(content_text or "") if content_text is not None else None,
        meta=meta or {},
    )
    db.add(turn)
    subsession = db.get(WechatSubsession, normalized_subsession_id)
    if subsession:
        subsession.last_active_at = timestamp or datetime.now()
    return turn


def _message_has_prefix(text: str, prefixes: list[str]) -> bool:
    body = str(text or "").strip().lower()
    if not prefixes:
        return True
    return any(body.startswith(str(prefix or "").strip().lower()) for prefix in prefixes if str(prefix or "").strip())


def _strip_matching_prefix(text: str, prefixes: list[str]) -> str:
    body = str(text or "").strip()
    body_lower = body.lower()
    for prefix in prefixes:
        pref = str(prefix or "").strip()
        pref_lower = pref.lower()
        if pref and body_lower.startswith(pref_lower):
            return body[len(pref):].strip()
    return body


def _message_matches_regexp(text: str, patterns: list[str]) -> bool:
    body = str(text or "").strip()
    if not patterns:
        return False
    for pattern in patterns:
        compiled = str(pattern or "").strip()
        if not compiled:
            continue
        try:
            if re.match(compiled, body):
                return True
        except re.error:
            continue
    return False


def _extract_at_user_list(msg_source: Any) -> list[str]:
    source = str(msg_source or "").strip()
    if not source:
        return []
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return []
    text = (root.findtext("atuserlist") or "").strip()
    if not text:
        return []
    text = text.replace("&#44;", ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _message_has_at_mention(message_meta: Any) -> bool:
    meta = message_meta if isinstance(message_meta, dict) else {}
    raw = meta.get("raw") if isinstance(meta.get("raw"), dict) else {}
    data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
    self_wxid = str(raw.get("Wxid") or "").strip()
    mentioned = set(_extract_at_user_list(data.get("MsgSource")))
    if self_wxid and self_wxid in mentioned:
        return True
    return False


def _pick_trigger_match(text: str, rules: dict[str, Any], is_group: bool = False, message_meta: Any = None) -> tuple[bool, str | None]:
    prefixes = list(rules.get("prefixes") or [])
    regexp_patterns = list(rules.get("regexp_patterns") or [])
    # @提及触发只在群中生效；私聊不应因为没 @ 而被拦
    at_mention_enabled = bool(rules.get("at_mention_enabled")) and is_group
    random_rate = int(rules.get("random_rate") or 0)
    normalized_text = str(text or "").strip()

    if at_mention_enabled and _message_has_at_mention(message_meta):
        return True, "at_mention"
    if prefixes and _message_has_prefix(normalized_text, prefixes):
        return True, "prefix"
    if regexp_patterns and _message_matches_regexp(normalized_text, regexp_patterns):
        return True, "regexp"
    if random_rate > 0 and random.random() < (float(random_rate) / 100.0):
        return True, "random"

    # 失败原因按用户明确配置的触发器顺序报告，更直观
    if prefixes:
        return False, "prefix_miss"
    if regexp_patterns:
        return False, "regexp_miss"
    if at_mention_enabled:
        return False, "at_mention_required"
    if random_rate > 0:
        return False, "random_miss"
    return True, "always"


def _coerce_message_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value))
    except Exception:
        pass
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _message_type_51_references_auto_reply(db: Session, chat_id: str, content_text: Any) -> bool:
    """Return True when a msg_type=51 status callback is only an echo for our bot send.

    WeChat iPad callbacks often emit <op><name>lastMessage</name> rows after an
    outbound message.  If the embedded messageSvrId matches an outbound auto-reply
    we already recorded, it is just provider echo and must not suppress future
    replies.  If it points at an unknown message, treat the manual/human flag as
    a real human takeover signal.
    """
    text = str(content_text or "")
    match = re.search(r'"messageSvrId"\s*:\s*"?(\d+)"?', text)
    if not match:
        return False
    message_svr_id = match.group(1)
    recent_rows = (
        db.query(Message)
        .filter(Message.chat_id == chat_id, Message.direction == "out", Message.timestamp.is_not(None))
        .order_by(Message.timestamp.desc(), Message.id.desc())
        .limit(50)
        .all()
    )
    for row in recent_rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        if not meta.get("auto_reply"):
            continue
        if str(meta.get("external_new_msg_id") or "").strip() == message_svr_id:
            return True
        provider_value = meta.get("provider_result")
        provider = provider_value if isinstance(provider_value, dict) else {}
        data_value = provider.get("data")
        data = data_value if isinstance(data_value, dict) else {}
        if str(data.get("newMsgId") or data.get("NewMsgId") or "").strip() == message_svr_id:
            return True
    return False


def _has_human_manual_reply_since(db: Session, chat_id: str, threshold: datetime) -> bool:
    recent_rows = (
        db.query(Message)
        .filter(Message.chat_id == chat_id, Message.direction == "out", Message.timestamp.is_not(None))
        .order_by(Message.timestamp.desc(), Message.id.desc())
        .limit(50)
        .all()
    )
    for row in recent_rows:
        if row.timestamp and row.timestamp < threshold:
            continue
        meta = row.meta if isinstance(row.meta, dict) else {}
        if meta.get("auto_reply"):
            continue
        if str(meta.get("source") or "").strip() == "wechat_gateway":
            msg_type = str(meta.get("msg_type") or "").strip()
            if msg_type == "51" and _message_type_51_references_auto_reply(db, chat_id, row.content_text):
                continue
            if not (meta.get("human_manual") or meta.get("manual")):
                continue
        return True
    return False


def _recent_human_reply_exists(db: Session, chat_id: str, seconds: int, *, message_time: Any = None, wait_for_window: bool = False) -> bool:
    if seconds <= 0:
        return False
    baseline = _coerce_message_time(message_time) or datetime.utcnow()
    threshold = baseline - timedelta(seconds=seconds)
    if _has_human_manual_reply_since(db, chat_id, threshold):
        return True
    if not wait_for_window:
        return False
    deadline = baseline + timedelta(seconds=seconds)
    while True:
        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(0.2, remaining))
        if _has_human_manual_reply_since(db, chat_id, threshold):
            return True
    return _has_human_manual_reply_since(db, chat_id, threshold)


def evaluate_auto_reply_rules(
    db: Session,
    *,
    chat_id: str,
    sender_id: str | None,
    text: str,
    is_group: bool,
    message_time: Any = None,
    wait_for_human_reply_suppression: bool = False,
    message_meta: Any = None,
) -> dict[str, Any]:
    rules = load_trigger_rules(db)
    if not rules.get("enabled"):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "trigger_rules_disabled", "rules": rules}
    if not rules.get("smart_reply_enabled"):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "smart_reply_disabled", "rules": rules}
    if is_group and not rules.get("group_enabled"):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "group_disabled", "rules": rules}
    if (not is_group) and not rules.get("private_enabled"):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "private_disabled", "rules": rules}
    if rules.get("whitelist_chat_ids_enabled") and rules.get("whitelist_chat_ids") and chat_id not in set(rules.get("whitelist_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "chat_not_whitelisted", "rules": rules}
    if rules.get("blacklist_chat_ids_enabled") and chat_id in set(rules.get("blacklist_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "chat_blacklisted", "rules": rules}
    if sender_id and rules.get("whitelist_sender_ids_enabled") and rules.get("whitelist_sender_ids") and sender_id not in set(rules.get("whitelist_sender_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "sender_not_whitelisted", "rules": rules}
    if sender_id and rules.get("blacklist_sender_ids_enabled") and sender_id in set(rules.get("blacklist_sender_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "sender_blacklisted", "rules": rules}
    normalized_text = str(text or "").strip()
    matched, match_reason = _pick_trigger_match(normalized_text, rules, is_group=is_group, message_meta=message_meta)
    if not matched:
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": str(match_reason or "no_trigger_match"), "rules": rules}
    content_text = _strip_matching_prefix(normalized_text, list(rules.get("prefixes") or []))
    if len(content_text) < int(rules.get("min_text_length") or 0):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "text_too_short", "rules": rules}
    if _recent_human_reply_exists(
        db,
        chat_id,
        int(rules.get("human_reply_suppression_seconds") or 0),
        message_time=message_time,
        wait_for_window=wait_for_human_reply_suppression,
    ):
        return {"scope": _RULE_SCOPE, "allowed": False, "reason": "human_reply_suppressed", "rules": rules}
    return {"scope": _RULE_SCOPE, "allowed": True, "reason": "passed", "matched_by": str(match_reason or "always"), "rules": rules}


def evaluate_inbound_message(conf: dict[str, Any], *, chat_id: str, sender_id: str | None, text: str) -> dict[str, Any]:
    if not conf.get("enabled"):
        return {"scope": _RULE_SCOPE, "action": "allow", "reason": "gateway_disabled"}
    if conf.get("allow_chat_ids_enabled") and conf.get("allow_chat_ids") and chat_id not in set(conf.get("allow_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "action": "drop", "reason": "chat_not_whitelisted"}
    if conf.get("block_chat_ids_enabled") and chat_id in set(conf.get("block_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "action": "drop", "reason": "chat_blocked"}
    lowered = str(text or "").lower()
    for keyword in conf.get("keyword_blocklist") or []:
        if keyword and str(keyword).lower() in lowered:
            return {"scope": _RULE_SCOPE, "action": "drop", "reason": "keyword_blocked", "keyword": keyword}
    return {"scope": _RULE_SCOPE, "action": "allow", "reason": "passed"}


def evaluate_outbound_message(conf: dict[str, Any], *, target: str, text: str) -> dict[str, Any]:
    if not conf.get("enabled"):
        return {"scope": _RULE_SCOPE, "allowed": True, "action": "allow", "reason": "gateway_disabled"}
    if not conf.get("outbound_enabled"):
        return {"scope": _RULE_SCOPE, "allowed": False, "action": "block", "reason": "outbound_disabled"}
    if conf.get("allow_chat_ids_enabled") and conf.get("allow_chat_ids") and target not in set(conf.get("allow_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "action": "block", "reason": "chat_not_whitelisted"}
    if conf.get("block_chat_ids_enabled") and target in set(conf.get("block_chat_ids") or []):
        return {"scope": _RULE_SCOPE, "allowed": False, "action": "block", "reason": "chat_blocked"}
    lowered = str(text or "").lower()
    for keyword in conf.get("keyword_blocklist") or []:
        if keyword and str(keyword).lower() in lowered:
            return {"scope": _RULE_SCOPE, "allowed": False, "action": "block", "reason": "keyword_blocked", "keyword": keyword}
    return {"scope": _RULE_SCOPE, "allowed": True, "action": "allow", "reason": "passed"}


def apply_outbound_random_delay(conf: dict[str, Any]) -> float:
    min_delay = _clamp_int(conf.get("outbound_random_delay_min_seconds"), 0, 0, 3600)
    max_delay = _clamp_int(conf.get("outbound_random_delay_max_seconds"), 0, 0, 3600)
    if max_delay <= 0:
        return 0.0
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    delay = random.uniform(float(min_delay), float(max_delay))
    if delay > 0:
        time.sleep(delay)
    return delay


def _message_timestamp(create_time: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(create_time))
    except Exception:
        return None


def _resolve_display_name(db: Session, wxid: str | None, fallback: str | None = None) -> str | None:
    candidate = str(wxid or "").strip()
    fb = str(fallback or "").strip()
    if candidate:
        try:
            contact = db.get(Contact, candidate)
            if contact:
                alias = str(contact.alias or "").strip()
                name = str(contact.name or "").strip()
                if name and name != candidate:
                    return name
                if alias and alias != candidate:
                    return alias
                if name:
                    return name
                if alias:
                    return alias
        except Exception:
            pass
        try:
            chat = db.get(Chat, candidate)
            if chat:
                title = str(chat.title or "").strip()
                if title and title != candidate:
                    return title
        except Exception:
            pass
    if fb and fb != candidate:
        return fb
    if candidate:
        return candidate
    return fb or None


def _find_recent_outbound_by_external_new_msg_id(db: Session, chat_id: str, external_new_msg_id: Any) -> Message | None:
    target = str(external_new_msg_id or "").strip()
    if not target:
        return None
    recent_rows = (
        db.query(Message)
        .filter(Message.chat_id == chat_id, Message.direction == "out")
        .order_by(Message.id.desc())
        .limit(50)
        .all()
    )
    for row in recent_rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        if str(meta.get("external_new_msg_id") or "").strip() == target:
            return row
    return None


def _find_auto_reply_attempt_by_delivery(
    db: Session,
    *,
    chat_id: str,
    external_new_msg_id: Any,
) -> dict[str, Any] | None:
    target_message_id = str(external_new_msg_id or "").strip()
    target_chat_id = str(chat_id or "").strip()
    if not target_message_id or not target_chat_id:
        return None

    delivery_row = db.get(
        SyncState,
        _auto_reply_delivery_key(target_chat_id, target_message_id),
    )
    if delivery_row and delivery_row.value:
        attempt_row = db.get(SyncState, str(delivery_row.value))
        indexed_attempt = _json_load(attempt_row.value if attempt_row else None)
        if _auto_reply_attempt_matches_delivery(
            indexed_attempt,
            chat_id=target_chat_id,
            external_new_msg_id=target_message_id,
        ):
            return indexed_attempt

    # Backward-compatible fallback for attempts written before the delivery index existed.
    rows = (
        db.query(SyncState)
        .filter(SyncState.key.like(f"{AUTO_REPLY_ATTEMPT_PREFIX}:%"))
        .order_by(SyncState.updated_at.desc(), SyncState.key.desc())
        .all()
    )
    for row in rows:
        attempt = _json_load(row.value)
        if not _auto_reply_attempt_matches_delivery(
            attempt,
            chat_id=target_chat_id,
            external_new_msg_id=target_message_id,
        ):
            continue

        trigger_message_id = attempt.get("trigger_message_id")
        if trigger_message_id in {None, ""}:
            try:
                trigger_message_id = int(str(row.key).rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                continue
        try:
            attempt["trigger_message_id"] = int(trigger_message_id)
        except (TypeError, ValueError):
            continue
        return attempt
    return None


def _auto_reply_attempt_matches_delivery(
    attempt: dict[str, Any],
    *,
    chat_id: str,
    external_new_msg_id: str,
) -> bool:
    if str(attempt.get("state") or "").strip() not in {
        "sent_pending_record",
        "recorded",
        "delivery_unknown",
    }:
        return False
    delivery_value = attempt.get("delivery")
    delivery = delivery_value if isinstance(delivery_value, dict) else {}
    provider_new_message_id = str(delivery.get("provider_new_message_id") or "").strip()
    attempt_target = str(delivery.get("target") or attempt.get("target") or "").strip()
    return provider_new_message_id == external_new_msg_id and attempt_target == chat_id


def _auto_reply_marker_from_attempt(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(attempt, dict):
        return None
    try:
        trigger_message_id = int(attempt.get("trigger_message_id"))
    except (TypeError, ValueError):
        return None
    return {
        "trigger_message_id": trigger_message_id,
        "reconciled_from_attempt": True,
    }


def ingest_callback_event(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("TypeName") or "").strip()
    app_id = str(payload.get("Appid") or "").strip()
    data = payload.get("Data") if isinstance(payload.get("Data"), dict) else {}
    new_msg_id = str(data.get("NewMsgId") or "").strip()
    if event_type != "AddMsg":
        return {"ok": True, "duplicate": False, "stored": False, "reason": "ignored_event", "event_type": event_type}
    if not app_id or not new_msg_id:
        return {"ok": False, "duplicate": False, "stored": False, "reason": "missing_appid_or_newmsgid"}

    dedupe_key = _dedupe_key(app_id, new_msg_id)
    dedupe = db.get(SyncState, dedupe_key)
    if dedupe:
        try:
            existing_id = int(str(dedupe.value or "0"))
            if existing_id and db.get(Message, existing_id):
                return {"ok": True, "duplicate": True, "stored": False, "message_id": dedupe.value}
            db.delete(dedupe)
            db.flush()
        except Exception:
            return {"ok": True, "duplicate": True, "stored": False, "message_id": dedupe.value}

    conf = load_config(db)
    from_user = _string_field(data.get("FromUserName"))
    to_user = _string_field(data.get("ToUserName"))
    self_wxid = str(payload.get("Wxid") or "").strip()
    raw_text = _string_field(data.get("Content"))
    sender_id, clean_text = _split_group_sender(from_user, raw_text)
    normalized = normalize_wechat_message(
        msg_type=data.get("MsgType"),
        content=clean_text,
        media_policy="wechatapi",
    )
    timestamp = _message_timestamp(data.get("CreateTime"))

    direction = "out" if self_wxid and from_user == self_wxid else "in"
    if direction == "out":
        chat_id = to_user or from_user
        sender_id = self_wxid or sender_id or from_user
    else:
        chat_id = from_user or to_user
        sender_id = sender_id or from_user

    display_text = normalized.content_text
    if normalized.source_username.startswith("gh_"):
        sender_id = normalized.source_username or sender_id
    auto_reply_marker = None
    if direction == "out":
        auto_reply_marker = _auto_reply_marker_from_attempt(
            _find_auto_reply_attempt_by_delivery(
                db,
                chat_id=chat_id,
                external_new_msg_id=data.get("NewMsgId"),
            )
        )
        existing_outbound = _find_recent_outbound_by_external_new_msg_id(db, chat_id, data.get("NewMsgId"))
        if existing_outbound is not None:
            meta = dict(existing_outbound.meta or {})
            if auto_reply_marker is not None:
                existing_auto_reply = meta.get("auto_reply")
                reconciled_auto_reply = dict(existing_auto_reply) if isinstance(existing_auto_reply, dict) else {}
                reconciled_auto_reply.update(auto_reply_marker)
                meta["auto_reply"] = reconciled_auto_reply
                meta.pop("manual", None)
                meta.pop("human_manual", None)
            elif not meta.get("auto_reply"):
                meta["manual"] = True
                meta["human_manual"] = True
            msg_id_value = data.get("MsgId") if isinstance(data, dict) else None
            new_msg_id_value = data.get("NewMsgId") if isinstance(data, dict) else None
            msg_type_value = data.get("MsgType") if isinstance(data, dict) else None
            meta["event_type"] = event_type
            meta["external_msg_id"] = msg_id_value
            meta["external_new_msg_id"] = new_msg_id_value
            meta["msg_type"] = msg_type_value
            meta["raw"] = payload
            existing_outbound.timestamp = timestamp or existing_outbound.timestamp
            existing_outbound.meta = meta
            db.add(existing_outbound)
            db.add(SyncState(key=dedupe_key, value=str(existing_outbound.id)))
            db.commit()
            db.refresh(existing_outbound)
            subsession_raw = meta.get("subsession")
            subsession_meta = subsession_raw if isinstance(subsession_raw, dict) else {}
            return {
                "ok": True,
                "duplicate": False,
                "stored": True,
                "message_id": existing_outbound.id,
                "pipeline": None,
                "subsession_id": subsession_meta.get("id"),
            }
    pipeline = evaluate_inbound_message(conf, chat_id=chat_id, sender_id=sender_id, text=display_text)
    if pipeline.get("action") == "drop":
        dedupe = SyncState(key=dedupe_key, value="dropped")
        db.add(dedupe)
        db.commit()
        return {"ok": True, "duplicate": False, "stored": False, "dropped": True, "pipeline": pipeline}

    subsession = resolve_gateway_subsession(db, conf=conf, chat_id=chat_id, sender_id=sender_id)
    subsession_meta = None
    if subsession:
        subsession_meta = {
            "id": subsession.id,
            "name": subsession.name,
            "channel": subsession.channel,
            "mode": subsession.mode,
        }

    outbound_classification_meta: dict[str, Any] = {}
    if direction == "out":
        if auto_reply_marker is not None:
            outbound_classification_meta["auto_reply"] = auto_reply_marker
        else:
            outbound_classification_meta.update({"manual": True, "human_manual": True})

    _ensure_chat(db, chat_id, title=None, timestamp=timestamp)
    _ensure_contact(db, sender_id, name=normalized.contents.get("sourcedisplayname") or None)
    sender_display_name = _resolve_display_name(db, sender_id, fallback=sender_id)
    talker_display_name = _resolve_display_name(db, chat_id, fallback=chat_id)
    message = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_display_name,
        talker_name=talker_display_name,
        timestamp=timestamp,
        direction=direction,
        type=normalized.message_type,
        content_text=display_text,
        media_url=normalized.media_url,
        meta={
            "source": "wechat_gateway",
            "contents": normalized.contents,
            "display_title": normalized.display_title,
            "event_type": event_type,
            "external_msg_id": data.get("MsgId"),
            "external_new_msg_id": data.get("NewMsgId"),
            "msg_type": data.get("MsgType"),
            "pipeline": pipeline,
            "subsession": subsession_meta,
            **outbound_classification_meta,
            "raw": payload,
        },
    )
    db.add(message)
    db.flush()
    record_subsession_turn(
        db,
        subsession_id=subsession.id if subsession else None,
        message_id=message.id,
        chat_id=chat_id,
        sender_id=sender_id,
        direction=direction,
        timestamp=timestamp,
        content_text=display_text,
        meta={"source": "wechat_gateway", "event_type": event_type, "contents": normalized.contents},
    )
    db.add(SyncState(key=dedupe_key, value=str(message.id)))
    db.commit()
    db.refresh(message)
    return {"ok": True, "duplicate": False, "stored": True, "message_id": message.id, "pipeline": pipeline, "subsession_id": subsession.id if subsession else None}


def _parse_agent_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value))
    except Exception:
        pass
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            # Preserve the sender-side wall clock for display in the unified UI.
            return parsed.replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _agent_dedupe_key(source: str, channel: str, message_id: str) -> str:
    return f"{DEDUP_PREFIX}:agent:{source}:{channel}:{message_id}"


def ingest_agent_wechat_event(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Ingest a normalized agent-side WeChat event into the 0913 message aggregation.

    This intentionally ignores non-WeChat agent channels so Hermes/OpenClaw main chat,
    terminal UI, and other channels are not affected by the automation gateway.
    """
    data = payload if isinstance(payload, dict) else {}
    channel = str(data.get("channel") or data.get("agent_channel") or "").strip().lower()
    if channel not in {"wechat", "weixin", "wechat_gateway", "wechatapi"}:
        return {"ok": True, "stored": False, "duplicate": False, "reason": "non_wechat_channel"}

    source = str(data.get("source") or data.get("agent_source") or "agent").strip() or "agent"
    message_id = str(data.get("message_id") or data.get("msg_id") or data.get("id") or "").strip()
    chat_id = str(data.get("chat_id") or data.get("room_wxid") or data.get("from_wxid") or "").strip()
    sender_id = str(data.get("sender_id") or data.get("sender") or data.get("from_wxid") or "").strip()
    text = str(data.get("text") or data.get("content") or data.get("message") or "")
    if not message_id or not chat_id:
        return {"ok": False, "stored": False, "duplicate": False, "reason": "missing_message_id_or_chat_id"}

    dedupe_key = _agent_dedupe_key(source, channel, message_id)
    dedupe = db.get(SyncState, dedupe_key)
    if dedupe:
        return {"ok": True, "stored": False, "duplicate": True, "message_id": dedupe.value}

    timestamp = _parse_agent_timestamp(data.get("timestamp") or data.get("time") or data.get("created_at"))
    message_meta = data.get("message_meta") if isinstance(data.get("message_meta"), dict) else (data.get("meta") if isinstance(data.get("meta"), dict) else {})
    sender_name = str(
        data.get("sender_name")
        or message_meta.get("sender_name")
        or message_meta.get("sender")
        or sender_id
        or ""
    ).strip() or None
    talker_name = str(
        data.get("chat_name")
        or data.get("talker_name")
        or message_meta.get("talker_name")
        or message_meta.get("chat_name")
        or message_meta.get("room_name")
        or chat_id
        or ""
    ).strip() or None
    raw_direction = str(data.get("direction") or "in").strip().lower()
    direction = "out" if raw_direction in {"out", "send", "sent", "self"} else "in"
    msg_type = str(data.get("type") or data.get("msg_type") or "text").strip() or "text"
    normalized = normalize_wechat_message(
        msg_type=msg_type,
        content=text,
        contents=message_meta.get("contents"),
        media_url=data.get("media_url"),
        media_policy="wechatapi",
    )

    pipeline = evaluate_inbound_message(
        load_config(db),
        chat_id=chat_id,
        sender_id=sender_id or None,
        text=normalized.content_text,
    )
    if pipeline.get("action") == "drop":
        db.add(SyncState(key=dedupe_key, value="dropped"))
        db.commit()
        return {"ok": True, "stored": False, "duplicate": False, "dropped": True, "pipeline": pipeline}

    _ensure_chat(db, chat_id, title=talker_name or str(data.get("chat_name") or chat_id), timestamp=timestamp)
    _ensure_contact(db, sender_id, name=sender_name)
    message = Message(
        chat_id=chat_id,
        sender_id=sender_id or None,
        sender_name=sender_name,
        talker_name=talker_name or _resolve_display_name(db, chat_id, fallback=str(data.get("chat_name") or chat_id)),
        timestamp=timestamp,
        direction=direction,
        type=normalized.message_type,
        content_text=normalized.content_text,
        media_url=normalized.media_url,
        meta={
            "source": "wechat_gateway",
            "agent_source": source,
            "agent_channel": channel,
            "agent_message_id": message_id,
            "contents": normalized.contents,
            "display_title": normalized.display_title,
            "pipeline": pipeline,
            "raw": data,
        },
    )
    db.add(message)
    db.flush()
    db.add(SyncState(key=dedupe_key, value=str(message.id)))
    db.commit()
    db.refresh(message)
    return {"ok": True, "stored": True, "duplicate": False, "message_id": message.id, "pipeline": pipeline}


def _extract_provider_result_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data:
        return data
    results = result.get("results") if isinstance(result.get("results"), list) else []
    for item in results:
        if not isinstance(item, dict):
            continue
        resp = item.get("resp") if isinstance(item.get("resp"), dict) else {}
        nested = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        if nested:
            return nested
    return {}


def _looks_like_manual_wechat_outbound_event(*, result: dict[str, Any], data: dict[str, Any]) -> bool:
    if not result:
        return False
    if str(result.get("source") or "").strip() == "wechat_gateway_auto_reply":
        return False
    if isinstance(result.get("auto_reply"), dict):
        return False
    if result.get("manual") is True or result.get("human_manual") is True:
        return True
    if data.get("msgId") or data.get("MsgId") or data.get("newMsgId") or data.get("NewMsgId"):
        return True
    return False


def _auto_reply_attempt_key(message_id: int) -> str:
    return f"{AUTO_REPLY_ATTEMPT_PREFIX}:{int(message_id)}"


def _auto_reply_delivery_key(target: str, provider_new_message_id: Any) -> str:
    return f"{AUTO_REPLY_DELIVERY_PREFIX}:{str(target or '').strip()}:{str(provider_new_message_id or '').strip()}"


def _build_auto_reply_attempt_insert(*, key: str, value: str):
    return insert(SyncState).values(key=key, value=value)


def _is_unique_constraint_error(exc: IntegrityError) -> bool:
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if str(sqlstate or "") == "23505":
        return True
    text = str(original or exc).lower()
    return "unique constraint" in text or "duplicate key" in text or "is not unique" in text


def claim_auto_reply_attempt(db: Session, *, message_id: int, target: str) -> dict[str, Any]:
    key = _auto_reply_attempt_key(message_id)
    now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    attempt = {
        "state": "claimed",
        "trigger_message_id": int(message_id),
        "target": str(target or ""),
        "claimed_at": now,
        "updated_at": now,
    }

    # End the read transaction opened while evaluating the message so concurrent
    # workers can race on one atomic INSERT instead of both upgrading stale reads.
    db.rollback()
    last_locked_error: OperationalError | None = None
    for retry_index in range(20):
        try:
            db.execute(
                _build_auto_reply_attempt_insert(
                    key=key,
                    value=json.dumps(attempt, ensure_ascii=False),
                )
            )
            db.commit()
            return {"claimed": True, "attempt": attempt}
        except IntegrityError as exc:
            db.rollback()
            if not _is_unique_constraint_error(exc):
                raise
            row = db.get(SyncState, key)
            return {"claimed": False, "attempt": _json_load(row.value if row else None)}
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower():
                raise
            last_locked_error = exc
            try:
                row = db.get(SyncState, key)
            except OperationalError as read_exc:
                db.rollback()
                if "locked" not in str(read_exc).lower():
                    raise
                last_locked_error = read_exc
                row = None
            if row is not None:
                return {"claimed": False, "attempt": _json_load(row.value)}
            db.rollback()
            time.sleep(min(0.005 * (retry_index + 1), 0.05))
    if last_locked_error is not None:
        raise last_locked_error
    raise RuntimeError(f"failed to claim auto reply attempt: {message_id}")


def update_auto_reply_attempt(
    db: Session,
    *,
    message_id: int,
    state: str,
    delivery: dict[str, Any] | None = None,
    error: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    key = _auto_reply_attempt_key(message_id)
    row = db.get(SyncState, key)
    if row is None:
        raise RuntimeError(f"auto reply attempt not found: {message_id}")

    attempt = _json_load(row.value)
    attempt.update(
        {
            "state": str(state or "").strip() or "unknown",
            "trigger_message_id": int(message_id),
            "updated_at": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
        }
    )
    if isinstance(delivery, dict):
        attempt["delivery"] = dict(delivery)
        delivery_target = str(delivery.get("target") or attempt.get("target") or "").strip()
        provider_new_message_id = str(delivery.get("provider_new_message_id") or "").strip()
        if delivery_target and provider_new_message_id:
            delivery_key = _auto_reply_delivery_key(delivery_target, provider_new_message_id)
            delivery_row = db.get(SyncState, delivery_key)
            if delivery_row is None:
                delivery_row = SyncState(key=delivery_key, value=key)
            else:
                delivery_row.value = key
            db.add(delivery_row)
    if error:
        attempt["error"] = str(error)
    elif attempt["state"] in {"sent_pending_record", "recorded"}:
        attempt.pop("error", None)
    row.value = json.dumps(attempt, ensure_ascii=False)
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return attempt


def record_outbound_message(
    db: Session,
    *,
    target: str,
    text: str,
    provider_result: dict[str, Any] | None = None,
    commit: bool = True,
) -> Message:
    result = provider_result if isinstance(provider_result, dict) else {}
    data = _extract_provider_result_data(result)
    external_msg_id = data.get("msgId") or data.get("MsgId")
    external_new_msg_id = data.get("newMsgId") or data.get("NewMsgId")
    result_auto_reply_value = result.get("auto_reply")
    result_auto_reply = dict(result_auto_reply_value) if isinstance(result_auto_reply_value, dict) else None
    is_auto_reply = (
        str(result.get("source") or "").strip() == "wechat_gateway_auto_reply"
        or result_auto_reply is not None
    )

    existing_outbound = _find_recent_outbound_by_external_new_msg_id(db, target, external_new_msg_id)
    if existing_outbound is not None:
        meta = dict(existing_outbound.meta or {})
        meta["external_msg_id"] = external_msg_id
        meta["external_new_msg_id"] = external_new_msg_id
        meta["provider_result"] = result
        if is_auto_reply:
            existing_auto_reply_value = meta.get("auto_reply")
            existing_auto_reply = (
                dict(existing_auto_reply_value) if isinstance(existing_auto_reply_value, dict) else {}
            )
            existing_auto_reply.update(result_auto_reply or {"source": "wechat_gateway_auto_reply"})
            meta["auto_reply"] = existing_auto_reply
            meta.pop("manual", None)
            meta.pop("human_manual", None)
        elif _looks_like_manual_wechat_outbound_event(result=result, data=data) and not meta.get("auto_reply"):
            meta["manual"] = True
            meta["human_manual"] = True
        existing_outbound.type = "text"
        existing_outbound.content_text = str(text or "")
        existing_outbound.media_url = None
        existing_outbound.meta = meta
        existing_outbound.send_status = "sent"
        db.add(existing_outbound)
        if commit:
            db.commit()
            db.refresh(existing_outbound)
        return existing_outbound

    timestamp = datetime.now()
    existing_chat = db.get(Chat, target)
    existing_contact = db.get(Contact, target)
    _ensure_chat(db, target, title=None, timestamp=timestamp)
    _ensure_contact(db, target, name=None)
    if existing_chat and str(existing_chat.title or '').strip():
        talker_display_name = str(existing_chat.title).strip()
    elif existing_contact and (str(existing_contact.alias or '').strip() or str(existing_contact.name or '').strip()):
        talker_display_name = _resolve_display_name(db, target, fallback=target)
    else:
        talker_display_name = target
    subsession = resolve_gateway_subsession(db, conf=load_config(db), chat_id=target, sender_id=None)
    subsession_meta = None
    if subsession:
        subsession_meta = {
            "id": subsession.id,
            "name": subsession.name,
            "channel": subsession.channel,
            "mode": subsession.mode,
        }
    outbound_classification_meta: dict[str, Any] = {}
    if is_auto_reply:
        outbound_classification_meta["auto_reply"] = result_auto_reply or {
            "source": "wechat_gateway_auto_reply"
        }
    elif _looks_like_manual_wechat_outbound_event(result=result, data=data):
        outbound_classification_meta.update({"manual": True, "human_manual": True})
    message = Message(
        chat_id=target,
        sender_id=None,
        sender_name=None,
        talker_name=talker_display_name,
        timestamp=timestamp,
        direction="out",
        type="text",
        content_text=str(text or ""),
        media_url=None,
        meta={
            "source": "wechat_gateway",
            "external_msg_id": external_msg_id,
            "external_new_msg_id": external_new_msg_id,
            "provider_result": result,
            "subsession": subsession_meta,
            **outbound_classification_meta,
        },
        send_status="sent",
    )
    db.add(message)
    db.flush()
    record_subsession_turn(
        db,
        subsession_id=subsession.id if subsession else None,
        message_id=message.id,
        chat_id=target,
        sender_id=None,
        direction="out",
        timestamp=timestamp,
        content_text=str(text or ""),
        meta={"source": "wechat_gateway", "provider_result": result},
    )
    if commit:
        db.commit()
        db.refresh(message)
    return message
