from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from threading import Lock
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, or_, case, func
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from ..db import SessionLocal
from ..models import EmailAccount, EmailMessage
from ..schemas import EmailAccountIn, EmailAccountOut, EmailMessageOut, PaginatedEmailMessages, EmailSendRequest
from ..services.email_engine import imap_fetch, FetchOptions, smtp_send, pop3_fetch
from ..services.email_features import build_email_features, persist_email_features


router = APIRouter(prefix="/api/email", tags=["email"])

# serialize per-account sync to avoid SQLite "database is locked" under concurrent writes
_ACCOUNT_LOCKS: dict[int, Lock] = {}
EMAIL_PROGRESS: dict[str, dict] = {}


class EmailReplyRequest(BaseModel):
    body_text: str
    subject: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None


def _normalize_reply_subject(subject: str | None) -> str:
    text = str(subject or "").strip() or "邮件回复"
    return text if text.lower().startswith("re:") else f"Re: {text}"


def _parse_email_address(value: str | None) -> str:
    import email.utils as _email_utils
    name, addr = _email_utils.parseaddr(str(value or ""))
    return (addr or str(value or "")).strip()


def _mask_account_auth(auth: dict | None) -> dict:
    payload = dict(auth or {})
    password = str(payload.get("password") or "")
    oauth_token = str(payload.get("oauth_token") or "")
    payload["password"] = ""
    payload["oauth_token"] = ""
    payload["has_password"] = bool(password)
    payload["has_oauth_token"] = bool(oauth_token)
    return payload


def _build_account_out(row: EmailAccount) -> EmailAccountOut:
    data = {
        "id": row.id,
        "name": row.name,
        "email_address": row.email_address,
        "provider": row.provider,
        "imap_host": row.imap_host,
        "imap_port": row.imap_port,
        "imap_ssl": row.imap_ssl,
        "smtp_host": row.smtp_host,
        "smtp_port": row.smtp_port,
        "smtp_ssl": row.smtp_ssl,
        "auth": _mask_account_auth(row.auth),
        "enabled": row.enabled,
        "last_sync_at": row.last_sync_at,
    }
    return EmailAccountOut.model_validate(data)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/accounts", response_model=list[EmailAccountOut])
def list_accounts(db: Session = Depends(get_db)):
    rows = db.execute(select(EmailAccount).order_by(EmailAccount.id.desc())).scalars().all()
    return [_build_account_out(r) for r in rows]


