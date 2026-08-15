import re

from fastapi import APIRouter, Depends, HTTPException, Query

from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.config import Settings, get_settings


router = APIRouter(prefix="/api/capital-flow", tags=["capital-flow"])


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
