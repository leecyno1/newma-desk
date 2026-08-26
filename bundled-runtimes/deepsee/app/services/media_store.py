from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _iso_from_epoch_seconds(v: Any) -> str | None:
    try:
        if v is None:
            return None
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v.strip())
        if isinstance(v, (int, float)):
            # Heuristic: ms epoch if too large
            if v > 10_000_000_000:
                v = v / 1000.0
            return datetime.fromtimestamp(float(v), tz=timezone.utc).astimezone().replace(tzinfo=None).isoformat()
    except Exception:
        return None
    return None


def _infer_platform(item: dict) -> str:
    if any(k in item for k in ("aweme_id", "aweme_url", "video_download_url", "sec_uid")):
        return "douyin"
    if any(k in item for k in ("note_id", "note_url", "xsec_token", "xhs_note_id")):
        return "xhs"
    if any(k in item for k in ("bvid", "bili_id", "bilibili_url")):
        return "bilibili"
    if any(k in item for k in ("weibo_id", "weibo_url")):
        return "weibo"
    if any(k in item for k in ("tieba_id", "tieba_url")):
        return "tieba"
    if any(k in item for k in ("zhihu_id", "zhihu_url", "question_id")):
        return "zhihu"
    return (str(item.get("platform") or "")).strip() or "unknown"


