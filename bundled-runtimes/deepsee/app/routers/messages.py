from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import Session
from typing import Optional
import threading
from ..db import session_scope, SessionLocal
from ..models import Message, Interaction, InteractionExt, Contact
from ..schemas import PaginatedMessages, MessageOut, UpDownVoteResult, TagUpdateIn, MessageDeriveRequest
from ..config import settings
from ..services.ai_tools import ensure_message_features, populate_fallback_derived
from ..services.wechat_message_normalizer import (
    extract_app_message_fields,
    extract_image_fields,
    extract_wechat_xml_payload,
    is_file_app_message,
    normalize_message_type,
    normalize_wechat_message,
)
from ..services.wechatapi_client import WechatApiClient
from ..services.llm_client import load_ai_config
from ..services.message_filters import filter_effective_messages, WECHAT_NOISE_SENDER_IDS, WECHAT_NOISE_CHAT_IDS
from starlette.responses import FileResponse, Response, RedirectResponse
from typing import Dict, Any, List
import csv, hashlib, io, html, json, mimetypes, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import requests


router = APIRouter(prefix="/api/messages", tags=["messages"])
_SMALL_FILE_CACHE_LIMIT = 1024 * 1024

# simple in-memory progress for derive tasks
PROGRESS: Dict[str, Dict[str, Any]] = {}
_PROGRESS_LOCK = threading.RLock()
_DERIVE_JOBS: Dict[str, threading.Thread] = {}

_DROP_META_KEYS = {
    # common heavy fields we never need in list responses
    "raw",
    "xml",
    "xmlstr",
    "xml_str",
    "payload",
    "buffer",
    "bytes",
    "base64",
    "data_base64",
    "thumb_base64",
    "content",
    "content_text",
    "full_text",
}


def _contact_display_name(contact_id: Any, alias: Any = None, name: Any = None, fallback: Any = None) -> str:
    contact_key = str(contact_id or "").strip()
    for value in (alias, name, fallback, contact_key):
        text_value = str(value or "").strip()
        if text_value:
            return text_value
    return ""


def _load_contact_display_names(db: Session, sender_ids: list[Any]) -> dict[str, str]:
    contact_ids = sorted({str(value or "").strip() for value in sender_ids if str(value or "").strip()})
    if not contact_ids:
        return {}
    try:
        rows = db.execute(
            select(Contact.id, Contact.alias, Contact.name).where(Contact.id.in_(contact_ids))
        ).all()
    except Exception:
        return {}
    display_names: dict[str, str] = {}
    for contact_id, alias, name in rows:
        contact_key = str(contact_id or "").strip()
        if not contact_key:
            continue
        display_name = _contact_display_name(contact_key, alias=alias, name=name)
        if display_name:
            display_names[contact_key] = display_name
    return display_names


def _compose_message_display_summary(d: dict | None) -> str:
    if not isinstance(d, dict):
        return ""
    try:
        raw_num = str(d.get("meeting_number") or "").strip()
        num = re.sub(r"\D", "", raw_num)
        if len(num) < 9 or len(num) > 13:
            num = ""
        plat = str(d.get("platform") or d.get("meeting_platform") or "").strip()
        raw_sum = str(d.get("summary") or "").strip()
        key = re.sub(r"^\s*(ai:|fallback:)\s*", "", raw_sum, flags=re.IGNORECASE).strip() if raw_sum else ""
        if not key:
            key = str(d.get("key_info") or d.get("main_point") or d.get("summary_full") or "").strip()
            key = re.sub(r"^\s*(ai:|fallback:)\s*", "", key, flags=re.IGNORECASE).strip()
        if plat:
            key = re.sub(rf"^\s*{re.escape(plat)}\s*[:：|]?\s*", "", key).strip()
        if num:
            key = re.sub(rf"^\s*(会议号[:：]?\s*)?{re.escape(num)}\s*[:：|]?\s*", "", key).strip()
            key = re.sub(rf"\s*(会议号[:：]?\s*)?{re.escape(num)}\s*$", "", key).strip()
        if plat:
            key = re.sub(rf"^\s*{re.escape(plat)}\s*[:：|]?\s*", "", key).strip()
        left = " ".join([x for x in (num, plat) if x])
        if key:
            return f"{left} | {key}" if left else key
        return left
    except Exception:
        return ""


def _normalize_media_host(host: str | None) -> str:
    v = (host or "").strip()
    if not v:
        v = (settings.CHATLOG_HTTP_BASE or "").strip() or "http://127.0.0.1:5030"
    if not v.startswith(("http://", "https://")):
        v = "http://" + v
    return v.rstrip("/")


def _encode_rel_path(path: str | None) -> str:
    p = str(path or "").strip().replace("\\", "/").lstrip("/")
    if not p:
        return ""
    return "/".join(quote(seg, safe="") for seg in p.split("/") if seg)


def _build_image_candidates(*, host: str | None, md5: str | None, path: str | None, direct_url: str | None) -> List[str]:
    base = _normalize_media_host(host)
    key = (md5 or "").strip()
    rel = _encode_rel_path(path)
    out: List[str] = []
    if direct_url:
        out.append(direct_url.strip())
    # chatlog 的 /image 端点会按 md5+路径解密并自动回退到可用缩略图；
    # 直接 /data 原图在本地缺失时常见 404，所以放在解密端点之后。
    if key and rel:
        out.append(f"{base}/image/{quote(key, safe='')},{rel}")
    if key:
        out.append(f"{base}/image/{quote(key, safe='')}")
    if rel:
        out.append(f"{base}/data/{rel}_M.dat")
        out.append(f"{base}/data/{rel}.dat")
        out.append(f"{base}/data/{rel}_t.dat")
        out.append(f"{base}/data/{rel}")
    # dedupe preserving order
    seen = set()
    uniq: List[str] = []
    for u in out:
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def _looks_like_http_url(value: Any) -> str:
    text_value = str(value or "").strip()
    if text_value.startswith(("http://", "https://")):
        return text_value
    return ""


