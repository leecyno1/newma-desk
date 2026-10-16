from datetime import datetime, timezone
import asyncio

import httpx

from .research import CapitalResearchService
from .service import finite_number


def price_windows(prices, factors, sessions):
    prices = {row["date"]: row for row in prices}
    factors = {row["date"]: row for row in factors}
    def positive(value):
        value = finite_number(value)
        return value if value is not None and value > 0 else None
    windows = {}
    for days in (1, 5, 20):
        base_date = sessions[-days - 1] if len(sessions) > days else None
        dates = sessions[-days:]
        checked = ([base_date] if base_date else []) + dates
        points = [{"date": day, "close": positive(prices.get(day, {}).get("close")),
                   "factor": positive(factors.get(day, {}).get("adj_factor")),
                   "volume": positive(prices.get(day, {}).get("vol"))} for day in checked]
        missing = [row["date"] for row in points if row["close"] is None or row["factor"] is None or row["volume"] is None]
        changes = [row["date"] for previous, row in zip(points, points[1:])
                   if row["factor"] is not None and previous["factor"] is not None and abs(row["factor"] / previous["factor"] - 1) > 1e-8]
        complete = base_date is not None and len(dates) == days and not missing
        first, last = (points[0], points[-1]) if points else ({}, {})
        raw = (last["close"] / first["close"] - 1) * 100 if complete else None
        adjusted = (last["close"] * last["factor"] / (first["close"] * first["factor"]) - 1) * 100 if complete else None
        reason = "交易日不足，无法建立价格窗口" if base_date is None else (
            "价格、复权因子或有效成交缺失；不填充停牌日" if missing else
            "窗口复权因子变化，分红／折算尚需核验，暂停背离判断" if changes else "")
        windows[str(days)] = {"days": days, "baseDate": base_date, "start": dates[0] if dates else None,
            "end": dates[-1] if dates else None, "baseClose": first.get("close"), "endClose": last.get("close"),
            "baseFactor": first.get("factor"), "endFactor": last.get("factor"),
            "rawReturnPct": round(raw, 6) if raw is not None else None,
            "adjustedReturnPct": round(adjusted, 6) if adjusted is not None else None,
            "missingDates": missing, "factorChangeDates": changes, "current": complete and not changes,
            "reason": reason, "points": points}
    return windows


class ETFPriceService(CapitalResearchService):
    async def price(self, code, *, refresh=False):
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar, prices, factors = await asyncio.gather(
                self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
                self._dataset(client, "fund_daily", code, {"ts_code": code}, "ts_code,trade_date,close,vol", refresh=refresh, replace_window=True),
                self._dataset(client, "fund_adj", code, {"ts_code": code}, "ts_code,trade_date,adj_factor", refresh=refresh, replace_window=True),
            )
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
            windows = price_windows(prices["rows"], factors["rows"], sessions)
            feeds = {name: {"status": feed["status"], "reason": feed["reason"], "usingSaved": feed.get("usingSaved", False), "receivedAt": feed["receivedAt"]}
                     for name, feed in (("calendar", calendar), ("price", prices), ("adjustment", factors))}
            if any(feed["status"] != "ready" or feed["usingSaved"] for feed in feeds.values()):
                for window in windows.values():
                    window["current"] = False
                    window["reason"] = "；".join(filter(None, [window["reason"], "价格、复权因子或日历更新未确认，保留历史但暂停判断"]))
            return {"code": code, "generatedAt": datetime.now(timezone.utc).isoformat(), "windows": windows, "feeds": feeds,
                    "source": "Tushare fund_daily + fund_adj", "currency": "CNY",
                    "method": "复权参考涨跌=(期末收盘价×期末因子)/(期初收盘价×期初因子)-1；不是净值回报或实盘收益。因子变化窗口暂停背离判断。"}
        finally:
            if self.client is None:
                await client.aclose()
