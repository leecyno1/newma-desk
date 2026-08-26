"""FastAPI application factory for local immutable catalog queries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from seven_cycle_platform.api.dependencies import RequestContext
from seven_cycle_platform.api.repository import QueryResult
from seven_cycle_platform.api.schemas import Pagination, QueryFilters, ResponseEnvelope
from seven_cycle_platform.storage.run_context import canonical_json_bytes


CACHE_CONTROL = "private, max-age=0, must-revalidate"


def _row_caveats(rows: list[dict[str, Any]]) -> list[str]:
    caveats: set[str] = set()
    for row in rows:
        for key, value in row.items():
            normalized_key = key.casefold()
            if not value or normalized_key.endswith("_json"):
                continue
            if normalized_key == "reason_codes" or normalized_key.endswith(
                "_reason_codes"
            ):
                values = value if isinstance(value, (list, tuple, set)) else (value,)
            elif (
                "caveat" in normalized_key
                or normalized_key == "reason"
                or normalized_key.endswith("_reason")
            ):
                values = value if isinstance(value, (list, tuple, set)) else (value,)
            else:
                continue
            caveats.update(str(item) for item in values if item)
    return sorted(caveats)


def _objective_status(result: QueryResult) -> tuple[str, str, list[str]]:
    """Summarize status only from product rows and availability metadata."""

    if not result.available:
        return "unavailable", "unavailable", ["requested product is unavailable"]
    if not result.rows:
        return "available", "unknown", ["no rows matched the requested filters"]
    statuses = set(result.primary_usage_statuses)
    caveats = _row_caveats(result.rows)
    if "blocked" in statuses:
        usage_status = "blocked"
    elif len(statuses) == 1 and statuses <= {
        "available",
        "formal",
        "conditional",
        "partial",
        "unavailable",
        "retrospective_only",
    }:
        usage_status = next(iter(statuses))
    elif {"unavailable", "partial", "retrospective_only"} & statuses:
        usage_status = "partial"
    elif statuses <= {"formal", "available"}:
        usage_status = "formal" if "formal" in statuses else "available"
    else:
        usage_status = "partial"
    freshness_values = {
        str(row["freshness_status"]).casefold()
        for row in result.rows
        if row.get("freshness_status") is not None
    }
    if "stale" in freshness_values:
        freshness = "stale"
    elif freshness_values == {"fresh"}:
        freshness = "fresh"
    else:
        freshness = "unknown"
    return usage_status, freshness, caveats


def _etag(
    context: RequestContext,
    request: Request,
    filters: QueryFilters,
    payload: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> str:
    material = canonical_json_bytes(
        {
            "catalog_checksum": context.catalog_checksum,
            "manifest_checksum": context.manifest_checksum,
            "path": request.url.path,
            "payload": payload,
            "query": filters.etag_parameters(),
            "extra": extra or {},
        }
    )
    return f'"{hashlib.sha256(material).hexdigest()}"'


def _if_none_match_matches(value: str | None, etag: str) -> bool:
    """Recognize standard wildcard, weak, and comma-separated ETag validators."""

    if value is None:
        return False
    for candidate in value.split(","):
        normalized = candidate.strip()
        if normalized == "*":
            return True
        if normalized.startswith("W/"):
            normalized = normalized[2:].strip()
        if normalized == etag:
            return True
    return False


def envelope_response(
    request: Request,
    context: RequestContext,
    result: QueryResult,
    filters: QueryFilters,
    *,
    paginate: bool = True,
    etag_extra: dict[str, Any] | None = None,
) -> Response:
    """Build one validated envelope and handle conditional GET responses."""

    usage_status, freshness, caveats = _objective_status(result)
    row_provenance = {
        "run_id": context.manifest.run_id,
        "as_of": context.manifest.as_of,
        "data_vintage": context.manifest.data_vintage,
        "model_version": context.manifest.model_version,
        "config_hash": context.manifest.config_hash,
    }
    rows = [{**row_provenance, **row} for row in result.rows]
    envelope = ResponseEnvelope(
        data=jsonable_encoder(rows),
        provenance={
            "run_id": context.manifest.run_id,
            "as_of": context.manifest.as_of,
            "data_vintage": context.manifest.data_vintage,
            "model_version": context.manifest.model_version,
            "config_hash": context.manifest.config_hash,
            "manifest_checksum": context.manifest_checksum,
            "catalog_checksum": context.catalog_checksum,
            "quality_summary": jsonable_encoder(dict(context.manifest.quality_summary)),
            "data_quality": jsonable_encoder(dict(context.manifest.quality_summary)),
        },
        freshness=freshness,
        usage_status=usage_status,
        caveats=caveats,
        pagination=(
            Pagination(limit=filters.limit, offset=filters.offset, total=result.total)
            if paginate
            else None
        ),
    )
    payload = envelope.model_dump(mode="json", exclude_none=True)
    etag = _etag(context, request, filters, payload, etag_extra)
    headers = {
        "Cache-Control": CACHE_CONTROL,
        "ETag": etag,
        "X-Catalog-Checksum": context.catalog_checksum,
        "X-Manifest-Checksum": context.manifest_checksum,
        "X-Config-Hash": context.manifest.config_hash,
    }
    if _if_none_match_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)


def _error_response(request: Request, status_code: int) -> JSONResponse:
    """Return a redacted envelope for controlled API failures."""

    if status_code == 422:
        caveat = "request parameters are invalid or unavailable for this product"
    elif status_code == 404:
        caveat = "requested endpoint was not found"
    else:
        caveat = "published data is temporarily unavailable"
    envelope = ResponseEnvelope(
        data=[],
        provenance={},
        freshness="unavailable",
        usage_status="unavailable",
        caveats=[caveat],
    )
    payload = envelope.model_dump(mode="json", exclude_none=True)
    etag_material = canonical_json_bytes(
        {"path": request.url.path, "payload": payload, "status_code": status_code}
    )
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "Cache-Control": CACHE_CONTROL,
            "ETag": f'"{hashlib.sha256(etag_material).hexdigest()}"',
        },
    )


def create_app(
    *,
    product_root: Path | str = Path("products/seven_cycle"),
    catalog_root: Path | str | None = None,
    web_root: Path | str | None = None,
) -> FastAPI:
    """Create a local-only application without opening data at import time."""

    normalized_product_root = Path(product_root)
    app = FastAPI(
        title="Seven Cycle Platform",
        version="v1",
        docs_url=None,
        redoc_url=None,
    )
    app.state.product_root = normalized_product_root
    app.state.catalog_root = (
        Path(catalog_root)
        if catalog_root is not None
        else normalized_product_root / "catalogs"
    )
    normalized_web_root = Path(web_root).resolve(strict=True) if web_root else None
    if normalized_web_root is not None:
        web_root_stat = normalized_web_root.lstat()
        if not stat.S_ISDIR(web_root_stat.st_mode):
            raise ValueError("web root must be a real directory")
        index_path = normalized_web_root / "index.html"
        index_stat = index_path.lstat()
        if not stat.S_ISREG(index_stat.st_mode):
            raise ValueError("web root must contain index.html")
    app.state.web_root = normalized_web_root

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exception: HTTPException
    ) -> JSONResponse:
        return _error_response(request, exception.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(request, exception.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        return _error_response(request, 422)

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request, exception: Exception
    ) -> JSONResponse:
        return _error_response(request, 503)

    from seven_cycle_platform.api.routes import (
        analogs,
        assets,
        cycles,
        governance,
        runs,
        scenarios,
        surfaces,
    )

    app.include_router(runs.router, prefix="/v1")
    app.include_router(cycles.router, prefix="/v1")
    app.include_router(assets.router, prefix="/v1")
    app.include_router(analogs.router, prefix="/v1")
    app.include_router(scenarios.router, prefix="/v1")
    app.include_router(surfaces.router, prefix="/v1")
    app.include_router(governance.router, prefix="/v1")

    from seven_cycle_platform.api.dependencies import (
        HealthContext,
        HealthContextCache,
        get_health_context,
    )

    app.state.health_context_cache = HealthContextCache()

    @app.get("/healthz", include_in_schema=False)
    def healthz(
        context: HealthContext = Depends(get_health_context),
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "catalog": "available",
            "run_id": context.manifest.run_id,
            "service": "seven-cycle-platform",
            "status": "ok",
            "web": "available" if normalized_web_root is not None else "disabled",
        }
        deployment_path = normalized_product_root / "deployment.json"
        web_deployment_path = (
            normalized_web_root / "data" / "deployment.json"
            if normalized_web_root is not None
            else None
        )
        product_deployment_exists = deployment_path.is_file()
        web_deployment_exists = (
            web_deployment_path.is_file()
            if web_deployment_path is not None
            else False
        )
        if not product_deployment_exists and (
            web_deployment_path is None or not web_deployment_exists
        ):
            payload["deployment"] = "disabled"
            return payload
        if not product_deployment_exists:
            payload["deployment"] = "inconsistent"
            payload["status"] = "degraded"
            return payload
        try:
            deployment_bytes = deployment_path.read_bytes()
            deployment = json.loads(deployment_bytes)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            payload["deployment"] = "invalid"
            payload["status"] = "degraded"
            return payload
        web_deployment_matches = True
        if web_deployment_path is not None and web_deployment_exists:
            try:
                web_deployment_matches = (
                    web_deployment_path.read_bytes() == deployment_bytes
                )
            except OSError:
                web_deployment_matches = False
        if (
            isinstance(deployment, dict)
            and deployment.get("api_run_id") == context.manifest.run_id
            and deployment.get("catalog_checksum") == context.catalog_checksum
            and isinstance(deployment.get("deployment_id"), str)
            and web_deployment_matches
        ):
            payload["deployment"] = "available"
            payload["deployment_as_of"] = deployment.get("deployment_as_of")
            payload["deployment_id"] = deployment["deployment_id"]
            if web_deployment_path is not None and not web_deployment_exists:
                # A direct Vite build replaces web/dist and may omit the paired
                # audit copy. The API identity is still verified by the product
                # manifest; report the reduced verification scope without
                # making the otherwise usable local Mod fail its health probe.
                payload["deployment_verification"] = "product-only"
        else:
            payload["deployment"] = "inconsistent"
            payload["status"] = "degraded"
        return payload

    if normalized_web_root is not None:

        @app.get("/", include_in_schema=False)
        def web_index() -> FileResponse:
            return FileResponse(normalized_web_root / "index.html")

        @app.get("/{requested_path:path}", include_in_schema=False)
        def web_asset(requested_path: str) -> FileResponse:
            if requested_path.startswith("v1/") or requested_path == "healthz":
                raise HTTPException(status_code=404)
            candidate = (normalized_web_root / requested_path).resolve()
            try:
                candidate.relative_to(normalized_web_root)
            except ValueError as error:
                raise HTTPException(status_code=404) from error
            try:
                candidate_stat = candidate.lstat()
            except OSError:
                return FileResponse(normalized_web_root / "index.html")
            if not stat.S_ISREG(candidate_stat.st_mode):
                return FileResponse(normalized_web_root / "index.html")
            return FileResponse(candidate)

    return app
