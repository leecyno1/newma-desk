import asyncio
import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.capital_flow.research import CapitalResearchService
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.sectors import SectorResearchService
from vibe_visualization_api.capital_flow.supply import CapitalSupplyService
from vibe_visualization_api.capital_flow.verification import CapitalVerificationService
from vibe_visualization_api.capital_flow.security import SecurityResearchService
from vibe_visualization_api.capital_flow.evidence import CapitalEvidenceService
from vibe_visualization_api.capital_flow.liquidity import LiquidityResearchService
from vibe_visualization_api.capital_flow.appetite import AppetiteResearchService
from vibe_visualization_api.capital_flow.turnover import TurnoverResearchService, with_turnover
from vibe_visualization_api.capital_flow.turnover_history import TurnoverHistoryService
from vibe_visualization_api.capital_flow.connect_research import ConnectResearchService
from vibe_visualization_api.config import Settings, get_settings


router = APIRouter(prefix="/api/capital-flow", tags=["capital-flow"])


@router.get("/connect-research")
async def get_connect_research(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    return await ConnectResearchService(CapitalHistoryStore(settings.database_path)).research(refresh=refresh)


@router.get("/turnover-history")
async def get_turnover_history(days: int = Query(default=20), refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    if days not in {20, 60}:
        raise HTTPException(422, "成交基线仅支持20或60个交易日")
    return await TurnoverHistoryService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).history(days, refresh=refresh)


@router.get("/appetite-research")
async def get_appetite_research(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    return await AppetiteResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(refresh=refresh)


@router.get("/liquidity-research")
async def get_liquidity_research(
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    return await LiquidityResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(refresh=refresh)


@router.get("/security-evidence")
async def get_security_evidence(
    code: str = Query(pattern=r"^\d{6}$"),
    board_date: date | None = None,
    audit_date: date | None = None,
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    service = CapitalEvidenceService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path))
    if any(day and (day.isoformat() > service.end or day.isoformat() < service.start) for day in (board_date, audit_date)):
        raise HTTPException(422, "请选择最近150天且已结束的日期")
    return await service.research(code, board_date=board_date.isoformat() if board_date else None,
                                 audit_date=audit_date.isoformat() if audit_date else None, refresh=refresh)


@router.get("/security-research")
async def get_security_research(
    code: str = Query(pattern=r"^\d{6}$"),
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    return await SecurityResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(code, refresh=refresh)


@router.get("/supply-verification")
async def get_supply_verification(
    code: str = Query(pattern=r"^\d{6}$"),
    kind: Literal["repurchase", "stk_holdertrade", "share_float"] = "repurchase",
    ann_date: date = Query(),
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalVerificationService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).verify(code, kind, ann_date.isoformat(), refresh=refresh)


@router.get("/supply-research")
async def get_supply_research(
    code: str = Query(pattern=r"^\d{6}$"),
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalSupplyService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(code, refresh=refresh)


@router.get("/sector-research")
async def get_sector_research(
    category: Literal["industry", "concept", "region"] = "industry",
    level: Literal["all", "L1", "L2", "L3", "unknown"] = "all",
    code: str | None = Query(default=None, pattern=r"^BK\d{4,6}\.DC$"),
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict:
    return await SectorResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(category=category, code=code, refresh=refresh, level=level)


@router.get("/research")
async def get_capital_research(
    refresh: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(refresh=refresh)


@router.get("/search")
async def search_capital_flow_security(
    query: str = Query(min_length=1, max_length=48),
    limit: int = Query(default=8, ge=1, le=20),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalFlowService(
        settings.research_base_url,
        timeout_seconds=settings.capital_flow_timeout_seconds,
        tushare_token=settings.tushare_token.get_secret_value(),
    ).search_securities(query.strip(), limit)


@router.get("")
async def get_capital_flow(
    code: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    refresh: bool = False,
) -> dict:
    normalized = code.strip() if code else None
    if normalized and not re.fullmatch(r"\d{6}", normalized):
        raise HTTPException(422, "证券代码必须为 6 位数字")
    dashboard, turnover = await asyncio.gather(
        CapitalFlowService(
            settings.research_base_url,
            timeout_seconds=settings.capital_flow_timeout_seconds,
            tushare_token=settings.tushare_token.get_secret_value(),
        ).dashboard(normalized, include_legacy_turnover=False),
        TurnoverResearchService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).research(refresh=refresh),
    )
    return with_turnover(dashboard, turnover)
