"""Market structure reuses the capital daily sample; it is not a market timing score."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from .research import CapitalResearchService
from .service import finite_number
from .turnover import TurnoverResearchService


INDEXES = (("000300.SH", "沪深300"), ("000905.SH", "中证500"), ("000852.SH", "中证1000"),
           ("000918.CSI", "300成长"), ("000919.CSI", "300价值"))


def index_analysis(code: str, name: str, feed: dict, sessions: list[str], calendar_ok: bool) -> dict:
    indexed = {row["date"]: row for row in feed["rows"] if row.get("ts_code") == code}
    windows = {}
    for days in (1, 5, 20):
        dates = sessions[-days - 1:]
        prices = [finite_number(indexed.get(day, {}).get("close")) for day in dates]
        missing = [day for day, price in zip(dates, prices) if price is None or price <= 0]
        complete = len(dates) == days + 1 and not missing
        current = bool(complete and calendar_ok and feed["status"] == "ready" and not feed.get("usingSaved"))
        windows[str(days)] = {"days": days, "baseDate": dates[0] if complete else None,
            "end": dates[-1] if dates else None, "returnPct": (prices[-1] / prices[0] - 1) * 100 if complete else None,
            "current": current, "missingDates": missing,
            "reason": "" if current else feed.get("reason") or "窗口缺数、交易日历或本次更新未确认"}
    return {"code": code, "name": name, "asOf": max(indexed, default=None), "windows": windows,
            "source": "Tushare index_daily · 价格指数，不含分红再投资"}


def build_structure(turnover: dict, indices: list[dict], sessions: list[str]) -> dict:
    breadth = dict(turnover.get("breadth") or {})
    breadth["current"] = bool(turnover["current"] and breadth.get("validCount") and not breadth.get("missingPctCount"))
    by_code = {row["code"]: row for row in indices}
    styles = []
    for label, a, b in (("中证1000 − 沪深300", "000852.SH", "000300.SH"),
                        ("300成长 − 300价值", "000918.CSI", "000919.CSI")):
        windows = {}
        for days in ("1", "5", "20"):
            left, right = by_code[a]["windows"][days], by_code[b]["windows"][days]
            current = left["current"] and right["current"] and left["baseDate"] == right["baseDate"] and left["end"] == right["end"]
            windows[days] = {"current": current, "spreadPp": left["returnPct"] - right["returnPct"] if current else None,
                             "baseDate": left["baseDate"], "end": left["end"]}
        styles.append({"label": label, "windows": windows})
    benchmark = by_code["000300.SH"]["windows"]["1"]
    aligned = breadth["current"] and benchmark["current"] and turnover.get("asOf") == benchmark["end"]
    relationship = "日期或数据未齐，暂不判断指数与样本参与度"
    if aligned:
        p, ratio = benchmark["returnPct"], breadth["upRatioPct"]
        relationship = ("沪深300上涨，但样本上涨不足一半" if p > 0 and ratio < 50 else
                        "沪深300下跌，但样本上涨超过一半" if p < 0 and ratio > 50 else
                        "沪深300上涨，样本多数上涨" if p > 0 and ratio > 50 else
                        "沪深300下跌，样本多数未上涨" if p < 0 and ratio < 50 else "指数或参与率处于分界，不判同向关系")
    return {"schemaVersion": "newma-desk.market-structure.v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
            "expectedDate": turnover.get("expectedDate"), "asOf": turnover.get("asOf"), "breadth": breadth,
            "turnover": {key: turnover.get(key) for key in ("current", "asOf", "summary", "coverage", "reason", "usingSaved", "source")},
            "indices": indices, "styles": styles, "relationship": {"current": bool(aligned), "text": relationship},
            "current": bool(aligned and all(w["current"] for row in indices for w in row["windows"].values())),
            "calendar": {"dates": sessions[-21:], "status": turnover.get("calendarStatus")},
            "notes": ["昨日及以前最近交易日；不是盘中行情。样本不等于交易所全市场，缺数不补零。",
                "涨跌分布为单日；不能据此声称广度连续改善或恶化。指数与样本覆盖不同，背离仅作复核线索。",
                "风格差为两个价格指数区间涨幅之差，单位百分点；不是可交易组合收益或因果归因。",
                "成交集中度复用资金模块同日完整分页样本，成交额不是资金净流入。不生成市场评分或仓位指令。"]}


class MarketStructureService(CapitalResearchService):
    async def research(self, *, refresh=False):
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            turnover, calendar, *feeds = await asyncio.gather(
                TurnoverResearchService(self.token, self.store, client=client, today=self.today).research(refresh=refresh),
                self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
                *(self._dataset(client, "index_daily", code, {"ts_code": code}, "ts_code,trade_date,close,pct_chg",
                                refresh=refresh, cache_key="appetite.index.v1") for code, _ in INDEXES))
            sessions = sorted(row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1")
            calendar_ok = calendar["status"] == "ready" and not calendar.get("usingSaved")
            indices = [index_analysis(code, name, feed, sessions, calendar_ok) for (code, name), feed in zip(INDEXES, feeds)]
            return build_structure(turnover, indices, sessions)
        finally:
            if owns:
                await client.aclose()
