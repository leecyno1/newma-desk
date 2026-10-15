from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx

from vibe_visualization_api.capital_flow.service import CapitalFlowService
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATASET = "capital.hkex-daily.v1"


def connect_point(snapshot: dict, day: str, direction: str) -> dict:
    keys = [f"{exchange}-{direction}" for exchange in ("sse", "szse")]
    flags = [snapshot.get(key, {}).get("tradingDay") for key in keys]
    base = {"date": day, "status": "unavailable", "turnoverYi": None, "buyYi": None, "sellYi": None, "netBuyYi": None,
            "etfTurnoverYi": None, "sseTurnoverYi": None, "szseTurnoverYi": None, "reason": "缺少同日两路官方数据"}
    if snapshot.get("date") != day:
        return base
    if flags == [0, 0]:
        return {**base, "status": "closed", "reason": "HKEX 官方标记休市，不填零"}
    if flags != [1, 1]:
        return base
    components = [CapitalFlowService._connect_summary(snapshot, key) for key in keys]
    required = ["turnoverYi"] + (["buyYi", "sellYi"] if direction == "southbound" else [])
    if any(row.get(key) is None or row[key] < 0 for row in components for key in required):
        return base
    if direction == "southbound" and any(abs(row["buyYi"] + row["sellYi"] - row["turnoverYi"]) > .001 for row in components):
        return {**base, "reason": "买入加卖出与总成交额不一致，待核验"}
    def total(key):
        values = [row.get(key) for row in components]
        return round(sum(values), 4) if all(value is not None and value >= 0 for value in values) else None
    return {**base, "status": "ready", "reason": "", "turnoverYi": total("turnoverYi"),
            "etfTurnoverYi": total("etfTurnoverYi"), "sseTurnoverYi": components[0]["turnoverYi"], "szseTurnoverYi": components[1]["turnoverYi"],
            "buyYi": total("buyYi") if direction == "southbound" else None,
            "sellYi": total("sellYi") if direction == "southbound" else None,
            "netBuyYi": round(total("buyYi") - total("sellYi"), 4) if direction == "southbound" else None}


def connect_momentum(active: list[dict], direction: str) -> dict:
    """Compare equal, non-overlapping channel-session windows, never net-flow growth rates."""
    south = direction == "southbound"
    def period(points):
        complete = len(points) == 5 and all(row["status"] == "ready" for row in points)
        turnover = round(sum(row["turnoverYi"] for row in points), 4) if complete else None
        net = round(sum(row["netBuyYi"] for row in points), 4) if complete and south else None
        return {"start": points[0]["date"] if points else None, "end": points[-1]["date"] if points else None,
                "available": sum(row["status"] == "ready" for row in points), "current": complete,
                "turnoverYi": turnover, "netBuyYi": net,
                "netIntensityPct": net / turnover * 100 if net is not None and turnover else None}
    recent, previous = period(active[-5:]), period(active[-10:-5])
    complete = recent["current"] and previous["current"]
    intensity = [part["netIntensityPct"] for part in (recent, previous)]
    return {"days": 5, "current": complete, "recent": recent, "previous": previous,
            "missingDates": [row["date"] for row in active[-10:] if row["status"] != "ready"],
            "netChangeYi": round(recent["netBuyYi"] - previous["netBuyYi"], 4) if complete and south else None,
            "intensityChangePp": intensity[0] - intensity[1] if complete and all(value is not None for value in intensity) else None,
            "turnoverRatio": recent["turnoverYi"] / previous["turnoverYi"] if complete and previous["turnoverYi"] else None}


def connect_window(rows: list[dict], candidates: list[str], direction: str, days: int) -> dict:
    index = {row["date"]: row.get(direction, {}) for row in rows}
    ordered = [{"date": day, "status": "unavailable", **index.get(day, {})} for day in candidates]
    # Unknown weekdays are retained; only an official closed flag can remove a day.
    active = [row for row in ordered if row["status"] != "closed"]
    points = active[-days:]
    complete = len(points) == days and all(row["status"] == "ready" for row in points)
    latest = points[-1] if points else {}
    def total(key):
        values = [row.get(key) for row in points]
        return round(sum(values), 4) if complete and all(value is not None for value in values) else None
    baseline = active[-21:-1]
    baseline_ok = len(baseline) == 20 and all(row["status"] == "ready" for row in baseline) and latest.get("status") == "ready"
    mean = sum(row["turnoverYi"] for row in baseline) / 20 if baseline_ok else None
    streak = 0
    sign = None
    if complete and direction == "southbound":
        for row in reversed(points):
            current_sign = 1 if row["netBuyYi"] > 0 else -1 if row["netBuyYi"] < 0 else 0
            if current_sign == 0 or (sign is not None and current_sign != sign): break
            sign = current_sign; streak += 1
    return {"direction": direction, "days": days, "currency": "HKD" if direction == "southbound" else "CNY",
            "unit": "港元亿元" if direction == "southbound" else "人民币亿元", "current": complete,
            "asOf": latest.get("date"), "start": points[0]["date"] if points else None,
            "available": sum(row["status"] == "ready" for row in points),
            "closedDays": [row["date"] for row in ordered if row["status"] == "closed"],
            "missingDates": [row["date"] for row in points if row["status"] != "ready"], "points": points,
            "momentum": connect_momentum(active, direction),
            "summary": {"turnoverYi": total("turnoverYi"), "buyYi": total("buyYi"), "sellYi": total("sellYi"),
                        "netBuyYi": total("netBuyYi"),
                        "positiveDays": sum(row["netBuyYi"] > 0 for row in points) if complete and direction == "southbound" else None,
                        "streakDays": streak if complete and direction == "southbound" else None,
                        "streakDirection": "unavailable" if direction == "northbound" else "buy" if sign == 1 else "sell" if sign == -1 else "flat" if complete else "unknown",
                        "streakCensored": bool(streak and streak == days),
                        "prior20MeanTurnoverYi": mean,
                        "latestVsPrior20": latest["turnoverYi"] / mean if mean and mean > 0 else None}}