@router.post("/accounts", response_model=EmailAccountOut)
def create_account(body: EmailAccountIn, db: Session = Depends(get_db)):
    # basic validation for required hosts
    if not (body.imap_host or "").strip() or not (body.smtp_host or "").strip():
        raise HTTPException(400, "imap_host 和 smtp_host 不能为空")
    row = EmailAccount(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _build_account_out(row)


@router.put("/accounts/{account_id}", response_model=EmailAccountOut)
def update_account(account_id: int, body: EmailAccountIn, db: Session = Depends(get_db)):
    row = db.get(EmailAccount, account_id)
    if not row:
        raise HTTPException(404, "account not found")
    if not (body.imap_host or "").strip() or not (body.smtp_host or "").strip():
        raise HTTPException(400, "imap_host 和 smtp_host 不能为空")
    incoming = body.model_dump()
    incoming_auth = dict(incoming.get("auth") or {})
    existing_auth = dict(row.auth or {})
    if not str(incoming_auth.get("password") or "").strip() and str(existing_auth.get("password") or "").strip():
        incoming_auth["password"] = existing_auth.get("password")
    if not str(incoming_auth.get("oauth_token") or "").strip() and str(existing_auth.get("oauth_token") or "").strip():
        incoming_auth["oauth_token"] = existing_auth.get("oauth_token")
    incoming["auth"] = incoming_auth
    for k, v in incoming.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _build_account_out(row)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    row = db.get(EmailAccount, account_id)
    if not row:
        raise HTTPException(404, "account not found")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@router.post("/accounts/{account_id}/sync")
def sync_account(account_id: int, unseen_only: bool = True, limit: int = 100, db: Session = Depends(get_db)):
    row = db.get(EmailAccount, account_id)
    if not row:
        raise HTTPException(404, "account not found")
    lock = _ACCOUNT_LOCKS.setdefault(account_id, Lock())
    with lock:
        try:
            n = imap_fetch(db, row, FetchOptions(limit=limit, unseen_only=unseen_only))
            row.last_sync_at = datetime.utcnow()
            db.commit()
            return {"status": "ok", "new": n, "mode": "imap"}
        except Exception as e:
            # Fallback to POP3 on auth/IMAP errors
            db.rollback()
            try:
                n = pop3_fetch(db, row, limit=limit)
                row.last_sync_at = datetime.utcnow()
                db.commit()
                return {"status": "ok", "new": n, "mode": "pop3", "imap_error": str(e)}
            except Exception as e2:
                db.rollback()
                msg = f"imap_error={str(e)}; pop3_error={str(e2)}"
                if 'Authentication unsuccessful' in msg or 'LOGIN failed' in msg or 'Logon failure' in msg:
                    msg += "; 请在邮箱设置中开启 IMAP/POP，或使用应用专用密码，或改用 OAuth(微软/谷歌建议)。"
                raise HTTPException(502, f"sync error: {msg}")


@router.get("/messages", response_model=PaginatedEmailMessages)
def list_email_messages(
    account_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_bodies: bool = Query(default=False, description="Include body_text/body_html in list payload."),
    db: Session = Depends(get_db),
):
    query = select(EmailMessage)
    if account_id:
        query = query.where(EmailMessage.account_id == account_id)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(EmailMessage.subject.like(like), EmailMessage.snippet.like(like), EmailMessage.from_addr.like(like))
        )
    # 不能直接对 ORM select 使用 with_only_columns(count(*))，否则在 SQLite 下可能丢失 FROM，
    # 进而把总数错误算成 1。这里显式对子查询计数，确保过滤条件和数据查询完全对齐。
    filtered_subquery = query.order_by(None).subquery()
    total = db.execute(select(func.count()).select_from(filtered_subquery)).scalar() or 0
    # SQLite 不支持 NULLS LAST 语法，这里用 CASE 将 NULL 置后
    order_nulls_last = case((EmailMessage.sent_at == None, 1), else_=0)  # noqa: E711
    rows = (
        db.execute(
            query.order_by(order_nulls_last.asc(), desc(EmailMessage.sent_at)).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    # 兼容旧前端：如果存在 summary/summary_full，则在响应中填充 key_info 和 key_info_origin
    def _compose_display_summary(d: dict | None) -> str:
        try:
            if not isinstance(d, dict):
                return ""
            num = (d.get("meeting_number") or "").strip()
            plat = (d.get("platform") or "").strip()
            # 展示策略（看齐微信）：会议 + 号 + 小模型摘要
            # - 优先使用工具摘要（去掉 ai:/fallback: 前缀），否则用 key_info
            # - 左侧展示会议信息：会议 <平台?> <会议号?>
            raw_sum = (d.get("summary") or "").strip()
            clean_sum = raw_sum
            if clean_sum:
                # 去掉前缀，仅用于展示
                import re as _re
                clean_sum = _re.sub(r"^\s*(ai:|fallback:)\s*", "", clean_sum, flags=_re.IGNORECASE).strip()
            key = clean_sum or (d.get("key_info") or "").strip()
            left_parts = []
            if num or plat:
                label = "会议"
                if plat:
                    label += f" {plat}"
                if num:
                    label += f" {num}"
                left_parts.append(label)
            left = " ".join(left_parts).strip()
            if key:
                return f"{left} | {key}" if left else key
            return left
        except Exception:
            return ""

    items: list[EmailMessageOut] = []
    for r in rows:
        out = EmailMessageOut.model_validate(r)
        d = dict(out.derived or {})
        # 前端旧逻辑优先读取 key_info；我们用新的字段回填
        if (d.get("summary_full") or d.get("summary")) and not d.get("key_info"):
            d["key_info"] = d.get("summary_full") or d.get("summary") or ""
        if d.get("summary_origin") and not d.get("key_info_origin"):
            d["key_info_origin"] = d.get("summary_origin")
        d["display_summary"] = _compose_display_summary(d)
        # 确保类型为 dict（pydantic 模型允许赋值）
        out.derived = d
        if not include_bodies:
            out.body_text = None
            out.body_html = None
        items.append(out)
    return {"total": int(total), "items": items}


@router.get("/messages/{message_id}", response_model=EmailMessageOut)
def get_email_message(message_id: int, db: Session = Depends(get_db)):
    row = db.get(EmailMessage, message_id)
    if not row:
        raise HTTPException(404, "message not found")
    return EmailMessageOut.model_validate(row)


@router.post("/features")
def derive_email_features(payload: dict, db: Session = Depends(get_db)):
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(400, "invalid payload: items must be list")
    features = build_email_features(items)
    # 兼容前端：填充 key_info/key_info_origin，保持与 summary/summary_origin 一致
    compat = {}
    for k, f in (features or {}).items():
        if not isinstance(f, dict):
            compat[k] = f
            continue
        g = dict(f)
        if (g.get("summary_full") or g.get("summary")) and not g.get("key_info"):
            g["key_info"] = g.get("summary_full") or g.get("summary") or ""
        if g.get("summary_origin") and not g.get("key_info_origin"):
            g["key_info_origin"] = g.get("summary_origin")
        compat[k] = g
    features = compat
    if payload.get("persist", True):
        ids = [int(it.get("id")) for it in items if it.get("id") is not None]
        if ids:
            rows = db.execute(select(EmailMessage).where(EmailMessage.id.in_(ids))).scalars().all()
            persist_email_features(db, rows, precomputed=features, force=True, commit=True)
    return {"features": features}


@router.post("/derive")
def derive_email_messages(payload: dict, progress_key: str | None = None, db: Session = Depends(get_db)):
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(400, "ids is required")
    try:
        id_list = [int(i) for i in ids]
    except Exception:
        raise HTTPException(400, "invalid ids")

    # progress path (chunked)
    if progress_key:
        ids2 = list(dict.fromkeys(id_list))
        EMAIL_PROGRESS[progress_key] = {"status": "running", "total": len(ids2), "done": 0}
        bs = max(10, min(200, int(payload.get("batch_size", 50))))
        done = 0
        errs: list[str] = []
        for i in range(0, len(ids2), bs):
            chunk = ids2[i:i+bs]
            rows = db.execute(select(EmailMessage).where(EmailMessage.id.in_(chunk))).scalars().all()
            try:
                persist_email_features(db, rows, force=bool(payload.get("force", False)), commit=True)
            except Exception as e:
                errs.append(str(e))
            done = min(len(ids2), i + len(chunk))
            EMAIL_PROGRESS[progress_key]["done"] = done
        EMAIL_PROGRESS[progress_key]["status"] = "done"
        return {"status": "ok", "updated": done, "errors": errs[:50], "progress_key": progress_key}

    # non-progress path (single batch)
    rows = db.execute(select(EmailMessage).where(EmailMessage.id.in_(id_list))).scalars().all()
    features = persist_email_features(db, rows, force=bool(payload.get("force", False)), commit=True)
    # readback for debug visibility
    readback: list[dict] = []
    try:
        rws = db.execute(select(EmailMessage.id, EmailMessage.derived).where(EmailMessage.id.in_(id_list))).all()
        for rid, derv in rws:
            readback.append({
                "id": int(rid),
                "summary_origin": (derv or {}).get("summary_origin") if isinstance(derv, dict) else None,
                "has_ai": bool(isinstance(derv, dict) and isinstance(derv.get("summary"), str) and derv.get("summary"," ").lower().strip().startswith("ai:")),
            })
    except Exception:
        pass
    # 兼容前端：填充 key_info/key_info_origin 字段
    compat = {}
    for k, f in (features or {}).items():
        if not isinstance(f, dict):
            compat[k] = f
            continue
        g = dict(f)
        if (g.get("summary_full") or g.get("summary")) and not g.get("key_info"):
            g["key_info"] = g.get("summary_full") or g.get("summary") or ""
        if g.get("summary_origin") and not g.get("key_info_origin"):
            g["key_info_origin"] = g.get("summary_origin")
        compat[k] = g
    return {"status": "ok", "processed": len(rows), "features": compat, "debug_readback": readback[:50]}


@router.post("/derive/latest")
def derive_latest_emails(limit: int = 10, db: Session = Depends(get_db)):
    """强制对最新 N 封邮件重新生成小模型摘要（覆盖旧的 fallback/tool 结果）。"""
    try:
        limit = max(1, min(200, int(limit)))
    except Exception:
        limit = 10
    # SQLite 无 NULLS LAST，使用 CASE 将 NULL 置后
    order_nulls_last = case((EmailMessage.sent_at == None, 1), else_=0)  # noqa: E711
    rows = (
        db.execute(select(EmailMessage).order_by(order_nulls_last.asc(), desc(EmailMessage.sent_at)).limit(limit))
        .scalars()
        .all()
    )
    from ..services.email_features import persist_email_features
    features = persist_email_features(db, rows, force=True, commit=True)
    # 返回简要结果
    out = []
    for em in rows:
        d = em.derived if isinstance(em.derived, dict) else {}
        out.append({
            "id": em.id,
            "subject": em.subject,
            "summary_origin": (d or {}).get("summary_origin"),
            "has_ai": bool(isinstance(d, dict) and isinstance(d.get("summary"), str) and d.get("summary"," ").lower().strip().startswith("ai:")),
        })
    return {"status": "ok", "processed": len(out), "items": out}


@router.get("/derive/progress")
def email_derive_progress(key: str):
    info = EMAIL_PROGRESS.get(key)
    if not info:
        return {"status": "unknown", "done": 0, "total": 0}
    return {"status": info.get("status"), "done": info.get("done"), "total": info.get("total")}

@router.post("/messages/{message_id}/reply")
def reply_email_message(message_id: int, body: EmailReplyRequest, db: Session = Depends(get_db)):
    row = db.get(EmailMessage, message_id)
    if not row:
        raise HTTPException(404, "message not found")
    acc = db.get(EmailAccount, row.account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    to_addr = _parse_email_address(row.from_addr if str(row.direction or "in") == "in" else ((row.to_addrs or [""])[0] if row.to_addrs else ""))
    if not to_addr:
        raise HTTPException(400, "reply target is empty")
    text = str(body.body_text or "").strip()
    if not text:
        raise HTTPException(400, "body_text is required")
    try:
        resp = smtp_send(
            db,
            acc,
            [to_addr],
            _normalize_reply_subject(body.subject or row.subject),
            text,
            cc=body.cc,
            bcc=body.bcc,
        )
        db.commit()
        return {"status": "ok", "to": to_addr, "account_id": acc.id, "resp": resp}
    except Exception as e:
        db.rollback()
        raise HTTPException(502, f"reply error: {e}")


@router.post("/send")
def send_email(body: EmailSendRequest, db: Session = Depends(get_db)):
    acc = db.get(EmailAccount, body.account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    try:
        # Microsoft OAuth/Graph 已移除：统一走 SMTP 发送（或由用户自行配置 IMAP/SMTP / 应用专用密码）。
        resp = smtp_send(db, acc, body.to, body.subject, body.body_text, cc=body.cc, bcc=body.bcc)
        db.commit()
        return resp
    except Exception as e:
        db.rollback()
        raise HTTPException(502, f"send error: {e}")
