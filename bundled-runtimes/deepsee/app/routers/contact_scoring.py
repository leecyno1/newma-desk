from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..services.contact_scoring import (
    backfill_prediction_event_metadata,
    build_scoring_overview,
    evaluate_prediction_events_to_db,
    extract_prediction_events_to_db,
    get_focus_contact_ids,
    recompute_contact_scores,
    run_full_scoring_cycle,
)


router = APIRouter(prefix="/api/contact-scoring", tags=["contact-scoring"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return build_scoring_overview(db)


@router.post("/extract")
def extract(time_from: str | None = None, time_to: str | None = None, force: bool = False, db: Session = Depends(get_db)):
    return extract_prediction_events_to_db(
        db,
        time_from=_parse_dt(time_from),
        time_to=_parse_dt(time_to),
        force=force,
    )


@router.post("/evaluate")
def evaluate(as_of: str | None = None, db: Session = Depends(get_db)):
    return evaluate_prediction_events_to_db(db, as_of=_parse_dt(as_of))


@router.post("/backfill")
def backfill(limit: int | None = None, db: Session = Depends(get_db)):
    return backfill_prediction_event_metadata(db, limit=limit)


@router.post("/recompute")
def recompute(as_of: str | None = None, db: Session = Depends(get_db)):
    return recompute_contact_scores(db, as_of=_parse_dt(as_of))


@router.post("/run")
def run(time_from: str | None = None, time_to: str | None = None, force_extract: bool = False, as_of: str | None = None, db: Session = Depends(get_db)):
    return run_full_scoring_cycle(
        db,
        time_from=_parse_dt(time_from),
        time_to=_parse_dt(time_to),
        force_extract=force_extract,
        as_of=_parse_dt(as_of),
    )


@router.get("/focus")
def focus_contacts(db: Session = Depends(get_db)):
    ids = sorted(get_focus_contact_ids(db))
    return {"count": len(ids), "items": ids}
