"""Read-only adapters over Deepsee's persisted data; no collection or model calls."""
from __future__ import annotations

import base64
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..data_api_schemas import (ChatData, ContactData, ContentData, DataPage, EmailData,
                                LabelData, LabelsData, MessageData, PageMeta)
from ..models import Chat, Contact, EmailMessage, Message, SyncState
from .wechat_labels import LABEL_CACHE_KEY
from .wechat_message_normalizer import extract_app_message_fields, normalize_message_type

SNAPSHOT_LIMIT = 1000
PROTOCOL = re.compile(r"<(?:\?xml|msg\b|img\b|appmsg\b|voicemsg\b|videomsg\b|emoji\b)", re.I)


def utc_time(value) -> str | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            if not value:
                return None
            dt = datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, timezone.utc)
        else:
            dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(settings.DATA_API_TIMEZONE))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def local_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "timezone_required")
    return value.astimezone(ZoneInfo(settings.DATA_API_TIMEZONE)).replace(tzinfo=None)


def readable_text(value, kind="other") -> str:
    text = str(value or "")
    if not PROTOCOL.search(text):
        return text
    fields = extract_app_message_fields(text)
    return "\n".join(x for x in [fields.get("title"), fields.get("desc")] if x) or f"[{kind}]"


def clean_summary(derived) -> str | None:
    data = derived if isinstance(derived, dict) else {}
    text = data.get("display_summary") or data.get("key_info") or data.get("summary")
    return str(text) if text and not PROTOCOL.search(str(text)) else None


def display_name(identifier, remark=None, name=None, fallback=None) -> str:
    return next((str(v).strip() for v in (remark, name, fallback)
                 if v and str(v).strip() and str(v).strip() != identifier), identifier or "")


def contact_data(row: Contact) -> ContactData:
    labels = row.labels if isinstance(row.labels, dict) else {}
    return ContactData(id=row.id, display_name=display_name(row.id, row.alias, row.name),
                       nickname=row.name, remark=row.alias, rating=row.rating or 0,
                       labels=[str(v) for v in labels.get("tags", [])],
                       label_ids=[str(v) for v in labels.get("label_ids", [])])


def chat_data(row: Chat) -> ChatData:
    return ChatData(id=row.id, display_name=row.title or row.id, is_group=bool(row.is_chatroom),
                    last_message_at=utc_time(row.last_message_at))


def message_data(db: Session, rows: list[Message]) -> list[MessageData]:
    from .public_data_media import retained_url
    ids = {v for row in rows for v in (row.sender_id, row.chat_id) if v}
    contacts = {c.id: c for c in db.scalars(select(Contact).where(Contact.id.in_(ids)))} if ids else {}
    chats = {c.id: c for c in db.scalars(select(Chat).where(Chat.id.in_(ids)))} if ids else {}
    result = []
    for row in rows:
        sender, chat_contact, chat = contacts.get(row.sender_id), contacts.get(row.chat_id), chats.get(row.chat_id)
        derived = row.derived if isinstance(row.derived, dict) else {}
        kind = normalize_message_type(row.type)
        protocol_summary = PROTOCOL.search(str(derived.get("display_summary") or derived.get("key_info") or derived.get("summary") or ""))
        result.append(MessageData(
            id=row.id, chat_id=row.chat_id,
            chat_name=display_name(row.chat_id, chat_contact.alias if chat_contact else None,
                                   chat_contact.name if chat_contact else None, chat.title if chat else row.talker_name),
            sender_id=row.sender_id,
            sender_name=display_name(row.sender_id, sender.alias if sender else None,
                                     sender.name if sender else None, row.sender_name),
            occurred_at=utc_time(row.timestamp), type=kind, direction=row.direction,
            text=readable_text(row.content_text, kind), summary=clean_summary(derived),
            category=None if protocol_summary else derived.get("category"),
            sentiment=None if protocol_summary else derived.get("tone"), importance=row.importance_score or 0,
            attachment_path=f"/api/v1/messages/{row.id}/attachment" if retained_url(row.media_url) else None,
        ))
    return result


def email_data(row: EmailMessage) -> EmailData:
    return EmailData(id=row.id, account_id=row.account_id, subject=row.subject or "",
                     sender=row.from_addr, recipients=row.to_addrs or [], occurred_at=utc_time(row.sent_at),
                     direction=row.direction, text=row.body_text or row.snippet or "", summary=clean_summary(row.derived))


