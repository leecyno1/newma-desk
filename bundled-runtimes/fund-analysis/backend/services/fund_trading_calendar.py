"""基金日频核验使用的公开交易日历；只读本地已核验快照，不在页面请求时联网。"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "sse_trading_calendar.json"
DOMESTIC_FUND_TYPES = ("债券型", "股票型", "混合型", "指数型", "REITs")
CROSS_MARKET_PATTERN = "QDII|海外|全球|香港|港股|沪港深|恒生|纳斯达克|标普|美股|FOF"


def fund_risk_calendar(fund: Dict[str, Any]) -> Optional[str]:
    text = " ".join(str(fund.get(key) or "") for key in ("type", "name", "fund_type_raw", "invest_type"))
    if fund.get("type") in DOMESTIC_FUND_TYPES and not re.search(CROSS_MARKET_PATTERN, text, re.IGNORECASE):
        return "SSE"
    return None


class TradingCalendar:
    def __init__(self, snapshot: Dict[str, Any]):
        if snapshot.get("source") != "tushare.trade_cal" or snapshot.get("exchange") != "SSE":
            raise ValueError("交易日历来源或市场不匹配")
        self.start = date.fromisoformat(snapshot["start_date"])
        self.end = date.fromisoformat(snapshot["end_date"])
        self.fetched_at = snapshot["fetched_at"]
        self.closed_weekdays = {date.fromisoformat(value) for value in snapshot["closed_weekdays"]}
        self.open_weekends = {date.fromisoformat(value) for value in snapshot["open_weekends"]}
        if self.end < self.start or snapshot.get("encoding") != "verified_weekday_exceptions":
            raise ValueError("交易日历快照格式无效")
        if any(not self.start <= day <= self.end or day.weekday() >= 5 for day in self.closed_weekdays):
            raise ValueError("交易日历休市日期无效")
        if any(not self.start <= day <= self.end or day.weekday() < 5 for day in self.open_weekends):
            raise ValueError("交易日历周末开市日期无效")
        for year in range(self.start.year, self.end.year + 1):
            start, end = date(year, 1, 1), date(year, 12, 31)
            days = self.open_days(start, end)
            if days is None or snapshot["years"][str(year)] != {"calendar_days": (end-start).days+1, "open_days": len(days)}:
                raise ValueError("交易日历完整覆盖校验失败")

    def open_days(self, start: date, end: date) -> Optional[set[date]]:
        if start < self.start or end > self.end or end < start:
            return None
        days = set()
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if (day.weekday() < 5 and day not in self.closed_weekdays) or day in self.open_weekends:
                days.add(day)
        return days


@lru_cache(maxsize=1)
def get_trading_calendar() -> Optional[TradingCalendar]:
    try:
        return TradingCalendar(json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def fetch_calendar_snapshot(pro: Any, start_year: int, end_year: int) -> Dict[str, Any]:
    """逐年校验每个自然日，空/截断/冲突结果不生成快照。"""
    if not 1990 <= start_year <= end_year <= date.today().year:
        raise ValueError("交易日历年份范围无效")
    closed_weekdays, open_weekends = [], []
    counts = {}
    for year in range(start_year, end_year + 1):
        start, end = date(year, 1, 1), date(year, 12, 31)
        frame = pro.trade_cal(exchange="SSE", start_date=start.strftime("%Y%m%d"),
                              end_date=end.strftime("%Y%m%d"), fields="exchange,cal_date,is_open")
        if frame is None or frame.empty:
            raise ValueError(f"{year}年交易日历为空")
        days = {}
        for row in frame.to_dict("records"):
            day = datetime.strptime(str(row["cal_date"]), "%Y%m%d").date()
            if row["exchange"] != "SSE" or not start <= day <= end or row["is_open"] not in (0, 1, "0", "1"):
                raise ValueError(f"{year}年交易日历字段无效")
            is_open = int(row["is_open"])
            if day in days and days[day] != is_open:
                raise ValueError(f"{year}年交易日历同日冲突")
            days[day] = is_open
        expected = {start + timedelta(days=offset) for offset in range((end - start).days + 1)}
        if set(days) != expected:
            raise ValueError(f"{year}年交易日历覆盖不完整")
        counts[str(year)] = {"calendar_days": len(days), "open_days": sum(days.values())}
        closed_weekdays.extend(day.isoformat() for day, opened in sorted(days.items()) if day.weekday() < 5 and not opened)
        open_weekends.extend(day.isoformat() for day, opened in sorted(days.items()) if day.weekday() >= 5 and opened)
    return {"source": "tushare.trade_cal", "exchange": "SSE", "source_url": "https://tushare.pro/document/2?doc_id=26",
            "fetched_at": datetime.now(timezone.utc).isoformat(), "start_date": f"{start_year}-01-01", "end_date": f"{end_year}-12-31",
            "encoding": "verified_weekday_exceptions", "years": counts,
            "closed_weekdays": closed_weekdays, "open_weekends": open_weekends}
