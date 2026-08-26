from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Iterable


DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.getcwd(), "data", "wechat8061_backup.db"))


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
    except Exception:
        pass
    return conn


def ensure_schema(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wx_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  wxid TEXT NOT NULL,
                  msg_id TEXT NOT NULL,
                  msg_type INTEGER,
                  timestamp TEXT,
                  sender_id TEXT,
                  sender_nickname TEXT,
                  content TEXT,
                  raw_json TEXT,
                  source TEXT,
                  received_at TEXT NOT NULL,
                  UNIQUE(wxid, msg_id) ON CONFLICT IGNORE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wx_messages_timestamp ON wx_messages(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wx_messages_received_at ON wx_messages(received_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wx_messages_sender_id ON wx_messages(sender_id)")
    finally:
        conn.close()


def insert_messages(records: Iterable[dict[str, Any]], *, db_path: str = DEFAULT_DB_PATH) -> int:
    """Insert normalized message records into backup DB.

    Each record should contain:
      - wxid (str), msg_id (str)
      - msg_type (int|None), timestamp (str|None)
      - sender_id/sender_nickname/content/raw_json/source (optional)
    """
    ensure_schema(db_path)
    rows = []
    received_at = datetime.utcnow().isoformat(timespec="seconds")
    for rec in records:
        wxid = str(rec.get("wxid") or "").strip()
        msg_id = str(rec.get("msg_id") or "").strip()
        if not wxid or not msg_id:
            continue
        try:
            msg_type = rec.get("msg_type")
            msg_type_i = int(msg_type) if msg_type is not None else None
        except Exception:
            msg_type_i = None
        rows.append(
            (
                wxid,
                msg_id,
                msg_type_i,
                rec.get("timestamp"),
                rec.get("sender_id"),
                rec.get("sender_nickname"),
                rec.get("content"),
                rec.get("raw_json"),
                rec.get("source"),
                received_at,
            )
        )
    if not rows:
        return 0
    conn = _connect(db_path)
    try:
        before = conn.total_changes
        with conn:
            conn.executemany(
                """
                INSERT INTO wx_messages (
                    wxid, msg_id, msg_type, timestamp, sender_id, sender_nickname, content, raw_json, source, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return max(0, conn.total_changes - before)
    finally:
        conn.close()


def list_messages(
    *,
    wxid: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_schema(db_path)
    page = max(1, int(page or 1))
    size = max(1, min(500, int(size or 50)))
    offset = (page - 1) * size

    clauses: list[str] = []
    params: list[Any] = []
    if wxid:
        clauses.append("wxid = ?")
        params.append(wxid)
    if q:
        clauses.append("(content LIKE ? OR sender_nickname LIKE ? OR sender_id LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    conn = _connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(1) AS cnt FROM wx_messages {where_sql}", params).fetchone()["cnt"]
        rows = conn.execute(
            f"""
            SELECT id, wxid, msg_id, msg_type, timestamp, sender_id, sender_nickname, content, source, received_at
            FROM wx_messages
            {where_sql}
            ORDER BY received_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [size, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
        return {"total": int(total or 0), "items": items}
    finally:
        conn.close()

