from fastapi import APIRouter, Depends, Request

from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)
from vibe_visualization_api.model_gateway.service import ModelGatewayService


router = APIRouter(tags=["model-gateway"])


def get_model_gateway_service(request: Request) -> ModelGatewayService:
    return request.app.state.model_gateway_service


@router.get("/api/model/providers")
async def model_providers(
    service: ModelGatewayService = Depends(get_model_gateway_service),
) -> dict[str, object]:
    return {"providers": await service.describe_adapters()}


@router.post("/api/model/responses", response_model=ModelResponse)
async def create_model_response(
    response_request: ModelResponseCreate,
    service: ModelGatewayService = Depends(get_model_gateway_service),
) -> ModelResponse:
    return await service.create_response(response_request)
