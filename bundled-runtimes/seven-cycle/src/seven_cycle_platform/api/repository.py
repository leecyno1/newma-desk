"""Allow-listed, parameterized read-only catalog queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from seven_cycle_platform.api.dependencies import RequestContext
from seven_cycle_platform.api.schemas import QueryFilters


_VIEWS = frozenset(
    {
        "runs",
        "cycle_current",
        "cycle_history",
        "cycle_forecast",
        "assets",
        "attribution",
        "asset_mapping_current",
        "asset_mapping_future",
        "cycle_asset_surface",
        "historical_analogs",
        "scenarios",
        "cycle_evidence",
        "data_identity",
        "publication_gates",
        "calibration_log",
    }
)
_ORDER_COLUMNS = (
    "asset_id",
    "cycle_id",
    "entity_id",
    "scenario_id",
    "layer",
    "date",
    "calibration_date",
    "forecast_date",
    "future_date",
    "period_end",
    "historical_date",
    "horizon_months",
    "component_type",
    "component_id",
    "subject_id",
    "analog_rank",
    "run_id",
)
_PRIMARY_STATUS_COLUMNS = {
    "cycle_forecast": "status",
    "asset_mapping_current": "mapping_status",
    "asset_mapping_future": "mapping_status",
    "cycle_asset_surface": "status",
    "attribution": "status",
    "historical_analogs": "status",
    "publication_gates": "status",
}
_PUBLICATION_LAYER_ORDER = (
    "historical",
    "realtime",
    "forecast",
    "asset_statistics",
)


@dataclass(frozen=True, slots=True)
class QueryResult:
    rows: list[dict[str, Any]]
    total: int
    available: bool
    view: str
    primary_usage_statuses: tuple[str, ...]


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _columns(context: RequestContext, view: str) -> set[str]:
    if view not in _VIEWS:
        raise ValueError("view is not approved")
    try:
        return {
            row[0]
            for row in context.connection.execute(
                f"DESCRIBE {_quote_identifier(view)}"
            ).fetchall()
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="published data is temporarily unavailable",
        ) from error


def _is_available(context: RequestContext, view: str) -> bool:
    try:
        row = context.connection.execute(
            "SELECT available FROM _catalog_views WHERE view_name = ?",
            [view],
        ).fetchone()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="published data is temporarily unavailable",
        ) from error
    return bool(row and row[0])


def _require_filter_column(columns: set[str], column: str, parameter: str) -> None:
    if column not in columns:
        raise HTTPException(
            status_code=422,
            detail=f"{parameter} is unavailable for this product",
        )


def _filters(
    columns: set[str],
    filters: QueryFilters,
    *,
    asset_id: str | None,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    values: list[object] = []

    def append(column: str, value: object, parameter: str) -> None:
        _require_filter_column(columns, column, parameter)
        clauses.append(f"{_quote_identifier(column)} = ?")
        values.append(value)

    if asset_id is not None:
        append("asset_id", asset_id, "asset_id")
    if filters.as_of is not None:
        append("as_of", filters.as_of, "as_of")
    if filters.vintage is not None:
        append("vintage", filters.vintage, "vintage")
    if filters.model_version is not None:
        append("model_version", filters.model_version, "model_version")
    if filters.horizon is not None:
        append("horizon_months", filters.horizon, "horizon")
    if filters.scenario is not None:
        append("scenario_id", filters.scenario, "scenario")
    if filters.benchmark is not None:
        append("benchmark", filters.benchmark, "benchmark")
    if filters.asset_tier is not None:
        append("asset_tier", filters.asset_tier, "asset_tier")
    if filters.cycle_ids:
        _require_filter_column(columns, "cycle_id", "cycle_ids")
        placeholders = ", ".join("?" for _ in filters.cycle_ids)
        clauses.append(f"{_quote_identifier('cycle_id')} IN ({placeholders})")
        values.extend(filters.cycle_ids)
    return clauses, values


def _primary_usage_statuses(
    view: str,
    rows: list[dict[str, Any]],
) -> tuple[str, ...]:
    """Extract only the documented top-level usage state for a product."""

    primary_column = _PRIMARY_STATUS_COLUMNS.get(view)
    if primary_column is None:
        return ()
    statuses: list[str] = []
    for row in rows:
        primary_value = row.get(primary_column)
        if primary_value is None:
            continue
        status = str(primary_value).casefold()
        if view == "asset_mapping_future":
            product_status = row.get("status")
            if product_status is not None and str(product_status).casefold() in {
                "blocked",
                "unavailable",
            }:
                status = str(product_status).casefold()
        statuses.append(status)
    return tuple(statuses)


def _order_sql(view: str, columns: set[str]) -> str:
    if view == "publication_gates" and {"cycle_id", "layer"} <= columns:
        quoted_layer = _quote_identifier("layer")
        layer_rank = (
            "CASE "
            + quoted_layer
            + " "
            + " ".join(
                f"WHEN '{layer}' THEN {rank}"
                for rank, layer in enumerate(_PUBLICATION_LAYER_ORDER)
            )
        )
        layer_rank += f" ELSE {len(_PUBLICATION_LAYER_ORDER)} END"
        tie_breakers = [
            column
            for column in (
                "layer",
                "status",
                "reason_codes_json",
                "run_id",
                "as_of",
                "model_version",
                "config_hash",
                "created_at",
            )
            if column in columns
        ]
        terms = [
            _quote_identifier("cycle_id"),
            layer_rank,
            *(_quote_identifier(column) for column in tie_breakers),
        ]
        return " ORDER BY " + ", ".join(terms)
    order_columns = [column for column in _ORDER_COLUMNS if column in columns]
    return (
        " ORDER BY " + ", ".join(_quote_identifier(column) for column in order_columns)
        if order_columns
        else ""
    )


def query_view(
    context: RequestContext,
    view: str,
    filters: QueryFilters,
    *,
    asset_id: str | None = None,
    paginate: bool = True,
) -> QueryResult:
    """Read one stable view with fixed projection, filtering, and ordering."""

    columns = _columns(context, view)
    available = _is_available(context, view)
    clauses, values = _filters(columns, filters, asset_id=asset_id)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    quoted_view = _quote_identifier(view)
    order_sql = _order_sql(view, columns)
    try:
        total = int(
            context.connection.execute(
                f"SELECT count(*) FROM {quoted_view}{where_sql}", values
            ).fetchone()[0]
        )
        query = f"SELECT * FROM {quoted_view}{where_sql}{order_sql}"
        parameters = list(values)
        if paginate:
            query += " LIMIT ? OFFSET ?"
            parameters.extend([filters.limit, filters.offset])
        rows = (
            context.connection.execute(query, parameters)
            .fetch_arrow_table()
            .to_pylist()
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="published data is temporarily unavailable",
        ) from error
    return QueryResult(
        rows=rows,
        total=total,
        available=available,
        view=view,
        primary_usage_statuses=_primary_usage_statuses(view, rows),
    )
