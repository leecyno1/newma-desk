from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import SessionLocal
from ..models import Report
from ..schemas import ReportOut, ReportDetailOut


router = APIRouter(prefix="/api/reports", tags=["reports"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    items = db.execute(select(Report).order_by(Report.created_at.desc())).scalars().all()
    return [ReportOut.model_validate(i) for i in items]


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, "report not found")
    return ReportDetailOut.model_validate(rep)


@router.get("/{report_id}/export")
def export_report(report_id: int, format: str = "html", db: Session = Depends(get_db)):
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, "report not found")
    body = rep.result_body or ""
    if format == "markdown" or (format == "md"):
        return Response(content=body, media_type="text/markdown")
    return Response(content=body, media_type="text/html")
