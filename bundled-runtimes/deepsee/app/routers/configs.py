from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import SyncState
import json
from ..config import settings
import requests
from ..services.mp_rss_store import DEFAULT_MP_UPSTREAM_URL
from ..services.market_data import (
    load_market_data_config,
    market_provider_health,
    sanitize_market_data_config_for_ui,
    save_market_data_config,
)


router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config():
    return {
        "chatlog_http_base": settings.CHATLOG_HTTP_BASE,
        "chatlog_dir": settings.CHATLOG_DIR,
        "n8n": {
            "reply": settings.N8N_REPLY_WEBHOOK,
            "summary": settings.N8N_SUMMARY_WEBHOOK,
            "contact": settings.N8N_CONTACT_WEBHOOK,
            "send": settings.N8N_SEND_WEBHOOK,
            "auth": bool(settings.N8N_AUTH_TOKEN),
        },
    }


@router.get("/config/test")
def test_connectivity():
    checks = {}
    # chatlog
    try:
        r = requests.get(f"{settings.CHATLOG_HTTP_BASE}/api/v1/session", timeout=3)
        checks["chatlog"] = r.status_code
    except Exception as e:
        checks["chatlog"] = f"error: {e}"
    # n8n endpoints presence
    checks["n8n_reply_configured"] = bool(settings.N8N_REPLY_WEBHOOK)
    checks["n8n_summary_configured"] = bool(settings.N8N_SUMMARY_WEBHOOK)
    checks["n8n_contact_configured"] = bool(settings.N8N_CONTACT_WEBHOOK)
    checks["n8n_send_configured"] = bool(settings.N8N_SEND_WEBHOOK)
    return checks


# --------- Black/White List Management (persisted in SyncState) ---------

def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_json_list(db: Session, key: str) -> list[str]:
    row = db.get(SyncState, key)
    if not row or not row.value:
        return []
    try:
        data = json.loads(row.value)
        if isinstance(data, list):
            return [str(x) for x in data]
        return []
    except Exception:
        return []


def _set_json_list(db: Session, key: str, values: list[str]) -> None:
    row = db.get(SyncState, key)
    payload = json.dumps(list(dict.fromkeys([str(v) for v in values])))
    if not row:
        row = SyncState(key=key, value=payload)
    else:
        row.value = payload
    db.add(row)


@router.get("/filters")
def get_filters(db: Session = Depends(_get_db)):
    return {
        "blacklist_senders": _get_json_list(db, "blacklist_senders"),
        "blacklist_talkers": _get_json_list(db, "blacklist_talkers"),
        "whitelist_senders": _get_json_list(db, "whitelist_senders"),
        "whitelist_talkers": _get_json_list(db, "whitelist_talkers"),
    }


@router.post("/filters/blacklist")
def set_blacklist(payload: dict, db: Session = Depends(_get_db)):
    senders = payload.get("senders") or []
    talkers = payload.get("talkers") or []
    if not isinstance(senders, list) or not isinstance(talkers, list):
        raise HTTPException(400, "invalid payload")
    _set_json_list(db, "blacklist_senders", [str(x) for x in senders])
    _set_json_list(db, "blacklist_talkers", [str(x) for x in talkers])
    db.commit()
    return {"status": "ok"}


# --------- Module Configurations (persisted in SyncState) ---------

def _get_json_obj(db: Session, key: str) -> dict:
    row = db.get(SyncState, key)
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_json_obj(db: Session, key: str, obj: dict) -> None:
    payload = json.dumps(obj or {})
    row = db.get(SyncState, key)
    if not row:
        row = SyncState(key=key, value=payload)
    else:
        row.value = payload
    db.add(row)


@router.get("/config/newsnow")
def get_newsnow_config(db: Session = Depends(_get_db)):
    return _get_json_obj(db, "newsnow_config")


