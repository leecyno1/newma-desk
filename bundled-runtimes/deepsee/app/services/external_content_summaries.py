from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import SyncState
from .ai_tools import extract_message_features


_LOCKS = {"media": threading.Lock(), "mp": threading.Lock()}
_PROMPT_KEYS = {
    "media": "media_content_summary",
    "mp": "mp_content_summary",
}


def _cache_key(kind: str) -> str:
    return f"cli_content_summaries:{kind}"


def _load_cache(db: Session, kind: str) -> dict[str, dict[str, Any]]:
    row = db.get(SyncState, _cache_key(kind))
    if not row or not row.value:
        return {}
    try:
        value = json.loads(row.value)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_cache(db: Session, kind: str, cache: dict[str, dict[str, Any]]) -> None:
    if len(cache) > 2_000:
        ordered = sorted(
            cache.items(),
            key=lambda pair: str(pair[1].get("updated_at") or ""),
            reverse=True,
        )
        cache = dict(ordered[:2_000])
    key = _cache_key(kind)
    row = db.get(SyncState, key)
    if row is None:
        row = SyncState(key=key, value="")
    row.value = json.dumps(cache, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()


def _source_text(kind: str, item: dict[str, Any]) -> str:
    generated_summary = str(item.get("summary") or "").strip()
    if str(item.get("summary_origin") or "").strip().lower() == "tool":
        generated_summary = ""
    source_summary = str(item.get("source_summary") or "").strip()
    if kind == "media":
        title = str(item.get("title") or "").strip()
        body = str(
            item.get("description")
            or item.get("content")
            or source_summary
            or generated_summary
            or ""
        ).strip()
        platform = str(item.get("platform") or "").strip()
        return f"平台：{platform}\n标题：{title}\n内容：{body}".strip()
    title = str(item.get("title") or "").strip()
    body = str(
        item.get("content")
        or item.get("description")
        or source_summary
        or generated_summary
        or ""
    ).strip()
    channel = str(item.get("channel_name") or "").strip()
    return f"公众号：{channel}\n标题：{title}\n正文或简介：{body}".strip()


def _fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def overlay_cached_summaries(
    db: Session | None,
    kind: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if db is None or kind not in _PROMPT_KEYS or not items:
        return items
    cache = _load_cache(db, kind)
    out: list[dict[str, Any]] = []
    for item in items:
        current = dict(item)
        item_id = str(item.get("id") or "").strip()
        text = _source_text(kind, item)
        cached = cache.get(item_id) if item_id else None
        if cached and cached.get("fingerprint") == _fingerprint(text):
            current["source_summary"] = str(
                current.get("source_summary") or current.get("summary") or ""
            )
            current["summary"] = str(cached.get("summary") or current.get("summary") or "")
            current["summary_origin"] = str(cached.get("origin") or "tool")
            current["summary_tone"] = str(cached.get("tone") or "neutral")
            current["summary_keywords"] = cached.get("keywords") or []
        out.append(current)
    return out


def summarize_external_items(
    db: Session,
    kind: str,
    items: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, Any]:
    if kind not in _PROMPT_KEYS:
        raise ValueError(f"unsupported content summary kind: {kind}")
    normalized = [dict(item) for item in items[:500] if str(item.get("id") or "").strip()]
    with _LOCKS[kind]:
        cache = _load_cache(db, kind)
        prepared: list[dict[str, Any]] = []
        fingerprints: dict[str, str] = {}
        for item in normalized:
            item_id = str(item.get("id") or "").strip()
            text = _source_text(kind, item)
            fingerprint = _fingerprint(text)
            fingerprints[item_id] = fingerprint
            cached = cache.get(item_id)
            cached_origin = str((cached or {}).get("origin") or "tool").strip().lower()
            if (
                not force
                and cached
                and cached.get("fingerprint") == fingerprint
                and cached_origin not in {"fallback", "local-fallback"}
            ):
                continue
            prepared.append(
                {
                    "id": item_id,
                    "time": item.get("time") or item.get("publish_time"),
                    "sender": item.get("author") or item.get("channel_name") or "",
                    "content": text,
                }
            )

        features = extract_message_features(
            prepared,
            batch_size=10,
            concurrency=3,
            temperature=0.1,
            prompt_key=_PROMPT_KEYS[kind],
            route_key="mediawatch" if kind == "media" else "mpwatch",
        ) if prepared else {}
        errors = list(features.pop("__errors__", []) or [])
        debug = list(features.pop("__debug__", []) or [])
        now = datetime.utcnow().isoformat()
        generated_count = 0
        for item_id, feature in features.items():
            summary = str(feature.get("summary") or "").strip()
            origin = str(feature.get("summary_origin") or "tool").strip().lower()
            if not summary or origin == "fallback":
                continue
            cache[item_id] = {
                "fingerprint": fingerprints.get(item_id, ""),
                "summary": summary,
                "origin": origin,
                "tone": feature.get("tone") or "neutral",
                "keywords": feature.get("keywords") or [],
                "updated_at": now,
            }
            generated_count += 1
        if prepared:
            _save_cache(db, kind, cache)

    results = []
    for item in overlay_cached_summaries(db, kind, normalized):
        results.append(
            {
                "id": str(item.get("id") or ""),
                "summary": str(item.get("summary") or ""),
                "summary_origin": str(item.get("summary_origin") or ""),
                "tone": str(item.get("summary_tone") or "neutral"),
                "keywords": item.get("summary_keywords") or [],
            }
        )
    return {
        "items": results,
        "requested": len(normalized),
        "attempted": len(prepared),
        "generated": generated_count,
        "failed": max(0, len(prepared) - generated_count),
        "cached": max(0, len(normalized) - len(prepared)),
        "errors": errors,
        "debug": debug,
    }
