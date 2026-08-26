from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
import requests
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisSnapshot, Message, Contact, EmailMessage
from .message_filters import filter_effective_messages


DEFAULT_PERIODS: Tuple[str, ...] = ("1day", "3days", "1week", "1month")


def _normalize_ids(message_ids: Optional[Iterable[int]]) -> List[int]:
    if not message_ids:
        return []
    normalized: List[int] = []
    for mid in message_ids:
        try:
            value = int(mid)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        normalized.append(value)
    return sorted(set(normalized))


def _scope_key(message_ids: List[int], filters: Optional[Dict[str, Any]]) -> str:
    payload = {
        "ids": message_ids,
        "filters": filters or {},
    }
    data = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def _period_to_cutoff(period: Optional[str]) -> Optional[datetime]:
    if not period:
        return None
    period = period.lower()
    now = datetime.utcnow()
    mapping = {
        "1day": timedelta(days=1),
        "3days": timedelta(days=3),
        "1week": timedelta(weeks=1),
        "1month": timedelta(days=30),
    }
    delta = mapping.get(period)
    if not delta:
        return None
    return now - delta


def _message_to_dict(msg: Message) -> Dict[str, Any]:
    ts = msg.timestamp.isoformat() if msg.timestamp else None
    return {
        "channel": "wechat",
        "id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "talker_name": msg.talker_name,
        "timestamp": ts,
        "time": ts,
        "direction": msg.direction,
        "message_type": msg.type,
        "type": msg.type,
        "content": msg.content_text,
        "content_text": msg.content_text,
        "media_url": msg.media_url,
        "meta": msg.meta or {},
        "tags": msg.tags or {},
        "derived": msg.derived or {},
        "importance_score": msg.importance_score,
        "upvotes": msg.upvotes,
        "downvotes": msg.downvotes,
        "send_status": msg.send_status,
    }


def _email_to_dict(em: EmailMessage) -> Dict[str, Any]:
    ts = em.sent_at.isoformat() if em.sent_at else None
    # Snapshot payload must stay compact (LLM cost + SQLite JSON write performance).
    # Prefer derived summary; otherwise keep only a short snippet/body prefix.
    derived = em.derived or {}
    summary = ""
    if isinstance(derived, dict):
        summary = (derived.get("summary") or "").strip()
    body = (em.body_text or "").strip()
    snippet = (em.snippet or "").strip()
    content = summary or snippet or (body[:800] if body else "")
    return {
        "channel": "email",
        "id": em.id,
        "time": ts,
        "timestamp": ts,
        "direction": em.direction,
        "message_type": "邮件",
        "type": "email",
        "sender_name": em.from_addr,
        "talker_name": None,
        "subject": em.subject,
        "content": content,
        "content_text": content,
        "derived": derived,
        "meta": {
            "to": em.to_addrs,
            "cc": em.cc_addrs,
        },
    }


def _collect_contacts(db: Session, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    sender_ids = {m.get("sender_id") for m in messages if m.get("sender_id")}
    if not sender_ids:
        return {}
    contacts = db.execute(select(Contact).where(Contact.id.in_(sender_ids))).scalars().all()
    data: Dict[str, Any] = {}
    for contact in contacts:
        data[contact.id] = {
            "rating": contact.rating,
            "name": contact.name,
            "alias": contact.alias,
            "labels": contact.labels or {},
        }
    return data


def _time_range(messages: List[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[datetime]]:
    times: List[datetime] = []
    for msg in messages:
        ts = msg.get("timestamp") or msg.get("time")
        if not ts:
            continue
        if isinstance(ts, datetime):
            times.append(ts)
            continue
        text = str(ts)
        if text.endswith("Z"):
            text = text[:-1]
        try:
            times.append(datetime.fromisoformat(text))
        except Exception:
            continue
    if not times:
        return None, None
    return min(times), max(times)


def collect_messages(
    db: Session,
    message_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Message]:
    ids = _normalize_ids(message_ids)
    query = select(Message)
    if ids:
        query = query.where(Message.id.in_(ids))
    period = (filters or {}).get("period") if filters else None
    cutoff = _period_to_cutoff(period)
    if cutoff:
        query = query.where(Message.timestamp >= cutoff)
    # If filters specify direction or others in future, extend here.
    if not ids:
        query = query.order_by(Message.timestamp.desc()).limit(2000)
    else:
        query = query.order_by(Message.timestamp.asc())
    rows = db.execute(query).scalars().all()
    # ensure chronological order
    rows.sort(key=lambda m: (m.timestamp or datetime.min))
    # Apply the same filters as message list to guarantee consistency
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
        }
        for m in rows
    ]
    f = filters or {}
    eff = list(
        filter_effective_messages(
            raw_rows,
            external_only=bool(f.get("external_only", True)),
            exclude_short=bool(f.get("exclude_short", True)),
            exclude_system=bool(f.get("exclude_system", True)),
        )
    )
    id_map = {r["id"] for r in eff}
    rows = [m for m in rows if m.id in id_map]
    return rows


