from __future__ import annotations

import json
import mimetypes
import os
import secrets
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from fastapi import Request, UploadFile

from ..config import settings
from ..db import SessionLocal
from .link_preview import fetch_link_preview, normalize_card_thumbnail_url
from .wechat_gateway import apply_outbound_random_delay, evaluate_outbound_message, load_config as load_wechat_gateway_config, record_outbound_message
from .wechatapi_client import WechatApiClient


SEND_UPLOAD_MAX_BYTES = int(os.getenv("SEND_UPLOAD_MAX_BYTES", str(20 * 1024 * 1024)))


def _data_root() -> Path:
    raw = str(settings.DATABASE_URL or "")
    if raw.startswith("sqlite:///"):
        db_path = Path(raw.split("sqlite:///")[-1]).expanduser().resolve()
        return db_path.parent
    return Path.cwd() / "data"


def send_upload_dir() -> Path:
    path = (_data_root() / "send_uploads").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(name: str) -> str:
    text = (name or "upload").strip().replace("\\", "_").replace("/", "_")
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", " "} else "_" for ch in text).strip()
    return cleaned[:180] or "upload"


def _guess_kind(name: str, mime: str | None = None) -> str:
    m = str(mime or "").lower()
    if m.startswith("image/"):
        return "image"
    ext = Path(name or "").suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        return "image"
    return "file"


def _upload_meta_path(file_id: str) -> Path:
    return send_upload_dir() / f"{file_id}.json"


def _upload_bin_path(file_id: str, name: str) -> Path:
    return send_upload_dir() / f"{file_id}__{_safe_filename(name)}"


def _request_base(request: Request | None = None) -> str:
    if request is None:
        return ""
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        return ""


def make_upload_url(file_id: str, request: Request | None = None) -> str:
    path = f"/api/send/uploads/{file_id}"
    base = _request_base(request)
    return f"{base}{path}" if base else path


