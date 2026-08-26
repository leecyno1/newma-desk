from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    AnalysisSnapshot,
    ContactScoreSnapshot,
    ContactValueMetricSnapshot,
    Report,
    Task,
)

DEFAULT_RETENTION_DAYS = 90

_DATASET_PREFIXES = (
    "messages_",
    "summaries_",
    "news_snapshot_",
)


def _coerce_retention_days(value: int | None) -> int:
    try:
        days = int(value or DEFAULT_RETENTION_DAYS)
    except Exception:
        days = DEFAULT_RETENTION_DAYS
    return max(1, days)


def prune_aggregation_data(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int | None = DEFAULT_RETENTION_DAYS,
    datasets_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Delete derived aggregation/snapshot rows older than the retention window.

    Raw source data such as messages, contacts and emails is intentionally left intact.
    """
    effective_now = now or datetime.utcnow()
    days = _coerce_retention_days(retention_days)
    cutoff = effective_now - timedelta(days=days)

    deleted: dict[str, int] = {}

    targets = [
        ("analysis_snapshots", AnalysisSnapshot, AnalysisSnapshot.created_at),
        ("tasks", Task, Task.created_at),
        ("contact_score_snapshots", ContactScoreSnapshot, ContactScoreSnapshot.as_of),
        ("contact_value_metric_snapshots", ContactValueMetricSnapshot, ContactValueMetricSnapshot.as_of),
    ]

    for name, model, column in targets:
        result = db.execute(delete(model).where(column < cutoff))
        deleted[name] = int(result.rowcount or 0)

    old_report_ids = list(db.execute(select(Report.id).where(Report.created_at < cutoff)).scalars().all())
    if old_report_ids:
        from ..models import ReportArtifact

        artifact_result = db.execute(delete(ReportArtifact).where(ReportArtifact.report_id.in_(old_report_ids)))
        deleted["report_artifacts"] = int(artifact_result.rowcount or 0)
        report_result = db.execute(delete(Report).where(Report.id.in_(old_report_ids)))
        deleted["reports"] = int(report_result.rowcount or 0)
    else:
        deleted["report_artifacts"] = 0
        deleted["reports"] = 0

    deleted["dataset_files"] = _prune_dataset_files(datasets_dir, cutoff)

    return {
        "status": "ok",
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "deleted": deleted,
    }


def _prune_dataset_files(datasets_dir: str | Path | None, cutoff: datetime) -> int:
    base = Path(datasets_dir or Path.cwd() / "data" / "datasets")
    if not base.exists() or not base.is_dir():
        return 0
    cutoff_ts = cutoff.timestamp()
    removed = 0
    for path in base.iterdir():
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        if not path.name.startswith(_DATASET_PREFIXES):
            continue
        try:
            if path.stat().st_mtime >= cutoff_ts:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed
