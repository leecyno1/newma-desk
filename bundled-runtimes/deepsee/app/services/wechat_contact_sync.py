from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chat, Contact, Message, SyncState
from .wechatapi_client import WechatApiClient
from .wechat_labels import resolve_label_names


CONTACT_CACHE_KEY = "wechatapi_contacts_cache_v1"
DETAIL_BATCH_SIZE = 20


def _unique_ids(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().replace("＠", "@")
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _normalize_roster(data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    raw_friends = _unique_ids(data.get("friends") or [])
    raw_rooms = _unique_ids(data.get("chatrooms") or [])
    raw_ghs = _unique_ids(data.get("ghs") or [])
    friends: list[str] = []
    moved_rooms: list[str] = []
    moved_ghs: list[str] = []
    for item in raw_friends:
        lower = item.lower()
        if lower.endswith("@chatroom"):
            moved_rooms.append(item)
        elif lower.startswith("gh"):
            moved_ghs.append(item)
        else:
            friends.append(item)
    return _unique_ids(friends), _unique_ids([*raw_rooms, *moved_rooms]), _unique_ids([*raw_ghs, *moved_ghs])


def _response_data(response: Any) -> Any:
    return response.get("data") if isinstance(response, dict) else None


def _fetch_roster(client: WechatApiClient) -> tuple[list[str], list[str], list[str], str]:
    fresh_error: Exception | None = None
    try:
        data = _response_data(client.fetch_contacts_list())
        if isinstance(data, dict) and any(isinstance(data.get(k), list) for k in ("friends", "chatrooms", "ghs")):
            return (*_normalize_roster(data), "fresh")
    except Exception as exc:
        fresh_error = exc
    try:
        data = _response_data(client.fetch_contacts_list_cache())
        if isinstance(data, dict) and any(isinstance(data.get(k), list) for k in ("friends", "chatrooms", "ghs")):
            return (*_normalize_roster(data), "provider_cache")
    except Exception as cache_exc:
        if fresh_error is None:
            fresh_error = cache_exc
    if fresh_error is not None:
        raise RuntimeError(f"WeChatAPI 通讯录拉取失败：{fresh_error}") from fresh_error
    raise RuntimeError("WeChatAPI 通讯录返回为空，且供应商缓存不可用")


def _label_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,，;\s]+", str(value or ""))
    return _unique_ids(raw)


def _detail_map(
    client: WechatApiClient, ids: list[str], workers: int, room_context: dict[str, str] | None = None,
    batch_size: int = DETAIL_BATCH_SIZE,
) -> tuple[dict[str, dict[str, Any]], int]:
    batches = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]
    details: dict[str, dict[str, Any]] = {}
    errors = 0

    def fetch(batch: list[str]) -> list[dict[str, Any]]:
        kwargs = {"room_context": room_context} if getattr(client, "device_key_mode", False) else {}
        data = _response_data(client.get_brief_info(wxids=batch, **kwargs))
        return [row for row in (data or []) if isinstance(row, dict)] if isinstance(data, list) else []

    if max(1, workers) == 1:
        futures = [(batch, None) for batch in batches]
        for batch, _ in futures:
            try:
                rows = fetch(batch)
            except Exception:
                errors += 1
                continue
            for row in rows:
                wxid = str(row.get("userName") or row.get("wxid") or "").strip()
                if wxid:
                    details[wxid.lower()] = row
        return details, errors

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 6))) as executor:
        pending = {executor.submit(fetch, batch): batch for batch in batches}
        for future in as_completed(pending):
            try:
                rows = future.result()
            except Exception:
                errors += 1
                continue
            for row in rows:
                wxid = str(row.get("userName") or row.get("wxid") or "").strip()
                if wxid:
                    details[wxid.lower()] = row
    return details, errors


def _display_fields(detail: dict[str, Any] | None, fallback_id: str) -> tuple[str, str | None]:
    row = detail or {}
    nick_name = str(row.get("nickName") or row.get("nickname") or fallback_id).strip() or fallback_id
    remark = str(row.get("remark") or "").strip() or None
    return nick_name, remark


