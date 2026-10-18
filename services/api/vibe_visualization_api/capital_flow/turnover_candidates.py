"""Transparent daily turnover screening, with dated cohorts and complete forward paths."""
import asyncio
from datetime import datetime, timedelta, timezone
from math import prod
from statistics import median, quantiles

import httpx

from .service import finite_number
from .turnover_history import DATASET as HISTORY, TurnoverHistoryService

DATASET = "capital.turnover-candidates.v1"
RULE = {"id": "relative-turnover-v1", "baselineDays": 20, "minAmountYi": 1,
        "minOwnRatio": 2, "minMarketAdjustedRatio": 1.5}


def scan(observations, sessions, target, calendar_ready):
    indexed = {row["date"]: row for row in observations}
    position = sessions.index(target)
    window = sessions[max(0, position - 20):position + 1]
    missing = [day for day in window if indexed.get(day, {}).get("status") != "ready"]
    result = {"date": target, "rules": RULE, "current": False, "baselineStart": window[0],
              "baselineEnd": window[-2] if len(window) > 1 else None, "missingDates": missing,
              "eligibleCount": 0, "excludedCount": 0, "marketMedianRatio": None, "candidates": [], "reason": ""}
    if not calendar_ready or len(window) != 21 or missing:
        result["reason"] = "交易日历或信号日前20日基线不完整，不生成候选"
        return result
    latest = indexed[target]
    eligible = []
    for code, amount in latest.get("amounts", {}).items():
        amounts = [finite_number(indexed[day].get("amounts", {}).get(code)) for day in window]
        if any(value is None or value <= 0 for value in amounts):
            continue
        average = sum(amounts[:-1]) / 20
        eligible.append({"code": code, "amountYi": amounts[-1] / 100000, "baselineYi": average / 100000,
                         "ownRatio": amounts[-1] / average,
                         "signalPct": finite_number(latest.get("returns", {}).get(code))})
    result.update(eligibleCount=len(eligible), excludedCount=len(latest.get("amounts", {})) - len(eligible))
    if len(eligible) < 20:
        result["reason"] = "可比较样本不足20只，不计算横截面基准"
        return result
    market_ratio = median(row["ownRatio"] for row in eligible)
    for row in eligible:
        row["marketAdjustedRatio"] = row["ownRatio"] / market_ratio
    result.update(current=True, marketMedianRatio=market_ratio, eligibleCodes=sorted(row["code"] for row in eligible),
                  candidates=sorted([row for row in eligible if row["amountYi"] >= RULE["minAmountYi"]
                                     and row["ownRatio"] >= RULE["minOwnRatio"]
                                     and row["marketAdjustedRatio"] >= RULE["minMarketAdjustedRatio"]],
                                    key=lambda row: (-row["marketAdjustedRatio"], row["code"])))
    return result


def forward_path(code, target, sessions, indexed, days):
    start = sessions.index(target) + 1
    dates = sessions[start:start + days]
    if len(dates) < days:
        return {"days": days, "status": "pending", "end": None, "changePct": None, "reason": "观察期尚未走完"}
    values = [finite_number(indexed.get(day, {}).get("returns", {}).get(code))
              if indexed.get(day, {}).get("status") == "ready" else None for day in dates]
    if any(value is None or value < -100 for value in values):
        return {"days": days, "status": "missing", "end": dates[-1], "changePct": None, "reason": "窗口存在行情缺口，不跳过缺失日"}
    return {"days": days, "status": "ready", "end": dates[-1],
            "changePct": (prod(1 + value / 100 for value in values) - 1) * 100, "reason": ""}


def cohort_summary(candidates, *, scope="全部候选，不随分页变化"):
    """Describe the entire fixed cohort, never a paginated slice or a portfolio return."""
    windows = []
    total = len(candidates)
    for days in (1, 3, 5):
        paths = [next(path for path in row["forward"] if path["days"] == days) for row in candidates]
        values = [finite_number(path["changePct"]) for path in paths if path["status"] == "ready"]
        values = sorted(value for value in values if value is not None)
        valid = len(values)
        pending = sum(path["status"] == "pending" for path in paths)
        missing = total - valid - pending
        up, down = sum(value > 0 for value in values), sum(value < 0 for value in values)
        quartiles = quantiles(values, n=4, method="inclusive") if valid > 1 else values * 3
        windows.append({"days": days, "end": next((path["end"] for path in paths if path["end"]), None),
                        "status": "empty" if not total else "pending" if pending == total else "ready" if valid == total else "partial" if valid else "missing",
                        "total": total, "valid": valid, "missing": missing, "pending": pending,
                        "coveragePct": valid / total * 100 if total else None,
                        "up": up, "flat": valid - up - down, "down": down,
                        "positivePct": up / valid * 100 if valid else None,
                        "medianPct": median(values) if valid else None,
                        "meanPct": sum(values) / valid if valid else None,
                        "p25Pct": quartiles[0] if valid else None, "p75Pct": quartiles[2] if valid else None,
                        "minPct": values[0] if valid else None, "maxPct": values[-1] if valid else None})
    return {"total": total, "scope": scope, "windows": windows,
            "method": "每只股票等计数，按信号后固定1/3/5个交易日的daily日涨跌幅链式变化统计。正收益比例=变化大于0的只数÷有效只数；缺失和未到期不补零、不计入分母。均值、中位数、四分位及极值仅描述有效子样本，四分位采用含端点线性插值。缺失可能带来选择偏差；未逐只核验复权、停牌及成交条件，不是组合收益、交易胜率或策略有效性证明。"}


