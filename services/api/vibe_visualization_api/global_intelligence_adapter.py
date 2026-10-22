"""Keep the Desk registry, credentials and database in the owning host."""
import asyncio
from contextlib import suppress

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .data_services.client import DataServiceClientError
from .data_services.registry import DataServiceRegistryError
from .global_intel.client import GlobalIntelClient
from .global_topics.sources import TopicSources
from .control_plane.routes import _validate_session
from .control_plane.repository import ModuleRepositoryError


GLOBAL_READ_PATHS = frozenset({
    "/api/global-intel/health", "/api/global-intel/static", "/api/global-intel/overview",
    "/api/global-intel/stream", "/api/crucix/health", "/api/crucix/snapshot",
})
TOPIC_MODULES = {"fed-rates": "fed-rates", "hormuz": "hormuz-conflict", "us-china-trade": "us-china-trade"}


def topic_access(path: str, method: str):
    for topic, module in TOPIC_MODULES.items():
        if method == "GET" and path == f"/api/global-topics/{topic}":
            return module, "market.read"
        if method == "POST" and path == f"/api/global-topics/{topic}/forecast":
            return module, "storage.write"
    return None


async def authorize_global_read(request: Request):
    if request.method != "GET" or request.url.path not in GLOBAL_READ_PATHS:
        raise HTTPException(403, "当前插件未获全球情报读取权限")
    return await _authorize_global(request, "global-situation", "market.read")


async def authorize_global_topic(request: Request):
    auth = getattr(request.app.state, "website_auth", None)
    if not (auth is not None and auth.enabled) and not request.headers.get("authorization"):
        return None  # Keep standalone/local 404 and legacy storage semantics.
    access = topic_access(request.url.path, request.method)
    if access is None:
        raise HTTPException(403, "当前专题操作未获授权")
    claims = await _authorize_global(request, *access)
    return (claims.user_id, claims.workspace_id) if claims is not None else None


async def _authorize_global(request: Request, module_id: str, permission: str):
    auth = getattr(request.app.state, "website_auth", None)
    if auth is not None and auth.enabled:
        await auth.authenticate(request, require_mod=True)
    elif not request.headers.get("authorization"):
        return  # Existing local/standalone mode; never used in cloud auth mode.
    claims = _validate_session(request, request.headers.get("authorization"), request.headers.get("x-newma-desk-instance-id"))
    if claims.module_id != module_id or permission not in claims.permissions:
        raise HTTPException(403, "当前插件未获专题操作权限")
    try:
        module = await run_in_threadpool(request.app.state.resolve_module_repository().get_published, claims.module_id)
    except ModuleRepositoryError as error:
        raise HTTPException(403, "全球情报模块尚未发布") from error
    if module.revision != claims.revision or permission not in module.manifest.get("permissions", []):
        raise HTTPException(403, "模块授权已变更，请重新加载")
    return claims


async def guard_global_stream(request, chunks, *, interval=5.0):
    """Recheck expiry/revocation even when upstream sends no events."""
    iterator = chunks.__aiter__()
    pending = None
    try:
        while True:
            await authorize_global_read(request)
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            ready, _ = await asyncio.wait({pending}, timeout=interval)
            if not ready:
                continue
            try:
                chunk = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            await authorize_global_read(request)
            yield chunk
    except HTTPException:
        yield b'event: error\ndata: {"status":"unauthorized","message":"Global intelligence authorization expired"}\n\n'
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        await iterator.aclose()


def install_global_intelligence(app: FastAPI, settings: Settings) -> None:
    app.state.global_intelligence_settings = settings
    app.state.global_intel_client = GlobalIntelClient(settings.world_intel_url)
    app.state.global_read_authorizer = authorize_global_read
    app.state.global_topic_authorizer = authorize_global_topic
    app.state.global_stream_guard = guard_global_stream

    async def read_crucix(capability_id: str):
        return await app.state.data_service_client.invoke(
            app.state.data_service_registry.get("crucix"), capability_id, {}
        )

    async def crucix_snapshot():
        return await read_crucix("crucix.snapshot")

    async def maritime_snapshot():
        return await app.state.global_intel_client.get_json("/api/maritime/warnings", timeout_seconds=15)

    app.state.crucix_reader = read_crucix
    app.state.global_topic_sources = TopicSources(
        tushare_token=settings.tushare_token.get_secret_value(),
        crucix_snapshot=crucix_snapshot,
        maritime_snapshot=maritime_snapshot,
        upstream_errors=(DataServiceClientError, DataServiceRegistryError),
    )
