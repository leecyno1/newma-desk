"""Dated, non-ST limit-board pools; never infer a pool from price thresholds."""
import asyncio
import re
from collections import Counter
from datetime import datetime, timezone

import httpx

from .research import iso_date
from .service import finite_number
from .turnover import TurnoverResearchService
from .board_quotes import DAILY_FIELDS, LIMIT_FIELDS, verify_cohort

DATASET = "capital.limit-boards.v1"
FIELDS = "trade_date,ts_code,name,industry,limit,limit_times,open_times,first_time,last_time"


def integer(value, minimum=0):
    number = finite_number(value)
    return int(number) if number is not None and number >= minimum and number.is_integer() else None


def pool_snapshot(rows: list[dict], day: str) -> dict:
    items, rejected, duplicates, conflicts = {}, 0, 0, set()
    for row in rows:
        code, kind = str(row.get("ts_code") or ""), row.get("limit")
        if iso_date(row.get("trade_date")) != day or not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code) or kind not in {"U", "D", "Z"}:
            rejected += 1
            continue
        item = {"code": code, "name": row.get("name") or code, "industry": row.get("industry") or "未提供",
                "kind": kind, "boards": integer(row.get("limit_times"), 1) if kind == "U" else None,
                "openTimes": integer(row.get("open_times")), "firstTime": row.get("first_time"), "lastTime": row.get("last_time")}
        if code in items:
            duplicates += 1
            if items[code] != item:
                conflicts.add(code)
        items[code] = item
    valid = not rejected and not conflicts
    return {"date": day, "status": "ready" if valid else "invalid", "items": list(items.values()) if valid else [],
            "reason": "" if valid else "名单包含日期、代码、分类或重复冲突，停止计数与比率计算",
            "coverage": {"received": len(rows), "duplicates": duplicates, "rejected": rejected, "conflicts": len(conflicts)}}


def follow_previous(current: dict, previous: dict, ready: bool) -> dict:
    """Track yesterday's cohort; absence from these pools is not a verified break."""
    note = "按昨日涨停股逐股核对今日三池；仅凭未入三池不能认定断板、下跌或停牌，需另看同日行情核验。续封不等于连板数晋级；层级只使用昨日来源值。"
    if not ready or previous.get("status") != "ready":
        return {"ready": False, "reason": "两日名单未同时就绪，暂不判断昨日涨停去向", "note": note,
                "rows": [], "tiers": [], "summary": None, "unmatchedContinuations": []}
    today = {row["code"]: row for row in current["items"]}
    yesterday = [row for row in previous["items"] if row["kind"] == "U"]
    rows, tiers = [], {}
    for old in sorted(yesterday, key=lambda row: (-(row["boards"] or 0), row["code"])):
        new = today.get(old["code"])
        outcome = new["kind"] if new else "absent"
        comparable = outcome == "U" and old["boards"] is not None and new["boards"] is not None
        mismatch = comparable and new["boards"] != old["boards"] + 1
        rows.append({"code": old["code"], "name": new["name"] if new else old["name"],
                     "industry": new["industry"] if new else old["industry"], "previousBoards": old["boards"],
                     "currentBoards": new["boards"] if new else None, "outcome": outcome,
                     "progression": "mismatch" if mismatch else "matched" if comparable else "unknown"})
        tier = tiers.setdefault(old["boards"], {"boards": old["boards"], "total": 0, "U": 0, "Z": 0, "D": 0, "absent": 0})
        tier["total"] += 1
        tier[outcome] += 1
    old_codes = {row["code"] for row in yesterday}
    unmatched = [row for row in current["items"] if row["kind"] == "U" and (row["boards"] or 0) >= 2 and row["code"] not in old_codes]
    return {"ready": True, "reason": "", "note": note, "rows": rows,
            "tiers": [{**tier, "retentionRatePct": tier["U"] / tier["total"] * 100} for tier in tiers.values()],
            "summary": {"total": len(rows), **{key: sum(row["outcome"] == key for row in rows) for key in ("U", "Z", "D", "absent")},
                        "mismatches": sum(row["progression"] == "mismatch" for row in rows)},
            "unmatchedContinuations": unmatched}