def compare_cohorts(cohort, summary, target, sessions, indexed):
    eligible = cohort.get("eligibleCodes")
    if eligible is None:
        return {"status": "unavailable", "reason": "旧快照未保存信号日可比较范围，不能还原冻结对照组；不使用当前重算名单替代。", "control": None, "windows": []}
    selected = {row["code"] for row in cohort["candidates"]}
    controls = [{"forward": [forward_path(code, target, sessions, indexed, days) for days in (1, 3, 5)]}
                for code in eligible if code not in selected]
    control = cohort_summary(controls, scope="信号日可比较范围内未入选股票")
    windows = []
    for candidate, other in zip(summary["windows"], control["windows"]):
        complete = candidate["status"] == other["status"] == "ready"
        reason = "" if complete else "任一组无样本，不能比较" if not candidate["total"] or not other["total"] else "观察期未到期" if candidate["pending"] or other["pending"] else "两组样本未齐，不计算差值"
        windows.append({"days": candidate["days"], "end": candidate["end"] or other["end"],
                        "status": "ready" if complete else "unavailable", "reason": reason,
                        "positiveGapPp": candidate["positivePct"] - other["positivePct"] if complete else None,
                        "medianGapPp": candidate["medianPct"] - other["medianPct"] if complete else None,
                        "meanGapPp": candidate["meanPct"] - other["meanPct"] if complete else None})
    return {"status": "ready", "reason": "", "eligibleCount": len(eligible), "control": control, "windows": windows,
            "method": "同一信号日、同一观察窗口。对照为信号日及此前20日均有正成交额、但未命中放量规则的股票；两组互斥，不按后续行情是否齐全重选成分。差值=候选组−非候选组（百分点），仅两组非空且行情完整时计算。没有匹配行业、市值或波动率，不是随机实验、因果效应或风险调整alpha；单日横截面不能证明长期有效。"}


def record_timing(captured_at, signal_date, next_session):
    """A timestamp check, not proof of point-in-time data or an executable signal."""
    if not captured_at:
        return "unknown"
    try:
        captured = datetime.fromisoformat(captured_at)
        zone = timezone(timedelta(hours=8))
        close = datetime.fromisoformat(f"{signal_date}T15:00:00").replace(tzinfo=zone)
        if captured.tzinfo is None or captured < close:
            return "unknown"
        if not next_session:
            return "pending-calendar"
        opening = datetime.fromisoformat(f"{next_session}T09:30:00").replace(tzinfo=zone)
        return "before-open" if captured < opening else "late"
    except ValueError:
        return "unknown"


def track_cohorts(observations, sessions, recorded, calendar_ready):
    indexed = {row["date"]: row for row in observations}
    rows = []
    for day in reversed(sessions[20:]):
        current = scan(observations, sessions, day, calendar_ready)
        saved = recorded.get(day)
        group = saved or current
        position = sessions.index(day)
        next_session = sessions[position + 1] if position + 1 < len(sessions) else None
        timing = record_timing(saved.get("capturedAt"), day, next_session) if saved else "retrospective"
        candidate_rows = [{"forward": [forward_path(row["code"], day, sessions, indexed, days) for days in (1, 3, 5)]}
                          for row in group["candidates"]] if current["current"] else []
        summary = cohort_summary(candidate_rows) if current["current"] else None
        comparison = compare_cohorts(group, summary, day, sessions, indexed) if summary else None
        windows = []
        for days in (1, 3, 5):
            candidate = next((row for row in (summary or {}).get("windows", []) if row["days"] == days), None)
            difference = next((row for row in (comparison or {}).get("windows", []) if row["days"] == days), None)
            ready = bool(difference and difference["status"] == "ready")
            windows.append({"days": days, "end": candidate["end"] if candidate else None,
                            "candidateValid": candidate["valid"] if candidate else None,
                            "medianGapPp": difference["medianGapPp"] if ready else None,
                            "forwardEligible": timing == "before-open" and ready,
                            "reason": "" if ready else current["reason"] or (comparison or {}).get("reason") or (difference or {}).get("reason") or "数据待核验"})
        rows.append({"signalDate": day, "mode": "recorded" if saved else "retrospective", "timing": timing,
                     "capturedAt": saved.get("capturedAt") if saved else None,
                     "nextSession": next_session, "candidateCount": len(group["candidates"]) if current["current"] else None,
                     "current": current["current"], "windows": windows})
    return {"rows": rows, "recordedDays": sum(row["mode"] == "recorded" for row in rows),
            "retrospectiveDays": sum(row["mode"] == "retrospective" for row in rows),
            "forwardCompleteDays": {str(days): sum(window["forwardEligible"] for row in rows for window in row["windows"] if window["days"] == days) for days in (1, 3, 5)},
            "note": "仅最近6个可核验信号日；首次记录可来自页面观察或已启用的收盘采集任务，运行状态见归档面板。入场前记录指信号日收盘后、下一交易日09:30（北京时间）前首次保存；下一交易日尚未进入已取得日历时待判定。只计时间条件满足、两组样本非空且行情完整的日期，不等于策略有效。首次记录并不保证数据在当时可得或可成交。历史重算不写回前向记录；窗口重叠和重复股票不视为独立样本，不合成胜率。"}


