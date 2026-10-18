"""On-demand candidate diagnostics, not a fill simulation or strategy backtest."""
import asyncio
from datetime import datetime, timezone

import httpx

from .etf_price import price_windows
from .research import CapitalResearchService
from .service import finite_number
from .market_structure import INDEXES


def performance_windows(prices, factors, benchmark, sessions, signal_date):
    start = sessions.index(signal_date)
    prices_by_day = {row["date"]: row for row in prices}
    benchmarks = {row["date"]: finite_number(row.get("close")) for row in benchmark}
    result = []
    for days in (1, 3, 5):
        dates = sessions[start:start + days + 1]
        row = {"days": days, "baseDate": signal_date, "end": None, "status": "pending",
               "rawReturnPct": None, "adjustedReturnPct": None, "benchmarkReturnPct": None,
               "excessPp": None, "nextOpenReturnPct": None, "entryDate": dates[1] if len(dates) > 1 else None,
               "execution": "unverified", "executionNote": "尚未完成观察期", "reason": "观察期尚未走完",
               "missingDates": [], "factorChangeDates": []}
        if len(dates) < days + 1:
            result.append(row)
            continue
        window = price_windows(prices, factors, dates, periods=(days,))[str(days)]
        row.update({key: window[key] for key in ("rawReturnPct", "adjustedReturnPct", "missingDates", "factorChangeDates")})
        row.update(end=dates[-1], status="ready" if window["current"] else "review" if window["factorChangeDates"] and not window["missingDates"] else "missing",
                   reason=window["reason"])
        if row["status"] == "review":
            row["reason"] = "复权因子发生变化，结果仅供参考，需核验公司行动"
        values = [benchmarks.get(day) for day in dates]
        if all(value is not None and value > 0 for value in values):
            row["benchmarkReturnPct"] = (values[-1] / values[0] - 1) * 100
            if window["adjustedReturnPct"] is not None:
                row["excessPp"] = row["adjustedReturnPct"] - row["benchmarkReturnPct"]
        else:
            row["reason"] = "；".join(filter(None, [row["reason"], "同期基准缺失，不计算超额变化"]))
        entry, exit_quote = [{key: finite_number(prices_by_day.get(day, {}).get(key)) for key in ("open", "high", "low", "close")}
                             for day in (dates[1], dates[-1])]
        opening = finite_number(entry.get("open"))
        quotes = [entry, exit_quote]
        valid_ohlc = all(all((finite_number(q.get(key)) or 0) > 0 for key in ("open", "high", "low", "close"))
                         and q["low"] <= min(q["open"], q["close"]) <= max(q["open"], q["close"]) <= q["high"] for q in quotes)
        if days == 1:
            row.update(execution="t-plus-one", executionNote="A股T+1：次日开盘买入不能当天卖出，不提供同日交易参考收益")
        elif window["adjustedReturnPct"] is None or not valid_ohlc:
            row.update(execution="blocked", executionNote="价格、成交或复权待核验，不给出开盘参考表现")
        elif any(q["high"] == q["low"] for q in quotes):
            row.update(execution="blocked", executionNote="入场或退出日为单一成交价，成交能力未确认，暂停开盘参考")
        else:
            factor_map = {point["date"]: point["factor"] for point in window["points"]}
            row.update(nextOpenReturnPct=(exit_quote["close"] * factor_map[dates[-1]] / (opening * factor_map[dates[1]]) - 1) * 100,
                       execution="indicative", executionNote="次日开盘至期末收盘参考；未核验涨跌停、竞价排队及成交容量，不代表可成交")
        result.append(row)
    return result


class CandidatePerformanceService(CapitalResearchService):
    async def research(self, code, signal_date, *, benchmark_code="000300.SH", refresh=False):
        benchmarks = dict(INDEXES)
        if benchmark_code not in benchmarks:
            raise ValueError("不支持该基准，请从可选市场／风格指数中选择")
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar = await self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"},
                                           "cal_date,is_open", "cal_date", refresh=refresh)
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
            if signal_date not in sessions[-6:]:
                raise ValueError("信号日不在最近6个可核验交易日内")
            # Separate cache identity: ordinary security daily caches need not contain open/high/low.
            prices, factors, benchmark = await asyncio.gather(
                self._dataset(client, "daily", code, {"ts_code": code}, "ts_code,trade_date,open,high,low,close,vol",
                              refresh=refresh, replace_window=True, cache_key="capital.candidate-price.v1"),
                self._dataset(client, "adj_factor", code, {"ts_code": code}, "ts_code,trade_date,adj_factor",
                              refresh=refresh, replace_window=True),
                self._dataset(client, "index_daily", benchmark_code, {"ts_code": benchmark_code}, "ts_code,trade_date,close",
                              refresh=refresh, replace_window=True),
            )
            feeds = {name: {"status": feed["status"], "reason": feed["reason"], "usingSaved": feed.get("usingSaved", False), "receivedAt": feed["receivedAt"]}
                     for name, feed in (("calendar", calendar), ("price", prices), ("adjustment", factors), ("benchmark", benchmark))}
            valid = lambda feed: feed["status"] == "ready" and not feed.get("usingSaved")
            windows = performance_windows(prices["rows"] if valid(prices) else [], factors["rows"] if valid(factors) else [],
                                          [row for row in benchmark["rows"] if row.get("ts_code") == benchmark_code] if valid(benchmark) else [], sessions, signal_date)
            if not valid(calendar):
                windows = []
            return {"code": code, "signalDate": signal_date, "asOf": sessions[-1], "windows": windows, "feeds": feeds,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "reason": "" if valid(calendar) else "交易日历未确认，停止表现核验",
                    "benchmark": {"code": benchmark_code, "name": benchmarks[benchmark_code], "note": "用户选择的市场／风格参照，不代表已核验成分或行业匹配；价格指数，非全收益指数"},
                    "benchmarkOptions": [{"code": key, "name": name} for key, name in INDEXES],
                    "source": "Tushare daily / adj_factor / index_daily / trade_cal",
                    "method": "复权参考涨跌=(期末close×adj_factor)/(信号日close×adj_factor)-1。超额变化=复权参考涨跌−同期所选价格指数涨跌（百分点），不是风险调整alpha。不得根据事后表现挑选更有利的基准，比较结论须保留基准代码和区间。信号日收盘仅为观察起点，不假设可在该时点买入。次日开盘参考另列；A股T+1禁止买入当日卖出，后1日不提供交易参考。历史重算或晚于入场时间的首次记录，不证明信号提前可用。均未扣税费滑点，不是策略收益。因子变动需核验公司行动；任一交易日缺数据不填充、不跳过。"}
        finally:
            if self.client is None:
                await client.aclose()
