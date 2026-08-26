"""Historical analog route."""

from fastapi import APIRouter, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    QueryFiltersDependency,
    RequestContextDependency,
)
from seven_cycle_platform.api.repository import query_view
from seven_cycle_platform.api.schemas import APPROVED_ROUTE_RESPONSES, ResponseEnvelope


router = APIRouter(tags=["analogs"])


@router.get(
    "/analogs", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def historical_analogs(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    return envelope_response(
        request,
        context,
        query_view(context, "historical_analogs", filters),
        filters,
    )
