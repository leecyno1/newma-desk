"""Cycle-state to asset-response surface routes."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    QueryFiltersDependency,
    RequestContextDependency,
)
from seven_cycle_platform.api.schemas import APPROVED_ROUTE_RESPONSES, ResponseEnvelope
from seven_cycle_platform.api.surface_repository import query_cycle_asset_surface


router = APIRouter(prefix="/surfaces", tags=["surfaces"])


@router.get(
    "/cycle-asset",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def cycle_asset_surface(
    request: Request,
    context: RequestContextDependency,
    filters: QueryFiltersDependency,
    asset_id: Annotated[str, Query(min_length=1, max_length=200)],
    cycle_x: Annotated[str, Query(pattern=r"^C[1-7]$")],
    cycle_y: Annotated[str, Query(pattern=r"^C[1-7]$")],
    window_months: Annotated[int, Query(ge=36, le=120)] = 60,
    grid_size: Annotated[int, Query(ge=9, le=41)] = 27,
):
    if cycle_x == cycle_y:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="cycle_x and cycle_y must differ")
    horizon = filters.horizon or 12
    scenario = filters.scenario or "baseline"
    result = query_cycle_asset_surface(
        context,
        asset_id=asset_id,
        cycle_x=cycle_x,
        cycle_y=cycle_y,
        horizon=horizon,
        scenario=scenario,
        window_months=window_months,
        grid_size=grid_size,
    )
    return envelope_response(
        request,
        context,
        result,
        filters,
        paginate=False,
        etag_extra={
            "asset_id": asset_id,
            "cycle_x": cycle_x,
            "cycle_y": cycle_y,
            "window_months": window_months,
            "grid_size": grid_size,
        },
    )
