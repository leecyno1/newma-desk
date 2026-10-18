from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from vibe_visualization_api.capital_flow.turnover import TurnoverResearchService, turnover_snapshot
from vibe_visualization_api.capital_flow.service import finite_number
from vibe_visualization_api.capital_flow.sentiment import breadth_history


DATASET = "capital.turnover-history.v1"


def history_analysis(observations: list[dict], sessions: list[str], days: int, calendar_ready: bool) -> dict:
    sessions = sessions[-(days + 1):]
    indexed = {row["date"]: row for row in observations}
    good = {day: indexed[day] for day in sessions if indexed.get(day, {}).get("status") == "ready"}
    complete = calendar_ready and len(sessions) == days + 1 and len(good) == len(sessions)
    common = set.intersection(*(set(row["amounts"]) for row in good.values())) if complete else set()
    comparable = complete and len(common) >= 20
    points = []
    for day in sessions:
        row = indexed.get(day, {})
        values = sorted((row["amounts"][code] for code in common), reverse=True) if comparable else []
        total = sum(values) / 100_000 if comparable else None  # raw daily.amount is thousand yuan
        points.append({"date": day, "status": row.get("status", "pending"), "reason": row.get("reason", ""),
                       "sampleCount": len(row.get("amounts", {})), "turnoverYi": total,
                       "top20SharePct": sum(values[:20]) / sum(values) * 100 if values and sum(values) > 0 else None})
    summary = {key: None for key in ("latestTurnoverYi", "meanTurnoverYi", "relativeVolume", "percentilePct", "top20SharePct", "meanTop20SharePct", "concentrationChangePp")}
    if comparable:
        latest, prior = points[-1], points[:-1]
        average = sum(row["turnoverYi"] for row in prior) / days
        concentrations = [row["top20SharePct"] for row in prior]
        mean_share = sum(concentrations) / days if all(value is not None for value in concentrations) else None
        summary.update(latestTurnoverYi=latest["turnoverYi"], meanTurnoverYi=average,
                       relativeVolume=latest["turnoverYi"] / average if average > 0 else None,
                       percentilePct=sum(row["turnoverYi"] <= latest["turnoverYi"] for row in prior) / days * 100,
                       top20SharePct=latest["top20SharePct"], meanTop20SharePct=mean_share,
                       concentrationChangePp=latest["top20SharePct"] - mean_share if latest["top20SharePct"] is not None and mean_share is not None else None)
    latest_count = points[-1]["sampleCount"] if points else 0
    return {"days": days, "asOf": sessions[-1] if sessions else None, "start": sessions[0] if sessions else None,
            "current": comparable, "completed": len(good), "expected": days + 1,
            "remaining": len(sessions) - len(good), "commonCount": len(common), "latestSampleCount": latest_count,
            "excludedLatest": latest_count - len(common) if complete else None,
            "summary": summary, "points": points,
            "note": "基线不含最新日；窗口内共同有行情的股票固定为比较池，前20每天重排。剔除新股、停牌和缺数标的可能产生选择偏差，不能代表全市场。分位为历史值不高于最新值的比例，非预测概率。历史使用已保存快照，刷新只更新最新日及缺口，不追溯历史修订。"}


class TurnoverHistoryService(TurnoverResearchService):
    batch_size = 8

    async def history(self, days: int = 20, *, refresh: bool = False, include_breadth: bool = False) -> dict:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar = await self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"},
                                           "cal_date,is_open", "cal_date", refresh=refresh)
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})[-(days if include_breadth else days + 1):]
            calendar_ready = calendar["status"] == "ready" and not calendar.get("usingSaved")
            rows, _ = await asyncio.to_thread(self.store.read, DATASET, "CN", self.start, self.end)
            indexed = {row["date"]: row for row in rows}
            now = datetime.now(timezone.utc)
            def ready(row):
                return row.get("status") == "ready" and (not include_breadth or row.get("breadthStatus") == "ready")
            pending = [day for day in reversed(sessions) if not ready(indexed.get(day, {}))]
            if sessions:
                latest = indexed.get(sessions[-1], {})
                expired = not latest.get("receivedAt") or (now - datetime.fromisoformat(latest["receivedAt"])).total_seconds() >= 300
                if (refresh or expired) and sessions[-1] not in pending:
                    pending.insert(0, sessions[-1])
            targets = pending[:self.batch_size] if self.token and calendar_ready else []
            gate = asyncio.Semaphore(3)

            async def fetch_day(day):
                async with gate:
                    try:
                        quotes = await asyncio.wait_for(self._pages(client, "daily", {"trade_date": day.replace("-", "")}, "ts_code,trade_date,amount,close,pct_chg"), timeout=20)
                        snapshot = turnover_snapshot(quotes, [], day)
                        if not snapshot["coverage"]["valid"]:
                            raise ValueError("日线为空或含日期、金额、重复冲突缺口")
                        returns = {row["ts_code"]: finite_number(row.get("pct_chg")) for row in quotes
                                   if float(row["amount"]) > 0 and (finite_number(row.get("close")) or 0) > 0
                                   and finite_number(row.get("pct_chg")) is not None}
                        return {"date": day, "status": "ready", "reason": "", "receivedAt": now.isoformat(),
                                "returns": returns, "breadthStatus": "ready" if returns else "unavailable",
                                "amounts": {row["ts_code"]: float(row["amount"]) for row in quotes}}
                    except (httpx.HTTPError, ValueError, TimeoutError):
                        return {**indexed.get(day, {}), "date": day, "status": "unavailable", "receivedAt": now.isoformat(),
                                "reason": "当日分页或数据校验失败；保留值不参与基线计算"}

            fetched = await asyncio.gather(*(fetch_day(day) for day in targets))
            if fetched:
                await asyncio.to_thread(self.store.save, DATASET, "CN", fetched, start=sessions[0], end=sessions[-1],
                                        status="ready" if all(row["status"] == "ready" for row in fetched) else "partial",
                                        reason="", received_at=now.isoformat())
                indexed.update({row["date"]: row for row in fetched})
            result = (breadth_history if include_breadth else history_analysis)(list(indexed.values()), sessions, days, calendar_ready and bool(self.token))
            failures = [row["date"] for row in fetched if not ready(row)]
            return {**result, "schemaVersion": "newma-desk.sentiment-history.v1" if include_breadth else "newma-desk.turnover-history.v1", "generatedAt": now.isoformat(),
                    "source": "Tushare daily / trade_cal · 未复权日线", "unit": "% / 百分点" if include_breadth else "人民币亿元", "calendarStatus": calendar["status"],
                    "failedDates": failures, "fetchedDays": len(fetched),
                    "canContinue": bool(targets and not failures and result["remaining"] > 0),
                    "reason": result.get("reason", "") if calendar_ready and self.token else "交易日历未确认或 Tushare 未配置"}
        finally:
            if owns:
                await client.aclose()
