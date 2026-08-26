from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from typing import Any

import requests

from .llm_client import load_ai_config, save_ai_config
from .wechat8061_store import insert_messages

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None


_STATE_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "enabled": False,
    "connected": False,
    "ws_url": "",
    "http_base": "",
    "wxid": "",
    "last_error": None,
    "last_message_at": None,
    "last_poll_at": None,
    "inserted_total": 0,
}

_ws = None


def _is_deprecated_ws_url(url: str) -> bool:
    value = (url or "").strip().lower()
    return (
        not value
        or "{wxid}" in value
        or "60.205.58.39:8088" in value
        or "getsyncmsg" in value
    )


def get_status() -> dict[str, Any]:
    with _STATE_LOCK:
        return dict(_STATE)


def set_sync_enabled(enabled: bool) -> None:
    conf = load_ai_config()
    conf["wechatpad_sync_enabled"] = bool(enabled)
    save_ai_config(conf)


def _set_state(**kwargs: Any) -> None:
    with _STATE_LOCK:
        _STATE.update(kwargs)


def _build_ws_url(raw: str, wxid: str) -> str:
    url = (raw or "").strip()
    if _is_deprecated_ws_url(url):
        return ""
    if not url.lower().startswith(("ws://", "wss://")):
        return ""
    if "{wxid}" in url:
        if not wxid:
            return ""
        return url.replace("{wxid}", wxid)
    if wxid:
        stripped = url.rstrip("/")
        if stripped.endswith("/ws"):
            return stripped + "/" + wxid
        if url.endswith("/ws/"):
            return url + wxid
    return url


def _nested_str(msg: dict[str, Any], key: str, default: str = "") -> str:
    v = msg.get(key)
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("string", "String", "value"):
            vv = v.get(k)
            if isinstance(vv, str):
                return vv
    return default


def _int_val(msg: dict[str, Any], key: str, default: int | None = None) -> int | None:
    v = msg.get(key)
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    try:
        if v is not None:
            return int(v)
    except Exception:
        return default
    return default


def _normalize_addmsg(wxid: str, msg: dict[str, Any]) -> dict[str, Any] | None:
    msg_id = _int_val(msg, "MsgId")
    if msg_id is None:
        return None
    create_time = _int_val(msg, "CreateTime")
    ts = None
    if create_time:
        try:
            ts = datetime.fromtimestamp(create_time).isoformat(sep=" ", timespec="seconds")
        except Exception:
            ts = None
    msg_type = _int_val(msg, "MsgType")
    sender_id = _nested_str(msg, "FromUserName", "")
    sender_nickname = _nested_str(msg, "DisplayName", sender_id)
    content = _nested_str(msg, "Content", "")
    return {
        "wxid": wxid,
        "msg_id": str(msg_id),
        "msg_type": msg_type,
        "timestamp": ts,
        "sender_id": sender_id,
        "sender_nickname": sender_nickname,
        "content": content,
        "raw_json": json.dumps(msg, ensure_ascii=False),
        "source": "poll",
    }


def _poll_sync(http_base: str, wxid: str) -> int:
    base = (http_base or "").rstrip("/")
    if not base or not wxid:
        return 0
    url = f"{base}/api/Msg/Sync"
    payload = {"wxid": wxid, "Synckey": "", "Scene": 0}
    session = requests.Session()
    session.trust_env = False
    r = session.post(url, json=payload, timeout=15)
    r.raise_for_status()
    body = r.json()
    data = body.get("Data") if isinstance(body, dict) else None
    add_msgs = (data or {}).get("AddMsgs") if isinstance(data, dict) else None
    if not isinstance(add_msgs, list) or not add_msgs:
        return 0
    records: list[dict[str, Any]] = []
    for msg in add_msgs:
        if not isinstance(msg, dict):
            continue
        rec = _normalize_addmsg(wxid, msg)
        if rec:
            records.append(rec)
    if not records:
        return 0
    inserted = insert_messages(records)
    return int(inserted or 0)