def sync_contacts_from_wechatapi(
    db: Session,
    *,
    client: WechatApiClient | None = None,
    insert_missing: bool = True,
    limit: int | None = None,
    detail_workers: int = 3,
) -> dict[str, Any]:
    api = client or WechatApiClient()
    if not api.configured():
        raise RuntimeError("WeChatAPI 未配置")

    friends, chatrooms, official_accounts, roster_mode = _fetch_roster(api)
    if limit is not None:
        friends = friends[: max(0, int(limit))]
    all_ids = _unique_ids([*friends, *chatrooms, *official_accounts])
    extra_contacts: list[str] = []
    room_context: dict[str, str] = {}
    observed_ids: list[str] = []
    if getattr(api, "device_key_mode", False):
        observed = db.execute(
            select(Message.sender_id, Message.chat_id)
            .where(Message.meta["source"].as_string() == "wechat_gateway").distinct()
        ).all()
        observed_ids = _unique_ids(value for pair in observed for value in pair)
        for sender_id, chat_id in observed:
            if sender_id and str(chat_id or "").endswith("@chatroom"):
                room_context.setdefault(sender_id, chat_id)
        extra_contacts = [item for item in observed_ids if item not in all_ids and not item.endswith("@chatroom")]
        chatrooms = _unique_ids([*chatrooms, *(item for item in observed_ids if item.endswith("@chatroom"))])
        all_ids = _unique_ids([*all_ids, *observed_ids])
    label_state = resolve_label_names(db, api)
    labels = label_state["names"]
    details, detail_errors = _detail_map(api, all_ids, detail_workers, room_context)
    # The gateway can return blank entries in large batches. Give names needed
    # by existing messages a smaller, targeted second pass.
    missing = [item for item in observed_ids if not any(
        str((details.get(item.lower()) or {}).get(field) or "").strip() for field in ("nickName", "remark")
    )]
    if missing:
        recovered, retry_errors = _detail_map(api, missing, detail_workers, room_context, batch_size=5)
        details.update(recovered)
        detail_errors += retry_errors

    contacts = {row.id: row for row in db.execute(select(Contact)).scalars().all()}
    chats = {row.id: row for row in db.execute(select(Chat)).scalars().all()}
    inserted = updated = updated_alias = updated_labels = 0

    for wxid in [*friends, *extra_contacts]:
        detail = details.get(wxid.lower())
        name, remark = _display_fields(detail, wxid)
        label_ids = _label_ids((detail or {}).get("labelList"))
        label_names = [(labels or {})[item] for item in label_ids if item in (labels or {})]
        label_payload = {
            "tags": label_names,
            "label_ids": label_ids,
            "source": "wechatapi_gateway" if wxid in friends else "wechatapi_group_member",
        }
        contact = contacts.get(wxid)
        if (not detail or "labelList" not in detail) and contact is not None:
            label_payload = {**(contact.labels or {}), "source": label_payload["source"]}
        if contact is None:
            if not insert_missing:
                continue
            contact = Contact(
                id=wxid,
                name=name,
                alias=remark,
                rating=50,
                labels=label_payload,
                stats={"manual_rating": 50, "final_rating": 50, "auto_focus": False},
            )
            db.add(contact)
            contacts[wxid] = contact
            inserted += 1
            continue
        changed = False
        if name != wxid and contact.name != name:
            contact.name = name
            changed = True
        if remark and contact.alias != remark:
            contact.alias = remark
            updated_alias += 1
            changed = True
        if contact.labels != label_payload:
            contact.labels = label_payload
            updated_labels += 1
            changed = True
        if changed:
            db.add(contact)
            updated += 1

    # Existing private chats use the same personal remark as the contact book.
    for wxid in [*friends, *extra_contacts]:
        contact = contacts.get(wxid)
        chat = chats.get(wxid)
        if contact and chat:
            display_name = contact.alias or contact.name
            if display_name and display_name != wxid:
                chat.title = display_name
                db.add(chat)

    for chat_id, chat_type in [*( (item, "group") for item in chatrooms), *( (item, "official") for item in official_accounts)]:
        detail = details.get(chat_id.lower())
        title, remark = _display_fields(detail, chat_id)
        display_title = remark or title or chat_id
        chat = chats.get(chat_id)
        is_room = chat_type == "group"
        if chat is None:
            chat = Chat(id=chat_id, title=display_title, type=chat_type, is_chatroom=is_room)
            db.add(chat)
            chats[chat_id] = chat
            continue
        if display_title != chat_id:
            chat.title = display_title
        chat.type = chat_type
        chat.is_chatroom = is_room
        db.add(chat)

    cache_payload = {
        "version": 1,
        "saved_at": datetime.utcnow().isoformat(),
        "source": "wechatapi_gateway",
        "roster_mode": roster_mode,
        "friends": friends,
        "chatrooms": chatrooms,
        "official_accounts": official_accounts,
        "detail_count": len(details),
    }
    state = db.get(SyncState, CONTACT_CACHE_KEY)
    if state is None:
        state = SyncState(key=CONTACT_CACHE_KEY, value=json.dumps(cache_payload, ensure_ascii=False))
    else:
        state.value = json.dumps(cache_payload, ensure_ascii=False)
    db.add(state)
    db.commit()
    return {
        "status": "ok",
        "source": "wechatapi_gateway",
        "roster_mode": roster_mode,
        "friends": len(friends),
        "chatrooms": len(chatrooms),
        "official_accounts": len(official_accounts),
        "labels": len(labels or {}),
        "labels_available": label_state["upstream_available"] or bool(labels),
        "labels_upstream_available": label_state["upstream_available"],
        "labels_source": label_state["source"],
        "labels_warning": label_state.get("warning"),
        "details": len(details),
        "detail_batch_errors": detail_errors,
        "inserted": inserted,
        "updated": updated,
        "updated_alias": updated_alias,
        "updated_labels": updated_labels,
    }
