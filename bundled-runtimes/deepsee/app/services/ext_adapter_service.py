from __future__ import annotations

"""External adapter ingestion service.

This module monitors a configured directory of adapter logs (e.g., produced by langbot
adapters) and imports messages into the DB. Each adapter can specify a subdirectory or
explicit log file path. We expect either:
- JSON Lines (*.jsonl) where each line is a JSON object
- Simple log lines with a leading JSON object {...}

Minimal expected JSON fields per line:
  { "id": str|int, "chat_id": str, "sender": str, "text": str, "timestamp": ISO8601|epoch, "direction": "in"|"out" }

Unknown shapes are skipped gracefully.
"""

import json
import hashlib
import os
import re
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExtAdapter, AdapterMessage


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s or "")


def _fallback_external_id(adapter_key: str, obj: dict) -> str | None:
    """Build a stable synthetic id when source doesn't provide one.

    This prevents repeated ingestion of the same log lines when `id` is missing.
    """
    try:
        chat_id = str(obj.get("chat_id") or "")
        sender = str(obj.get("sender") or "")
        ts = obj.get("timestamp")
        text = str(obj.get("text") or obj.get("content") or "")
        if not (chat_id or sender or ts or text):
            return None
        raw = json.dumps(
            {"k": adapter_key, "c": chat_id, "s": sender, "t": ts, "x": text},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        return f"h:{h}"
    except Exception:
        return None


def _to_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v)
        except Exception:
            return None
    if isinstance(v, str):
        try:
            if v.endswith("Z"):
                v = v.replace("Z", "+00:00")
            return datetime.fromisoformat(v)
        except Exception:
            return None
    return None


def _parse_json_from_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    # best-effort: find first '{' and parse
    try:
        idx = line.find("{")
        if idx >= 0:
            return json.loads(line[idx:])
    except Exception:
        return None
    return None


def _parse_langbot_log_datetime(line: str, *, default_year: int | None = None) -> datetime | None:
    """Parse LangBot log prefix like: [12-29 20:52:37.781] ... (no year)."""
    try:
        s = _strip_ansi(line)
        m = re.search(r"\[(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\]", s)
        if not m:
            return None
        month, day, hh, mm, ss = (int(m.group(i)) for i in range(1, 6))
        year = int(default_year) if default_year else datetime.now().year
        return datetime(year, month, day, hh, mm, ss)
    except Exception:
        return None