class ConnectResearchService:
    def __init__(self, store: CapitalHistoryStore, *, client=None, today: date | None = None):
        self.store, self.client = store, client
        self.today = today or datetime.now(timezone(timedelta(hours=8))).date()

    async def research(self, *, refresh=False):
        end = self.today - timedelta(days=1)
        start = end - timedelta(days=44)
        candidates = [(start + timedelta(days=i)).isoformat() for i in range(45) if (start + timedelta(days=i)).weekday() < 5]
        saved, _ = await asyncio.to_thread(self.store.read, DATASET, "CONNECT", start.isoformat(), end.isoformat())
        index = {row["date"]: row for row in saved}
        now = datetime.now(timezone.utc)
        valid = lambda row: all(row.get(side, {}).get("status") in {"ready", "closed"} for side in ("northbound", "southbound"))
        pending = [day for day in reversed(candidates) if not valid(index.get(day, {}))]
        latest = index.get(candidates[-1], {})
        expired = not latest.get("receivedAt") or (now - datetime.fromisoformat(latest["receivedAt"])).total_seconds() >= 300
        if (refresh or expired) and candidates[-1] not in pending: pending.insert(0, candidates[-1])
        targets = pending[:6]
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=12, trust_env=False)
        source = CapitalFlowService("", client=client)
        gate = asyncio.Semaphore(3)
        async def fetch_day(day):
            async with gate:
                try:
                    snapshot = await source._fetch_hkex_connect(client, day, exact=True)
                except (httpx.HTTPError, ValueError):
                    snapshot = {}
                point = {"date": day, "receivedAt": now.isoformat(),
                         "url": f"https://www.hkex.com.hk/chi/csm/DailyStat/data_tab_daily_{day.replace('-', '')}c.js"}
                for direction in ("northbound", "southbound"):
                    point[direction] = connect_point(snapshot, day, direction)
                    old = index.get(day, {}).get(direction, {})
                    if point[direction]["status"] == "unavailable" and old:
                        point[direction] = {**old, "status": "unavailable", "usingSaved": True, "reason": point[direction]["reason"]}
                return point
        try:
            fetched = await asyncio.gather(*(fetch_day(day) for day in targets))
        finally:
            if owns: await client.aclose()
        if fetched:
            await asyncio.to_thread(self.store.save, DATASET, "CONNECT", fetched, start=start.isoformat(), end=end.isoformat(),
                                    status="ready" if all(valid(row) for row in fetched) else "partial", reason="", received_at=now.isoformat())
            index.update({row["date"]: row for row in fetched})
        failed = [row["date"] for row in fetched if not valid(row)]
        remaining = sum(not valid(index.get(day, {})) for day in candidates)
        return {"schemaVersion": "newma-desk.connect-research.v1", "generatedAt": now.isoformat(),
                "cutoff": end.isoformat(), "source": "HKEX 官方逐日统计", "completed": len(candidates) - remaining,
                "expected": len(candidates), "remaining": remaining, "failedDates": failed,
                "canContinue": bool(targets and not failed and remaining),
                "windows": {str(days): {side: connect_window(list(index.values()), candidates, side, days)
                            for side in ("northbound", "southbound")} for days in (5, 20)},
                "notes": ["历史截止昨日；单日快照可能更新到今日，两者日期分别显示。",
                          "仅官方标记休市才跳过；未知日期保留为缺口，不补零。所有展示历史逐日直接读取港交所，不以最新日核验代表整段核验。",
                          "北向仅研究成交活跃度，不推算净流入；南向买入减卖出按港元统计，不与人民币相加。",
                          "连续方向仅在所选窗口内统计，达到窗口上限时至少连续这么多天；不代表未来持续流入。",
                          "历史复用本地快照，刷新仅重新读取最新候选日和缺口，不追溯历史修订。"]}
