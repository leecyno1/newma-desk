"""Vibe-Research 后端 —— A股数据层 HTTP 接口（FastAPI）。

端点全部在 /api 下，前端 vite 代理 /api → localhost:8900。
只读、无状态、按用户传入代码返回客观数据。不预置标的、不建议。

启动：
    uvicorn app:app --host 127.0.0.1 --port 8900
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import astock
import catalyst_calendar
import equity_research
import gstock
import newsradar
import portfolio as pf
import market
import market_terminal
import security_master
import macro_monitor
import myreports as mr


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


_INTEGRATED_DOMAIN_RUNTIME = _env_enabled(
    "NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME"
) or _env_enabled("VIBEDESK_INTEGRATED_DOMAIN_RUNTIME")

app = FastAPI(title="Vibe-Research API", version="0.1.3")


@app.on_event("startup")
def _start_security_master_scheduler() -> None:
    security_master.start_scheduler()

# 独立版保留原有的持仓快照刷新线程；集成版由 Desk Scheduler /
# 显式刷新统一编排，避免每个 Research worker 都常驻一条重复线程。
if not _INTEGRATED_DOMAIN_RUNTIME:
    pf.start_scheduler(1800)

# CORS：默认放开（本地自托管友好）；公网部署时用 VR_ALLOW_ORIGINS 收紧成白名单。
#   例：VR_ALLOW_ORIGINS="https://myhost"  （逗号分隔多个）
_ORIGINS = [o.strip() for o in os.environ.get("VR_ALLOW_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 可选鉴权：设了 VR_API_KEY 就要求所有 /api/* 带 `Authorization: Bearer <key>`
#   （本地自托管不设=开放；公网部署务必设，否则别人能读你的持仓/调你的后端）。
_API_KEY = os.environ.get("VR_API_KEY", "").strip()


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if (
        _API_KEY
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
    ):
        if request.headers.get("authorization", "") != f"Bearer {_API_KEY}":
            return JSONResponse({"detail": "未授权：缺少或错误的 API Key（VR_API_KEY）"}, status_code=401)
    return await call_next(request)

_CODE_RE = r"^\d{6}$"


def _validate(code: str) -> str:
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    return code


@app.get("/api/health")
def health():
    return {"ok": True, "service": "vibe-research-api", "version": "0.1.3"}


@app.get("/api/catalysts")
def catalysts(
    symbols: str = Query("", max_length=512),
    concepts: str = Query("", max_length=300),
    days: int = Query(180, ge=14, le=1095),
    include_cycles: bool = Query(True),
    include_macro: bool = Query(True),
):
    """Upcoming research catalysts with evidence, freshness and invalidation rules."""
    universe = [item.strip() for item in symbols.split(",") if item.strip()]
    invalid = [item for item in universe if not item.isdigit() or len(item) != 6]
    if invalid:
        raise HTTPException(400, "symbols 仅支持逗号分隔的 6 位 A 股代码")
    concept_list = list(dict.fromkeys(
        item.strip() for item in concepts.split(",") if item.strip()
    ))
    if len(concept_list) > 5 or any(len(item) > 40 for item in concept_list):
        raise HTTPException(400, "concepts 最多支持 5 个、每个不超过 40 字")
    return {"data": catalyst_calendar.build_catalyst_feed(
        universe,
        days,
        include_cycles,
        concept_list,
        include_macro,
    )}


@app.get("/api/macro-monitor")
def macro_monitor_feed(days: int = Query(7, ge=1, le=30)):
    """Macro indicators, evidence quality and upcoming economic events."""
    return {"data": macro_monitor.build_macro_monitor(days)}


if not _INTEGRATED_DOMAIN_RUNTIME:
    class LLMConfig(BaseModel):
        provider: str = ""       # cli-* = 订阅接入（调本机 CLI）；其余 = API 接入
        baseURL: str = ""        # 订阅接入时留空
        apiKey: str = ""         # 订阅接入时留空
        model: str


    class ChatReq(BaseModel):
        messages: list[dict]
        context: str = ""
        llm: LLMConfig


    @app.post("/api/chat")
    def chat(req: ChatReq):
        """独立版系统 AI 对话，流式返回 NDJSON 事件。

        原生模型与 CLI 层在首次请求时才加载，不增加普通数据路由的
        启动开销。集成域运行时不注册此路由，并统一使用 Desk Agent。
        """
        if not req.messages:
            raise HTTPException(400, "messages 不能为空")
        if not req.llm.model:
            raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")

        # 延迟导入：即使是独立版，只读数据 API 也无需加载模型、
        # requests 工具调用层和 CLI 运行时。
        import json
        from fastapi.responses import StreamingResponse
        import chat as chat_layer
        import cli_runtime

        is_cli = req.llm.provider.startswith("cli-")
        if is_cli:
            kind = req.llm.provider[4:]
            if not cli_runtime.detect_cli(kind):
                raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
        elif not req.llm.apiKey or not req.llm.baseURL:
            raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")

        cfg = req.llm.model_dump()

        def gen():
            try:
                events = (chat_layer.run_chat_cli_stream if is_cli else chat_layer.run_chat_stream)(cfg, req.messages, req.context)
                for ev in events:
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
            except Exception as e:  # noqa: BLE001 — 运行时错误以流内事件上报，不中断连接
                yield json.dumps({"type": "error", "message": f"对话失败：{e}"}, ensure_ascii=False) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")


class HoldingIn(BaseModel):
    code: str
    shares: float
    cost: float


@app.get("/api/portfolio")
def portfolio_get():
    """持仓 + 实时盈亏（浮动盈亏红涨绿跌）。"""
    try:
        return {"data": pf.get_portfolio()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"持仓读取异常：{e}") from e


@app.post("/api/portfolio/holding")
def portfolio_add(h: HoldingIn):
    """加一笔持仓（同代码按加权平均成本合并）。存本地，不上传。"""
    code = (h.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if h.shares <= 0:
        raise HTTPException(400, "数量必须大于 0")
    # 成本价不限正负：融券 / 返息 / 摊薄后为负成本等情形按结果计算，用户想怎么输就怎么输。
    return {"data": pf.add_holding(code, h.shares, h.cost)}


@app.delete("/api/portfolio/holding")
def portfolio_remove(code: str = Query(...)):
    return {"data": pf.remove_holding(code.strip())}


# ---- 我的研报（用户上传自己的研报，存本地、不上传、不进开源仓库）----

class ReportIn(BaseModel):
    name: str
    content_b64: str


@app.get("/api/myreports")
def myreports_list():
    return {"data": mr.list_reports()}


@app.post("/api/myreports")
def myreports_upload(r: ReportIn):
    """上传一份研报（base64）→ 存本地 + 按文件名自动打行业标签。"""
    try:
        return {"data": mr.save_report(r.name, r.content_b64)}
    except mr.ReportError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/myreports/file/{rid}")
def myreports_file(rid: str):
    """下载/预览某份研报原文件。"""
    hit = mr.report_path(rid)
    if not hit:
        raise HTTPException(404, "研报不存在")
    path, name = hit
    return FileResponse(str(path), filename=name)


@app.delete("/api/myreports/{rid}")
def myreports_delete(rid: str):
    return {"data": {"ok": mr.delete_report(rid)}}


class CloseIn(BaseModel):
    code: str
    date: str
    price: float
    shares: float
    cost: float


@app.post("/api/portfolio/close")
def portfolio_close(c: CloseIn):
    """记一笔已清仓（已实现盈亏）。存本地。"""
    code = (c.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    if c.price <= 0 or c.shares <= 0:
        raise HTTPException(400, "清仓价与股数必须大于 0")
    # 买入成本不限正负（同持仓录入）：按 (清仓价 - 成本) × 股数 的结果计算已实现盈亏。
    date = (c.date or "").strip()
    if not date:
        raise HTTPException(400, "请填清仓日期")
    from datetime import datetime
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "清仓日期格式应为 YYYY-MM-DD") from None
    return {"data": pf.close_position(code, date, c.price, c.shares, c.cost)}


@app.delete("/api/portfolio/close")
def portfolio_close_remove(index: int = Query(...)):
    return {"data": pf.remove_closed(index)}


@app.post("/api/portfolio/refresh")
def portfolio_refresh():
    """手动刷新：立即重拉行情算盈亏。"""
    try:
        return {"data": pf.get_portfolio()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"刷新失败：{e}") from e


@app.get("/api/radar")
def radar():
    """资讯雷达：12 赛道公开 RSS 资讯（读缓存，无缓存返回赛道骨架）。"""
    try:
        return {"data": newsradar.get_radar(force=False)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达异常：{e}") from e


@app.get("/api/radar/topics")
def radar_topics(
    q: str = Query("", max_length=200),
    industry: str = Query("all", max_length=48),
    signal: str = Query("all", max_length=24),
    sort: str = Query("attention", max_length=24),
    offset: int = Query(0, ge=0),
    limit: int = Query(80, ge=1, le=160),
):
    """完整主题列表：支持服务端搜索、筛选和分页。"""
    if signal not in {"all", "rising", "risk", "opportunity", "verify"}:
        raise HTTPException(400, "signal 参数无效")
    if sort not in {"attention", "latest"}:
        raise HTTPException(400, "sort 参数无效")
    try:
        return {"data": newsradar.query_topics(
            query=q,
            industry=industry,
            signal=signal,
            sort=sort,
            offset=offset,
            limit=limit,
        )}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"新闻主题查询失败：{e}") from e


@app.post("/api/radar/refresh")
def radar_refresh():
    """强制重抓全部 RSS 源（耗时约 20-40s），更新缓存。"""
    try:
        return {"data": newsradar.get_radar(force=True)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资讯雷达刷新失败：{e}") from e


@app.get("/api/market/overview")
def market_overview():
    """市场情绪 + 板块资金流（板块/大盘级，全站共享缓存 5 分钟）。"""
    try:
        return {"data": market.get_overview()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"市场总览异常：{e}") from e


@app.get("/api/market/emotion")
def market_emotion():
    """短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    含连板梯队个股清单（code/name/连板数等）——2026-07-05 起如实展示客观公开榜单（东财同款），
    只呈现事实，不附推荐/评分/预测/买卖时机。全站共享缓存 5 分钟。
    """
    try:
        return {"data": market.get_short_term_emotion()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"短线情绪异常：{e}") from e


@app.get("/api/market/turnover-top")
def market_turnover_top():
    """全市场成交额榜 Top20（客观公开榜单数据，非推荐/非预测/不评分）。全站共享缓存 5 分钟。"""
    try:
        return {"data": market.get_turnover_top()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"成交额榜异常：{e}") from e


@app.get("/api/global/indices")
def global_indices():
    """全球指数快照（道指 / 标普500 / 纳斯达克 / 恒生 / 恒生科技）—— A 股看隔夜外围脸色。缓存 5 分钟。"""
    try:
        return {"data": market.get_global_indices()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"全球指数异常：{e}") from e


@app.get("/api/global/stock")
def global_stock(symbol: str = Query(..., min_length=1, max_length=16)):
    """美股 / 港股个股聚合：按 global-stock-data Skill 优先级拉取行情与关键财务指标。"""
    try:
        data = gstock.us_hk_stock(symbol.strip())
        if not data:
            raise HTTPException(404, f"未找到美股/港股代码「{symbol}」")
        return {"data": data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"美港股查询异常：{e}") from e


@app.get("/api/equity-research/snapshot")
def equity_research_snapshot(symbol: str = Query(..., min_length=1, max_length=16)):
    """A/H/US 共用研究框架与 Evidence Ledger；EDGAR 仅作美股可选披露源。"""
    try:
        return {"data": equity_research.default_service.snapshot(symbol)}
    except (ValueError, LookupError) as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"个股研究证据聚合异常：{e}") from e


@app.get("/api/equity-research/comparison")
def equity_research_comparison(symbols: str = Query(..., min_length=3, max_length=160)):
    """按统一财务字段横向比较 2-8 个 A/H/US 证券；不改变原始市场口径。"""
    try:
        return {"data": equity_research.default_service.comparison(symbols.split(","))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"个股横向比较异常：{e}") from e


@app.get("/api/indices")
def indices():
    """A股大盘指数实时行情（上证/深证成指/创业板指/沪深300）。仅标准库。"""
    try:
        return {"data": astock.index_quote()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"指数行情异常：{e}") from e


@app.get("/api/quote")
def quote(codes: str = Query(..., description="逗号分隔的 6 位代码")):
    """实时行情：现价/涨跌/PE/PB/市值/换手/涨跌停。仅标准库，永远可用。"""
    lst = [c.strip() for c in codes.split(",") if c.strip()]
    if not lst or any(not c.isdigit() or len(c) != 6 for c in lst):
        raise HTTPException(400, "codes 必须是逗号分隔的 6 位数字")
    try:
        return {"data": astock.tencent_quote(lst)}
    except Exception as e:  # noqa: BLE001 — 边界统一兜底
        raise HTTPException(502, f"行情源异常：{e}") from e


# ---- VibeDesk 市场终端统一协议（A 股 / 港股 / 美股）----

@app.get("/api/market-terminal/search")
def market_terminal_search(
    query: str = Query(..., min_length=1, max_length=48),
    market_id: str = Query("ALL", alias="market", pattern="^(ALL|CN|HK|US)$"),
    limit: int = Query(12, ge=1, le=30),
):
    """跨 A/H/US 的统一标的搜索。"""
    try:
        return {"data": market_terminal.search_symbols(query, limit=limit, market=market_id)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"标的搜索异常：{e}") from e


@app.get("/api/market-terminal/security-master")
def market_security_master_status():
    """A 股证券主数据覆盖状态。"""
    return {"data": security_master.status()}


@app.post("/api/market-terminal/security-master/refresh")
def market_security_master_refresh():
    """刷新沪深北全部 A 股证券目录；重行情按需读取。"""
    result = security_master.refresh()
    if not result.get("ok"):
        raise HTTPException(502, detail={"message": "A 股证券主数据刷新失败", **result})
    return {"data": result}


@app.get("/api/market-terminal/quotes")
def market_terminal_quotes(
    symbols: str = Query(..., min_length=1, max_length=512),
):
    """批量统一报价，symbols 使用 CN:600519,HK:00700,US:AAPL 格式。"""
    try:
        return {"data": market_terminal.get_quotes(symbols)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"批量行情异常：{e}") from e


@app.get("/api/market-terminal/quote")
def market_terminal_quote(
    symbol: str = Query(..., min_length=1, max_length=24),
    market_id: str = Query("", alias="market", pattern="^(|CN|HK|US)$"),
    asset_type: str = Query("stock", alias="assetType", pattern="^(stock|etf|fund|index)$"),
):
    """单标的统一报价与可用盘口。"""
    try:
        data = market_terminal.get_quote(symbol, market=market_id, asset_type=asset_type)
        if not data:
            raise HTTPException(404, f"未找到标的「{symbol}」")
        return {"data": data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"行情查询异常：{e}") from e


@app.get("/api/market-terminal/scan")
def market_terminal_scan(
    market: str = Query("CN", pattern="^(CN|HK|US)$"),
    sort: str = Query("amount", pattern="^(changePct|amount|turnoverPct|volumeRatio|marketCap|pe|pb)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=20, le=200),
):
    """A/H/US 大范围行情扫描池；单请求返回标准化指标，避免逐标的扇出。"""
    try:
        return {
            "data": market_terminal.scan_market_quotes(
                market,
                sort=sort,
                order=order,
                limit=limit,
            )
        }
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"市场扫描异常：{e}") from e


@app.get("/api/market-terminal/ohlcv")
def market_terminal_ohlcv(
    symbol: str = Query(..., min_length=1, max_length=24),
    market_id: str = Query("", alias="market", pattern="^(|CN|HK|US)$"),
    timeframe: str = Query("1d", pattern="^(1m|5m|15m|30m|60m|1d|1w|1M)$"),
    limit: int = Query(320, ge=40, le=800),
    adjust: str = Query("qfq", pattern="^(none|qfq|hfq)$"),
    asset_type: str = Query("stock", alias="assetType", pattern="^(stock|etf|fund|index)$"),
):
    """KLineChart 所需的统一 OHLCV 数据。"""
    try:
        return {
            "data": market_terminal.get_ohlcv(
                symbol,
                market=market_id,
                timeframe=timeframe,
                limit=limit,
                adjust=adjust,
                asset_type=asset_type,
            )
        }
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"K 线查询异常：{e}") from e


import time as _time
_PCT_CACHE: dict = {}


@app.get("/api/valuation/percentile")
def valuation_percentile(code: str = Query(...)):
    """PE-TTM / PB 历史分位（近5年）。全站缓存 30 分钟/代码（历史序列日频、变化慢）。"""
    code = _validate(code)
    hit = _PCT_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.valuation_percentile(code)
        _PCT_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值分位异常：{e}") from e


_ANN_CACHE: dict = {}


@app.get("/api/announcements")
def announcements(
    code: str = Query(...),
    asset_type: str = Query("stock", alias="assetType", pattern="^(stock|etf|fund)$"),
):
    """股票、ETF 或开放式基金近期公告。缓存 15 分钟/标的。"""
    code = _validate(code)
    cache_key = (asset_type, code)
    hit = _ANN_CACHE.get(cache_key)
    if hit and _time.time() - hit[0] < 900:
        return {"data": hit[1]}
    try:
        data = astock.fund_announcements(code) if asset_type in {"etf", "fund"} else astock.announcements(code)
        _ANN_CACHE[cache_key] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"公告源异常：{e}") from e


_FIN_CACHE: dict = {}


@app.get("/api/financials")
def financials(code: str = Query(...)):
    """财务关键指标（同花顺财务摘要，最新报告期）。缓存 30 分钟/代码。"""
    code = _validate(code)
    hit = _FIN_CACHE.get(code)
    if hit and _time.time() - hit[0] < 1800:
        return {"data": hit[1]}
    try:
        data = astock.financials(code)
        _FIN_CACHE[code] = (_time.time(), data)
        return {"data": data}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务摘要异常：{e}") from e


@app.get("/api/valuation")
def valuation(code: str = Query(...)):
    """完整估值：行情 + 一致预期 + 前向PE/PEG/消化年数。"""
    code = _validate(code)
    try:
        return {"data": astock.full_valuation(code)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"估值计算异常：{e}") from e


@app.get("/api/reports")
def reports(code: str = Query(...), pages: int = Query(2, ge=1, le=5)):
    """个股研报列表（东财，含 PDF 链接）。仅需 requests。"""
    code = _validate(code)
    try:
        rows = astock.eastmoney_reports(code, max_pages=pages)
        for r in rows:
            r["pdfUrl"] = astock.pdf_url(r.get("infoCode", "")) if r.get("infoCode") else None
        return {"data": rows}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"研报源异常：{e}") from e


@app.get("/api/news")
def news(code: str = Query(...), limit: int = Query(20, ge=1, le=50)):
    """个股新闻（东财，需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.stock_news(code, limit=limit)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"新闻源异常：{e}") from e


