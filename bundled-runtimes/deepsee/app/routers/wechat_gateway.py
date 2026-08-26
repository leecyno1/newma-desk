from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, sessionmaker

from ..db import SessionLocal
from ..models import Message
from ..services.wechat_auto_reply_transaction import (
    AutoReplyAdapters,
    execute_wechat_auto_reply_transaction,
)
from ..services.wechatapi_client import WechatApiClient
from ..services.contact_scoring import extract_prediction_events_to_db
from ..services.wechat_gateway import (
    apply_outbound_random_delay,
    evaluate_auto_reply_rules,
    evaluate_outbound_message,
    ingest_agent_wechat_event,
    ingest_callback_event,
    load_config,
    load_subsession_config,
    record_outbound_message,
    load_trigger_rules,
    save_config,
    save_subsession_config,
    save_trigger_rules,
)


router = APIRouter(prefix="/api/wechat-gateway", tags=["wechat-gateway"])
# WeChatAPI can deliver callbacks in bursts. Serializing the SQLite write path keeps
# those requests from occupying FastAPI's shared worker pool and exhausting DB connections.
_callback_ingest_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wechat-callback-ingest")
_auto_reply_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wechat-auto-reply")
_contact_scoring_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wechat-contact-scoring")
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_auto_reply_for_message(
    message_id: int,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    execute_wechat_auto_reply_transaction(
        message_id,
        session_factory=session_factory,
        adapters=AutoReplyAdapters(client_factory=WechatApiClient),
    )


def _refresh_contact_prediction_for_message(
    message_id: int,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    db = session_factory()
    try:
        message = db.get(Message, message_id)
        if (
            message is None
            or message.direction != "in"
            or str(message.type or "") != "text"
            or not message.sender_id
            or message.timestamp is None
        ):
            return
        extract_prediction_events_to_db(
            db,
            time_from=message.timestamp,
            time_to=message.timestamp,
            contact_ids={str(message.sender_id)},
            force=False,
        )
    except Exception:
        db.rollback()
        logger.exception("incremental contact prediction refresh failed for message_id=%s", message_id)
    finally:
        db.close()


def _queue_contact_prediction_refresh(
    db: Session,
    result: dict,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    if not result.get("stored") or result.get("duplicate"):
        return
    message_id = int(result.get("message_id") or 0)
    message = db.get(Message, message_id) if message_id else None
    if (
        message is None
        or message.direction != "in"
        or str(message.type or "") != "text"
        or not message.sender_id
    ):
        return
    _contact_scoring_executor.submit(_refresh_contact_prediction_for_message, message_id, session_factory)
    result["contact_scoring"] = {"status": "queued", "message_id": message_id}


def _ingest_callback_payload(payload: dict, session_factory: Callable[[], Session]) -> dict:
    db = session_factory()
    try:
        result = ingest_callback_event(db, payload)
        if result.get("stored") and not result.get("duplicate"):
            message_id = int(result.get("message_id") or 0)
            message = db.get(Message, message_id) if message_id else None
            if message and message.direction == "in" and str(message.type or "") == "text":
                _auto_reply_executor.submit(_run_auto_reply_for_message, message_id, session_factory)
                result["auto_reply"] = {"status": "queued", "message_id": message_id}
        _queue_contact_prediction_refresh(db, result, session_factory)
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/config")
def get_wechat_gateway_config(db: Session = Depends(get_db)):
    return load_config(db)


@router.post("/config")
def set_wechat_gateway_config(payload: dict, db: Session = Depends(get_db)):
    if not isinstance(payload, dict):
        return {"status": "error", "error": "invalid payload"}
    cfg = save_config(db, payload)
    return {"status": "ok", "config": cfg}


@router.get("/subsession-config/{subsession_id}")
def get_wechat_gateway_subsession_config(subsession_id: str, db: Session = Depends(get_db)):
    conf = load_subsession_config(db, subsession_id)
    if conf is None:
        raise HTTPException(status_code=404, detail="subsession not found")
    return {"status": "ok", "subsession": conf}


@router.post("/subsession-config/{subsession_id}")
def set_wechat_gateway_subsession_config(subsession_id: str, payload: dict, db: Session = Depends(get_db)):
    if not isinstance(payload, dict):
        return {"status": "error", "error": "invalid payload"}
    conf = save_subsession_config(db, subsession_id=subsession_id, payload=payload)
    return {"status": "ok", "subsession": conf}


@router.get("/trigger-rules")
def get_wechat_gateway_trigger_rules(db: Session = Depends(get_db)):
    return load_trigger_rules(db)


@router.post("/trigger-rules")
def set_wechat_gateway_trigger_rules(payload: dict, db: Session = Depends(get_db)):
    if not isinstance(payload, dict):
        return {"status": "error", "error": "invalid payload"}
    rules = save_trigger_rules(db, payload)
    return {"status": "ok", "rules": rules}


@router.post("/evaluate-reply")
def evaluate_wechat_gateway_reply(payload: dict, db: Session = Depends(get_db)):
    data = payload if isinstance(payload, dict) else {}
    result = evaluate_auto_reply_rules(
        db,
        chat_id=str(data.get("chat_id") or "").strip(),
        sender_id=str(data.get("sender_id") or "").strip() or None,
        text=str(data.get("text") or ""),
        is_group=bool(data.get("is_group")),
        message_time=data.get("message_time") or data.get("timestamp"),
        wait_for_human_reply_suppression=bool(data.get("wait_for_human_reply_suppression")),
        message_meta=data.get("message_meta") or data.get("meta"),
    )
    return {"status": "ok", "result": result}


@router.post("/bind-callback")
def bind_wechat_gateway_callback(db: Session = Depends(get_db)):
    cfg = load_config(db)
    callback_url = str(cfg.get("callback_public_url") or "").strip()
    if not callback_url:
        raise HTTPException(status_code=400, detail="callback_public_url is required")
    client = WechatApiClient(
        base_url=str(cfg.get("base_url") or ""),
        token=str(cfg.get("token") or ""),
        header_name=str(cfg.get("header_name") or "VideosApi-token"),
        app_id=str(cfg.get("app_id") or ""),
    )
    if not client.configured():
        raise HTTPException(status_code=400, detail="wechatapi gateway not configured")
    try:
        result = client.set_callback(callback_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "callback_url": callback_url, "result": result}


@router.post("/callback")
async def receive_wechat_gateway_callback(
    payload: dict,
    response: Response,
    db: Session = Depends(get_db),
):
    data = payload if isinstance(payload, dict) else {}
    # The dependency provides the correct engine (including temporary test DBs), but
    # this request-level Session never performs I/O or checks out a pool connection.
    callback_session_factory = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    result = await asyncio.get_running_loop().run_in_executor(
        _callback_ingest_executor,
        _ingest_callback_payload,
        data,
        callback_session_factory,
    )
    response.status_code = 200
    return result


@router.post("/agent-send-text")
def agent_send_wechat_text(payload: dict, db: Session = Depends(get_db)):
    data = payload if isinstance(payload, dict) else {}
    channel = str(data.get("channel") or data.get("agent_channel") or "").strip().lower()
    if channel not in {"wechat", "weixin", "wechat_gateway", "wechatapi"}:
        return {"status": "ignored", "sent": False, "reason": "non_wechat_channel"}

    target = str(data.get("target") or data.get("to_wxid") or data.get("chat_id") or "").strip()
    text = str(data.get("text") or data.get("content") or data.get("message") or "")
    source = str(data.get("source") or data.get("agent_source") or "agent").strip() or "agent"
    if not target or not text:
        raise HTTPException(status_code=400, detail="target and text are required")

    cfg = load_config(db)
    rule = evaluate_outbound_message(cfg, target=target, text=text)
    if not rule.get("allowed", True):
        return {"status": "blocked", "sent": False, "provider": "wechatapi_gateway", "rule": rule}

    client = WechatApiClient(
        base_url=str(cfg.get("base_url") or ""),
        token=str(cfg.get("token") or ""),
        header_name=str(cfg.get("header_name") or "VideosApi-token"),
        app_id=str(cfg.get("app_id") or ""),
    )
    if not client.configured():
        raise HTTPException(status_code=400, detail="wechatapi gateway not configured")
    try:
        delay_seconds = apply_outbound_random_delay(cfg)
        provider_result = client.send_text(to_wxid=target, text=text)
        message = record_outbound_message(db, target=target, text=text, provider_result=provider_result)
        meta = dict(message.meta or {})
        meta["agent_source"] = source
        meta["agent_channel"] = channel
        meta["rule"] = rule
        meta["outbound_delay_seconds"] = delay_seconds
        message.meta = meta
        db.add(message)
        db.commit()
        db.refresh(message)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "ok",
        "sent": True,
        "provider": "wechatapi_gateway",
        "message_id": message.id,
        "rule": rule,
        "result": provider_result,
    }


@router.post("/agent-event")
def receive_agent_wechat_event(payload: dict, response: Response, db: Session = Depends(get_db)):
    result = ingest_agent_wechat_event(db, payload if isinstance(payload, dict) else {})
    _queue_contact_prediction_refresh(db, result)
    response.status_code = 200
    return result


@router.websocket("/ws/agent")
async def agent_wechat_gateway_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            db = SessionLocal()
            try:
                result = ingest_agent_wechat_event(db, payload if isinstance(payload, dict) else {})
            finally:
                db.close()
            await websocket.send_json(result)
    except WebSocketDisconnect:
        return
