from __future__ import annotations

import asyncio
import math
import statistics
from datetime import datetime, timezone

import httpx

from vibe_visualization_api.capital_flow.liquidity import LiquidityResearchService
from vibe_visualization_api.capital_flow.research import CapitalResearchService
from vibe_visualization_api.capital_flow.sectors import SectorResearchService
from vibe_visualization_api.capital_flow.service import finite_number


BROAD_POOL = ("510300.SH", "510500.SH", "159915.SZ")


def benchmark_analysis(feed: dict, sessions: list[str], calendar_ok: bool) -> dict:
    indexed = {row["date"]: row for row in feed["rows"] if row.get("ts_code") == "000300.SH"}
    points = [{"date": day, "close": finite_number(indexed.get(day, {}).get("close")),
               "pct": finite_number(indexed.get(day, {}).get("pct_chg"))} for day in sessions[-60:]]
    def returns(days):
        values = [row["pct"] for row in points[-days:]]
        return round((math.prod(1 + value / 100 for value in values) - 1) * 100, 4) if len(values) == days and all(value is not None for value in values) else None
    daily = [row["pct"] for row in points[-20:]]
    vol = statistics.stdev(daily) * math.sqrt(252) if len(daily) == 20 and all(value is not None for value in daily) else None
    prices = [row["close"] for row in points]
    drawdown = None
    if len(prices) == 60 and all(value is not None and value > 0 for value in prices):
        peak, drawdown = prices[0], 0.0
        for price in prices:
            peak = max(peak, price)
            drawdown = min(drawdown, (price / peak - 1) * 100)
    latest = max(indexed, default=None)
    return {"code": "000300.SH", "name": "沪深300价格指数", "asOf": latest,
            "current": bool(calendar_ok and sessions and latest == sessions[-1] and feed["status"] == "ready" and not feed.get("usingSaved")),
            "points": points, "return5dPct": returns(5), "return20dPct": returns(20),
            "volatility20dPct": round(vol, 4) if vol is not None else None,
            "maxDrawdown60dPct": round(drawdown, 4) if drawdown is not None else None,
            "volatilitySamples": sum(value is not None for value in daily),
            "drawdownSamples": sum(value is not None and value > 0 for value in prices),
            "source": "Tushare index_daily · 000300.SH",
            "note": "价格指数不含分红再投资。区间收益复合每日涨跌幅；20日波动率为日收益样本标准差×√252；最大回撤限最近60交易日收盘价，缺观测不计算。"}


def breadth_analysis(sectors: dict) -> dict:
    buckets = {key: {"id": key, "name": name, "count": 0, "examples": []} for key, name in (
        ("aligned", "上涨且净流入"), ("price-only", "上涨但净流出"),
        ("absorption", "下跌且净流入"), ("weak", "下跌且净流出"),
        ("flat", "价格或净额持平"), ("missing", "缺少可比字段"))}
    for row in sectors.get("boards", []):
        net, pct = finite_number(row.get("net")), finite_number(row.get("pct"))
        key = "missing" if net is None or pct is None else "flat" if net == 0 or pct == 0 else (
            "aligned" if net > 0 and pct > 0 else "price-only" if net < 0 and pct > 0 else "absorption" if net > 0 else "weak")
        buckets[key]["count"] += 1
        if len(buckets[key]["examples"]) < 6:
            buckets[key]["examples"].append({"code": row["code"], "name": row["name"]})
    total = sum(row["count"] for row in buckets.values())
    coverage = sectors.get("coverage", {})
    return {"asOf": sectors.get("asOf"), "total": total, "comparable": total - buckets["missing"]["count"],
            "current": bool(total and coverage.get("status") == "ready" and not coverage.get("usingSaved")
                and sectors.get("calendar", {}).get("status") == "ready" and sectors.get("asOf") == sectors.get("expectedDate")),
            "buckets": list(buckets.values()), "source": sectors.get("source"),
            "scope": "东财一级行业" if sectors.get("level") == "L1" else "行业及子行业",
            "classification": sectors.get("classification"),
            "note": "只观察同日代码匹配的东财一级行业，不混入二级/三级；成分交叉尚未核验，不是全市场上涨家数或5/20日历史信号。"
                    if sectors.get("level") == "L1" else "当日行业与子行业观察样本，成分可能重叠；不代表全市场，也不是5/20日历史信号。"}


