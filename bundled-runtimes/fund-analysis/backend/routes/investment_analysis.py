"""
高级基金研究 API
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api/investment-analysis", tags=["高级基金研究"])


@router.get("/fund/{wind_code}/factor-lens")
def get_factor_lens(
    wind_code: str,
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        from services.investment_analysis_service import InvestmentAnalysisService

        return InvestmentAnalysisService().factor_lens(
            wind_code=wind_code,
            start_date=startDate,
            end_date=endDate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Investment analysis store unavailable: {exc.__class__.__name__}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/fund/{wind_code}/attribution")
def get_advanced_attribution(
    wind_code: str,
    benchmark: Optional[str] = Query(None),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        from services.investment_analysis_service import InvestmentAnalysisService

        return InvestmentAnalysisService().advanced_attribution(
            wind_code=wind_code,
            benchmark=benchmark,
            start_date=startDate,
            end_date=endDate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Investment analysis store unavailable: {exc.__class__.__name__}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
