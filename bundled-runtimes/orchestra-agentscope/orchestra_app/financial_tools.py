from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

import httpx
from agentscope.message import TextBlock
from agentscope.tool import FunctionTool, ToolChunk

from .credentials import current_credentials
from .settings import settings


API_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
STOCK_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/138 Safari/537.36"
)
_eastmoney_lock = asyncio.Lock()
_ima_base_cache: dict[str, list[dict[str, str]]] = {}


def _text_chunk(payload: dict[str, Any]) -> ToolChunk:
    return ToolChunk(
        content=[TextBlock(text=json.dumps(payload, ensure_ascii=False, default=str))],
    )


async def tushare_query(
    api_name: str,
    params: dict[str, Any] | None = None,
    fields: str = "",
    row_limit: int = 50,
) -> ToolChunk:
    """Query a read-only Tushare Pro endpoint and return bounded JSON rows.

    Args:
        api_name: Tushare Pro API name, such as daily, fund_portfolio or cn_gdp.
        params: Endpoint parameters such as ts_code, start_date and end_date.
        fields: Comma-separated fields to request. Empty means endpoint defaults.
        row_limit: Maximum rows returned to the model, capped by server settings.
    """
    credentials = current_credentials()
    if not credentials.tushare_token:
        return _text_chunk(
            {"ok": False, "source": "Tushare Pro", "error": "TUSHARE_TOKEN 未配置"},
        )
    if not API_NAME_PATTERN.fullmatch(api_name):
        return _text_chunk(
            {"ok": False, "source": "Tushare Pro", "error": "api_name 格式无效"},
        )

    limit = min(max(1, row_limit), settings.max_financial_rows)
    request_body = {
        "api_name": api_name,
        "token": credentials.tushare_token,
        "params": params or {},
        "fields": fields,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.financial_tool_timeout) as client:
            response = await client.post(settings.tushare_api_url, json=request_body)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _text_chunk(
            {
                "ok": False,
                "source": "Tushare Pro",
                "api_name": api_name,
                "error": f"请求失败：{error}",
            },
        )

    if payload.get("code") != 0:
        return _text_chunk(
            {
                "ok": False,
                "source": "Tushare Pro",
                "api_name": api_name,
                "error": payload.get("msg") or "接口返回错误",
                "code": payload.get("code"),
            },
        )

    data = payload.get("data") or {}
    field_names = data.get("fields") or []
    items = data.get("items") or []
    rows = [dict(zip(field_names, item, strict=False)) for item in items[:limit]]
    return _text_chunk(
        {
            "ok": True,
            "source": "Tushare Pro",
            "api_name": api_name,
            "params": params or {},
            "fields": field_names,
            "row_count": len(rows),
            "total_rows": len(items),
            "truncated": len(items) > len(rows),
            "rows": rows,
        },
    )


async def tavily_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
) -> ToolChunk:
    """Search public web sources with Tavily and return bounded cited results.

    Args:
        query: Search query including entity, topic and desired date range.
        max_results: Maximum results returned, from 1 to 10.
        search_depth: Tavily search depth, basic or advanced.
    """
    credentials = current_credentials()
    if not credentials.tavily_api_key:
        return _text_chunk(
            {"ok": False, "source": "Tavily", "error": "TAVILY_API_KEY 未配置"},
        )

    result_limit = min(max(1, max_results), 10)
    depth = search_depth if search_depth in {"basic", "advanced"} else "advanced"
    try:
        async with httpx.AsyncClient(timeout=settings.financial_tool_timeout) as client:
            response = await client.post(
                settings.tavily_api_url,
                json={
                    "api_key": credentials.tavily_api_key,
                    "query": query,
                    "search_depth": depth,
                    "max_results": result_limit,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _text_chunk(
            {"ok": False, "source": "Tavily", "error": f"请求失败：{error}"},
        )

    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": (item.get("content") or "")[: settings.max_web_content_chars],
            "score": item.get("score"),
            "published_date": item.get("published_date"),
        }
        for item in (payload.get("results") or [])[:result_limit]
    ]
    return _text_chunk(
        {
            "ok": True,
            "source": "Tavily",
            "query": query,
            "row_count": len(results),
            "results": results,
        },
    )


