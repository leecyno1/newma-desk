from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import SessionLocal
from ..models import SyncState
import json
import requests


router = APIRouter(prefix="/api/folo", tags=["folo"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_conf(db: Session) -> dict:
    row = db.get(SyncState, "folo_config")
    conf = json.loads(row.value) if row and row.value else {}
    return conf if isinstance(conf, dict) else {}


@router.get("/posts")
def list_posts(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conf = _get_conf(db)
    base = conf.get("base_url")
    if not base:
        raise HTTPException(400, "folo base_url not configured")
    api = base.rstrip("/") + "/api/posts"
    headers = {}
    if conf.get("api_key"):
        headers["Authorization"] = f"Bearer {conf['api_key']}"
    try:
        r = requests.get(api, params={"limit": limit, "offset": offset}, headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(502, f"proxy error: {e}")
    # Expect a list of posts; if shape differs, front-end will adapt via mapping.
    return {"items": data}