def _parse_ws_payload(wxid: str, payload: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in (payload or "").splitlines():
        s = line.strip()
        if not s or not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        msg_id = obj.get("msgId") or obj.get("msg_id") or obj.get("MsgId")
        if msg_id is None:
            continue
        msg_type = obj.get("category") or obj.get("msgType") or obj.get("MsgType")
        try:
            msg_type_i = int(msg_type) if msg_type is not None else None
        except Exception:
            msg_type_i = None
        sender = obj.get("sender") if isinstance(obj.get("sender"), dict) else {}
        sender_id = (sender or {}).get("id") or obj.get("senderId") or ""
        sender_nickname = (sender or {}).get("nickname") or obj.get("senderName") or sender_id
        records.append(
            {
                "wxid": wxid,
                "msg_id": str(msg_id),
                "msg_type": msg_type_i,
                "timestamp": obj.get("timestamp"),
                "sender_id": str(sender_id) if sender_id is not None else "",
                "sender_nickname": str(sender_nickname) if sender_nickname is not None else "",
                "content": obj.get("content"),
                "raw_json": s,
                "source": "ws",
            }
        )
    return records


async def wechat8061_sync_loop() -> None:
    """Background loop: poll + (optional) websocket listener for wechat8061.

    Controlled by ai_config.json keys:
      - wechatpad_sync_enabled: bool
      - wechatpad_http_base / wechatpad_wxid / wechatpad_ws_url
      - wechatpad_sync_poll_seconds (optional, default 30)
      - wechatpad_sync_ws_heartbeat_seconds (optional, default 30)
    """
    global _ws
    backoff = 1.0
    last_poll = 0.0
    while True:
        try:
            conf = load_ai_config()
            enabled = bool(conf.get("wechatpad_sync_enabled", False))
            http_base = str(conf.get("wechatpad_http_base") or "").strip()
            wxid = str(conf.get("wechatpad_wxid") or "").strip()
            ws_raw = str(conf.get("wechatpad_ws_url") or "").strip()
            ws_url = _build_ws_url(ws_raw, wxid)
            poll_seconds = int(conf.get("wechatpad_sync_poll_seconds") or 30)
            poll_seconds = max(5, min(3600, poll_seconds))
            hb_seconds = int(conf.get("wechatpad_sync_ws_heartbeat_seconds") or 30)
            hb_seconds = max(10, min(600, hb_seconds))

            _set_state(enabled=enabled, http_base=http_base, wxid=wxid, ws_url=ws_url)

            if not enabled:
                if _ws is not None:
                    try:
                        await _ws.close()
                    except Exception:
                        pass
                    _ws = None
                _set_state(connected=False)
                await asyncio.sleep(2)
                continue

            if not wxid:
                _set_state(connected=False, last_error="wechatpad_wxid not configured")
                await asyncio.sleep(5)
                continue

            # Polling path (works even if WS not configured)
            now = time.monotonic()
            if http_base and (now - last_poll) >= poll_seconds:
                try:
                    inserted = await asyncio.to_thread(_poll_sync, http_base, wxid)
                    last_poll = now
                    _set_state(last_poll_at=datetime.utcnow().isoformat(timespec="seconds"))
                    if inserted:
                        with _STATE_LOCK:
                            _STATE["inserted_total"] = int(_STATE.get("inserted_total") or 0) + int(inserted)
                            _STATE["last_message_at"] = datetime.utcnow().isoformat(timespec="seconds")
                except Exception as e:
                    _set_state(last_error=f"poll: {e}")

            # WebSocket listener (best-effort)
            if not ws_url or websockets is None:
                if websockets is None:
                    _set_state(last_error="websockets package not available")
                await asyncio.sleep(1)
                continue

            if _ws is None or getattr(_ws, "closed", False):
                try:
                    _ws = await websockets.connect(ws_url, open_timeout=8, ping_interval=None, max_size=2**20)
                    _set_state(connected=True, last_error=None)
                    backoff = 1.0
                except Exception as e:
                    _set_state(connected=False, last_error=f"ws connect: {e}")
                    _ws = None
                    await asyncio.sleep(min(30.0, backoff))
                    backoff = min(30.0, backoff * 2)
                    continue

            try:
                msg = await asyncio.wait_for(_ws.recv(), timeout=hb_seconds)
            except asyncio.TimeoutError:
                try:
                    await _ws.send("ping")
                except Exception as e:
                    _set_state(connected=False, last_error=f"ws ping: {e}")
                    try:
                        await _ws.close()
                    except Exception:
                        pass
                    _ws = None
                await asyncio.sleep(0)
                continue

            if isinstance(msg, (bytes, bytearray)):
                try:
                    msg = msg.decode("utf-8", errors="ignore")
                except Exception:
                    msg = ""
            if not isinstance(msg, str):
                continue
            if not msg.strip():
                continue

            records = _parse_ws_payload(wxid, msg)
            if records:
                inserted = await asyncio.to_thread(insert_messages, records)
                if inserted:
                    with _STATE_LOCK:
                        _STATE["inserted_total"] = int(_STATE.get("inserted_total") or 0) + int(inserted)
                        _STATE["last_message_at"] = datetime.utcnow().isoformat(timespec="seconds")
            _set_state(last_error=None)
        except Exception as e:
            _set_state(connected=False, last_error=str(e))
            try:
                if _ws is not None:
                    await _ws.close()
            except Exception:
                pass
            _ws = None
            await asyncio.sleep(2)
