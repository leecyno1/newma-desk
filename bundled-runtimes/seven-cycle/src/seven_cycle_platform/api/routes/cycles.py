"""Cycle product routes."""

from fastapi import APIRouter, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    QueryFiltersDependency,
    RequestContextDependency,
)
from seven_cycle_platform.api.repository import query_view
from seven_cycle_platform.api.schemas import APPROVED_ROUTE_RESPONSES, ResponseEnvelope


router = APIRouter(prefix="/cycles", tags=["cycles"])


@router.get(
    "/current", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def current_cycles(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    return envelope_response(
        request, context, query_view(context, "cycle_current", filters), filters
    )


@router.get(
    "/history", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def cycle_history(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    return envelope_response(
        request, context, query_view(context, "cycle_history", filters), filters
    )


@router.get(
    "/forecast", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def cycle_forecast(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    return envelope_response(
        request, context, query_view(context, "cycle_forecast", filters), filters
    )
