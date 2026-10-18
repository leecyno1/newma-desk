"""Resumable local history import, separate from live WS and AI/reply pipelines."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
import json

from sqlalchemy import select, text

from ..db import SessionLocal
from ..models import Chat, Contact, Message, SyncState
from .chatlog_client import ChatlogClient
from .sync_service import (
    _load_wechat_id_filters, _passes_wechat_filters, _normalize_chatlog_message,
    _normalized_meta, _stored_message_identity, _to_local_naive,
)
from .wechat_message_normalizer import build_wechat_message_identity, wechat_message_identities_match

STATE_KEY = "chatlog_history_backfill_v1"


def _server_id(meta):
    return str(meta.get("external_new_msg_id") or meta.get("server_id") or "").strip()


def import_page(db, rows: list[dict], *, account_id: str) -> dict:
    """Import one page atomically; caller owns the transaction. Never trigger replies."""
    stats = {"fetched": len(rows), "inserted": 0, "existing": 0, "filtered": 0, "enriched": 0}
    if not rows:
        return stats
    times = [_to_local_naive(datetime.fromisoformat(row["time"])) for row in rows]
    talker = rows[0]["talker"]
    if any(row["talker"] != talker for row in rows):
        raise ValueError("A history page must contain a single conversation")
    filters = _load_wechat_id_filters(db)
    existing = list(db.scalars(select(Message).where(
        Message.chat_id == talker, Message.timestamp >= min(times).replace(second=0, microsecond=0),
        Message.timestamp <= max(times),
    )))
    by_server, by_local, by_coordinate = {}, {}, defaultdict(list)
    for message in existing:
        meta = message.meta if isinstance(message.meta, dict) else {}
        if _server_id(meta):
            by_server[_server_id(meta)] = message
        local_id = str(meta.get("chatlog_id") or meta.get("external_id") or "")
        if local_id:
            by_local[local_id] = message
        by_coordinate[(message.sender_id, message.timestamp)].append(message)
    contacts = {}
    used = set()
    chat = db.get(Chat, talker)
    for row, timestamp in zip(rows, times):
        sender = row.get("sender")
        if not _passes_wechat_filters(talker, sender, filters):
            stats["filtered"] += 1
            continue
        normalized = _normalize_chatlog_message(row)
        server_id = str(row.get("server_id") or "").strip()
        if server_id == "0":
            server_id = ""
        local_id = str(row.get("message_id") or row.get("id") or "")
        marker_key = f"wechat_gateway_dedup:{account_id}:{server_id}" if server_id else None
        marker = db.get(SyncState, marker_key) if marker_key else None
        match = by_server.get(server_id) if server_id else None
        # File transfers can have different timestamps on local DB and WS delivery.
        # The shared server-ID marker is authoritative, not the page's time window.
        if match is None and marker and str(marker.value or "").isdigit():
            candidate = db.get(Message, int(marker.value))
            # WeChat stores a second copy of public-account DMs in this aggregate table.
            # Keep the original conversation and media path, not the aggregate copy.
            if (candidate and talker == "brandprivatemsg@hardcode"
                    and (candidate.chat_id or "").startswith("gh_")
                    and _server_id(candidate.meta or {}) == server_id):
                stats["existing"] += 1
                continue
            if candidate and candidate.chat_id == talker:
                match = candidate
        match = match or (by_local.get(local_id) if local_id else None)
        if match is None:
            identity = build_wechat_message_identity(msg_type=normalized.message_type,
                content=normalized.content_text, contents=normalized.contents)
            for candidate in by_coordinate.get((sender, timestamp), []):
                if candidate.id in used:
                    continue
                candidate_meta = candidate.meta if isinstance(candidate.meta, dict) else {}
                candidate_server = _server_id(candidate_meta)
                if server_id and candidate_server and server_id != candidate_server:
                    continue
                stored = _stored_message_identity(candidate.type, candidate.content_text, candidate_meta)
                if wechat_message_identities_match(identity, replace(stored, external_id="")):
                    match = candidate
                    break
        historical_meta = _normalized_meta(normalized)
        historical_meta.update(chatlog_id=local_id, history_import=True)
        if server_id:
            historical_meta["external_new_msg_id"] = server_id
        if match is not None:
            old_meta = dict(match.meta or {})
            # Keep original gateway payload/classification; add the local media fallback.
            old_meta.update({k: v for k, v in historical_meta.items() if k != "contents"})
            old_meta["contents"] = {**(old_meta.get("contents") or {}), **normalized.contents}
            changed = old_meta != (match.meta or {})
            match.meta = old_meta
            if normalized.media_url and match.media_url != normalized.media_url:
                match.media_url = normalized.media_url
                changed = True
            if match.timestamp != timestamp and local_id in by_local:
                match.timestamp = timestamp
                changed = True
            used.add(match.id)
            stats["existing"] += 1
            stats["enriched"] += int(changed)
            message = match
        else:
            if chat is None:
                chat = Chat(id=talker, title=row.get("talkerName") or talker,
                            is_chatroom=bool(row.get("isChatRoom")))
                db.add(chat)
            elif row.get("talkerName") and (not chat.title or chat.title == talker):
                chat.title = row["talkerName"]
            if sender and sender not in contacts:
                contact = db.get(Contact, sender)
                if contact is None:
                    contact = Contact(id=sender, name=row.get("senderName"))
                    db.add(contact)
                contacts[sender] = contact
            message = Message(chat_id=talker, sender_id=sender, sender_name=row.get("senderName"),
                talker_name=row.get("talkerName"), timestamp=timestamp,
                direction="out" if row.get("isSelf") else "in", type=normalized.message_type,
                content_text=normalized.content_text, media_url=normalized.media_url,
                meta={**historical_meta, "source": "chatlog_history", "account_id": account_id})
            db.add(message)
            db.flush()
            stats["inserted"] += 1
            if chat.last_message_at is None or timestamp > chat.last_message_at:
                chat.last_message_at = timestamp
            by_coordinate[(sender, timestamp)].append(message)
            used.add(message.id)
        if local_id:
            by_local[local_id] = message
        if server_id:
            by_server[server_id] = message
            # Share the WS dedupe marker, so reconnect replay cannot duplicate history.
            if marker is None:
                db.add(SyncState(key=marker_key, value=str(message.id)))
    return stats


def _save_state(db, state):
    row = db.get(SyncState, STATE_KEY)
    if row is None:
        row = SyncState(key=STATE_KEY)
        db.add(row)
    state["updated_at"] = datetime.now().astimezone().isoformat()
    row.value = json.dumps(state, ensure_ascii=False)


def backfill(*, start: datetime, end: datetime, account_id: str, progress=print,
             client=None, session_factory=SessionLocal):
    client = client or ChatlogClient()
    with session_factory() as db:
        saved = db.get(SyncState, STATE_KEY)
        state = json.loads(saved.value) if saved and saved.value else None
    if state:
        if state["account_id"] != account_id or state["start"] != start.isoformat():
            raise ValueError("Existing history job belongs to a different account or start date")
        end = datetime.fromisoformat(state["end"])
    else:
        sessions = client.get_all_sessions()
        state = {"account_id": account_id, "start": start.isoformat(), "end": end.isoformat(),
                 "status": "running", "talkers": sorted({row["username"] for row in sessions
                     if row.get("username") and (row.get("timestamp") or 0) >= start.timestamp()}),
                 "completed": 0, "offset": 0, "fetched": 0, "inserted": 0, "existing": 0,
                 "filtered": 0, "enriched": 0, "errors": []}
        with session_factory() as db:
            _save_state(db, state)
            db.commit()
    if not state.get("database_catalog_checked"):
        # Session lists omit deleted/hidden conversations whose local tables still exist.
        discovered = client.get_database_talkers()
        state["talkers"].extend(sorted(set(discovered) - set(state["talkers"])))
        state["database_catalog_checked"] = True
        with session_factory() as db:
            _save_state(db, state)
            db.commit()
    total = len(state["talkers"])
    state["status"] = "running"
    for index in range(state["completed"], total):
        talker = state["talkers"][index]
        offset = state["offset"]
        checkpoint = dict(state)
        try:
            while True:
                checkpoint = dict(state)
                payload = client.get_history_page(talker, int(start.timestamp()), int(end.timestamp()), offset=offset)
                rows = payload["messages"]
                if len(rows) == 0 and offset < int(payload.get("total_count") or 0):
                    raise ValueError("Chatlog returned an empty page before the end of history")
                with session_factory() as db:
                    if db.bind.dialect.name == "sqlite":
                        db.execute(text("BEGIN IMMEDIATE"))
                    counts = import_page(db, rows, account_id=account_id)
                    for key, value in counts.items():
                        state[key] += value
                    offset += len(rows)
                    more = offset < int(payload.get("total_count", offset))
                    state["offset"] = offset if more else 0
                    state["completed"] = index if more else index + 1
                    _save_state(db, state)
                    db.commit()
                checkpoint = dict(state)
                progress(json.dumps({k: state[k] for k in ("completed", "offset", "fetched", "inserted", "existing", "filtered")}, ensure_ascii=False))
                if not more:
                    break
        except Exception as exc:
            # Keep current page checkpoint; fail visibly instead of reporting missing data as success.
            state = checkpoint
            offset = state["offset"]
            state["status"] = "interrupted"
            state["errors"].append({"index": index, "offset": offset, "type": type(exc).__name__})
            with session_factory() as db:
                _save_state(db, state)
                db.commit()
            raise
    state["status"] = "complete"
    with session_factory() as db:
        _save_state(db, state)
        db.commit()
    return {k: v for k, v in state.items() if k not in {"talkers", "account_id"}}
