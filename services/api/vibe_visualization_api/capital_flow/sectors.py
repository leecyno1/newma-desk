from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService, baseline, window_sum
from vibe_visualization_api.capital_flow.service import finite_number


CATEGORIES = {"industry": "行业", "concept": "概念", "region": "地域"}
FIELDS = "trade_date,content_type,ts_code,name,pct_change,close,net_amount,net_amount_rate,buy_elg_amount,buy_lg_amount"
LEVELS = {"东财一级行业": "L1", "东财二级行业": "L2", "东财三级行业": "L3"}


def classify_boards(boards: list[dict], feed: dict, as_of: str | None, expected: str | None, calendar_ok: bool) -> tuple[list[dict], dict]:
    """Join dated DC codes, never infer a hierarchy from names or a SW taxonomy."""
    records = [row for snapshot in feed.get("rows", []) if snapshot["date"] == as_of
               for row in snapshot.get("boards", []) if row.get("idx_type") == "行业板块" and row.get("date") == as_of]
    indexed: dict[str, set[str]] = {}
    for row in records:
        indexed.setdefault(row.get("ts_code"), set()).add(str(row.get("level") or ""))
    current = bool(calendar_ok and as_of and as_of == expected and feed.get("status") == "ready"
                   and not feed.get("usingSaved") and records)
    result, counts, conflicts = [], {"L1": 0, "L2": 0, "L3": 0, "unknown": 0}, 0
    for board in boards:
        levels = indexed.get(board["code"], set())
        conflict = len(levels) > 1
        raw = next(iter(levels)) if len(levels) == 1 else None
        level = LEVELS.get(raw, "unknown") if current and not conflict else "unknown"
        counts[level] += 1
        conflicts += conflict
        result.append({**board, "level": level, "reportedLevel": raw, "classificationDate": as_of if levels else None,
                       "classificationConflict": conflict})
    return result, {"source": "Tushare dc_index · 东财行业层级", "url": "https://tushare.pro/document/2?doc_id=362",
                    "status": feed.get("status", "unavailable"), "reason": feed.get("reason", ""), "current": current,
                    "usingSaved": feed.get("usingSaved", False), "asOf": as_of if records else None,
                    "total": len(boards), "matched": len(boards) - counts["unknown"], "counts": counts, "conflicts": conflicts,
                    "constituentsVerified": False,
                    "note": "同日东财代码匹配供应商行业层级；分层避免父子行业混计，但成分交叉未核验，不合计全市场净额。"}


def sector_point(row: dict) -> dict:
    def yi(field):
        value = finite_number(row.get(field))
        return round(value / 1e8, 4) if value is not None else None
    return {"date": row["date"], "net": yi("net_amount"), "pct": finite_number(row.get("pct_change")),
            "close": finite_number(row.get("close")), "netSharePct": finite_number(row.get("net_amount_rate")),
            "superNetYi": yi("buy_elg_amount"), "largeNetYi": yi("buy_lg_amount")}


def sector_summary(points: list[dict], sessions: list[str]) -> dict:
    indexed = {point["date"]: point for point in points}
    streak, direction = 0, "unknown"
    for day in reversed(sessions):
        value = finite_number(indexed.get(day, {}).get("net"))
        if value is None:
            break
        current = "in" if value > 0 else "out" if value < 0 else "flat"
        if direction == "unknown":
            direction = current
        if current != direction or current == "flat":
            break
        streak += 1
    def price_change(days):
        if len(sessions) < days:
            return None
        values = [finite_number(indexed.get(day, {}).get("pct")) for day in sessions[-days:]]
        if any(value is None for value in values):
            return None
        result = 1
        for value in values:
            result *= 1 + value / 100
        return round((result - 1) * 100, 4)
    return {"net1dYi": window_sum(points, sessions, "net", 1),
            "net5dYi": window_sum(points, sessions, "net", 5),
            "net20dYi": window_sum(points, sessions, "net", 20),
            "price5dPct": price_change(5), "price20dPct": price_change(20),
            "streak": {"direction": direction, "days": streak}, "baseline": baseline(points, sessions, "net")}


def catalog_rows(rows: list[dict], category: str) -> tuple[list[dict], int]:
    unique = {}
    count = 0
    for row in rows:
        if row.get("content_type") != CATEGORIES[category] or not row.get("ts_code"):
            continue
        count += 1
        code = row["ts_code"]
        point = sector_point(row)
        board = {**point, "code": code, "name": row.get("name") or code,
                 "category": category, "asOf": row["date"], "aggregateSafe": False,
                 "metric": "large-order-net", "source": "Tushare moneyflow_ind_dc / 东财"}
        if code in unique and unique[code] != board:
            # Conflicting duplicates cannot silently become a valid ranking.
            board.update(net=None, pct=None, netSharePct=None, duplicateConflict=True)
        unique[code] = board
    return sorted(unique.values(), key=lambda row: row["net"] if row["net"] is not None else float("-inf"), reverse=True), count - len(unique)


