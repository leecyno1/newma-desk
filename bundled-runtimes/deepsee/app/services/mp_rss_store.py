from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


DEFAULT_MP_UPSTREAM_URL = os.getenv("MP_UPSTREAM_URL", "http://45.197.148.64:8000").strip()
MP_UPSTREAM_TIMEOUT_SEC = max(3.0, float(os.getenv("MP_UPSTREAM_TIMEOUT_SEC", "12")))
MP_PUBLIC_MAX_CHANNELS = max(10, int(os.getenv("MP_PUBLIC_MAX_CHANNELS", "60")))
MP_PUBLIC_CHANNELS_PAGE = max(10, int(os.getenv("MP_PUBLIC_CHANNELS_PAGE", "60")))


def _default_we_mp_rss_db() -> Path | None:
    env_db = os.getenv("WE_MP_RSS_DB", "").strip()
    if env_db:
        p = Path(env_db).expanduser().resolve()
        return p if p.exists() else None
    env_dir = os.getenv("WE_MP_RSS_DIR", "").strip()
    if env_dir:
        p = (Path(env_dir).expanduser().resolve() / "data" / "db.db").resolve()
        return p if p.exists() else None
    guess = (Path(os.getcwd()).resolve().parent / "we-mp-rss" / "data" / "db.db").resolve()
    return guess if guess.exists() else None


def _iso_from_publish_time(v: Any) -> str | None:
    try:
        if v is None:
            return None
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v.strip())
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc).astimezone().replace(tzinfo=None).isoformat()
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo:
                    return dt.astimezone().replace(tzinfo=None).isoformat()
                return dt.isoformat()
            except Exception:
                return s
    except Exception:
        return None
    return None


def _normalize_base_url(url: str | None) -> str | None:
    s = str(url or "").strip()
    if not s:
        return None
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "http://" + s
    return s.rstrip("/")


def _to_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _time_sort_key(v: Any) -> float:
    try:
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v or "").strip()
        if not s:
            return 0.0
        if s.isdigit():
            return float(s)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.timestamp()
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def _request_remote_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = MP_UPSTREAM_TIMEOUT_SEC,
) -> Any:
    resp = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    try:
        payload = resp.json()
    except Exception as exc:
        snippet = (resp.text or "")[:240]
        raise RuntimeError(f"remote invalid json ({resp.status_code}): {snippet}") from exc

    if isinstance(payload, dict) and "code" in payload:
        code = payload.get("code")
        if resp.status_code >= 400 or str(code) != "0":
            msg = str(payload.get("message") or f"code={code}").strip()
            raise RuntimeError(f"remote error {resp.status_code}: {msg}")
        return payload.get("data")

    if resp.status_code >= 400:
        raise RuntimeError(f"remote http {resp.status_code}")
    return payload


def _normalize_remote_article(raw: dict[str, Any], default_channel: str = "") -> dict:
    summary = str(raw.get("summary") or raw.get("insight_summary") or raw.get("description") or "").strip()
    channel_name = (
        str(raw.get("channel_name") or "").strip()
        or str(raw.get("mp_name") or "").strip()
        or str(raw.get("name") or "").strip()
        or default_channel
    )
    return {
        "id": raw.get("id"),
        "mp_id": raw.get("mp_id"),
        "channel_name": channel_name,
        "title": str(raw.get("title") or "").strip(),
        "url": str(raw.get("url") or "").strip(),
        "summary": summary[:800],
        "publish_time": _iso_from_publish_time(raw.get("publish_time")),
        "is_read": bool(raw.get("is_read") or 0),
        "read_count": _to_int(raw.get("read_count")),
        "like_count": _to_int(raw.get("like_count")),
        "share_count": _to_int(raw.get("share_count")),
        "recommend_count": _to_int(raw.get("recommend_count")),
    }


def _list_remote_articles_auth(
    *,
    base_url: str,
    limit: int,
    offset: int,
    q: str | None,
    auth_token: str | None,
) -> dict:
    headers: dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    data = _request_remote_json(
        f"{base_url}/api/v1/wx/articles",
        params={
            "limit": int(limit),
            "offset": int(offset),
            "search": (q or "").strip() or None,
            "with_total": True,
        },
        headers=headers,
    )
    if isinstance(data, dict):
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        total = _to_int(data.get("total")) if data.get("total") is not None else len(rows)
    elif isinstance(data, list):
        rows = data
        total = len(rows)
    else:
        rows = []
        total = 0
    items = [_normalize_remote_article(it if isinstance(it, dict) else {}) for it in rows]
    return {
        "items": items,
        "total": total,
        "source": {"ok": True, "remote": True, "mode": "wx/articles", "base_url": base_url},
    }


