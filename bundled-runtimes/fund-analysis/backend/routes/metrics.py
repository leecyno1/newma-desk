"""
指标快照 API
"""
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from repositories import get_metric_snapshot_repo
from services.metric_factory import MetricFactory
from services.manager_tenure_metric_service import ManagerTenureMetricService
from services.rolling_metric_service import RollingMetricService

router = APIRouter(prefix="/api/metrics", tags=["指标快照"])


@router.get("/health")
def metrics_health() -> Dict[str, str]:
    return {"status": "ok", "service": "metrics"}


@router.get("/fund/{fund_code}")
def get_fund_metrics(fund_code: str) -> Dict[str, Any]:
    """获取基金最新指标面板。"""
    repo = get_metric_snapshot_repo()
    try:
        metrics = repo.get_latest_panel("fund", fund_code)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Metric store unavailable: {exc.__class__.__name__}") from exc
    return {"fund_code": fund_code, "metrics": metrics, "count": len(metrics)}


@router.post("/fund/{fund_code}/recalculate")
def recalculate_fund_metrics(
    fund_code: str,
    as_of_date: Optional[date] = Query(None),
    window: Optional[str] = Query(None),
    source_snapshot_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """重算基金指标并保存为 MetricSnapshot。"""
    factory = MetricFactory()
    try:
        result = factory.calculate_and_save_fund_metrics(
            fund_code=fund_code,
            as_of_date=as_of_date,
            window=window,
            source_snapshot_id=source_snapshot_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Metric store unavailable: {exc.__class__.__name__}") from exc
    if result.get("saved", 0) == 0:
        raise HTTPException(status_code=404, detail="No NAV data available for fund")
    return result


@router.post("/fund/{fund_code}/rolling/recalculate")
def recalculate_fund_rolling_metrics(
    fund_code: str,
    source_snapshot_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """重算基金多窗口滚动指标并保存为 MetricSnapshot。"""
    service = RollingMetricService()
    try:
        result = service.calculate_and_save_for_fund(
            fund_code=fund_code,
            source_snapshot_id=source_snapshot_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Rolling metric calculation unavailable: {exc.__class__.__name__}") from exc
    if result.get("saved", 0) == 0:
        raise HTTPException(status_code=404, detail="No enough NAV data available for rolling metrics")
    return result


@router.post("/fund/{fund_code}/tenure/recalculate")
def recalculate_fund_tenure_metrics(
    fund_code: str,
    source_snapshot_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """按现任经理任期起点重算基金指标并保存为 MetricSnapshot。"""
    service = ManagerTenureMetricService()
    try:
        result = service.calculate_and_save_for_fund(
            fund_code=fund_code,
            source_snapshot_id=source_snapshot_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Tenure metric calculation unavailable: {exc.__class__.__name__}") from exc
    if result.get("saved", 0) == 0:
        raise HTTPException(status_code=404, detail=result.get("reason", "No enough tenure NAV data available"))
    return result
