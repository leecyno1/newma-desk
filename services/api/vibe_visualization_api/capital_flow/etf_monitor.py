"""Observable ETF creation/redemption clues, never investor-identity attribution."""
from statistics import median

from .service import finite_number

CSI300_POOL = ("510300.SH", "510310.SH", "510330.SH", "159919.SZ")


def build_etf_monitor(etfs: list[dict], sessions: list[str], calendar_ok: bool) -> dict:
    as_of = sessions[-1] if sessions else None
    baseline_dates = sessions[-21:-1]
    rows = []
    for etf in etfs:
        points = {point["date"]: point for point in etf["points"]}
        latest = points.get(as_of, {})
        def intensity(day):
            point = points.get(day, {})
            return None if point.get("suspectedSplit") or finite_number(point.get("flowYi")) is None else finite_number(point.get("shareChangePct"))
        value = intensity(as_of)
        flow = finite_number(latest.get("flowYi"))
        known = [v for day in baseline_dates if (v := intensity(day)) is not None]
        baseline_ready = len(baseline_dates) == len(known) == 20
        center = median(known) if baseline_ready else None
        mad = median(abs(v - center) for v in known) if baseline_ready else None
        score = (value - center) / (1.4826 * mad) if value is not None and mad is not None and mad > 1e-10 else None
        current = bool(calendar_ok and etf.get("fetchStatus") == "ready" and not etf.get("usingSaved")
                       and etf.get("asOf") == as_of and etf.get("summary", {}).get("strength", {}).get("1", {}).get("current")
                       and value is not None and flow is not None)
        direction = 1 if value is not None and value > 0 else -1 if value is not None and value < 0 else 0
        tail = [intensity(day) for day in sessions[-5:]]
        persistence_ready = len(tail) == 5 and all(v is not None for v in tail)
        same_days = sum(v * direction > 0 for v in tail) if persistence_ready and direction else 0 if persistence_ready else None
        flagged = bool(current and score is not None and score * direction >= 3 and abs(value) >= .1 and abs(flow) >= 1)
        reason = "" if current else "来源更新、日期或当日申赎未确认"
        if not baseline_ready:
            reason += ("；" if reason else "") + "前20交易日基准不完整，不计算异常度"
        elif score is None:
            reason += ("；" if reason else "") + "历史MAD为零或当日值缺失，不计算异常度"
        label = "待核验" if not current or score is None else (
            "大额净申购异常" if flagged and direction > 0 else "大额净赎回异常" if flagged else "未触发阈值")
        rows.append({"code": etf["code"], "name": etf["name"], "source": etf.get("source"),
                     "asOf": as_of, "current": current, "flowYi": flow if current else None,
                     "shareChangePct": value if current else None, "robustZ": round(score, 3) if current and score is not None else None,
                     "baselineSamples": len(known), "baselineExpected": 20, "medianPct": center, "madPct": mad,
                     "sameDirection5d": same_days if current else None,
                     "persistenceComplete": current and persistence_ready, "direction": direction if current else None,
                     "flagged": flagged, "label": label, "reason": reason})
    indexed = {row["code"]: row for row in rows}
    members = [indexed.get(code) for code in CSI300_POOL]
    complete = all(row and row["current"] for row in members)
    positive = sum(row["direction"] == 1 for row in members) if complete else None
    negative = sum(row["direction"] == -1 for row in members) if complete else None
    simultaneous = sum(row["flagged"] for row in members) if complete and all(row["robustZ"] is not None for row in members) else None
    return {"asOf": as_of, "rows": rows,
            "cohort": {"name": "四只沪深300ETF", "codes": list(CSI300_POOL), "expected": 4,
                       "available": sum(bool(row and row["current"]) for row in members), "current": complete,
                       "inflowCount": positive, "outflowCount": negative,
                       "sameDirectionPct": max(positive, negative) / 4 * 100 if complete else None,
                       "flowYi": round(sum(row["flowYi"] for row in members), 4) if complete else None,
                       "abnormalCount": simultaneous,
                       "missingCodes": [code for code, row in zip(CSI300_POOL, members) if not row or not row["current"]]},
            "thresholds": {"baselineDays": 20, "robustZ": 3, "minAbsShareChangePct": .1, "minAbsFlowYi": 1},
            "method": "异常度=(当日份额变化率−前20交易日中位数)/(1.4826×MAD)，基准不含当日，缺日或MAD为零不评分。异常须同向≥3、份额变化绝对值≥0.1%、申赎等值绝对值≥1亿元。持续性为最近5交易日中与当日同向的天数，不等于连续天数。",
            "boundary": "申赎等值=份额变化×同日净值；含实物申赎、套利、做市及份额时点差，不是外部现金流。仅识别可观察异常，不推断汇金、国家队或其他持有人身份，不估算其持仓。阈值为研究规则，未经收益或身份识别验证。"}