def _list_remote_articles_public(*, base_url: str, limit: int, offset: int, q: str | None) -> dict:
    target = min(180, max(int(limit), int(offset) + int(limit)))
    max_channels = MP_PUBLIC_MAX_CHANNELS
    channels_page = min(MP_PUBLIC_CHANNELS_PAGE, max_channels)
    per_channel_limit = max(2, min(12, (target + 19) // 20))

    channels_offset = 0
    scanned = 0
    rows: list[dict] = []
    errors: list[str] = []
    qv = (q or "").strip()

    while scanned < max_channels and len(rows) < target:
        data = _request_remote_json(
            f"{base_url}/api/v1/wx/public/channels",
            params={"limit": channels_page, "offset": channels_offset, "kw": qv or None},
        )
        channels = data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else []
        if not channels:
            break
        for ch in channels:
            if scanned >= max_channels or len(rows) >= target:
                break
            scanned += 1
            cid = str((ch or {}).get("id") or "").strip()
            if not cid:
                continue
            ch_name = str((ch or {}).get("name") or "").strip()
            try:
                articles_data = _request_remote_json(
                    f"{base_url}/api/v1/wx/public/channels/{quote(cid, safe='')}/articles",
                    params={"limit": per_channel_limit, "offset": 0, "kw": qv or None},
                )
                article_rows = (
                    articles_data.get("list")
                    if isinstance(articles_data, dict) and isinstance(articles_data.get("list"), list)
                    else []
                )
                for item in article_rows:
                    if isinstance(item, dict):
                        rows.append(_normalize_remote_article(item, default_channel=ch_name))
            except Exception as exc:
                if len(errors) < 3:
                    errors.append(f"{cid}:{exc}")
                continue
        channels_offset += len(channels)
        if len(channels) < channels_page:
            break

    rows.sort(key=lambda it: _time_sort_key(it.get("publish_time")), reverse=True)
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for it in rows:
        k = str(it.get("id") or "").strip()
        if not k or k in seen_ids:
            continue
        seen_ids.add(k)
        deduped.append(it)
    page = deduped[int(offset): int(offset) + int(limit)]
    source = {
        "ok": True,
        "remote": True,
        "mode": "wx/public/channels/*/articles",
        "base_url": base_url,
        "scanned_channels": scanned,
    }
    if errors:
        source["notes"] = "; ".join(errors[:3])
    return {"items": page, "total": len(deduped), "source": source}


def _get_remote_article(
    article_id: str,
    *,
    include_content: bool,
    base_url: str,
    auth_token: str | None,
) -> dict:
    headers: dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    article_data = _request_remote_json(
        f"{base_url}/api/v1/wx/articles/{quote(str(article_id), safe='')}",
        headers=headers,
    )
    if not isinstance(article_data, dict):
        return {}
    item = _normalize_remote_article(article_data)
    if include_content:
        item["content"] = str(article_data.get("content") or article_data.get("description") or "").strip()
        if not item.get("summary"):
            item["summary"] = str(article_data.get("summary") or "").strip()
        try:
            insights = _request_remote_json(
                f"{base_url}/api/v1/wx/public/insights/{quote(str(article_id), safe='')}",
                headers=headers,
            )
            if isinstance(insights, dict):
                if not item.get("summary"):
                    item["summary"] = str(insights.get("summary") or "").strip()
                kp = insights.get("key_points_json")
                if kp is None:
                    kp = insights.get("key_points")
                if kp is not None:
                    item["key_points_json"] = kp
        except Exception:
            pass
    return item


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def list_mp_articles(
    *,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
    db_path: str | None = None,
    upstream_base_url: str | None = None,
    upstream_auth_token: str | None = None,
) -> dict:
    remote_base = _normalize_base_url(upstream_base_url) or _normalize_base_url(DEFAULT_MP_UPSTREAM_URL)
    remote_enabled = os.getenv("MP_REMOTE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"} or bool(
        str(upstream_auth_token or "").strip()
    )
    remote_error: str | None = None
    if remote_enabled and remote_base:
        try:
            if str(upstream_auth_token or "").strip():
                return _list_remote_articles_auth(
                    base_url=remote_base,
                    limit=limit,
                    offset=offset,
                    q=q,
                    auth_token=str(upstream_auth_token).strip(),
                )
            return _list_remote_articles_public(base_url=remote_base, limit=limit, offset=offset, q=q)
        except Exception as exc:
            remote_error = str(exc)

    path = Path(db_path).expanduser().resolve() if db_path else _default_we_mp_rss_db()
    if not path:
        source = {"ok": False, "reason": "WE_MP_RSS_DB/WE_MP_RSS_DIR not set and default not found"}
        if remote_error:
            source["remote_error"] = remote_error
            source["remote_base_url"] = remote_base or ""
        return {"items": [], "total": 0, "source": source}
    if not path.exists():
        source = {"ok": False, "reason": "we-mp-rss db not found", "db": str(path)}
        if remote_error:
            source["remote_error"] = remote_error
            source["remote_base_url"] = remote_base or ""
        return {"items": [], "total": 0, "source": source}

    ql = (q or "").strip().lower()
    st = path.stat()
    con = _connect(path)
    try:
        where = "1=1"
        params: list[Any] = []
        if ql:
            where = "(lower(a.title) like ? OR lower(a.description) like ? OR lower(f.mp_name) like ?)"
            params.extend([f"%{ql}%", f"%{ql}%", f"%{ql}%"])
        sql = f"""
            SELECT
                a.id, a.mp_id, a.title, a.url, a.description, a.publish_time, a.created_at, a.updated_at, a.is_read,
                a.read_count, a.like_count, a.share_count, a.recommend_count,
                f.mp_name,
                i.summary AS insight_summary
            FROM articles a
            LEFT JOIN feeds f ON f.id = a.mp_id
            LEFT JOIN article_insights i ON i.article_id = a.id
            WHERE a.status != 0 AND {where}
            ORDER BY a.publish_time DESC
            LIMIT ? OFFSET ?
        """
        params.extend([int(limit), int(offset)])
        rows = con.execute(sql, params).fetchall()
        items: list[dict] = []
        for r in rows:
            title = (r["title"] or "").strip()
            summary = (r["insight_summary"] or r["description"] or "").strip()
            read_count = int(r["read_count"] or 0)
            like_count = int(r["like_count"] or 0)
            share_count = int(r["share_count"] or 0)
            recommend_count = int(r["recommend_count"] or 0)
            items.append(
                {
                    "id": r["id"],
                    "mp_id": r["mp_id"],
                    "channel_name": r["mp_name"] or r["mp_id"],
                    "title": title,
                    "url": r["url"] or "",
                    "summary": summary[:800],
                    "publish_time": _iso_from_publish_time(r["publish_time"]),
                    "is_read": bool(r["is_read"] or 0),
                    "read_count": read_count,
                    "like_count": like_count,
                    "share_count": share_count,
                    "recommend_count": recommend_count,
                }
            )
        source = {"ok": True, "db": str(path), "mtime": int(st.st_mtime), "size": int(st.st_size)}
        if remote_error:
            source["remote_error"] = remote_error
            source["remote_base_url"] = remote_base or ""
        return {
            "items": items,
            "total": len(items),
            "source": source,
        }
    finally:
        con.close()


def get_mp_article(
    article_id: str,
    *,
    include_content: bool = False,
    db_path: str | None = None,
    upstream_base_url: str | None = None,
    upstream_auth_token: str | None = None,
) -> dict:
    remote_base = _normalize_base_url(upstream_base_url) or _normalize_base_url(DEFAULT_MP_UPSTREAM_URL)
    remote_enabled = os.getenv("MP_REMOTE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"} or bool(
        str(upstream_auth_token or "").strip()
    )
    remote_error: str | None = None
    if remote_enabled and remote_base:
        try:
            item = _get_remote_article(
                article_id,
                include_content=include_content,
                base_url=remote_base,
                auth_token=str(upstream_auth_token or "").strip() or None,
            )
            if item:
                return item
        except Exception as exc:
            remote_error = str(exc)

    path = Path(db_path).expanduser().resolve() if db_path else _default_we_mp_rss_db()
    if not path:
        if remote_error:
            raise FileNotFoundError(f"remote fetch failed: {remote_error}")
        raise FileNotFoundError("we-mp-rss db not configured")
    con = _connect(path)
    try:
        row = con.execute(
            """
            SELECT
                a.id, a.mp_id, a.title, a.url, a.description, a.publish_time, a.created_at, a.updated_at, a.is_read, a.content,
                a.read_count, a.like_count, a.share_count, a.recommend_count,
                f.mp_name,
                i.summary AS insight_summary, i.key_points_json
            FROM articles a
            LEFT JOIN feeds f ON f.id = a.mp_id
            LEFT JOIN article_insights i ON i.article_id = a.id
            WHERE a.id = ?
            """,
            [article_id],
        ).fetchone()
        if not row:
            return {}
        item = {
            "id": row["id"],
            "mp_id": row["mp_id"],
            "channel_name": row["mp_name"] or row["mp_id"],
            "title": (row["title"] or "").strip(),
            "url": row["url"] or "",
            "publish_time": _iso_from_publish_time(row["publish_time"]),
            "summary": (row["insight_summary"] or row["description"] or "").strip(),
            "is_read": bool(row["is_read"] or 0),
            "read_count": int(row["read_count"] or 0),
            "like_count": int(row["like_count"] or 0),
            "share_count": int(row["share_count"] or 0),
            "recommend_count": int(row["recommend_count"] or 0),
        }
        if include_content:
            item["content"] = (row["content"] or "").strip()
            item["key_points_json"] = row["key_points_json"]
        return item
    finally:
        con.close()