def save_send_upload(upload: UploadFile, request: Request | None = None) -> dict[str, Any]:
    file_id = f"up_{int(time.time() * 1000)}_{secrets.token_hex(5)}"
    filename = _safe_filename(upload.filename or "upload")
    data = upload.file.read()
    size = len(data)
    if size > SEND_UPLOAD_MAX_BYTES:
        raise ValueError(f"file too large: {size} > {SEND_UPLOAD_MAX_BYTES}")
    mime = str(upload.content_type or "").strip() or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    kind = _guess_kind(filename, mime)
    bin_path = _upload_bin_path(file_id, filename)
    meta = {
        "file_id": file_id,
        "name": filename,
        "mime": mime,
        "size": size,
        "kind": kind,
        "path": str(bin_path),
        "url": make_upload_url(file_id, request),
        "created_at": int(time.time()),
    }
    with open(bin_path, "wb") as fh:
        fh.write(data)
    with open(_upload_meta_path(file_id), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    return meta


def get_send_upload_meta(file_id: str) -> dict[str, Any] | None:
    p = _upload_meta_path(file_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_send_upload_path(file_id: str) -> Path | None:
    meta = get_send_upload_meta(file_id)
    if not isinstance(meta, dict):
        return None
    raw = str(meta.get("path") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def normalize_attachment(item: Any, request: Request | None = None) -> dict[str, Any] | None:
    if isinstance(item, str):
        url = item.strip()
        if not url:
            return None
        path_part = urlparse(url).path or url
        name = Path(path_part).name or "attachment"
        kind = _guess_kind(name)
        return {
            "file_id": "",
            "name": name,
            "mime": mimetypes.guess_type(name)[0] or "",
            "size": 0,
            "url": url,
            "kind": kind,
        }
    if not isinstance(item, dict):
        return None
    file_id = str(item.get("file_id") or "").strip()
    meta = get_send_upload_meta(file_id) if file_id else None
    merged = {}
    if isinstance(meta, dict):
        merged.update(meta)
    merged.update({k: v for k, v in item.items() if v not in (None, "")})
    name = str(merged.get("name") or "attachment").strip()
    if not name:
        return None
    merged["name"] = name
    merged["kind"] = _guess_kind(name, str(merged.get("mime") or ""))
    if file_id and not merged.get("url"):
        merged["url"] = make_upload_url(file_id, request)
    merged.setdefault("mime", mimetypes.guess_type(name)[0] or "")
    merged.setdefault("size", 0)
    merged.setdefault("file_id", file_id)
    return merged


def normalize_content_parts(item: Any, request: Request | None = None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    raw_parts = item if isinstance(item, list) else []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "").strip().lower()
        if part_type not in {"text", "link", "image", "file"}:
            continue
        cleaned = {"type": part_type}
        if part_type == "text":
            text = str(part.get("text") or "").strip()
            if not text:
                continue
            cleaned["text"] = text
        else:
            att = normalize_attachment(part, request)
            if not att:
                continue
            cleaned.update(att)
            if part_type == "link":
                cleaned["url"] = str(part.get("url") or att.get("url") or "").strip()
                cleaned["text"] = str(part.get("text") or part.get("name") or "").strip()
            cleaned["type"] = part_type
        parts.append(cleaned)
    return parts


def apply_template_vars(text: str, template_vars: dict[str, Any] | None) -> str:
    out = str(text or "")
    for key, value in (template_vars or {}).items():
        token = "{" + str(key).strip() + "}"
        out = out.replace(token, str(value or ""))
    return out


def build_item_payload(item: Any, request: Request | None = None) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        raw = item.model_dump()
    elif isinstance(item, dict):
        raw = dict(item)
    else:
        raw = {}
    template_vars = raw.get("template_vars") if isinstance(raw.get("template_vars"), dict) else {}
    parts = normalize_content_parts(raw.get("content_parts"), request)
    text = apply_template_vars(str(raw.get("text") or ""), template_vars).strip()
    if text and not any(p.get("type") == "text" for p in parts):
        parts.insert(0, {"type": "text", "text": text})
    elif text:
        for part in parts:
            if part.get("type") == "text":
                part["text"] = apply_template_vars(str(part.get("text") or ""), template_vars).strip()
    attachments = [a for a in (normalize_attachment(v, request) for v in (raw.get("attachments") or [])) if a]
    return {
        "target": str(raw.get("target") or raw.get("chat_id") or raw.get("talker") or "").strip(),
        "target_name": str(raw.get("target_name") or "").strip(),
        "campaign_id": raw.get("campaign_id"),
        "delivery_id": raw.get("delivery_id"),
        "provider_override": str(raw.get("provider_override") or "").strip(),
        "channel": str(raw.get("channel") or "").strip(),
        "template_vars": template_vars,
        "content_parts": parts,
        "attachments": attachments,
    }


def render_text_fallback(parts: Iterable[dict[str, Any]], attachments: Iterable[dict[str, Any]]) -> str:
    lines: list[str] = []
    for part in parts:
        p_type = str(part.get("type") or "")
        if p_type == "text":
            text = str(part.get("text") or "").strip()
            if text:
                lines.append(text)
        elif p_type == "link":
            text = str(part.get("text") or "").strip()
            url = str(part.get("url") or "").strip()
            if text and url:
                lines.append(f"{text}\n{url}")
            elif url:
                lines.append(url)
        elif p_type == "image":
            name = str(part.get("name") or "图片").strip()
            url = str(part.get("url") or "").strip()
            lines.append(f"图片：{name}" + (f"\n{url}" if url else ""))
        elif p_type == "file":
            name = str(part.get("name") or "文件").strip()
            url = str(part.get("url") or "").strip()
            lines.append(f"文件：{name}" + (f"\n{url}" if url else ""))
    if attachments:
        rendered_urls = []
        for att in attachments:
            url = str(att.get("url") or "").strip()
            if not url:
                continue
            name = str(att.get("name") or "附件").strip()
            rendered_urls.append(f"{name}: {url}")
        if rendered_urls:
            lines.append("附件：\n" + "\n".join(rendered_urls))
    return "\n\n".join(line for line in lines if line.strip()).strip()


def get_send_provider(provider_override: str | None = None) -> str:
    return "wechatapi_gateway"


def provider_capabilities(provider: str | None = None) -> dict[str, Any]:
    chosen = "wechatapi_gateway"
    client = WechatApiClient()
    configured = client.configured()
    supports_image = True
    supports_file = True
    notes = ["微信联系人、群发、卡片、图片和文件统一通过 WeChatAPI；本地数据库仅作缓存。"]
    return {
        "provider": chosen,
        "configured": configured,
        "supports_text": True,
        "supports_link": True,
        "supports_image": supports_image,
        "supports_file": supports_file,
        "fallback_text_for_media": True,
        "upload_max_bytes": SEND_UPLOAD_MAX_BYTES,
        "notes": notes,
    }


def _has_rich_media(parts: list[dict[str, Any]], attachments: list[dict[str, Any]]) -> bool:
    for part in parts:
        if str(part.get("type") or "") in {"image", "file"}:
            return True
    for att in attachments:
        if str(att.get("kind") or "") in {"image", "file"}:
            return True
    return False


def _part_url(part: dict[str, Any]) -> str:
    return str(part.get("url") or part.get("fileUrl") or part.get("imageUrl") or "").strip()


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _enrich_link_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for part in parts:
        if str(part.get("type") or "").strip().lower() != "link":
            continue
        url = _part_url(part)
        title = str(part.get("title") or part.get("text") or part.get("name") or "").strip()
        desc = str(part.get("desc") or part.get("description") or "").strip()
        thumb_url = normalize_card_thumbnail_url(
            str(part.get("thumb_url") or part.get("thumbUrl") or "").strip()
        )
        if not url:
            continue
        if not title or _looks_like_url(title) or not thumb_url:
            preview = fetch_link_preview(url)
            if not title or _looks_like_url(title):
                title = str(preview.get("title") or "").strip()
            if not desc:
                desc = str(preview.get("desc") or "").strip()
            if not thumb_url:
                thumb_url = normalize_card_thumbnail_url(str(preview.get("thumb_url") or "").strip())
        if not title:
            raise ValueError("链接卡片缺少标题")
        if not thumb_url:
            raise ValueError("链接卡片缺少封面")
        part.update(
            title=title,
            text=title,
            desc=desc,
            thumb_url=thumb_url,
        )
    return parts


def _dispatch_wechatapi_parts(client: WechatApiClient, target: str, parts: list[dict[str, Any]], attachments: list[dict[str, Any]], rendered_text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    rich_supported = all(hasattr(client, name) for name in ("send_link", "send_image", "send_file"))
    if not rich_supported:
        return [{"type": "text_fallback", "resp": client.send_text(to_wxid=target, text=rendered_text)}] if rendered_text else []
    for part in parts:
        p_type = str(part.get("type") or "text").strip().lower()
        if p_type == "text":
            text = str(part.get("text") or "").strip()
            if text:
                results.append({"type": "text", "resp": client.send_text(to_wxid=target, text=text)})
        elif p_type == "link":
            url = _part_url(part)
            if url:
                results.append({"type": "link", "resp": client.send_link(
                    to_wxid=target,
                    url=url,
                    title=str(part.get("title") or part.get("text") or part.get("name") or "链接"),
                    desc=str(part.get("desc") or part.get("description") or ""),
                    thumb_url=str(part.get("thumb_url") or part.get("thumbUrl") or ""),
                )})
        elif p_type == "image":
            url = _part_url(part)
            if url:
                results.append({"type": "image", "resp": client.send_image(to_wxid=target, image_url=url)})
        elif p_type == "file":
            url = _part_url(part)
            if url:
                results.append({"type": "file", "resp": client.send_file(to_wxid=target, file_url=url, file_name=str(part.get("name") or "文件"))})
    for att in attachments:
        url = _part_url(att)
        if not url:
            continue
        kind = str(att.get("kind") or "file").lower()
        if kind == "image":
            results.append({"type": "image", "resp": client.send_image(to_wxid=target, image_url=url)})
        else:
            results.append({"type": "file", "resp": client.send_file(to_wxid=target, file_url=url, file_name=str(att.get("name") or "文件"))})
    if not results and rendered_text:
        results.append({"type": "text", "resp": client.send_text(to_wxid=target, text=rendered_text)})
    return results


def dispatch_send_item(item: Any, request: Request | None = None) -> dict[str, Any]:
    payload = build_item_payload(item, request)
    target = payload["target"]
    if not target:
        return {"ok": False, "error": "missing target"}
    provider = get_send_provider(payload.get("provider_override"))
    parts = payload["content_parts"]
    attachments = payload["attachments"]
    rendered_text = render_text_fallback(parts, attachments)
    if not rendered_text:
        return {"ok": False, "error": "empty rendered text", "target": target}
    db = SessionLocal()
    try:
        conf = load_wechat_gateway_config(db)
        decision = evaluate_outbound_message(conf, target=target, text=rendered_text)
        if not decision.get("allowed"):
            return {
                "ok": False,
                "target": target,
                "provider": provider,
                "blocked": True,
                "rendered_text": rendered_text,
                "error": str(decision.get("reason") or "blocked by wechat gateway rule"),
                "rule": decision,
            }
        apply_outbound_random_delay(conf)
        client = WechatApiClient()
        if not client.configured():
            return {"ok": False, "error": "wechatapi gateway not configured", "target": target, "provider": provider}
        _enrich_link_parts(parts)
        part_results = _dispatch_wechatapi_parts(client, target, parts, attachments, rendered_text)
        resp = {"status": "ok", "results": part_results}
        local_record_error = ""
        try:
            record_outbound_message(db, target=target, text=rendered_text, provider_result=resp)
        except Exception as exc:
            # The remote send has already succeeded. A local cache/SQLite failure
            # must not turn that irreversible external result into a failed send,
            # otherwise the UI invites a retry and can duplicate the message.
            local_record_error = str(exc)
            try:
                db.rollback()
            except Exception:
                pass
        used_text_fallback = any(str(r.get("type") or "") == "text_fallback" for r in part_results)
        result = {
            "ok": True,
            "target": target,
            "provider": provider,
            "mode": "text" if used_text_fallback else ("rich" if _has_rich_media(parts, attachments) or any(str(p.get("type") or "") == "link" for p in parts) else "text"),
            "rendered_text": rendered_text,
            "resp": resp,
        }
        if local_record_error:
            result["local_record_error"] = local_record_error
        return result
    except Exception as exc:
        return {
            "ok": False,
            "target": target,
            "provider": provider,
            "mode": "text",
            "rendered_text": rendered_text,
            "error": str(exc),
        }
    finally:
        db.close()


def dispatch_send_items(items: Iterable[Any], request: Request | None = None) -> dict[str, Any]:
    results = [dispatch_send_item(item, request=request) for item in items]
    return {"status": "ok", "provider": get_send_provider(), "results": results}
