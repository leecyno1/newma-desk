"""Trusted request-scoped bindings for immutable published runs."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import stat
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from seven_cycle_platform.catalog import open_catalog
from seven_cycle_platform.catalog.duckdb import VerifiedCatalogConnection
from seven_cycle_platform.storage.manifest import (
    RunManifest,
    load_manifest,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import (
    RUN_ID_PATTERN,
    canonical_json_bytes,
)

from seven_cycle_platform.api.schemas import QueryFilters


DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_OFFSET = 100_000
MAX_HORIZON = 120
MAX_CYCLE_IDS = 7


@dataclass(frozen=True, slots=True)
class RequestContext:
    """One verified run and catalog connection for exactly one request."""

    connection: VerifiedCatalogConnection
    manifest: RunManifest
    catalog_checksum: str
    manifest_checksum: str


@dataclass(frozen=True, slots=True)
class HealthContext:
    """Verified release identity without retaining an open Catalog connection."""

    manifest: RunManifest
    catalog_checksum: str
    manifest_checksum: str


class HealthContextCache:
    """Single-flight cache for the expensive immutable-release verification."""

    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._expires_at = 0.0
        self._latest_signature: tuple[int, int, int, int] | None = None
        self._context: HealthContext | None = None

    @staticmethod
    def _signature(path: Path) -> tuple[int, int, int, int]:
        _require_regular_file(path)
        try:
            info = path.stat()
        except OSError as error:
            raise _unavailable() from error
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def get(self, request: Request) -> HealthContext:
        product_root = Path(request.app.state.product_root)
        signature = self._signature(product_root / "latest.json")
        now = monotonic()
        with self._lock:
            if (
                self._context is not None
                and self._latest_signature == signature
                and now < self._expires_at
            ):
                return self._context

            context = _open_request_context(request)
            try:
                verified = HealthContext(
                    manifest=context.manifest,
                    catalog_checksum=context.catalog_checksum,
                    manifest_checksum=context.manifest_checksum,
                )
            finally:
                context.connection.close()
            self._context = verified
            self._latest_signature = signature
            self._expires_at = monotonic() + self._ttl_seconds
            return verified


def _unavailable(status_code: int = 503) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail="published data is temporarily unavailable",
    )


def _require_real_directory(path: Path) -> None:
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise _unavailable() from error
    if not stat.S_ISDIR(path_stat.st_mode):
        raise _unavailable()


def _require_regular_file(path: Path) -> None:
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise _unavailable() from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise _unavailable()


def _read_latest_run_id(product_root: Path) -> str:
    """Read and validate the published pointer exactly once."""

    latest_path = product_root / "latest.json"
    _require_regular_file(latest_path)
    try:
        pointer_bytes = latest_path.read_bytes()
        pointer = json.loads(pointer_bytes)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise _unavailable() from error
    if (
        not isinstance(pointer, dict)
        or set(pointer) != {"run_id"}
        or not isinstance(pointer.get("run_id"), str)
        or not RUN_ID_PATTERN.fullmatch(pointer["run_id"])
        or pointer_bytes != canonical_json_bytes(pointer) + b"\n"
    ):
        raise _unavailable(409)
    return pointer["run_id"]


def _metadata(connection: VerifiedCatalogConnection) -> tuple[str, str]:
    try:
        rows = connection.execute(
            "SELECT catalog_checksum, manifest_checksum FROM runs"
        ).fetchall()
    except Exception as error:
        raise _unavailable() from error
    if (
        len(rows) != 1
        or not isinstance(rows[0], tuple)
        or len(rows[0]) != 2
        or not all(isinstance(value, str) for value in rows[0])
    ):
        raise _unavailable(409)
    return rows[0][0], rows[0][1]


def _close_after_setup_failure(connection: VerifiedCatalogConnection) -> None:
    """Attempt cleanup without masking the controlled setup failure."""

    try:
        connection.close()
    except Exception:
        pass


def _open_request_context(request: Request) -> RequestContext:
    """Open and fully verify one immutable published run."""
    product_root = Path(request.app.state.product_root)
    catalog_root = Path(request.app.state.catalog_root)
    _require_real_directory(product_root)
    _require_real_directory(product_root / "runs")
    _require_real_directory(catalog_root)
    run_id = _read_latest_run_id(product_root)
    run_dir = product_root / "runs" / run_id
    catalog_path = catalog_root / f"{run_id}.duckdb"
    _require_real_directory(run_dir)
    _require_regular_file(catalog_path)
    connection: VerifiedCatalogConnection | None = None
    try:
        expected_manifest = load_manifest(run_dir)
        manifest = verify_manifest(run_dir, expected=expected_manifest)
        connection = open_catalog(
            catalog_path,
            run_dir=run_dir,
            expected_manifest=manifest,
        )
        catalog_checksum, manifest_checksum = _metadata(connection)
    except HTTPException:
        if connection is not None:
            _close_after_setup_failure(connection)
        raise
    except Exception as error:
        if connection is not None:
            _close_after_setup_failure(connection)
        raise _unavailable(409) from error

    return RequestContext(
        connection=connection,
        manifest=manifest,
        catalog_checksum=catalog_checksum,
        manifest_checksum=manifest_checksum,
    )


def get_request_context(request: Request) -> Generator[RequestContext, None, None]:
    """Bind a request to a verified, immutable run and close it afterwards."""

    context = _open_request_context(request)
    try:
        yield context
    finally:
        context.connection.close()


def get_health_context(request: Request) -> HealthContext:
    """Return a cached verified identity for high-frequency health probes."""

    cache = getattr(request.app.state, "health_context_cache", None)
    if cache is None:
        cache = HealthContextCache()
        request.app.state.health_context_cache = cache
    return cache.get(request)


def _bounded_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise HTTPException(status_code=422, detail=f"invalid {name}")
    return normalized


def get_query_filters(
    as_of: Annotated[date | None, Query()] = None,
    vintage: Annotated[str | None, Query()] = None,
    model_version: Annotated[str | None, Query()] = None,
    horizon: Annotated[int | None, Query(gt=0, le=MAX_HORIZON)] = None,
    scenario: Annotated[str | None, Query()] = None,
    benchmark: Annotated[str | None, Query()] = None,
    asset_tier: Annotated[str | None, Query()] = None,
    cycle_ids: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> QueryFilters:
    """Parse only documented, bounded filter and pagination parameters."""

    normalized_cycle_ids = tuple(
        item.strip() for item in (cycle_ids or "").split(",") if item.strip()
    )
    if len(normalized_cycle_ids) > MAX_CYCLE_IDS or len(
        set(normalized_cycle_ids)
    ) != len(normalized_cycle_ids):
        raise HTTPException(status_code=422, detail="invalid cycle_ids")
    if any(len(item) > 64 for item in normalized_cycle_ids):
        raise HTTPException(status_code=422, detail="invalid cycle_ids")
    return QueryFilters(
        as_of=as_of,
        vintage=_bounded_text(vintage, "vintage"),
        model_version=_bounded_text(model_version, "model_version"),
        horizon=horizon,
        scenario=_bounded_text(scenario, "scenario"),
        benchmark=_bounded_text(benchmark, "benchmark"),
        asset_tier=_bounded_text(asset_tier, "asset_tier"),
        cycle_ids=normalized_cycle_ids,
        limit=limit,
        offset=offset,
    )


RequestContextDependency = Annotated[RequestContext, Depends(get_request_context)]
QueryFiltersDependency = Annotated[QueryFilters, Depends(get_query_filters)]
