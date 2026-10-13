from __future__ import annotations

import requests
from typing import Optional
from ..config import settings


class ChatlogClient:
    def __init__(self, base: Optional[str] = None):
        self.base = (base or settings.CHATLOG_HTTP_BASE or "").rstrip("/")

    def get_sessions(self):
        url = f"{self.base}/api/v1/sessions"
        r = requests.get(
            url,
            params={"limit": "500"},
            timeout=settings.CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        # Some builds return plain text instead of JSON
        ctype = r.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            try:
                return r.json()
            except Exception:
                pass
        return r.text

    def get_chatlog(self, time_range: str, talker: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None):
        if not talker:
            return {"messages": []}
        params = {"time": time_range, "chat": talker}
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        url = f"{self.base}/api/v1/history"
        r = requests.get(url, params=params, timeout=settings.CHATLOG_HTTP_TIMEOUT_SECONDS)
        # Some versions return 400 for range queries; try fallback to single day for end date
        if r.status_code == 400 and "~" in time_range:
            # try split and query each day will be handled at higher level; here just raise
            r.raise_for_status()
        r.raise_for_status()
        payload = r.json()
        return self._normalize_history(payload, talker=talker)

    @staticmethod
    def _normalize_history(payload, *, talker: str):
        if not isinstance(payload, dict):
            return payload
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return payload
        normalized = []
        username = str(payload.get("username") or talker)
        talker_name = str(payload.get("chat") or username)
        is_chatroom = bool(payload.get("is_group"))
        for item in messages:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["talker"] = username
            row["talkerName"] = talker_name
            row["isChatRoom"] = is_chatroom
            row["isSelf"] = bool(row.get("is_self"))
            row["senderName"] = row.get("sender")
            row["sender"] = row.get("sender_id") or row.get("sender")
            if row.get("media_url") and not row.get("contents"):
                row["contents"] = {"url": row["media_url"]}
            normalized.append(row)
        result = dict(payload)
        result["messages"] = normalized
        return result

    @staticmethod
    def extract_talker_ids(session_payload) -> list[str]:
        talkers: set[str] = set()
        # JSON shape
        if isinstance(session_payload, (list, tuple)):
            for it in session_payload:
                if isinstance(it, dict):
                    for key in ("talker", "username", "id", "wxid", "chat_id"):
                        v = it.get(key)
                        if isinstance(v, str) and v:
                            talkers.add(v)
                            break
            return list(talkers)
        if isinstance(session_payload, dict):
            items = (
                session_payload.get("sessions")
                or session_payload.get("items")
                or session_payload.get("data")
                or []
            )
            for it in items:
                if isinstance(it, dict):
                    for key in ("talker", "username", "id", "wxid", "chat_id"):
                        v = it.get(key)
                        if isinstance(v, str) and v:
                            talkers.add(v)
                            break
            return list(talkers)
        # Plain text format: lines like "Name(wxid@chatroom) time"
        if isinstance(session_payload, str):
            import re
            pattern = re.compile(r"\(([^)]+)\)")
            for line in session_payload.splitlines():
                m = pattern.search(line)
                if m:
                    talkers.add(m.group(1))
            return list(talkers)
        return []
