import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from .etf_catalog import ETFCatalog
from .etf_price import ETFPriceService
from .market_structure import MarketStructureService
from .market_evidence import MarketEvidenceService
from .sentiment import sentiment_snapshot
from .limit_boards import LimitBoardsService

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
from vibe_visualization_api.capital_flow.turnover_candidates import TurnoverCandidatesService
from vibe_visualization_api.capital_flow.candidate_performance import CandidatePerformanceService
from vibe_visualization_api.capital_flow.candidate_archive import archive, archive_detail
from vibe_visualization_api.capital_flow.candidate_collector import collection_status
from vibe_visualization_api.scheduler.store import SchedulerStore
from vibe_visualization_api.capital_flow.connect_research import ConnectResearchService
from vibe_visualization_api.config import Settings, get_settings


router = APIRouter(prefix="/api/capital-flow", tags=["capital-flow"])


@router.get("/sentiment")
async def get_market_sentiment(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    turnover = await TurnoverResearchService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(refresh=refresh)
    return {"data": sentiment_snapshot(turnover)}


@router.get("/sentiment-history")
async def get_sentiment_history(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    result = await TurnoverHistoryService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).history(20, refresh=refresh, include_breadth=True)
    return {"data": result}


@router.get("/limit-boards")
async def get_limit_boards(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    return {"data": await LimitBoardsService(
        settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path),
    ).research(refresh=refresh)}


@router.get("/market-evidence")
async def get_market_evidence(
    code: str = Query(pattern=r"^\d{6}\.(SH|SZ)$"), as_of: date = Query(),
    industry: str = Query(min_length=1, max_length=32), aliases: list[str] = Query(default=[]),
    refresh: bool = False, settings: Settings = Depends(get_settings),
) -> dict:
    today = datetime.now(timezone(timedelta(hours=8))).date()
    if not today - timedelta(days=150) <= as_of < today:
        raise HTTPException(422, "复盘日期须为最近150天内已结束的日期")
    if len(aliases) > 12 or any(not alias or len(alias) > 32 for alias in aliases):
        raise HTTPException(422, "行业别名数量或长度不合法")
    return await MarketEvidenceService(settings.tushare_token.get_secret_value(), settings.database_path).research(
        code, as_of, industry, list(dict.fromkeys([industry, *aliases])), refresh=refresh)


@router.get("/market-structure")
async def get_market_structure(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    return await MarketStructureService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).research(refresh=refresh)


class ETFWatchItem(BaseModel):
    code: str = Field(pattern=r"^\d{6}\.(SH|SZ)$")
    category: Literal["宽基", "行业", "债券", "商品", "跨境", "货币", "未分类"] = "未分类"


class ETFWatchRequest(BaseModel):
    items: list[ETFWatchItem] = Field(min_length=1, max_length=12)


@router.get("/etf-search")
async def search_etfs(query: str = Query(min_length=1, max_length=48), settings: Settings = Depends(get_settings)) -> dict:
    if not query.strip():
        raise HTTPException(422, "请输入ETF名称或代码")
    return await ETFCatalog(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).search(query)


@router.get("/etf-price")
async def get_etf_price(code: str = Query(pattern=r"^\d{6}\.(SH|SZ)$"), refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    return await ETFPriceService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).price(code, refresh=refresh)


@router.post("/research")
async def research_etf_watchlist(body: ETFWatchRequest, refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    if len({item.code for item in body.items}) != len(body.items):
        raise HTTPException(422, "观察池不能包含重复ETF")
    store = CapitalHistoryStore(settings.database_path)
    catalog = await ETFCatalog(settings.tushare_token.get_secret_value(), store).read()
    if catalog["status"] != "ready":
        raise HTTPException(503, "ETF目录未完成更新，不能确认自选标的；已保存观察池不受影响")
    index = {item["code"]: item for item in catalog["items"]}
    if any(item.code not in index for item in body.items):
        raise HTTPException(422, "观察池包含不在当前上市ETF目录中的代码，请重新搜索核对")
    return await CapitalResearchService(settings.tushare_token.get_secret_value(), store).research(
        refresh=refresh, samples=[(item.code, index[item.code]["name"], item.category) for item in body.items])


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


@router.get("/turnover-candidates")
async def get_turnover_candidates(signal_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                                  refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    try:
        return await TurnoverCandidatesService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).candidates(
            signal_date=signal_date, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/turnover-candidate-archive")
async def get_candidate_archive(start: date = Query(default=date(1990, 1, 1)),
                                end: date = Query(default=date(9999, 12, 31)),
                                page: int = Query(default=1, ge=1), settings: Settings = Depends(get_settings)) -> dict:
    if start > end:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    store = CapitalHistoryStore(settings.database_path)
    result = await asyncio.to_thread(archive, store, start.isoformat(), end.isoformat(), page)
    result["collection"] = await asyncio.to_thread(collection_status, store, SchedulerStore(settings.database_path),
                                                  enabled=settings.enable_capital_candidate_archive,
                                                  token_ready=bool(settings.tushare_token.get_secret_value()))
    return result


@router.get("/turnover-candidate-archive/{signal_date}")
async def get_candidate_archive_detail(signal_date: date, page: int = Query(default=1, ge=1),
                                       settings: Settings = Depends(get_settings)) -> dict:
    result = await asyncio.to_thread(archive_detail, CapitalHistoryStore(settings.database_path), signal_date.isoformat(), page)
    if result is None:
        raise HTTPException(404, "该日期没有首次观察归档，不使用事后重算替代")
    return result


@router.get("/candidate-performance")
async def get_candidate_performance(code: str = Query(pattern=r"^\d{6}\.(SH|SZ|BJ)$"), signal_date: date = Query(),
                                    benchmark_code: str = Query(default="000300.SH", max_length=16),
                                    refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict:
    try:
        return await CandidatePerformanceService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).research(
            code, signal_date.isoformat(), benchmark_code=benchmark_code, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


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
    request: Request,
    query: str = Query(min_length=1, max_length=48),
    limit: int = Query(default=8, ge=1, le=20),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await CapitalFlowService(
        settings.research_base_url,
        transport_factory=getattr(request.app.state, "research_transport_factory", None),
        timeout_seconds=settings.capital_flow_timeout_seconds,
        tushare_token=settings.tushare_token.get_secret_value(),
    ).search_securities(query.strip(), limit)


@router.get("")
async def get_capital_flow(
    request: Request,
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
            transport_factory=getattr(request.app.state, "research_transport_factory", None),
            timeout_seconds=settings.capital_flow_timeout_seconds,
            tushare_token=settings.tushare_token.get_secret_value(),
        ).dashboard(normalized, include_legacy_turnover=False),
        TurnoverResearchService(settings.tushare_token.get_secret_value(), CapitalHistoryStore(settings.database_path)).research(refresh=refresh),
    )
    return with_turnover(dashboard, turnover)
