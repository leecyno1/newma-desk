from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Contact, SyncState
import json
from ..schemas import ContactOut, ContactsLookupRequest
from ..services.wechat_contact_sync import sync_contacts_from_wechatapi
from ..services.wechatapi_client import WechatApiClient
from ..services.contact_scoring import (
    build_contact_score_summaries,
    build_contact_scorecard,
    is_sales_contact_payload,
    is_focus_contact,
    resolve_auto_rating,
    resolve_contact_watch,
    resolve_contact_stats,
    resolve_manual_rating,
    set_contact_focus,
    set_contact_watch,
    summarize_contact_score,
)


router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[ContactOut])
def list_contacts(
    limit: int | None = None,
    offset: int = 0,
    include_labels: bool = False,
    include_score_summary: bool = False,
    wechatapi_only: bool = False,
    response: Response = None,
    db: Session = Depends(get_db),
):
    source_filter = Contact.labels["source"].as_string() == "wechatapi_gateway"
    count_query = select(func.count()).select_from(Contact)
    query = select(Contact)
    if wechatapi_only:
        count_query = count_query.where(source_filter)
        query = query.where(source_filter)
    total = db.execute(count_query).scalar() or 0
    query = query.order_by(Contact.rating.desc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    items = db.execute(query).scalars().all()
    if response is not None:
        response.headers["X-Total-Count"] = str(int(total))
    score_summaries = (
        build_contact_score_summaries(db, [str(item.id) for item in items])
        if include_score_summary
        else {}
    )
    out: list[ContactOut] = []
    for i in items:
        stats = resolve_contact_stats(i)
        is_sales = is_sales_contact_payload({
            "name": i.name,
            "alias": i.alias,
            "labels": i.labels,
        })
        payload = {
            "id": i.id,
            "name": i.name,
            "alias": i.alias,
            "rating": i.rating,
            "labels": i.labels if include_labels else None,
            "manual_rating": resolve_manual_rating(i),
            "auto_rating": resolve_auto_rating(i),
            "sample_size": int(stats.get("sample_size", 0) or 0),
            "hit_rate_overall": float(stats.get("hit_rate_overall", 0.0) or 0.0),
            "last_scored_at": stats.get("last_scored_at"),
            "focus": is_focus_contact(i),
            "watch": resolve_contact_watch(i),
            "score_summary": score_summaries.get(str(i.id)),
            "role": "sales" if is_sales else "research",
            "is_sales": is_sales,
        }
        out.append(ContactOut.model_validate(payload))
    return out


@router.get("/ratings")
def list_contact_ratings(db: Session = Depends(get_db)):
    rows = db.execute(select(Contact.id, Contact.rating)).all()
    return {str(contact_id): int(rating or 50) for contact_id, rating in rows if contact_id}


@router.get("/labels")
def list_contact_labels():
    """List labels from the configured WeChatAPI account."""
    client = WechatApiClient()
    if not client.configured():
        raise HTTPException(503, "WeChatAPI 未配置")
    try:
        response = client.list_labels()
    except Exception as exc:
        raise HTTPException(502, f"WeChatAPI 标签拉取失败：{exc}") from exc
    data = response.get("data") if isinstance(response, dict) else None
    rows = data.get("labelList") if isinstance(data, dict) else []
    items = [
        {"id": row.get("labelId"), "name": str(row.get("labelName") or "").strip()}
        for row in (rows or [])
        if isinstance(row, dict) and str(row.get("labelName") or "").strip()
    ]
    return {"status": "ok", "items": items, "source": "wechatapi_gateway"}


@router.post("/lookup", response_model=list[ContactOut])
def lookup_contacts(body: ContactsLookupRequest, db: Session = Depends(get_db)):
    ids = [str(x).strip() for x in (body.ids or []) if str(x).strip()]
    if not ids:
        return []
    items = db.execute(select(Contact).where(Contact.id.in_(ids))).scalars().all()
    return [ContactOut.model_validate(i) for i in items]


@router.post("/{contact_id}/rating")
def set_rating(contact_id: str, delta: int, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    stats = resolve_contact_stats(c)
    manual_rating = max(0, min(100, int(round(resolve_manual_rating(c) + delta))))
    auto_rating = resolve_auto_rating(c)
    final_rating = manual_rating if auto_rating is None else round(manual_rating * 0.3 + float(auto_rating) * 0.7)
    stats["manual_rating"] = manual_rating
    stats["final_rating"] = final_rating
    if auto_rating is not None:
        stats["auto_rating"] = float(auto_rating)
    c.stats = stats
    c.rating = max(0, min(100, int(round(final_rating))))
    db.add(c)
    db.commit()
    return {"id": c.id, "rating": c.rating}


@router.post("/{contact_id}/focus")
def toggle_contact_focus(contact_id: str, enabled: bool = True, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    row = set_contact_focus(db, contact_id, enabled)
    return {"contact_id": row.contact_id, "enabled": row.enabled}


@router.post("/{contact_id}/watch")
def toggle_contact_watch(
    contact_id: str,
    enabled: bool = True,
    reason: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    try:
        payload = set_contact_watch(db, contact_id, enabled, reason=reason)
    except ValueError:
        raise HTTPException(404, "contact not found")
    return {"contact_id": contact_id, **payload}


@router.get("/{contact_id}/scorecard")
def get_contact_scorecard(contact_id: str, db: Session = Depends(get_db)):
    payload = build_contact_scorecard(db, contact_id)
    if not payload:
        raise HTTPException(404, "contact not found")
    return payload


@router.get("/{contact_id}/predictions")
def list_contact_predictions(contact_id: str, limit: int = 50, db: Session = Depends(get_db)):
    payload = build_contact_scorecard(db, contact_id, limit=limit)
    if not payload:
        raise HTTPException(404, "contact not found")
    return {"contact_id": contact_id, "items": payload["predictions"]}


@router.delete("/{contact_id}")
def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    db.delete(c)
    db.commit()
    return {"status": "ok"}


@router.post("/{contact_id}/blacklist")
def add_to_blacklist(contact_id: str, db: Session = Depends(get_db)):
    row = db.get(SyncState, "blacklist_senders")
    arr: list[str] = []
    if row and row.value:
        try:
            data = json.loads(row.value)
            if isinstance(data, list):
                arr = [str(x) for x in data]
        except Exception:
            arr = []
    if contact_id not in arr:
        arr.append(contact_id)
    payload = json.dumps(arr)
    if not row:
        row = SyncState(key="blacklist_senders", value=payload)
    else:
        row.value = payload
    db.add(row)
    db.commit()
    return {"status": "ok", "blacklist_senders": arr}


@router.post("/sync-book")
def sync_contact_book(limit: int | None = None, insert_missing: bool = True, db: Session = Depends(get_db)):
    """Sync friends, saved groups, official accounts and labels from WeChatAPI."""
    try:
        return sync_contacts_from_wechatapi(
            db,
            client=WechatApiClient(),
            insert_missing=insert_missing,
            limit=limit,
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"WeChatAPI 通讯录同步失败：{exc}") from exc