def board_analysis(current: dict, previous: dict, calendar_ready: bool) -> dict:
    ready = calendar_ready and current.get("status") == "ready"
    items = current.get("items", []) if ready else []
    up = [row for row in items if row["kind"] == "U"]
    down = [row for row in items if row["kind"] == "D"]
    broken = [row for row in items if row["kind"] == "Z"]
    tiers = Counter(row["boards"] for row in up if row["boards"] is not None)
    old_up = {row["code"] for row in previous.get("items", []) if row["kind"] == "U"} if previous.get("status") == "ready" else None
    retained = len(old_up & {row["code"] for row in up}) if ready and old_up is not None else None
    attempts = len(up) + len(broken)
    return {"current": ready, "asOf": current.get("date"), "previousDate": previous.get("date"),
            "status": "ready" if ready else "unavailable", "reason": current.get("reason") or ("" if calendar_ready else "交易日历未确认"),
            "summary": {"up": len(up) if ready else None, "down": len(down) if ready else None,
                        "broken": len(broken) if ready else None, "attempts": attempts if ready else None,
                        "sealRatePct": len(up) / attempts * 100 if ready and attempts else None,
                        "breakRatePct": len(broken) / attempts * 100 if ready and attempts else None,
                        "knownMaxBoards": max(tiers) if tiers else None,
                        "unknownBoards": sum(row["boards"] is None for row in up) if ready else None,
                        "reopenedUp": sum(row["openTimes"] > 0 for row in up) if ready and all(row["openTimes"] is not None for row in up) else None,
                        "previousUp": len(old_up) if calendar_ready and old_up is not None else None,
                        "retainedUp": retained, "retentionRatePct": retained / len(old_up) * 100 if retained is not None and old_up else None},
            "ladder": [{"boards": boards, "count": count} for boards, count in sorted(tiers.items(), reverse=True)],
            "items": sorted(items, key=lambda row: (-(row["boards"] or 0), row["code"])),
            "tracking": follow_previous(current, previous, ready),
            "coverage": current.get("coverage"), "previousStatus": previous.get("status", "unavailable"),
            "note": "Tushare limit_list_d：来源不含ST股票，不代表全部A股。U=涨停、D=跌停、Z=炸板；同日名单按代码去重，跨分类冲突不计算。收盘封住占比=U/(U+Z)，炸板占比=Z/(U+Z)，均为名单分类口径。开板回封是U中open_times>0的股票，不加入Z。昨日涨停续封率=前后两交易日U名单交集/昨日U名单，不是各梯队晋级率。连板数仅用来源limit_times，缺失不默认首板；均为日终研究，非盘中交易信号。"}


class LimitBoardsService(TurnoverResearchService):
    page_size = 1000  # Official limit_list_d cap is 2500; retain explicit pagination below it.

    async def verify_quotes(self, client, current, tracking, now, refresh):
        codes = sorted(row["code"] for row in tracking["rows"])
        saved = current.get("quoteCheck", {})
        if not refresh and saved.get("codes") == codes and saved.get("asOf") == current["date"] and saved.get("receivedAt") and (now - datetime.fromisoformat(saved["receivedAt"])).total_seconds() < 300:
            return saved

        async def fetch(api, fields, params):
            try:
                rows = await asyncio.wait_for(self._pages(client, api, params, fields, page_size=4000), 25)
                return {"status": "ready", "rows": rows}
            except (httpx.HTTPError, ValueError, TimeoutError):
                return {"status": "unavailable", "rows": []}

        params = {"trade_date": current["date"].replace("-", "")}
        # daily explicitly supports comma-separated codes; stk_limit is paginated by day.
        daily, limits = await asyncio.gather(fetch("daily", DAILY_FIELDS, {**params, "ts_code": ",".join(codes)}),
                                             fetch("stk_limit", LIMIT_FIELDS, params))
        check = {**verify_cohort(tracking["rows"], current["date"], daily, limits), "codes": codes, "receivedAt": now.isoformat()}
        current["quoteCheck"] = check
        await asyncio.to_thread(self.store.save, DATASET, "CN", [current], start=current["date"], end=current["date"],
                                status=current["status"], reason=current["reason"], received_at=current["receivedAt"])
        return check

    async def research(self, *, refresh=False):
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar = await self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh)
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})[-2:]
            calendar_ready = bool(sessions) and calendar["status"] == "ready" and not calendar.get("usingSaved")
            saved, _ = await asyncio.to_thread(self.store.read, DATASET, "CN", self.start, self.end)
            indexed = {row["date"]: row for row in saved}
            now = datetime.now(timezone.utc)

            async def fetch_day(day):
                prior = indexed.get(day, {})
                cached = bool(prior.get("receivedAt") and (now - datetime.fromisoformat(prior["receivedAt"])).total_seconds() < 300)
                if cached and not refresh:
                    return prior
                try:
                    rows = await asyncio.wait_for(self._pages(client, "limit_list_d", {"trade_date": day.replace("-", "")}, FIELDS), 25)
                    result = pool_snapshot(rows, day)
                    # An entirely empty daily response cannot establish that all three pools have zero members.
                    if not rows:
                        result.update(status="empty", reason="目标日三类名单均为空，尚不能确认已发布，不按零市场展示")
                except (httpx.HTTPError, ValueError, TimeoutError):
                    result = {"date": day, "status": "unavailable", "items": [], "reason": "limit_list_d 请求或分页失败，请核对权限、额度或来源状态；不展示保留旧名单"}
                result["receivedAt"] = now.isoformat()
                await asyncio.to_thread(self.store.save, DATASET, "CN", [result], start=day, end=day,
                                        status=result["status"], reason=result["reason"], received_at=now.isoformat())
                return result

            results = await asyncio.gather(*(fetch_day(day) for day in sessions)) if calendar_ready and self.token else []
            current = results[-1] if results else {"date": sessions[-1] if sessions else None, "status": "unavailable", "reason": "交易日历未确认或Tushare未配置"}
            previous = results[-2] if len(results) > 1 else {"status": "unavailable"}
            analysis = board_analysis(current, previous, calendar_ready)
            if analysis["tracking"]["ready"] and analysis["tracking"]["rows"]:
                analysis["tracking"]["quoteVerification"] = await self.verify_quotes(client, current, analysis["tracking"], now, refresh)
            return {**analysis, "source": "Tushare limit_list_d / trade_cal · 不含ST",
                    "generatedAt": now.isoformat(), "receivedAt": current.get("receivedAt"), "calendarStatus": calendar["status"]}
        finally:
            if owns:
                await client.aclose()
