"""旧 Brinson 路由的统一归因兼容 Adapter。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api/brinson", tags=["Brinson业绩归因"])


def _legacy_brinson_payload(bundle: Dict[str, Any]) -> Dict[str, Any]:
    brinson = bundle.get("brinson") or {}
    returns = brinson.get("returns") or {}
    effects = {
        item.get("name"): item.get("value")
        for item in brinson.get("effects") or []
        if item.get("name")
    }
    active_return = returns.get("active")
    fund_code = (bundle.get("fund") or {}).get("wind_code")
    return {
        "fund_code": fund_code,
        "benchmark": bundle.get("benchmark"),
        "benchmark_source": bundle.get("benchmark_source"),
        "quarter": bundle.get("quarter"),
        "holding_snapshot_quarter": bundle.get("holding_snapshot_quarter"),
        "status": brinson.get("status", "insufficient_evidence"),
        "source": brinson.get("source", "evidence_gate"),
        "returns": {
            "fund": returns.get("fund"),
            "portfolio": returns.get("fund"),
            "benchmark": returns.get("benchmark"),
            "active": active_return,
        },
        "attribution": {
            "allocation_effect": effects.get("allocation"),
            "selection_effect": effects.get("selection"),
            "interaction_effect": effects.get("interaction"),
            "residual": effects.get("residual"),
            "total": active_return if effects else None,
        },
        "industry_detail": brinson.get("industry_detail") or [],
        "coverage": brinson.get("coverage") or {},
        "missing_items": brinson.get("missing_items") or [],
        "replacement_endpoint": f"/api/attribution/fund/{fund_code}",
    }


def _run_attribution(
    fund_code: str,
    benchmark: Optional[str],
    quarter: Optional[str],
) -> Dict[str, Any]:
    from services.performance_attribution_service import PerformanceAttributionService

    return PerformanceAttributionService().analyze(
        wind_code=fund_code,
        benchmark=benchmark,
        quarter=quarter,
    )


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        status_code = 404 if str(exc).startswith("Fund not found") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(status_code=503, detail=f"Attribution store unavailable: {exc.__class__.__name__}") from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/attribution/{fund_code}", deprecated=True)
async def get_brinson_attribution(
    fund_code: str,
    benchmark: Optional[str] = Query(None, description="留空时使用基金分类目录基准"),
    quarter: Optional[str] = Query(None, description="归因季度，如 2026Q2"),
) -> Dict[str, Any]:
    """兼容旧调用方；结果由统一业绩归因 Module 生成。"""
    try:
        bundle = _run_attribution(fund_code, benchmark, quarter)
        return _legacy_brinson_payload(bundle)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/history/{fund_code}", deprecated=True)
async def get_brinson_history(
    fund_code: str,
    quarters: int = Query(8, ge=1, le=16, description="已弃用，仅保留参数兼容"),
) -> Dict[str, Any]:
    """停止用一年收益复制季度历史；历史分析应由用户逐季度现场运行。"""
    return {
        "fund_code": fund_code,
        "status": "deprecated",
        "source": "methodology_scope",
        "requested_quarters": quarters,
        "attributions": [],
        "summary": {
            "avg_allocation": None,
            "avg_selection": None,
            "total_active": None,
            "information_ratio": None,
        },
        "replacement_endpoint": f"/api/attribution/fund/{fund_code}?quarter=YYYYQ1",
        "missing_items": [
            "旧接口曾把同一个一年收益拆成多个季度，口径错误，现已停止输出",
            "需要历史归因时，请按季度现场运行统一业绩归因",
        ],
    }
