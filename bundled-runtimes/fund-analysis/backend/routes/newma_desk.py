"""Newma Desk 数据能力入口。"""
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from routes.funds import _clean_nan


router = APIRouter(prefix="/api/newma-desk", tags=["Newma Desk"])


class FundSearchRequest(BaseModel):
    search: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
    peer_group: str = ""
    availability: Literal["evaluated", "classified", "all"] = "all"


class FundSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    window: Literal["1y", "3y", "5y"] = "1y"


class FundCompareRequest(BaseModel):
    windCodes: list[str] = Field(min_length=2, max_length=12)
    window: Literal["1y", "3y", "5y"] = "1y"


class FundAttributionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    quarter: Optional[str] = Field(default=None, max_length=8)
    benchmark: Optional[str] = Field(default=None, max_length=80)


class FundAnalysisRequest(BaseModel):
    windCode: str = Field(min_length=1, max_length=24)
    question: str = Field(default="", max_length=1000)


class FundRecommendationRequest(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    style: Optional[str] = Field(default=None, max_length=80)


@router.get("/health")
def health():
    from database import check_database_health

    database = check_database_health(min_fund_count=1)
    return {
        "ok": database.get("status") == "ok",
        "service": "fund-analysis-data",
        "database": database,
    }


@router.post("/fund-search")
def fund_search(payload: FundSearchRequest):
    from services.fund_browser_service import FundBrowserService

    return _clean_nan(FundBrowserService().browse(
        keyword=payload.search or None,
        peer_group=payload.peer_group or None,
        page=payload.page,
        page_size=payload.page_size,
        availability=payload.availability,
    ))


@router.post("/fund-research-snapshot")
def fund_research_snapshot(payload: FundSymbolRequest):
    from services.fund_research_snapshot_service import FundResearchSnapshotService

    return _clean_nan(FundResearchSnapshotService().build(
        payload.symbol,
        window=payload.window,
        include_research=True,
        include_attribution=True,
    ))


@router.post("/fund-risk-evidence")
def fund_risk_evidence(payload: FundSymbolRequest):
    """只投影本地已有证据，不触发同步、回归计算或 AI。"""
    from repositories import get_fund_repo
    from services.fund_bond_duration_service import FundBondDurationService

    repo = get_fund_repo()
    symbol = payload.symbol.strip().upper()
    candidates = [symbol] + ([f"{symbol}.{suffix}" for suffix in ("OF", "SH", "SZ")] if len(symbol) == 6 and symbol.isdigit() else [])
    matches = {str(f["wind_code"]): f for code in candidates if (f := repo.get_fund_by_identifier(code))}
    if not matches:
        return {"status": "not_found", "symbol": payload.symbol}
    if len(matches) > 1:
        return {"status": "ambiguous", "symbol": payload.symbol}
    fund = next(iter(matches.values()))
    code = str(fund["wind_code"])
    duration = FundBondDurationService().get(code)
    return _clean_nan({
        "status": "available", "symbol": code,
        "name": fund.get("fund_name") or fund.get("name"),
        "source": "fund-analysis.local",
        "duration": {key: duration.get(key) for key in (
            "status", "as_of_date", "estimated_duration", "r_squared",
            "observations", "methodology_version", "source", "source_url",
            "limitations", "missing_items",
        )},
    })


@router.post("/fund-compare")
def fund_compare(payload: FundCompareRequest):
    from services.peer_comparison_service import PeerComparisonService

    return _clean_nan(PeerComparisonService().build_comparison_matrix(
        payload.windCodes,
        window=payload.window,
    ))


@router.post("/fund-attribution")
def fund_attribution(payload: FundAttributionRequest):
    from services.performance_attribution_service import PerformanceAttributionService

    return _clean_nan(PerformanceAttributionService().analyze(
        wind_code=payload.symbol,
        quarter=payload.quarter,
        benchmark=payload.benchmark,
    ))


@router.post("/fund-analysis")
async def fund_analysis(payload: FundAnalysisRequest):
    from routes.reports import FundEvaluationAnalysisRequest, generate_fund_evaluation_analysis

    return await generate_fund_evaluation_analysis(
        payload.windCode,
        FundEvaluationAnalysisRequest(question=payload.question, include_research=True),
    )


@router.post("/fund-recommendations")
def fund_recommendations(payload: FundRecommendationRequest):
    from services.fund_recommendation_service import FundRecommendationService
    from services.fund_research_snapshot_service import FundResearchSnapshotService

    result = FundRecommendationService().build_candidate_group(
        peer_group=payload.category,
        style=payload.style,
        limit=10,
    )
    result["candidates"] = [
        FundResearchSnapshotService.candidate_snapshot(candidate)
        for candidate in result.get("candidates") or []
    ]
    return _clean_nan(result)