def _iter_langbot_runtime_log(
    path: str, *, year_hint: int | None = None, since: datetime | None = None
) -> Iterable[dict]:
    """Yield message-like dicts parsed from LangBot runtime logs.

    Supports at least:
    - process.py: "Processing request from <session> (<conv>): <text>"
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = _strip_ansi(raw_line).strip()
                if not line:
                    continue
                if "Processing request from " not in line:
                    continue
                m = re.search(r"Processing request from (.+?) \((\d+)\):\s*(.*)$", line)
                if not m:
                    continue
                session_id = (m.group(1) or "").strip()
                conv_id = (m.group(2) or "").strip()
                text = (m.group(3) or "").strip()
                if not session_id or not text:
                    continue
                ts = _parse_langbot_log_datetime(line, default_year=year_hint)
                if not ts:
                    ts = datetime.now()
                if since and ts < since:
                    continue
                sender = session_id
                if session_id.startswith("person_"):
                    sender = session_id[len("person_") :].strip() or session_id
                ext_id = f"lb:req:{conv_id}:{int(ts.timestamp())}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"
                yield {
                    "id": ext_id,
                    "chat_id": session_id,
                    "sender": sender,
                    "timestamp": ts.isoformat(),
                    "direction": "in",
                    "text": text,
                    "conv_id": conv_id,
                    "source": "langbot_runtime_log",
                    "talker_name": session_id,
                    "sender_name": sender,
                    "line": line[:3000],
                }
    except Exception:
        return []


def _iter_log_json(path: str) -> Iterable[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                obj = _parse_json_from_line(line)
                if obj:
                    yield obj
    except Exception:
        return []


def _iter_adapter_sources(base_dir: str, adapter_key: str) -> list[str]:
    sources: list[str] = []
    sub = os.path.join(base_dir, adapter_key)
    if os.path.isdir(sub):
        # prefer *.jsonl; fallback *.log
        for fn in sorted(os.listdir(sub)):
            if fn.endswith(".jsonl") or fn.endswith(".log"):
                sources.append(os.path.join(sub, fn))
    else:
        # maybe a single file named <key>.jsonl/log under base_dir
        for ext in (".jsonl", ".log"):
            p = os.path.join(base_dir, adapter_key + ext)
            if os.path.exists(p):
                sources.append(p)
        # Special: LangBot runtime logs are typically rotated as `langbot-YYYY-MM-DD.log`
        if not sources and os.path.isdir(base_dir) and adapter_key in {"langbot", "langbot_runtime"}:
            for fn in sorted(os.listdir(base_dir)):
                if fn.startswith("langbot-") and fn.endswith(".log"):
                    sources.append(os.path.join(base_dir, fn))
    return sources


def ingest_adapter_logs(db: Session, adapter: ExtAdapter, base_dir: str, since: datetime | None = None) -> int:
    """Ingest messages from adapter logs. Returns number of new rows.

    Deduplication is by (adapter_key, external_id) when available, else a stable synthetic
    hash id based on (chat_id, sender, timestamp, text).
    """

    total_new = 0
    sources = _iter_adapter_sources(base_dir, adapter.key)
    if not sources:
        return 0

    seen_ids: set[str] = set(
        x[0]
        for x in db.execute(
            select(AdapterMessage.external_id).where(AdapterMessage.adapter_key == adapter.key)
        ).all()
        if x[0]
    )

    # Reduce scan range for LangBot rotated logs
    if since and adapter.key in {"langbot", "langbot_runtime"}:
        filtered: list[str] = []
        min_date = (since - timedelta(days=1)).date()
        for p in sources:
            bn = os.path.basename(p)
            m = re.search(r"langbot-(\d{4})-(\d{2})-(\d{2})\.log$", bn)
            if not m:
                filtered.append(p)
                continue
            try:
                y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if datetime(y, mo, da).date() >= min_date:
                    filtered.append(p)
            except Exception:
                filtered.append(p)
        sources = filtered or sources

    for path in sources:
        it: Iterable[dict]
        if adapter.key in {"langbot", "langbot_runtime"} and path.endswith(".log"):
            # Try to derive year from filename `langbot-YYYY-MM-DD.log`
            year_hint = None
            try:
                bn = os.path.basename(path)
                m = re.search(r"langbot-(\d{4})-\d{2}-\d{2}\.log$", bn)
                if m:
                    year_hint = int(m.group(1))
            except Exception:
                year_hint = None
            it = _iter_langbot_runtime_log(path, year_hint=year_hint, since=since)
        else:
            it = _iter_log_json(path)
        for obj in it:
            ext_id = str(obj.get("id")) if obj.get("id") is not None else None
            if not ext_id:
                ext_id = _fallback_external_id(adapter.key, obj)
            if ext_id and ext_id in seen_ids:
                continue
            ts = _to_dt(obj.get("timestamp"))
            if since and ts and ts < since:
                continue
            msg = AdapterMessage(
                adapter_key=adapter.key,
                external_id=ext_id,
                chat_id=str(obj.get("chat_id") or ""),
                sender=str(obj.get("sender") or ""),
                timestamp=ts,
                direction=str(obj.get("direction") or "in"),
                content_text=str(obj.get("text") or obj.get("content") or ""),
                meta={k: v for k, v in obj.items() if k not in {"id", "chat_id", "sender", "timestamp", "direction", "text", "content"}},
            )
            db.add(msg)
            total_new += 1
            if ext_id:
                seen_ids.add(ext_id)

    return total_new