def _normalize_a_share_symbol(symbol: str) -> tuple[str, str, str] | None:
    match = STOCK_CODE_PATTERN.search(symbol)
    if not match:
        return None
    code = match.group(1)
    market = "sh" if code.startswith(("5", "6", "9")) else "bj" if code.startswith("8") else "sz"
    secid = f"{1 if market == 'sh' else 0}.{code}"
    return code, market, secid


async def _eastmoney_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    async with _eastmoney_lock:
        async with httpx.AsyncClient(
            timeout=settings.financial_tool_timeout,
            headers={"User-Agent": USER_AGENT, "Referer": "https://quote.eastmoney.com/"},
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        await asyncio.sleep(0.45)
    return payload


async def a_stock_data(
    action: str,
    symbol: str = "",
    row_limit: int = 20,
) -> ToolChunk:
    """Query the BOT a-stock-data public-source layer for A-share market evidence.

    Args:
        action: One of quote, fund_flow, margin, reports or industry_rank.
        symbol: Six-digit A-share code for symbol-specific actions.
        row_limit: Maximum returned records, capped by Orchestra settings.
    """
    normalized_action = action.strip().lower()
    limit = min(max(1, row_limit), settings.max_financial_rows)
    symbol_info = _normalize_a_share_symbol(symbol)
    if normalized_action != "industry_rank" and symbol_info is None:
        return _text_chunk(
            {"ok": False, "source": "A Stock Data", "error": "symbol 需要包含6位A股代码"},
        )

    try:
        if normalized_action == "quote" and symbol_info:
            code, market, _ = symbol_info
            async with httpx.AsyncClient(timeout=settings.financial_tool_timeout) as client:
                response = await client.get(
                    "https://qt.gtimg.cn/q=" + market + code,
                    headers={"User-Agent": USER_AGENT, "Referer": "https://gu.qq.com/"},
                )
                response.raise_for_status()
            text = response.content.decode("gbk", errors="ignore")
            match = re.search(r'="(.+)"', text)
            fields = match.group(1).split("~") if match else []
            if len(fields) < 40:
                raise ValueError("腾讯行情返回字段不足")
            row = {
                "name": fields[1],
                "code": fields[2],
                "price": fields[3],
                "prev_close": fields[4],
                "open": fields[5],
                "volume_lots": fields[6],
                "timestamp": fields[30],
                "change": fields[31],
                "change_pct": fields[32],
                "high": fields[33],
                "low": fields[34],
                "turnover_amount_wan": fields[37],
                "turnover_rate": fields[38],
                "pe_ttm": fields[39],
                "pb": fields[46] if len(fields) > 46 else None,
                "float_market_cap_yi": fields[44] if len(fields) > 44 else None,
                "market_cap_yi": fields[45] if len(fields) > 45 else None,
            }
            return _text_chunk(
                {
                    "ok": True,
                    "source": "A Stock Data / Tencent Finance",
                    "action": normalized_action,
                    "symbol": code,
                    "row_count": 1,
                    "rows": [row],
                },
            )

        if normalized_action == "fund_flow" and symbol_info:
            code, _, secid = symbol_info
            payload = await _eastmoney_get(
                "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                {
                    "secid": secid,
                    "fields1": "f1,f2,f3,f7",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                    "lmt": str(limit),
                },
            )
            rows = []
            for line in ((payload.get("data") or {}).get("klines") or [])[-limit:]:
                parts = line.split(",")
                if len(parts) >= 6:
                    rows.append(
                        {
                            "date": parts[0],
                            "main_net": parts[1],
                            "small_net": parts[2],
                            "mid_net": parts[3],
                            "large_net": parts[4],
                            "super_net": parts[5],
                        },
                    )
            return _text_chunk(
                {
                    "ok": True,
                    "source": "A Stock Data / Eastmoney fund flow",
                    "action": normalized_action,
                    "symbol": code,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )

        if normalized_action == "margin" and symbol_info:
            code, _, _ = symbol_info
            payload = await _eastmoney_get(
                "https://datacenter-web.eastmoney.com/api/data/v1/get",
                {
                    "reportName": "RPTA_WEB_RZRQ_GGMX",
                    "columns": "ALL",
                    "filter": f'(SCODE="{code}")',
                    "pageNumber": "1",
                    "pageSize": str(limit),
                    "sortColumns": "DATE",
                    "sortTypes": "-1",
                    "source": "WEB",
                    "client": "WEB",
                },
            )
            items = ((payload.get("result") or {}).get("data") or [])[:limit]
            rows = [
                {
                    "date": str(item.get("DATE") or "")[:10],
                    "financing_balance": item.get("RZYE"),
                    "financing_buy": item.get("RZMRE"),
                    "financing_repay": item.get("RZCHE"),
                    "securities_lending_balance": item.get("RQYE"),
                    "margin_balance": item.get("RZRQYE"),
                }
                for item in items
            ]
            return _text_chunk(
                {
                    "ok": True,
                    "source": "A Stock Data / Eastmoney margin",
                    "action": normalized_action,
                    "symbol": code,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )

        if normalized_action == "reports" and symbol_info:
            code, _, _ = symbol_info
            payload = await _eastmoney_get(
                "https://reportapi.eastmoney.com/report/list",
                {
                    "industryCode": "*",
                    "pageSize": str(limit),
                    "industry": "*",
                    "rating": "*",
                    "ratingChange": "*",
                    "beginTime": "2024-01-01",
                    "endTime": "2030-01-01",
                    "pageNo": "1",
                    "qType": "0",
                    "code": code,
                },
            )
            rows = [
                {
                    "title": item.get("title"),
                    "institution": item.get("orgSName"),
                    "analyst": item.get("researcher"),
                    "rating": item.get("emRatingName"),
                    "rating_change": item.get("ratingChange"),
                    "publish_date": str(item.get("publishDate") or "")[:10],
                    "eps_current_year": item.get("predictThisYearEps"),
                    "eps_next_year": item.get("predictNextYearEps"),
                    "pdf_url": (
                        f"https://pdf.dfcfw.com/pdf/H3_{item.get('infoCode')}_1.pdf"
                        if item.get("infoCode")
                        else None
                    ),
                }
                for item in (payload.get("data") or [])[:limit]
            ]
            return _text_chunk(
                {
                    "ok": True,
                    "source": "A Stock Data / Eastmoney reports",
                    "action": normalized_action,
                    "symbol": code,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )

        if normalized_action == "industry_rank":
            payload = await _eastmoney_get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": "1",
                    "pz": "100",
                    "po": "1",
                    "np": "1",
                    "fltt": "2",
                    "invt": "2",
                    "fs": "m:90+t:2",
                    "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
                },
            )
            items = ((payload.get("data") or {}).get("diff") or [])
            rows = [
                {
                    "rank": index + 1,
                    "name": item.get("f14"),
                    "code": item.get("f12"),
                    "change_pct": item.get("f3"),
                    "up_count": item.get("f104"),
                    "down_count": item.get("f105"),
                    "leader": item.get("f140"),
                    "leader_change_pct": item.get("f136"),
                }
                for index, item in enumerate(items[:limit])
            ]
            return _text_chunk(
                {
                    "ok": True,
                    "source": "A Stock Data / Eastmoney industries",
                    "action": normalized_action,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )
    except (httpx.HTTPError, ValueError, TypeError) as error:
        return _text_chunk(
            {
                "ok": False,
                "source": "A Stock Data",
                "action": normalized_action,
                "error": f"请求失败：{error}",
            },
        )

    return _text_chunk(
        {
            "ok": False,
            "source": "A Stock Data",
            "error": "action 仅支持 quote、fund_flow、margin、reports、industry_rank",
        },
    )


async def global_stock_data(
    action: str,
    symbol: str,
    market: str = "us",
    range_name: str = "1y",
    interval: str = "1d",
    row_limit: int = 60,
) -> ToolChunk:
    """Query the BOT global-stock-data public-source layer for US/HK evidence.

    Args:
        action: One of quote, chart or search.
        symbol: US ticker, HK code, or a search phrase.
        market: us or hk.
        range_name: Yahoo chart range such as 1mo, 6mo, 1y or 5y.
        interval: Yahoo chart interval such as 1d or 1wk.
        row_limit: Maximum chart/search records returned.
    """
    normalized_action = action.strip().lower()
    normalized_market = market.strip().lower()
    limit = min(max(1, row_limit), settings.max_financial_rows)
    try:
        if normalized_action == "quote":
            if normalized_market == "hk":
                code = re.sub(r"\D", "", symbol).zfill(5)
                query_code = f"r_hk{code}"
            else:
                code = re.sub(r"[^A-Za-z.-]", "", symbol).upper()
                query_code = f"us{code}"
            async with httpx.AsyncClient(timeout=settings.financial_tool_timeout) as client:
                response = await client.get(f"https://qt.gtimg.cn/q={query_code}")
                response.raise_for_status()
            text = response.content.decode("gbk", errors="ignore")
            match = re.search(r'="(.+)"', text)
            fields = match.group(1).split("~") if match else []
            if len(fields) < 45:
                raise ValueError("腾讯全球行情返回字段不足")
            row = {
                "name": fields[1],
                "symbol": fields[2],
                "price": fields[3],
                "prev_close": fields[4],
                "open": fields[5],
                "volume": fields[6],
                "timestamp": fields[30],
                "change_pct": fields[32],
                "high": fields[33],
                "low": fields[34],
                "currency": (
                    fields[75]
                    if normalized_market == "hk" and len(fields) > 75
                    else fields[35] if len(fields) > 35 else None
                ),
                "high_52w": fields[48] if len(fields) > 48 else None,
                "low_52w": fields[49] if len(fields) > 49 else None,
                "market_cap": fields[44] if len(fields) > 44 else None,
                "float_market_cap": fields[45] if len(fields) > 45 else None,
                "pe": fields[39] if len(fields) > 39 else None,
                "pb": (
                    fields[58]
                    if normalized_market == "hk" and len(fields) > 58
                    else fields[41] if len(fields) > 41 else None
                ),
            }
            return _text_chunk(
                {
                    "ok": True,
                    "source": "Global Stock Data / Tencent Finance",
                    "action": normalized_action,
                    "market": normalized_market,
                    "row_count": 1,
                    "rows": [row],
                },
            )

        if normalized_action == "chart":
            hk_code = re.sub(r"\D", "", symbol).lstrip("0") or "0"
            yahoo_symbol = (
                f"{hk_code}.HK"
                if normalized_market == "hk"
                else re.sub(r"[^A-Za-z0-9.^=-]", "", symbol).upper()
            )
            async with httpx.AsyncClient(
                timeout=settings.financial_tool_timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
                    params={"range": range_name, "interval": interval, "events": "div,splits"},
                )
                response.raise_for_status()
                payload = response.json()
            result = (((payload.get("chart") or {}).get("result") or [{}])[0])
            timestamps = result.get("timestamp") or []
            quote = ((((result.get("indicators") or {}).get("quote") or [{}])[0]))
            rows = []
            for index, timestamp in enumerate(timestamps[-limit:]):
                source_index = len(timestamps) - min(len(timestamps), limit) + index
                rows.append(
                    {
                        "timestamp": timestamp,
                        "open": (quote.get("open") or [None] * len(timestamps))[source_index],
                        "high": (quote.get("high") or [None] * len(timestamps))[source_index],
                        "low": (quote.get("low") or [None] * len(timestamps))[source_index],
                        "close": (quote.get("close") or [None] * len(timestamps))[source_index],
                        "volume": (quote.get("volume") or [None] * len(timestamps))[source_index],
                    },
                )
            return _text_chunk(
                {
                    "ok": True,
                    "source": "Global Stock Data / Yahoo Finance",
                    "action": normalized_action,
                    "symbol": yahoo_symbol,
                    "range": range_name,
                    "interval": interval,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )

        if normalized_action == "search":
            async with httpx.AsyncClient(
                timeout=settings.financial_tool_timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(
                    "https://query2.finance.yahoo.com/v1/finance/search",
                    params={"q": symbol, "quotesCount": str(limit), "newsCount": "0"},
                )
                response.raise_for_status()
                payload = response.json()
            rows = [
                {
                    "symbol": item.get("symbol"),
                    "name": item.get("longname") or item.get("shortname"),
                    "exchange": item.get("exchange"),
                    "type": item.get("quoteType"),
                }
                for item in (payload.get("quotes") or [])[:limit]
            ]
            return _text_chunk(
                {
                    "ok": True,
                    "source": "Global Stock Data / Yahoo Search",
                    "action": normalized_action,
                    "query": symbol,
                    "row_count": len(rows),
                    "rows": rows,
                },
            )
    except (httpx.HTTPError, ValueError, TypeError, IndexError) as error:
        return _text_chunk(
            {
                "ok": False,
                "source": "Global Stock Data",
                "action": normalized_action,
                "error": f"请求失败：{error}",
            },
        )
    return _text_chunk(
        {"ok": False, "source": "Global Stock Data", "error": "action 仅支持 quote、chart、search"},
    )


async def _ima_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    credentials = current_credentials()
    if not credentials.ima_client_id or not credentials.ima_api_key:
        raise ValueError("IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY 未配置")
    async with httpx.AsyncClient(timeout=settings.financial_tool_timeout) as client:
        response = await client.post(
            f"{settings.ima_base_url.rstrip('/')}/{path.lstrip('/')}",
            headers={
                "ima-openapi-clientid": credentials.ima_client_id,
                "ima-openapi-apikey": credentials.ima_api_key,
                "ima-openapi-ctx": "skill_version=1.1.8",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(str(payload.get("msg") or "IMA 接口返回错误"))
    return payload.get("data") or {}


async def _ima_knowledge_bases() -> list[dict[str, str]]:
    credentials = current_credentials()
    if settings.ima_knowledge_base_ids:
        return [
            {"id": item, "name": f"Configured IMA KB {index + 1}"}
            for index, item in enumerate(settings.ima_knowledge_base_ids)
        ]
    cache_key = hashlib.sha256((credentials.ima_client_id or "").encode()).hexdigest()[:16]
    if cache_key in _ima_base_cache:
        return _ima_base_cache[cache_key]
    data = await _ima_post(
        "openapi/wiki/v1/get_addable_knowledge_base_list",
        {"cursor": "", "limit": 50},
    )
    bases = [
        {"id": str(item.get("id") or ""), "name": str(item.get("name") or "未命名知识库")}
        for item in data.get("addable_knowledge_base_list") or []
        if item.get("id")
    ]
    _ima_base_cache[cache_key] = bases
    return bases


async def ima_knowledge_search(
    query: str,
    knowledge_base_id: str = "",
    max_results: int = 6,
    include_content: bool = True,
) -> ToolChunk:
    """Search the user's IMA knowledge bases and return cited snippets or note content.

    Args:
        query: Keywords to search in IMA, preferably concise industry/entity terms.
        knowledge_base_id: Optional exact IMA knowledge base ID. Empty searches discovered bases.
        max_results: Maximum combined records returned, from 1 to 10.
        include_content: Retrieve readable note text for the first matching notes when permitted.
    """
    limit = min(max(1, max_results), 10)
    try:
        bases = (
            [{"id": knowledge_base_id, "name": "指定知识库"}]
            if knowledge_base_id
            else await _ima_knowledge_bases()
        )
        results: list[dict[str, Any]] = []
        for base in bases:
            data = await _ima_post(
                "openapi/wiki/v1/search_knowledge",
                {
                    "query": query,
                    "cursor": "",
                    "knowledge_base_id": base["id"],
                },
            )
            for item in data.get("info_list") or []:
                result = {
                    "knowledge_base_id": base["id"],
                    "knowledge_base_name": base["name"],
                    "media_id": item.get("media_id"),
                    "media_type": item.get("media_type"),
                    "title": item.get("title"),
                    "highlight": (item.get("highlight_content") or "")[:1200],
                }
                if include_content and item.get("media_type") == 11 and len(results) < 3:
                    media = await _ima_post(
                        "openapi/wiki/v1/get_media_info",
                        {"media_id": item.get("media_id")},
                    )
                    note_id = ((media.get("notebook_ext_info") or {}).get("notebook_id"))
                    if note_id:
                        content = await _ima_post(
                            "openapi/note/v1/get_doc_content",
                            {"note_id": note_id, "target_content_format": 0},
                        )
                        result["content_excerpt"] = str(content.get("content") or "")[
                            : settings.max_web_content_chars * 2
                        ]
                results.append(result)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return _text_chunk(
            {
                "ok": True,
                "source": "IMA Knowledge Base",
                "query": query,
                "searched_bases": [{"id": item["id"], "name": item["name"]} for item in bases],
                "row_count": len(results),
                "results": results,
            },
        )
    except (httpx.HTTPError, ValueError, TypeError) as error:
        return _text_chunk(
            {"ok": False, "source": "IMA Knowledge Base", "query": query, "error": str(error)},
        )


def financial_function_tools() -> list[FunctionTool]:
    return [
        FunctionTool(tushare_query, is_read_only=True),
        FunctionTool(a_stock_data, is_read_only=True),
        FunctionTool(global_stock_data, is_read_only=True),
        FunctionTool(tavily_search, is_read_only=True),
        FunctionTool(ima_knowledge_search, is_read_only=True),
    ]
