"""统一基金业绩归因路由。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api/attribution", tags=["基金业绩归因"])


@router.get("/fund/{wind_code}")
def get_fund_attribution(
    wind_code: str,
    benchmark: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None, description="归因季度，如 2026Q2"),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        from services.performance_attribution_service import PerformanceAttributionService

        return PerformanceAttributionService().analyze(
            wind_code=wind_code,
            benchmark=benchmark,
            quarter=quarter,
            start_date=startDate,
            end_date=endDate,
        )
    except ValueError as exc:
        status_code = 404 if str(exc).startswith("Fund not found") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Attribution store unavailable: {exc.__class__.__name__}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/fund/{wind_code}/history")
def get_fund_attribution_history(
    wind_code: str,
    limit: int = Query(8, ge=1, le=40),
) -> Dict[str, Any]:
    try:
        from repositories import get_attribution_repo

        rows = get_attribution_repo().list_history(wind_code, limit)
        return {
            "wind_code": wind_code,
            "count": len(rows),
            "history": rows,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Attribution store unavailable: {exc.__class__.__name__}") from exc
