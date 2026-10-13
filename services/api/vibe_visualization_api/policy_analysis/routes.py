from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.policy_analysis.service import build_policy_interpretation, policy_dashboard

router = APIRouter(prefix="/api/policy-analysis", tags=["policy-analysis"])


class PolicyAssessmentReview(BaseModel):
    level: int = Field(ge=1, le=3)
    note: str = Field(default="", max_length=300)


@router.get("")
async def get_policy_dashboard(
    as_of: date | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await policy_dashboard(
        as_of,
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
    )


@router.post("/refresh")
async def refresh_policy_dashboard(
    settings: Settings = Depends(get_settings),
) -> dict:
    return await policy_dashboard(
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
        refresh=True,
    )


@router.patch("/events/{event_id}/assessment")
async def review_policy_assessment(
    event_id: str,
    review: PolicyAssessmentReview,
    settings: Settings = Depends(get_settings),
) -> dict:
    from vibe_visualization_api.policy_analysis.store import PolicyStore

    event = PolicyStore(settings.database_path).review_assessment(
        event_id, review.level, review.note
    )
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    return event


@router.post("/events/{event_id}/interpretation")
async def interpret_policy_event(
    event_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    dashboard = await policy_dashboard(
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
    )
    event = next((item for item in dashboard["events"] if item["id"] == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    if event["status"] != "published":
        raise HTTPException(status_code=409, detail="只有已发布政策可以进行解读")
    related = [
        item
        for item in dashboard["events"]
        if item["id"] in event.get("relatedPolicyIds", [])
    ]
    return build_policy_interpretation(event, related)
