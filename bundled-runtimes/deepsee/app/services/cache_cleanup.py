from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import SyncState


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEDIA_CACHE_ROOT = (PROJECT_ROOT / "data" / "media_cache").resolve()
CACHE_STATE_PREFIXES = ("summary_cache:", "minutes:", "news_snapshot:", "newsnow_cache:")


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _safe_media_cache_root(root: str | Path | None = None) -> Path:
    target = Path(root).expanduser().resolve() if root else MEDIA_CACHE_ROOT
    if target != MEDIA_CACHE_ROOT and not _is_inside(target, MEDIA_CACHE_ROOT):
        raise ValueError("cache cleanup root must stay inside data/media_cache")
    return target


def _unlink(path: Path, *, dry_run: bool) -> bool:
    if dry_run:
        return True
    path.unlink(missing_ok=True)
    return True


def _prune_empty_dirs(root: Path, *, dry_run: bool) -> int:
    if not root.exists():
        return 0
    removed = 0
    dirs = [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
    for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        if directory == root:
            continue
        try:
            if any(directory.iterdir()):
                continue
            if not dry_run:
                directory.rmdir()
            removed += 1
        except Exception:
            continue
    return removed


def cleanup_media_cache(
    *,
    root: str | Path | None = None,
    ttl_hours: int = 720,
    max_mb: int = 256,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete expired media cache files and enforce a total size cap.

    The cleaner is intentionally constrained to ``data/media_cache`` so it cannot
    accidentally remove user data or source files.
    """
    cache_root = _safe_media_cache_root(root)
    ttl_seconds = max(1, int(ttl_hours or 720)) * 3600
    max_bytes = max(1, int(max_mb or 256)) * 1024 * 1024
    cutoff = time.time() - ttl_seconds
    result: dict[str, Any] = {
        "status": "ok",
        "dry_run": bool(dry_run),
        "root": str(cache_root),
        "ttl_hours": int(ttl_hours or 720),
        "max_mb": int(max_mb or 256),
        "scanned": 0,
        "kept": 0,
        "deleted": 0,
        "deleted_expired": 0,
        "deleted_for_size": 0,
        "bytes_total_before": 0,
        "bytes_total_after": 0,
        "bytes_deleted": 0,
        "dirs_pruned": 0,
        "errors": [],
    }
    if not cache_root.exists():
        return result

    files: list[dict[str, Any]] = []
    for path in cache_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            stat = path.stat()
            item = {"path": path, "size": int(stat.st_size), "mtime": float(stat.st_mtime)}
            files.append(item)
            result["scanned"] += 1
            result["bytes_total_before"] += item["size"]
        except Exception as exc:
            if len(result["errors"]) < 20:
                result["errors"].append({"path": str(path), "error": str(exc)})

    for item in files:
        path = item["path"]
        size = int(item["size"])
        if float(item["mtime"]) < cutoff:
            try:
                _unlink(path, dry_run=dry_run)
                result["deleted"] += 1
                result["deleted_expired"] += 1
                result["bytes_deleted"] += size
            except Exception as exc:
                if len(result["errors"]) < 20:
                    result["errors"].append({"path": str(path), "error": str(exc)})

    result["bytes_total_after"] = max(0, int(result["bytes_total_before"]) - int(result["bytes_deleted"]))
    result["kept"] = max(0, int(result["scanned"]) - int(result["deleted"]))
    result["over_limit"] = result["bytes_total_after"] > max_bytes
    result["dirs_pruned"] = _prune_empty_dirs(cache_root, dry_run=dry_run)
    if result["errors"]:
        result["status"] = "partial"
    return result


def cleanup_state_cache(
    db: Session,
    *,
    ttl_hours: int = 720,
    dry_run: bool = False,
) -> dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(ttl_hours or 720)))
    rows = db.execute(select(SyncState.key).where(SyncState.updated_at < cutoff)).scalars().all()
    keys = [str(key) for key in rows if any(str(key).startswith(prefix) for prefix in CACHE_STATE_PREFIXES)]
    result: dict[str, Any] = {
        "status": "ok",
        "dry_run": bool(dry_run),
        "ttl_hours": int(ttl_hours or 720),
        "cutoff": cutoff.isoformat(),
        "prefixes": list(CACHE_STATE_PREFIXES),
        "scanned_old_rows": len(rows),
        "deleted": 0,
        "matched": len(keys),
    }
    if keys and not dry_run:
        res = db.execute(delete(SyncState).where(SyncState.key.in_(keys)))
        result["deleted"] = int(res.rowcount or 0)
    return result


def cleanup_application_cache(
    db: Session | None = None,
    *,
    ttl_hours: int = 720,
    max_mb: int = 256,
    dry_run: bool = False,
) -> dict[str, Any]:
    files = cleanup_media_cache(ttl_hours=ttl_hours, max_mb=max_mb, dry_run=dry_run)
    state = cleanup_state_cache(db, ttl_hours=ttl_hours, dry_run=dry_run) if db is not None else None
    deleted_items = int(files.get("deleted") or 0) + int((state or {}).get("deleted") or 0)
    matched_items = int(files.get("deleted") or 0) + int((state or {}).get("matched") or 0)
    return {
        "status": "partial" if files.get("status") == "partial" else "ok",
        "dry_run": bool(dry_run),
        "ttl_hours": int(ttl_hours or 720),
        "retention_days": round(max(1, int(ttl_hours or 720)) / 24, 2),
        "deleted_items": deleted_items,
        "matched_items": matched_items,
        "files": files,
        "state": state,
    }
