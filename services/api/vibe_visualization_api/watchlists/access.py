"""Identity boundary for shared watchlists and price alerts, not a new store."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.mod_storage.routes import _claims, _instance_id


WATCHLIST_EDITORS = frozenset({"market-daily", "watchlist"})
WATCHLIST_READERS = WATCHLIST_EDITORS | {"news-radar", "catalyst-calendar"}
ALERT_MODULES = frozenset({
    "market-daily", "market-technical", "multi-timeframe", "relative-strength",
    "event-timeline", "trading-replay",
})


def storage_permission(path: str, method: str, module_id: str) -> str | None:
    read = method in {"GET", "HEAD"}
    resource = path.rstrip("/")
    if resource == "/api/watchlists" or resource.startswith("/api/watchlists/"):
        allowed = WATCHLIST_READERS if read else WATCHLIST_EDITORS
    elif resource == "/api/market-alerts" or resource.startswith("/api/market-alerts/"):
        allowed = ALERT_MODULES
    elif resource == "/api/artifacts/replays" or resource.startswith("/api/artifacts/replays/"):
        allowed = {"trading-replay"}
    else:
        return None
    return ("storage.read" if read else "storage.write") if module_id in allowed else None


@dataclass(frozen=True)
class MarketStorageScope:
    user_id: str
    workspace_id: str
    module_id: str | None = None


async def market_storage_scope(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
    legacy_instance_id: str | None = Header(default=None, alias="X-Newma-Dock-Instance-Id"),
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)] = "local-user",
    workspace_id: Annotated[str, Header(alias="X-Workspace-Id", min_length=1, max_length=128)] = "local-workspace",
    repository: ModuleRepository = Depends(get_repository),
) -> MarketStorageScope:
    response.headers["Cache-Control"] = "private, no-store"
    cloud = getattr(getattr(request.app.state, "website_auth", None), "enabled", False)
    # Keep the explicitly local standalone API. A supplied broken credential
    # must never fall through to its legacy caller-selected identity.
    if (not cloud and authorization is None and instance_id is None
            and legacy_instance_id is None and "x-newma-desk-mod-session" not in request.headers):
        return MarketStorageScope(user_id, workspace_id)
    claims = _claims(request, authorization, _instance_id(instance_id, legacy_instance_id))
    permission = storage_permission(request.url.path, request.method, claims.module_id)
    if permission is None or permission not in claims.permissions:
        raise HTTPException(403, "当前模组未获自选股或预警存储权限")
    module = await run_in_threadpool(repository.get_published, claims.module_id)
    if claims.revision != module.revision or permission not in module.manifest.get("permissions", []):
        raise HTTPException(403, "模组授权已更新，请重新打开页面")
    return MarketStorageScope(claims.user_id, claims.workspace_id, claims.module_id)


StorageScope = Annotated[MarketStorageScope, Depends(market_storage_scope)]
