"""Asset index, comparison, attribution, and mapping routes."""

from fastapi import APIRouter, Path, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    QueryFiltersDependency,
    RequestContextDependency,
)
from seven_cycle_platform.api.repository import query_view
from seven_cycle_platform.api.schemas import APPROVED_ROUTE_RESPONSES, ResponseEnvelope


router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES)
def list_assets(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    return envelope_response(
        request, context, query_view(context, "assets", filters), filters
    )


@router.get(
    "/compare", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def compare_assets(
    request: Request, context: RequestContextDependency, filters: QueryFiltersDependency
):
    view = (
        "asset_mapping_future"
        if filters.scenario is not None
        else "asset_mapping_current"
    )
    return envelope_response(
        request, context, query_view(context, view, filters), filters
    )


@router.get(
    "/{asset_id}/attribution",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def asset_attribution(
    request: Request,
    context: RequestContextDependency,
    filters: QueryFiltersDependency,
    asset_id: str = Path(min_length=1, max_length=200),
):
    return envelope_response(
        request,
        context,
        query_view(context, "attribution", filters, asset_id=asset_id),
        filters,
    )


@router.get(
    "/{asset_id}/mapping",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def asset_mapping(
    request: Request,
    context: RequestContextDependency,
    filters: QueryFiltersDependency,
    asset_id: str = Path(min_length=1, max_length=200),
):
    view = (
        "asset_mapping_future"
        if filters.scenario is not None
        else "asset_mapping_current"
    )
    return envelope_response(
        request,
        context,
        query_view(context, view, filters, asset_id=asset_id),
        filters,
    )
