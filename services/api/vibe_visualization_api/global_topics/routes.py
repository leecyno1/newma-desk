from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.global_topics.service import TOPICS, forecast, topic_snapshot
from vibe_visualization_api.global_topics.store import GlobalTopicStore


router = APIRouter(prefix="/api/global-topics", tags=["global-topics"])


class ForecastRequest(BaseModel):
    factors: dict[str, float] = Field(default_factory=dict)


def _require_topic(topic_id: str) -> None:
    if topic_id not in TOPICS:
        raise HTTPException(status_code=404, detail="专题不存在")


@router.get("/{topic_id}")
async def get_topic(topic_id: str, request: Request) -> dict:
    _require_topic(topic_id)
    evidence = await request.app.state.global_topic_sources.snapshot(topic_id)
    return topic_snapshot(topic_id, evidence)


@router.post("/{topic_id}/forecast")
def run_forecast(topic_id: str, request: ForecastRequest, settings: Settings = Depends(get_settings)) -> dict:
    _require_topic(topic_id)
    valid_ids = {factor["id"] for factor in TOPICS[topic_id]["factors"]}
    factors = {key: value for key, value in request.factors.items() if key in valid_ids}
    result = forecast(topic_id, factors)
    GlobalTopicStore(settings.database_path).save_forecast(
        topic_id, datetime.now(UTC).isoformat(), factors, result
    )
    return result
