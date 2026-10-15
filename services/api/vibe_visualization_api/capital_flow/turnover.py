from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService, iso_date
from vibe_visualization_api.capital_flow.service import finite_number


SOURCE = "Tushare daily · 未复权日线"
NOTE = "统一取昨日及以前最近交易日。仅统计来源返回的沪深北 A 股行情样本，不含无行情标的；不是交易所全市场统计，成交额不等于资金净流入。"
VENUES = {"SH": "上海", "SZ": "深圳", "BJ": "北京"}


def turnover_snapshot(rows: list[dict], names: list[dict], day: str) -> dict:
    catalog = {row["ts_code"]: row for row in names if row.get("ts_code")}
    unique, conflicts = {}, set()
    rejected = duplicates = 0
    for row in rows:
        code = str(row.get("ts_code") or "")
        if iso_date(row.get("trade_date")) != day or not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code):
            rejected += 1
            continue
        # B-share identifiers must not enter the A-share sample.
        if code.startswith(("200", "900")):
            rejected += 1
            continue
        if code in unique:
            duplicates += 1
            if any(unique[code].get(key) != row.get(key) for key in ("amount", "close", "pct_chg")):
                conflicts.add(code)
        unique[code] = row
    stocks = []
    invalid = 0
    for code, row in unique.items():
        amount = finite_number(row.get("amount"))
        if amount is None or amount < 0 or code in conflicts:
            invalid += 1
            continue
        info = catalog.get(code, {})
        stocks.append({"code": code.split(".")[0], "tsCode": code, "name": info.get("name") or code,
                       "industry": info.get("industry") or "", "exchange": code.split(".")[1],
                       "price": finite_number(row.get("close")), "pct": finite_number(row.get("pct_chg")),
                       "amount": amount * 1000})
    stocks.sort(key=lambda row: (-row["amount"], row["tsCode"]))
    valid = bool(stocks) and not (invalid or rejected)
    total = sum(row["amount"] for row in stocks) / 1e8 if valid else None
    top = sum(row["amount"] for row in stocks[:20]) / 1e8 if valid else None
    return {"date": day, "leaders": stocks[:20],
            "summary": {"sampleTurnoverYi": total, "top20TurnoverYi": top,
                        "top20SharePct": top / total * 100 if total and top is not None else None},
            "coverage": {"received": len(rows), "sampleCount": len(stocks), "rejected": rejected,
                         "invalid": invalid, "duplicates": duplicates, "conflicts": len(conflicts),
                         "namesMatched": sum(row["tsCode"] in catalog for row in stocks),
                         "universeVerified": False, "valid": valid},
            "exchanges": [{"id": key, "name": name,
                           "count": sum(row["exchange"] == key for row in stocks),
                           "turnoverYi": sum(row["amount"] for row in stocks if row["exchange"] == key) / 1e8
                           if valid and any(row["exchange"] == key for row in stocks) else None}
                          for key, name in VENUES.items()]}