def _first_str(item: dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _first_int(item: dict, keys: Iterable[str]) -> int | None:
    for k in keys:
        v = item.get(k)
        try:
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return int(v)
        except Exception:
            continue
    return None


def _default_media_project_dir() -> Path | None:
    env = os.getenv("MEDIA_PROJECT_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.exists() else None
    # sibling project
    guess = (Path(os.getcwd()).resolve().parent / "MediaCrawlerPro-Python").resolve()
    return guess if guess.exists() else None


def _iter_result_files(root: Path) -> list[Path]:
    base = root / "data" / "results"
    if not base.exists():
        return []
    files = [p for p in base.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def list_media_items(*, limit: int = 200, q: str | None = None, project_dir: str | None = None) -> dict:
    root = Path(project_dir).expanduser().resolve() if project_dir else _default_media_project_dir()
    if not root:
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "MEDIA_PROJECT_DIR not set and default not found"}}

    results_dir = (root / "data" / "results").resolve()
    if not results_dir.exists():
        return {
            "items": [],
            "total": 0,
            "source": {
                "ok": False,
                "reason": "results dir not found",
                "project_dir": str(root),
                "results_dir": str(results_dir),
            },
        }

    ql = (q or "").strip().lower()
    raw_items: list[dict] = []
    # Collect more than `limit` so we can keep platform diversity (newest file may be single-platform).
    # Hard cap to avoid large memory usage if results folder is huge.
    soft_cap = max(800, limit * 6)
    result_files = _iter_result_files(root)
    latest_file = result_files[0] if result_files else None
    for path in result_files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for raw in data:
            if not isinstance(raw, dict):
                continue
            # Keep a back-reference to source file for mtime-based sorting/caching.
            raw2 = raw.copy()
            raw2["_source_file"] = path.name
            raw2["_source_mtime"] = int(path.stat().st_mtime)
            raw_items.append(raw2)
            if len(raw_items) >= soft_cap:
                break
        if len(raw_items) >= soft_cap:
            break

    # Normalize and group by platform
    normalized: list[dict] = []
    for raw in raw_items:
        platform = _infer_platform(raw)
        time_iso = (
            _iso_from_epoch_seconds(raw.get("create_time"))
            or _iso_from_epoch_seconds(raw.get("note_time"))
            or _iso_from_epoch_seconds(raw.get("add_ts"))
            or _iso_from_epoch_seconds(raw.get("last_modify_ts"))
        )
        title = _first_str(raw, ("title", "desc", "content", "text"))
        author = _first_str(raw, ("nickname", "user_name", "author", "username"))
        url = _first_str(raw, ("aweme_url", "note_url", "share_url", "url"))
        transcript = _first_str(raw, ("transcript_text", "transcript_raw"))
        summary = transcript or title
        task_source = _first_str(
            raw,
            (
                "task_source",
                "task_name",
                "task_type",
                "task",
                "source_task",
                "source_type",
                "source_name",
                "source",
            ),
        )
        if not task_source:
            task_source = str(raw.get("source_keyword") or "").strip()
        if not task_source:
            # Fallback to source file name (usually includes task type like keyword_search / blogger_monitor)
            task_source = str(raw.get("_source_file") or "").strip()

        liked = _first_int(raw, ("liked_count", "digg_count", "like_count"))
        comments = _first_int(raw, ("comment_count", "comments_count"))
        shares = _first_int(raw, ("share_count", "share_cnt"))
        collects = _first_int(raw, ("collected_count", "collect_count", "favorite_count"))

        # basic search filter
        if ql:
            hay = " ".join([platform, author, title, summary, url]).lower()
            if ql not in hay:
                continue

        normalized.append(
            {
                "id": str(raw.get("id") or raw.get("note_id") or raw.get("aweme_id") or ""),
                "platform": platform,
                "time": time_iso,
                "author": author,
                "task_source": task_source,
                "title": title,
                "summary": summary[:600] if isinstance(summary, str) else "",
                "url": url,
                "stats": {"like": liked, "comment": comments, "share": shares, "collect": collects},
                "transcript_status": str(raw.get("transcript_status") or ""),
                "source_keyword": str(raw.get("source_keyword") or ""),
                "source_file": str(raw.get("_source_file") or ""),
                "source_mtime": int(raw.get("_source_mtime") or 0),
            }
        )

    def _sort_key(it: dict) -> tuple[int, str]:
        mtime = int(it.get("source_mtime") or 0)
        return (mtime, str(it.get("time") or ""))

    by_platform: dict[str, list[dict]] = {}
    for it in normalized:
        by_platform.setdefault(str(it.get("platform") or "unknown"), []).append(it)
    for k in list(by_platform.keys()):
        by_platform[k].sort(key=_sort_key, reverse=True)

    # Ensure platform coverage: take a small quota per platform, then fill the rest by recency.
    platforms = list(by_platform.keys())
    platforms.sort()
    per_platform = max(10, min(60, limit // max(1, min(len(platforms), 6))))
    selected: list[dict] = []
    seen_ids: set[str] = set()
    for plat in platforms:
        for it in by_platform.get(plat, [])[:per_platform]:
            mid = str(it.get("id") or "")
            if mid and mid in seen_ids:
                continue
            if mid:
                seen_ids.add(mid)
            selected.append(it)
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        # Fill remaining slots with newest items overall
        overall = sorted(normalized, key=_sort_key, reverse=True)
        for it in overall:
            if len(selected) >= limit:
                break
            mid = str(it.get("id") or "")
            if mid and mid in seen_ids:
                continue
            if mid:
                seen_ids.add(mid)
            selected.append(it)

    # Final sort by time/mtime desc for UI
    selected.sort(key=_sort_key, reverse=True)

    return {
        "items": selected[:limit],
        "total": len(selected[:limit]),
        "source": {
            "ok": True,
            "project_dir": str(root),
            "results_dir": str(results_dir),
            "latest_file": (latest_file.name if latest_file else None),
            "latest_mtime": (int(latest_file.stat().st_mtime) if latest_file else None),
            "latest_size": (int(latest_file.stat().st_size) if latest_file else None),
        },
    }


def _safe_join(root: Path, rel: str) -> Path | None:
    try:
        rel = (rel or "").strip().lstrip("/").lstrip("\\")
        if not rel:
            return None
        p = (root / rel).resolve()
        root_res = root.resolve()
        if not str(p).startswith(str(root_res) + os.sep) and p != root_res:
            return None
        return p
    except Exception:
        return None


def list_media_meeting_records(*, limit: int = 200, project_dir: str | None = None) -> dict:
    root = Path(project_dir).expanduser().resolve() if project_dir else _default_media_project_dir()
    if not root:
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "MEDIA_PROJECT_DIR not set and default not found"}}

    base = root / "data" / "meeting_records"
    if not base.exists():
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "meeting_records dir not found", "dir": str(base)}}

    files = [p for p in base.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict] = []
    for path in files[: max(0, limit)]:
        try:
            data = json.load(open(path, "r", encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        audio_rel = str(data.get("audio_path") or "").strip()
        audio_abs = _safe_join(root, audio_rel) if audio_rel else None
        out.append(
            {
                "id": str(data.get("id") or path.stem),
                "time": str(data.get("start_time") or ""),
                "title": str(data.get("title") or ""),
                "topic": str(data.get("topic") or ""),
                "duration_seconds": data.get("duration_seconds"),
                "transcript_status": str(data.get("transcript_status") or ""),
                "meeting_minutes": str(data.get("meeting_minutes") or ""),
                "raw_text": str(data.get("raw_text") or ""),
                "audio_path": audio_rel,
                "audio_exists": bool(audio_abs and audio_abs.exists()),
                "source_file": path.name,
                "source_mtime": int(path.stat().st_mtime),
            }
        )

    return {
        "items": out,
        "total": len(out),
        "source": {"ok": True, "project_dir": str(root), "meeting_records_dir": str(base.resolve())},
    }


def resolve_media_meeting_audio_path(record_id: str, *, project_dir: str | None = None) -> Path | None:
    root = Path(project_dir).expanduser().resolve() if project_dir else _default_media_project_dir()
    if not root:
        return None
    base = root / "data" / "meeting_records"
    if not base.exists():
        return None
    json_path = base / f"{record_id}.json"
    if not json_path.exists():
        # some ids are like meeting_... already
        candidates = list(base.glob(f"*{record_id}*.json"))
        if candidates:
            json_path = candidates[0]
        else:
            return None
    try:
        data = json.load(open(json_path, "r", encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    audio_rel = str(data.get("audio_path") or "").strip()
    if not audio_rel:
        return None
    audio_abs = _safe_join(root, audio_rel)
    if not audio_abs or not audio_abs.exists():
        return None
    return audio_abs