@app.get("/api/info")
def info(code: str = Query(...)):
    """个股基本面：行业/股本/上市时间（需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.individual_info(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"基本面源异常：{e}") from e


@app.get("/api/disclosure")
def disclosure(code: str = Query(...)):
    """巨潮公告列表（需 akshare）。"""
    code = _validate(code)
    try:
        return {"data": astock.disclosure(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"公告源异常：{e}") from e


@app.get("/api/kline")
def kline(code: str = Query(...), category: int = Query(4), offset: int = Query(60, ge=1, le=800)):
    """K线兼容接口。category 4=日 5=周 6=月 11=60分钟。"""
    code = _validate(code)
    try:
        return {"data": astock.kline(code, category=category, offset=offset)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"K线源异常：{e}") from e


@app.get("/api/finance")
def finance(code: str = Query(...)):
    """季报财务快照（需 mootdx）。"""
    code = _validate(code)
    try:
        return {"data": astock.finance(code)}
    except astock.DependencyMissing as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"财务源异常：{e}") from e


# ---------------------------------------------------------------------------
# 资金面 / 筹码 / 信号（东财数据中心，v3.3 并入）—— 均为「用户查的那只股」的公开数据。
# 东财有 1s 限流，这些多为日/季级静态数据，统一走 30 分钟缓存，进一步降低被封风险。
# ---------------------------------------------------------------------------

_DC_CACHE: dict = {}  # key=(endpoint, code) -> (ts, data)


def _cached(endpoint: str, code: str, ttl: int, fetch):
    key = (endpoint, code)
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    data = fetch()
    _DC_CACHE[key] = (_time.time(), data)
    return data


@app.get("/api/margin")
def margin(code: str = Query(...)):
    """融资融券明细（东财，日级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("margin", code, 1800, lambda: astock.margin_trading(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"融资融券异常：{e}") from e


@app.get("/api/block-trade")
def block_trade(code: str = Query(...)):
    """大宗交易（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("block", code, 1800, lambda: astock.block_trade(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"大宗交易异常：{e}") from e


@app.get("/api/holders")
def holders(code: str = Query(...)):
    """股东户数变化（东财，季度级）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("holders", code, 1800, lambda: astock.holder_num_change(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"股东户数异常：{e}") from e


@app.get("/api/dividend")
def dividend(code: str = Query(...)):
    """分红送转历史（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dividend", code, 1800, lambda: astock.dividend_history(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"分红送转异常：{e}") from e


@app.get("/api/fund-flow")
def fund_flow(code: str = Query(...)):
    """个股资金流（东财 push2his，120 日主力净流入）。缓存 15 分钟。
    注：push2his 对部分大陆住宅 IP 有间歇风控，可能返回空（非代码问题）。"""
    code = _validate(code)
    try:
        return {"data": _cached("fundflow", code, 900, lambda: astock.stock_fund_flow_120d(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"资金流异常：{e}") from e


@app.get("/api/dragon-tiger")
def dragon_tiger(code: str = Query(...)):
    """龙虎榜：该股近期上榜记录 + 买卖席位 + 机构净买（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("dt", code, 1800, lambda: astock.dragon_tiger_board(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"龙虎榜异常：{e}") from e


@app.get("/api/lockup")
def lockup(code: str = Query(...)):
    """限售解禁日历：历史解禁 + 未来 90 天待解禁（东财）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("lockup", code, 1800, lambda: astock.lockup_expiry(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"解禁日历异常：{e}") from e


@app.get("/api/blocks")
def blocks(code: str = Query(...)):
    """个股所属板块/概念归属（东财 slist）。缓存 30 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("blocks", code, 1800, lambda: astock.concept_blocks(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"板块归属异常：{e}") from e


@app.get("/api/hot-concepts")
def hot_concepts(code: str = Query(...)):
    """个股当下被市场归到哪些概念在炒（东财热门概念命中）。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("hotcon", code, 900, lambda: astock.hot_concepts(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"热门概念异常：{e}") from e


@app.get("/api/investor-qa")
def investor_qa(code: str = Query(...)):
    """互动易问答（巨潮）：投资者提问 + 公司回复。缓存 15 分钟。"""
    code = _validate(code)
    try:
        return {"data": _cached("irm", code, 900, lambda: astock.investor_qa(code))}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"互动易异常：{e}") from e


@app.get("/api/industry")
def industry(top: int = Query(20, ge=5, le=50)):
    """全行业涨跌幅排名（东财行业板块，板块级、零个股名单）。缓存 5 分钟。"""
    key = ("industry", str(top))
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < 300:
        return {"data": hit[1]}
    try:
        data = astock.industry_comparison(top_n=top)
        _DC_CACHE[key] = (_time.time(), data)
        return {"data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"行业排名异常：{e}") from e
