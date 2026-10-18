from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from websockets.asyncio.client import connect

from ..db import SessionLocal
from .wechat_gateway import load_config
from .wechatapi_client import WechatApiClient


_STATE: dict[str, Any] = {
    "enabled": False, "connected": False, "base_url": "", "self_wxid": "",
    "last_error": None, "connected_at": None, "last_message_at": None,
    "last_frame_at": None, "last_frame_fields": [], "last_frame_type": None,
    "last_payload_fields": [],
    "received_total": 0, "stored_total": 0,
}


def get_status() -> dict[str, Any]:
    return dict(_STATE)


def _text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("str", value.get("string", value.get("String", "")))
    return str(value or "")


def normalize_device_events(payload: Any, self_wxid: str) -> list[dict[str, Any]]:
    """Translate device WS/callback frames into the existing deduplicated gateway pipeline."""
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return []
    if isinstance(payload, list):
        return [event for item in payload for event in normalize_device_events(item, self_wxid)]
    if not isinstance(payload, dict):
        return []
    from_user = _text(payload.get("FromUserName") or payload.get("fromUserName") or payload.get("from_user_name") or payload.get("from_user"))
    to_user = _text(payload.get("ToUserName") or payload.get("toUserName") or payload.get("to_user_name") or payload.get("to_user"))
    msg_id = payload.get("NewMsgId") or payload.get("newMsgId") or payload.get("new_msg_id") or payload.get("message_id") or payload.get("MsgId") or payload.get("msgId") or payload.get("msg_id")
    if from_user and to_user and msg_id:
        data = {
            "NewMsgId": str(msg_id),
            "MsgId": payload.get("MsgId") or payload.get("msgId") or payload.get("msg_id") or str(msg_id),
            "FromUserName": {"string": from_user}, "ToUserName": {"string": to_user},
            "Content": {"string": _text(payload.get("Content") or payload.get("content"))},
            "MsgType": payload.get("MsgType", payload.get("msgType", payload.get("msg_type", payload.get("message_type", 1)))),
            "CreateTime": payload.get("CreateTime") or payload.get("createTime") or payload.get("create_time"),
            "MsgSource": _text(payload.get("MsgSource") or payload.get("msgSource") or payload.get("msg_source")),
        }
        return [{"TypeName": "AddMsg", "Appid": self_wxid, "Wxid": self_wxid, "Data": data}]
    for key in ("data", "Data", "message", "AddMsgs", "addMsgs", "messages", "message_data"):
        if isinstance(payload.get(key), (dict, list, str)):
            events = normalize_device_events(payload[key], self_wxid)
            if events:
                return events
    return []


def _load_config() -> dict[str, Any]:
    with SessionLocal() as db:
        return load_config(db)


async def ingest_device_frame(payload: Any, self_wxid: str) -> int:
    from ..routers.wechat_gateway import _callback_ingest_executor, _ingest_callback_payload

    _STATE["last_frame_at"] = datetime.now(timezone.utc).isoformat()
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return 0
    _STATE["last_frame_fields"] = list(payload)[:12] if isinstance(payload, dict) else []
    if isinstance(payload, dict):
        _STATE["last_frame_type"] = payload.get("type")
        message = payload.get("message")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except ValueError:
                message = None
        _STATE["last_payload_fields"] = list(message)[:20] if isinstance(message, dict) else []
    events = normalize_device_events(payload, self_wxid)
    stored = 0
    for event in events:
        created = event["Data"].get("CreateTime")
        try:
            recent = 0 <= time.time() - float(created) <= 300
        except (TypeError, ValueError):
            recent = False
        result = await asyncio.get_running_loop().run_in_executor(
            _callback_ingest_executor,
            lambda event=event, recent=recent: _ingest_callback_payload(
                event, SessionLocal, allow_auto_reply=recent,
            ),
        )
        stored += int(bool(result.get("stored") and not result.get("duplicate")))
    _STATE["received_total"] += len(events)
    _STATE["stored_total"] += stored
    if events:
        _STATE["last_message_at"] = datetime.now(timezone.utc).isoformat()
    return stored


async def wechat_device_ws_loop() -> None:
    backoff = 1
    while True:
        cfg = await asyncio.to_thread(_load_config)
        enabled = bool(cfg.get("enabled") and cfg.get("ws_enabled") and cfg.get("header_name") == "key")
        _STATE.update(enabled=enabled, connected=False, base_url=cfg.get("base_url", ""))
        if not enabled:
            await asyncio.sleep(2)
            continue
        client = WechatApiClient(base_url=cfg["base_url"], token=cfg["token"], header_name="key", app_id="")
        try:
            profile = await asyncio.to_thread(client.get_device_profile)
            data = profile.get("data") or {}
            own = _text((data.get("userInfo") or {}).get("userName"))
            if not own:
                raise RuntimeError("设备未返回本人微信 ID，请检查登录状态")
            async with connect(client.device_ws_url(), proxy=None, open_timeout=10, ping_interval=20,
                               ping_timeout=20, max_size=8 * 1024 * 1024) as ws:
                _STATE.update(connected=True, self_wxid=own, last_error=None,
                              connected_at=datetime.now(timezone.utc).isoformat())
                backoff = 1
                # Recover messages buffered while disconnected; the same dedupe
                # and five-minute reply gate apply. This is not a polling loop.
                try:
                    cached = await asyncio.to_thread(client.get_device_cached_messages)
                    await ingest_device_frame(cached, own)
                except Exception as exc:
                    _STATE["last_error"] = str(exc).replace(client.token, "***")
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=2)
                        await ingest_device_frame(raw, own)
                    except asyncio.TimeoutError:
                        pass
                    current = await asyncio.to_thread(_load_config)
                    if not current.get("enabled") or not current.get("ws_enabled") or any(
                        current.get(key) != cfg.get(key) for key in ("base_url", "token", "header_name")
                    ):
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _STATE["last_error"] = str(exc).replace(client.token, "***") if client.token else str(exc)
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)
        finally:
            _STATE["connected"] = False
            client._session.close()
