from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Chat, Message, SyncState
from ..schemas import ChatOut


router = APIRouter(prefix="/api/chats", tags=["chats"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _wechatapi_chat_ids(db: Session) -> set[str]:
    out: set[str] = set()
    state = db.get(SyncState, "wechatapi_contacts_cache_v1")
    if state and state.value:
        try:
            payload = json.loads(state.value)
            out.update(str(item).strip() for item in (payload.get("chatrooms") or []) if str(item).strip())
        except Exception:
            pass
    callback_ids = db.execute(
        select(Message.chat_id)
        .where(Message.meta["source"].as_string() == "wechat_gateway")
        .where(Message.chat_id.like("%@chatroom"))
        .distinct()
    ).scalars().all()
    out.update(str(item).strip() for item in callback_ids if str(item or "").strip())
    return out


@router.get("", response_model=list[ChatOut])
def list_chats(wechatapi_only: bool = False, db: Session = Depends(get_db)):
    items = db.execute(select(Chat).order_by(Chat.last_message_at.desc().nullslast())).scalars().all()
    if wechatapi_only:
        allowed = _wechatapi_chat_ids(db)
        items = [item for item in items if str(item.id or "") in allowed]
    return [ChatOut.model_validate(i) for i in items]