class SectorResearchService(CapitalResearchService):
    async def research(self, *, category="industry", code=None, refresh=False, include_history=True, level="all") -> dict:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar = await self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"},
                                           "cal_date,is_open", "cal_date", refresh=refresh)
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
            expected = sessions[-1] if sessions else None
            catalog = {"rows": [], "status": "unavailable", "reason": "交易日历缺失，未请求板块排名", "usingSaved": False}
            hierarchy = {"rows": [], "status": "unavailable", "reason": "行业层级目录未取得", "usingSaved": False}
            if expected:
                catalog_query = self._dataset(client, "moneyflow_ind_dc", f"catalog:{category}",
                    {"trade_date": expected.replace("-", ""), "content_type": CATEGORIES[category]}, FIELDS,
                    refresh=refresh, group_field="boards")
                if category == "industry":
                    catalog, hierarchy = await asyncio.gather(catalog_query,
                        self._dataset(client, "dc_index", "industry-levels", {"trade_date": expected.replace("-", ""), "idx_type": "行业板块"},
                                      "ts_code,trade_date,name,idx_type,level", refresh=refresh, group_field="boards"))
                else:
                    catalog = await catalog_query
            days = sorted(catalog["rows"], key=lambda row: row["date"])
            latest = days[-1] if days else {}
            boards, duplicates = catalog_rows(latest.get("boards", []), category)
            classification = None
            if category == "industry":
                boards, classification = classify_boards(boards, hierarchy, latest.get("date"), expected, calendar["status"] == "ready")
                if level != "all":
                    boards = [row for row in boards if row["level"] == level]
                classification.update(selectedLevel=level, selectedCount=len(boards))
            else:
                level = "all"
            chosen = next((row for row in boards if row["code"] == code), None) if code else next(iter(boards), None)
            selected = None
            if chosen and include_history:
                history = await self._dataset(client, "moneyflow_ind_dc", chosen["code"],
                    {"ts_code": chosen["code"], "content_type": CATEGORIES[category]}, FIELDS, refresh=refresh)
                points = [sector_point(row) for row in history["rows"]
                          if row.get("ts_code") == chosen["code"] and row.get("content_type") == CATEGORIES[category]]
                summary = sector_summary(points, sessions)
                selected = {"code": chosen["code"], "name": chosen["name"], "points": points,
                            "summary": summary, "asOf": points[-1]["date"] if points else None,
                            "fetchStatus": history["status"], "sourceNote": history["reason"],
                            "usingSaved": history["usingSaved"],
                            "status": "ready" if history["status"] == "ready" and summary["net1dYi"] is not None
                                      else "partial" if points else "unavailable"}
            return {"schemaVersion": "newma-desk.sector-research.v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "source": "Tushare moneyflow_ind_dc / 东财", "category": category, "categoryLabel": CATEGORIES[category],
                    "expectedDate": expected, "asOf": latest.get("date"), "boards": boards, "selected": selected,
                    "level": level, "classification": classification,
                    "calendar": {"status": calendar["status"], "reason": calendar["reason"], "dates": sessions[-60:]},
                    "coverage": {"status": catalog["status"], "reason": catalog["reason"],
                                 "usingSaved": catalog["usingSaved"], "duplicatesRemoved": duplicates,
                                 "classified": len(boards), "aggregateSafe": False,
                                 "hierarchyVerified": bool(classification and classification["current"] and classification["matched"] == classification["total"]),
                                 "selectedNotFound": bool(code and not chosen)},
                    "notes": ["行业、概念、地域分开请求；按同一分类的板块代码去重，不按名称猜分类",
                              "行业按同日dc_index代码匹配东财一级/二级/三级；未知单列，不按名称猜测，也不是申万分类",
                              "同层级仍未独立核验成分交叉，一级/二级/三级不可相加，不合计为全市场净流",
                              "主力是供应商订单大小分类，不是机构账户，也不是ETF一级市场申赎",
                              "严格交易日1/5/20日窗口；缺失不补零，连续天数遇缺失中断；分位不是风险概率",
                              "价格窗口复合日涨跌幅；供应商指数成分调整未独立核验，不是策略回测"]}
        finally:
            if owns:
                await client.aclose()