def _build_file_candidates(
    *,
    host: str | None,
    md5: str | None,
    path: str | None,
    direct_url: str | None,
    contents: dict[str, Any] | None = None,
) -> List[str]:
    base = _normalize_media_host(host)
    c = contents or {}
    out: List[str] = []
    for value in (
        direct_url,
        c.get("fileUrl"),
        c.get("file_url"),
        c.get("url"),
        c.get("cdn_dataurl"),
        c.get("cdndataurl"),
        c.get("dataurl"),
    ):
        url_value = _looks_like_http_url(value)
        if url_value:
            out.append(url_value)
    key = (md5 or c.get("md5") or c.get("fullmd5") or c.get("id") or c.get("mediaId") or "").strip()
    rel = _encode_rel_path(path or c.get("path") or c.get("data") or c.get("relative") or c.get("localPath") or "")
    if key:
        out.append(f"{base}/file/{quote(key, safe='')}")
    if rel:
        out.append(f"{base}/data/{rel}")
    seen = set()
    uniq: List[str] = []
    for u in out:
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def _find_url_deep(value: Any) -> str:
    if isinstance(value, str):
        return _looks_like_http_url(value)
    if isinstance(value, dict):
        preferred = (
            "fileUrl",
            "file_url",
            "downloadUrl",
            "download_url",
            "url",
            "cdnUrl",
            "cdn_url",
        )
        for key in preferred:
            found = _find_url_deep(value.get(key))
            if found:
                return found
        for item in value.values():
            found = _find_url_deep(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_url_deep(item)
            if found:
                return found
    return ""


def _is_file_appmsg(appmsg: dict[str, Any] | None) -> bool:
    """Compatibility wrapper for legacy callers."""
    return is_file_app_message(appmsg)


def _parse_file_size(*values: Any) -> int | None:
    for value in values:
        text_value = str(value or "").strip()
        if not text_value:
            continue
        try:
            parsed = int(float(text_value))
            if parsed >= 0:
                return parsed
        except Exception:
            continue
    return None


def _safe_download_name(value: Any, fallback: str = "wechat-file") -> str:
    text_value = str(value or "").strip() or fallback
    text_value = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", text_value)
    text_value = text_value.strip(" ._")
    return (text_value or fallback)[:180]


def _wechat_file_cache_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "media_cache" / "wechat_files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wechat_image_cache_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "media_cache" / "wechat_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cached_file_path(url: str, filename: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return _wechat_file_cache_dir() / f"{digest}__{_safe_download_name(filename)}"


def _guess_image_suffix(media_type: str | None, url: str = "") -> str:
    media = str(media_type or "").split(";", 1)[0].strip().lower()
    if media == "image/png":
        return ".png"
    if media in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if media == "image/gif":
        return ".gif"
    if media == "image/webp":
        return ".webp"
    guessed = mimetypes.guess_extension(media or "")
    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed
    suffix = Path(str(url or "").split("?", 1)[0]).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    return ".jpg"


def _cached_image_path(cache_key: str, suffix: str = ".jpg") -> Path:
    digest = hashlib.sha256(str(cache_key or "").encode("utf-8")).hexdigest()[:32]
    return _wechat_image_cache_dir() / f"{digest}{suffix or '.jpg'}"


def _serve_or_cache_image_url(url: str, cache_key: str):
    if not url:
        return None
    existing = list(_wechat_image_cache_dir().glob(f"{hashlib.sha256(str(cache_key or url).encode('utf-8')).hexdigest()[:32]}.*"))
    for path in existing:
        if path.exists() and path.stat().st_size > 0:
            media_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
            return FileResponse(str(path), media_type=media_type, filename=path.name, content_disposition_type="inline")
    tmp_path = _cached_image_path(cache_key or url, ".part")
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=15) as resp:
            if resp.status_code >= 400:
                return None
            content_type = resp.headers.get("content-type") or ""
            suffix = _guess_image_suffix(content_type, url)
            cache_path = _cached_image_path(cache_key or url, suffix)
            total = 0
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > 12 * 1024 * 1024:
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return RedirectResponse(url=url, status_code=302)
                    fh.write(chunk)
        if tmp_path.stat().st_size <= 0:
            tmp_path.unlink(missing_ok=True)
            return None
        tmp_path.replace(cache_path)
        media_type = mimetypes.guess_type(str(cache_path))[0] or (content_type.split(";", 1)[0] if content_type else "image/jpeg")
        return FileResponse(str(cache_path), media_type=media_type, filename=cache_path.name, content_disposition_type="inline")
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _serve_or_cache_small_file(url: str, filename: str, expected_size: int | None = None):
    if not url:
        return None
    filename = _safe_download_name(filename)
    cache_path = _cached_file_path(url, filename)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return FileResponse(str(cache_path), media_type=media_type, filename=filename, content_disposition_type="inline")
    if expected_size is not None and expected_size > _SMALL_FILE_CACHE_LIMIT:
        return RedirectResponse(url=url, status_code=302)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".part")
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=12) as resp:
            if resp.status_code >= 400:
                return None
            content_length = _parse_file_size(resp.headers.get("content-length"))
            if content_length is not None and content_length > _SMALL_FILE_CACHE_LIMIT:
                return RedirectResponse(url=url, status_code=302)
            total = 0
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _SMALL_FILE_CACHE_LIMIT:
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return RedirectResponse(url=url, status_code=302)
                    fh.write(chunk)
        tmp_path.replace(cache_path)
        return FileResponse(str(cache_path), media_type=media_type, filename=filename, content_disposition_type="inline")
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _coerce_json_field(v: Any) -> Any:
    """Coerce possibly-stringified JSON fields (meta/derived/tags) to python objects."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return v
    return v


def _extract_wechat_xml_payload(content: Any) -> str:
    """Compatibility wrapper for legacy callers."""
    return extract_wechat_xml_payload(content)


def _extract_wechat_appmsg(content: Any) -> dict[str, str]:
    """Compatibility wrapper for legacy callers."""
    return extract_app_message_fields(content)


def _extract_wechat_img(content: Any) -> dict[str, str]:
    """Compatibility wrapper for legacy callers."""
    return extract_image_fields(content)


def _is_wechat_mp_message(sender_id: Any, chat_id: Any, meta: Any = None) -> bool:
    ids = [str(sender_id or "").strip(), str(chat_id or "").strip()]
    meta_obj = _coerce_json_field(meta) if meta is not None else None
    if isinstance(meta_obj, dict):
        contents = meta_obj.get("contents") if isinstance(meta_obj.get("contents"), dict) else {}
        ids.extend([
            str(contents.get("sourceusername") or "").strip(),
            str(contents.get("userName") or "").strip(),
            str(contents.get("username") or "").strip(),
        ])
    return any(value.startswith("gh_") for value in ids if value)


def _normalize_message_type_value(msg_type: Any) -> Any:
    if msg_type is None:
        return None
    text_value = str(msg_type).strip()
    if not text_value:
        return None
    return normalize_message_type(msg_type)


def _normalize_wechat_gateway_message_fields(
    sender_id: Any,
    sender_name: Any,
    chat_id: Any,
    talker_name: Any,
    msg_type: Any,
    content_text: Any,
    media_url: Any,
    meta: Any,
    db: Session | None = None,
) -> dict[str, Any]:
    meta_obj = _coerce_json_field(meta) if meta is not None else None
    meta_obj = meta_obj if isinstance(meta_obj, dict) else {}
    out_sender_name = sender_name or meta_obj.get('sender_name') or meta_obj.get('sender')
    out_talker_name = talker_name or meta_obj.get('talker_name') or meta_obj.get('chat_name') or meta_obj.get('room_name')
    out_meta = dict(meta_obj) if isinstance(meta_obj, dict) else {}
    contents = out_meta.get('contents') if isinstance(out_meta.get('contents'), dict) else {}

    raw = out_meta.get('raw') if isinstance(out_meta.get('raw'), dict) else {}
    data = raw.get('Data') if isinstance(raw.get('Data'), dict) else {}
    content_payload = content_text
    content_xml = _extract_wechat_xml_payload(content_text)
    raw_xml = _extract_wechat_xml_payload(data.get('Content'))
    content_lower = content_xml.lower()
    raw_lower = raw_xml.lower()
    if not any(marker in content_lower for marker in ('<msg', '<appmsg', '<img')) and any(
        marker in raw_lower for marker in ('<msg', '<appmsg', '<img')
    ):
        content_payload = raw_xml

    normalized = normalize_wechat_message(
        msg_type=msg_type,
        content=content_payload,
        contents=contents,
        media_url=media_url,
        media_policy=(
            "wechatapi"
            if str(out_meta.get('source') or '').strip() == 'wechat_gateway'
            else "chatlog"
        ),
    )
    has_xml_fields = bool(extract_app_message_fields(content_payload) or extract_image_fields(content_payload))
    out_type = (
        None
        if (msg_type is None or not str(msg_type).strip()) and not has_xml_fields
        else normalized.message_type
    )
    out_media_url = normalized.media_url
    if normalized.contents:
        out_meta['contents'] = normalized.contents
    if normalized.display_title and not str(out_meta.get('display_title') or '').strip():
        out_meta['display_title'] = normalized.display_title

    if str(out_meta.get('source') or '').strip() == 'wechat_gateway':
        sender_id_text = str(sender_id or '').strip()
        sender_name_text = str(out_sender_name or '').strip()
        talker_id_text = str(chat_id or '').strip()
        talker_name_text = str(out_talker_name or '').strip()
        lookup_db = db
        if sender_id_text and lookup_db is not None:
            try:
                row = lookup_db.execute(text('select alias, name from contacts where id = :id'), {'id': sender_id_text}).fetchone()
                if row:
                    out_sender_name = _contact_display_name(
                        sender_id_text,
                        alias=row[0],
                        name=row[1],
                        fallback=out_sender_name,
                    )
            except Exception:
                pass
        if talker_id_text and talker_name_text == talker_id_text and lookup_db is not None:
            try:
                row = lookup_db.execute(text('select title from chats where id = :id'), {'id': talker_id_text}).fetchone()
                if row:
                    title = str(row[0] or '').strip()
                    out_talker_name = title or out_talker_name
            except Exception:
                pass

    return {
        'sender_name': out_sender_name,
        'talker_name': out_talker_name,
        'type': out_type,
        'media_url': out_media_url,
        'meta': out_meta,
    }


def _truncate_text(s: Any, max_chars: int) -> str | None:
    if s is None:
        return None
    txt = str(s)
    if max_chars <= 0:
        return txt
    if len(txt) <= max_chars:
        return txt
    return txt[: max_chars - 1] + "…"


def _prune_meta(obj: Any, *, depth: int, max_depth: int, max_items: int, max_str: int) -> Any:
    """Best-effort prune of meta payload to avoid huge JSON responses crashing the UI."""
    if obj is None:
        return None
    if depth >= max_depth:
        if isinstance(obj, str):
            return obj[:max_str]
        if isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, (int, float, bool)):
            return obj
        return None
    if isinstance(obj, str):
        return obj if len(obj) <= max_str else obj[: max_str - 1] + "…"
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [
            _prune_meta(x, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_str=max_str)
            for x in obj[:max_items]
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in list(obj.items())[:max_items]:
            kk = str(k)
            if kk.strip().lower() in _DROP_META_KEYS:
                continue
            out[kk] = _prune_meta(v, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_str=max_str)
        return out
    return None


def _sanitize_meta_for_list(meta: Any, *, max_depth: int = 4, max_items: int = 80, max_str: int = 600) -> dict | None:
    m = _coerce_json_field(meta)
    if not isinstance(m, dict):
        return None
    return _prune_meta(m, depth=0, max_depth=max_depth, max_items=max_items, max_str=max_str)


def _derive_readback_item(msg_id: Any, derived: Any) -> dict | None:
    try:
        rid = int(msg_id)
    except Exception:
        return None
    derv = _coerce_json_field(derived)
    if not isinstance(derv, dict):
        derv = {}
    summary = derv.get("summary")
    has_ai = isinstance(summary, str) and summary.lower().strip().startswith("ai:")
    return {
        "id": rid,
        "summary_origin": derv.get("summary_origin"),
        "has_ai": bool(has_ai),
    }


def _merge_memory_readback(readback: list[dict], messages: list[Message]) -> list[dict]:
    by_id = {int(item["id"]): dict(item) for item in readback if isinstance(item, dict) and item.get("id") is not None}
    for msg in messages:
        item = _derive_readback_item(getattr(msg, "id", None), getattr(msg, "derived", None))
        if not item:
            continue
        current = by_id.get(item["id"])
        if not current or (not current.get("summary_origin") and item.get("summary_origin")):
            by_id[item["id"]] = item
    return list(by_id.values())


def _set_progress(key: str, **updates: Any) -> None:
    with _PROGRESS_LOCK:
        current = dict(PROGRESS.get(key) or {})
        current.update(updates)
        PROGRESS[key] = current


def _prepare_derive_request(body: MessageDeriveRequest) -> tuple[MessageDeriveRequest, bool]:
    try:
        conf = load_ai_config()
        dd = conf.get("derive_defaults") or {}
    except Exception:
        dd = {}
    payload = body.model_dump()
    if payload.get("batch_size") is None:
        payload["batch_size"] = int(dd.get("batch_size", 100))
    if payload.get("concurrency") is None:
        payload["concurrency"] = int(dd.get("concurrency", 3))
    if payload.get("temperature") is None:
        payload["temperature"] = float(dd.get("temperature", 0.1))
    if payload.get("force") is None:
        payload["force"] = bool(dd.get("force", False))
    prepared = MessageDeriveRequest(**payload)
    effective_force = bool(prepared.force)
    return prepared, effective_force


def _resolve_message_ids(db: Session, body: MessageDeriveRequest) -> list[int]:
    query = select(Message.id)
    if body.message_ids:
        query = query.where(Message.id.in_(body.message_ids))
    else:
        period = (body.period or "").lower()
        period_mapping = {
            "1day": 1,
            "3days": 3,
            "1week": 7,
            "1month": 30,
        }
        days = period_mapping.get(period)
        if days:
            since = datetime.utcnow() - timedelta(days=days)
            query = query.where(Message.timestamp >= since)
        if body.limit:
            query = query.order_by(Message.timestamp.desc()).limit(max(1, body.limit))
        elif not days:
            query = query.order_by(Message.timestamp.desc()).limit(500)
        else:
            query = query.order_by(Message.timestamp.desc())
    rows = db.execute(query).all()
    out: list[int] = []
    for row in rows:
        try:
            out.append(int(row[0]))
        except Exception:
            continue
    return out


def _derive_messages_internal(
    db: Session,
    messages: List[Message],
    body: MessageDeriveRequest,
    *,
    effective_force: bool,
    progress_key: str | None = None,
) -> dict[str, Any]:
    def _fatal_tool_error_list(items: list[str]) -> bool:
        if not items:
            return False
        fatal_tokens = (
            "missing_api_key",
            "bad_api_key_cached",
            "invalid api key",
            "api key is disabled",
            "unauthorized",
            "401 client error",
            "403 client error",
        )
        matched = 0
        for it in items:
            low = str(it or "").lower()
            if any(tok in low for tok in fatal_tokens):
                matched += 1
        return matched == len(items)

    if not messages:
        if progress_key:
            _set_progress(progress_key, status="done", total=0, done=0, updated=0, errors=[], debug=[])
            return {"status": "ok", "updated": 0, "progress_key": progress_key}
        return {"status": "ok", "updated": 0}

    if progress_key:
        bs = max(1, min(100, int(body.batch_size or 100)))
        idx = 0
        errs: list[str] = []
        debs: list[dict] = []
        total_updated = 0
        tool_disabled_for_run = False
        id_list = [int(getattr(m, "id")) for m in messages if getattr(m, "id", None) is not None]
        _set_progress(progress_key, status="running", total=len(messages), done=0, updated=0, errors=[], debug=[])
        while idx < len(messages):
            chunk = messages[idx : idx + bs]
            try:
                db.rollback()
            except Exception:
                pass
            try:
                populate_fallback_derived(db, chunk, force=effective_force)
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                errs.append(f"fallback_chunk_failed[{idx}:{idx+len(chunk)}]: {str(exc)[:180]}")
            if tool_disabled_for_run:
                res = {"updated": 0, "errors": [], "debug": [], "applied": []}
            else:
                try:
                    res = ensure_message_features(
                        db,
                        chunk,
                        force=effective_force,
                        batch_size=bs,
                        concurrency=body.concurrency,
                        temperature=body.temperature,
                    )
                except Exception as exc:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    errs.append(f"tool_chunk_failed[{idx}:{idx+len(chunk)}]: {str(exc)[:180]}")
                    res = {"updated": 0, "errors": [], "debug": [], "applied": []}
            try:
                total_updated += int(res.get("updated", 0))
                e = res.get("errors") or []
                if isinstance(e, list):
                    errs.extend([str(x) for x in e])
                    if _fatal_tool_error_list([str(x) for x in e]):
                        tool_disabled_for_run = True
                d = res.get("debug") or []
                if isinstance(d, list):
                    debs.extend(d)
                a = res.get("applied") or []
                if isinstance(a, list):
                    debs.extend([{**x, "applied": True} for x in a])
            except Exception:
                pass
            idx += bs
            _set_progress(
                progress_key,
                status="running",
                done=min(len(messages), idx),
                total=len(messages),
                updated=total_updated,
                errors=errs[:50],
                debug=debs[:50],
            )
        readback: list[dict] = []
        try:
            if id_list:
                rows = db.execute(select(Message.id, Message.derived).where(Message.id.in_(id_list))).all()
                for rid, derv in rows:
                    item = _derive_readback_item(rid, derv)
                    if item:
                        readback.append(item)
        except Exception:
            pass
        readback = _merge_memory_readback(readback, messages)
        _set_progress(
            progress_key,
            status="done",
            done=len(messages),
            total=len(messages),
            updated=total_updated,
            errors=errs[:50],
            debug=debs[:50],
            debug_readback=readback[:50],
        )
        return {
            "status": "ok",
            "updated": total_updated,
            "errors": errs[:50],
            "debug": debs[:50],
            "debug_readback": readback[:50],
            "progress_key": progress_key,
        }

    id_list = [int(getattr(m, "id")) for m in messages if getattr(m, "id", None) is not None]
    try:
        db.rollback()
    except Exception:
        pass
    try:
        populate_fallback_derived(db, messages, force=effective_force)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        fallback_err = f"fallback_failed: {str(exc)[:180]}"
    else:
        fallback_err = ""
    try:
        res = ensure_message_features(
            db,
            messages,
            force=effective_force,
            batch_size=body.batch_size,
            concurrency=body.concurrency,
            temperature=body.temperature,
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        res = {"updated": 0, "errors": [f"tool_failed: {str(exc)[:180]}"], "debug": [], "applied": []}
    if fallback_err:
        try:
            res_errors = res.get("errors") if isinstance(res, dict) else None
            if not isinstance(res_errors, list):
                res_errors = []
            res_errors.insert(0, fallback_err)
            res["errors"] = res_errors
        except Exception:
            pass
    try:
        updated = int(res.get("updated", len(messages)))
    except Exception:
        updated = len(messages)
    readback: list[dict] = []
    try:
        if id_list:
            rows = db.execute(select(Message.id, Message.derived).where(Message.id.in_(id_list))).all()
            for rid, derv in rows:
                item = _derive_readback_item(rid, derv)
                if item:
                    readback.append(item)
    except Exception:
        pass
    readback = _merge_memory_readback(readback, messages)
    deb = (res.get("debug") or [])
    appd = (res.get("applied") or [])
    debug_combined = []
    if isinstance(deb, list):
        debug_combined.extend(deb)
    if isinstance(appd, list):
        debug_combined.extend([{**x, "applied": True} for x in appd])
    return {"status": "ok", "updated": updated, "errors": (res.get("errors") or [])[:50], "debug": debug_combined[:50], "debug_readback": readback[:50]}


def _run_derive_job(progress_key: str, body_payload: dict[str, Any], message_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        body = MessageDeriveRequest(**body_payload)
        effective_force = bool(body.force)
        if not message_ids:
            _set_progress(progress_key, status="done", total=0, done=0, updated=0, errors=[], debug=[])
            return
        messages = db.execute(select(Message).where(Message.id.in_(message_ids)).order_by(Message.timestamp.desc())).scalars().all()
        _derive_messages_internal(db, messages, body, effective_force=effective_force, progress_key=progress_key)
    except Exception as exc:
        _set_progress(progress_key, status="error", error=str(exc), errors=[str(exc)[:400]])
    finally:
        try:
            db.close()
        except Exception:
            pass
        with _PROGRESS_LOCK:
            _DERIVE_JOBS.pop(progress_key, None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        # ensure proper close even if generator exits early
        db.close()


@router.get("/media/image")
def resolve_image_media(
    message_id: int | None = Query(default=None),
    md5: str | None = Query(default=None),
    path: str | None = Query(default=None),
    host: str | None = Query(default=None),
    url: str | None = Query(default=None, description="optional direct media url"),
    db: Session = Depends(get_db),
):
    message = db.get(Message, message_id) if message_id else None
    meta_obj = _coerce_json_field(message.meta) if message and message.meta is not None else None
    meta_obj = meta_obj if isinstance(meta_obj, dict) else {}
    contents = meta_obj.get("contents") if isinstance(meta_obj.get("contents"), dict) else {}

    raw_xml = _extract_wechat_xml_payload(message.content_text) if message else ""
    if message and not raw_xml:
        raw = meta_obj.get("raw") if isinstance(meta_obj.get("raw"), dict) else {}
        data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
        raw_xml = _extract_wechat_xml_payload(data.get("Content"))

    img_fields = _extract_wechat_img(raw_xml)
    if img_fields:
        merged_contents = dict(contents)
        for key, val in img_fields.items():
            if val and not merged_contents.get(key):
                merged_contents[key] = val
        contents = merged_contents

    aeskey = str(contents.get("aeskey") or contents.get("cdnthumbaeskey") or "").strip()
    message_media_url = message.media_url if message else ""
    file_id = str(
        path
        or contents.get("cdnmidimgurl")
        or contents.get("cdnbigimgurl")
        or contents.get("cdnthumburl")
        or message_media_url
        or ""
    ).strip()
    image_md5 = str(md5 or contents.get("md5") or "").strip()
    direct_url = _looks_like_http_url(url) or _looks_like_http_url(message.media_url if message else "") or ""
    candidates = _build_image_candidates(host=host, md5=image_md5, path=file_id, direct_url=direct_url)
    configured_base = (settings.CHATLOG_HTTP_BASE or "").strip()
    if configured_base and configured_base.rstrip("/") != _normalize_media_host(host).rstrip("/"):
        candidates.extend(_build_image_candidates(host=configured_base, md5=image_md5, path=file_id, direct_url=None))

    cache_key = "|".join([str(message_id or ""), image_md5, file_id, direct_url])
    for candidate in candidates:
        served = _serve_or_cache_image_url(candidate, cache_key or candidate)
        if served is not None:
            return served

    if raw_xml and "<img" in raw_xml.lower():
        try:
            client = WechatApiClient()
            if client.configured():
                for img_type in (2, 1, 3):
                    try:
                        result = client.download_image_by_xml(xml=raw_xml, img_type=img_type)
                        file_url = _find_url_deep(result)
                        if file_url:
                            served = _serve_or_cache_image_url(file_url, f"{cache_key}|xml|{img_type}")
                            return served or RedirectResponse(url=file_url, status_code=302)
                    except Exception:
                        continue
                if aeskey and file_id:
                    for img_type in ("mid", "hd", "thumb"):
                        try:
                            result = client.download_image(aeskey=aeskey, file_id=file_id, img_type=img_type)
                            file_url = _find_url_deep(result)
                            if file_url:
                                served = _serve_or_cache_image_url(file_url, f"{cache_key}|cdn|{img_type}")
                                return served or RedirectResponse(url=file_url, status_code=302)
                        except Exception:
                            continue
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"image download failed: {exc}") from exc

    if not candidates:
        raise HTTPException(status_code=400, detail="missing md5/path/url")

    return RedirectResponse(url=candidates[0], status_code=302)


@router.get("/media/file")
def resolve_file_media(
    message_id: int | None = Query(default=None),
    md5: str | None = Query(default=None),
    path: str | None = Query(default=None),
    host: str | None = Query(default=None),
    url: str | None = Query(default=None, description="optional direct media url"),
    name: str | None = Query(default=None, description="optional display filename"),
    db: Session = Depends(get_db),
):
    message = db.get(Message, message_id) if message_id else None
    meta_obj = _coerce_json_field(message.meta) if message and message.meta is not None else None
    meta_obj = meta_obj if isinstance(meta_obj, dict) else {}
    contents = meta_obj.get("contents") if isinstance(meta_obj.get("contents"), dict) else {}

    if message:
        appmsg = _extract_wechat_appmsg(message.content_text)
        if not appmsg:
            raw_meta = _coerce_json_field(message.meta) if message.meta is not None else None
            if isinstance(raw_meta, dict):
                raw = raw_meta.get("raw") if isinstance(raw_meta.get("raw"), dict) else {}
                data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
                appmsg = _extract_wechat_appmsg(data.get("Content"))
        if appmsg:
            merged_contents = dict(contents)
            for key, val in appmsg.items():
                if val and not merged_contents.get(key):
                    merged_contents[key] = val
            contents = merged_contents

    filename = _safe_download_name(
        name
        or contents.get("title")
        or contents.get("datatitle")
        or contents.get("desc")
        or contents.get("datadesc")
        or f"wechat-file-{message_id or md5 or 'unknown'}"
    )
    expected_size = _parse_file_size(
        contents.get("totallen"),
        contents.get("datasize"),
        contents.get("fullsize"),
    )
    candidates = _build_file_candidates(host=host, md5=md5, path=path, direct_url=url, contents=contents)
    for candidate in candidates:
        served = _serve_or_cache_small_file(candidate, filename, expected_size=expected_size)
        if served is not None:
            return served

    raw_xml = _extract_wechat_xml_payload(message.content_text) if message else ""
    if message and (not raw_xml or "<appmsg" not in raw_xml.lower()):
        raw_meta = _coerce_json_field(message.meta) if message.meta is not None else None
        if isinstance(raw_meta, dict):
            raw = raw_meta.get("raw") if isinstance(raw_meta.get("raw"), dict) else {}
            data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
            raw_xml = _extract_wechat_xml_payload(data.get("Content"))
    if raw_xml and "<appmsg" in raw_xml.lower():
        last_error: Exception | None = None
        try:
            client = WechatApiClient()
            if client.configured():
                try:
                    result = client.download_file_by_xml(xml=raw_xml)
                    file_url = _find_url_deep(result)
                    if file_url:
                        served = _serve_or_cache_small_file(file_url, filename, expected_size=expected_size)
                        return served or RedirectResponse(url=file_url, status_code=302)
                except Exception as exc:
                    last_error = exc
                aeskey = str(contents.get("aeskey") or contents.get("cdndatakey") or contents.get("cdn_datakey") or "").strip()
                file_id = str(contents.get("cdnattachurl") or contents.get("cdndataurl") or contents.get("cdn_dataurl") or "").strip()
                total_size = str(expected_size if expected_size is not None else "").strip()
                suffix = str(contents.get("fileext") or contents.get("datafmt") or "").strip().lstrip(".")
                if aeskey and file_id:
                    result = client.download_cdn_file(
                        aeskey=aeskey,
                        file_id=file_id,
                        total_size=total_size or "0",
                        suffix=suffix,
                    )
                    file_url = _find_url_deep(result)
                    if file_url:
                        served = _serve_or_cache_small_file(file_url, filename, expected_size=expected_size)
                        return served or RedirectResponse(url=file_url, status_code=302)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"WeChat API 文件下载失败：{exc}",
            )
        if last_error:
            raise HTTPException(
                status_code=502,
                detail=f"WeChat API 文件下载失败：{last_error}",
            )

    raise HTTPException(
        status_code=404,
        detail=f"未找到可浏览文件链接：{name or md5 or message_id or 'unknown'}",
    )


@router.get("", response_model=PaginatedMessages)
def list_messages(
    q: Optional[str] = Query(default=None, description="full text query"),
    chat_id: Optional[str] = None,
    sender_id: Optional[str] = None,
    type: Optional[str] = Query(default=None, alias="msg_type"),
    direction: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    fast: bool = Query(default=False, description="Skip expensive total count; total will be len(items)."),
    include_meta: bool = Query(default=True, description="Include meta payload (pruned) for list rendering."),
    include_mp_messages: bool = Query(default=False, description="Include WeChat official-account gh_ messages in WeChat list."),
    content_max_chars: int = Query(default=4000, ge=0, le=20000, description="Truncate content_text to avoid huge payloads."),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    size = max(1, min(1000, size))

    direction = (direction or "").strip().lower() or None
    if direction == "external":
        direction = "in"
    if direction and direction not in {"in", "out"}:
        direction = None

    if q:
        # Use FTS5 when q exists. IMPORTANT: apply the same filters as non-FTS path
        # so search respects chat_id/sender_id/type/time/direction consistently.
        def _parse_dt(v: Optional[str]) -> Optional[datetime]:
            if not v:
                return None
            try:
                if len(v) == 10:
                    return datetime.fromisoformat(v + "T00:00:00")
                text_v = v.replace("Z", "+00:00")
                dt = datetime.fromisoformat(text_v)
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                return dt
            except Exception:
                return None

        clauses: list[str] = ["messages_fts MATCH :q"]
        params = {"q": q, "limit": size, "offset": (page - 1) * size}

        if chat_id:
            clauses.append("m.chat_id = :chat_id")
            params["chat_id"] = chat_id
        if sender_id:
            clauses.append("m.sender_id = :sender_id")
            params["sender_id"] = sender_id
        if type:
            clauses.append("m.type = :type")
            params["type"] = type
        # direction: keep historic compatibility where NULL/'' treated as inbound
        if direction == "in":
            clauses.append("(m.direction = 'in' OR m.direction IS NULL OR m.direction = '')")
        elif direction == "out":
            clauses.append("m.direction = 'out'")
        if not include_mp_messages:
            clauses.append("(coalesce(m.chat_id, '') NOT LIKE 'gh_%' AND coalesce(m.sender_id, '') NOT LIKE 'gh_%')")
            clauses.append("(m.sender_id NOT IN ('weixin', 'filehelper') OR m.sender_id IS NULL)")
            clauses.append("(m.chat_id NOT IN ('filehelper') OR m.chat_id IS NULL)")
            clauses.append("(m.type != 'system' OR m.type IS NULL)")

        dt_from = _parse_dt(time_from)
        dt_to = _parse_dt(time_to)
        if dt_from:
            clauses.append("m.timestamp >= :dt_from")
            params["dt_from"] = dt_from
        if dt_to:
            clauses.append("m.timestamp <= :dt_to")
            params["dt_to"] = dt_to

        where_sql = " AND ".join(clauses) if clauses else "1=1"
        base_sql = (
            "SELECT m.* FROM messages m "
            "JOIN messages_fts fts ON fts.rowid = m.id "
            f"WHERE {where_sql} "
        )
        fts_sql = text(base_sql + "ORDER BY m.timestamp DESC LIMIT :limit OFFSET :offset")
        count_sql = text(base_sql.replace("SELECT m.*", "SELECT COUNT(1) as cnt").replace(" ORDER BY m.timestamp DESC LIMIT :limit OFFSET :offset", ""))

        items = db.execute(fts_sql, params).mappings().all()
        ids = [row["id"] for row in items if row.get("id") is not None]
        derived_map: dict[int, dict | None] = {}
        # 为了保证列表接口快速稳定，这里不触发小模型派生；
        # 派生由前端在进入页面或点击“拉取”时调用 /api/messages/derive 完成
        total = (
            len(items)
            if fast
            else (db.execute(count_sql, {k: v for k, v in params.items() if k != "limit" and k != "offset"}).scalar() or 0)
        )
        contact_display_names = _load_contact_display_names(db, [row.get("sender_id") for row in items])
        data = []
        for row in items:
            rd = dict(row)
            normalized = _normalize_wechat_gateway_message_fields(
                rd.get("sender_id"),
                rd.get("sender_name"),
                rd.get("chat_id"),
                rd.get("talker_name"),
                rd.get("type"),
                rd.get("content_text"),
                rd.get("media_url"),
                rd.get("meta"),
                db=db,
            )
            rd["sender_name"] = normalized.get("sender_name")
            rd["talker_name"] = normalized.get("talker_name")
            rd["type"] = normalized.get("type")
            rd["media_url"] = normalized.get("media_url")
            rd["meta"] = normalized.get("meta")
            sender_key = str(rd.get("sender_id") or "").strip()
            if sender_key and contact_display_names.get(sender_key):
                rd["sender_name"] = contact_display_names[sender_key]
            msg_id = rd.get("id")
            if msg_id in derived_map:
                rd["derived"] = derived_map[msg_id]
            
            # Fix JSON field parsing for FTS queries
            # FTS queries return JSON fields as strings, need to parse them
            try:
                if isinstance(rd.get("meta"), str):
                    rd["meta"] = json.loads(rd["meta"]) if rd["meta"] else None
            except (json.JSONDecodeError, TypeError):
                rd["meta"] = None
                
            try:
                if isinstance(rd.get("derived"), str):
                    rd["derived"] = json.loads(rd["derived"]) if rd["derived"] else None
            except (json.JSONDecodeError, TypeError):
                rd["derived"] = None
                
            try:
                if isinstance(rd.get("tags"), str):
                    rd["tags"] = json.loads(rd["tags"]) if rd["tags"] else None
            except (json.JSONDecodeError, TypeError):
                rd["tags"] = None

            # Prune meta/content for stability (FTS path returns mapping rows).
            if not include_meta:
                rd["meta"] = None
            else:
                rd["meta"] = _sanitize_meta_for_list(rd.get("meta"))
            display_title = ""
            try:
                display_title = str(((rd.get("meta") or {}).get("display_title") or "")).strip()
            except Exception:
                display_title = ""
            rd["content_text"] = _truncate_text(display_title or rd.get("content_text"), content_max_chars)
            
            # include raw meta to allow frontend to render link/image badges
            if include_meta and rd.get("meta") is None and "meta" in row:
                try:
                    rd["meta"] = _coerce_json_field(row["meta"])
                except Exception:
                    pass
            # 兼容旧前端：回填 key_info/key_info_origin
            try:
                d = rd.get("derived") or {}
                if isinstance(d, dict):
                    if (d.get("summary_full") or d.get("summary")) and not d.get("key_info"):
                        d["key_info"] = d.get("summary_full") or d.get("summary") or ""
                    if d.get("summary_origin") and not d.get("key_info_origin"):
                        d["key_info_origin"] = d.get("summary_origin")
                    # Compose display-only summary from meeting_number/platform/key_info
                    d["display_summary"] = _compose_message_display_summary(d)
                    rd["derived"] = d
            except Exception:
                pass
            data.append(MessageOut(**rd))
        return {"total": int(total), "items": data}

    query = select(Message)
    if chat_id:
        query = query.where(Message.chat_id == chat_id)
    if sender_id:
        query = query.where(Message.sender_id == sender_id)
    if type:
        query = query.where(Message.type == type)
    if direction:
        if direction == "in":
            # 兼容历史数据：direction 为空/NULL 视作 "in"
            query = query.where(or_(Message.direction == "in", Message.direction == None, Message.direction == ""))
        else:
            query = query.where(Message.direction == direction)
    if not include_mp_messages:
        query = query.where(
            (Message.chat_id == None) | (~Message.chat_id.like("gh_%")),
            (Message.sender_id == None) | (~Message.sender_id.like("gh_%")),
            (Message.sender_id == None) | (~Message.sender_id.in_(["weixin", "filehelper"])),
            (Message.chat_id == None) | (~Message.chat_id.in_(["filehelper"])),
            (Message.type == None) | (Message.type != "system"),
        )
    def _parse_dt(v: Optional[str]) -> Optional[datetime]:
        """Parse ISO-like datetime strings from the frontend.

        - Accepts date-only (YYYY-MM-DD) and full ISO timestamps (with/without Z/offset).
        - If timezone-aware, convert to local naive time to match DB stored timestamps
          (DB stores naive local times coming from chatlog). This avoids missing latest
          data due to UTC/local mismatches.
        """
        if not v:
            return None
        try:
            # support date-only like YYYY-MM-DD
            if len(v) == 10:
                return datetime.fromisoformat(v + "T00:00:00")
            text = v.replace("Z", "+00:00")  # allow trailing Z from toISOString()
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                # convert to local naive time
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None

    dt_from = _parse_dt(time_from)
    dt_to = _parse_dt(time_to)
    if dt_from:
        query = query.where(Message.timestamp >= dt_from)
    if dt_to:
        query = query.where(Message.timestamp <= dt_to)

    items = db.execute(query.order_by(Message.timestamp.desc()).limit(size).offset((page - 1) * size)).scalars().all()
    total = len(items) if fast else (db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0)
    # 同理：列表接口不做派生，避免阻塞首屏。/derive 负责派生。
    # try:
    #     conf = load_ai_config()
    #     adv = conf.get("analysis_defaults") or {}
    #     concurrency = int(adv.get("concurrency") or 8)
    # except Exception:
    #     concurrency = 8
    # ensure_message_features(db, list(items), concurrency=concurrency)
    contact_display_names = _load_contact_display_names(db, [item.sender_id for item in items])
    compat_items: list[MessageOut] = []
    for i in items:
        normalized = _normalize_wechat_gateway_message_fields(i.sender_id, i.sender_name, i.chat_id, i.talker_name, i.type, i.content_text, i.media_url, i.meta, db=db)
        sender_key = str(i.sender_id or "").strip()
        sender_display_name = contact_display_names.get(sender_key) or normalized['sender_name']
        out = MessageOut(
            id=int(i.id),
            chat_id=i.chat_id,
            sender_id=i.sender_id,
            sender_name=sender_display_name,
            talker_name=normalized['talker_name'],
            timestamp=i.timestamp,
            direction=i.direction,
            type=normalized['type'],
            content_text=_truncate_text((normalized.get('meta') or {}).get('display_title') or i.content_text, content_max_chars),
            media_url=normalized['media_url'],
            meta=(None if not include_meta else _sanitize_meta_for_list(normalized['meta'])),
            tags=_coerce_json_field(i.tags),
            derived=_coerce_json_field(i.derived),
            importance_score=int(i.importance_score or 0),
            upvotes=int(i.upvotes or 0),
            downvotes=int(i.downvotes or 0),
        )
        try:
            d = dict(out.derived or {})
            if (d.get("summary_full") or d.get("summary")) and not d.get("key_info"):
                d["key_info"] = d.get("summary_full") or d.get("summary") or ""
            if d.get("summary_origin") and not d.get("key_info_origin"):
                d["key_info_origin"] = d.get("summary_origin")
            d["display_summary"] = _compose_message_display_summary(d)
            out.derived = d
        except Exception:
            pass
        compat_items.append(out)
    return {"total": int(total), "items": compat_items}



@router.get("/mp", response_model=PaginatedMessages)
def list_mp_messages(
    page: int = 1,
    size: int = 50,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    chat_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List WeChat official account (gh_*) push messages for the 公众号 module."""
    page = max(1, page)
    size = max(1, min(500, size))

    query = select(Message).where(
        or_(
            Message.sender_id.like("gh_%"),
            Message.chat_id.like("gh_%"),
        ),
        or_(Message.direction == "in", Message.direction == None, Message.direction == ""),
    )

    if chat_id:
        query = query.where(Message.chat_id == chat_id)

    def _parse_dt(v):
        if not v:
            return None
        try:
            if len(v) == 10:
                return datetime.fromisoformat(v + "T00:00:00")
            text = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None

    dt_from = _parse_dt(time_from)
    dt_to = _parse_dt(time_to)
    if dt_from:
        query = query.where(Message.timestamp >= dt_from)
    if dt_to:
        query = query.where(Message.timestamp <= dt_to)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    items = db.execute(query.order_by(Message.timestamp.desc()).limit(size).offset((page - 1) * size)).scalars().all()

    data: list[MessageOut] = []
    for m in items:
        out = MessageOut.model_validate(m)
        appmsg = _extract_wechat_appmsg(m.content_text)
        if appmsg:
            d = dict(out.derived or {})
            if appmsg.get("title"):
                d["mp_title"] = str(appmsg["title"]).strip()
            if appmsg.get("desc"):
                d["mp_desc"] = str(appmsg["desc"]).strip()
            if appmsg.get("url"):
                d["mp_url"] = str(appmsg["url"]).strip()
            if appmsg.get("sourcedisplayname"):
                d["mp_source"] = str(appmsg["sourcedisplayname"]).strip()
            if appmsg.get("thumburl"):
                d["mp_thumb"] = str(appmsg["thumburl"]).strip()
            out.derived = d
        data.append(out)

    return {"total": int(total), "items": data}


