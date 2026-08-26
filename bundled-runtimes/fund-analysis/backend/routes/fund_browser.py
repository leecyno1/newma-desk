"""基金浏览器路由。"""
from typing import Optional

from fastapi import APIRouter, Query

from services.fund_browser_service import FundBrowserService


router = APIRouter(prefix="/api/fund-browser", tags=["基金浏览器"])


@router.get("")
async def browse_funds(
    keyword: Optional[str] = Query(None),
    peer_group: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    asset_min: Optional[float] = Query(None, ge=0),
    min_age_years: Optional[int] = Query(None, ge=0, le=50),
    min_manager_years: Optional[float] = Query(None, ge=0, le=50),
    return_6m_min: Optional[float] = Query(None),
    return_1y_min: Optional[float] = Query(None),
    return_3y_min: Optional[float] = Query(None),
    max_drawdown_1y_max: Optional[float] = Query(None, ge=0, le=1),
    sharpe_1y_min: Optional[float] = Query(None),
    style_tags: Optional[str] = Query(None, description="逗号分隔的风格标签"),
    style_match: str = Query("any", pattern="^(any|all)$"),
    availability: str = Query("evaluated", pattern="^(evaluated|classified|all)$"),
    sort_by: str = Query("quality", pattern="^(quality|return|return_6m|return_1y|return_3y|multi_period|drawdown|sharpe|asset|history)$"),
):
    return FundBrowserService().browse(
        keyword=keyword,
        peer_group=peer_group,
        page=page,
        page_size=page_size,
        asset_min=asset_min,
        min_age_years=min_age_years,
        min_manager_years=min_manager_years,
        return_6m_min=return_6m_min,
        return_1y_min=return_1y_min,
        return_3y_min=return_3y_min,
        max_drawdown_1y_max=max_drawdown_1y_max,
        sharpe_1y_min=sharpe_1y_min,
        style_tags=[item.strip() for item in (style_tags or "").split(",") if item.strip()],
        style_match=style_match,
        availability=availability,
        sort_by=sort_by,
    )