def database_page(db, model, resource, filters, conditions, limit, cursor=None, after_id=None):
    after = after_id
    if cursor:
        if after_id is not None:
            raise HTTPException(422, "cursor_and_after_id_conflict")
        try:
            state = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if state["resource"] != resource or state["filters"] != filters:
                raise ValueError()
            after = state["after"]
            if model in (Message, EmailMessage):
                if type(after) is not int or after < 0:
                    raise ValueError()
            elif not isinstance(after, str):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            raise HTTPException(422, "invalid_cursor") from None
    query = select(model).where(*conditions)
    if after is not None:
        query = query.where(model.id > after)
    rows = list(db.scalars(query.order_by(model.id.asc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        state = {"resource": resource, "filters": filters, "after": rows[-1].id}
        next_cursor = base64.urlsafe_b64encode(json.dumps(state, ensure_ascii=False).encode()).decode().rstrip("=")
    last_id = (rows[-1].id if rows else after) if model in (Message, EmailMessage) else None
    return rows, PageMeta(limit=limit, has_more=has_more, next_cursor=next_cursor, last_id=last_id)


def text_search(q, *columns):
    return [or_(*(column.icontains(q, autoescape=True) for column in columns))] if q else []


def labels_data(db: Session) -> LabelsData:
    row = db.get(SyncState, LABEL_CACHE_KEY)
    cache = json.loads(row.value) if row and row.value else {}
    names = cache.get("names") or {}
    counts = Counter()
    for labels in db.scalars(select(Contact.labels)):
        if isinstance(labels, dict):
            counts.update(set(str(v) for v in labels.get("label_ids", [])))
    return LabelsData(
        data=[LabelData(id=key, name=names.get(key), member_count=counts[key]) for key in sorted(set(names) | set(counts))],
        name_source="local_cache" if names else "unavailable", account_id=cache.get("account"),
        names_cached_at=utc_time(cache.get("saved_at") + "Z") if cache.get("saved_at") else None,
    )


def snapshot_rows(db: Session, source: str) -> list[dict]:
    """Read retained local records, without triggering upstream fetches."""
    count = SNAPSHOT_LIMIT + 1
    if source == "news":
        from .news_engine import _load_local_news_items
        rows, _ = _load_local_news_items(limit=count)
        return rows
    if source == "media":
        from .media_collector_store import list_all_items
        from .media_store import list_media_items
        return (list_all_items(limit=count).get("items") or []) + (list_media_items(limit=count).get("items") or [])
    if source == "mp":
        from ..routers.mp_rss import _get_mp_config, _list_local_wechat_mp_articles
        from .mp_rss_store import list_mp_articles
        config = _get_mp_config(db)
        rows = list_mp_articles(limit=count, db_path=config.get("db_path"), local_only=True).get("items") or []
        return rows + _list_local_wechat_mp_articles(db, limit=count)
    if source == "meetings":
        from ..routers.minutes import _collect_minutes_items
        return _collect_minutes_items(limit=count)
    raise HTTPException(422, "unsupported_source")


def snapshot_page(db: Session, source: str, limit: int, offset: int, q: str | None) -> DataPage[ContentData]:
    rows = snapshot_rows(db, source)
    unique: dict[str, ContentData] = {}
    for row in rows:
        identifier = str(row.get("id") or row.get("url") or "")
        if not identifier:
            continue
        # Media hot-list IDs encode rank, not identity; use its URL when available.
        if source == "media" and row.get("url"):
            identifier = str(row["url"])
        source_id = str(row.get("source_id") or row.get("platform") or row.get("channel_name") or source)
        key = f"{source}:{identifier}"
        if key in unique:
            continue
        raw_text = row.get("content_text") or row.get("content") or row.get("description") or ""
        title = str(row.get("title") or (Path(row["path"]).stem if row.get("path") else ""))
        summary = clean_summary(row.get("derived")) or row.get("summary") or row.get("description")
        unique[key] = ContentData(
            id=key, source=source, source_id=source_id, title=readable_text(title),
            author=row.get("author") or row.get("sender_name") or row.get("channel_name"),
            published_at=utc_time(row.get("pub_ts") or row.get("publish_time") or row.get("time")),
            url=str(row["url"]) if str(row.get("url") or "").startswith(("https://", "http://")) else None,
            text=readable_text(raw_text), summary=readable_text(summary) if summary else None,
        )
    items = sorted(unique.values(), key=lambda x: (x.published_at or "", x.id), reverse=True)
    truncated = len(items) > SNAPSHOT_LIMIT or len(rows) > SNAPSHOT_LIMIT
    items = items[:SNAPSHOT_LIMIT]
    if q:
        items = [x for x in items if q.casefold() in f"{x.title} {x.text} {x.summary or ''} {x.author or ''}".casefold()]
    page = items[offset:offset + limit]
    more = offset + limit < len(items)
    warnings = ["local_snapshot_only"]
    if truncated:
        warnings.append(f"snapshot_window_limited_to_{SNAPSHOT_LIMIT}")
    return DataPage(data=page, meta=PageMeta(limit=limit, has_more=more,
                    next_offset=offset + limit if more else None,
                    coverage="local_snapshot", truncated=truncated, warnings=warnings))
