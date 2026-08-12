from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from vibe_visualization_api.global_intel.client import (
    GlobalIntelClient,
    GlobalIntelUnavailable,
)


router = APIRouter(prefix="/api/global-intel", tags=["global-intel"])


def get_global_intel_client(request: Request) -> GlobalIntelClient:
    return request.app.state.global_intel_client


async def _json_response(
    client: GlobalIntelClient,
    path: str,
    *,
    timeout_seconds: float,
) -> dict:
    try:
        return await client.get_json(path, timeout_seconds=timeout_seconds)
    except GlobalIntelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/health")
async def global_intel_health(
    client: GlobalIntelClient = Depends(get_global_intel_client),
) -> dict:
    payload = await _json_response(client, "/api/health", timeout_seconds=5.0)
    return {
        "status": "ok" if payload.get("status") == "ok" else "degraded",
        "service": "world-intel-mcp",
        "upstream": payload,
    }


@router.get("/static")
async def global_intel_static(
    client: GlobalIntelClient = Depends(get_global_intel_client),
) -> dict:
    return await _json_response(client, "/api/static", timeout_seconds=10.0)


@router.get("/overview")
async def global_intel_overview(
    client: GlobalIntelClient = Depends(get_global_intel_client),
) -> dict:
    return await _json_response(client, "/api/overview", timeout_seconds=150.0)


@router.get("/stream")
async def global_intel_stream(
    client: GlobalIntelClient = Depends(get_global_intel_client),
) -> StreamingResponse:
    return StreamingResponse(
        client.stream("/api/stream"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
