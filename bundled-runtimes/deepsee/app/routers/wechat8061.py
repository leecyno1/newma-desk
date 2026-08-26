from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services.llm_client import load_ai_config
from ..services.wechat8061_store import list_messages
from ..services.wechat8061_sync import get_status, set_sync_enabled


router = APIRouter(prefix="/api/wechat8061", tags=["wechat8061"])


class SyncEnableIn(BaseModel):
    enabled: bool


@router.get("/sync/status")
def sync_status():
    return get_status()


@router.post("/sync/enable")
def sync_enable(body: SyncEnableIn):
    set_sync_enabled(bool(body.enabled))
    return {"status": "ok", "enabled": bool(body.enabled)}


@router.get("/messages")
def backup_messages(
    q: str | None = Query(default=None),
    wxid: str | None = Query(default=None, description="filter by login wxid"),
    page: int = 1,
    size: int = 50,
):
    if not wxid:
        try:
            conf = load_ai_config()
            wxid = str(conf.get("wechatpad_wxid") or "").strip() or None
        except Exception:
            wxid = None
    return list_messages(wxid=wxid, q=q, page=page, size=size)

