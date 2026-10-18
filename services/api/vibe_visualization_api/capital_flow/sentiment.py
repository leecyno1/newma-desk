"""A dated sentiment view of the existing turnover sample, not a second data pipeline."""

from statistics import median


def breadth_history(observations: list[dict], sessions: list[str], days: int, calendar_ready: bool) -> dict:
    sessions = sorted(set(sessions))[-days:]
    indexed = {row["date"]: row for row in observations}
    good = {day: indexed[day] for day in sessions if indexed.get(day, {}).get("status") == "ready"
            and indexed[day].get("breadthStatus") == "ready" and indexed[day].get("returns")}
    complete = calendar_ready and len(sessions) == days and len(good) == days
    common = set.intersection(*(set(row["returns"]) for row in good.values())) if complete else set()
    comparable = complete and len(common) >= 20
    points = []
    for day in sessions:
        row = indexed.get(day, {})
        values = [row["returns"][code] for code in common] if comparable else []
        points.append({"date": day, "status": "ready" if day in good else "missing",
                       "reason": "" if day in good else row.get("reason") or "有效涨跌幅历史待补齐",
                       "sampleCount": len(row.get("returns", {})) if day in good else None,
                       "excludedCount": len(row["returns"]) - len(common) if comparable else None,
                       "upRatioPct": sum(value > 0 for value in values) / len(values) * 100 if values else None,
                       "medianPct": median(values) if values else None})
    summary = {key: None for key in ("latestUpRatioPct", "latestChangePp", "mean5Pct", "previous5Pct", "change5Pp", "aboveHalfDays")}
    if comparable:
        values = [row["upRatioPct"] for row in points]
        recent, previous = sum(values[-5:]) / 5, sum(values[-10:-5]) / 5
        summary.update(latestUpRatioPct=values[-1], latestChangePp=values[-1] - values[-2],
                       mean5Pct=recent, previous5Pct=previous, change5Pp=recent - previous,
                       aboveHalfDays=sum(value > 50 for value in values))
    missing = [day for day in sessions if day not in good]
    return {"days": days, "asOf": sessions[-1] if sessions else None, "start": sessions[0] if sessions else None,
            "current": comparable, "completed": len(good), "expected": days, "remaining": len(missing),
            "calendarReady": calendar_ready, "missingDates": missing, "commonCount": len(common),
            "summary": summary, "points": points,
            "reason": "" if comparable else "交易日历未确认" if not calendar_ready else
                      "交易日历窗口不足" if len(sessions) < days else "涨跌幅历史存在缺口" if missing else "共同有效样本不足20只",
            "note": "含最新日在内20个交易日，共同有效股票固定为比较池；零成交、无效价格和缺涨跌幅排除。近5日均值与此前5日比较，变化单位为百分点。每日样本数仅说明覆盖，不用于拼接趋势。剔除新股、停牌和缺数标的会产生选择偏差；窗口滚动会改变共同样本，不用于无偏回测。50%为上涨家数过半参考线，不是买卖阈值。历史快照不追溯源端修订。"}


def sentiment_snapshot(turnover: dict) -> dict:
    breadth = turnover.get("breadth") or {}
    usable = (turnover.get("status") in {"ready", "partial"}
              and not turnover.get("usingSaved") and breadth.get("validCount", 0) > 0)
    reason = turnover.get("reason") or ("" if usable else "未取得有效日线样本；不以旧快照或零替代")
    return {
        "sentiment": {
            **{key: breadth.get(key) if usable else None for key in ("up", "down", "flat")},
            "zt": None, "dt": None,
            "date": turnover.get("asOf") if usable else None,
            "source": turnover["source"],
            "scope": breadth.get("note") or turnover["note"],
        },
        "sample": breadth if usable else None,
        "coverage": turnover.get("coverage"),
        "session": {
            "expectedDate": turnover.get("expectedDate"),
            "current": bool(usable and turnover.get("current")),
            "calendarStatus": turnover.get("calendarStatus"),
            "cached": turnover.get("cached", False),
            "usingSaved": turnover.get("usingSaved", False),
        },
        "sources": {
            "sentiment": {"status": "ready" if usable and turnover.get("current") else "unavailable",
                          "reason": reason, "receivedAt": turnover.get("receivedAt")},
        },
        "sectors": [],
        "updated": turnover.get("generatedAt"),
    }
