from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from .client import CrucixUnavailable
from vibe_visualization_api.global_intel.runtime import authorize_global_read


router = APIRouter(prefix="/api/crucix", tags=["crucix"], dependencies=[Depends(authorize_global_read)])


CrucixReader = Callable[[str], Awaitable[dict]]


def get_reader(request: Request) -> CrucixReader:
    reader = getattr(request.app.state, "crucix_reader", None)
    if reader is None:
        raise HTTPException(503, "Crucix 数据读取器未接入")
    return reader


async def _invoke(
    capability_id: str,
    reader: CrucixReader,
) -> Any:
    try:
        return await reader(capability_id)
    except CrucixUnavailable as error:
        raise HTTPException(503, str(error)) from error


@router.get("/health")
async def crucix_health(
    reader: CrucixReader = Depends(get_reader),
) -> Any:
    return await _invoke("crucix.health", reader)


@router.get("/snapshot")
async def crucix_snapshot(
    reader: CrucixReader = Depends(get_reader),
) -> Any:
    return await _invoke("crucix.snapshot", reader)
