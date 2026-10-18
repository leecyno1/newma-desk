from __future__ import annotations

import requests
from datetime import datetime
import hashlib
import re
from typing import Optional
from ..config import settings


class ChatlogClient:
    def __init__(self, base: Optional[str] = None):
        self.base = (base or settings.CHATLOG_HTTP_BASE or "").rstrip("/")

    def get_sessions(self, offset: int = 0):
        url = f"{self.base}/api/v1/sessions"
        r = requests.get(
            url,
            params={"limit": "500", "offset": str(offset)},
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

    def get_all_sessions(self) -> list[dict]:
        sessions = []
        seen = set()
        offset = 0
        while True:
            payload = self.get_sessions(offset=offset)
            if not isinstance(payload, dict) or not isinstance(payload.get("sessions"), list):
                raise ValueError("Chatlog must return paginated sessions for history import")
            rows = payload["sessions"]
            for row in rows:
                identifier = row.get("username")
                if identifier in seen:
                    raise ValueError("Chatlog session pagination repeated a conversation; retry after service upgrade")
                seen.add(identifier)
                sessions.append(row)
            if payload.get("has_more") is False or len(rows) < 500:
                return sessions
            offset += len(rows)

    def get_database_talkers(self) -> list[str]:
        """Include retained message tables even when their session was removed from the sidebar."""
        response = requests.get(f"{self.base}/api/v1/db", timeout=30)
        response.raise_for_status()
        talkers = set()
        for file in response.json().get("message", []):
            if not re.fullmatch(r"(?:biz_)?message_\d+\.db", file.rsplit("/", 1)[-1]):
                continue
            response = requests.get(f"{self.base}/api/v1/db/tables",
                params={"group": "message", "file": file}, timeout=30)
            response.raise_for_status()
            tables = set(response.json())
            offset = 0
            while True:
                response = requests.get(f"{self.base}/api/v1/db/query", params={
                    "group": "message", "file": file, "sql": "SELECT user_name FROM Name2Id ORDER BY rowid",
                    "limit": 10000, "offset": offset,
                }, timeout=30)
                response.raise_for_status()
                rows = response.json()
                for row in rows:
                    name = row.get("user_name") or ""
                    if name and "Msg_" + hashlib.md5(name.encode()).hexdigest() in tables:
                        talkers.add(name)
                if response.headers.get("X-Chatlog-Has-More", "false") == "false":
                    break
                offset += len(rows)
        return sorted(talkers)

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

    def get_history_page(self, talker: str, since: int, until: int, offset: int = 0, limit: int = 500):
        response = requests.get(f"{self.base}/api/v1/history", params={
            "chat": talker, "since": since, "until": until, "limit": limit, "offset": offset,
        }, timeout=max(60, settings.CHATLOG_HTTP_TIMEOUT_SECONDS))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise ValueError("Chatlog returned an invalid history page")
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
            # The human-readable time is only minute precision in Chatlog Alpha.
            stamp = row.get("timestamp")
            if isinstance(stamp, (int, float)) and stamp > 0:
                row["time"] = datetime.fromtimestamp(stamp).astimezone().isoformat()
            if row.get("type_num"):
                row["type"] = row["type_num"]
                if row["type"] == 49 and row.get("sub_type") == 6:
                    row["type"] = "file"
            row["talker"] = username
            row["talkerName"] = talker_name
            row["isChatRoom"] = is_chatroom
            row["isSelf"] = bool(row.get("is_self"))
            row["senderName"] = row.get("sender")
            row["sender"] = row.get("sender_id") or row.get("sender")
            contents = dict(row.get("contents") or {})
            if row.get("media_url"):
                contents["media_url"] = row["media_url"]
            if row.get("image_url"):
                contents["image_url"] = row["image_url"]
            row["contents"] = contents
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
