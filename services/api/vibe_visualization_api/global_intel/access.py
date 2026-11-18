"""Ask the owning Desk to validate grants; never implement its account system here."""
import asyncio
import logging
from contextlib import suppress
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


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


def required_access(path: str, method: str):
    if method == "GET" and path in GLOBAL_READ_PATHS:
        return "global-situation", "market.read"
    return topic_access(path, method)


def validate_scope_url(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
            or url.path != "/api/mods/runtime/global-scope" or url.username is not None
            or url.password is not None or url.query or url.fragment):
        raise ValueError("desk_scope_url must select the loopback Desk global-scope validator")
    return value


class DeskScopeResolver:
    def __init__(self, endpoint: str, *, client=None):
        self.endpoint = validate_scope_url(endpoint)
        self.client = client

    async def __call__(self, request):
        if required_access(request.url.path, request.method) is None:
            raise HTTPException(403, "当前全球情报操作未获授权")
        authorization = request.headers.get("authorization", "")
        instance = request.headers.get("x-newma-desk-instance-id", "")
        if not authorization.startswith("Bearer ") or not authorization[7:] or not instance:
            raise HTTPException(401, "需要有效的 Desk 会话和实例")
        headers = {"Authorization": authorization, "X-Newma-Desk-Instance-Id": instance}
        target = {"method": request.method, "path": request.url.path}
        try:
            if self.client is not None:
                response = await self.client.post(self.endpoint, headers=headers, json=target)
            else:
                async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
                    response = await client.post(self.endpoint, headers=headers, json=target)
            if response.status_code in (401, 403):
                raise HTTPException(response.status_code, "Desk 会话已失效或未获授权")
            if response.status_code != 200:
                raise HTTPException(503, "Desk 授权校验暂不可用，未回退到独立数据")
            identity = response.json()
            if not isinstance(identity, dict) or not all(
                isinstance(identity.get(key), str) and identity[key] for key in ("userId", "workspaceId")
            ):
                raise ValueError("invalid identity")
            return identity["userId"], identity["workspaceId"]
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(503, "Desk 授权校验暂不可用，未回退到独立数据") from error


async def reject_desk_session_in_local_mode(request):
    if any(request.headers.get(key) for key in ("authorization", "x-newma-desk-instance-id", "x-newma-desk-session")):
        raise HTTPException(503, "当前为本机单用户模式，未配置 Desk 会话校验")


async def guard_stream(request, chunks, authorizer, *, interval=5.0, stage="domain_scope"):
    """Check even a silent stream; failure closes its pending upstream read."""
    iterator = chunks.__aiter__()
    pending = None
    try:
        while True:
            await authorizer(request)
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
            await authorizer(request)
            yield chunk
    except HTTPException as error:
        status = "unauthorized" if error.status_code in (401, 403) else "unavailable"
        code = "scope_denied" if status == "unauthorized" else "scope_unavailable"
        logger.warning("Global stream stopped: code=%s stage=%s http_status=%d", code, stage, error.status_code)
        yield f'event: error\ndata: {{"status":"{status}","code":"{code}","stage":"{stage}","message":"Global intelligence authorization unavailable"}}\n\n'.encode()
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        await iterator.aclose()
