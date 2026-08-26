"""异常筛查器 API — 主动发现值得关注的基金变化。"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from services.anomaly_scanner_service import AnomalyScannerService

router = APIRouter(prefix="/api/anomalies", tags=["异常筛查"])


@router.get("/scan")
def scan_anomalies(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    """执行全量异常扫描。"""
    try:
        return AnomalyScannerService().scan(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"anomaly scan failed: {exc.__class__.__name__}") from exc
