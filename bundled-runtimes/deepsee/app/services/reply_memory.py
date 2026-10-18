"""Provider-independent, bounded conversation memory from the local message store."""
from __future__ import annotations

from datetime import datetime, timedelta
import math

from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from ..models import Message, SyncState, WechatSubsessionTurn


class ReplyMemoryConfig(BaseModel):
    enabled: bool = True
    max_messages: int = Field(default=50, ge=1, le=100)
    max_tokens: int = Field(default=6000, ge=256, le=16000)
    max_age_hours: int = Field(default=720, ge=1, le=4320)
    group_sender_only: bool = True


def estimate_tokens(text: str) -> int:
    cjk = sum('\u4e00' <= ch <= '\u9fff' for ch in text)
    return cjk + math.ceil((len(text) - cjk) / 3)


def reset_memory(db: Session, chat_id: str) -> int:
    last = db.scalar(select(func.max(Message.id)).where(Message.chat_id == chat_id)) or 0
    key = 'reply_memory_reset:' + chat_id
    state = db.get(SyncState, key)
    if state is None:
        state = SyncState(key=key)
    state.value = str(last)
    db.add(state)
    db.commit()
    return last


def build_reply_memory(db: Session, *, conf: dict, chat_id: str, sender_id: str = '',
                       current_text: str = '', message_id: int | None = None,
                       now: datetime | None = None,
                       subsession: dict | None = None) -> tuple[list[dict], dict]:
    cfg = ReplyMemoryConfig.model_validate(conf.get('reply_memory') or {})
    info = {'enabled': cfg.enabled, 'messages': 0, 'estimated_tokens': 0, 'scope': 'chat',
            'max_messages': cfg.max_messages, 'max_tokens': cfg.max_tokens,
            'max_age_hours': cfg.max_age_hours, 'inbound': 0, 'outbound': 0,
            'oldest_at': None, 'newest_at': None, 'reason': 'no_history_in_window'}
    if not cfg.enabled or not chat_id:
        info['reason'] = 'disabled' if not cfg.enabled else 'missing_chat_id'
        return [], info
    # The automation memory panel is the single source of window limits.
    # Legacy subsession defaults must not silently shrink this window.
    current = db.get(Message, message_id) if message_id else None
    if current is not None and current.chat_id != chat_id:
        current = None
    if current is not None and current.timestamp:
        now = current.timestamp
    now = now or datetime.now()
    reset = db.get(SyncState, 'reply_memory_reset:' + chat_id)
    after_id = int(reset.value) if reset and str(reset.value).isdigit() else 0
    info['reset_applied'] = bool(reset)
    query = select(Message).where(Message.chat_id == chat_id, Message.id > after_id,
                                 Message.timestamp >= now - timedelta(hours=cfg.max_age_hours),
                                 Message.timestamp <= now, Message.content_text.isnot(None))
    if message_id:
        # Historical imports can have newer database IDs than live messages.
        query = query.where(Message.id != message_id)
        if current is not None:
            query = query.where(or_(Message.timestamp < now,
                                    and_(Message.timestamp == now, Message.id < message_id)))
    if chat_id.endswith('@chatroom') and cfg.group_sender_only:
        info['scope'] = 'chat_and_sender'
        allowed = select(Message.id).where(Message.chat_id == chat_id,
                                           Message.sender_id == sender_id).correlate(None)
        query = query.where(or_(
            and_(or_(Message.direction != 'out', Message.direction.is_(None)), Message.sender_id == sender_id),
            and_(Message.direction == 'out', Message.meta['auto_reply']['trigger_message_id'].as_integer().in_(allowed)),
        ))
    rows = db.scalars(query.order_by(Message.timestamp.desc(), Message.id.desc()).limit(cfg.max_messages+1)).all()
    # Older installations may only have reply turns. Keep them usable without
    # restoring cross-chat pooling or bypassing the reset boundary.
    if not rows and subsession and not reset:
        query = select(WechatSubsessionTurn).where(
            WechatSubsessionTurn.subsession_id == subsession['id'],
            WechatSubsessionTurn.chat_id == chat_id,
            WechatSubsessionTurn.timestamp >= now - timedelta(hours=cfg.max_age_hours),
            WechatSubsessionTurn.timestamp <= now,
        )
        if cfg.group_sender_only and chat_id.endswith('@chatroom'):
            query = query.where(WechatSubsessionTurn.sender_id == sender_id)
        if message_id:
            query = query.where(or_(WechatSubsessionTurn.message_id.is_(None),
                                   WechatSubsessionTurn.message_id != message_id))
        rows = db.scalars(query.order_by(WechatSubsessionTurn.timestamp.desc(),
                                        WechatSubsessionTurn.id.desc()).limit(cfg.max_messages)).all()
    selected, timestamps, budget = [], [], cfg.max_tokens
    info['truncated'] = len(rows) > cfg.max_messages
    for row in rows:
        text = str((row.content_text if isinstance(row, Message)
                    else row.content_text_snapshot) or '').strip()
        if not text:
            continue
        if chat_id.endswith('@chatroom') and not cfg.group_sender_only and row.direction != 'out':
            name = getattr(row, 'sender_name', None) or row.sender_id or '未知成员'
            text = f'【群成员：{name}】{text}'
        cost = estimate_tokens(text)
        if cost > budget:
            text = text[:budget]  # conservative for CJK; never exceeds the budget
            cost = estimate_tokens(text)
            info['truncated'] = True
        selected.append({'role': 'assistant' if row.direction == 'out' else 'user', 'content': text,
                         'timestamp': row.timestamp.isoformat() if row.timestamp else None})
        timestamps.append(row.timestamp.isoformat() if row.timestamp else None)
        info['outbound' if row.direction == 'out' else 'inbound'] += 1
        budget -= cost
        if len(selected) >= cfg.max_messages or budget <= 0:
            break
    info.update(messages=len(selected), estimated_tokens=cfg.max_tokens-budget)
    if selected:
        info.update(reason='loaded', oldest_at=timestamps[-1], newest_at=timestamps[0])
    # Evidence is untrusted. Do not inject historical instructions as a system role.
    return list(reversed(selected)), info
