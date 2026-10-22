"""Authorize the cycle runtime's current read surface, using Desk's existing session."""
import re
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .repository import ModuleRepositoryError

SNAPSHOTS = frozenset(f"/data/{name}.json" for name in (
    "market-surface", "cycle-research", "asset-statistics", "forecast-extension", "data-calibration",
))


class CycleReadTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET"]
    path: str = Field(max_length=256)
    query: str = Field(default="", max_length=64)


async def authorize_cycle_scope(request: Request, target: CycleReadTarget):
    from .routes import _instance_id_header, _validate_session

    auth = getattr(request.app.state, "website_auth", None)
    if auth is not None and auth.enabled:
        await auth.authenticate(request, require_mod=True)
    claims = _validate_session(request, request.headers.get("authorization"), _instance_id_header(
        request.headers.get("x-newma-desk-instance-id"), request.headers.get("x-newma-dock-instance-id"),
    ))
    if claims.module_id != "seven-cycle-research" or "analysis.read" not in claims.permissions:
        raise HTTPException(403, "当前 Mod 未获周期读取权限")
    try:
        module = await run_in_threadpool(request.app.state.resolve_module_repository().get_published, claims.module_id)
    except ModuleRepositoryError as error:
        raise HTTPException(403, "周期模块未获发布准入") from error
    if module.revision != claims.revision or "analysis.read" not in module.manifest.get("permissions", []):
        raise HTTPException(403, "周期模块授权已变更，请重新打开")
    snapshot = target.path in SNAPSHOTS and not target.query
    attribution = bool(re.fullmatch(r"/v1/assets/[^/\\%?#\x00-\x1f]{1,200}/attribution", target.path)) and target.query == "horizon=12"
    if not (snapshot or attribution):
        raise HTTPException(403, "当前周期页面未授权此读取入口")
    return {"userId": claims.user_id, "workspaceId": claims.workspace_id}
