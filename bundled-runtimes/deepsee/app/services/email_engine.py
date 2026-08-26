from __future__ import annotations

"""Minimal email engine for multi-account receive/send.

Design goals:
- IMAP fetch (default) for inbound; POP3 could be added later.
- SMTP send with SSL/TLS; support login auth.
- Store lightweight message rows to DB; avoid large bodies/attachments for now.
- Idempotent fetch via Message UID/Message-ID tracking.
"""

from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, getaddresses
import imaplib
import os
import smtplib
import ssl
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EmailAccount, EmailMessage
from .email_features import persist_email_features, persist_email_fallback
import threading


def _decode(s: str | bytes | None) -> str | None:
    if s is None:
        return None
    try:
        if isinstance(s, bytes):
            return str(make_header(decode_header(s)))
        return str(make_header(decode_header(s)))
    except Exception:
        return s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else s


def _addr_list(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        pairs = getaddresses([raw])
        addrs = []
        for name, addr in pairs:
            if name:
                name = str(make_header(decode_header(name)))
                addrs.append(f"{name} <{addr}>")
            else:
                addrs.append(addr)
        return addrs
    except Exception:
        return [raw]


EMAIL_CONNECT_TIMEOUT_SECONDS = max(3, int(os.getenv("EMAIL_CONNECT_TIMEOUT_SECONDS", "8")))
EMAIL_POP3_TIMEOUT_SECONDS = max(3, int(os.getenv("EMAIL_POP3_TIMEOUT_SECONDS", "8")))


@dataclass
class FetchOptions:
    folder: str = "INBOX"
    limit: int = 100
    unseen_only: bool = False


def imap_fetch(db: Session, account: EmailAccount, opts: FetchOptions | None = None) -> int:
    """Fetch latest emails into the DB. Returns number of new rows inserted.

    Strategy:
    - IMAP SEARCH to get recent UIDs (unseen or all, up to limit*2 as buffer)
    - FETCH BODY.PEEK[HEADER] and optionally small TEXT part to build snippet.
    - Deduplicate by (account_id, external_id [UID]) if available; fallback to Message-ID.
    """

    opts = opts or FetchOptions()
    context = ssl.create_default_context()
    new_count = 0
    new_rows: List[EmailMessage] = []

    if account.imap_ssl:
        M = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, ssl_context=context, timeout=EMAIL_CONNECT_TIMEOUT_SECONDS)
    else:
        M = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=EMAIL_CONNECT_TIMEOUT_SECONDS)

    try:
        username = (account.auth or {}).get("username") or account.email_address
        password = (account.auth or {}).get("password") or ""
        M.login(username, password)
        # ensure a selectable mailbox is selected; fallback to INBOX
        try:
            typ, _ = M.select(opts.folder)
            if typ != "OK":
                typ, _ = M.select("INBOX")
                if typ != "OK":
                    raise RuntimeError("IMAP select mailbox failed")
        except Exception:
            # force close and re-raise to trigger POP3 fallback upstream
            try:
                M.logout()
            except Exception:
                pass
            raise

        criteria = "UNSEEN" if opts.unseen_only else "ALL"
        typ, data = M.search(None, criteria)
        if typ != "OK":
            return 0
        uids = data[0].split() if data and data[0] else []
        uids = uids[-(opts.limit * 2) :]

        # Build existing uid set to skip duplicates
        existing: set[str] = set(
            x[0]
            for x in db.execute(
                select(EmailMessage.external_id).where(EmailMessage.account_id == account.id)
            ).all()
            if x[0]
        )

        for uid in reversed(uids):  # newest first
            uid_s = uid.decode() if isinstance(uid, (bytes, bytearray)) else str(uid)
            if uid_s in existing:
                continue
            typ, msgdata = M.fetch(uid, "(RFC822)")
            if typ != "OK" or not msgdata:
                continue
            raw = msgdata[0][1]
            if not raw:
                continue
            try:
                em = message_from_bytes(raw)
            except Exception:
                continue

            subject = _decode(em.get("Subject"))
            from_raw = em.get("From")
            to_raw = em.get("To")
            cc_raw = em.get("Cc")
            date_hdr = em.get("Date")
            msg_id_hdr = em.get("Message-ID")

            sent_at = None
            try:
                if date_hdr:
                    sent_at = parsedate_to_datetime(date_hdr)
            except Exception:
                sent_at = None

            # Extract best-effort plain text for snippet
            body_text = None
            body_html = None
            try:
                if em.is_multipart():
                    for part in em.walk():
                        ctype = part.get_content_type()
                        disp = part.get("Content-Disposition", "") or ""
                        if ctype == "text/plain" and "attachment" not in disp:
                            body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                            break
                        if ctype == "text/html" and "attachment" not in disp and not body_html:
                            body_html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                else:
                    payload = em.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(em.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                pass

            snippet = (body_text or "" ).strip().replace("\r", " ").replace("\n", " ")[:400]

            row = EmailMessage(
                account_id=account.id,
                external_id=uid_s or (msg_id_hdr or None),
                thread_id=None,
                subject=subject,
                from_addr=_addr_list(from_raw)[0] if _addr_list(from_raw) else from_raw,
                to_addrs=_addr_list(to_raw),
                cc_addrs=_addr_list(cc_raw),
                bcc_addrs=None,
                sent_at=sent_at,
                direction="in",
                snippet=snippet,
                body_text=(body_text or None),
                body_html=(body_html or None),
                flags=["seen"] if ("Seen" in (msgdata[0][0].decode(errors="ignore") if isinstance(msgdata[0][0], (bytes, bytearray)) else "")) else None,
                meta={"message_id": msg_id_hdr} if msg_id_hdr else None,
            )

            db.add(row)
            db.flush()
            new_rows.append(row)
            new_count += 1

    finally:
        try:
            M.logout()
        except Exception:
            pass

    # First persist local fallback summaries for instant UI (for any new rows)
    overlay_ids: list[int] = []
    if new_rows:
        try:
            persist_email_fallback(db, new_rows, force=True, commit=True)
        except Exception as feature_err:
            print(f"[email_engine] persist fallback failed: {feature_err}")
        overlay_ids.extend([r.id for r in new_rows if getattr(r, 'id', None) is not None])

    # Always schedule a small overlay window for recent messages that still lack tool results,
    # so clicking "同步" 可以修复之前遗漏的邮件（增量覆盖）。允许在“功能设置”中关闭或调整窗口大小。
    try:
        # Read runtime switches from SyncState
        from ..models import SyncState
        ai_switch = db.get(SyncState, "ai_runtime")
        import json as _json
        cfg = {}
        try:
            if ai_switch and ai_switch.value:
                cfg = _json.loads(ai_switch.value) or {}
        except Exception:
            cfg = {}
        enable_overlay = bool((cfg or {}).get("enable_email_tool_overlay", True))
        win = int((cfg or {}).get("email_overlay_window", 120))
        cap = int((cfg or {}).get("email_overlay_cap", 160))
        if win <= 0 or cap <= 0:
            enable_overlay = False
        if not enable_overlay:
            overlay_ids = overlay_ids  # no-op; skip building recent window
            raise RuntimeError("overlay_disabled")
        from sqlalchemy import desc as _desc
        recent = (
            db.execute(
                select(EmailMessage)
                .where(EmailMessage.account_id == account.id)
                .order_by(_desc(EmailMessage.sent_at), _desc(EmailMessage.id))
                .limit(max(20, min(1000, win)))
            )
            .scalars()
            .all()
        )
        for em in recent:
            d = em.derived if isinstance(em.derived, dict) else {}
            if str(d.get('summary_origin') or '').lower() != 'tool':
                if getattr(em, 'id', None) is not None:
                    overlay_ids.append(int(em.id))
        # de-dup and cap to a safe size to avoid bursts
        seen: set[int] = set()
        capped: list[int] = []
        for i in overlay_ids:
            if i not in seen:
                seen.add(i)
                capped.append(i)
            if len(capped) >= max(20, min(2000, cap)):
                break
        overlay_ids = capped
    except Exception:
        pass

    if overlay_ids:
        def _run_ai_overlay(ids: list[int]):
            sess = None
            try:
                from ..db import SessionLocal as _SessionLocal
                sess = _SessionLocal()
                rows = sess.execute(select(EmailMessage).where(EmailMessage.id.in_(ids))).scalars().all()
                # force=False：仅对缺失/非tool 的项进行覆盖；已是 tool 的将被跳过
                persist_email_features(sess, rows, force=False, commit=True)
            except Exception as e:
                print(f"[email_engine] async ai overlay failed: {e}")
            finally:
                try:
                    if sess:
                        sess.close()
                except Exception:
                    pass
        try:
            t = threading.Thread(target=_run_ai_overlay, args=(overlay_ids,), daemon=True)
            t.start()
        except Exception:
            # fallback to sync if thread creation fails
            try:
                rows = db.execute(select(EmailMessage).where(EmailMessage.id.in_(overlay_ids))).scalars().all()
                persist_email_features(db, rows, force=False, commit=True)
            except Exception as feature_err:
                print(f"[email_engine] persist features failed: {feature_err}")

    return new_count


def smtp_send(db: Session, account: EmailAccount, to: list[str], subject: str, body_text: str, cc: Optional[list[str]] = None, bcc: Optional[list[str]] = None) -> dict:
    """Send a simple plain-text email via SMTP.

    Returns a summary dict; also persists an outgoing EmailMessage row.
    """

    from email.message import EmailMessage as PyEmailMessage

    msg = PyEmailMessage()
    msg["From"] = f"{account.name} <{account.email_address}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.set_content(body_text)

    username = (account.auth or {}).get("username") or account.email_address
    password = (account.auth or {}).get("password") or ""

    if account.smtp_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, context=context) as s:
            s.login(username, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(account.smtp_host, account.smtp_port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(username, password)
            s.send_message(msg)

    row = EmailMessage(
        account_id=account.id,
        external_id=None,
        thread_id=None,
        subject=subject,
        from_addr=f"{account.name} <{account.email_address}>",
        to_addrs=to,
        cc_addrs=cc,
        bcc_addrs=bcc,
        sent_at=None,
        direction="out",
        snippet=body_text[:400],
        body_text=body_text,
        body_html=None,
        flags=["sent"],
        meta=None,
    )
    db.add(row)
    db.flush()
    try:
        # immediate fallback, then async overlay
        persist_email_fallback(db, [row], force=True, commit=True)
        try:
            t = threading.Thread(target=lambda: persist_email_features(db, [row], force=True, commit=True), daemon=True)
            t.start()
        except Exception:
            # if thread fails, do sync
            persist_email_features(db, [row], force=True, commit=True)
    except Exception as feature_err:
        print(f"[email_engine] persist features failed: {feature_err}")

    return {"status": "ok", "message_id": row.id}


# --------- POP3 (fallback) ---------
import poplib

def pop3_fetch(db: Session, account: EmailAccount, limit: int = 50) -> int:
    """Fallback fetch using POP3 when IMAP is unavailable.

    For Outlook/Hotmail, host is usually 'pop-mail.outlook.com', port 995 (SSL).
    This fetches top-N messages (most recent IDs), retrieves headers and a small
    portion of the body for snippet.
    """
    base_host = (account.imap_host or '').lower()
    # Try multiple common POP hosts for Outlook
    candidates: list[tuple[str,int]] = []
    if 'outlook.' in base_host or 'office365.com' in base_host:
        candidates = [
            ('pop-mail.outlook.com', 995),
            ('outlook.office365.com', 995),
        ]
    if not candidates:
        cands: list[tuple[str,int]] = []
        if base_host.startswith('imap.'):
            cands.append((base_host.replace('imap.', 'pop.', 1), 995))
        # also try plain pop.<domain> if not already covered
        if base_host and not base_host.startswith('pop.'):
            domain = base_host.split('imap.',1)[-1] if base_host.startswith('imap.') else base_host
            cands.append((f'pop.{domain}', 995))
        # final fallback to original host (might be actual pop)
        cands.append((base_host or 'pop-mail.outlook.com', 995))
        candidates = cands

    username = (account.auth or {}).get("username") or account.email_address
    password = (account.auth or {}).get("password") or ""

    new_count = 0
    server = None
    new_rows: List[EmailMessage] = []
    try:
        last_err: Exception | None = None
        for host, port in candidates:
            try:
                server = poplib.POP3_SSL(host, port, timeout=EMAIL_POP3_TIMEOUT_SECONDS)
                server.user(username)
                server.pass_(password)
                break
            except Exception as e:
                last_err = e
                server = None
        if not server:
            raise last_err or RuntimeError('POP3 connect failed')
        num_messages = len(server.list()[1])
        start = max(1, num_messages - limit + 1)

        # Build existing ext ids as 'pop-<msgno>' to dedupe
        existing = set(
            x[0]
            for x in db.execute(
                select(EmailMessage.external_id).where(EmailMessage.account_id == account.id)
            ).all()
            if x[0]
        )

        for i in range(num_messages, start - 1, -1):
            ext_id = f"pop-{i}"
            if ext_id in existing:
                continue
            # TOP command: headers + first N lines of body
            try:
                resp, lines, octets = server.top(i, 50)
            except Exception:
                continue
            data = b"\r\n".join(lines)
            try:
                em = message_from_bytes(data)
            except Exception:
                continue
            subject = _decode(em.get("Subject"))
            from_raw = em.get("From")
            date_hdr = em.get("Date")
            sent_at = None
            try:
                if date_hdr:
                    sent_at = parsedate_to_datetime(date_hdr)
            except Exception:
                pass
            snippet = None
            try:
                if em.is_multipart():
                    for part in em.walk():
                        ctype = part.get_content_type()
                        disp = part.get("Content-Disposition", "") or ""
                        if ctype == "text/plain" and "attachment" not in disp:
                            snippet = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                            break
                else:
                    payload = em.get_payload(decode=True)
                    if payload:
                        snippet = payload.decode(em.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                pass
            snippet = (snippet or "").strip().replace("\r"," ").replace("\n"," ")[:400]
            row = EmailMessage(
                account_id=account.id,
                external_id=ext_id,
                subject=subject,
                from_addr=_addr_list(from_raw)[0] if _addr_list(from_raw) else from_raw,
                sent_at=sent_at,
                direction="in",
                snippet=snippet,
                body_text=None,
            )
            db.add(row)
            db.flush()
            new_rows.append(row)
            new_count += 1
        if new_rows:
            try:
                persist_email_features(db, new_rows, force=True, commit=True)
            except Exception as feature_err:
                print(f"[email_engine] persist features failed: {feature_err}")
        return new_count
    finally:
        try:
            if server:
                server.quit()
        except Exception:
            pass