class TurnoverCandidatesService(TurnoverHistoryService):
    async def candidates(self, *, signal_date=None, refresh=False):
        # 20 baseline sessions + six selectable signal days, sufficient for a five-day follow-up.
        history = await self.history(25, refresh=refresh)
        sessions = [row["date"] for row in history["points"]]
        selectable = sessions[20:]
        target = signal_date or (sessions[-1] if sessions else None)
        if signal_date and signal_date not in selectable:
            raise ValueError("仅支持当前可选的最近6个信号日")
        observations, _ = await asyncio.to_thread(self.store.read, HISTORY, "CN", self.start, self.end)
        calendar_ready = history["calendarStatus"] == "ready" and not history["reason"] and bool(self.token)
        current = scan(observations, sessions, target, calendar_ready) if target else None
        snapshots, _ = await asyncio.to_thread(self.store.read, DATASET, RULE["id"], self.start, self.end)
        recorded = {row["date"]: row for row in snapshots}
        captured = None
        if current and current["current"]:
            captured = recorded.get(target)
            if not captured and target == sessions[-1]:
                captured = await asyncio.to_thread(self.store.save_once, DATASET, RULE["id"],
                                                   {**current, "capturedAt": datetime.now(timezone.utc).isoformat(), "captureSource": "page-observation"})
                recorded[target] = captured
        cohort = captured or current
        indexed = {row["date"]: row for row in observations}
        rows = [{**row, "forward": [forward_path(row["code"], target, sessions, indexed, days) for days in (1, 3, 5)]}
                for row in (cohort or {}).get("candidates", [])]
        catalog = {"items": [], "receivedAt": None, "usingSaved": False, "reason": ""}
        if rows:
            client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
            try:
                catalog = await self.stock_names(client, refresh=refresh)
            finally:
                if self.client is None:
                    await client.aclose()
        names = {item["ts_code"]: item for item in catalog["items"] if item.get("ts_code")}
        rows = [{**row, "name": names.get(row["code"], {}).get("name") or None} for row in rows]
        summary = cohort_summary(rows) if current and current["current"] else None
        comparison = compare_cohorts(cohort, summary, target, sessions, indexed) if summary else None
        tracking = await asyncio.to_thread(track_cohorts, observations, sessions, recorded, calendar_ready)
        # Full membership remains in the frozen store, not in every page/Agent payload.
        public_cohort = {key: value for key, value in (cohort or {}).items() if key != "eligibleCodes"}
        return {**public_cohort, "current": bool(current and current["current"]), "asOf": sessions[-1] if sessions else None,
                "signalDate": target, "signalDates": list(reversed(selectable)), "generatedAt": history["generatedAt"],
                "mode": "recorded" if captured else "retrospective", "capturedAt": (captured or {}).get("capturedAt"),
                "candidates": rows, "candidateCount": len(rows), "displayLimit": len(rows),
                "cohort": summary, "comparison": comparison, "tracking": tracking,
                "nameCatalog": {"receivedAt": catalog["receivedAt"], "usingSaved": catalog["usingSaved"],
                                "reason": catalog["reason"], "matched": sum(bool(row["name"]) for row in rows),
                                "note": "名称为当前在市目录，仅供识别，不代表信号日名称；未匹配不剔除候选"},
                "completed": history["completed"], "expected": 26, "canContinue": history["canContinue"],
                "reason": (current or {}).get("reason") or history["reason"],
                "source": "Tushare daily / trade_cal；复用成交历史快照",
                "note": "规则为研究筛选而非已验证策略：当日成交≥1亿元、自身前20日均值≥2倍、相对横截面倍数中位数≥1.5倍。基线不含信号日，选股不使用后续日期成分。缺20日正成交的标的排除，会遗漏新股及停牌样本。首次观察记录冻结触发条件，未归档历史标为事后重算；来源修订和披露时滞仍可能造成偏差。后续1/3/5日为daily日涨跌幅的链式变化，不是复权总回报或可实现策略收益，未扣费用滑点；缺失不跳日。成交额不是净流入，不识别账户身份。"}
