from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chat, Contact, SyncState
from .wechatapi_client import WechatApiClient


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


def _label_mapping(client: WechatApiClient) -> dict[str, str]:
    data = _response_data(client.list_labels())
    rows = data.get("labelList") if isinstance(data, dict) else []
    mapping: dict[str, str] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        label_id = str(row.get("labelId") or "").strip()
        label_name = str(row.get("labelName") or "").strip()
        if label_id and label_name:
            mapping[label_id] = label_name
    return mapping


def _label_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,，;\s]+", str(value or ""))
    return _unique_ids(raw)


def _detail_map(client: WechatApiClient, ids: list[str], workers: int) -> tuple[dict[str, dict[str, Any]], int]:
    batches = [ids[i : i + DETAIL_BATCH_SIZE] for i in range(0, len(ids), DETAIL_BATCH_SIZE)]
    details: dict[str, dict[str, Any]] = {}
    errors = 0

    def fetch(batch: list[str]) -> list[dict[str, Any]]:
        data = _response_data(client.get_brief_info(wxids=batch))
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
    labels = _label_mapping(api)
    details, detail_errors = _detail_map(api, all_ids, detail_workers)

    contacts = {row.id: row for row in db.execute(select(Contact)).scalars().all()}
    chats = {row.id: row for row in db.execute(select(Chat)).scalars().all()}
    inserted = updated = updated_alias = updated_labels = 0

    for wxid in friends:
        detail = details.get(wxid.lower())
        name, remark = _display_fields(detail, wxid)
        label_ids = _label_ids((detail or {}).get("labelList"))
        label_names = [labels[item] for item in label_ids if item in labels]
        label_payload = {
            "tags": label_names,
            "label_ids": label_ids,
            "source": "wechatapi_gateway",
        }
        contact = contacts.get(wxid)
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
        if name and contact.name != name:
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
        "labels": len(labels),
        "details": len(details),
        "detail_batch_errors": detail_errors,
        "inserted": inserted,
        "updated": updated,
        "updated_alias": updated_alias,
        "updated_labels": updated_labels,
    }