class TurnoverResearchService(CapitalResearchService):
    page_size = 4000
    max_pages = 5

    async def _pages(self, client, api, params, fields):
        rows = []
        for page in range(self.max_pages):
            response = await client.post("https://api.tushare.pro", json={
                "api_name": api, "token": self.token,
                "params": {**params, "limit": self.page_size, "offset": page * self.page_size}, "fields": fields})
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                # Do not forward provider messages which could contain request credentials.
                raise ValueError(f"{api} 请求未成功，请核对权限或调用额度")
            data = payload.get("data") or {}
            if not set(fields.split(",")).issubset(data.get("fields") or []):
                raise ValueError(f"{api} 返回字段不完整")
            items = data.get("items") or []
            batch = [dict(zip(data["fields"], values)) for values in items]
            if page and batch and batch == rows[-len(batch):]:
                raise ValueError(f"{api} 分页重复，不能确认榜单完整")
            rows.extend(batch)
            if len(items) < self.page_size:
                return rows
        raise ValueError(f"{api} 达到分页上限，不能确认榜单完整")

    async def research(self, *, refresh=False):
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar = await self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"},
                                           "cal_date,is_open", "cal_date", refresh=refresh)
            sessions = sorted(row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1")
            expected = sessions[-1] if sessions else None
            saved, run = await asyncio.to_thread(self.store.read, "capital.turnover.v1", "CN", self.start, self.end)
            now = datetime.now(timezone.utc)
            cached = bool(run and run["end_date"] == expected
                          and (now - datetime.fromisoformat(run["received_at"])).total_seconds() < 300 and not refresh)
            status, reason = run.get("status", "unavailable"), run.get("reason", "")
            if not cached:
                status, reason = "unavailable", "交易日历未确认或 Tushare 未配置"
                if self.token and expected and calendar["status"] == "ready" and not calendar.get("usingSaved"):
                    try:
                        rows = await self._pages(client, "daily", {"trade_date": expected.replace("-", "")},
                                                 "ts_code,trade_date,close,pct_chg,amount")
                        names, name_reason = [], ""
                        try:
                            names = await self._pages(client, "stock_basic", {"list_status": "L"}, "ts_code,name,industry")
                        except (httpx.HTTPError, ValueError):
                            name_reason = "名称目录读取失败，未匹配项显示证券代码"
                        if rows:
                            snapshot = turnover_snapshot(rows, names, expected)
                            snapshot["nameNote"] = name_reason or "名称及行业为当前在市目录，不用于历史成分回测"
                            status = "ready" if snapshot["coverage"]["valid"] else "partial"
                            reason = "" if status == "ready" else "日期、金额或重复记录存在缺口，停止合计及集中度计算"
                            saved = [snapshot]
                            await asyncio.to_thread(self.store.save, "capital.turnover.v1", "CN", saved,
                                                    start=self.start, end=expected, status=status, reason=reason, received_at=now.isoformat())
                        else:
                            status, reason = "empty", "目标交易日尚无日线，保留快照不代表更新成功"
                    except httpx.HTTPError:
                        status, reason = "upstream-error", "成交日线请求失败，保留上次完整分页快照"
                    except ValueError as exc:
                        status, reason = "upstream-error", str(exc) if str(exc).startswith(("daily ", "stock_basic ")) else "成交日线返回格式异常"
                if status not in {"ready", "partial"}:
                    await asyncio.to_thread(self.store.save, "capital.turnover.v1", "CN", [], start=self.start,
                                            end=expected or self.end, status=status, reason=reason, received_at=now.isoformat())
            snapshot = saved[-1] if saved else {}
            current = bool(status == "ready" and snapshot.get("date") == expected and calendar["status"] == "ready" and not calendar.get("usingSaved"))
            using_saved = bool(snapshot) and status not in {"ready", "partial"}
            if calendar["status"] != "ready" or calendar.get("usingSaved"):
                reason = reason or "交易日历未确认，不能将保留行情当作最新交易日数据"
            return {"schemaVersion": "newma-desk.turnover.v1", "generatedAt": now.isoformat(),
                    "asOf": snapshot.get("date"), "expectedDate": expected, "status": status, "current": current,
                    "usingSaved": using_saved, "cached": cached, "reason": reason,
                    "source": SOURCE, "unit": "人民币亿元", "rawUnit": "千元", "note": NOTE,
                    "calendarStatus": calendar["status"], "nameNote": snapshot.get("nameNote", ""),
                    "coverage": snapshot.get("coverage"), "exchanges": snapshot.get("exchanges", []),
                    "leaders": snapshot.get("leaders", []),
                    "summary": snapshot.get("summary", {"sampleTurnoverYi": None, "top20TurnoverYi": None, "top20SharePct": None})}
        finally:
            if owns:
                await client.aclose()


def with_turnover(dashboard: dict, turnover: dict) -> dict:
    dashboard["turnover"] = turnover
    dashboard["turnoverLeaders"] = turnover["leaders"]
    # Legacy summary must not confirm failed/stale updates. Saved figures live in the explicitly dated snapshot.
    dashboard["summary"]["top20TurnoverYi"] = turnover["summary"]["top20TurnoverYi"] if turnover["current"] else None
    market = next(row for row in dashboard["dimensions"] if row["id"] == "market")
    market.update(status="ready" if turnover["current"] else "degraded", frequency="日频", lag="昨日及以前，非盘中",
                  source=SOURCE, asOf=turnover["asOf"], note=NOTE + (turnover["reason"] or ""))
    for driver in dashboard["riskAppetite"]["drivers"]:
        if driver["id"] == "market-activity":
            driver.update(signal="observed" if turnover["current"] else "unavailable", value=None,
                          detail=NOTE, source=SOURCE, asOf=turnover["asOf"])
    dashboard["riskAppetite"]["available"] = sum(row["signal"] != "unavailable" for row in dashboard["riskAppetite"]["drivers"])
    dashboard["upstream"]["status"] = "ready" if all(row["status"] == "ready" for row in dashboard["dimensions"]
        if row["id"] in {"market", "sector", "northbound", "southbound", "liquidity"}) else "degraded"
    return dashboard