@router.post("/config/newsnow")
def set_newsnow_config(payload: dict, db: Session = Depends(_get_db)):
    # expected: { base_url: str, auth_token?: str }
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    _set_json_obj(db, "newsnow_config", payload)
    db.commit()
    return {"status": "ok"}


# --------- AI runtime (tool overlay) switches ---------

_AI_RUNTIME_KEY = "ai_runtime"


@router.get("/config/ai-runtime")
def get_ai_runtime(db: Session = Depends(_get_db)):
    obj = _get_json_obj(db, _AI_RUNTIME_KEY)
    # defaults
    return {
        "enable_msg_tool_overlay": bool(obj.get("enable_msg_tool_overlay", True)) if isinstance(obj, dict) else True,
        "enable_email_tool_overlay": bool(obj.get("enable_email_tool_overlay", True)) if isinstance(obj, dict) else True,
        "email_overlay_window": int(obj.get("email_overlay_window", 120)) if isinstance(obj, dict) else 120,
        "email_overlay_cap": int(obj.get("email_overlay_cap", 160)) if isinstance(obj, dict) else 160,
        "messages_overlay_batch": int(obj.get("messages_overlay_batch", 200)) if isinstance(obj, dict) else 200,
        "default_concurrency": int(obj.get("default_concurrency", 3)) if isinstance(obj, dict) else 3,
    }


