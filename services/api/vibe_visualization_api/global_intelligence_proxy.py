"""Explicit domain-service connection; no anonymous or embedded fallback."""
from urllib.parse import urlsplit
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .global_intel.access import required_access
from .global_intelligence_adapter import _authorize_global, guard_global_stream
from .schema_validation import validate_json_contract


router = APIRouter()
logger = logging.getLogger(__name__)

# Registered engine reads -> the same domain paths used by the global page.
GLOBAL_DATA_READS = {
    ("world-intel", "global-intel.snapshot"): ("/api/overview", "/api/global-intel/overview"),
    ("world-intel", "global-intel.static-map"): ("/api/static", "/api/global-intel/static"),
    ("crucix", "crucix.snapshot"): ("/api/data", "/api/crucix/snapshot"),
    ("crucix", "crucix.health"): ("/api/health", "/api/crucix/health"),
}


async def invoke_global_data(request: Request, service, capability_id: str, input_data: dict):
    capability = service.capabilities[capability_id]
    target = GLOBAL_DATA_READS.get((service.id, capability_id))
    if target is None or capability.method != "GET" or capability.path != target[0]:
        raise HTTPException(403, "全球情报能力与已声明的只读入口不符")
    validate_json_contract(capability.input_schema, input_data, direction="input")
    upstream = await forward_global(request, path=target[1], method="GET")
    result = json.loads(upstream.body)
    # Domain responses are already normalized. Never run the embedded adapter twice.
    validate_json_contract(capability.output_schema, result, direction="output")
    return result


async def proxy_global(request: Request):
    return await forward_global(request, path=request.url.path, method=request.method, content=None)


async def forward_global(request: Request, *, path: str, method: str, content: bytes | None = b""):
    access = required_access(path, method)
    if access is None:
        raise HTTPException(403, "当前全球情报操作未获授权")
    await _authorize_global(request, *access, require_session=True)
    settings = request.app.state.global_intelligence_settings
    if not settings.global_intelligence_api_url:
        raise HTTPException(503, "独立全球情报地址未配置")
    target = urlsplit(settings.global_intelligence_api_url)
    server = request.scope.get("server")
    if server and (target.port or 80) == server[1]:
        raise HTTPException(503, "独立全球情报地址不能指向当前 Desk 服务")
    if content is None:
        content = await request.body()
    headers = {key: request.headers[key] for key in ("authorization", "x-newma-desk-instance-id")}
    if request.headers.get("content-type"):
        headers["content-type"] = request.headers["content-type"]
    # No Cookies, caller-supplied identity, redirects, environment proxy or retries.
    streaming = path == "/api/global-intel/stream"
    client = httpx.AsyncClient(timeout=httpx.Timeout(160, connect=8, read=None if streaming else 160),
                              trust_env=False, follow_redirects=False)
    try:
        upstream = await client.send(client.build_request(
            method, settings.global_intelligence_api_url + path,
            headers=headers, content=content,
        ), stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(503, "独立全球情报服务暂不可用，未回退到内置数据") from error
    except BaseException:
        await client.aclose()
        raise
    if upstream.status_code != 200:
        status = upstream.status_code if upstream.status_code in (401, 403, 404, 422) else 503
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status, "独立全球情报请求未完成，请检查授权、参数或数据源；未自动重试")

    if streaming:
        if not upstream.headers.get("content-type", "").startswith("text/event-stream"):
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(503, "独立全球情报未返回实时流")
        async def events():
            try:
                async for chunk in guard_global_stream(request, upstream.aiter_bytes()):
                    yield chunk
            except httpx.HTTPError as error:
                logger.warning("Global stream stopped: code=domain_stream_disconnected cause=%s", type(error).__name__)
                yield b'event: error\ndata: {"status":"unavailable","code":"domain_stream_disconnected","stage":"desk_proxy","message":"Global intelligence service disconnected"}\n\n'
            finally:
                await upstream.aclose()
                await client.aclose()
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    try:
        await upstream.aread()
        if not isinstance(upstream.json(), dict):
            raise ValueError("invalid domain response")
        return Response(upstream.content, media_type="application/json", headers={"Cache-Control": "no-store"})
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(503, "独立全球情报响应未确认，未自动重试") from error
    finally:
        await upstream.aclose()
        await client.aclose()


for prefix in ("global-intel", "global-topics", "crucix"):
    router.add_api_route(f"/api/{prefix}/{{resource:path}}", proxy_global, methods=["GET", "POST"])
