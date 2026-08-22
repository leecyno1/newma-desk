import re

from fastapi import APIRouter, Depends, HTTPException, Query

from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.config import Settings, get_settings


router = APIRouter(prefix="/api/capital-flow", tags=["capital-flow"])


@router.get("/search")
async def search_capital_flow_security(
    query: str = Query(min_length=1, max_length=48),
    limit: int = Query(default=8, ge=1, le=20),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalFlowService(
        settings.research_base_url,
        timeout_seconds=settings.capital_flow_timeout_seconds,
    ).search_securities(query.strip(), limit)


@router.get("")
async def get_capital_flow(
    code: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    normalized = code.strip() if code else None
    if normalized and not re.fullmatch(r"\d{6}", normalized):
        raise HTTPException(422, "证券代码必须为 6 位数字")
    return await CapitalFlowService(
        settings.research_base_url,
        timeout_seconds=settings.capital_flow_timeout_seconds,
    ).dashboard(normalized)
