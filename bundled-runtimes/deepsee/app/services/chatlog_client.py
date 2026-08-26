from __future__ import annotations

import requests
from typing import Optional
from ..config import settings


class ChatlogClient:
    def __init__(self, base: Optional[str] = None):
        self.base = (base or settings.CHATLOG_HTTP_BASE or "").rstrip("/")

    def get_sessions(self):
        url = f"{self.base}/api/v1/session"
        r = requests.get(url, timeout=settings.CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS)
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
        # Some chatlog builds may require single-day query. Accept 'YYYY-MM-DD' or 'YYYY-MM-DD~YYYY-MM-DD'.
        params = {"time": time_range, "format": "json"}
        if talker:
            params["talker"] = talker
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        url = f"{self.base}/api/v1/chatlog"
        r = requests.get(url, params=params, timeout=settings.CHATLOG_HTTP_TIMEOUT_SECONDS)
        # Some versions return 400 for range queries; try fallback to single day for end date
        if r.status_code == 400 and "~" in time_range:
            # try split and query each day will be handled at higher level; here just raise
            r.raise_for_status()
        r.raise_for_status()
        return r.json()

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
            items = session_payload.get("items") or session_payload.get("data") or []
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
