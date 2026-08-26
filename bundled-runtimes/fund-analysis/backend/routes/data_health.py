"""
数据健康检查 API
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from repositories import get_data_snapshot_repo

router = APIRouter(prefix="/api/data-health", tags=["数据健康"])


@router.get("/summary")
def get_data_health_summary(stale_hours: int = Query(24, ge=1, le=24 * 30)) -> Dict[str, Any]:
    """返回各数据集最新同步状态、近期失败数和过期数据集。"""
    repo = get_data_snapshot_repo()
    try:
        latest_snapshots = repo.list_latest_by_dataset()
        recent_failed_count = repo.count_recent_failures(hours=stale_hours)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Data health store unavailable: {exc.__class__.__name__}") from exc

    cutoff = datetime.now() - timedelta(hours=stale_hours)
    stale_datasets: List[Dict[str, Any]] = []
    for snapshot in latest_snapshots:
        finished_at = snapshot.get("finished_at") or snapshot.get("started_at")
        status = snapshot.get("status")
        is_stale = False
        if finished_at:
            try:
                is_stale = datetime.fromisoformat(finished_at) < cutoff
            except ValueError:
                is_stale = False
        if status != "success" or is_stale:
            stale_datasets.append({
                "dataset": snapshot.get("dataset"),
                "source": snapshot.get("source"),
                "status": status,
                "last_seen_at": finished_at,
            })

    return {
        "latest_snapshots": latest_snapshots,
        "recent_failed_count": recent_failed_count,
        "stale_datasets": stale_datasets,
        "stale_threshold_hours": stale_hours,
    }


def _runbook_path() -> Path:
    base = os.environ.get("SCHEDULED_UPDATE_LOG_ROOT")
    if base:
        return Path(base) / "runbook.jsonl"
    # fall back to repo-root relative path (backend cwd is repo root during dev)
    return Path.cwd() / "logs" / "scheduled_update" / "runbook.jsonl"


@router.get("/scheduler")
def get_scheduler_status(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """读取 scheduled_update.sh 的 runbook.jsonl，返回每个任务最近一次执行摘要。

    - last_by_task: 每个 task_id 的最近一次执行
    - recent_runs: 最新 N 次（默认 50）执行按时间倒序
    - buckets: 每个 bucket 的最近一次完整扫过时间
    - runbook_present: 若无 runbook 文件（还没跑过任何任务）返回 False
    """
    path = _runbook_path()
    payload: Dict[str, Any] = {
        "runbook_path": str(path),
        "runbook_present": path.exists(),
        "last_by_task": {},
        "recent_runs": [],
        "buckets": {},
    }
    if not path.exists():
        return payload

    lines: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Cannot read runbook: {exc}") from exc

    lines.sort(key=lambda item: str(item.get("ts") or ""))

    last_by_task: Dict[str, Dict[str, Any]] = {}
    for item in lines:
        task = str(item.get("task") or "").strip()
        if task:
            last_by_task[task] = item

    buckets: Dict[str, Dict[str, Any]] = {}
    for item in lines:
        bucket = str(item.get("bucket") or "").strip()
        if not bucket:
            continue
        current = buckets.setdefault(bucket, {"last_run": None, "success_count": 0, "failed_count": 0})
        current["last_run"] = item.get("ts")
        if item.get("status") == "ok":
            current["success_count"] += 1
        elif item.get("status") == "failed":
            current["failed_count"] += 1

    payload["last_by_task"] = last_by_task
    payload["recent_runs"] = list(reversed(lines[-limit:]))
    payload["buckets"] = buckets
    return payload


@router.get("/pending-queue")
def get_pending_queue(folder_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """汇总当前待确认（human review）项目按 kind 的分类计数。

    kinds: manager / fund / classification / style_label / tag / other
    返回 total 与 by_kind 计数，方便首页/健康面板显示"99项待确认"红点。
    """
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        repo = PostgresLocalResearchFolderRepo()
        items = repo.list_pending_reviews(folder_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Pending queue unavailable: {exc.__class__.__name__}") from exc

    kinds = Counter()
    for item in items:
        kind = str(item.get("kind") or "").strip() or "other"
        kinds[kind] += 1

    return {
        "total": len(items),
        "by_kind": dict(kinds),
        "folder_id": folder_id,
    }

