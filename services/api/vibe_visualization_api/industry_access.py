"""Desk identity boundary; the standalone industry package stays host-independent."""
from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from .control_plane.repository import ModuleRepositoryError
from .control_plane.routes import _instance_id_header, _validate_session

INDUSTRY_READ_PATHS = frozenset({
    "/api/industry-research", "/api/industry-research/history",
    "/api/industry-research/production", "/api/industry-research/prices",
    "/api/industry-research/capacity",
})


async def authorize_industry_read(request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    if request.method != "GET" or request.url.path not in INDUSTRY_READ_PATHS:
        raise HTTPException(403, "当前行业操作未获授权")
    auth = getattr(request.app.state, "website_auth", None)
    if auth is not None and auth.enabled:
        await auth.authenticate(request, require_mod=True)
    elif not any(name in request.headers for name in (
        "authorization", "x-newma-desk-instance-id", "x-vibedesk-instance-id",
    )):
        return  # Existing local public data access, never the Website-enabled deployment.
    claims = _validate_session(request, request.headers.get("authorization"), _instance_id_header(
        request.headers.get("x-newma-desk-instance-id"), request.headers.get("x-vibedesk-instance-id"),
    ))
    if claims.module_id != "industry-prosperity" or "market.read" not in claims.permissions:
        raise HTTPException(403, "当前插件未获行业读取权限")
    try:
        module = await run_in_threadpool(request.app.state.resolve_module_repository().get_published, claims.module_id)
    except ModuleRepositoryError as error:
        raise HTTPException(403, "行业模块未获发布准入") from error
    if module.revision != claims.revision or "market.read" not in module.manifest.get("permissions", []):
        raise HTTPException(403, "模块授权已变更，请重新加载")
    return claims