@router.get("/effective", response_model=PaginatedMessages)
def list_effective_messages(
    period: str | None = Query(default=None, description="1day/3days/1week/1month"),
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    chat_id: Optional[str] = None,
    sender_id: Optional[str] = None,
    type: Optional[str] = Query(default=None, alias="msg_type"),
    page: int = 1,
    size: int = 1000,
    external_only: Optional[bool] = None,
    exclude_short: Optional[bool] = None,
    exclude_system: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    size = max(1, min(2000, size))

    query = select(Message)
    if chat_id:
        query = query.where(Message.chat_id == chat_id)
    if sender_id:
        query = query.where(Message.sender_id == sender_id)
    if type:
        query = query.where(Message.type == type)

    def _parse_dt(v: Optional[str]) -> Optional[datetime]:
        if not v:
            return None
        try:
            if len(v) == 10:
                return datetime.fromisoformat(v + "T00:00:00")
            text = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                # convert to local naive to align with DB naive timestamps
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None

    def _cutoff_for_period(p: Optional[str]) -> Optional[datetime]:
        if not p:
            return None
        p = p.lower()
        mapping = {
            "1day": timedelta(days=1),
            "3days": timedelta(days=3),
            "1week": timedelta(weeks=1),
            "1month": timedelta(days=30),
        }
        delta = mapping.get(p)
        if not delta:
            return None
        return datetime.utcnow() - delta

    dt_from = _parse_dt(time_from)
    dt_to = _parse_dt(time_to)
    if period and not dt_from:
        dt_from = _cutoff_for_period(period)
    if dt_from:
        query = query.where(Message.timestamp >= dt_from)
    if dt_to:
        query = query.where(Message.timestamp <= dt_to)

    # Fetch a window and apply uniform backend filters to keep consistency with AI snapshot
    base_items = db.execute(query.order_by(Message.timestamp.desc()).limit(10000)).scalars().all()
    raw_rows = [
        {
            "id": m.id,
            "chat_id": m.chat_id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "talker_name": m.talker_name,
            "timestamp": m.timestamp,
            "direction": m.direction,
            "type": m.type,
            "content_text": m.content_text,
            "media_url": m.media_url,
            "tags": m.tags,
            "derived": m.derived,
            "importance_score": m.importance_score,
            "upvotes": m.upvotes,
            "downvotes": m.downvotes,
            "send_status": m.send_status,
        }
        for m in base_items
    ]
    # default filter switches from config if not specified
    try:
        conf = load_ai_config()
        mf = conf.get("message_filters") or {}
    except Exception:
        mf = {}
    eo = external_only if external_only is not None else bool(mf.get("external_only", True))
    es = exclude_short if exclude_short is not None else bool(mf.get("exclude_short", True))
    sy = exclude_system if exclude_system is not None else bool(mf.get("exclude_system", True))

    filtered = list(
        filter_effective_messages(
            raw_rows,
            external_only=eo,
            exclude_short=es,
            exclude_system=sy,
        )
    )
    total = len(filtered)
    page_slice = filtered[(page - 1) * size : (page - 1) * size + size]
    id_map = {row["id"] for row in page_slice}
    orm_page = []
    if id_map:
        orm_page = db.execute(select(Message).where(Message.id.in_(id_map))).scalars().all()
        orm_page.sort(key=lambda m: m.timestamp or datetime.min, reverse=True)
    compat_items: list[MessageOut] = []
    for i in orm_page:
        out = MessageOut.model_validate(i)
        try:
            d = dict(out.derived or {})
            if (d.get("summary_full") or d.get("summary")) and not d.get("key_info"):
                d["key_info"] = d.get("summary_full") or d.get("summary") or ""
            if d.get("summary_origin") and not d.get("key_info_origin"):
                d["key_info_origin"] = d.get("summary_origin")
            out.derived = d
        except Exception:
            pass
        compat_items.append(out)
    return {"total": int(total), "items": compat_items}


@router.post("/{message_id}/upvote", response_model=UpDownVoteResult)
def upvote(message_id: int, db: Session = Depends(get_db)):
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(404, "message not found")
    msg.upvotes += 1
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return UpDownVoteResult(id=msg.id, upvotes=msg.upvotes, downvotes=msg.downvotes)


@router.post("/{message_id}/downvote", response_model=UpDownVoteResult)
def downvote(message_id: int, db: Session = Depends(get_db)):
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(404, "message not found")
    msg.downvotes += 1
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return UpDownVoteResult(id=msg.id, upvotes=msg.upvotes, downvotes=msg.downvotes)


@router.post("/{message_id}/tags")
def update_tags(message_id: int, body: TagUpdateIn, db: Session = Depends(get_db)):
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(404, "message not found")
    msg.tags = body.tags
    db.add(msg)
    db.commit()
    return {"id": msg.id, "tags": msg.tags}


@router.post("/{message_id}/interact")
def interact(message_id: int, kind: str, db: Session = Depends(get_db)):
    if kind not in ("约","问","答","顶","踩"):
        raise HTTPException(400, "invalid kind")
    if not db.get(Message, message_id):
        raise HTTPException(404, "message not found")
    it = Interaction(message_id=message_id, kind=kind, payload=None)
    db.add(it)
    db.commit()
    return {"status": "ok", "id": it.id}


@router.post("/interact-ext")
def interact_ext(kind: str, payload: dict | None = None, db: Session = Depends(get_db)):
    if kind not in ("约","问","答","顶","踩"):
        raise HTTPException(400, "invalid kind")
    it = InteractionExt(kind=kind, payload=payload or {})
    db.add(it)
    db.commit()
    return {"status": "ok", "id": it.id}


@router.get("/export")
def export_messages(
    format: str = "csv",
    q: Optional[str] = None,
    chat_id: Optional[str] = None,
    sender_id: Optional[str] = None,
    type: Optional[str] = Query(default=None, alias="msg_type"),
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # reuse list logic (without pagination)
    def _parse_dt(v: Optional[str]):
        # accept YYYY-MM-DD, ISO timestamps and trailing Z; normalize to naive UTC
        if not v:
            return None
        try:
            if len(v) == 10:
                return datetime.fromisoformat(v+"T00:00:00")
            text = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    items: list[MessageOut]
    if q:
        # Apply same filters in FTS branch as non-FTS branch so exports match UI filters
        clauses: list[str] = ["messages_fts MATCH :q"]
        params: dict[str, Any] = {"q": q}
        if chat_id:
            clauses.append("m.chat_id = :chat_id")
            params["chat_id"] = chat_id
        if sender_id:
            clauses.append("m.sender_id = :sender_id")
            params["sender_id"] = sender_id
        if type:
            clauses.append("m.type = :type")
            params["type"] = type
        dt_from = _parse_dt(time_from)
        dt_to = _parse_dt(time_to)
        if dt_from:
            clauses.append("m.timestamp >= :dt_from")
            params["dt_from"] = dt_from
        if dt_to:
            clauses.append("m.timestamp <= :dt_to")
            params["dt_to"] = dt_to
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        fts_sql = text(
            "SELECT m.* FROM messages m "
            "JOIN messages_fts fts ON fts.rowid = m.id "
            f"WHERE {where_sql} "
            "ORDER BY m.timestamp DESC"
        )
        rows = db.execute(fts_sql, params).mappings().all()
        items = []
        for r in rows:
            rd = dict(r)
            # Fix JSON field parsing for FTS queries
            try:
                if isinstance(rd.get("meta"), str):
                    rd["meta"] = json.loads(rd["meta"]) if rd["meta"] else None
            except (json.JSONDecodeError, TypeError):
                rd["meta"] = None
                
            try:
                if isinstance(rd.get("derived"), str):
                    rd["derived"] = json.loads(rd["derived"]) if rd["derived"] else None
            except (json.JSONDecodeError, TypeError):
                rd["derived"] = None
                
            try:
                if isinstance(rd.get("tags"), str):
                    rd["tags"] = json.loads(rd["tags"]) if rd["tags"] else None
            except (json.JSONDecodeError, TypeError):
                rd["tags"] = None
            
            items.append(MessageOut(**rd))
    else:
        query = select(Message)
        if chat_id:
            query = query.where(Message.chat_id == chat_id)
        if sender_id:
            query = query.where(Message.sender_id == sender_id)
        if type:
            query = query.where(Message.type == type)
        dt_from = _parse_dt(time_from)
        dt_to = _parse_dt(time_to)
        if dt_from:
            query = query.where(Message.timestamp >= dt_from)
        if dt_to:
            query = query.where(Message.timestamp <= dt_to)
        rows = db.execute(query.order_by(Message.timestamp.desc())).scalars().all()
        items = [MessageOut.model_validate(r) for r in rows]

    # build output
    fn = f"messages.{format}"
    if format == "csv":
        sio = io.StringIO()
        w = csv.writer(sio)
        w.writerow(["id","time","chat_id","talker_name","sender_id","sender_name","type","content"])
        for m in items:
            w.writerow([
                m.id,
                m.timestamp.isoformat() if m.timestamp else "",
                m.chat_id or "",
                m.talker_name or "",
                m.sender_id or "",
                m.sender_name or "",
                m.type or "",
                (m.content_text or "").replace("\n"," ")
            ])
        data = sio.getvalue()
        return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={fn}"})
    else:
        # html/xls use table
        rows = []
        for m in items:
            rows.append(
                f"<tr><td>{m.id}</td><td>{html.escape(m.timestamp.isoformat() if m.timestamp else '')}</td>"
                f"<td>{html.escape(m.chat_id or '')}</td><td>{html.escape(m.talker_name or '')}</td>"
                f"<td>{html.escape(m.sender_name or m.sender_id or '')}</td><td>{html.escape(m.type or '')}</td>"
                f"<td>{html.escape((m.content_text or '')[:200])}</td></tr>"
            )
        table = """
        <table border="1" cellspacing="0" cellpadding="4">
        <thead><tr><th>ID</th><th>时间</th><th>会话</th><th>对象</th><th>发送人</th><th>类型</th><th>内容</th></tr></thead>
        <tbody>{rows}</tbody></table>
        """.replace("{rows}", "\n".join(rows))
        mt = "text/html; charset=utf-8" if format == "html" else "application/vnd.ms-excel"
        ext = "html" if format == "html" else "xls"
        return Response(table, media_type=mt, headers={"Content-Disposition": f"attachment; filename=messages.{ext}"})


@router.post("/derive")
def derive_message_features(body: MessageDeriveRequest, progress_key: str | None = None, db: Session = Depends(get_db)):
    body, effective_force = _prepare_derive_request(body)
    message_ids = _resolve_message_ids(db, body)
    if not message_ids:
        if progress_key:
            _set_progress(progress_key, status="done", total=0, done=0, updated=0, errors=[], debug=[])
            return {"status": "ok", "updated": 0, "progress_key": progress_key}
        return {"status": "ok", "updated": 0}

    if progress_key:
        with _PROGRESS_LOCK:
            existing = _DERIVE_JOBS.get(progress_key)
            if existing and existing.is_alive():
                info = dict(PROGRESS.get(progress_key) or {})
                return {
                    "status": str(info.get("status") or "running"),
                    "updated": int(info.get("updated") or 0),
                    "progress_key": progress_key,
                    "total": int(info.get("total") or len(message_ids)),
                    "done": int(info.get("done") or 0),
                }
            _set_progress(progress_key, status="queued", total=len(message_ids), done=0, updated=0, errors=[], debug=[])
            thread = threading.Thread(
                target=_run_derive_job,
                args=(progress_key, body.model_dump(), message_ids),
                daemon=True,
                name=f"msg-derive-{progress_key}",
            )
            _DERIVE_JOBS[progress_key] = thread
            thread.start()
        return {"status": "queued", "updated": 0, "progress_key": progress_key, "total": len(message_ids), "done": 0}

    messages: List[Message] = db.execute(select(Message).where(Message.id.in_(message_ids)).order_by(Message.timestamp.desc())).scalars().all()
    return _derive_messages_internal(db, messages, body, effective_force=effective_force, progress_key=None)


@router.get("/derive/progress")
def derive_progress(key: str):
    info = PROGRESS.get(key)
    if not info:
        return {"status": "unknown", "done": 0, "total": 0}
    return {
        "status": info.get("status"),
        "done": info.get("done"),
        "total": info.get("total"),
        "updated": info.get("updated", 0),
        "errors": info.get("errors", [])[:10],
        "error": info.get("error"),
    }


@router.get("/by-ids", response_model=PaginatedMessages)
def get_messages_by_ids(ids: str, db: Session = Depends(get_db)):
    try:
        id_list = [int(x) for x in ids.split(',') if x.strip().isdigit()]
    except Exception:
        id_list = []
    if not id_list:
        return {"total": 0, "items": []}
    rows = db.execute(select(Message).where(Message.id.in_(id_list))).scalars().all()
    # keep same order
    rows.sort(key=lambda m: (m.timestamp or datetime.min), reverse=True)

    items: list[MessageOut] = []
    for i in rows:
        out = MessageOut.model_validate(i)
        try:
            d = dict(out.derived or {})
            if (d.get("summary_full") or d.get("summary")) and not d.get("key_info"):
                d["key_info"] = d.get("summary_full") or d.get("summary") or ""
            if d.get("summary_origin") and not d.get("key_info_origin"):
                d["key_info_origin"] = d.get("summary_origin")
            d["display_summary"] = _compose_message_display_summary(d)
            out.derived = d
        except Exception:
            pass
        items.append(out)
    return {"total": len(rows), "items": items}
