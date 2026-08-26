from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..services.invitations_report import extract_invite_events


router = APIRouter(prefix="/api/reports/invitations", tags=["reports"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def invitations_report(
    year: int = Query(default=2025, ge=2000, le=2100),
    include_outgoing_seeds: bool = Query(default=False),
    mode: str = Query(default="speaker", description="all|speaker(direct-to-me)|speak(strict-speaker)"),
    window_before_hours: int = Query(default=24, ge=1, le=168),
    window_after_hours: int = Query(default=72, ge=1, le=168),
    merge_gap_hours: int = Query(default=12, ge=1, le=72),
    max_events: int = Query(default=2000, ge=1, le=20000),
    max_messages_per_event: int = Query(default=30, ge=5, le=200),
    limit: int = Query(default=200, ge=0, le=5000, description="How many events to return; 0 means only stats/meta."),
    db: Session = Depends(get_db),
):
    data = extract_invite_events(
        db,
        year=year,
        include_outgoing_seeds=include_outgoing_seeds,
        mode=mode,
        window_before_hours=window_before_hours,
        window_after_hours=window_after_hours,
        merge_gap_hours=merge_gap_hours,
        max_events=max_events,
        max_messages_per_event=max_messages_per_event,
    )
    if limit == 0:
        data["events"] = []
    else:
        data["events"] = (data.get("events") or [])[:limit]
    return data
