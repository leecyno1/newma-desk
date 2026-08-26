"""
读取 media-collector 的落盘数据（data/hot/ 和 data/search/）
替代原先仅依赖 MediaCrawlerPro 的 data/results/*.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

TZ = timezone(timedelta(hours=8))


def _collector_data_dir() -> Path:
    """默认: 0913 项目下的 data/ 目录"""
    env = os.getenv("COLLECTOR_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent.parent / "data").resolve()


def _parse_iso(ts: str) -> str | None:
    """解析 ISO 时间字符串，统一格式"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt.isoformat()
    except Exception:
        return ts


def list_hot_items(
    *, limit: int = 100, date_dir: str | None = None, platform: str | None = None
) -> dict:
    """从 data/hot/ 读取最新热榜数据"""
    base = _collector_data_dir() / "hot"
    if not base.exists():
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "data/hot/ not found"}}

    # 找最新日期的目录
    if date_dir:
        day_dir = base / date_dir
    else:
        days = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
        if not days:
            return {"items": [], "total": 0}
        day_dir = days[0]

    if not day_dir.exists():
        return {"items": [], "total": 0}

    items = []
    for f in day_dir.glob("*.json"):
        fname = f.name
        if fname.startswith("_") or fname.startswith("."):
            continue

        # 提取平台名
        plat = fname.replace(".json", "")
        plat_display = plat.replace("newsnow_", "").replace("_hot", "")

        if platform and plat != platform and f"newsnow_{platform}" != plat:
            continue

        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        item_list = data.get("items") or []
        fetched_at = data.get("fetched_at", "")

        for it in item_list[:30]:
            items.append({
                "id": f"hot_{plat}_{it.get('rank', 0)}",
                "platform": plat_display,
                "source_type": "hot",
                "time": fetched_at,
                "title": it.get("title", ""),
                "author": it.get("extra", {}).get("author", ""),
                "url": it.get("url", ""),
                "heat": it.get("heat", 0),
                "description": it.get("description", "")[:300],
                "stats": {
                    "heat": it.get("heat", 0),
                    "rank": it.get("rank", 0),
                    "extra": it.get("extra", {}),
                },
                "source_file": f.name,
                "source_mtime": int(f.stat().st_mtime),
            })

    items.sort(key=lambda x: x.get("source_mtime", 0), reverse=True)
    return {
        "items": items[:limit],
        "total": len(items[:limit]),
        "date_dir": day_dir.name,
        "source": {"ok": True, "dir": str(day_dir)},
    }


def list_search_items(
    *, limit: int = 100, date_dir: str | None = None, keyword: str | None = None
) -> dict:
    """从 data/search/ 读取关键词搜索结果"""
    base = _collector_data_dir() / "search"
    if not base.exists():
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "data/search/ not found"}}

    if date_dir:
        day_dir = base / date_dir
    else:
        days = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
        if not days:
            return {"items": [], "total": 0}
        day_dir = days[0]

    if not day_dir.exists():
        return {"items": [], "total": 0}

    items = []
    for kw_dir in sorted(day_dir.iterdir()):
        if not kw_dir.is_dir():
            continue

        dir_name = kw_dir.name
        # 尝试从 _summary.json 读取关键词
        summary_file = kw_dir / "_summary.json"
        kw = keyword or ""
        if summary_file.exists():
            try:
                with open(summary_file) as f:
                    s = json.load(f)
                kw = s.get("keyword", dir_name.split("_")[0])
            except Exception:
                kw = dir_name.split("_")[0] if "_" in dir_name else dir_name

        if keyword and keyword not in kw and keyword not in dir_name:
            continue

        for f in kw_dir.glob("*.json"):
            fname = f.name
            if fname.startswith("_") or fname.startswith("."):
                continue

            plat = fname.replace(".json", "")
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue

            if not isinstance(data, dict) or "error" in data:
                continue

            item_list = data.get("items") or []
            fetched_at = data.get("fetched_at", "")

            for it in item_list[:30]:
                items.append({
                    "id": f"search_{kw}_{plat}_{it.get('rank', 0)}",
                    "platform": plat,
                    "source_type": "search",
                    "keyword": kw,
                    "time": fetched_at,
                    "title": it.get("title", ""),
                    "author": it.get("extra", {}).get("author", ""),
                    "url": it.get("url", ""),
                    "heat": it.get("heat", 0),
                    "description": it.get("description", "")[:300],
                    "stats": {
                        "heat": it.get("heat", 0),
                        "rank": it.get("rank", 0),
                        "extra": it.get("extra", {}),
                    },
                    "source_file": f.name,
                    "source_mtime": int(f.stat().st_mtime),
                })

    items.sort(key=lambda x: (x.get("keyword", ""), x.get("heat", 0)), reverse=True)
    return {
        "items": items[:limit],
        "total": len(items[:limit]),
        "date_dir": day_dir.name,
        "source": {"ok": True, "dir": str(day_dir)},
    }


def list_author_items(*, limit: int = 100, date_dir: str | None = None, author: str | None = None) -> dict:
    """从 data/authors/ 读取作者搜索结果"""
    base = _collector_data_dir() / "authors"
    if not base.exists():
        return {"items": [], "total": 0, "source": {"ok": False, "reason": "data/authors/ not found"}}

    if date_dir:
        day_dir = base / date_dir
    else:
        days = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
        if not days:
            return {"items": [], "total": 0}
        day_dir = days[0]

    if not day_dir.exists():
        return {"items": [], "total": 0}

    items = []
    for f in sorted(day_dir.glob("*.json")):
        if f.name.startswith("_") or f.name.startswith("."):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("error"):
            continue
        author_query = data.get("author_query") or data.get("keyword") or f.stem
        if author and author not in author_query:
            continue
        fetched_at = data.get("fetched_at", "")
        for it in (data.get("items") or [])[:30]:
            extra = it.get("extra") if isinstance(it.get("extra"), dict) else {}
            items.append({
                "id": f"author_{author_query}_{it.get('rank', 0)}",
                "platform": "bilibili",
                "source_type": "author",
                "keyword": author_query,
                "author_query": author_query,
                "time": fetched_at,
                "title": it.get("title", ""),
                "author": extra.get("author") or author_query,
                "url": it.get("url", ""),
                "heat": it.get("heat", 0),
                "description": it.get("description", "")[:300],
                "stats": {
                    "heat": it.get("heat", 0),
                    "rank": it.get("rank", 0),
                    "extra": extra,
                },
                "source_file": f.name,
                "source_mtime": int(f.stat().st_mtime),
            })

    items.sort(key=lambda x: (x.get("source_mtime", 0), x.get("heat", 0)), reverse=True)
    return {
        "items": items[:limit],
        "total": len(items[:limit]),
        "date_dir": day_dir.name,
        "source": {"ok": True, "dir": str(day_dir)},
    }


def list_all_items(*, limit: int = 200, keyword: str | None = None) -> dict:
    """合并热榜、关键词搜索、作者搜索数据"""
    hot_limit = max(1, limit // 3)
    search_limit = max(1, limit // 3)
    author_limit = max(1, limit - hot_limit - search_limit)
    hot = list_hot_items(limit=hot_limit)
    search = list_search_items(limit=search_limit, keyword=keyword)
    authors = list_author_items(limit=author_limit)

    all_items = hot.get("items", []) + search.get("items", []) + authors.get("items", [])
    all_items.sort(key=lambda x: x.get("source_mtime", 0), reverse=True)

    return {
        "items": all_items[:limit],
        "total": len(all_items[:limit]),
        "hot": {"total": hot.get("total", 0)},
        "search": {"total": search.get("total", 0)},
        "authors": {"total": authors.get("total", 0)},
    }


def get_collector_status() -> dict:
    """获取采集器状态"""
    base = _collector_data_dir()
    hot_dir = base / "hot"
    search_dir = base / "search"
    authors_dir = base / "authors"

    status = {
        "data_dir": str(base),
        "hot": {"exists": hot_dir.exists()},
        "search": {"exists": search_dir.exists()},
        "authors": {"exists": authors_dir.exists()},
    }

    if hot_dir.exists():
        days = sorted([d.name for d in hot_dir.iterdir() if d.is_dir()], reverse=True)
        status["hot"]["days"] = days[:7]
        if days:
            latest = hot_dir / days[0]
            files = [f.name for f in latest.glob("*.json") if not f.name.startswith(("_", "."))]
            status["hot"]["latest_day"] = days[0]
            status["hot"]["latest_files"] = files

    if search_dir.exists():
        days = sorted([d.name for d in search_dir.iterdir() if d.is_dir()], reverse=True)
        status["search"]["days"] = days[:7]
        if days:
            kw_count = len([d for d in (search_dir / days[0]).iterdir() if d.is_dir()])
            status["search"]["latest_day"] = days[0]
            status["search"]["keywords_count"] = kw_count

    if authors_dir.exists():
        days = sorted([d.name for d in authors_dir.iterdir() if d.is_dir()], reverse=True)
        status["authors"]["days"] = days[:7]
        if days:
            latest = authors_dir / days[0]
            files = [f.name for f in latest.glob("*.json") if not f.name.startswith(("_", "."))]
            status["authors"]["latest_day"] = days[0]
            status["authors"]["authors_count"] = len(files)

    return status
