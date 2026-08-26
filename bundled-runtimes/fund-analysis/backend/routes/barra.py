"""旧 Barra 路由的统一归因兼容 Adapter。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api/barra", tags=["Barra风险分析"])


def _legacy_exposure_payload(bundle: Dict[str, Any]) -> Dict[str, Any]:
    barra = bundle.get("barra") or {}
    factor_exposures = barra.get("factor_exposures") or []
    return {
        "fund_code": (bundle.get("fund") or {}).get("wind_code"),
        "quarter": barra.get("quarter") or bundle.get("holding_snapshot_quarter"),
        "attribution_quarter": bundle.get("quarter"),
        "status": barra.get("status", "insufficient_evidence"),
        "source": barra.get("source", "evidence_gate"),
        "formal_model_ready": bool(barra.get("formal_model_ready")),
        "exposures": factor_exposures,
        "industry_exposures": barra.get("industry_exposures") or {},
        "risk_contributions": barra.get("risk_contributions") or [],
        "total_factor_risk": None,
        "specific_risk": None,
        "r_squared": barra.get("r_squared"),
        "num_holdings": barra.get("holdings_count", 0),
        "top10_weight": barra.get("holdings_disclosed_weight", 0),
        "missing_items": barra.get("missing_items") or [],
        "replacement_endpoint": f"/api/attribution/fund/{(bundle.get('fund') or {}).get('wind_code')}",
    }


def _run_attribution(fund_code: str, quarter: Optional[str]) -> Dict[str, Any]:
    from services.performance_attribution_service import PerformanceAttributionService

    return PerformanceAttributionService().analyze(wind_code=fund_code, quarter=quarter)


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        status_code = 404 if str(exc).startswith("Fund not found") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(status_code=503, detail=f"Attribution store unavailable: {exc.__class__.__name__}") from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/exposure/{fund_code}", deprecated=True)
async def get_barra_exposure(
    fund_code: str,
    quarter: Optional[str] = Query(None, description="归因季度，如 2026Q2"),
) -> Dict[str, Any]:
    """兼容旧调用方；结果由统一业绩归因 Module 生成。"""
    try:
        return _legacy_exposure_payload(_run_attribution(fund_code, quarter))
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/risk-decomposition/{fund_code}", deprecated=True)
async def get_risk_decomposition(
    fund_code: str,
    quarter: Optional[str] = Query(None, description="归因季度，如 2026Q2"),
) -> Dict[str, Any]:
    """兼容旧调用方；无正式协方差矩阵时不输出风险贡献。"""
    try:
        payload = _legacy_exposure_payload(_run_attribution(fund_code, quarter))
        return {
            "fund_code": payload["fund_code"],
            "quarter": payload["quarter"],
            "attribution_quarter": payload["attribution_quarter"],
            "status": payload["status"],
            "source": payload["source"],
            "formal_model_ready": payload["formal_model_ready"],
            "factor_risk": None,
            "specific_risk": None,
            "factor_risk_pct": None,
            "specific_risk_pct": None,
            "r_squared": payload["r_squared"],
            "risk_contributions": payload["risk_contributions"],
            "missing_items": payload["missing_items"],
            "replacement_endpoint": payload["replacement_endpoint"],
        }
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/score/{fund_code}", deprecated=True)
async def get_barra_score(
    fund_code: str,
    quarter: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """兼容旧调用方：Barra 不再生成基金评价分数。"""
    return {
        "fund_code": fund_code,
        "quarter": quarter,
        "status": "deprecated",
        "source": "methodology_scope",
        "role": "explanatory_evidence",
        "included_in_fund_evaluation_score": False,
        "overall_score": None,
        "grade": "not_applicable",
        "dimensions": {},
        "details": {},
        "replacement_endpoint": f"/api/funds/{fund_code}/evaluation",
        "missing_items": [
            "Barra 只用于解释风格暴露和风险来源，不单独判断基金优劣",
            "旧版手工加权 Barra 分数已停止输出",
        ],
    }