def upsert_snapshot(
    db: Session,
    *,
    message_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
) -> AnalysisSnapshot:
    ids = _normalize_ids(message_ids)
    scope = _scope_key(ids, filters)
    snapshot = db.execute(
        select(AnalysisSnapshot).where(AnalysisSnapshot.scope_key == scope)
    ).scalar_one_or_none()

    messages = collect_messages(db, ids, filters)
    payload_messages: list[dict] = [_message_to_dict(m) for m in messages]

    # 同期拉取邮件：按 period 过滤 sent_at，并追加到快照中（紧凑字段）
    period = (filters or {}).get("period") if filters else None
    cutoff = _period_to_cutoff(period)
    try:
        q = select(EmailMessage)
        if cutoff:
            q = q.where(EmailMessage.sent_at >= cutoff)
        # Cap to keep snapshot JSON small and DB writes fast
        rows = db.execute(q.order_by(EmailMessage.sent_at.desc()).limit(300)).scalars().all()
        for em in rows:
            payload_messages.append(_email_to_dict(em))
    except Exception:
        pass

    # 同期拉取新闻（关注页）默认关闭：newswatch 模块会直接读取新闻源，
    # 且这里的抓取可能触发 Playwright 回退导致 summary 请求显著变慢。
    include_news = bool((options or {}).get("include_news", False)) if options else False
    if include_news:
        try:
            from ..models import SyncState
            row = db.get(SyncState, "newsnow_config")
            news_conf = json.loads(row.value) if row and row.value else {}
            base = (news_conf or {}).get("base_url") or "http://localhost:4444"
            base = str(base).rstrip("/")
            endpoints = [
                f"{base}/api/follow",
                f"{base}/api/news?tab=follow",
                f"{base}/api/articles?tab=follow",
                f"{base}/api/items?tab=follow",
            ]
            items: list[dict] = []

            def _try_json(u: str) -> list[dict]:
                try:
                    headers = {}
                    tok = (news_conf or {}).get("auth_token") or (news_conf or {}).get("token")
                    if tok:
                        headers["Authorization"] = f"Bearer {tok}"
                    r = requests.get(u, timeout=4, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        for key in ("items", "data", "list", "records"):
                            v = data.get(key)
                            if isinstance(v, list):
                                return v
                    return []
                except Exception:
                    return []

            for ep in endpoints:
                items = _try_json(ep)
                if items:
                    break

            # HTML fallback: 解析 /follow 或首页的 SSR/静态内容（不再启用 Playwright 回退）
            if not items:
                try:
                    from bs4 import BeautifulSoup

                    def _try_html(u: str) -> list[dict]:
                        try:
                            r = requests.get(u, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                            r.raise_for_status()
                            soup = BeautifulSoup(r.text, "html.parser")
                            nodes = soup.find_all("article")
                            if not nodes:
                                nodes = soup.find_all(
                                    ["div", "li"],
                                    class_=lambda c: c and any(k in c.lower() for k in ["card", "item", "news", "article"]),
                                )
                            results: list[dict] = []
                            for n in nodes[:80]:
                                a = n.find("a", href=True)
                                title = ""
                                for tag in ("h1", "h2", "h3", "h4"):
                                    h = n.find(tag)
                                    if h and h.get_text(strip=True):
                                        title = h.get_text(strip=True)
                                        break
                                if not title and a and a.get_text(strip=True):
                                    title = a.get_text(strip=True)
                                summary = ""
                                for c in n.find_all(["p", "div", "span"], limit=6):
                                    txt = c.get_text(" ", strip=True)
                                    if txt and len(txt) >= 12:
                                        summary = txt
                                        break
                                src = ""
                                src_el = n.find(
                                    class_=lambda c: c and any(k in c.lower() for k in ["source", "from", "author", "site"])
                                )
                                if src_el:
                                    src = src_el.get_text(strip=True)
                                ts = ""
                                t_el = n.find("time")
                                if t_el:
                                    ts = t_el.get("datetime") or t_el.get_text(strip=True)
                                url = a["href"] if a and a.has_attr("href") else ""
                                if not (title or summary):
                                    continue
                                results.append(
                                    {"title": title or summary[:40], "summary": summary, "source": src, "url": url, "publishedAt": ts}
                                )
                            return results
                        except Exception:
                            return []

                    for path in ("/c/focus", "/follow", "/"):
                        items = _try_html(base + path)
                        if items:
                            break
                except Exception:
                    items = []

            def _news_map(it: dict) -> dict:
                tit = (it.get("title") or it.get("headline") or it.get("name") or "").strip()
                src = (it.get("source") or it.get("site") or it.get("author") or "").strip()
                summ = (it.get("summary") or it.get("desc") or it.get("excerpt") or it.get("content") or "").strip()
                url = (it.get("url") or it.get("link") or it.get("href") or "").strip()
                ts = it.get("publishedAt") or it.get("time") or it.get("date") or None
                lines = []
                if tit:
                    lines.append(f"标题: {tit}")
                if src:
                    lines.append(f"来源: {src}")
                if summ:
                    lines.append(f"摘要: {summ}")
                if url:
                    lines.append(f"链接: {url}")
                text = "\n".join(lines).strip()
                raw_id = url or (tit + str(ts or ""))
                nid = int(hashlib.sha1(raw_id.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)
                return {
                    "channel": "news",
                    "id": nid,
                    "timestamp": ts,
                    "time": ts,
                    "message_type": "新闻",
                    "type": "news",
                    "sender_name": src or None,
                    "talker_name": None,
                    "content": text,
                    "content_text": text,
                    "meta": {"url": url, "source": src},
                    "derived": {},
                }

            if items:
                for it in items[:300]:
                    payload_messages.append(_news_map(it))
        except Exception:
            pass
    contact_ratings = _collect_contacts(db, payload_messages)
    time_from, time_to = _time_range(payload_messages)

    meta = {
        "total_messages": len(payload_messages),
        "generated_at": datetime.utcnow().isoformat(),
        "period": (filters or {}).get("period") if filters else None,
        "channels": {
            "wechat": sum(1 for m in payload_messages if m.get("channel") == "wechat"),
            "email": sum(1 for m in payload_messages if m.get("channel") == "email"),
        },
    }

    if snapshot is None:
        snapshot = AnalysisSnapshot(
            scope_key=scope,
            title=title,
            filters=filters,
            options=options,
            message_ids=ids,
            messages=payload_messages,
            contact_ratings=contact_ratings,
            meta=meta,
            status="ready",
            message_count=len(payload_messages),
            time_from=time_from,
            time_to=time_to,
        )
        db.add(snapshot)
    else:
        snapshot.title = title or snapshot.title
        snapshot.filters = filters
        snapshot.options = options
        snapshot.message_ids = ids
        snapshot.messages = payload_messages
        snapshot.contact_ratings = contact_ratings
        snapshot.meta = meta
        snapshot.status = "ready"
        snapshot.message_count = len(payload_messages)
        snapshot.time_from = time_from
        snapshot.time_to = time_to
        snapshot.updated_at = datetime.utcnow()

    return snapshot


def refresh_default_snapshots(db: Session) -> List[AnalysisSnapshot]:
    snapshots: List[AnalysisSnapshot] = []
    for period in DEFAULT_PERIODS:
        snap = upsert_snapshot(db, filters={"period": period})
        snapshots.append(snap)
    return snapshots


__all__ = ["collect_messages", "upsert_snapshot", "refresh_default_snapshots"]