def build_window(days: int, funding: dict, liquidity: dict, market: dict) -> dict:
    sessions = funding.get("calendar", {}).get("dates", [])
    end = funding.get("expectedDate")
    start = sessions[-days] if len(sessions) >= days else None
    calendar_ok = funding.get("calendar", {}).get("status") == "ready" and bool(end and start)
    pool = {row["code"]: row for row in funding.get("etfs", [])}
    etfs = []
    for code in BROAD_POOL:
        row = pool.get(code, {})
        amount = finite_number(row.get("summary", {}).get(f"flow{days}dYi"))
        current = bool(calendar_ok and amount is not None and row.get("fetchStatus") == "ready"
                       and not row.get("usingSaved") and row.get("asOf") == end)
        etfs.append({"code": code, "name": row.get("name") or code, "value": amount, "current": current,
                     "asOf": row.get("asOf"), "note": row.get("sourceNote") or row.get("note", "未取得该ETF")})
    values = [row["value"] for row in etfs]
    etf_value = round(sum(values), 4) if all(value is not None for value in values) else None
    leverage = funding.get("leverage", {})
    margin_value = finite_number(leverage.get("summary", {}).get(f"net{days}dYi"))
    price_value = market.get(f"return{days}dPct")
    def evidence(key, name, value, unit, current, as_of, scope, source, note):
        return {"id": key, "name": name, "value": value, "unit": unit, "current": bool(current and value is not None),
                "asOf": as_of, "scope": scope, "source": source, "note": note}
    rows = [
        evidence("price", "沪深300区间涨跌", price_value, "%", calendar_ok and market["current"], market["asOf"],
                 f"{days}交易日", market["source"], "大盘价格参照，不能代替全市场或管理组合的收益。"),
        evidence("etf", "宽基ETF申赎估算", etf_value, "亿元", all(row["current"] for row in etfs),
                 etfs[0]["asOf"] if len({row["asOf"] for row in etfs}) == 1 else None,
                 f"{days}交易日 · 3只观察池", "Tushare份额变化 × 同日净值", "三只均完整才合计；含实物申赎和套利，非外部现金净流入。"),
        evidence("margin", "沪深北融资净增加", margin_value, "亿元", calendar_ok and leverage.get("fetchStatus") == "ready"
                 and not leverage.get("usingSaved") and leverage.get("asOf") == end,
                 leverage.get("asOf"), f"{days}交易日", leverage.get("source", "Tushare margin"),
                 "融资买入减偿还；三所缺一不合计，不能与ETF申赎相加。"),
    ]
    rates = {row["id"]: row for row in liquidity.get("daily", {}).get("series", [])}
    for key, name in (("dr007", "DR007成本变化"), ("spreadBp", "R007−DR007利差变化")):
        rate = rates.get(key, {})
        rows.append(evidence(key, name, rate.get(f"change{days}Bp"), "bp", rate.get("current"), rate.get("asOf"),
                             f"{days}观测日", "Tushare repo_daily · 加权价", "货币市场观测日与股票交易日可能不同；作为背景条件，独立解读。"))
    social = liquidity.get("credit", {}).get("social", {})
    rows.append(evidence("credit", "近3月社融同比多增", social.get("flow3mYoYDiffYi"), "亿元", social.get("current"),
                         social.get("month"), "同季节3个月 · 与日频窗口独立", "Tushare sf_month",
                         "含政府债券融资，不直接代表私人需求；需与存量增速共同验证。"))
    by_id = {row["id"]: row for row in rows}
    def relation(key, inputs, positive, negative, cross_up, cross_down, watch):
        a, b = [by_id[name] for name in inputs]
        state, title = "incomplete", "证据未齐，暂不能确认"
        if a["current"] and b["current"]:
            if a["value"] == 0 or b["value"] == 0:
                state, title = "flat", "至少一项持平，方向未形成"
            elif a["value"] > 0 and b["value"] > 0:
                state, title = "aligned", positive
            elif a["value"] < 0 and b["value"] < 0:
                state, title = "aligned", negative
            else:
                state, title = "divergent", cross_up if a["value"] > 0 else cross_down
        return {"id": key, "inputs": inputs, "status": state, "title": title, "watch": watch}
    relationships = [
        relation("price-etf", ["price", "etf"], "价格上涨、宽基配置净申购", "价格回落、宽基配置净赎回",
                 "价格上涨，但宽基配置净赎回", "价格回落，宽基仍净申购",
                 "查看三只ETF是否同向及份额公告；价格指数和ETF池覆盖不同，背离并不说明价格将反转。"),
        relation("price-margin", ["price", "margin"], "价格上涨、融资净增加", "价格回落、融资净减少",
                 "价格上涨，融资净减少", "价格回落，融资仍净增加",
                 "下跌伴随融资净增加时，核查持仓集中、融资期限和安全垫；本页不掌握账户负债，不能推断爆仓风险。"),
    ]
    if relationships[1]["status"] != "incomplete":
        relationships[1]["watch"] = (
            "融资买入减偿还为负；核查到期、主动偿还与余额集中度，净减少不等于所有账户减仓。"
            if margin_value < 0 else
            "融资净增加与上涨同向；核查余额集中、融资期限和后续成交承接，不把杠杆增加当作趋势保证。"
            if margin_value > 0 and price_value > 0 else
            "下跌伴随融资净增加时，核查持仓集中、融资期限和安全垫；本页没有账户负债，不能推断爆仓风险。"
            if margin_value > 0 and price_value < 0 else "至少一项持平，等待后续同窗口观察；不能据此判断账户安全垫。"
        )
    # Money-market conditions are compared only with each other, outside the equity conclusion.
    conditions = relation("cost-spread", ["dr007", "spreadBp"], "成本与分层利差同时上升", "成本与分层利差同时下降",
                          "融资成本上升，分层利差收窄", "融资成本下降，分层利差走阔",
                          "绝对成本和资金分层分别核对；不能据此直接推断权益资金流入。")
    return {"days": days, "start": start, "end": end, "evidence": rows, "etfs": etfs,
            "relationships": relationships, "conditions": conditions,
            "verifiedRelationships": sum(row["status"] != "incomplete" for row in relationships),
            "divergences": sum(row["status"] == "divergent" for row in relationships)}


