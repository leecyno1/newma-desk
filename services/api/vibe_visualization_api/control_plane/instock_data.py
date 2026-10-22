"""Declared stock-page dependencies, not a generic privileged data proxy."""
import re
from typing import Any, Literal

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict


class StockDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: Literal["market.scan", "market.quotes", "market.overview", "market.emotion", "market.turnover-top"]
    parameters: dict[str, Any]


async def invoke_stock_dependency(request: Request, response: Response, target: StockDependency):
    from .routes import _validate_session, _instance_id_header, instock_request_scope
    from vibe_visualization_api.website_auth import local_request
    if not local_request(request):
        raise HTTPException(403, "股票数据委托仅接受本地分析进程")
    authorization = request.headers.get("authorization")
    instance = _instance_id_header(request.headers.get("x-newma-desk-instance-id"), request.headers.get("x-newma-dock-instance-id"))
    claims = _validate_session(request, authorization, instance)
    pages = {
        "instock-market-map": ("/market-maps/snapshots", {"market.scan", "market.quotes"}),
        "instock-market-workbench": ("/market-workbench/snapshots", {
            "market.scan", "market.quotes", "market.overview", "market.emotion", "market.turnover-top"}),
    }
    page = pages.get(claims.module_id)
    if page is None or target.capability not in page[1]:
        raise HTTPException(403, "当前股票页面尚未接入此数据委托")
    await instock_request_scope(request=request, response=response,
        target={"method": "GET", "path": "/api/v1" + page[0]},
        authorization=authorization, instance_id=instance, legacy_instance_id=None,
        repository=request.app.state.resolve_module_repository())
    params = target.parameters
    if target.capability == "market.scan":
        limits = {100, 200} if claims.module_id == "instock-market-map" else {50, 100, 200}
        rankings = {("turnoverPct", "desc"), ("volumeRatio", "desc"), ("changePct", "desc"), ("changePct", "asc")}
        if claims.module_id == "instock-market-map":
            rankings |= {("marketCap", "desc"), ("amount", "desc")}
        valid = set(params) == {"market", "sort", "order", "limit"} and params.get("market") == "CN" \
            and type(params.get("limit")) is int and params["limit"] in limits \
            and isinstance(params.get("sort"), str) and isinstance(params.get("order"), str) \
            and (params.get("sort"), params.get("order")) in rankings
    elif target.capability == "market.quotes":
        symbols = params.get("symbols")
        valid = set(params) == {"symbols"} and isinstance(symbols, str) and bool(re.fullmatch(r"CN:\d{6}(?:,CN:\d{6}){0,49}", symbols))
    else:
        valid = not params
    if not valid:
        raise HTTPException(422, "超出当前股票页面的数据读取范围")
    registry = request.app.state.data_service_registry
    service = registry.get("market-data")
    capability = service.capabilities.get(target.capability)
    if capability is None or capability.method != "GET" or capability.permission != "market.read":
        raise HTTPException(503, "股票只读数据能力未正确配置")
    # Reuse the registered provider, URL safety, schemas and existing data transport.
    # The current Website/Mod authorization was checked above; never pass its token upstream.
    response.headers["Cache-Control"] = "private, no-store"
    return await request.app.state.data_service_client.invoke(service, target.capability, params)
