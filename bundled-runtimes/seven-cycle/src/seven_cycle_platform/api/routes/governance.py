"""Governance evidence and audit routes."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    DEFAULT_LIMIT,
    MAX_CYCLE_IDS,
    MAX_LIMIT,
    MAX_OFFSET,
    RequestContextDependency,
)
from seven_cycle_platform.api.repository import QueryResult, query_view
from seven_cycle_platform.api.schemas import (
    APPROVED_ROUTE_RESPONSES,
    QueryFilters,
    ResponseEnvelope,
)


router = APIRouter(prefix="/governance", tags=["governance"])

_COMMON_QUERY_PARAMETERS = frozenset({"as_of", "model_version", "limit", "offset"})
_CYCLE_QUERY_PARAMETERS = _COMMON_QUERY_PARAMETERS | {"cycle_ids"}
_JSON_FIELDS = {
    "cycle_evidence": (
        ("reason_codes_json", "reason_codes", "strings"),
        ("family_centers_json", "family_centers", "numbers"),
    ),
    "publication_gates": (("reason_codes_json", "reason_codes", "strings"),),
}


def _reject_unsupported_query_parameters(
    request: Request, allowed: frozenset[str]
) -> None:
    unsupported = sorted(set(request.query_params) - allowed)
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported query parameters: {', '.join(unsupported)}",
        )


def _bounded_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise HTTPException(status_code=422, detail=f"invalid {name}")
    return normalized


def _cycle_ids(value: str | None) -> tuple[str, ...]:
    normalized = tuple(
        item.strip() for item in (value or "").split(",") if item.strip()
    )
    if (
        len(normalized) > MAX_CYCLE_IDS
        or len(set(normalized)) != len(normalized)
        or any(len(item) > 64 for item in normalized)
    ):
        raise HTTPException(status_code=422, detail="invalid cycle_ids")
    return normalized


def _filters(
    *,
    as_of: date | None,
    model_version: str | None,
    cycle_ids: tuple[str, ...] = (),
    limit: int,
    offset: int,
) -> QueryFilters:
    return QueryFilters(
        as_of=as_of,
        vintage=None,
        model_version=_bounded_text(model_version, "model_version"),
        horizon=None,
        scenario=None,
        benchmark=None,
        asset_tier=None,
        cycle_ids=cycle_ids,
        limit=limit,
        offset=offset,
    )


def get_governance_cycle_filters(
    request: Request,
    as_of: Annotated[date | None, Query()] = None,
    model_version: Annotated[str | None, Query()] = None,
    cycle_ids: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> QueryFilters:
    """Parse only filters supported by cycle-scoped governance products."""

    _reject_unsupported_query_parameters(request, _CYCLE_QUERY_PARAMETERS)
    return _filters(
        as_of=as_of,
        model_version=model_version,
        cycle_ids=_cycle_ids(cycle_ids),
        limit=limit,
        offset=offset,
    )


def get_governance_common_filters(
    request: Request,
    as_of: Annotated[date | None, Query()] = None,
    model_version: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> QueryFilters:
    """Parse only filters supported by non-cycle governance products."""

    _reject_unsupported_query_parameters(request, _COMMON_QUERY_PARAMETERS)
    return _filters(
        as_of=as_of,
        model_version=model_version,
        limit=limit,
        offset=offset,
    )


GovernanceCycleFiltersDependency = Annotated[
    QueryFilters, Depends(get_governance_cycle_filters)
]
GovernanceCommonFiltersDependency = Annotated[
    QueryFilters, Depends(get_governance_common_filters)
]


def _decode_json_array(
    row: dict[str, object],
    *,
    view: str,
    source: str,
    item_kind: str,
) -> list[object]:
    raw_value = row.get(source)
    try:
        if not isinstance(raw_value, str):
            raise TypeError("JSON field must be a string")
        decoded = json.loads(raw_value)
        if not isinstance(decoded, list):
            raise TypeError("JSON field must contain an array")
        if item_kind == "strings":
            if not all(isinstance(item, str) for item in decoded):
                raise TypeError("JSON array must contain strings")
            return decoded
        if not all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in decoded
        ):
            raise TypeError("JSON array must contain finite numbers")
        return [float(item) for item in decoded]
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"published governance JSON is invalid: {view}.{source}",
        ) from error


def _decode_governance_result(result: QueryResult) -> QueryResult:
    field_specs = _JSON_FIELDS.get(result.view, ())
    if not field_specs:
        return result
    rows: list[dict[str, object]] = []
    for source_row in result.rows:
        row = dict(source_row)
        for source, target, item_kind in field_specs:
            row[target] = _decode_json_array(
                row,
                view=result.view,
                source=source,
                item_kind=item_kind,
            )
        rows.append(row)
    return replace(result, rows=rows)


def _respond(request, context, filters, view):
    result = _decode_governance_result(query_view(context, view, filters))
    return envelope_response(request, context, result, filters)


@router.get(
    "/evidence", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES
)
def evidence(
    request: Request,
    context: RequestContextDependency,
    filters: GovernanceCycleFiltersDependency,
):
    return _respond(request, context, filters, "cycle_evidence")


@router.get(
    "/publication",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def publication(
    request: Request,
    context: RequestContextDependency,
    filters: GovernanceCycleFiltersDependency,
):
    return _respond(request, context, filters, "publication_gates")


@router.get(
    "/data-identity",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def data_identity(
    request: Request,
    context: RequestContextDependency,
    filters: GovernanceCommonFiltersDependency,
):
    return _respond(request, context, filters, "data_identity")


@router.get(
    "/calibrations",
    response_model=ResponseEnvelope,
    responses=APPROVED_ROUTE_RESPONSES,
)
def calibrations(
    request: Request,
    context: RequestContextDependency,
    filters: GovernanceCommonFiltersDependency,
):
    return _respond(request, context, filters, "calibration_log")
