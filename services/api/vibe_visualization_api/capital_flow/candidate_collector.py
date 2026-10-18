"""Scheduled close-only observations; missing past signals are never backdated."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .store import CapitalHistoryStore
from .turnover_candidates import DATASET, RULE, scan
from .turnover_history import DATASET as HISTORY, TurnoverHistoryService

RUNS = "capital.candidate-collection.v1"
CRON = "0,30 16-20 * * *"
ZONE = timezone(timedelta(hours=8))


class CandidateCollector:
    def __init__(self, token, store: CapitalHistoryStore):
        self.token, self.store = token, store

    async def collect(self, now=None):
        instant = now or datetime.now(timezone.utc)
        local = instant.astimezone(ZONE)
        day = local.date().isoformat()

        async def record(status, reason, **values):
            checked = now or datetime.now(timezone.utc)
            result = {"date": day, "checkedAt": checked.isoformat(), "status": status, "reason": reason, **values}
            await asyncio.to_thread(self.store.save, RUNS, RULE["id"], [result], start=day, end=day,
                                    status=status, reason=reason, received_at=checked.isoformat())
            return result

        if not 16 <= local.hour < 21:
            return await record("outside-window", "不在北京时间16:00–21:00收盘采集窗口；不回填错过的信号")
        if not self.token:
            await record("unavailable", "Tushare未配置，不能确认交易日及当日行情")
            raise ValueError("Tushare未配置")
        try:
            async with httpx.AsyncClient(timeout=18, trust_env=False) as client:
                history_service = TurnoverHistoryService(self.token, self.store, client=client, today=local.date())
                # Only this close-gated task includes today; interactive research retains its prior-day boundary.
                history_service.end = day
                calendar = await history_service._pages(client, "trade_cal", {
                    "exchange": "SSE", "start_date": day.replace("-", ""), "end_date": day.replace("-", ""),
                }, "cal_date,is_open")
                if len(calendar) != 1 or str(calendar[0].get("cal_date")) != day.replace("-", "") or str(calendar[0].get("is_open")) not in {"0", "1"}:
                    raise ValueError("当日交易日历未确认")
                if str(calendar[0]["is_open"]) == "0":
                    return await record("closed", "交易日历确认休市，无需生成信号")
                saved, _ = await asyncio.to_thread(self.store.read, DATASET, RULE["id"], day, day)
                if saved:
                    return await record("recorded", "首次观察已存在，保留原始记录", signalDate=day, capturedAt=saved[0]["capturedAt"])
                history = await history_service.history(25, refresh=True)
                sessions = [row["date"] for row in history["points"]]
                if not sessions or sessions[-1] != day:
                    raise ValueError("当日交易窗口未确认")
                observations, _ = await asyncio.to_thread(self.store.read, HISTORY, "CN", history_service.start, day)
                current = await asyncio.to_thread(scan, observations, sessions, day,
                                                  history["calendarStatus"] == "ready" and not history["reason"])
                if not current["current"]:
                    return await record("waiting-data", current["reason"], signalDate=day, missingDates=current["missingDates"])
                captured_at = now or datetime.now(timezone.utc)
                completed_local = captured_at.astimezone(ZONE)
                if completed_local.date() != local.date() or not 16 <= completed_local.hour < 21:
                    raise ValueError("采集完成时已越过收盘采集窗口，不补写记录")
                frozen = await asyncio.to_thread(self.store.save_once, DATASET, RULE["id"],
                                                {**current, "capturedAt": captured_at.isoformat(), "captureSource": "scheduled-close"})
                return await record("recorded", "首次观察已归档，名单与对照范围已冻结", signalDate=day, capturedAt=frozen["capturedAt"])
        except (httpx.HTTPError, ValueError) as error:
            # Never persist provider responses or credentials in scheduler/Agent status.
            message = str(error) if isinstance(error, ValueError) and str(error) in {
                "当日交易日历未确认", "当日交易窗口未确认", "采集完成时已越过收盘采集窗口，不补写记录",
            } else "当日行情或20日基线未齐，或上游请求失败；下次计划重试"
            await record("failed", message, signalDate=day)
            raise ValueError(message) from None


def collection_status(store, scheduler_store, *, enabled, token_ready, now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(ZONE)
    today = local.date()
    end, start = today.isoformat(), (today - timedelta(days=60)).isoformat()
    runs, _ = store.read(RUNS, RULE["id"], start, end)
    saved, _ = store.read(DATASET, RULE["id"], start, end)
    calendar, _ = store.read("trade_cal", "SSE", start, end)
    latest_closed = sorted(row["date"] for row in calendar if str(row.get("is_open")) == "1" and (row["date"] < end or local.hour >= 21))[-20:]
    recorded = {row["date"] for row in saved}
    try:
        job = scheduler_store.get("capital-overview").model_dump(mode="json")
    except KeyError:
        job = None
    return {"enabled": enabled, "tokenReady": token_ready, "schedule": "北京时间每日16:00–20:30，每30分钟检查；休市由交易日历确认",
            "job": job, "lastCheck": runs[-1] if runs else None,
            "missingDates": [day for day in latest_closed if day not in recorded], "knownSessionCount": len(latest_closed),
            "note": "检查成功不等于新信号入库；以首次归档为准。未归档日期仅来自已缓存的最近20个往日交易日，可能早于任务启用，非完整漏采审计。Desk后端停机或电脑休眠期间不会运行，恢复后不补写过去信号。"}
