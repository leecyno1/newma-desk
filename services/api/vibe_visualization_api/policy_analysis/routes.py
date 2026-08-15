from datetime import date

from fastapi import APIRouter, Depends, Query

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.policy_analysis.service import policy_dashboard

router = APIRouter(prefix="/api/policy-analysis", tags=["policy-analysis"])


@router.get("")
async def get_policy_dashboard(
    as_of: date | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await policy_dashboard(as_of, rsshub_base_url=settings.policy_rsshub_base_url, timeout_seconds=settings.policy_collector_timeout_seconds)
