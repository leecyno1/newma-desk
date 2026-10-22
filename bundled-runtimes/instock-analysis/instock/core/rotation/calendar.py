"""One independent session axis for rotation research and execution diagnostics."""

import pandas as pd

from instock.core.market_data_provider import MarketDataError


def align_benchmark_calendar(provider, benchmark_frame, trade_frames, as_of, *, limit, minimum_sessions):
    frames = [benchmark_frame, *trade_frames.values()]
    start = min(pd.to_datetime(frame["date"]).min() for frame in frames).strftime("%Y-%m-%d")
    end = as_of or max(pd.to_datetime(frame["date"]).max() for frame in frames).strftime("%Y-%m-%d")
    calendar = provider.get_trading_calendar(start, end)
    if (calendar.get("status") != "ready" or calendar.get("start") != start
            or calendar.get("end") != end or calendar.get("exchange") != "SSE"):
        raise MarketDataError("独立交易日历未完整覆盖轮动分析区间")
    sessions = pd.DatetimeIndex(pd.to_datetime(calendar["sessions"]))
    if (sessions.hasnans or not sessions.is_unique or not sessions.is_monotonic_increasing
            or any(day < pd.Timestamp(start) or day > pd.Timestamp(end) for day in sessions)):
        raise MarketDataError("独立交易日历日期无效")
    sessions = sessions[-limit:]
    if len(sessions) < minimum_sessions:
        raise MarketDataError(f"独立交易日历不足{minimum_sessions}个交易日")
    source = benchmark_frame.copy()
    source["date"] = pd.to_datetime(source["date"])
    source = source.sort_values("date").drop_duplicates("date", keep="last")
    aligned = source.set_index("date").reindex(sessions).rename_axis("date").reset_index()
    aligned.attrs.update(benchmark_frame.attrs)
    audit = {key: calendar.get(key) for key in ("source", "exchange", "start", "end", "receivedAt", "coverage")}
    audit.update(session_start=sessions[0].strftime("%Y-%m-%d"),
                 session_end=sessions[-1].strftime("%Y-%m-%d"), session_count=len(sessions),
                 missing_benchmark_dates=[day.strftime("%Y-%m-%d") for day in sessions.difference(source["date"])],
                 window_policy=f"last_{limit}_exchange_sessions_within_loaded_history")
    return aligned, audit
