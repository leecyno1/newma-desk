from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.finance_pilots.models import (
    DailyStockAnalysisContext,
    PilotAdaptRequest,
    PilotStatusDocument,
    StrategyLedgerRecord,
)


router = APIRouter(prefix="/api/finance-pilots", tags=["finance-pilots"])


@router.get("", response_model=PilotStatusDocument)
async def finance_pilot_status(request: Request):
    return await run_in_threadpool(request.app.state.finance_pilot_service.status)


@router.post(
    "/{pilot_id}/adapt",
    response_model=DailyStockAnalysisContext | StrategyLedgerRecord,
)
async def adapt_finance_pilot_payload(
    pilot_id: str,
    body: PilotAdaptRequest,
    request: Request,
):
    return await run_in_threadpool(
        request.app.state.finance_pilot_service.adapt,
        pilot_id,
        body.payload,
    )
