"""media-collector 管理 API — 状态查询 + 关键词配置"""
from __future__ import annotations

import json
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings

router = APIRouter(prefix="/api/collector", tags=["collector"])


class KeywordsUpdate(BaseModel):
    keywords: list[str]


class AuthorsUpdate(BaseModel):
    authors: list[str]


class CollectorRefreshRequest(BaseModel):
    hot: bool = True
    search: bool = True
    authors: bool = True
    timeout_seconds: int | None = None
    wait: bool = False


def _keywords_path() -> Path:
    return (Path(__file__).resolve().parent.parent.parent / "media-collector" / "keywords.json").resolve()


def _authors_path() -> Path:
    return (Path(__file__).resolve().parent.parent.parent / "media-collector" / "authors.json").resolve()


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _default_sources_status() -> dict:
    keywords_path = _keywords_path()
    authors_path = _authors_path()
    keywords_data = _read_json_file(keywords_path)
    authors_data = _read_json_file(authors_path)
    keywords = keywords_data.get("keywords") if isinstance(keywords_data.get("keywords"), list) else []
    authors = authors_data.get("authors") if isinstance(authors_data.get("authors"), list) else []
    return {
        "collector_dir": str(keywords_path.parent),
        "keywords_path": str(keywords_path),
        "authors_path": str(authors_path),
        "keywords_count": len(keywords),
        "authors_count": len(authors),
        "keywords_updated": keywords_data.get("updated") or "",
        "authors_updated": authors_data.get("updated") or "",
        "ready": keywords_path.exists() and authors_path.exists() and bool(keywords or authors),
    }


@router.get("/keywords")
def get_keywords():
    """获取当前关键词列表"""
    path = _keywords_path()
    if not path.exists():
        return {"keywords": [], "path": str(path)}
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "keywords": data.get("keywords", []),
            "description": data.get("description", ""),
            "updated": data.get("updated", ""),
            "path": str(path),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/keywords")
def update_keywords(payload: KeywordsUpdate):
    """更新关键词列表"""
    path = _keywords_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = {}
        if path.exists():
            with open(path) as f:
                existing = json.load(f)
        existing["keywords"] = payload.keywords
        from datetime import date
        existing["updated"] = str(date.today())
        with open(path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"ok": True, "path": str(path), "count": len(payload.keywords)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/authors")
def get_authors():
    """获取当前作者列表"""
    path = _authors_path()
    if not path.exists():
        return {"authors": [], "path": str(path)}
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "authors": data.get("authors", []),
            "description": data.get("description", ""),
            "updated": data.get("updated", ""),
            "platform": data.get("platform", "bilibili"),
            "path": str(path),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/authors")
def update_authors(payload: AuthorsUpdate):
    """更新作者列表"""
    path = _authors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = {}
        if path.exists():
            with open(path) as f:
                existing = json.load(f)
        existing["authors"] = payload.authors
        from datetime import date
        existing["updated"] = str(date.today())
        existing.setdefault("platform", "bilibili")
        with open(path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"ok": True, "path": str(path), "count": len(payload.authors)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/status")
def collector_status():
    """采集器数据状态"""
    from ..services.media_collector_store import get_collector_status
    from ..services.media_collector_runner import get_media_collector_run_state

    status = get_collector_status()
    run_state = get_media_collector_run_state()
    return {
        **status,
        "running": bool(run_state.get("running")),
        "current_run": run_state.get("current_run"),
        "last_run": run_state.get("last_run"),
        "default_sources": _default_sources_status(),
        "auto_bootstrap": bool(settings.__dict__.get("MEDIA_COLLECTOR_AUTO_BOOTSTRAP", True)),
        "bootstrap_timeout_seconds": int(settings.__dict__.get("MEDIA_COLLECTOR_BOOTSTRAP_TIMEOUT_SECONDS", 60) or 60),
    }


@router.post("/refresh")
def refresh_collector(payload: CollectorRefreshRequest | None = None):
    """立即触发轻量自媒体采集。"""
    from ..services.media_collector_runner import run_media_collector_once, start_media_collector_job

    req = payload or CollectorRefreshRequest()
    if not bool(req.wait):
        return start_media_collector_job(
            hot=bool(req.hot),
            search=bool(req.search),
            authors=bool(req.authors),
            timeout_seconds=req.timeout_seconds,
        )
    return run_media_collector_once(
        hot=bool(req.hot),
        search=bool(req.search),
        authors=bool(req.authors),
        timeout_seconds=req.timeout_seconds,
    )


@router.get("/hot")
def hot_items(limit: int = 50):
    """获取热榜数据"""
    from ..services.media_collector_store import list_hot_items
    return list_hot_items(limit=limit)


@router.get("/search")
def search_items(keyword: str = "", limit: int = 50):
    """获取搜索结果"""
    from ..services.media_collector_store import list_search_items
    return list_search_items(limit=limit, keyword=keyword or None)


@router.get("/authors/items")
def author_items(author: str = "", limit: int = 50):
    """获取作者搜索结果"""
    from ..services.media_collector_store import list_author_items
    return list_author_items(limit=limit, author=author or None)