@router.post("/config/ai-runtime")
def set_ai_runtime(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    # sanitize/clamp
    def _b(v, d):
        return bool(v) if isinstance(v, (bool, int)) else d
    def _i(v, d, lo, hi):
        try:
            n = int(v)
            return max(lo, min(hi, n))
        except Exception:
            return d
    obj = _get_json_obj(db, _AI_RUNTIME_KEY)
    obj = obj if isinstance(obj, dict) else {}
    obj["enable_msg_tool_overlay"] = _b(payload.get("enable_msg_tool_overlay"), True)
    obj["enable_email_tool_overlay"] = _b(payload.get("enable_email_tool_overlay"), True)
    obj["email_overlay_window"] = _i(payload.get("email_overlay_window"), 120, 20, 1000)
    obj["email_overlay_cap"] = _i(payload.get("email_overlay_cap"), 160, 20, 2000)
    obj["messages_overlay_batch"] = _i(payload.get("messages_overlay_batch"), 200, 20, 2000)
    obj["default_concurrency"] = _i(payload.get("default_concurrency"), 3, 1, 16)
    _set_json_obj(db, _AI_RUNTIME_KEY, obj)
    db.commit()
    return {"status": "ok"}


@router.get("/config/folo")
def get_folo_config(db: Session = Depends(_get_db)):
    return _get_json_obj(db, "folo_config")


@router.post("/config/folo")
def set_folo_config(payload: dict, db: Session = Depends(_get_db)):
    # expected: { base_url: str, api_key?: str }
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    _set_json_obj(db, "folo_config", payload)
    db.commit()
    return {"status": "ok"}


@router.get("/config/media")
def get_media_config(db: Session = Depends(_get_db)):
    return _get_json_obj(db, "media_config")


@router.post("/config/media")
def set_media_config(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    _set_json_obj(db, "media_config", payload)
    db.commit()
    return {"status": "ok"}


@router.get("/config/mp")
def get_mp_config(db: Session = Depends(_get_db)):
    cfg = _get_json_obj(db, "mp_config")
    cfg = cfg if isinstance(cfg, dict) else {}
    if not str(cfg.get("upstream_base_url") or "").strip():
        cfg = {**cfg, "upstream_base_url": DEFAULT_MP_UPSTREAM_URL}
    return cfg


@router.post("/config/mp")
def set_mp_config(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    _set_json_obj(db, "mp_config", payload)
    db.commit()
    return {"status": "ok"}


@router.get("/config/minutes")
def get_minutes_config(db: Session = Depends(_get_db)):
    return _get_json_obj(db, "minutes_config")


@router.post("/config/minutes")
def set_minutes_config(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    _set_json_obj(db, "minutes_config", payload)
    db.commit()
    return {"status": "ok"}


@router.get("/config/extensions")
def get_extensions_config(db: Session = Depends(_get_db)):
    cfg = _get_json_obj(db, "extensions_config")
    return cfg if isinstance(cfg, dict) else {}


@router.post("/config/extensions")
def set_extensions_config(payload: dict, db: Session = Depends(_get_db)):
    # expected (merged into existing): { langbot_log_dir?: str, ... }
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    existing = _get_json_obj(db, "extensions_config")
    existing = existing if isinstance(existing, dict) else {}
    for k, v in payload.items():
        if v is None:
            existing.pop(k, None)
        else:
            existing[k] = v
    _set_json_obj(db, "extensions_config", existing)
    db.commit()
    return {"status": "ok"}


# --------- Market data configuration (persisted in SyncState) ---------

@router.get("/config/market-data")
def get_market_data_config(db: Session = Depends(_get_db)):
    cfg = load_market_data_config(db)
    return {
        **sanitize_market_data_config_for_ui(cfg),
        "health": market_provider_health(cfg),
    }


@router.post("/config/market-data")
def set_market_data_config(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    cfg = save_market_data_config(db, payload)
    return {
        "status": "ok",
        "config": sanitize_market_data_config_for_ui(cfg),
        "health": market_provider_health(cfg),
    }


@router.get("/config/market-data/test")
def test_market_data_config(db: Session = Depends(_get_db)):
    cfg = load_market_data_config(db)
    return market_provider_health(cfg)


# --------- Email sync schedule (persisted in SyncState) ---------

def _normalize_email_sync_times(values) -> list[str]:
    if not isinstance(values, list):
        values = []
    cleaned: list[str] = []
    for item in values:
        text = str(item or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            continue
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except Exception:
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            cleaned.append(f"{hour:02d}:{minute:02d}")
    return list(dict.fromkeys(cleaned)) or ["06:00", "21:00"]


@router.get("/config/email-sync-schedule")
def get_email_sync_schedule(db: Session = Depends(_get_db)):
    obj = _get_json_obj(db, "email_sync_schedule")
    return {"times": _normalize_email_sync_times(obj.get("times") if isinstance(obj, dict) else [])}


@router.post("/config/email-sync-schedule")
def set_email_sync_schedule(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    times = _normalize_email_sync_times(payload.get("times"))
    _set_json_obj(db, "email_sync_schedule", {"times": times})
    db.commit()
    return {"status": "ok", "times": times}


# --------- Email default account (persisted in SyncState) ---------

@router.get("/config/email-default")
def get_email_default(db: Session = Depends(_get_db)):
    obj = _get_json_obj(db, "email_default_account_id")
    # support both {"account_id": 1} and legacy {"id": 1}
    acc_id = None
    if isinstance(obj, dict):
        acc_id = obj.get("account_id") or obj.get("id")
    return {"account_id": acc_id}


@router.post("/config/email-default")
def set_email_default(payload: dict, db: Session = Depends(_get_db)):
    if not isinstance(payload, dict) or not payload.get("account_id"):
        raise HTTPException(400, "invalid payload: require account_id")
    _set_json_obj(db, "email_default_account_id", {"account_id": int(payload.get("account_id"))})
    db.commit()
    return {"status": "ok"}


@router.post("/filters/whitelist")
def set_whitelist(payload: dict, db: Session = Depends(_get_db)):
    senders = payload.get("senders") or []
    talkers = payload.get("talkers") or []
    if not isinstance(senders, list) or not isinstance(talkers, list):
        raise HTTPException(400, "invalid payload")
    _set_json_list(db, "whitelist_senders", [str(x) for x in senders])
    _set_json_list(db, "whitelist_talkers", [str(x) for x in talkers])
    db.commit()
    return {"status": "ok"}
