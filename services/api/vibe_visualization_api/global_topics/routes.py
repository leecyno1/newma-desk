from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from vibe_visualization_api.global_intel.runtime import Settings, get_settings, global_topic_scope
from vibe_visualization_api.global_topics.service import TOPICS, forecast, topic_snapshot
from vibe_visualization_api.global_topics.store import GlobalTopicStore


router = APIRouter(prefix="/api/global-topics", tags=["global-topics"])


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factors: dict[str, Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]] = Field(default_factory=dict, max_length=3)


def _require_topic(topic_id: str) -> None:
    if topic_id not in TOPICS:
        raise HTTPException(status_code=404, detail="专题不存在")


@router.get("/{topic_id}")
async def get_topic(topic_id: str, request: Request, scope=Depends(global_topic_scope)) -> dict:
    _require_topic(topic_id)
    evidence = await request.app.state.global_topic_sources.snapshot(topic_id)
    return topic_snapshot(topic_id, evidence)


@router.post("/{topic_id}/forecast")
def run_forecast(topic_id: str, request: ForecastRequest, settings: Settings = Depends(get_settings), scope=Depends(global_topic_scope)) -> dict:
    _require_topic(topic_id)
    valid_ids = {factor["id"] for factor in TOPICS[topic_id]["factors"]}
    if request.factors.keys() - valid_ids:
        raise HTTPException(422, "推演参数不属于当前专题")
    factors = {factor["id"]: request.factors.get(factor["id"], factor["value"]) for factor in TOPICS[topic_id]["factors"]}
    result = forecast(topic_id, factors)
    GlobalTopicStore(settings.database_path).save_forecast(
        topic_id, datetime.now(UTC).isoformat(), factors, result, scope=scope
    )
    return result