class AppetiteResearchService(CapitalResearchService):
    async def research(self, *, refresh=False) -> dict:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            funding_service = CapitalResearchService(self.token, self.store, client=client, today=self.today)
            liquidity_service = LiquidityResearchService(self.token, self.store, client=client, today=self.today)
            sectors_service = SectorResearchService(self.token, self.store, client=client, today=self.today)
            funding, liquidity, sectors, benchmark = await asyncio.gather(
                funding_service.research(refresh=refresh), liquidity_service.research(refresh=refresh),
                sectors_service.research(refresh=refresh, include_history=False, level="L1"),
                self._dataset(client, "index_daily", "000300.SH", {"ts_code": "000300.SH"},
                              "ts_code,trade_date,close,pct_chg", refresh=refresh, cache_key="appetite.index.v1"),
            )
            calendar = funding["calendar"]
            market = benchmark_analysis(benchmark, calendar["dates"], calendar["status"] == "ready")
            return {"schemaVersion": "newma-desk.appetite.v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "expectedDate": funding["expectedDate"], "market": market, "breadth": breadth_analysis(sectors),
                    "sectorSnapshot": sectors,
                    "windows": {str(days): build_window(days, funding, liquidity, market) for days in (5, 20)},
                    "leverage": funding["leverage"],
                    "credit": {"money": liquidity["credit"]["money"], "social": liquidity["credit"]["social"],
                               "transmission": [row for row in liquidity["transmission"] if row["id"] in {"money", "credit"}]},
                    "sources": {"calendar": calendar, "benchmark": {key: value for key, value in benchmark.items() if key != "rows"},
                        "leverage": {key: funding["leverage"].get(key) for key in ("status", "fetchStatus", "usingSaved", "sourceNote", "asOf")},
                        "sectors": sectors["coverage"], "liquidity": liquidity["feeds"]},
                    "notes": ["权益参照为沪深300价格指数；配置为3只宽基ETF观察池，不能代表全市场。",
                        "权益关系严格对齐同一股票交易日窗口；融资缺任一交易所或ETF缺任一成员时不确认关系。",
                        "资金价格按货币市场观测日，行业按最新单日，信用按月；不同频率不混入日频关系判断。",
                        "配置、杠杆、资金成本是不同经济含义，金额不混加，不输出恐惧贪婪分数或涨跌概率。",
                        "用于当前观察，月度发布时间/历史修订版本未齐备，不能作为无前视回测或账户风控结论。"]}
        finally:
            if owns:
                await client.aclose()
