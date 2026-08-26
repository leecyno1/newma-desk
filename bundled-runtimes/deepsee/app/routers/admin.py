from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import (
    AdapterMessage,
    AnalysisSnapshot,
    EmailMessage,
    Interaction,
    InteractionExt,
    Message,
    Report,
    ReportArtifact,
    SyncState,
    Task,
)
from ..services.aggregation_retention import prune_aggregation_data
from ..services.cache_cleanup import cleanup_application_cache
from ..services.deployment_status import summarize_diagnostics
from ..config import settings


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/aggregation-retention/prune")
def prune_aggregation_retention(payload: dict | None = None, db: Session = Depends(_get_db)):
    payload = payload or {}
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    days = payload.get("retention_days", 90)
    result = prune_aggregation_data(db, retention_days=days)
    db.commit()
    return result


@router.get("/diagnostics")
def diagnostics(db: Session = Depends(_get_db)):
    return {"status": "ok", "diagnostics": summarize_diagnostics(db)}


@router.post("/cache-cleanup")
def cache_cleanup(payload: dict | None = None, db: Session = Depends(_get_db)):
    payload = payload or {}
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    dry_run = bool(payload.get("dry_run", True))
    result = cleanup_application_cache(
        db,
        ttl_hours=int(payload.get("ttl_hours") or settings.__dict__.get("MEDIA_CACHE_TTL_HOURS", 720) or 720),
        max_mb=int(payload.get("max_mb") or settings.__dict__.get("MEDIA_CACHE_MAX_MB", 256) or 256),
        dry_run=dry_run,
    )
    if not dry_run:
        db.commit()
    return result


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None
    return None


def _in_range(col, start: datetime | None, end: datetime | None):
    if start and end:
        return (col >= start) & (col < end)
    if end:
        return col < end
    raise HTTPException(400, "require `to` (or `from`+`to`)")


@router.post("/cleanup")
def cleanup(payload: dict, db: Session = Depends(_get_db)):
    """Dangerous admin API: delete old records by time range.

    Body:
      {
        "from": "2025-01-01T00:00:00" (optional),
        "to":   "2025-12-01T00:00:00" (required),
        "types": ["messages","email_messages","adapter_messages","tasks","reports","snapshots","interactions","sync_cache"],
        "dry_run": true|false,
        "confirm": "DELETE" (required when dry_run=false)
      }
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")
    start = _parse_dt(payload.get("from"))
    end = _parse_dt(payload.get("to"))
    dry = bool(payload.get("dry_run", True))
    types = payload.get("types") or []
    if not isinstance(types, list) or not all(isinstance(x, str) for x in types):
        raise HTTPException(400, "invalid types")
    types = [t.strip() for t in types if t and t.strip()]
    if not end:
        raise HTTPException(400, "require `to` datetime")

    if not dry and str(payload.get("confirm") or "").strip().upper() != "DELETE":
        raise HTTPException(400, "missing confirm=DELETE")

    out: dict[str, Any] = {"status": "ok", "dry_run": dry, "from": start.isoformat() if start else None, "to": end.isoformat(), "deleted": {}}

    def _count(stmt) -> int:
        try:
            return int(db.execute(stmt).scalar() or 0)
        except Exception:
            return 0

    def _del(stmt, *, label: str) -> int:
        n = 0
        if dry:
            return 0
        try:
            res = db.execute(stmt)
            n = int(res.rowcount or 0)
        except Exception:
            db.rollback()
            raise
        return n

    # ---- messages ----
    if "messages" in types:
        cond = _in_range(Message.timestamp, start, end)
        cnt = _count(select(Message.id).where(cond))
        out["deleted"]["messages_count"] = cnt
        out["deleted"]["messages"] = _del(delete(Message).where(cond), label="messages")

    # ---- email messages ----
    if "email_messages" in types:
        cond = _in_range(EmailMessage.sent_at, start, end)
        cnt = _count(select(EmailMessage.id).where(cond))
        out["deleted"]["email_messages_count"] = cnt
        out["deleted"]["email_messages"] = _del(delete(EmailMessage).where(cond), label="email_messages")

    # ---- adapter messages ----
    if "adapter_messages" in types:
        cond = _in_range(AdapterMessage.timestamp, start, end)
        cnt = _count(select(AdapterMessage.id).where(cond))
        out["deleted"]["adapter_messages_count"] = cnt
        out["deleted"]["adapter_messages"] = _del(delete(AdapterMessage).where(cond), label="adapter_messages")

    # ---- tasks ----
    if "tasks" in types:
        cond = _in_range(Task.created_at, start, end)
        cnt = _count(select(Task.id).where(cond))
        out["deleted"]["tasks_count"] = cnt
        out["deleted"]["tasks"] = _del(delete(Task).where(cond), label="tasks")

    # ---- reports + artifacts ----
    if "reports" in types:
        cond = _in_range(Report.created_at, start, end)
        report_ids = [int(x) for x in db.execute(select(Report.id).where(cond)).scalars().all()]
        out["deleted"]["reports_count"] = len(report_ids)
        if report_ids:
            out["deleted"]["report_artifacts_count"] = len(
                db.execute(select(ReportArtifact.id).where(ReportArtifact.report_id.in_(report_ids))).all()
            )
            if not dry:
                _del(delete(ReportArtifact).where(ReportArtifact.report_id.in_(report_ids)), label="report_artifacts")
                _del(delete(Report).where(Report.id.in_(report_ids)), label="reports")
                out["deleted"]["reports"] = len(report_ids)
        else:
            out["deleted"]["report_artifacts_count"] = 0
            out["deleted"]["reports"] = 0

    # ---- analysis snapshots ----
    if "snapshots" in types:
        cond = _in_range(AnalysisSnapshot.created_at, start, end)
        cnt = _count(select(AnalysisSnapshot.id).where(cond))
        out["deleted"]["snapshots_count"] = cnt
        out["deleted"]["snapshots"] = _del(delete(AnalysisSnapshot).where(cond), label="snapshots")

    # ---- interactions ----
    if "interactions" in types:
        cond = _in_range(Interaction.created_at, start, end)
        cnt = _count(select(Interaction.id).where(cond))
        out["deleted"]["interactions_count"] = cnt
        out["deleted"]["interactions"] = _del(delete(Interaction).where(cond), label="interactions")

        cond2 = _in_range(InteractionExt.created_at, start, end)
        cnt2 = _count(select(InteractionExt.id).where(cond2))
        out["deleted"]["interactions_ext_count"] = cnt2
        out["deleted"]["interactions_ext"] = _del(delete(InteractionExt).where(cond2), label="interactions_ext")

    # ---- sync cache (best-effort; uses updated_at) ----
    if "sync_cache" in types:
        # Only remove known cache-like keys; keep user configs.
        patterns = ("summary_cache:", "minutes:", "news_snapshot:", "newsnow_cache:")
        q = select(SyncState.key).where(SyncState.updated_at < end)
        if start:
            q = q.where(SyncState.updated_at >= start)
        keys = [k for k in db.execute(q).scalars().all() if any(str(k).startswith(p) for p in patterns)]
        out["deleted"]["sync_cache_keys_count"] = len(keys)
        if keys and not dry:
            _del(delete(SyncState).where(SyncState.key.in_(keys)), label="sync_cache")
            out["deleted"]["sync_cache"] = len(keys)
        else:
            out["deleted"]["sync_cache"] = 0

    if not dry:
        db.commit()
    return out
